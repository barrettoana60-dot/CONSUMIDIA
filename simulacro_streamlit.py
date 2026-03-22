# ============================================================
#  simulacro_streamlit.py  —  Face & Eye Tracking 3D + Heatmap
#  Compatível com mediapipe >= 0.10.30 (Tasks API) + Python 3.13
#  Deps: streamlit, streamlit-webrtc, mediapipe, opencv-python-headless,
#        plotly, matplotlib, reportlab, scipy, av
# ============================================================

import os, io, time, threading, urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import cv2
import streamlit as st
import av

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import (
    FaceLandmarker, FaceLandmarkerOptions, RunningMode
)

from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase

import plotly.graph_objects as go
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Image as RLImage, Spacer, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet

# ───────────────────────── Configurações ─────────────────────
MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = "face_landmarker.task"

W, H            = 640, 480
HEATMAP_SIGMA   = 25   # suavização gaussiana (pixels)
REFRESH_INTERVAL = 1.0  # segundos entre reruns automáticos

# Índices de pontos-chave do Face Mesh (478 pts)
FACE_OVAL = [
    10,338,297,332,284,251,389,356,454,323,361,288,
    397,365,379,378,400,377,152,148,176,149,150,136,
    172,58,132,93,234,127,162,21,54,103,67,109
]
RIGHT_EYE = [33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246]
LEFT_EYE  = [362,382,381,380,374,373,390,249,263,466,388,387,386,385,384,398]
# Índice 468 = iris direito centro, 473 = iris esquerdo centro
RIGHT_IRIS, LEFT_IRIS = 468, 473

# ───────────────────── Carrega modelo (cache) ─────────────────
@st.cache_resource(show_spinner="Baixando modelo MediaPipe…")
def load_landmarker():
    if not os.path.exists(MODEL_PATH):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    opts = FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    return FaceLandmarker.create_from_options(opts)

# ──────────────────── Processador de vídeo ───────────────────
class FaceTrackingProcessor(VideoProcessorBase):

    def __init__(self):
        self._lm  = load_landmarker()
        self.lock = threading.Lock()
        # dados acumulados
        self.gaze_points: list[tuple[float, float]] = []
        self.latest_landmarks: list[tuple[float,float,float]] | None = None
        self.face_detected  = False
        self.frame_count    = 0
        self.active         = False   # controlado pela UI

    # ── processa cada frame ───────────────────────────────────
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = self._lm.detect(mp_img)

        if not result.face_landmarks:
            cv2.putText(img, "ROSTO NAO DETECTADO", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
            with self.lock:
                self.face_detected = False
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        raw = result.face_landmarks[0]
        n   = len(raw)
        lms = [(lm.x, lm.y, lm.z) for lm in raw]

        # ── desenha micropontos ──────────────────────────────
        for lm in raw:
            px, py = int(lm.x * w), int(lm.y * h)
            cv2.circle(img, (px, py), 1, (0, 255, 100), -1)

        # ── contorno do rosto ───────────────────────────────
        oval_pts = np.array(
            [(int(raw[i].x * w), int(raw[i].y * h))
             for i in FACE_OVAL if i < n], dtype=np.int32
        )
        if len(oval_pts) > 2:
            cv2.polylines(img, [oval_pts], True, (0, 220, 255), 1)

        # ── olhos ───────────────────────────────────────────
        for idx_list, col in [(RIGHT_EYE, (255,120,0)), (LEFT_EYE, (255,120,0))]:
            eye_pts = np.array(
                [(int(raw[i].x * w), int(raw[i].y * h))
                 for i in idx_list if i < n], dtype=np.int32
            )
            if len(eye_pts) > 2:
                cv2.polylines(img, [eye_pts], True, col, 1)

        # ── iris / gaze ─────────────────────────────────────
        gaze = None
        if n >= 478:
            ri = raw[RIGHT_IRIS]
            li = raw[LEFT_IRIS]
            gaze = ((ri.x + li.x) / 2, (ri.y + li.y) / 2)

            # desenha iris
            for iris in (ri, li):
                cv2.circle(img,
                           (int(iris.x * w), int(iris.y * h)),
                           8, (50, 50, 255), 2)

            # mira do olhar
            gx, gy = int(gaze[0] * w), int(gaze[1] * h)
            cv2.drawMarker(img, (gx, gy), (0, 0, 255),
                           cv2.MARKER_CROSS, 24, 2)
            cv2.circle(img, (gx, gy), 12, (255, 255, 0), 1)
        elif n > 0:
            # fallback: ponto do nariz
            nose = raw[1]
            gaze = (nose.x, nose.y)

        # ── HUD ─────────────────────────────────────────────
        status = "TRACKING ATIVO" if self.active else "PAUSADO"
        col_hud = (0, 255, 100) if self.active else (0, 150, 255)
        cv2.putText(img, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, col_hud, 2)
        cv2.putText(img, f"Pts: {len(self.gaze_points)}", (10, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # ── acumula dados ────────────────────────────────────
        with self.lock:
            self.face_detected = True
            self.latest_landmarks = lms
            self.frame_count += 1
            if self.active and gaze:
                self.gaze_points.append(gaze)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


# ──────────────────────── Heatmap ────────────────────────────
def make_heatmap_array(gaze_points: list, w=W, h=H, sigma=HEATMAP_SIGMA):
    grid = np.zeros((h, w), dtype=np.float32)
    for (nx, ny) in gaze_points:
        px = int(np.clip(nx * w, 0, w - 1))
        py = int(np.clip(ny * h, 0, h - 1))
        grid[py, px] += 1.0
    grid = gaussian_filter(grid, sigma=sigma)
    return grid


def plot_heatmap(gaze_points: list, title="Mapa de Calor do Olhar") -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7, 5.5), facecolor="#0e0e1a")
    ax.set_facecolor("#0e0e1a")

    if gaze_points:
        grid = make_heatmap_array(gaze_points)
        vmax = grid.max() or 1
        ax.imshow(
            grid, cmap="inferno", origin="upper",
            extent=[0, 1, 1, 0], aspect="auto",
            vmin=0, vmax=vmax, alpha=0.92
        )
        # pontos brutos
        xs = [p[0] for p in gaze_points[-200:]]  # últimos 200
        ys = [p[1] for p in gaze_points[-200:]]
        ax.scatter(xs, ys, s=3, c="white", alpha=0.25, linewidths=0)

        # centróide
        cx, cy = np.mean(xs), np.mean(ys)
        ax.plot(cx, cy, "o", ms=12, mec="cyan", mfc="none", mew=2, label="Centróide")
        ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=9)

    ax.set_xlim(0, 1); ax.set_ylim(1, 0)
    ax.set_xlabel("X normalizado", color="white", fontsize=10)
    ax.set_ylabel("Y normalizado", color="white", fontsize=10)
    ax.set_title(title, color="white", fontsize=13, pad=10)
    ax.tick_params(colors="white")
    for sp in ax.spines.values():
        sp.set_edgecolor("#444")
    plt.tight_layout()
    return fig


# ──────────────────── Mapa 3D de landmarks ───────────────────
def plot_3d_landmarks(landmarks: list) -> go.Figure:
    xs = [l[0] for l in landmarks]
    ys = [-l[1] for l in landmarks]          # flip Y
    zs = [-l[2] for l in landmarks]

    zmin, zmax = min(zs), max(zs)
    znorm = [(z - zmin) / (zmax - zmin + 1e-9) for z in zs]

    # separa iris (se existirem)
    n = len(landmarks)
    traces = []

    # micropontos principais
    traces.append(go.Scatter3d(
        x=xs[:468], y=zs[:468], z=ys[:468],
        mode="markers",
        marker=dict(size=2, color=znorm[:468],
                    colorscale="Viridis", opacity=0.85,
                    colorbar=dict(title="Prof.", thickness=10)),
        name="Face mesh",
        hovertemplate="x:%{x:.3f}  y:%{z:.3f}  z:%{y:.3f}<extra></extra>"
    ))

    # iris (vermelho)
    if n >= 478:
        ix = [xs[468], xs[473]]
        iy = [ys[468], ys[473]]
        iz = [zs[468], zs[473]]
        traces.append(go.Scatter3d(
            x=ix, y=iz, z=iy,
            mode="markers+text",
            marker=dict(size=7, color="red", symbol="circle"),
            text=["Iris D", "Iris E"],
            textfont=dict(color="red", size=10),
            name="Iris",
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        scene=dict(
            xaxis=dict(title="X", showbackground=False, color="white"),
            yaxis=dict(title="Profund.", showbackground=False, color="white"),
            zaxis=dict(title="Y", showbackground=False, color="white"),
            bgcolor="rgba(0,0,0,0)",
            camera=dict(eye=dict(x=0, y=-1.8, z=0.5))
        ),
        paper_bgcolor="rgba(14,14,26,1)",
        font_color="white",
        title=dict(text="Mapa 3D de Landmarks Faciais", font=dict(size=14)),
        legend=dict(bgcolor="rgba(30,30,50,0.8)"),
        margin=dict(l=0, r=0, b=0, t=50),
        height=500,
    )
    return fig


# ────────────────────── Relatório PDF ────────────────────────
def generate_pdf(gaze_points, session_start, frame_count) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()
    story  = []

    # ── cabeçalho ─────────────────────────────────────────
    story.append(Paragraph("Relatório de Rastreamento Ocular", styles["Title"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 0.6*cm))

    # ── informações da sessão ─────────────────────────────
    story.append(Paragraph("Informações da Sessão", styles["Heading2"]))
    story.append(Spacer(1, 0.2*cm))

    dur = 0
    if session_start:
        dur = max(0, (datetime.now() - session_start).seconds)

    session_data = [
        ["Campo", "Valor"],
        ["Início da sessão", session_start.strftime("%H:%M:%S") if session_start else "—"],
        ["Duração (s)",        str(dur)],
        ["Frames analisados",  str(frame_count)],
        ["Pontos de olhar",    str(len(gaze_points))],
        ["Taxa de captura",    f"{len(gaze_points)/max(dur,1):.1f} pts/s"],
    ]
    t = Table(session_data, colWidths=[7*cm, 10*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#1a1a4e")),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",    (0, 1), (0, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f4f4f8")]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#aaaacc")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.8*cm))

    # ── heatmap ───────────────────────────────────────────
    story.append(Paragraph("Mapa de Calor do Olhar", styles["Heading2"]))
    story.append(Spacer(1, 0.2*cm))

    hm_fig = plot_heatmap(gaze_points, title="Mapa de Calor — Sessão Completa")
    img_buf = io.BytesIO()
    hm_fig.savefig(img_buf, format="png", dpi=120, bbox_inches="tight",
                   facecolor="#0e0e1a")
    plt.close(hm_fig)
    img_buf.seek(0)
    story.append(RLImage(img_buf, width=15*cm, height=11.5*cm))
    story.append(Spacer(1, 0.8*cm))

    # ── estatísticas ──────────────────────────────────────
    if gaze_points:
        story.append(Paragraph("Estatísticas Descritivas", styles["Heading2"]))
        story.append(Spacer(1, 0.2*cm))
        xs = [p[0] for p in gaze_points]
        ys = [p[1] for p in gaze_points]

        # Quadrantes (dividido em 4)
        q1 = sum(1 for x,y in gaze_points if x<=0.5 and y<=0.5)
        q2 = sum(1 for x,y in gaze_points if x> 0.5 and y<=0.5)
        q3 = sum(1 for x,y in gaze_points if x<=0.5 and y> 0.5)
        q4 = sum(1 for x,y in gaze_points if x> 0.5 and y> 0.5)
        total = len(gaze_points)

        stats_data = [
            ["Métrica", "X", "Y"],
            ["Média",          f"{np.mean(xs):.3f}",  f"{np.mean(ys):.3f}"],
            ["Desvio padrão",  f"{np.std(xs):.3f}",   f"{np.std(ys):.3f}"],
            ["Mínimo",         f"{np.min(xs):.3f}",   f"{np.min(ys):.3f}"],
            ["Máximo",         f"{np.max(xs):.3f}",   f"{np.max(ys):.3f}"],
            ["Mediana",        f"{np.median(xs):.3f}", f"{np.median(ys):.3f}"],
        ]
        ts = Table(stats_data, colWidths=[7*cm, 4.5*cm, 4.5*cm])
        ts.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1a1a4e")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f4f4f8")]),
            ("GRID",        (0,0), (-1,-1), 0.4, colors.HexColor("#aaaacc")),
            ("ALIGN",       (1,0), (-1,-1), "CENTER"),
            ("TOPPADDING",  (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ]))
        story.append(ts)
        story.append(Spacer(1, 0.5*cm))

        # distribuição por quadrante
        story.append(Paragraph("Distribuição por Quadrante", styles["Heading3"]))
        story.append(Spacer(1, 0.2*cm))
        quad_data = [
            ["Quadrante",      "Superior Esq.", "Superior Dir.", "Inferior Esq.", "Inferior Dir."],
            ["Pontos (n)",     str(q1), str(q2), str(q3), str(q4)],
            ["Percentual (%)", f"{100*q1/total:.1f}", f"{100*q2/total:.1f}",
                               f"{100*q3/total:.1f}", f"{100*q4/total:.1f}"],
        ]
        qt = Table(quad_data, colWidths=[4*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])
        qt.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1a1a4e")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f4f4f8")]),
            ("GRID",        (0,0), (-1,-1), 0.4, colors.HexColor("#aaaacc")),
            ("ALIGN",       (1,0), (-1,-1), "CENTER"),
            ("TOPPADDING",  (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ]))
        story.append(qt)

    # ── rodapé ────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "Este relatório foi gerado automaticamente pelo sistema de Eye Tracking 3D.",
        styles["Italic"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf


# ═══════════════════════════ UI ══════════════════════════════
st.set_page_config(
    page_title="Eye Tracking 3D",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  .block-container { padding-top: 1.2rem; }
  .stMetric label { font-size: .8rem; }
</style>
""", unsafe_allow_html=True)

st.title("👁️ Eye Tracking 3D  —  Mapa de Calor + Relatório PDF")
st.caption("Powered by MediaPipe Face Landmarker Tasks API  •  Python 3.13 ✅")

# ── session state defaults ────────────────────────────────────
for k, v in [
    ("tracking_active", False),
    ("session_start",   None),
    ("snapshot_gaze",   []),      # cópia para plots / PDF
    ("snapshot_lms",    None),
    ("snapshot_frames", 0),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Controles")

    col1, col2 = st.columns(2)
    with col1:
        start_btn = st.button("▶ Iniciar", use_container_width=True, type="primary")
    with col2:
        stop_btn  = st.button("⏹ Pausar",  use_container_width=True)

    clear_btn = st.button("🗑️ Limpar dados", use_container_width=True)
    st.divider()

    status_txt = "🟢 ATIVO" if st.session_state.tracking_active else "🔴 PARADO"
    st.markdown(f"**Status:** {status_txt}")
    n_pts = len(st.session_state.snapshot_gaze)
    st.metric("Pontos capturados", n_pts)
    if st.session_state.session_start:
        dur = (datetime.now() - st.session_state.session_start).seconds
        st.metric("Duração (s)", dur)
    st.divider()

    show_3d      = st.checkbox("🧊 Mapa 3D",   value=True)
    show_heatmap = st.checkbox("🌡️ Heatmap",   value=True)
    auto_refresh = st.checkbox("🔄 Auto-refresh (1s)", value=True)

# ── botões ────────────────────────────────────────────────────
if start_btn:
    st.session_state.tracking_active = True
    if not st.session_state.session_start:
        st.session_state.session_start = datetime.now()
        st.session_state.snapshot_gaze   = []
        st.session_state.snapshot_frames = 0

if stop_btn:
    st.session_state.tracking_active = False

if clear_btn:
    st.session_state.tracking_active = False
    st.session_state.session_start   = None
    st.session_state.snapshot_gaze   = []
    st.session_state.snapshot_lms    = None
    st.session_state.snapshot_frames = 0

# ── layout principal ─────────────────────────────────────────
col_cam, col_viz = st.columns([1.1, 0.9], gap="medium")

with col_cam:
    st.subheader("📷 Webcam + Micropontos")

    webrtc_ctx = webrtc_streamer(
        key="eye-tracking-v2",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=FaceTrackingProcessor,
        media_stream_constraints={"video": {"width": W, "height": H}, "audio": False},
        async_processing=True,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    )

    # sincroniza estado tracking → processador
    if webrtc_ctx.video_processor:
        proc: FaceTrackingProcessor = webrtc_ctx.video_processor
        proc.active = st.session_state.tracking_active

        # lê dados acumulados no processador
        with proc.lock:
            gaze_snap = list(proc.gaze_points)
            lms_snap  = proc.latest_landmarks
            frames_n  = proc.frame_count
            face_ok   = proc.face_detected

        # atualiza session_state
        if gaze_snap:
            st.session_state.snapshot_gaze   = gaze_snap
            st.session_state.snapshot_frames = frames_n
        if lms_snap:
            st.session_state.snapshot_lms = lms_snap

        # indicador de face
        if face_ok:
            st.success(f"✅ Rosto detectado  |  {len(gaze_snap)} pts")
        elif webrtc_ctx.state.playing:
            st.warning("⚠️ Nenhum rosto na câmera")

with col_viz:
    tab_hm, tab_3d = st.tabs(["🌡️ Heatmap", "🧊 Mapa 3D"])

    with tab_hm:
        if st.session_state.snapshot_gaze and show_heatmap:
            fig_hm = plot_heatmap(st.session_state.snapshot_gaze)
            st.pyplot(fig_hm, use_container_width=True)
            plt.close(fig_hm)
        else:
            st.info("Inicie o tracking para ver o mapa de calor.")

    with tab_3d:
        if st.session_state.snapshot_lms and show_3d:
            fig3d = plot_3d_landmarks(st.session_state.snapshot_lms)
            st.plotly_chart(fig3d, use_container_width=True)
        else:
            st.info("O mapa 3D aparece quando um rosto é detectado.")

# ── exportar PDF ─────────────────────────────────────────────
st.divider()
col_pdf1, col_pdf2 = st.columns([1, 3])
with col_pdf1:
    gen_pdf = st.button(
        "📄 Gerar Relatório PDF",
        disabled=len(st.session_state.snapshot_gaze) == 0,
        type="primary",
        use_container_width=True,
    )
with col_pdf2:
    if gen_pdf:
        with st.spinner("Gerando PDF…"):
            pdf_buf = generate_pdf(
                st.session_state.snapshot_gaze,
                st.session_state.session_start,
                st.session_state.snapshot_frames,
            )
        fname = f"eye_tracking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        st.download_button(
            label="⬇️  Baixar PDF",
            data=pdf_buf,
            file_name=fname,
            mime="application/pdf",
            type="primary",
        )

# ── auto-refresh enquanto tracking ativo ─────────────────────
if (
    auto_refresh
    and st.session_state.tracking_active
    and webrtc_ctx.state.playing
):
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
