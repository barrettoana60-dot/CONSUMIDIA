import io
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import av
import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer


st.set_page_config(page_title="Simulacro Eye Tracking MVP", page_icon="👁️", layout="wide")


# =========================
# Configurações e estado
# =========================
W, H = 640, 480
GRID_N = 16
MAX_SAMPLES_DEFAULT = 6000


if "samples" not in st.session_state:
    st.session_state.samples = []
if "session_started_at" not in st.session_state:
    st.session_state.session_started_at = None
if "latest_frame" not in st.session_state:
    st.session_state.latest_frame = None
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = {
        "blink_count": 0,
        "face_found": False,
        "gaze_x": 0.0,
        "gaze_y": 0.0,
        "head_roll_deg": 0.0,
        "samples": 0,
    }


# =========================
# Utilidades matemáticas
# =========================
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def point_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.dist(p1, p2)


def normalize(value: float, old_min: float, old_max: float) -> float:
    if old_max - old_min == 0:
        return 0.0
    return (value - old_min) / (old_max - old_min)


def gaussian_stamp(grid: np.ndarray, gx: float, gy: float, sigma: float = 1.2, amplitude: float = 1.0) -> None:
    h, w = grid.shape
    cx, cy = gx * (w - 1), gy * (h - 1)
    radius = max(1, int(math.ceil(sigma * 3)))
    x0, x1 = max(0, int(cx - radius)), min(w - 1, int(cx + radius))
    y0, y1 = max(0, int(cy - radius)), min(h - 1, int(cy + radius))
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            grid[yy, xx] += amplitude * math.exp(-d2 / (2 * sigma * sigma))


# =========================
# MediaPipe landmarks
# =========================
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_EYE_H = [362, 263]
LEFT_EYE_V = [386, 374]
RIGHT_EYE_H = [33, 133]
RIGHT_EYE_V = [159, 145]

EAR_L = [386, 374, 387, 373, 362, 263]
EAR_R = [159, 145, 160, 144, 33, 133]


@dataclass
class GazeSample:
    ts: float
    gaze_x: float
    gaze_y: float
    cube_x: float
    cube_y: float
    cube_z: float
    head_roll_deg: float
    blink: int


class SharedState:
    def __init__(self) -> None:
        self.samples: List[GazeSample] = []
        self.latest_frame_bgr: np.ndarray | None = None
        self.latest_metrics = {
            "blink_count": 0,
            "face_found": False,
            "gaze_x": 0.0,
            "gaze_y": 0.0,
            "head_roll_deg": 0.0,
            "samples": 0,
        }
        self.max_samples = MAX_SAMPLES_DEFAULT


shared_state = SharedState()


class EyeTrackingProcessor(VideoProcessorBase):
    def __init__(self) -> None:
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.blink_count = 0
        self.blink_cooldown = 0
        self.ear_threshold = 0.18
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smooth_roll = 0.0
        self.last_face_found = False

    def _center(self, landmarks, indices, width: int, height: int) -> Tuple[float, float]:
        pts = [(landmarks[i].x * width, landmarks[i].y * height) for i in indices]
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        return x, y

    def _ear(self, landmarks, indices, width: int, height: int) -> float:
        pts = [(landmarks[i].x * width, landmarks[i].y * height) for i in indices]
        top1 = point_distance(pts[0], pts[1])
        top2 = point_distance(pts[2], pts[3])
        horiz = point_distance(pts[4], pts[5])
        return (top1 + top2) / (2 * horiz + 1e-6)

    def _estimate_gaze(self, landmarks, width: int, height: int) -> Tuple[float, float, float]:
        lx, ly = self._center(landmarks, LEFT_IRIS, width, height)
        rx, ry = self._center(landmarks, RIGHT_IRIS, width, height)

        left_eye_left = (landmarks[LEFT_EYE_H[0]].x * width, landmarks[LEFT_EYE_H[0]].y * height)
        left_eye_right = (landmarks[LEFT_EYE_H[1]].x * width, landmarks[LEFT_EYE_H[1]].y * height)
        left_eye_top = (landmarks[LEFT_EYE_V[0]].x * width, landmarks[LEFT_EYE_V[0]].y * height)
        left_eye_bottom = (landmarks[LEFT_EYE_V[1]].x * width, landmarks[LEFT_EYE_V[1]].y * height)

        right_eye_left = (landmarks[RIGHT_EYE_H[0]].x * width, landmarks[RIGHT_EYE_H[0]].y * height)
        right_eye_right = (landmarks[RIGHT_EYE_H[1]].x * width, landmarks[RIGHT_EYE_H[1]].y * height)
        right_eye_top = (landmarks[RIGHT_EYE_V[0]].x * width, landmarks[RIGHT_EYE_V[0]].y * height)
        right_eye_bottom = (landmarks[RIGHT_EYE_V[1]].x * width, landmarks[RIGHT_EYE_V[1]].y * height)

        left_h = normalize(lx, left_eye_left[0], left_eye_right[0])
        right_h = normalize(rx, right_eye_left[0], right_eye_right[0])
        left_v = normalize(ly, left_eye_top[1], left_eye_bottom[1])
        right_v = normalize(ry, right_eye_top[1], right_eye_bottom[1])

        gaze_x = clamp(((left_h + right_h) / 2.0 - 0.5) * 2.0, -1.0, 1.0)
        gaze_y = clamp(((left_v + right_v) / 2.0 - 0.5) * 2.0, -1.0, 1.0)

        roll = math.degrees(math.atan2(ly - ry, lx - rx))
        return gaze_x, gaze_y, roll

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        image = frame.to_ndarray(format="bgr24")
        image = cv2.flip(image, 1)
        height, width = image.shape[:2]

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        blink_now = 0
        face_found = False
        gaze_x = 0.0
        gaze_y = 0.0
        head_roll_deg = 0.0

        if results.multi_face_landmarks:
            face_found = True
            lms = results.multi_face_landmarks[0].landmark

            gaze_x, gaze_y, head_roll_deg = self._estimate_gaze(lms, width, height)
            self.smooth_x = lerp(self.smooth_x, (gaze_x + 1) / 2.0, 0.2)
            self.smooth_y = lerp(self.smooth_y, (gaze_y + 1) / 2.0, 0.2)
            self.smooth_roll = lerp(self.smooth_roll, head_roll_deg, 0.15)

            ear_l = self._ear(lms, EAR_L, width, height)
            ear_r = self._ear(lms, EAR_R, width, height)
            ear_avg = (ear_l + ear_r) / 2.0
            if ear_avg < self.ear_threshold and self.blink_cooldown <= 0:
                self.blink_count += 1
                blink_now = 1
                self.blink_cooldown = 10
            if self.blink_cooldown > 0:
                self.blink_cooldown -= 1

            cube_x = self.smooth_x * 2 - 1
            cube_y = -(self.smooth_y * 2 - 1)
            cube_z = clamp(1.0 - math.sqrt(cube_x ** 2 + cube_y ** 2) * 0.7, -1.0, 1.0)

            shared_state.samples.append(
                GazeSample(
                    ts=time.time(),
                    gaze_x=float(self.smooth_x),
                    gaze_y=float(self.smooth_y),
                    cube_x=float(cube_x),
                    cube_y=float(cube_y),
                    cube_z=float(cube_z),
                    head_roll_deg=float(self.smooth_roll),
                    blink=int(blink_now),
                )
            )
            if len(shared_state.samples) > shared_state.max_samples:
                shared_state.samples = shared_state.samples[-shared_state.max_samples :]

            # overlay visual simples
            center_px = int(self.smooth_x * width)
            center_py = int(self.smooth_y * height)
            cv2.circle(image, (center_px, center_py), 18, (0, 255, 255), 2)
            cv2.circle(image, (center_px, center_py), 4, (0, 0, 255), -1)
            cv2.putText(image, f"gaze=({cube_x:+.2f},{cube_y:+.2f},{cube_z:+.2f})", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 255, 50), 2)
            cv2.putText(image, f"blinks={self.blink_count}", (20, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 50), 2)

        shared_state.latest_frame_bgr = image.copy()
        shared_state.latest_metrics = {
            "blink_count": self.blink_count,
            "face_found": face_found,
            "gaze_x": float(self.smooth_x),
            "gaze_y": float(self.smooth_y),
            "head_roll_deg": float(self.smooth_roll),
            "samples": len(shared_state.samples),
        }

        return av.VideoFrame.from_ndarray(image, format="bgr24")


# =========================
# Cubo 3D e heatmap
# =========================
def build_cube_points(n: int = GRID_N) -> pd.DataFrame:
    vals = np.linspace(-1.0, 1.0, n)
    rows = []
    for y in vals:
        for x in vals:
            z = 1.0
            rows.append((x, y, z))
    df = pd.DataFrame(rows, columns=["x", "y", "z"])
    return df


def build_heat_grid(samples: List[GazeSample], n: int = GRID_N) -> np.ndarray:
    heat = np.zeros((n, n), dtype=np.float32)
    for s in samples:
        gx = clamp((s.cube_x + 1.0) / 2.0, 0.0, 1.0)
        gy = clamp((s.cube_y + 1.0) / 2.0, 0.0, 1.0)
        gy = 1.0 - gy
        gaussian_stamp(heat, gx, gy, sigma=1.0, amplitude=1.0)
    return heat


def cube_figure(samples: List[GazeSample], n: int = GRID_N, illusion_strength: float = 0.18) -> go.Figure:
    df = build_cube_points(n)
    heat = build_heat_grid(samples, n)

    if len(samples) > 0:
        gx = float(np.mean([s.cube_x for s in samples[-20:]]))
        gy = float(np.mean([s.cube_y for s in samples[-20:]]))
        gr = float(np.mean([s.head_roll_deg for s in samples[-20:]]))
    else:
        gx, gy, gr = 0.0, 0.0, 0.0

    xs = df["x"].to_numpy().copy()
    ys = df["y"].to_numpy().copy()
    zs = df["z"].to_numpy().copy()

    # ilusão óptica leve: desloca microspontos conforme olhar
    xs = xs + gx * illusion_strength * (1 - np.abs(xs) * 0.35)
    ys = ys + gy * illusion_strength * (1 - np.abs(ys) * 0.35)
    zs = zs + (1 - np.sqrt(np.clip(xs ** 2 + ys ** 2, 0, 2)) / math.sqrt(2)) * 0.12

    colors_flat = heat.flatten()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="markers",
            marker=dict(
                size=5,
                color=colors_flat,
                colorscale="Turbo",
                opacity=0.95,
                colorbar=dict(title="Calor"),
            ),
            name="Microspontos",
        )
    )

    edge = [-1, 1]
    edge_lines = [
        ([-1, 1], [-1, -1], [1, 1]),
        ([-1, 1], [1, 1], [1, 1]),
        ([-1, -1], [-1, 1], [1, 1]),
        ([1, 1], [-1, 1], [1, 1]),
    ]
    for ex, ey, ez in edge_lines:
        fig.add_trace(go.Scatter3d(x=ex, y=ey, z=ez, mode="lines", line=dict(width=4), showlegend=False))

    if len(samples) > 0:
        last = samples[-1]
        fig.add_trace(
            go.Scatter3d(
                x=[last.cube_x],
                y=[last.cube_y],
                z=[1.06],
                mode="markers",
                marker=dict(size=8, symbol="diamond"),
                name="Olhar atual",
            )
        )

    camera_eye = dict(
        x=1.45 + gx * 0.22,
        y=1.45 + gy * 0.22,
        z=1.0,
    )
    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=20, b=0),
        scene=dict(
            xaxis=dict(range=[-1.4, 1.4], visible=False),
            yaxis=dict(range=[-1.4, 1.4], visible=False),
            zaxis=dict(range=[-1.0, 1.4], visible=False),
            aspectmode="cube",
            camera=dict(eye=camera_eye),
        ),
        title=f"Cubo 3D com microspontos | roll médio recente: {gr:.1f}°",
    )
    return fig


# =========================
# Heatmap 2D e imagens
# =========================
def heatmap_figure(samples: List[GazeSample], n: int = 40) -> go.Figure:
    heat = np.zeros((n, n), dtype=np.float32)
    for s in samples:
        gaussian_stamp(heat, s.gaze_x, s.gaze_y, sigma=1.25, amplitude=1.0)
    fig = go.Figure(data=go.Heatmap(z=heat, colorscale="Turbo"))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=35, b=10), title="Mapa de temperatura 2D")
    return fig


def save_plotly_figure(fig: go.Figure, path: str) -> str:
    try:
        fig.write_image(path, scale=2)
        return path
    except Exception:
        # fallback HTML disabled in PDF flow; return empty string
        return ""


# =========================
# Relatório PDF
# =========================
def summarize_samples(samples: List[GazeSample]) -> dict:
    if not samples:
        return {
            "duration_s": 0,
            "sample_count": 0,
            "blinks": 0,
            "peak_cell": "-",
            "mean_x": 0.0,
            "mean_y": 0.0,
            "mean_roll": 0.0,
        }

    df = pd.DataFrame([s.__dict__ for s in samples])
    duration_s = max(0.0, df["ts"].iloc[-1] - df["ts"].iloc[0])
    heat = build_heat_grid(samples, GRID_N)
    peak_idx = np.unravel_index(np.argmax(heat), heat.shape)
    return {
        "duration_s": duration_s,
        "sample_count": int(len(samples)),
        "blinks": int(df["blink"].sum()),
        "peak_cell": f"linha {peak_idx[0] + 1}, coluna {peak_idx[1] + 1}",
        "mean_x": float(df["cube_x"].mean()),
        "mean_y": float(df["cube_y"].mean()),
        "mean_roll": float(df["head_roll_deg"].mean()),
    }


def generate_pdf_report(samples: List[GazeSample], frame_bgr: np.ndarray | None) -> bytes:
    summary = summarize_samples(samples)

    cube_fig = cube_figure(samples)
    heat_fig = heatmap_figure(samples)

    tmp_dir = Path("./tmp_simulacro")
    tmp_dir.mkdir(exist_ok=True)
    cube_img = str(tmp_dir / "cube.png")
    heat_img = str(tmp_dir / "heat.png")
    cam_img = str(tmp_dir / "frame.png")

    save_plotly_figure(cube_fig, cube_img)
    save_plotly_figure(heat_fig, heat_img)
    if frame_bgr is not None:
        cv2.imwrite(cam_img, frame_bgr)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.4 * cm, leftMargin=1.4 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = getSampleStyleSheet()
    story = []

    title = Paragraph("Simulacro — Relatório de Rastreamento Ocular em Cenário 3D", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 0.35 * cm))

    intro = Paragraph(
        "Este relatório resume uma sessão experimental de estimativa de olhar com webcam, projeção em cubo 3D de microspontos e mapa de temperatura das regiões mais observadas.",
        styles["BodyText"],
    )
    story.append(intro)
    story.append(Spacer(1, 0.35 * cm))

    data = [
        ["Duração da sessão", f"{summary['duration_s']:.1f} s"],
        ["Total de amostras", str(summary["sample_count"])],
        ["Piscadas detectadas", str(summary["blinks"])],
        ["Região de pico do calor", summary["peak_cell"]],
        ["Média eixo X do cubo", f"{summary['mean_x']:+.3f}"],
        ["Média eixo Y do cubo", f"{summary['mean_y']:+.3f}"],
        ["Roll médio da cabeça/olhos", f"{summary['mean_roll']:+.2f}°"],
    ]
    table = Table(data, colWidths=[6.3 * cm, 9.8 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eefb")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f8fc")),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.45 * cm))

    analysis = Paragraph(
        "Leitura interpretativa: valores mais altos no heatmap indicam fixações ou passagens recorrentes do olhar. O cubo 3D reage ao olhar recente deslocando a câmera e a nuvem de microspontos para criar ilusão de óptica e sensação de resposta espacial.",
        styles["BodyText"],
    )
    story.append(analysis)
    story.append(Spacer(1, 0.35 * cm))

    for img_path, label in [(cube_img, "Cenário 3D com microspontos"), (heat_img, "Mapa de temperatura 2D"), (cam_img, "Último frame da sessão")]:
        if Path(img_path).exists() and Path(img_path).stat().st_size > 0:
            story.append(Paragraph(label, styles["Heading3"]))
            story.append(RLImage(img_path, width=16.8 * cm, height=9.2 * cm))
            story.append(Spacer(1, 0.25 * cm))

    note = Paragraph(
        "Observação metodológica: este protótipo estima direção de olhar a partir de landmarks faciais/íris e pose relativa. O resultado é adequado para experimento visual e mapa de atenção, não para uso clínico ou biométrico de alta precisão.",
        styles["Italic"],
    )
    story.append(note)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================
# Interface Streamlit
# =========================
st.title("👁️ Simulacro — Cubo 3D com Microspontos + Heatmap + PDF")
st.caption("Protótipo experimental de rastreamento ocular simplificado com cenário 3D responsivo.")

with st.sidebar:
    st.header("Controles")
    shared_state.max_samples = st.slider("Máximo de amostras", 500, 12000, MAX_SAMPLES_DEFAULT, step=500)
    illusion_strength = st.slider("Força da ilusão óptica", 0.00, 0.60, 0.18, 0.01)
    auto_refresh = st.checkbox("Atualização manual mais leve", value=True)

    if st.button("Iniciar nova sessão", use_container_width=True):
        shared_state.samples = []
        st.session_state.samples = []
        st.session_state.session_started_at = time.time()
        st.success("Sessão reiniciada.")

    if st.button("Limpar amostras", use_container_width=True):
        shared_state.samples = []
        st.session_state.samples = []
        st.warning("Amostras removidas.")

col_cam, col_viz = st.columns([1.1, 1.2])

with col_cam:
    st.subheader("Webcam e tracking")
    webrtc_ctx = webrtc_streamer(
        key="simulacro-eye-tracking",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": {"width": W, "height": H}, "audio": False},
        video_processor_factory=EyeTrackingProcessor,
        async_processing=True,
    )

    metrics = shared_state.latest_metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rosto", "OK" if metrics["face_found"] else "—")
    m2.metric("Piscadas", metrics["blink_count"])
    m3.metric("Amostras", metrics["samples"])
    m4.metric("Roll", f"{metrics['head_roll_deg']:.1f}°")

    st.write(
        {
            "gaze_x_normalizado": round(metrics["gaze_x"], 4),
            "gaze_y_normalizado": round(metrics["gaze_y"], 4),
        }
    )

with col_viz:
    st.subheader("Cubo 3D e mapa de atenção")
    samples = list(shared_state.samples)
    fig3d = cube_figure(samples, illusion_strength=illusion_strength)
    st.plotly_chart(fig3d, use_container_width=True)

col_heat, col_table = st.columns([1.05, 0.95])
with col_heat:
    st.subheader("Heatmap 2D")
    st.plotly_chart(heatmap_figure(list(shared_state.samples)), use_container_width=True)

with col_table:
    st.subheader("Amostras recentes")
    df_recent = pd.DataFrame([s.__dict__ for s in shared_state.samples[-20:]])
    if df_recent.empty:
        st.info("Ainda sem amostras. Autorize a câmera e olhe para a tela.")
    else:
        st.dataframe(df_recent, use_container_width=True, height=360)

st.markdown("---")
st.subheader("Relatório")
summary = summarize_samples(list(shared_state.samples))
summary_cols = st.columns(5)
summary_cols[0].metric("Duração", f"{summary['duration_s']:.1f}s")
summary_cols[1].metric("Amostras", summary["sample_count"])
summary_cols[2].metric("Piscadas", summary["blinks"])
summary_cols[3].metric("Pico de calor", summary["peak_cell"])
summary_cols[4].metric("X médio", f"{summary['mean_x']:+.2f}")

pdf_bytes = generate_pdf_report(list(shared_state.samples), shared_state.latest_frame_bgr)
st.download_button(
    label="📄 Baixar relatório em PDF",
    data=pdf_bytes,
    file_name="relatorio_simulacro_eye_tracking.pdf",
    mime="application/pdf",
    use_container_width=True,
)

with st.expander("Dependências"):
    st.code(
        """
streamlit>=1.39
streamlit-webrtc>=0.64.5
mediapipe>=0.10
opencv-python-headless>=4.10
numpy>=1.26
pandas>=2.2
plotly>=5.24
reportlab>=4.2
kaleido>=0.2.1
av>=12.3
pillow>=10.4
        """.strip(),
        language="text",
    )

with st.expander("Observações importantes"):
    st.markdown(
        """
- Este MVP usa **estimativa simplificada do olhar** com webcam comum.
- O cubo 3D atual usa a **face frontal** como superfície principal de calor; a sensação espacial vem do deslocamento da câmera e dos microspontos.
- Para deploy na nuvem, WebRTC e permissões do navegador precisam estar corretos.
- Para um tracking mais forte, a próxima etapa é adicionar **calibração de 5 pontos** e compensação de pose da cabeça.
        """
    )

if auto_refresh:
    st.caption("Para reduzir travamentos, a página usa atualização mais estável; interaja com a webcam e use o botão de PDF quando já houver dados.")
