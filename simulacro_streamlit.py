import io
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional

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
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer


# =========================================================
# SEGURANÇA DE COMPATIBILIDADE
# =========================================================
if not hasattr(mp, "solutions"):
    raise RuntimeError(
        "A versão do MediaPipe instalada não expõe mp.solutions. "
        "Use mediapipe==0.10.21 e Python 3.12."
    )

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(
    page_title="Simulacro — Eye Tracking 3D",
    page_icon="👁️",
    layout="wide",
)

FRAME_W = 640
FRAME_H = 480
DEFAULT_MAX_SAMPLES = 7000

LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

LEFT_EYE_H = [362, 263]
LEFT_EYE_V = [386, 374]
RIGHT_EYE_H = [33, 133]
RIGHT_EYE_V = [159, 145]

EAR_L = [386, 374, 387, 373, 362, 263]
EAR_R = [159, 145, 160, 144, 33, 133]


# =========================================================
# UTILITÁRIOS
# =========================================================
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def dist2d(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.dist(p1, p2)


def normalize(v: float, old_min: float, old_max: float) -> float:
    denom = old_max - old_min
    if abs(denom) < 1e-9:
        return 0.5
    return (v - old_min) / denom


def gaussian_stamp(grid: np.ndarray, gx: float, gy: float, sigma: float = 1.25, amp: float = 1.0):
    h, w = grid.shape
    cx = gx * (w - 1)
    cy = gy * (h - 1)

    radius = max(1, int(math.ceil(sigma * 3)))
    x0 = max(0, int(cx - radius))
    x1 = min(w - 1, int(cx + radius))
    y0 = max(0, int(cy - radius))
    y1 = min(h - 1, int(cy + radius))

    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            grid[yy, xx] += amp * math.exp(-d2 / (2 * sigma * sigma))


# =========================================================
# QUATERNIONS
# =========================================================
def quat_from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=np.float64)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)

    axis = axis / norm
    half = angle_rad / 2.0
    s = math.sin(half)
    return np.array([math.cos(half), axis[0] * s, axis[1] * s, axis[2] * s], dtype=np.float64)


def quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], dtype=np.float64)


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def quat_rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    qv = np.array([0.0, v[0], v[1], v[2]], dtype=np.float64)
    qr = quat_multiply(quat_multiply(q, qv), quat_conjugate(q))
    return np.array([qr[1], qr[2], qr[3]], dtype=np.float64)


# =========================================================
# DADOS
# =========================================================
@dataclass
class GazeSample:
    ts: float
    gaze_x_norm: float
    gaze_y_norm: float
    cube_x: float
    cube_y: float
    cube_z: float
    roll_deg: float
    blink: int
    velocity: float


class SharedState:
    def __init__(self):
        self.samples: List[GazeSample] = []
        self.latest_frame_bgr: Optional[np.ndarray] = None
        self.latest_metrics = {
            "face_found": False,
            "blink_count": 0,
            "samples": 0,
            "gaze_x": 0.5,
            "gaze_y": 0.5,
            "roll_deg": 0.0,
            "velocity": 0.0,
        }
        self.max_samples = DEFAULT_MAX_SAMPLES


shared = SharedState()


# =========================================================
# PROCESSADOR DE VÍDEO
# =========================================================
class EyeTrackingProcessor(VideoProcessorBase):
    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.ear_threshold = 0.18
        self.blink_cooldown = 0
        self.blink_count = 0

        self.sx = 0.5
        self.sy = 0.5
        self.sroll = 0.0

        self.prev_cube_x = 0.0
        self.prev_cube_y = 0.0
        self.prev_ts = time.time()

    def _center(self, landmarks, idxs, w: int, h: int) -> Tuple[float, float]:
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in idxs]
        return (
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        )

    def _ear(self, landmarks, idxs, w: int, h: int) -> float:
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in idxs]
        top1 = dist2d(pts[0], pts[1])
        top2 = dist2d(pts[2], pts[3])
        horiz = dist2d(pts[4], pts[5])
        return (top1 + top2) / (2 * horiz + 1e-6)

    def _estimate_gaze(self, landmarks, w: int, h: int) -> Tuple[float, float, float]:
        lx, ly = self._center(landmarks, LEFT_IRIS, w, h)
        rx, ry = self._center(landmarks, RIGHT_IRIS, w, h)

        l_left = (landmarks[LEFT_EYE_H[0]].x * w, landmarks[LEFT_EYE_H[0]].y * h)
        l_right = (landmarks[LEFT_EYE_H[1]].x * w, landmarks[LEFT_EYE_H[1]].y * h)
        l_top = (landmarks[LEFT_EYE_V[0]].x * w, landmarks[LEFT_EYE_V[0]].y * h)
        l_bottom = (landmarks[LEFT_EYE_V[1]].x * w, landmarks[LEFT_EYE_V[1]].y * h)

        r_left = (landmarks[RIGHT_EYE_H[0]].x * w, landmarks[RIGHT_EYE_H[0]].y * h)
        r_right = (landmarks[RIGHT_EYE_H[1]].x * w, landmarks[RIGHT_EYE_H[1]].y * h)
        r_top = (landmarks[RIGHT_EYE_V[0]].x * w, landmarks[RIGHT_EYE_V[0]].y * h)
        r_bottom = (landmarks[RIGHT_EYE_V[1]].x * w, landmarks[RIGHT_EYE_V[1]].y * h)

        lh = normalize(lx, l_left[0], l_right[0])
        rh = normalize(rx, r_left[0], r_right[0])
        lv = normalize(ly, l_top[1], l_bottom[1])
        rv = normalize(ry, r_top[1], r_bottom[1])

        gaze_x = clamp(((lh + rh) / 2.0 - 0.5) * 2.0, -1.0, 1.0)
        gaze_y = clamp(((lv + rv) / 2.0 - 0.5) * 2.0, -1.0, 1.0)

        roll_deg = math.degrees(math.atan2(ly - ry, lx - rx))
        return gaze_x, gaze_y, roll_deg

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)

        blink_now = 0
        face_found = False
        velocity = 0.0

        if result.multi_face_landmarks:
            face_found = True
            lms = result.multi_face_landmarks[0].landmark

            gaze_x, gaze_y, roll_deg = self._estimate_gaze(lms, w, h)

            self.sx = lerp(self.sx, (gaze_x + 1) / 2.0, 0.22)
            self.sy = lerp(self.sy, (gaze_y + 1) / 2.0, 0.22)
            self.sroll = lerp(self.sroll, roll_deg, 0.15)

            ear_l = self._ear(lms, EAR_L, w, h)
            ear_r = self._ear(lms, EAR_R, w, h)
            ear_avg = (ear_l + ear_r) / 2.0

            if ear_avg < self.ear_threshold and self.blink_cooldown <= 0:
                self.blink_count += 1
                blink_now = 1
                self.blink_cooldown = 10

            if self.blink_cooldown > 0:
                self.blink_cooldown -= 1

            cube_x = self.sx * 2 - 1
            cube_y = -(self.sy * 2 - 1)
            radial = math.sqrt(cube_x * cube_x + cube_y * cube_y)
            cube_z = clamp(1.0 - radial * 0.75, -1.0, 1.0)

            now = time.time()
            dt = max(1e-5, now - self.prev_ts)
            velocity = math.sqrt((cube_x - self.prev_cube_x) ** 2 + (cube_y - self.prev_cube_y) ** 2) / dt

            shared.samples.append(
                GazeSample(
                    ts=now,
                    gaze_x_norm=float(self.sx),
                    gaze_y_norm=float(self.sy),
                    cube_x=float(cube_x),
                    cube_y=float(cube_y),
                    cube_z=float(cube_z),
                    roll_deg=float(self.sroll),
                    blink=int(blink_now),
                    velocity=float(velocity),
                )
            )

            if len(shared.samples) > shared.max_samples:
                shared.samples = shared.samples[-shared.max_samples:]

            self.prev_cube_x = cube_x
            self.prev_cube_y = cube_y
            self.prev_ts = now

            px = int(self.sx * w)
            py = int(self.sy * h)

            cv2.circle(img, (px, py), 18, (0, 255, 255), 2)
            cv2.circle(img, (px, py), 4, (0, 0, 255), -1)

            cv2.putText(img, f"gaze=({cube_x:+.2f},{cube_y:+.2f},{cube_z:+.2f})",
                        (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 255, 50), 2)
            cv2.putText(img, f"blinks={self.blink_count}",
                        (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 50), 2)
            cv2.putText(img, f"vel={velocity:.2f}",
                        (20, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 150, 150), 2)

        shared.latest_frame_bgr = img.copy()
        shared.latest_metrics = {
            "face_found": face_found,
            "blink_count": self.blink_count,
            "samples": len(shared.samples),
            "gaze_x": self.sx,
            "gaze_y": self.sy,
            "roll_deg": self.sroll,
            "velocity": velocity,
        }

        return av.VideoFrame.from_ndarray(img, format="bgr24")


# =========================================================
# CUBO E ILUSÃO ÓPTICA
# =========================================================
def build_front_face_points(grid_n: int) -> pd.DataFrame:
    vals = np.linspace(-1.0, 1.0, grid_n)
    rows = []
    for y in vals:
        for x in vals:
            rows.append((x, y, 1.0))
    return pd.DataFrame(rows, columns=["x", "y", "z"])


def build_heat_grid(samples: List[GazeSample], grid_n: int) -> np.ndarray:
    heat = np.zeros((grid_n, grid_n), dtype=np.float32)
    for s in samples:
        gx = clamp((s.cube_x + 1) / 2.0, 0.0, 1.0)
        gy = clamp((s.cube_y + 1) / 2.0, 0.0, 1.0)
        gy = 1.0 - gy
        gaussian_stamp(heat, gx, gy, sigma=1.05, amp=1.0)
    return heat


def optical_distortion(x: float, y: float, gaze_x: float, gaze_y: float, strength: float) -> Tuple[float, float, float]:
    r = math.sqrt(x * x + y * y)
    warp = (1.0 - min(1.0, r)) * strength

    dx = x + gaze_x * warp * (1.0 - abs(x) * 0.35)
    dy = y + gaze_y * warp * (1.0 - abs(y) * 0.35)
    dz = 1.0 + (1.0 - min(1.0, r)) * 0.18 * strength
    return dx, dy, dz


def cube_figure(
    samples: List[GazeSample],
    grid_n: int = 18,
    optical_strength: float = 0.32,
    quat_strength: float = 0.55,
) -> go.Figure:
    base = build_front_face_points(grid_n)
    heat = build_heat_grid(samples, grid_n)

    if samples:
        recent = samples[-20:]
        gaze_x = float(np.mean([s.cube_x for s in recent]))
        gaze_y = float(np.mean([s.cube_y for s in recent]))
        roll_deg = float(np.mean([s.roll_deg for s in recent]))
        motion = float(np.mean([s.velocity for s in recent]))
    else:
        gaze_x = gaze_y = roll_deg = motion = 0.0

    # quaternion de rotação baseado no olhar
    axis_y = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    axis_x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    axis_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    qx = quat_from_axis_angle(axis_x, -gaze_y * quat_strength * 0.35)
    qy = quat_from_axis_angle(axis_y, gaze_x * quat_strength * 0.35)
    qz = quat_from_axis_angle(axis_z, math.radians(roll_deg * 0.18))

    q = quat_multiply(qz, quat_multiply(qy, qx))

    xs, ys, zs = [], [], []
    heat_flat = heat.flatten()

    for i, row in base.iterrows():
        x, y, z = float(row["x"]), float(row["y"]), float(row["z"])

        # distorção óptica
        x, y, z = optical_distortion(x, y, gaze_x, gaze_y, optical_strength)

        # microvibração perceptiva
        vibr = 0.015 * min(1.0, motion / 3.0)
        x += math.sin(i * 0.37 + motion) * vibr
        y += math.cos(i * 0.23 + motion) * vibr

        # quaternion rotation
        vec = np.array([x, y, z], dtype=np.float64)
        vec_r = quat_rotate_vector(q, vec)

        xs.append(vec_r[0])
        ys.append(vec_r[1])
        zs.append(vec_r[2])

    fig = go.Figure()

    fig.add_trace(
        go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="markers",
            marker=dict(
                size=5,
                color=heat_flat,
                colorscale="Turbo",
                opacity=0.96,
                colorbar=dict(title="Calor"),
            ),
            name="Microspontos",
        )
    )

    # bordas do cubo frontal
    lines = [
        ([-1, 1], [-1, -1], [1, 1]),
        ([-1, 1], [1, 1], [1, 1]),
        ([-1, -1], [-1, 1], [1, 1]),
        ([1, 1], [-1, 1], [1, 1]),
    ]
    for lx, ly, lz in lines:
        pts = []
        for x, y, z in zip(lx, ly, lz):
            v = quat_rotate_vector(q, np.array([x, y, z], dtype=np.float64))
            pts.append(v)
        fig.add_trace(
            go.Scatter3d(
                x=[p[0] for p in pts],
                y=[p[1] for p in pts],
                z=[p[2] for p in pts],
                mode="lines",
                line=dict(width=5),
                showlegend=False,
            )
        )

    if samples:
        last = samples[-1]
        look_v = quat_rotate_vector(q, np.array([last.cube_x, last.cube_y, 1.05], dtype=np.float64))
        fig.add_trace(
            go.Scatter3d(
                x=[look_v[0]],
                y=[look_v[1]],
                z=[look_v[2]],
                mode="markers",
                marker=dict(size=9, symbol="diamond"),
                name="Olhar atual",
            )
        )

    camera_eye = dict(
        x=1.55 + gaze_x * 0.28,
        y=1.55 + gaze_y * 0.28,
        z=1.08 + (0.10 * (1.0 - min(1.0, math.sqrt(gaze_x * gaze_x + gaze_y * gaze_y)))),
    )

    fig.update_layout(
        title="Cubo 3D com microspontos, quaternions e ilusão óptica",
        height=620,
        margin=dict(l=0, r=0, t=45, b=0),
        scene=dict(
            xaxis=dict(range=[-1.6, 1.6], visible=False),
            yaxis=dict(range=[-1.6, 1.6], visible=False),
            zaxis=dict(range=[-1.2, 1.8], visible=False),
            aspectmode="cube",
            camera=dict(eye=camera_eye),
        ),
    )
    return fig


def heatmap_figure(samples: List[GazeSample], n: int = 42) -> go.Figure:
    heat = np.zeros((n, n), dtype=np.float32)
    for s in samples:
        gaussian_stamp(heat, s.gaze_x_norm, s.gaze_y_norm, sigma=1.25, amp=1.0)

    fig = go.Figure(data=go.Heatmap(z=heat, colorscale="Turbo"))
    fig.update_layout(
        title="Mapa de calor das áreas mais observadas",
        height=380,
        margin=dict(l=10, r=10, t=45, b=10),
    )
    return fig


# =========================================================
# ANÁLISE DE DADOS
# =========================================================
def summarize_samples(samples: List[GazeSample], grid_n: int = 18) -> dict:
    if not samples:
        return {
            "duration_s": 0.0,
            "sample_count": 0,
            "blinks": 0,
            "avg_x": 0.0,
            "avg_y": 0.0,
            "avg_z": 0.0,
            "avg_roll": 0.0,
            "avg_velocity": 0.0,
            "peak_region": "-",
            "focus_entropy": 0.0,
        }

    df = pd.DataFrame([asdict(s) for s in samples])
    duration_s = float(df["ts"].iloc[-1] - df["ts"].iloc[0]) if len(df) > 1 else 0.0

    heat = build_heat_grid(samples, grid_n)
    peak = np.unravel_index(np.argmax(heat), heat.shape)

    p = heat.flatten()
    p = p / (p.sum() + 1e-9)
    entropy = -np.sum(p * np.log2(p + 1e-12))

    return {
        "duration_s": duration_s,
        "sample_count": int(len(samples)),
        "blinks": int(df["blink"].sum()),
        "avg_x": float(df["cube_x"].mean()),
        "avg_y": float(df["cube_y"].mean()),
        "avg_z": float(df["cube_z"].mean()),
        "avg_roll": float(df["roll_deg"].mean()),
        "avg_velocity": float(df["velocity"].mean()),
        "peak_region": f"linha {peak[0] + 1}, coluna {peak[1] + 1}",
        "focus_entropy": float(entropy),
    }


def interpret_summary(summary: dict) -> str:
    if summary["sample_count"] == 0:
        return "Sem dados suficientes para interpretar a sessão."

    focus_type = "mais dispersa" if summary["focus_entropy"] > 6.5 else "mais concentrada"
    motion_type = "alta" if summary["avg_velocity"] > 1.2 else "moderada/baixa"

    return (
        f"A sessão teve duração de {summary['duration_s']:.1f}s com "
        f"{summary['sample_count']} amostras válidas e {summary['blinks']} piscadas. "
        f"O comportamento visual foi {focus_type}, indicando {'exploração ampla da cena' if focus_type == 'mais dispersa' else 'maior fixação em regiões específicas'}. "
        f"A velocidade média do olhar foi {motion_type} ({summary['avg_velocity']:.3f}). "
        f"A região de maior incidência ficou em {summary['peak_region']}. "
        f"As médias no cubo foram X={summary['avg_x']:+.3f}, Y={summary['avg_y']:+.3f}, Z={summary['avg_z']:+.3f}, "
        f"com roll médio de {summary['avg_roll']:+.2f}°."
    )


# =========================================================
# EXPORTAÇÃO PDF
# =========================================================
def save_plotly_png(fig: go.Figure, path: str) -> str:
    try:
        fig.write_image(path, scale=2)
        return path
    except Exception:
        return ""


def generate_pdf(samples: List[GazeSample], frame_bgr: Optional[np.ndarray]) -> bytes:
    summary = summarize_samples(samples)
    interp = interpret_summary(summary)

    cube_fig = cube_figure(samples)
    heat_fig = heatmap_figure(samples)

    tmp = Path("tmp_simulacro")
    tmp.mkdir(exist_ok=True)

    cube_path = str(tmp / "cube.png")
    heat_path = str(tmp / "heatmap.png")
    frame_path = str(tmp / "frame.png")

    save_plotly_png(cube_fig, cube_path)
    save_plotly_png(heat_fig, heat_path)

    if frame_bgr is not None:
        cv2.imwrite(frame_path, frame_bgr)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Simulacro — Relatório de Rastreamento Ocular 3D", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "Relatório experimental de rastreamento ocular simplificado com webcam, "
            "projeção em cenário 3D com microspontos, quaternions na movimentação, "
            "ilusão óptica e mapa de calor das áreas mais observadas.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 0.35 * cm))

    table_data = [
        ["Métrica", "Valor"],
        ["Duração", f"{summary['duration_s']:.1f} s"],
        ["Amostras válidas", str(summary["sample_count"])],
        ["Piscadas", str(summary["blinks"])],
        ["Região de pico", summary["peak_region"]],
        ["Média eixo X", f"{summary['avg_x']:+.3f}"],
        ["Média eixo Y", f"{summary['avg_y']:+.3f}"],
        ["Média eixo Z", f"{summary['avg_z']:+.3f}"],
        ["Roll médio", f"{summary['avg_roll']:+.2f}°"],
        ["Velocidade média", f"{summary['avg_velocity']:.3f}"],
        ["Entropia de foco", f"{summary['focus_entropy']:.3f}"],
    ]

    table = Table(table_data, colWidths=[6.2 * cm, 9.7 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f7f9fd")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Interpretação automática", styles["Heading2"]))
    story.append(Paragraph(interp, styles["BodyText"]))
    story.append(Spacer(1, 0.3 * cm))

    for img_path, title in [
        (cube_path, "Cenário 3D com microspontos e ilusão óptica"),
        (heat_path, "Mapa de calor das áreas mais observadas"),
        (frame_path, "Último frame da sessão"),
    ]:
        p = Path(img_path)
        if p.exists() and p.stat().st_size > 0:
            story.append(Paragraph(title, styles["Heading3"]))
            story.append(RLImage(str(p), width=16.5 * cm, height=9.2 * cm))
            story.append(Spacer(1, 0.25 * cm))

    story.append(
        Paragraph(
            "Observação metodológica: esta versão está em estágio inicial. "
            "A direção do olhar é estimada por landmarks faciais/íris e não substitui "
            "eye tracking clínico ou biométrico de alta precisão.",
            styles["Italic"],
        )
    )

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


# =========================================================
# UI
# =========================================================
st.title("👁️ Simulacro — Tracking 3D com Quaternions + Heatmap + PDF")
st.caption("Protótipo inicial com rastreamento ocular simplificado, cubo 3D responsivo e análise de dados.")

with st.sidebar:
    st.header("Controles")
    grid_n = st.slider("Resolução do cubo (microspontos)", 10, 28, 18)
    optical_strength = st.slider("Força da ilusão óptica", 0.00, 0.80, 0.32, 0.01)
    quat_strength = st.slider("Força da rotação por quaternion", 0.00, 1.20, 0.55, 0.01)
    shared.max_samples = st.slider("Máximo de amostras", 500, 12000, DEFAULT_MAX_SAMPLES, 500)

    if st.button("Iniciar nova sessão", use_container_width=True):
        shared.samples = []
        st.success("Sessão reiniciada.")

    if st.button("Limpar dados", use_container_width=True):
        shared.samples = []
        st.warning("Dados removidos.")

cam_col, vis_col = st.columns([1.0, 1.15])

with cam_col:
    st.subheader("Webcam / tracking")
    webrtc_ctx = webrtc_streamer(
        key="simulacro-eye-tracking",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": {"width": FRAME_W, "height": FRAME_H}, "audio": False},
        video_processor_factory=EyeTrackingProcessor,
        async_processing=True,
    )

    metrics = shared.latest_metrics
    a, b, c, d = st.columns(4)
    a.metric("Rosto", "OK" if metrics["face_found"] else "—")
    b.metric("Piscadas", metrics["blink_count"])
    c.metric("Amostras", metrics["samples"])
    d.metric("Roll", f"{metrics['roll_deg']:.1f}°")

    st.write(
        {
            "gaze_x_norm": round(metrics["gaze_x"], 4),
            "gaze_y_norm": round(metrics["gaze_y"], 4),
            "velocity": round(metrics["velocity"], 4),
        }
    )

with vis_col:
    st.subheader("Cubo 3D com microspontos")
    fig3d = cube_figure(
        shared.samples,
        grid_n=grid_n,
        optical_strength=optical_strength,
        quat_strength=quat_strength,
    )
    st.plotly_chart(fig3d, use_container_width=True)

heat_col, data_col = st.columns([1.0, 1.0])

with heat_col:
    st.subheader("Mapa de calor")
    st.plotly_chart(heatmap_figure(shared.samples), use_container_width=True)

with data_col:
    st.subheader("Dados recentes")
    if shared.samples:
        df = pd.DataFrame([asdict(s) for s in shared.samples[-25:]])
        st.dataframe(df, use_container_width=True, height=370)
    else:
        st.info("Ainda sem amostras. Autorize a câmera e olhe para a tela.")

st.markdown("---")
st.subheader("Análise da sessão")

summary = summarize_samples(shared.samples, grid_n=grid_n)
interp = interpret_summary(summary)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Duração", f"{summary['duration_s']:.1f}s")
m2.metric("Amostras", summary["sample_count"])
m3.metric("Piscadas", summary["blinks"])
m4.metric("Região pico", summary["peak_region"])
m5.metric("Velocidade média", f"{summary['avg_velocity']:.3f}")

st.write(interp)

pdf_bytes = generate_pdf(shared.samples, shared.latest_frame_bgr)
st.download_button(
    "📄 Baixar relatório PDF",
    data=pdf_bytes,
    file_name="relatorio_simulacro_tracking_3d.pdf",
    mime="application/pdf",
    use_container_width=True,
)

with st.expander("Notas técnicas"):
    st.markdown(
        """
- Tracking em **estágio inicial**, baseado em webcam comum.
- O cubo responde com **rotação por quaternion** e **distorção óptica**.
- O heatmap exportado no PDF mostra as **áreas mais observadas**.
- A próxima melhoria ideal é adicionar **calibração de 5 pontos**.
        """
    )
