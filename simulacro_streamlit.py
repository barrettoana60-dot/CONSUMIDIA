import streamlit as st
import cv2
import mediapipe as mp
import numpy as np
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import av
import threading

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🎯 Iris Ball Tracker",
    page_icon="👁️",
    layout="wide",
)

st.markdown("""
<style>
    .main { background-color: #0d0d1a; color: #e0e0ff; }
    .stApp { background-color: #0d0d1a; }
    h1 { color: #7eb8f7; text-align: center; font-size: 2.5rem; }
    .info-box {
        background: #1a1a2e;
        border: 1px solid #4a4aff;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .stat-value { color: #7eb8f7; font-size: 1.4rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ─── MediaPipe Indices ───────────────────────────────────────────────────────────
LEFT_IRIS  = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361,
             288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
             150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]

# ─── RTC Config ─────────────────────────────────────────────────────────────────
RTC_CONFIG = RTCConfiguration({
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ]
})

# ─── 3D Ball Drawing ─────────────────────────────────────────────────────────────

def draw_3d_ball(frame: np.ndarray, center: tuple, radius: int = 45,
                 color_hsv: tuple = (210, 220, 255)) -> np.ndarray:
    cx, cy = int(center[0]), int(center[1])
    h, w = frame.shape[:2]
    cx = max(radius, min(w - radius, cx))
    cy = max(radius, min(h - radius, cy))

    hsv_base = np.uint8([[[color_hsv[0], color_hsv[1], color_hsv[2]]]])
    base_bgr = cv2.cvtColor(hsv_base, cv2.COLOR_HSV2BGR)[0][0].tolist()

    hsv_dark = np.uint8([[[color_hsv[0], min(255, color_hsv[1] + 30), max(0, color_hsv[2] - 90)]]])
    dark_bgr = cv2.cvtColor(hsv_dark, cv2.COLOR_HSV2BGR)[0][0].tolist()

    overlay = frame.copy()

    # Shadow
    cv2.ellipse(overlay,
                (cx + radius // 4, cy + radius - 4),
                (int(radius * 1.1), int(radius * 0.35)),
                0, 0, 360, (10, 10, 10), -1)

    # Main sphere body
    cv2.circle(overlay, (cx, cy), radius, base_bgr, -1)

    # Shading gradient layers
    for i in range(radius, 0, -5):
        alpha_factor = (radius - i) / radius
        shade = [int(base_bgr[c] + alpha_factor * (dark_bgr[c] - base_bgr[c])) for c in range(3)]
        off = int((radius - i) * 0.35)
        cv2.circle(overlay, (cx + off, cy + off), i, shade, -1)

    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    # Specular highlights
    hl_x = cx - radius // 3
    hl_y = cy - radius // 3
    cv2.circle(frame, (hl_x, hl_y), max(4, radius // 4), (255, 255, 255), -1)
    cv2.circle(frame, (hl_x + 3, hl_y + 3), max(8, radius // 2), (220, 220, 255), -1)

    # Rim light
    cv2.circle(frame, (cx, cy), radius, (150, 180, 255), 2, cv2.LINE_AA)
    return frame


def draw_face_mesh_minimal(frame, landmarks, w, h):
    for idx in FACE_OVAL:
        lm = landmarks.landmark[idx]
        cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 1, (80, 80, 160), -1)
    pts = np.array([
        [int(landmarks.landmark[i].x * w), int(landmarks.landmark[i].y * h)]
        for i in FACE_OVAL
    ], dtype=np.int32)
    cv2.polylines(frame, [pts], True, (60, 60, 140), 1, cv2.LINE_AA)


# ─── Video Processor ─────────────────────────────────────────────────────────────

class IrisBallProcessor(VideoProcessorBase):
    """
    FaceMesh é criado LAZILY dentro do recv() para evitar o crash de
    inicialização de thread do MediaPipe 0.10+ no Streamlit Cloud.
    """

    def __init__(self):
        # ⚠️  NÃO crie FaceMesh aqui — causa crash na thread do webrtc
        self._face_mesh = None
        self._lock = threading.Lock()

        self.ball_x: float = 320.0
        self.ball_y: float = 240.0
        self.smoothing: float = 0.25
        self.ball_color_hsv = (210, 220, 255)
        self.ball_radius: int = 45
        self.show_mesh: bool = True
        self.detected: bool = False

    def _get_face_mesh(self):
        """Cria o FaceMesh na primeira chamada (lazy + thread-safe)."""
        if self._face_mesh is None:
            with self._lock:
                if self._face_mesh is None:          # double-checked locking
                    self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                        max_num_faces=1,
                        refine_landmarks=True,       # habilita landmarks da íris
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5,
                    )
        return self._face_mesh

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]

        face_mesh = self._get_face_mesh()
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if results.multi_face_landmarks:
            self.detected = True
            face_lm = results.multi_face_landmarks[0]

            if self.show_mesh:
                draw_face_mesh_minimal(img, face_lm, w, h)

            def iris_center(indices):
                pts = np.array([
                    [face_lm.landmark[i].x * w, face_lm.landmark[i].y * h]
                    for i in indices
                ])
                return pts.mean(axis=0)

            lc = iris_center(LEFT_IRIS)
            rc = iris_center(RIGHT_IRIS)
            iris_avg = (lc + rc) / 2.0

            # Desenhar pontos da íris
            cv2.circle(img, (int(lc[0]), int(lc[1])), 3, (0, 255, 180), -1)
            cv2.circle(img, (int(rc[0]), int(rc[1])), 3, (0, 255, 180), -1)

            # Normalizar posição e amplificar range do olhar
            norm_x = np.clip((iris_avg[0] / w - 0.5) * 2.0 * 2.2, -1, 1)
            norm_y = np.clip((iris_avg[1] / h - 0.5) * 2.0 * 2.2, -1, 1)

            target_x = (norm_x + 1) / 2.0 * w
            target_y = (norm_y + 1) / 2.0 * h

            # EMA smoothing
            self.ball_x += self.smoothing * (target_x - self.ball_x)
            self.ball_y += self.smoothing * (target_y - self.ball_y)

        else:
            self.detected = False

        # Desenhar bola 3D
        img = draw_3d_ball(
            img,
            (self.ball_x, self.ball_y),
            radius=self.ball_radius,
            color_hsv=self.ball_color_hsv,
        )

        # HUD
        status_color = (0, 255, 120) if self.detected else (0, 80, 255)
        cv2.putText(img, "TRACKING" if self.detected else "SEARCHING...",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, status_color, 2, cv2.LINE_AA)
        cv2.putText(img, f"X:{int(self.ball_x):4d}  Y:{int(self.ball_y):4d}",
                    (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 255), 1, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


# ─── Sidebar Controls ────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Controles")
    ball_radius = st.slider("Raio da Bola", 20, 100, 45)
    smoothing   = st.slider("Suavização (menor = mais fluido)", 0.05, 1.0, 0.25)
    show_mesh   = st.checkbox("Mostrar malha facial", value=True)

    st.markdown("### 🎨 Cor da Bola (HSV)")
    hue = st.slider("Matiz (Hue)", 0, 179, 210)
    sat = st.slider("Saturação",   0, 255, 220)
    val = st.slider("Brilho",      0, 255, 255)

    st.markdown("---")
    st.markdown("""
**Como funciona:**
- MediaPipe detecta 478 pontos do rosto
- Pontos 469–477 são exclusivos da íris
- A média das duas íris controla a bola 3D
- Suavização EMA evita tremidos

**Dica:** Mova os olhos devagar para os lados!
    """)

# ─── Main UI ─────────────────────────────────────────────────────────────────────

st.markdown("# 👁️ Iris Ball Tracker 3D")
st.markdown(
    '<div class="info-box">Controle a bola 3D <b>apenas com o movimento dos seus olhos</b>. '
    'Permita acesso à câmera e olhe em diferentes direções.</div>',
    unsafe_allow_html=True
)

col1, col2 = st.columns([3, 1])

with col1:
    ctx = webrtc_streamer(
        key="iris-tracker",
        video_processor_factory=IrisBallProcessor,
        rtc_configuration=RTC_CONFIG,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )

    if ctx.video_processor:
        ctx.video_processor.ball_radius    = ball_radius
        ctx.video_processor.smoothing      = smoothing
        ctx.video_processor.show_mesh      = show_mesh
        ctx.video_processor.ball_color_hsv = (hue, sat, val)

with col2:
    st.markdown("### 📊 Info")
    st.markdown("""
<div class="info-box">
  <b>Landmarks usados:</b><br>
  <span class="stat-value">469–477</span><br>
  <small>Íris esquerda e direita</small><br><br>
  <b>Modelo:</b><br>
  <span class="stat-value">FaceMesh</span><br>
  <small>refine_landmarks=True</small><br><br>
  <b>Pontos totais:</b><br>
  <span class="stat-value">478</span>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 🎮 Como usar")
    st.markdown("""
- 👁️ **Esq/Dir** → bola horizontal
- 👁️ **Cima/Baixo** → bola vertical
- 🔵 Ajuste o **raio** e **cor** no sidebar
""")

st.markdown("---")
st.markdown(
    "<center><small>Feito com ❤️ usando Streamlit + MediaPipe + OpenCV</small></center>",
    unsafe_allow_html=True
)
