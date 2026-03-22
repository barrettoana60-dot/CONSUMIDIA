import io
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from matplotlib import pyplot as plt
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

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(
    page_title="Simulacro — Tracking 3D Snapshot",
    page_icon="👁️",
    layout="wide",
)

DEFAULT_MAX_SAMPLES = 8000
DEFAULT_GRID_N = 18

# =========================================================
# SESSION STATE
# =========================================================
if "samples" not in st.session_state:
    st.session_state.samples = []
if "blink_count" not in st.session_state:
    st.session_state.blink_count = 0
if "last_frame_bgr" not in st.session_state:
    st.session_state.last_frame_bgr = None
if "last_processed_hash" not in st.session_state:
    st.session_state.last_processed_hash = None
if "prev_eye_state" not in st.session_state:
    st.session_state.prev_eye_state = "open"
if "session_started_at" not in st.session_state:
    st.session_state.session_started_at = None
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = {
        "face_found": False,
        "gaze_x_norm": 0.5,
        "gaze_y_norm": 0.5,
        "roll_deg": 0.0,
        "velocity": 0.0,
        "sample_count": 0,
    }

# =========================================================
# UTILITÁRIOS
# =========================================================
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def gaussian_stamp(grid: np.ndarray, gx: float, gy: float, sigma: float = 1.2, amp: float = 1.0) -> None:
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
    head_roll_deg: float
    blink: int
    velocity: float


# =========================================================
# OPENCV CASCADES
# =========================================================
@st.cache_resource
def load_cascades():
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    if face.empty() or eye.empty():
        raise RuntimeError("Não foi possível carregar as Haar Cascades do OpenCV.")
    return face, eye


FACE_CASCADE, EYE_CASCADE = load_cascades()


def estimate_pupil_center(eye_roi_gray: np.ndarray) -> Optional[Tuple[float, float]]:
    if eye_roi_gray is None or eye_roi_gray.size == 0:
        return None

    roi = cv2.GaussianBlur(eye_roi_gray, (7, 7), 0)
    _, thr = cv2.threshold(roi, 45, 255, cv2.THRESH_BINARY_INV)

    h, w = thr.shape[:2]
    mask = np.zeros_like(thr)
    cv2.rectangle(mask, (int(w * 0.15), int(h * 0.18)), (int(w * 0.85), int(h * 0.88)), 255, -1)
    thr = cv2.bitwise_and(thr, mask)

    cnts, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None

    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
    for c in cnts[:5]:
        area = cv2.contourArea(c)
        if area < 8:
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]
        return (cx, cy)

    return None


def detect_face_and_eyes(gray: np.ndarray):
    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(120, 120),
    )
    if len(faces) == 0:
        return None, []

    faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
    x, y, w, h = faces[0]
    face_roi = gray[y:y + h, x:x + w]

    eyes = EYE_CASCADE.detectMultiScale(
        face_roi,
        scaleFactor=1.08,
        minNeighbors=8,
        minSize=(28, 28),
    )

    eye_boxes = []
    for (ex, ey, ew, eh) in eyes:
        eye_boxes.append((x + ex, y + ey, ew, eh))

    eye_boxes = sorted(eye_boxes, key=lambda b: b[2] * b[3], reverse=True)[:2]
    eye_boxes = sorted(eye_boxes, key=lambda b: b[0])

    return (x, y, w, h), eye_boxes


def process_snapshot(image_bgr: np.ndarray):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    out = image_bgr.copy()

    face_box, eyes = detect_face_and_eyes(gray)

    face_found = False
    blink_now = 0
    velocity = 0.0
    gaze_x_norm = st.session_state.last_metrics["gaze_x_norm"]
    gaze_y_norm = st.session_state.last_metrics["gaze_y_norm"]
    roll_deg = st.session_state.last_metrics["roll_deg"]

    if face_box is not None:
        face_found = True
        fx, fy, fw, fh = face_box
        cv2.rectangle(out, (fx, fy), (fx + fw, fy + fh), (80, 180, 255), 2)

        eye_data = []
        for (ex, ey, ew, eh) in eyes:
            roi = gray[ey:ey + eh, ex:ex + ew]
            pupil = estimate_pupil_center(roi)
            cv2.rectangle(out, (ex, ey), (ex + ew, ey + eh), (0, 255, 120), 2)

            if pupil is not None:
                px = ex + pupil[0]
                py = ey + pupil[1]
                cv2.circle(out, (int(px), int(py)), 4, (0, 0, 255), -1)

                nx = clamp(pupil[0] / max(1.0, ew), 0.0, 1.0)
                ny = clamp(pupil[1] / max(1.0, eh), 0.0, 1.0)
                eye_data.append((ex, ey, ew, eh, px, py, nx, ny))

        if len(eye_data) == 2:
            left_eye, right_eye = eye_data[0], eye_data[1]

            avg_nx = (left_eye[6] + right_eye[6]) / 2.0
            avg_ny = (left_eye[7] + right_eye[7]) / 2.0

            raw_gaze_x = clamp((avg_nx - 0.5) * 2.0, -1.0, 1.0)
            raw_gaze_y = clamp((avg_ny - 0.5) * 2.0, -1.0, 1.0)

            gaze_x_norm = lerp(gaze_x_norm, (raw_gaze_x + 1.0) / 2.0, 0.35)
            gaze_y_norm = lerp(gaze_y_norm, (raw_gaze_y + 1.0) / 2.0, 0.35)

            left_center = (left_eye[4], left_eye[5])
            right_center = (right_eye[4], right_eye[5])
            roll_deg = math.degrees(math.atan2(left_center[1] - right_center[1], left_center[0] - right_center[0]))

            eye_open_score = 0.0
            for ed in eye_data:
                _, _, ew, eh, _, _, _, _ = ed
                eye_open_score += eh / max(1.0, ew)
            eye_open_score /= 2.0

            curr_state = "closed" if eye_open_score < 0.32 else "open"
            prev_state = st.session_state.prev_eye_state
            if prev_state == "closed" and curr_state == "open":
                st.session_state.blink_count += 1
                blink_now = 1
            st.session_state.prev_eye_state = curr_state

            cube_x = gaze_x_norm * 2.0 - 1.0
            cube_y = -(gaze_y_norm * 2.0 - 1.0)
            radial = math.sqrt(cube_x * cube_x + cube_y * cube_y)
            cube_z = clamp(1.0 - radial * 0.75, -1.0, 1.0)

            if st.session_state.samples:
                prev = st.session_state.samples[-1]
                dt = max(1e-5, time.time() - prev.ts)
                velocity = math.sqrt((cube_x - prev.cube_x) ** 2 + (cube_y - prev.cube_y) ** 2) / dt

            sample = GazeSample(
                ts=time.time(),
                gaze_x_norm=float(gaze_x_norm),
                gaze_y_norm=float(gaze_y_norm),
                cube_x=float(cube_x),
                cube_y=float(cube_y),
                cube_z=float(cube_z),
                head_roll_deg=float(roll_deg),
                blink=int(blink_now),
                velocity=float(velocity),
            )
            st.session_state.samples.append(sample)

            if len(st.session_state.samples) > DEFAULT_MAX_SAMPLES:
                st.session_state.samples = st.session_state.samples[-DEFAULT_MAX_SAMPLES:]

            px = int(gaze_x_norm * out.shape[1])
            py = int(gaze_y_norm * out.shape[0])
            cv2.circle(out, (px, py), 18, (0, 255, 255), 2)
            cv2.circle(out, (px, py), 4, (255, 255, 255), -1)

            cv2.putText(out, f"gaze=({cube_x:+.2f},{cube_y:+.2f},{cube_z:+.2f})",
                        (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (40, 255, 80), 2)
            cv2.putText(out, f"blinks={st.session_state.blink_count}",
                        (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 60), 2)
            cv2.putText(out, f"vel={velocity:.2f}",
                        (20, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 160, 160), 2)

    st.session_state.last_metrics = {
        "face_found": face_found,
        "gaze_x_norm": float(gaze_x_norm),
        "gaze_y_norm": float(gaze_y_norm),
        "roll_deg": float(roll_deg),
        "velocity": float(velocity),
        "sample_count": len(st.session_state.samples),
    }
    st.session_state.last_frame_bgr = out
    return out


# =========================================================
# HEATMAP / CUBO
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
        gx = clamp((s.cube_x + 1.0) / 2.0, 0.0, 1.0)
        gy = clamp((s.cube_y + 1.0) / 2.0, 0.0, 1.0)
        gy = 1.0 - gy
        gaussian_stamp(heat, gx, gy, sigma=1.0, amp=1.0)
    return heat


def optical_distortion(x: float, y: float, gaze_x: float, gaze_y: float, strength: float) -> Tuple[float, float, float]:
    r = math.sqrt(x * x + y * y)
    warp = (1.0 - min(1.0, r)) * strength
    dx = x + gaze_x * warp * (1.0 - abs(x) * 0.35)
    dy = y + gaze_y * warp * (1.0 - abs(y) * 0.35)
    dz = 1.0 + (1.0 - min(1.0, r)) * 0.22 * strength
    return dx, dy, dz


def cube_figure(
    samples: List[GazeSample],
    grid_n: int = DEFAULT_GRID_N,
    optical_strength: float = 0.34,
    quat_strength: float = 0.58,
) -> go.Figure:
    base = build_front_face_points(grid_n)
    heat = build_heat_grid(samples, grid_n)

    if samples:
        recent = samples[-20:]
        gaze_x = float(np.mean([s.cube_x for s in recent]))
        gaze_y = float(np.mean([s.cube_y for s in recent]))
        roll_deg = float(np.mean([s.head_roll_deg for s in recent]))
        motion = float(np.mean([s.velocity for s in recent]))
    else:
        gaze_x = gaze_y = roll_deg = motion = 0.0

    axis_x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    axis_y = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    axis_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    qx = quat_from_axis_angle(axis_x, -gaze_y * quat_strength * 0.36)
    qy = quat_from_axis_angle(axis_y, gaze_x * quat_strength * 0.36)
    qz = quat_from_axis_angle(axis_z, math.radians(roll_deg * 0.22))
    q = quat_multiply(qz, quat_multiply(qy, qx))

    xs, ys, zs = [], [], []
    heat_flat = heat.flatten()

    for i, row in base.iterrows():
        x = float(row["x"])
        y = float(row["y"])
        z = float(row["z"])

        x, y, z = optical_distortion(x, y, gaze_x, gaze_y, optical_strength)

        vibr = 0.018 * min(1.0, motion / 3.0)
        x += math.sin(i * 0.31 + motion) * vibr
        y += math.cos(i * 0.19 + motion) * vibr

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
                opacity=0.97,
                colorbar=dict(title="Calor"),
            ),
            name="Microspontos",
        )
    )

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
        x=1.55 + gaze_x * 0.30,
        y=1.55 + gaze_y * 0.30,
        z=1.10 + (0.12 * (1.0 - min(1.0, math.sqrt(gaze_x * gaze_x + gaze_y * gaze_y)))),
    )

    fig.update_layout(
        title="Cubo 3D com microspontos, quaternions e ilusão óptica",
        height=620,
        margin=dict(l=0, r=0, t=42, b=0),
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
        margin=dict(l=10, r=10, t=42, b=10),
    )
    return fig


# =========================================================
# ANÁLISE
# =========================================================
def summarize_samples(samples: List[GazeSample], grid_n: int = DEFAULT_GRID_N) -> dict:
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
        "avg_roll": float(df["head_roll_deg"].mean()),
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
        f"A sessão durou {summary['duration_s']:.1f}s, com {summary['sample_count']} amostras e "
        f"{summary['blinks']} piscadas. A distribuição do olhar foi {focus_type}, sugerindo "
        f"{'exploração ampla da cena' if focus_type == 'mais dispersa' else 'fixação mais intensa em áreas específicas'}. "
        f"A velocidade média do olhar foi {motion_type} ({summary['avg_velocity']:.3f}). "
        f"A região de maior incidência foi {summary['peak_region']}. "
        f"Médias no cubo: X={summary['avg_x']:+.3f}, Y={summary['avg_y']:+.3f}, Z={summary['avg_z']:+.3f}. "
        f"Roll médio: {summary['avg_roll']:+.2f}°."
    )


# =========================================================
# EXPORTAÇÃO PDF
# =========================================================
def save_heatmap_png(samples: List[GazeSample], path: str, n: int = 42):
    heat = np.zeros((n, n), dtype=np.float32)
    for s in samples:
        gaussian_stamp(heat, s.gaze_x_norm, s.gaze_y_norm, sigma=1.25, amp=1.0)

    plt.figure(figsize=(8, 5))
    plt.imshow(heat, cmap="turbo", aspect="auto")
    plt.title("Mapa de calor das áreas mais observadas")
    plt.colorbar(label="Intensidade")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def save_cube_projection_png(
    samples: List[GazeSample],
    path: str,
    grid_n: int = DEFAULT_GRID_N,
    optical_strength: float = 0.34,
    quat_strength: float = 0.58,
):
    base = build_front_face_points(grid_n)
    heat = build_heat_grid(samples, grid_n)

    if samples:
        recent = samples[-20:]
        gaze_x = float(np.mean([s.cube_x for s in recent]))
        gaze_y = float(np.mean([s.cube_y for s in recent]))
        roll_deg = float(np.mean([s.head_roll_deg for s in recent]))
    else:
        gaze_x = gaze_y = roll_deg = 0.0

    axis_x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    axis_y = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    axis_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    qx = quat_from_axis_angle(axis_x, -gaze_y * quat_strength * 0.36)
    qy = quat_from_axis_angle(axis_y, gaze_x * quat_strength * 0.36)
    qz = quat_from_axis_angle(axis_z, math.radians(roll_deg * 0.22))
    q = quat_multiply(qz, quat_multiply(qy, qx))

    xs, ys, cs = [], [], []
    for i, row in base.iterrows():
        x, y, z = optical_distortion(float(row["x"]), float(row["y"]), gaze_x, gaze_y, optical_strength)
        vec = quat_rotate_vector(q, np.array([x, y, z], dtype=np.float64))
        xs.append(vec[0])
        ys.append(vec[1])
        cs.append(heat.flatten()[i])

    plt.figure(figsize=(7, 7))
    plt.scatter(xs, ys, c=cs, cmap="turbo", s=28)
    plt.title("Projeção do cubo 3D com microspontos")
    plt.axis("equal")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def generate_pdf(samples: List[GazeSample], frame_bgr: Optional[np.ndarray]) -> bytes:
    summary = summarize_samples(samples)
    interp = interpret_summary(summary)

    tmp = Path("tmp_simulacro")
    tmp.mkdir(exist_ok=True)

    heat_path = str(tmp / "heatmap.png")
    cube_path = str(tmp / "cube_proj.png")
    frame_path = str(tmp / "frame.png")

    save_heatmap_png(samples, heat_path)
    save_cube_projection_png(samples, cube_path)

    if frame_bgr is not None:
        cv2.imwrite(frame_path, frame_bgr)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.3 * cm,
        leftMargin=1.3 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Simulacro — Relatório de Rastreamento Ocular 3D", styles["Title"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        Paragraph(
            "Relatório experimental com tracking ocular em estágio inicial, projeção em cubo 3D "
            "de microspontos, rotação por quaternions, ilusão óptica e mapa de calor das áreas mais observadas.",
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

    table = Table(table_data, colWidths=[6.3 * cm, 9.6 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9ff")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f7f9fd")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("Interpretação automática", styles["Heading2"]))
    story.append(Paragraph(interp, styles["BodyText"]))
    story.append(Spacer(1, 0.25 * cm))

    for img_path, title in [
        (heat_path, "Mapa de calor das áreas mais observadas"),
        (cube_path, "Projeção do cubo 3D com microspontos"),
        (frame_path, "Último frame da sessão"),
    ]:
        p = Path(img_path)
        if p.exists() and p.stat().st_size > 0:
            story.append(Paragraph(title, styles["Heading3"]))
            story.append(RLImage(str(p), width=16.7 * cm, height=9.3 * cm))
            story.append(Spacer(1, 0.2 * cm))

    story.append(
        Paragraph(
            "Observação metodológica: este protótipo usa detecção clássica de rosto/olhos do OpenCV e "
            "estimativa simplificada da posição pupilar. Ele é adequado para experimentação visual e mapa de atenção, "
            "não para uso clínico ou biométrico de alta precisão.",
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
st.title("👁️ Simulacro — Tracking 3D Snapshot + Quaternions + PDF")
st.caption("Versão estável para Streamlit Cloud sem MediaPipe e sem streamlit-webrtc.")

with st.sidebar:
    st.header("Controles")
    grid_n = st.slider("Resolução do cubo", 10, 28, DEFAULT_GRID_N)
    optical_strength = st.slider("Força da ilusão óptica", 0.00, 0.80, 0.34, 0.01)
    quat_strength = st.slider("Força do quaternion", 0.00, 1.20, 0.58, 0.01)

    if st.button("Iniciar nova sessão", width="stretch"):
        st.session_state.samples = []
        st.session_state.blink_count = 0
        st.session_state.last_frame_bgr = None
        st.session_state.last_processed_hash = None
        st.session_state.prev_eye_state = "open"
        st.session_state.session_started_at = time.time()
        st.success("Sessão reiniciada.")

    if st.button("Limpar dados", width="stretch"):
        st.session_state.samples = []
        st.session_state.blink_count = 0
        st.warning("Dados removidos.")

left, right = st.columns([1.0, 1.15])

with left:
    st.subheader("Captura da câmera")
    st.markdown("Use a câmera abaixo e faça capturas sucessivas para acumular a sessão.")
    camera_file = st.camera_input("Tirar foto para análise")

    if camera_file is not None:
        file_bytes = camera_file.getvalue()
        current_hash = hash(file_bytes)

        if st.session_state.session_started_at is None:
            st.session_state.session_started_at = time.time()

        if current_hash != st.session_state.last_processed_hash:
            pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            processed = process_snapshot(img_bgr)
            st.session_state.last_processed_hash = current_hash
            st.image(cv2.cvtColor(processed, cv2.COLOR_BGR2RGB), caption="Frame processado", width="stretch")
        elif st.session_state.last_frame_bgr is not None:
            st.image(cv2.cvtColor(st.session_state.last_frame_bgr, cv2.COLOR_BGR2RGB), caption="Último frame processado", width="stretch")

    metrics = st.session_state.last_metrics
    a, b, c, d = st.columns(4)
    a.metric("Rosto", "OK" if metrics["face_found"] else "—")
    b.metric("Piscadas", st.session_state.blink_count)
    c.metric("Amostras", metrics["sample_count"])
    d.metric("Roll", f"{metrics['roll_deg']:.1f}°")

    st.write(
        {
            "gaze_x_norm": round(metrics["gaze_x_norm"], 4),
            "gaze_y_norm": round(metrics["gaze_y_norm"], 4),
            "velocity": round(metrics["velocity"], 4),
        }
    )

with right:
    st.subheader("Cubo 3D com microspontos")
    fig3d = cube_figure(
        st.session_state.samples,
        grid_n=grid_n,
        optical_strength=optical_strength,
        quat_strength=quat_strength,
    )
    st.plotly_chart(fig3d, width="stretch")

heat_col, data_col = st.columns([1.0, 1.0])

with heat_col:
    st.subheader("Mapa de calor")
    st.plotly_chart(heatmap_figure(st.session_state.samples), width="stretch")

with data_col:
    st.subheader("Amostras recentes")
    if st.session_state.samples:
        df = pd.DataFrame([asdict(s) for s in st.session_state.samples[-25:]])
        st.dataframe(df, width="stretch", height=370)
    else:
        st.info("Ainda sem amostras. Tire fotos sucessivas com a câmera para acumular o tracking.")

st.markdown("---")
st.subheader("Análise da sessão")

summary = summarize_samples(st.session_state.samples, grid_n=grid_n)
interp = interpret_summary(summary)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Duração", f"{summary['duration_s']:.1f}s")
m2.metric("Amostras", summary["sample_count"])
m3.metric("Piscadas", summary["blinks"])
m4.metric("Região pico", summary["peak_region"])
m5.metric("Velocidade média", f"{summary['avg_velocity']:.3f}")

st.write(interp)

pdf_bytes = generate_pdf(st.session_state.samples, st.session_state.last_frame_bgr)
st.download_button(
    "📄 Baixar relatório PDF",
    data=pdf_bytes,
    file_name="relatorio_simulacro_tracking_3d.pdf",
    mime="application/pdf",
    width="stretch",
)

with st.expander("Notas técnicas"):
    st.markdown(
        """
- Esta versão foi feita para ser **mais estável no Streamlit Cloud**.
- O tracking é **inicial** e baseado em OpenCV clássico com snapshots da câmera.
- O cubo usa **quaternions** e **distorção óptica**.
- O PDF exporta **heatmap**, **projeção do cubo** e **último frame**.
- Próxima melhoria ideal: calibração de 5 pontos e componente frontend dedicado para vídeo contínuo.
        """
    )
