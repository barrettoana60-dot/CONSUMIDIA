rom __future__ import annotations

import io
import math
import os
import time
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple
from collections import deque

import av
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from streamlit_webrtc import WebRtcMode, VideoProcessorBase, webrtc_streamer

# =============================================================================
# Streamlit page config
# =============================================================================

st.set_page_config(
    page_title="Rastreamento de Íris - Streamlit",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# Robust MediaPipe import helpers
# =============================================================================

def load_mediapipe_face_mesh():
    """
    Load a Face Mesh module in a way that works across multiple MediaPipe layouts.

    Older code commonly uses:
        import mediapipe as mp
        mp_face_mesh = mp.solutions.face_mesh

    But reports from late 2025 onward indicate that top-level `mp.solutions`
    may no longer be exposed in some releases. We therefore try both the
    traditional top-level path and the direct python submodule path before
    failing with a clear message.
    """
    import mediapipe as mp

    # path 1: classic
    if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
        return mp, mp.solutions.face_mesh

    # path 2: direct import from python.solutions
    try:
        from mediapipe.python.solutions import face_mesh as mp_face_mesh  # type: ignore
        return mp, mp_face_mesh
    except Exception as exc:
        raise RuntimeError(
            "Não foi possível carregar o Face Mesh do MediaPipe. "
            "Use mediapipe==0.10.21 ou outra versão compatível com Face Mesh."
        ) from exc


MP, MP_FACE_MESH = load_mediapipe_face_mesh()

# drawing utils are optional for this app
try:
    MP_DRAWING = MP.solutions.drawing_utils if hasattr(MP, "solutions") else None
except Exception:
    MP_DRAWING = None


# =============================================================================
# Constants and landmark groups
# =============================================================================

LEFT_IRIS_IDX = [474, 475, 476, 477]
RIGHT_IRIS_IDX = [469, 470, 471, 472]

LEFT_EYE_OUTER = 33
LEFT_EYE_INNER = 133
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145

RIGHT_EYE_OUTER = 362
RIGHT_EYE_INNER = 263
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374

LEFT_EYE_RING = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE_RING = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]

DEFAULT_RTC_CONFIGURATION = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

# =============================================================================
# Data classes
# =============================================================================

@dataclass
class IrisDetection:
    timestamp: float = 0.0
    frame_w: int = 0
    frame_h: int = 0
    left_center: Optional[Tuple[int, int]] = None
    right_center: Optional[Tuple[int, int]] = None
    gaze_point: Optional[Tuple[int, int]] = None
    left_ratio_x: Optional[float] = None
    right_ratio_x: Optional[float] = None
    left_ratio_y: Optional[float] = None
    right_ratio_y: Optional[float] = None
    blink_ratio: Optional[float] = None
    blink_state: str = "open"
    fps: Optional[float] = None
    success: bool = False
    status: str = "idle"


@dataclass
class CalibPoint:
    name: str
    x: float
    y: float


@dataclass
class TrackerConfig:
    max_faces: int = 1
    refine_landmarks: bool = True
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    blink_threshold: float = 0.21
    blink_cooldown_sec: float = 0.22
    smoothing_alpha: float = 0.35
    heatmap_decay: float = 0.995
    show_mesh: bool = False
    show_eye_ring: bool = True
    show_iris: bool = True
    show_info: bool = True
    debug_text: bool = True
    draw_crosshair: bool = True
    gaze_gain_x: float = 1.6
    gaze_gain_y: float = 1.4


@dataclass
class SharedRuntime:
    metrics_queue: "queue.Queue[Dict[str, Any]]" = field(default_factory=queue.Queue)
    csv_rows: List[Dict[str, Any]] = field(default_factory=list)
    heatmap: Optional[np.ndarray] = None
    latest_frame_bgr: Optional[np.ndarray] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    calibrated: bool = False
    calibration_map: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    last_click_label: Optional[str] = None
    start_time: float = field(default_factory=time.time)


# =============================================================================
# Session state helpers
# =============================================================================

def init_state():
    if "tracker_config" not in st.session_state:
        st.session_state.tracker_config = TrackerConfig()
    if "runtime" not in st.session_state:
        st.session_state.runtime = SharedRuntime()
    if "processor_alive" not in st.session_state:
        st.session_state.processor_alive = False
    if "latest_metrics" not in st.session_state:
        st.session_state.latest_metrics = {}
    if "calibration_targets" not in st.session_state:
        st.session_state.calibration_targets = [
            CalibPoint("top_left", 0.12, 0.15),
            CalibPoint("top_right", 0.88, 0.15),
            CalibPoint("center", 0.50, 0.50),
            CalibPoint("bottom_left", 0.12, 0.85),
            CalibPoint("bottom_right", 0.88, 0.85),
        ]
    if "selected_calibration_target" not in st.session_state:
        st.session_state.selected_calibration_target = "center"


init_state()

# =============================================================================
# Geometry helpers
# =============================================================================

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def as_int_point(x: float, y: float) -> Tuple[int, int]:
    return int(round(x)), int(round(y))


def euclidean(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return float(math.hypot(p1[0] - p2[0], p1[1] - p2[1]))


def safe_mean(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    if not points:
        return None
    arr = np.array(points, dtype=np.float32)
    return float(arr[:, 0].mean()), float(arr[:, 1].mean())


def lerp(a: float, b: float, alpha: float) -> float:
    return (1.0 - alpha) * a + alpha * b


def smooth_point(prev: Optional[Tuple[float, float]], cur: Optional[Tuple[float, float]], alpha: float) -> Optional[Tuple[float, float]]:
    if cur is None:
        return prev
    if prev is None:
        return cur
    return (
        lerp(prev[0], cur[0], alpha),
        lerp(prev[1], cur[1], alpha),
    )


# =============================================================================
# Landmark helpers
# =============================================================================

def landmark_xy(landmarks, index: int, w: int, h: int) -> Tuple[float, float]:
    lm = landmarks[index]
    return lm.x * w, lm.y * h


def points_from_indices(landmarks, indices: List[int], w: int, h: int) -> List[Tuple[float, float]]:
    return [landmark_xy(landmarks, idx, w, h) for idx in indices]


def iris_center_from_landmarks(landmarks, iris_indices: List[int], w: int, h: int) -> Optional[Tuple[float, float]]:
    pts = points_from_indices(landmarks, iris_indices, w, h)
    return safe_mean(pts)


def blink_ratio_from_landmarks(landmarks, w: int, h: int) -> float:
    l_top = landmark_xy(landmarks, LEFT_EYE_TOP, w, h)
    l_bottom = landmark_xy(landmarks, LEFT_EYE_BOTTOM, w, h)
    l_outer = landmark_xy(landmarks, LEFT_EYE_OUTER, w, h)
    l_inner = landmark_xy(landmarks, LEFT_EYE_INNER, w, h)

    r_top = landmark_xy(landmarks, RIGHT_EYE_TOP, w, h)
    r_bottom = landmark_xy(landmarks, RIGHT_EYE_BOTTOM, w, h)
    r_outer = landmark_xy(landmarks, RIGHT_EYE_OUTER, w, h)
    r_inner = landmark_xy(landmarks, RIGHT_EYE_INNER, w, h)

    l_h = euclidean(l_outer, l_inner) + 1e-6
    r_h = euclidean(r_outer, r_inner) + 1e-6
    l_v = euclidean(l_top, l_bottom)
    r_v = euclidean(r_top, r_bottom)

    l_ratio = l_v / l_h
    r_ratio = r_v / r_h
    return float((l_ratio + r_ratio) / 2.0)


def eye_box_and_ratios(
    landmarks,
    iris_center: Optional[Tuple[float, float]],
    outer_idx: int,
    inner_idx: int,
    top_idx: int,
    bottom_idx: int,
    w: int,
    h: int,
) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[float], Optional[float]]:
    if iris_center is None:
        return None, None, None

    p_outer = landmark_xy(landmarks, outer_idx, w, h)
    p_inner = landmark_xy(landmarks, inner_idx, w, h)
    p_top = landmark_xy(landmarks, top_idx, w, h)
    p_bottom = landmark_xy(landmarks, bottom_idx, w, h)

    xs = [p_outer[0], p_inner[0], iris_center[0]]
    ys = [p_top[1], p_bottom[1], iris_center[1]]

    x_min, x_max = min(p_outer[0], p_inner[0]), max(p_outer[0], p_inner[0])
    y_min, y_max = min(p_top[1], p_bottom[1]), max(p_top[1], p_bottom[1])

    width = max(1.0, x_max - x_min)
    height = max(1.0, y_max - y_min)

    ratio_x = clamp((iris_center[0] - x_min) / width, 0.0, 1.0)
    ratio_y = clamp((iris_center[1] - y_min) / height, 0.0, 1.0)

    box = (
        int(round(min(xs) - 8)),
        int(round(min(ys) - 8)),
        int(round(max(xs) + 8)),
        int(round(max(ys) + 8)),
    )
    return box, ratio_x, ratio_y


# =============================================================================
# Gaze mapping
# =============================================================================

def normalized_gaze_from_eye_ratios(
    left_rx: Optional[float],
    right_rx: Optional[float],
    left_ry: Optional[float],
    right_ry: Optional[float],
) -> Optional[Tuple[float, float]]:
    valid_x = [v for v in [left_rx, right_rx] if v is not None]
    valid_y = [v for v in [left_ry, right_ry] if v is not None]
    if not valid_x or not valid_y:
        return None

    avg_x = float(np.mean(valid_x))
    avg_y = float(np.mean(valid_y))

    # center around 0
    norm_x = (avg_x - 0.5) * 2.0
    norm_y = (avg_y - 0.5) * 2.0
    return clamp(norm_x, -1.0, 1.0), clamp(norm_y, -1.0, 1.0)


def apply_gain(norm_xy: Optional[Tuple[float, float]], gain_x: float, gain_y: float) -> Optional[Tuple[float, float]]:
    if norm_xy is None:
        return None
    x, y = norm_xy
    return clamp(x * gain_x, -1.2, 1.2), clamp(y * gain_y, -1.2, 1.2)


def apply_calibration(
    norm_xy: Optional[Tuple[float, float]],
    calibration_map: Dict[str, Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    """
    Simple affine-like correction using center and axis anchors when present.
    """
    if norm_xy is None:
        return None
    x, y = norm_xy

    if "center" not in calibration_map:
        return x, y

    cx, cy = calibration_map["center"]
    x -= cx
    y -= cy

    # Horizontal scaling
    if "top_left" in calibration_map and "top_right" in calibration_map:
        lx = calibration_map["top_left"][0] - cx
        rx = calibration_map["top_right"][0] - cx
        left_scale = abs(lx) if abs(lx) > 1e-6 else 1.0
        right_scale = abs(rx) if abs(rx) > 1e-6 else 1.0
        x = x / (right_scale if x >= 0 else left_scale)

    # Vertical scaling
    if "top_left" in calibration_map and "bottom_left" in calibration_map:
        ty = calibration_map["top_left"][1] - cy
        by = calibration_map["bottom_left"][1] - cy
        top_scale = abs(ty) if abs(ty) > 1e-6 else 1.0
        bottom_scale = abs(by) if abs(by) > 1e-6 else 1.0
        y = y / (bottom_scale if y >= 0 else top_scale)

    return clamp(x, -1.0, 1.0), clamp(y, -1.0, 1.0)


def gaze_point_from_normalized(norm_xy: Optional[Tuple[float, float]], w: int, h: int) -> Optional[Tuple[int, int]]:
    if norm_xy is None:
        return None
    x, y = norm_xy
    px = int(round((x + 1.0) * 0.5 * (w - 1)))
    py = int(round((y + 1.0) * 0.5 * (h - 1)))
    return max(0, min(w - 1, px)), max(0, min(h - 1, py))


# =============================================================================
# Heatmap helpers
# =============================================================================

def init_heatmap_if_needed(runtime: SharedRuntime, h: int, w: int):
    with runtime.lock:
        if runtime.heatmap is None or runtime.heatmap.shape[:2] != (h, w):
            runtime.heatmap = np.zeros((h, w), dtype=np.float32)


def update_heatmap(runtime: SharedRuntime, gaze_point: Optional[Tuple[int, int]], sigma: int = 25):
    if gaze_point is None:
        return
    with runtime.lock:
        if runtime.heatmap is None:
            return
        runtime.heatmap *= st.session_state.tracker_config.heatmap_decay
        x, y = gaze_point
        h, w = runtime.heatmap.shape
        x0 = max(0, x - sigma * 3)
        y0 = max(0, y - sigma * 3)
        x1 = min(w, x + sigma * 3 + 1)
        y1 = min(h, y + sigma * 3 + 1)

        xs = np.arange(x0, x1, dtype=np.float32)
        ys = np.arange(y0, y1, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        blob = np.exp(-(((xx - x) ** 2) + ((yy - y) ** 2)) / (2.0 * sigma * sigma))
        runtime.heatmap[y0:y1, x0:x1] += blob.astype(np.float32)


def heatmap_to_color(heatmap: np.ndarray) -> np.ndarray:
    if heatmap.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    normalized = heatmap.copy()
    max_val = float(normalized.max())
    if max_val > 0:
        normalized = normalized / max_val
    normalized_u8 = np.uint8(np.clip(normalized * 255.0, 0, 255))
    return cv2.applyColorMap(normalized_u8, cv2.COLORMAP_JET)


def overlay_heatmap_on_frame(frame_bgr: np.ndarray, heatmap: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    heat_color = heatmap_to_color(heatmap)
    if heat_color.shape[:2] != frame_bgr.shape[:2]:
        heat_color = cv2.resize(heat_color, (frame_bgr.shape[1], frame_bgr.shape[0]))
    return cv2.addWeighted(frame_bgr, 1.0 - alpha, heat_color, alpha, 0.0)


# =============================================================================
# Export helpers
# =============================================================================

def dataframe_from_rows(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=[
            "timestamp", "elapsed_sec", "gaze_x", "gaze_y",
            "left_ratio_x", "right_ratio_x", "left_ratio_y", "right_ratio_y",
            "blink_ratio", "blink_state", "fps", "status"
        ])
    return pd.DataFrame(rows)


def image_to_png_bytes(image_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image_bgr)
    if not ok:
        raise RuntimeError("Falha ao converter imagem para PNG.")
    return bytes(buf.tobytes())


def build_pdf_report(runtime: SharedRuntime) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4
    margin = 36

    rows = dataframe_from_rows(runtime.csv_rows)
    duration = time.time() - runtime.start_time
    total_frames = len(rows)
    blink_count = int((rows["blink_state"] == "blink").sum()) if not rows.empty and "blink_state" in rows.columns else 0

    pdf.setTitle("Relatório de Rastreamento de Íris")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, H - margin, "Relatório de Rastreamento de Íris")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(margin, H - margin - 24, f"Duração da sessão: {duration:.2f} s")
    pdf.drawString(margin, H - margin - 40, f"Frames/leituras salvas: {total_frames}")
    pdf.drawString(margin, H - margin - 56, f"Piscadas detectadas: {blink_count}")

    y_cursor = H - margin - 90

    with runtime.lock:
        latest_frame = runtime.latest_frame_bgr.copy() if runtime.latest_frame_bgr is not None else None
        heatmap = runtime.heatmap.copy() if runtime.heatmap is not None else None

    if latest_frame is not None:
        frame_rgb = cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)
        pil_frame = Image.fromarray(frame_rgb)
        frame_reader = ImageReader(pil_frame)
        img_w = 240
        img_h = int(img_w * pil_frame.height / pil_frame.width)
        pdf.drawString(margin, y_cursor, "Último frame:")
        pdf.drawImage(frame_reader, margin, y_cursor - img_h - 8, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')

    if heatmap is not None and latest_frame is not None:
        over = overlay_heatmap_on_frame(latest_frame, heatmap, alpha=0.4)
        over_rgb = cv2.cvtColor(over, cv2.COLOR_BGR2RGB)
        pil_over = Image.fromarray(over_rgb)
        over_reader = ImageReader(pil_over)
        img_w2 = 240
        img_h2 = int(img_w2 * pil_over.height / pil_over.width)
        x2 = margin + 260
        pdf.drawString(x2, y_cursor, "Mapa de calor:")
        pdf.drawImage(over_reader, x2, y_cursor - img_h2 - 8, width=img_w2, height=img_h2, preserveAspectRatio=True, mask='auto')
        y_cursor = y_cursor - max(img_h2, img_h) - 28 if latest_frame is not None else y_cursor - img_h2 - 28
    elif latest_frame is not None:
        y_cursor = y_cursor - img_h - 28

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, y_cursor, "Resumo")
    pdf.setFont("Helvetica", 10)

    summary_lines = [
        "Este relatório foi gerado pelo app Streamlit de rastreamento de íris.",
        "O ponto de gaze é uma estimativa derivada da posição relativa das íris nos olhos.",
        "A precisão depende de iluminação, resolução da webcam, estabilidade do rosto e calibração.",
        "Este resultado não substitui eye trackers dedicados por infravermelho.",
    ]
    yy = y_cursor - 18
    for line in summary_lines:
        pdf.drawString(margin, yy, line)
        yy -= 14

    if not rows.empty:
        yy -= 8
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(margin, yy, "Métricas")
        pdf.setFont("Helvetica", 10)
        yy -= 18

        metrics = [
            ("FPS médio", f"{rows['fps'].dropna().mean():.2f}" if "fps" in rows and rows["fps"].dropna().size else "N/A"),
            ("Razão de blink média", f"{rows['blink_ratio'].dropna().mean():.4f}" if "blink_ratio" in rows and rows["blink_ratio"].dropna().size else "N/A"),
            ("Gaze X médio", f"{rows['gaze_x'].dropna().mean():.1f}" if "gaze_x" in rows and rows["gaze_x"].dropna().size else "N/A"),
            ("Gaze Y médio", f"{rows['gaze_y'].dropna().mean():.1f}" if "gaze_y" in rows and rows["gaze_y"].dropna().size else "N/A"),
        ]
        for k, v in metrics:
            pdf.drawString(margin, yy, f"{k}: {v}")
            yy -= 14

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


# =============================================================================
# Drawing helpers
# =============================================================================

def draw_point(frame: np.ndarray, pt: Optional[Tuple[float, float]], color: Tuple[int, int, int], radius: int = 3):
    if pt is None:
        return
    cv2.circle(frame, as_int_point(pt[0], pt[1]), radius, color, -1, lineType=cv2.LINE_AA)


def draw_crosshair(frame: np.ndarray, pt: Optional[Tuple[int, int]], color: Tuple[int, int, int] = (0, 255, 255), size: int = 12, thickness: int = 1):
    if pt is None:
        return
    x, y = pt
    cv2.line(frame, (x - size, y), (x + size, y), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(frame, (x, y - size), (x, y + size), color, thickness, lineType=cv2.LINE_AA)
    cv2.circle(frame, (x, y), max(2, size // 3), color, thickness, lineType=cv2.LINE_AA)


def draw_eye_ring(frame: np.ndarray, landmarks, indices: List[int], w: int, h: int, color: Tuple[int, int, int]):
    pts = points_from_indices(landmarks, indices, w, h)
    for p in pts:
        cv2.circle(frame, as_int_point(p[0], p[1]), 1, color, -1, lineType=cv2.LINE_AA)


def draw_box(frame: np.ndarray, box: Optional[Tuple[int, int, int, int]], color: Tuple[int, int, int]):
    if box is None:
        return
    x0, y0, x1, y1 = box
    cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1, lineType=cv2.LINE_AA)


def draw_info_panel(frame: np.ndarray, det: IrisDetection):
    lines = [
        f"status: {det.status}",
        f"blink: {det.blink_state}",
        f"blink_ratio: {det.blink_ratio:.3f}" if det.blink_ratio is not None else "blink_ratio: N/A",
        f"left_rx: {det.left_ratio_x:.3f}" if det.left_ratio_x is not None else "left_rx: N/A",
        f"right_rx: {det.right_ratio_x:.3f}" if det.right_ratio_x is not None else "right_rx: N/A",
        f"left_ry: {det.left_ratio_y:.3f}" if det.left_ratio_y is not None else "left_ry: N/A",
        f"right_ry: {det.right_ratio_y:.3f}" if det.right_ratio_y is not None else "right_ry: N/A",
        f"fps: {det.fps:.1f}" if det.fps is not None else "fps: N/A",
    ]
    pad = 8
    line_h = 16
    x0, y0 = 10, 10
    w = 250
    h = pad * 2 + line_h * len(lines)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + w, y0 + h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
    y = y0 + 18
    for line in lines:
        cv2.putText(frame, line, (x0 + pad, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        y += line_h


# =============================================================================
# Processor
# =============================================================================

class StreamlitIrisProcessor(VideoProcessorBase):
    def __init__(self):
        self.cfg = st.session_state.tracker_config
        self.runtime = st.session_state.runtime
        self.face_mesh = MP_FACE_MESH.FaceMesh(
            static_image_mode=False,
            max_num_faces=self.cfg.max_faces,
            refine_landmarks=self.cfg.refine_landmarks,
            min_detection_confidence=self.cfg.min_detection_confidence,
            min_tracking_confidence=self.cfg.min_tracking_confidence,
        )
        self.prev_gaze_norm: Optional[Tuple[float, float]] = None
        self.prev_gaze_px: Optional[Tuple[float, float]] = None
        self.prev_t = time.time()
        self.prev_blink = False
        self.last_blink_event_ts = 0.0
        st.session_state.processor_alive = True

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        out = img.copy()
        h, w = out.shape[:2]
        init_heatmap_if_needed(self.runtime, h, w)

        now = time.time()
        dt = max(1e-6, now - self.prev_t)
        fps = 1.0 / dt
        self.prev_t = now

        det = IrisDetection(
            timestamp=now,
            frame_w=w,
            frame_h=h,
            fps=fps,
            status="no_face",
        )

        try:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            if not results.multi_face_landmarks:
                if self.cfg.show_info:
                    draw_info_panel(out, det)
                self._push_metrics(det)
                with self.runtime.lock:
                    self.runtime.latest_frame_bgr = out.copy()
                return av.VideoFrame.from_ndarray(out, format="bgr24")

            face_landmarks = results.multi_face_landmarks[0].landmark

            left_center = iris_center_from_landmarks(face_landmarks, LEFT_IRIS_IDX, w, h)
            right_center = iris_center_from_landmarks(face_landmarks, RIGHT_IRIS_IDX, w, h)

            left_box, left_rx, left_ry = eye_box_and_ratios(
                face_landmarks, left_center,
                LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_EYE_TOP, LEFT_EYE_BOTTOM, w, h
            )
            right_box, right_rx, right_ry = eye_box_and_ratios(
                face_landmarks, right_center,
                RIGHT_EYE_OUTER, RIGHT_EYE_INNER, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM, w, h
            )

            blink_ratio = blink_ratio_from_landmarks(face_landmarks, w, h)
            is_blink = blink_ratio < self.cfg.blink_threshold

            if is_blink and (now - self.last_blink_event_ts) > self.cfg.blink_cooldown_sec and not self.prev_blink:
                blink_state = "blink"
                self.last_blink_event_ts = now
            else:
                blink_state = "closed" if is_blink else "open"
            self.prev_blink = is_blink

            gaze_norm = normalized_gaze_from_eye_ratios(left_rx, right_rx, left_ry, right_ry)
            gaze_norm = apply_gain(gaze_norm, self.cfg.gaze_gain_x, self.cfg.gaze_gain_y)
            gaze_norm = apply_calibration(gaze_norm, self.runtime.calibration_map)
            gaze_norm = smooth_point(self.prev_gaze_norm, gaze_norm, self.cfg.smoothing_alpha)
            self.prev_gaze_norm = gaze_norm

            gaze_point = gaze_point_from_normalized(gaze_norm, w, h)
            gaze_point_f = smooth_point(self.prev_gaze_px, gaze_point, self.cfg.smoothing_alpha)
            self.prev_gaze_px = gaze_point_f
            gaze_point_i = as_int_point(*gaze_point_f) if gaze_point_f is not None else None

            det.left_center = as_int_point(*left_center) if left_center else None
            det.right_center = as_int_point(*right_center) if right_center else None
            det.gaze_point = gaze_point_i
            det.left_ratio_x = left_rx
            det.right_ratio_x = right_rx
            det.left_ratio_y = left_ry
            det.right_ratio_y = right_ry
            det.blink_ratio = blink_ratio
            det.blink_state = blink_state
            det.success = True
            det.status = "tracking"

            update_heatmap(self.runtime, gaze_point_i)

            if self.cfg.show_eye_ring:
                draw_eye_ring(out, face_landmarks, LEFT_EYE_RING, w, h, (255, 140, 0))
                draw_eye_ring(out, face_landmarks, RIGHT_EYE_RING, w, h, (255, 140, 0))

            if self.cfg.show_iris:
                draw_point(out, left_center, (0, 255, 0), radius=4)
                draw_point(out, right_center, (0, 255, 0), radius=4)
                draw_box(out, left_box, (0, 200, 255))
                draw_box(out, right_box, (0, 200, 255))

            if self.cfg.draw_crosshair:
                draw_crosshair(out, gaze_point_i, color=(0, 255, 255), size=12, thickness=1)

            if self.cfg.show_info:
                draw_info_panel(out, det)

            self._push_metrics(det)
            with self.runtime.lock:
                self.runtime.latest_frame_bgr = out.copy()

            return av.VideoFrame.from_ndarray(out, format="bgr24")

        except Exception as exc:
            det.status = f"error: {type(exc).__name__}"
            if self.cfg.show_info:
                draw_info_panel(out, det)
            cv2.putText(
                out,
                f"Erro: {type(exc).__name__}",
                (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            self._push_metrics(det)
            with self.runtime.lock:
                self.runtime.latest_frame_bgr = out.copy()
            return av.VideoFrame.from_ndarray(out, format="bgr24")

    def _push_metrics(self, det: IrisDetection):
        payload = {
            "timestamp": det.timestamp,
            "elapsed_sec": det.timestamp - self.runtime.start_time,
            "frame_w": det.frame_w,
            "frame_h": det.frame_h,
            "gaze_x": det.gaze_point[0] if det.gaze_point else None,
            "gaze_y": det.gaze_point[1] if det.gaze_point else None,
            "left_ratio_x": det.left_ratio_x,
            "right_ratio_x": det.right_ratio_x,
            "left_ratio_y": det.left_ratio_y,
            "right_ratio_y": det.right_ratio_y,
            "blink_ratio": det.blink_ratio,
            "blink_state": det.blink_state,
            "fps": det.fps,
            "status": det.status,
        }
        try:
            self.runtime.metrics_queue.put_nowait(payload)
        except queue.Full:
            pass
        with self.runtime.lock:
            self.runtime.csv_rows.append(payload)


# =============================================================================
# Sidebar UI
# =============================================================================

def render_sidebar():
    st.sidebar.title("Configurações")

    cfg: TrackerConfig = st.session_state.tracker_config

    cfg.max_faces = int(st.sidebar.selectbox("Máx. rostos", [1, 2], index=0))
    cfg.refine_landmarks = st.sidebar.checkbox("Refinar landmarks (íris)", value=cfg.refine_landmarks)
    cfg.min_detection_confidence = float(st.sidebar.slider("Confiança detecção", 0.1, 1.0, cfg.min_detection_confidence, 0.05))
    cfg.min_tracking_confidence = float(st.sidebar.slider("Confiança tracking", 0.1, 1.0, cfg.min_tracking_confidence, 0.05))
    cfg.blink_threshold = float(st.sidebar.slider("Limiar de piscada", 0.08, 0.40, cfg.blink_threshold, 0.01))
    cfg.blink_cooldown_sec = float(st.sidebar.slider("Cooldown piscada (s)", 0.05, 1.00, cfg.blink_cooldown_sec, 0.01))
    cfg.smoothing_alpha = float(st.sidebar.slider("Suavização", 0.01, 1.00, cfg.smoothing_alpha, 0.01))
    cfg.gaze_gain_x = float(st.sidebar.slider("Ganho X", 0.5, 3.0, cfg.gaze_gain_x, 0.1))
    cfg.gaze_gain_y = float(st.sidebar.slider("Ganho Y", 0.5, 3.0, cfg.gaze_gain_y, 0.1))
    cfg.heatmap_decay = float(st.sidebar.slider("Decaimento heatmap", 0.90, 1.00, cfg.heatmap_decay, 0.001))

    st.sidebar.markdown("---")
    cfg.show_mesh = st.sidebar.checkbox("Mostrar malha facial", value=cfg.show_mesh)
    cfg.show_eye_ring = st.sidebar.checkbox("Mostrar contorno dos olhos", value=cfg.show_eye_ring)
    cfg.show_iris = st.sidebar.checkbox("Mostrar centro da íris", value=cfg.show_iris)
    cfg.show_info = st.sidebar.checkbox("Mostrar painel info", value=cfg.show_info)
    cfg.draw_crosshair = st.sidebar.checkbox("Mostrar mira do olhar", value=cfg.draw_crosshair)

    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar heatmap", use_container_width=True):
        runtime: SharedRuntime = st.session_state.runtime
        with runtime.lock:
            if runtime.heatmap is not None:
                runtime.heatmap[:] = 0
        st.sidebar.success("Mapa de calor limpo.")

    if st.sidebar.button("Limpar CSV/métricas", use_container_width=True):
        runtime: SharedRuntime = st.session_state.runtime
        with runtime.lock:
            runtime.csv_rows.clear()
        st.sidebar.success("Métricas limpas.")

    if st.sidebar.button("Resetar calibração", use_container_width=True):
        runtime: SharedRuntime = st.session_state.runtime
        runtime.calibration_map.clear()
        runtime.calibrated = False
        st.sidebar.success("Calibração resetada.")


# =============================================================================
# Calibration UI
# =============================================================================

def render_calibration_panel():
    st.subheader("Calibração")
    runtime: SharedRuntime = st.session_state.runtime
    targets: List[CalibPoint] = st.session_state.calibration_targets
    col1, col2 = st.columns([1.4, 1.2])

    with col1:
        st.write("1. Olhe para o alvo indicado.")
        st.write("2. Espere o olho estabilizar.")
        st.write("3. Clique em **Salvar leitura atual**.")
        target_names = [t.name for t in targets]
        selected = st.selectbox("Alvo atual", target_names, index=target_names.index(st.session_state.selected_calibration_target))
        st.session_state.selected_calibration_target = selected

        if st.button("Salvar leitura atual", use_container_width=True):
            metrics = st.session_state.latest_metrics or {}
            lx = metrics.get("left_ratio_x")
            rx = metrics.get("right_ratio_x")
            ly = metrics.get("left_ratio_y")
            ry = metrics.get("right_ratio_y")
            norm = normalized_gaze_from_eye_ratios(lx, rx, ly, ry)
            if norm is None:
                st.error("Sem leitura válida para calibrar.")
            else:
                runtime.calibration_map[selected] = norm
                runtime.calibrated = "center" in runtime.calibration_map
                st.success(f"Leitura salva para {selected}: ({norm[0]:.3f}, {norm[1]:.3f})")

        st.json(runtime.calibration_map)

    with col2:
        # a fixed reference canvas for where the user should look
        canvas_h = 280
        canvas_w = 420
        board = np.ones((canvas_h, canvas_w, 3), dtype=np.uint8) * 245
        for t in targets:
            px = int(round(t.x * (canvas_w - 1)))
            py = int(round(t.y * (canvas_h - 1)))
            is_sel = (t.name == st.session_state.selected_calibration_target)
            color = (0, 0, 255) if is_sel else (60, 60, 60)
            cv2.circle(board, (px, py), 10 if is_sel else 7, color, -1, lineType=cv2.LINE_AA)
            cv2.putText(board, t.name, (px + 12, py + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)

        st.image(cv2.cvtColor(board, cv2.COLOR_BGR2RGB), use_container_width=True)


# =============================================================================
# Metrics consumers
# =============================================================================

def drain_metrics_queue():
    runtime: SharedRuntime = st.session_state.runtime
    latest = None
    while True:
        try:
            latest = runtime.metrics_queue.get_nowait()
        except queue.Empty:
            break
    if latest is not None:
        st.session_state.latest_metrics = latest


def render_live_metrics():
    drain_metrics_queue()
    metrics = st.session_state.latest_metrics or {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", metrics.get("status", "N/A"))
    c2.metric("Blink", metrics.get("blink_state", "N/A"))
    fps = metrics.get("fps")
    c3.metric("FPS", f"{fps:.1f}" if isinstance(fps, (int, float)) else "N/A")
    br = metrics.get("blink_ratio")
    c4.metric("Blink ratio", f"{br:.3f}" if isinstance(br, (int, float)) else "N/A")

    c5, c6, c7, c8 = st.columns(4)
    gx = metrics.get("gaze_x")
    gy = metrics.get("gaze_y")
    c5.metric("Gaze X", f"{gx}" if gx is not None else "N/A")
    c6.metric("Gaze Y", f"{gy}" if gy is not None else "N/A")

    lrx = metrics.get("left_ratio_x")
    rrx = metrics.get("right_ratio_x")
    c7.metric("L RX", f"{lrx:.3f}" if isinstance(lrx, (int, float)) else "N/A")
    c8.metric("R RX", f"{rrx:.3f}" if isinstance(rrx, (int, float)) else "N/A")


def render_tables_and_exports():
    runtime: SharedRuntime = st.session_state.runtime
    rows = dataframe_from_rows(runtime.csv_rows)

    st.subheader("Métricas e Exportação")
    st.dataframe(rows.tail(200), use_container_width=True, height=260)

    col1, col2, col3 = st.columns(3)

    csv_bytes = rows.to_csv(index=False).encode("utf-8")
    col1.download_button(
        "Baixar CSV",
        data=csv_bytes,
        file_name="iris_tracking_metrics.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with runtime.lock:
        latest_frame = runtime.latest_frame_bgr.copy() if runtime.latest_frame_bgr is not None else None
        heatmap = runtime.heatmap.copy() if runtime.heatmap is not None else None

    if latest_frame is not None and heatmap is not None:
        overlay = overlay_heatmap_on_frame(latest_frame, heatmap, alpha=0.4)
        png_bytes = image_to_png_bytes(overlay)
        col2.download_button(
            "Baixar PNG do heatmap",
            data=png_bytes,
            file_name="iris_heatmap_overlay.png",
            mime="image/png",
            use_container_width=True,
        )
    else:
        col2.write("PNG indisponível.")

    pdf_bytes = build_pdf_report(runtime)
    col3.download_button(
        "Baixar PDF",
        data=pdf_bytes,
        file_name="relatorio_iris_streamlit.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


# =============================================================================
# Visualization panels
# =============================================================================

def render_heatmap_view():
    runtime: SharedRuntime = st.session_state.runtime
    st.subheader("Mapa de Calor")
    with runtime.lock:
        latest_frame = runtime.latest_frame_bgr.copy() if runtime.latest_frame_bgr is not None else None
        heatmap = runtime.heatmap.copy() if runtime.heatmap is not None else None

    if latest_frame is None or heatmap is None:
        st.info("O mapa de calor aparecerá quando a webcam começar a enviar frames.")
        return

    overlay = overlay_heatmap_on_frame(latest_frame, heatmap, alpha=0.4)
    st.image(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB), use_container_width=True)


def render_debug_eye_view():
    runtime: SharedRuntime = st.session_state.runtime
    metrics = st.session_state.latest_metrics or {}

    st.subheader("Debug")
    col1, col2 = st.columns(2)

    with col1:
        st.json(metrics)

    with col2:
        with runtime.lock:
            latest_frame = runtime.latest_frame_bgr.copy() if runtime.latest_frame_bgr is not None else None
        if latest_frame is not None:
            h, w = latest_frame.shape[:2]
            gx = metrics.get("gaze_x")
            gy = metrics.get("gaze_y")
            if gx is not None and gy is not None:
                crop_size = 140
                x0 = max(0, gx - crop_size)
                y0 = max(0, gy - crop_size)
                x1 = min(w, gx + crop_size)
                y1 = min(h, gy + crop_size)
                crop = latest_frame[y0:y1, x0:x1]
                if crop.size > 0:
                    st.image(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), caption="Recorte em torno do ponto de gaze", use_container_width=True)
            else:
                st.info("Sem ponto de gaze para o recorte.")


# =============================================================================
# Main app layout
# =============================================================================

def render_header():
    st.title("Rastreamento de Íris com Webcam")
    st.write(
        "App completo para Streamlit com webcam, MediaPipe Face Mesh, "
        "estimativa de ponto de olhar, calibração simples, mapa de calor e exportação."
    )
    st.caption(
        "Feito para rodar em ambiente headless com streamlit-webrtc e opencv-python-headless."
    )


def render_webrtc():
    st.subheader("Webcam")
    st.warning(
        "Permita acesso à webcam no navegador. "
        "Deixe este componente fixo na página e evite tradução automática/extensões ao testar."
    )

    webrtc_streamer(
        key="iris-tracker-main",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=DEFAULT_RTC_CONFIGURATION,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
        video_processor_factory=StreamlitIrisProcessor,
    )


def render_install_block():
    st.subheader("Arquivos do deploy")
    st.code(
        """requirements.txt
streamlit>=1.41.0
streamlit-webrtc>=0.62.4
opencv-python-headless>=4.10.0.84
mediapipe==0.10.21
numpy>=1.26.4
pandas>=2.2.2
av>=12.3.0
Pillow>=10.4.0
reportlab>=4.2.2

packages.txt
libgl1

runtime.txt
python-3.11.9
""",
        language="text",
    )


def main():
    render_sidebar()
    render_header()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Tracking",
        "Calibração",
        "Heatmap",
        "Debug",
        "Deploy",
    ])

    with tab1:
        render_webrtc()
        render_live_metrics()
        render_tables_and_exports()

    with tab2:
        render_calibration_panel()

    with tab3:
        render_heatmap_view()

    with tab4:
        render_debug_eye_view()

    with tab5:
        render_install_block()


if __name__ == "__main__":
    main()

