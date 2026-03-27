
import io
import os
import math
import time
import json
import uuid
import queue
import base64
import threading
from dataclasses import dataclass, field, asdict
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import av
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer

try:
    import mediapipe as mp
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "MediaPipe não pôde ser importado. Verifique requirements.txt e a versão do Python."
    ) from exc


# ============================================================================
# CONSTANTES GERAIS
# ============================================================================

APP_TITLE = "Simulacro Iris Tracker Streamlit"
APP_ICON = "👁️"
APP_LAYOUT = "wide"
DEFAULT_FRAME_WIDTH = 640
DEFAULT_FRAME_HEIGHT = 480
DEFAULT_FPS_ESTIMATE = 30.0
DEFAULT_HEATMAP_W = 64
DEFAULT_HEATMAP_H = 48
MAX_HISTORY = 1800
MAX_POINTS_FOR_CSV = 15000
DEFAULT_SESSION_NAME = "sessao_iris"

# MediaPipe helpers
MP_FACE_MESH = mp.solutions.face_mesh

# Landmarks principais.
# Nota: índices padronizados do MediaPipe Face Mesh com refine_landmarks=True.
# LEFT e RIGHT se referem ao modelo; em selfie, a imagem pode parecer espelhada.
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_EYE_OUTER = 33
LEFT_EYE_INNER = 133
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374
LEFT_EYE_CONTOUR = [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7]
RIGHT_EYE_CONTOUR = [362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380, 381, 382]
LEFT_BLINK_EAR = [33, 160, 158, 133, 153, 144]
RIGHT_BLINK_EAR = [362, 385, 387, 263, 373, 380]
NOSE_TIP = 1
FACE_LEFT = 234
FACE_RIGHT = 454
FOREHEAD = 10
CHIN = 152

CALIBRATION_TARGETS = ["center", "left", "right", "up", "down"]
CALIBRATION_TARGET_LABELS = {
    "center": "Centro",
    "left": "Esquerda",
    "right": "Direita",
    "up": "Cima",
    "down": "Baixo",
}

# Cores BGR para OpenCV
COLOR_BG = (28, 28, 28)
COLOR_PANEL = (40, 40, 40)
COLOR_TEXT = (245, 245, 245)
COLOR_GREEN = (80, 220, 120)
COLOR_RED = (70, 70, 240)
COLOR_YELLOW = (80, 220, 255)
COLOR_CYAN = (240, 220, 70)
COLOR_ORANGE = (0, 160, 255)
COLOR_BLUE = (255, 120, 50)
COLOR_MAGENTA = (255, 80, 220)

RTC_CONFIGURATION = {
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
    ]
}


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class TrackerConfig:
    """Configurações principais do rastreador."""

    frame_width: int = DEFAULT_FRAME_WIDTH
    frame_height: int = DEFAULT_FRAME_HEIGHT
    smoothing: float = 0.72
    blink_smoothing: float = 0.50
    heatmap_width: int = DEFAULT_HEATMAP_W
    heatmap_height: int = DEFAULT_HEATMAP_H
    blink_threshold: float = 0.205
    blink_double_window_ms: int = 650
    blink_cooldown_ms: int = 220
    gaze_deadzone: float = 0.02
    show_mesh: bool = False
    show_iris_points: bool = True
    show_eye_boxes: bool = True
    show_vectors: bool = True
    show_debug_text: bool = True
    show_heatmap_preview: bool = True
    draw_mirror: bool = True
    enhance_contrast: bool = True
    use_hist_eq: bool = False
    gamma: float = 1.0
    clahe_clip_limit: float = 2.0
    clahe_grid_size: int = 8
    calibration_samples_per_target: int = 24
    iris_ellipse_scale: float = 1.18
    score_min_eye_width_px: float = 12.0
    score_min_face_width_px: float = 80.0
    score_min_confidence: float = 0.25
    stable_center_weight: float = 0.65
    stable_ratio_weight: float = 0.35
    record_raw_points: bool = True
    save_frame_snapshots: bool = False
    max_export_points: int = MAX_POINTS_FOR_CSV


@dataclass
class IrisMeasurement:
    """Medições instantâneas do frame."""

    timestamp: float = 0.0
    fps_estimate: float = 0.0
    face_found: bool = False
    confidence: float = 0.0
    left_iris_center: Tuple[float, float] = (0.0, 0.0)
    right_iris_center: Tuple[float, float] = (0.0, 0.0)
    left_eye_center: Tuple[float, float] = (0.0, 0.0)
    right_eye_center: Tuple[float, float] = (0.0, 0.0)
    left_ratio_x: float = 0.0
    left_ratio_y: float = 0.0
    right_ratio_x: float = 0.0
    right_ratio_y: float = 0.0
    raw_gaze_x: float = 0.0
    raw_gaze_y: float = 0.0
    smooth_gaze_x: float = 0.0
    smooth_gaze_y: float = 0.0
    screen_x: float = 0.5
    screen_y: float = 0.5
    ear_left: float = 0.0
    ear_right: float = 0.0
    blink_strength: float = 0.0
    blink_count: int = 0
    blink_state: str = "open"
    command: str = "none"
    gaze_vector_3d: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    face_box: Tuple[int, int, int, int] = (0, 0, 0, 0)
    eye_width_left_px: float = 0.0
    eye_width_right_px: float = 0.0
    iris_radius_left_px: float = 0.0
    iris_radius_right_px: float = 0.0
    notes: str = ""


@dataclass
class CalibrationProfile:
    """Perfil de calibração baseado em amostras brutas."""

    target_samples: Dict[str, List[Tuple[float, float]]] = field(default_factory=lambda: {k: [] for k in CALIBRATION_TARGETS})
    raw_center: Tuple[float, float] = (0.0, 0.0)
    raw_left: Tuple[float, float] = (-0.3, 0.0)
    raw_right: Tuple[float, float] = (0.3, 0.0)
    raw_up: Tuple[float, float] = (0.0, -0.2)
    raw_down: Tuple[float, float] = (0.0, 0.2)
    completed: bool = False
    updated_at: float = 0.0


@dataclass
class SessionStats:
    """Estatísticas acumuladas da sessão."""

    start_time: float = field(default_factory=time.time)
    total_frames: int = 0
    valid_frames: int = 0
    total_blinks: int = 0
    single_blink_commands: int = 0
    double_blink_commands: int = 0
    avg_confidence: float = 0.0
    avg_fps: float = 0.0
    avg_screen_x: float = 0.5
    avg_screen_y: float = 0.5
    min_screen_x: float = 1.0
    min_screen_y: float = 1.0
    max_screen_x: float = 0.0
    max_screen_y: float = 0.0
    face_detect_ratio: float = 0.0
    last_update_time: float = field(default_factory=time.time)


# ============================================================================
# FUNÇÕES AUXILIARES DE BASE
# ============================================================================

def now_ts() -> float:
    return time.time()


def clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    if abs(b) < 1e-9:
        return default
    return a / b


def as_int_pt(pt: Tuple[float, float]) -> Tuple[int, int]:
    return int(round(pt[0])), int(round(pt[1]))


def ema(prev: Optional[float], new: float, alpha: float) -> float:
    if prev is None:
        return new
    return alpha * prev + (1.0 - alpha) * new


def ema_point(prev: Optional[Tuple[float, float]], new: Tuple[float, float], alpha: float) -> Tuple[float, float]:
    if prev is None:
        return new
    return (ema(prev[0], new[0], alpha), ema(prev[1], new[1], alpha))


def norm2(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def normalize_vec3(vec: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vec)
    if n < 1e-9:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)
    return (vec / n).astype(np.float32)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return float(math.hypot(p1[0] - p2[0], p1[1] - p2[1]))


def midpoint(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)


def to_bgr(rgb_img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)


def to_rgb(bgr_img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)


def ensure_uint8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    return np.clip(img, 0, 255).astype(np.uint8)


def crop_to_aspect_ratio(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Adaptação da ideia do código-base, mas sem janelas nativas."""
    if image is None or image.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)

    current_height, current_width = image.shape[:2]
    desired_ratio = width / height
    current_ratio = current_width / max(current_height, 1)

    if current_ratio > desired_ratio:
        new_width = int(desired_ratio * current_height)
        offset = max((current_width - new_width) // 2, 0)
        cropped = image[:, offset: offset + new_width]
    else:
        new_height = int(current_width / desired_ratio)
        offset = max((current_height - new_height) // 2, 0)
        cropped = image[offset: offset + new_height, :]

    resized = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)
    return resized


def apply_gamma(image_bgr: np.ndarray, gamma: float) -> np.ndarray:
    if abs(gamma - 1.0) < 1e-6:
        return image_bgr
    inv_gamma = 1.0 / max(gamma, 1e-6)
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(image_bgr, table)


def apply_clahe_to_luma(image_bgr: np.ndarray, clip_limit: float, grid_size: int) -> np.ndarray:
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=max(clip_limit, 0.5), tileGridSize=(max(grid_size, 2), max(grid_size, 2)))
    l2 = clahe.apply(l)
    merged = cv2.merge((l2, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def histogram_equalize_gray(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    return cv2.cvtColor(gray_eq, cv2.COLOR_GRAY2BGR)


def preprocess_frame_for_tracking(image_bgr: np.ndarray, config: TrackerConfig) -> np.ndarray:
    out = image_bgr.copy()
    if config.enhance_contrast:
        out = apply_clahe_to_luma(out, config.clahe_clip_limit, config.clahe_grid_size)
    if config.use_hist_eq:
        out = histogram_equalize_gray(out)
    out = apply_gamma(out, config.gamma)
    return out


def put_text_box(
    image: np.ndarray,
    text: str,
    origin: Tuple[int, int],
    color: Tuple[int, int, int] = COLOR_TEXT,
    bg_color: Tuple[int, int, int] = (10, 10, 10),
    scale: float = 0.52,
    thickness: int = 1,
) -> None:
    x, y = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    ((w, h), baseline) = cv2.getTextSize(text, font, scale, thickness)
    pad = 4
    x1, y1 = x - pad, y - h - pad
    x2, y2 = x + w + pad, y + baseline + pad
    cv2.rectangle(image, (x1, y1), (x2, y2), bg_color, -1)
    cv2.putText(image, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def draw_crosshair(image: np.ndarray, center: Tuple[int, int], size: int = 12, color: Tuple[int, int, int] = COLOR_ORANGE) -> None:
    cx, cy = center
    cv2.line(image, (cx - size, cy), (cx + size, cy), color, 1, cv2.LINE_AA)
    cv2.line(image, (cx, cy - size), (cx, cy + size), color, 1, cv2.LINE_AA)


def draw_transparent_panel(image: np.ndarray, rect: Tuple[int, int, int, int], color: Tuple[int, int, int], alpha: float = 0.45) -> None:
    x, y, w, h = rect
    x = max(x, 0)
    y = max(y, 0)
    x2 = min(x + w, image.shape[1])
    y2 = min(y + h, image.shape[0])
    if x2 <= x or y2 <= y:
        return
    roi = image[y:y2, x:x2]
    overlay = np.full_like(roi, color)
    blended = cv2.addWeighted(roi, 1.0 - alpha, overlay, alpha, 0)
    image[y:y2, x:x2] = blended


def bbox_from_points(points: np.ndarray, margin: int = 6) -> Tuple[int, int, int, int]:
    if points.size == 0:
        return 0, 0, 0, 0
    x_min = int(np.min(points[:, 0])) - margin
    y_min = int(np.min(points[:, 1])) - margin
    x_max = int(np.max(points[:, 0])) + margin
    y_max = int(np.max(points[:, 1])) + margin
    return x_min, y_min, max(x_max - x_min, 1), max(y_max - y_min, 1)


def limit_bbox(bbox: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
    x, y, w, h = bbox
    x = max(0, x)
    y = max(0, y)
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def mp_landmarks_to_np(landmarks: Any, width: int, height: int) -> np.ndarray:
    pts = np.zeros((len(landmarks.landmark), 2), dtype=np.float32)
    for i, lm in enumerate(landmarks.landmark):
        pts[i, 0] = lm.x * width
        pts[i, 1] = lm.y * height
    return pts


def pick_points(all_points: np.ndarray, indices: List[int]) -> np.ndarray:
    return np.array([all_points[idx] for idx in indices], dtype=np.float32)


def contour_center(points: np.ndarray) -> Tuple[float, float]:
    if points.size == 0:
        return 0.0, 0.0
    cx = float(np.mean(points[:, 0]))
    cy = float(np.mean(points[:, 1]))
    return cx, cy


def fit_ellipse_or_mean(points: np.ndarray) -> Tuple[Tuple[float, float], float, Optional[Tuple[Any, Any, Any]]]:
    """Ajusta elipse quando possível; se não, usa centro médio."""
    if points.shape[0] >= 5:
        contour = points.astype(np.int32).reshape((-1, 1, 2))
        try:
            ellipse = cv2.fitEllipse(contour)
            (cx, cy), (ma, mi), _ = ellipse
            radius = float(max(ma, mi) * 0.25)
            return (float(cx), float(cy)), radius, ellipse
        except Exception:
            pass
    center = contour_center(points)
    radius = float(np.mean(np.linalg.norm(points - np.array(center, dtype=np.float32), axis=1))) if points.size else 0.0
    return center, radius, None


def compute_ear(points_all: np.ndarray, indices: List[int]) -> float:
    """Eye Aspect Ratio clássico para detecção de piscada."""
    p1, p2, p3, p4, p5, p6 = [points_all[idx] for idx in indices]
    vertical_1 = np.linalg.norm(p2 - p6)
    vertical_2 = np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    return float((vertical_1 + vertical_2) / max(2.0 * horizontal, 1e-6))


def compute_face_box(points_all: np.ndarray, width: int, height: int) -> Tuple[int, int, int, int]:
    selected = np.array(
        [
            points_all[FACE_LEFT],
            points_all[FACE_RIGHT],
            points_all[FOREHEAD],
            points_all[CHIN],
        ],
        dtype=np.float32,
    )
    bbox = bbox_from_points(selected, margin=18)
    return limit_bbox(bbox, width, height)


def compute_eye_center_and_size(points_all: np.ndarray, contour_idx: List[int], outer_idx: int, inner_idx: int) -> Tuple[Tuple[float, float], float]:
    contour = pick_points(points_all, contour_idx)
    center = contour_center(contour)
    eye_width = distance(tuple(points_all[outer_idx]), tuple(points_all[inner_idx]))
    return center, eye_width


def compute_relative_iris_ratio(
    iris_center: Tuple[float, float],
    eye_outer: Tuple[float, float],
    eye_inner: Tuple[float, float],
    eye_top: Tuple[float, float],
    eye_bottom: Tuple[float, float],
) -> Tuple[float, float]:
    """
    Gera posição relativa da íris dentro do olho.
    0.0 ~ borda esquerda/superior e 1.0 ~ borda direita/inferior.
    """
    eye_width = max(distance(eye_outer, eye_inner), 1e-6)
    eye_height = max(distance(eye_top, eye_bottom), 1e-6)

    left_x = min(eye_outer[0], eye_inner[0])
    right_x = max(eye_outer[0], eye_inner[0])
    top_y = min(eye_top[1], eye_bottom[1])
    bottom_y = max(eye_top[1], eye_bottom[1])

    ratio_x = clamp((iris_center[0] - left_x) / max(right_x - left_x, 1e-6), 0.0, 1.0)
    ratio_y = clamp((iris_center[1] - top_y) / max(bottom_y - top_y, 1e-6), 0.0, 1.0)

    if not np.isfinite(ratio_x):
        ratio_x = 0.5
    if not np.isfinite(ratio_y):
        ratio_y = 0.5

    return ratio_x, ratio_y


def estimate_confidence(
    face_box: Tuple[int, int, int, int],
    eye_width_left_px: float,
    eye_width_right_px: float,
    iris_radius_left_px: float,
    iris_radius_right_px: float,
    config: TrackerConfig,
) -> float:
    x, y, w, h = face_box
    face_score = clamp(w / max(config.score_min_face_width_px, 1e-6), 0.0, 1.0)
    eye_score_l = clamp(eye_width_left_px / max(config.score_min_eye_width_px, 1e-6), 0.0, 1.0)
    eye_score_r = clamp(eye_width_right_px / max(config.score_min_eye_width_px, 1e-6), 0.0, 1.0)
    iris_score_l = clamp(iris_radius_left_px / 2.0, 0.0, 1.0)
    iris_score_r = clamp(iris_radius_right_px / 2.0, 0.0, 1.0)
    return float((0.30 * face_score) + (0.25 * eye_score_l) + (0.25 * eye_score_r) + (0.10 * iris_score_l) + (0.10 * iris_score_r))


def map_raw_to_screen(
    raw_x: float,
    raw_y: float,
    calib: CalibrationProfile,
) -> Tuple[float, float]:
    """
    Mapeia coordenadas brutas para 0..1 usando amostras de calibração.
    Estratégia simples e robusta para Streamlit.
    """
    cx, cy = calib.raw_center
    lx, _ = calib.raw_left
    rx, _ = calib.raw_right
    _, uy = calib.raw_up
    _, dy = calib.raw_down

    left_span = max(cx - lx, 1e-6)
    right_span = max(rx - cx, 1e-6)
    up_span = max(cy - uy, 1e-6)
    down_span = max(dy - cy, 1e-6)

    if raw_x <= cx:
        nx = 0.5 - 0.5 * ((cx - raw_x) / left_span)
    else:
        nx = 0.5 + 0.5 * ((raw_x - cx) / right_span)

    if raw_y <= cy:
        ny = 0.5 - 0.5 * ((cy - raw_y) / up_span)
    else:
        ny = 0.5 + 0.5 * ((raw_y - cy) / down_span)

    return clamp(nx, 0.0, 1.0), clamp(ny, 0.0, 1.0)


def default_heatmap_rgb(heatmap_small: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
    heat = heatmap_small.astype(np.float32)
    if float(heat.max()) > 0:
        heat = heat / float(heat.max())
    heat = np.uint8(np.clip(heat * 255.0, 0, 255))
    heat_colored = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
    heat_up = cv2.resize(heat_colored, target_size, interpolation=cv2.INTER_CUBIC)
    return heat_up


def blend_heatmap_on_frame(frame_bgr: np.ndarray, heatmap_rgb: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    overlay = heatmap_rgb.copy()
    if overlay.shape[:2] != frame_bgr.shape[:2]:
        overlay = cv2.resize(overlay, (frame_bgr.shape[1], frame_bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
    return cv2.addWeighted(frame_bgr, 1.0 - alpha, overlay, alpha, 0)


def encode_png_bytes(image_rgb: np.ndarray) -> bytes:
    image_bgr = to_bgr(image_rgb)
    ok, buf = cv2.imencode(".png", image_bgr)
    if not ok:
        return b""
    return bytes(buf.tobytes())


def image_to_base64(image_rgb: np.ndarray) -> str:
    return base64.b64encode(encode_png_bytes(image_rgb)).decode("utf-8")


def safe_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def rolling_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return float(np.mean(values))


def rolling_median_points(values: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    arr = np.array(values, dtype=np.float32)
    return float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))


# ============================================================================
# ESTRUTURAS DE ACÚMULO E ESTADO
# ============================================================================

class BlinkInterpreter:
    """
    Converte EAR em eventos de piscada simples ou dupla.
    """

    def __init__(self, threshold: float, double_window_ms: int, cooldown_ms: int):
        self.threshold = threshold
        self.double_window_ms = double_window_ms
        self.cooldown_ms = cooldown_ms
        self.prev_smoothed: Optional[float] = None
        self.eye_closed = False
        self.last_blink_ts = 0.0
        self.last_command_ts = 0.0
        self.pending_single_ts = 0.0
        self.blink_count = 0

    def reset(self) -> None:
        self.prev_smoothed = None
        self.eye_closed = False
        self.last_blink_ts = 0.0
        self.last_command_ts = 0.0
        self.pending_single_ts = 0.0
        self.blink_count = 0

    def update(self, ear_value: float, alpha: float = 0.50) -> Tuple[float, str, int, str]:
        t = now_ts() * 1000.0
        smoothed = ema(self.prev_smoothed, ear_value, alpha)
        self.prev_smoothed = smoothed
        command = "none"
        blink_state = "open"

        is_closed = smoothed < self.threshold

        if is_closed and not self.eye_closed:
            self.eye_closed = True
            blink_state = "closed"
        elif (not is_closed) and self.eye_closed:
            self.eye_closed = False
            blink_state = "opened"
            self.blink_count += 1
            self.last_blink_ts = t

            # Janela de cooldown para reduzir falso positivo.
            if (t - self.last_command_ts) >= self.cooldown_ms:
                if self.pending_single_ts > 0 and (t - self.pending_single_ts) <= self.double_window_ms:
                    command = "double_blink"
                    self.pending_single_ts = 0.0
                    self.last_command_ts = t
                else:
                    self.pending_single_ts = t
        else:
            blink_state = "closed" if self.eye_closed else "open"

        # Se passou a janela e ainda há piscada simples pendente, dispara comando.
        if self.pending_single_ts > 0 and command == "none":
            if (t - self.pending_single_ts) > self.double_window_ms:
                if (t - self.last_command_ts) >= self.cooldown_ms:
                    command = "single_blink"
                    self.last_command_ts = t
                self.pending_single_ts = 0.0

        blink_strength = clamp((self.threshold - smoothed) / max(self.threshold, 1e-6), 0.0, 1.0)
        return smoothed, command, self.blink_count, blink_state


class HeatmapAccumulator:
    """Acumula pontos normalizados 0..1 em uma grade."""

    def __init__(self, width: int, height: int):
        self.width = int(width)
        self.height = int(height)
        self.map = np.zeros((self.height, self.width), dtype=np.float32)
        self.total_points = 0

    def reset(self) -> None:
        self.map.fill(0.0)
        self.total_points = 0

    def add_point(self, x_norm: float, y_norm: float, weight: float = 1.0) -> None:
        x_norm = clamp(x_norm, 0.0, 1.0)
        y_norm = clamp(y_norm, 0.0, 1.0)
        xi = min(int(x_norm * (self.width - 1)), self.width - 1)
        yi = min(int(y_norm * (self.height - 1)), self.height - 1)
        self.map[yi, xi] += float(weight)
        self.total_points += 1

    def get_preview_rgb(self, target_size: Tuple[int, int]) -> np.ndarray:
        return default_heatmap_rgb(self.map, target_size)


class RuntimeState:
    """
    Estado compartilhado entre UI Streamlit e processador de vídeo.
    """

    def __init__(self, config: Optional[TrackerConfig] = None):
        self.lock = threading.RLock()
        self.config = config or TrackerConfig()
        self.stats = SessionStats()
        self.calibration = CalibrationProfile()
        self.heatmap = HeatmapAccumulator(self.config.heatmap_width, self.config.heatmap_height)
        self.measurements: Deque[IrisMeasurement] = deque(maxlen=MAX_HISTORY)
        self.last_measurement = IrisMeasurement()
        self.last_frame_rgb = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)
        self.last_heatmap_rgb = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)
        self.last_debug: Dict[str, Any] = {}
        self.current_calibration_target: Optional[str] = None
        self.last_command: str = "none"
        self.command_log: Deque[Tuple[float, str]] = deque(maxlen=200)
        self.recording_enabled = True
        self.snapshot_counter = 0
        self.session_name = DEFAULT_SESSION_NAME
        self.export_dir = "/mnt/data"
        self.pending_messages: "queue.Queue[str]" = queue.Queue()

    def update_config(self, new_config: TrackerConfig) -> None:
        with self.lock:
            self.config = new_config
            self.heatmap = HeatmapAccumulator(new_config.heatmap_width, new_config.heatmap_height)
            for m in self.measurements:
                self.heatmap.add_point(m.screen_x, m.screen_y, weight=max(m.confidence, 0.05))

    def clear_session(self) -> None:
        with self.lock:
            self.stats = SessionStats()
            self.calibration = CalibrationProfile()
            self.heatmap = HeatmapAccumulator(self.config.heatmap_width, self.config.heatmap_height)
            self.measurements.clear()
            self.command_log.clear()
            self.last_measurement = IrisMeasurement()
            self.last_command = "none"
            self.current_calibration_target = None
            self.last_debug = {}
            self.pending_messages.put("Sessão limpa com sucesso.")

    def add_measurement(self, measurement: IrisMeasurement, frame_rgb: np.ndarray, debug: Optional[Dict[str, Any]] = None) -> None:
        with self.lock:
            self.last_measurement = measurement
            self.last_frame_rgb = frame_rgb.copy()
            self.last_debug = debug or {}
            self.stats.total_frames += 1
            if measurement.face_found:
                self.stats.valid_frames += 1
                self.stats.avg_confidence = ema(self.stats.avg_confidence, measurement.confidence, 0.92)
                self.stats.avg_fps = ema(self.stats.avg_fps, measurement.fps_estimate, 0.90)
                self.stats.avg_screen_x = ema(self.stats.avg_screen_x, measurement.screen_x, 0.98)
                self.stats.avg_screen_y = ema(self.stats.avg_screen_y, measurement.screen_y, 0.98)
                self.stats.min_screen_x = min(self.stats.min_screen_x, measurement.screen_x)
                self.stats.min_screen_y = min(self.stats.min_screen_y, measurement.screen_y)
                self.stats.max_screen_x = max(self.stats.max_screen_x, measurement.screen_x)
                self.stats.max_screen_y = max(self.stats.max_screen_y, measurement.screen_y)
                self.heatmap.add_point(measurement.screen_x, measurement.screen_y, weight=max(measurement.confidence, 0.05))
                self.last_heatmap_rgb = self.heatmap.get_preview_rgb((frame_rgb.shape[1], frame_rgb.shape[0]))
            self.stats.face_detect_ratio = safe_div(self.stats.valid_frames, max(self.stats.total_frames, 1), 0.0)
            if measurement.command != "none":
                self.last_command = measurement.command
                self.command_log.append((measurement.timestamp, measurement.command))
                if measurement.command == "single_blink":
                    self.stats.single_blink_commands += 1
                elif measurement.command == "double_blink":
                    self.stats.double_blink_commands += 1
            self.stats.total_blinks = measurement.blink_count
            self.stats.last_update_time = now_ts()
            if self.recording_enabled:
                self.measurements.append(measurement)

    def request_calibration_capture(self, target: str) -> None:
        with self.lock:
            if target in CALIBRATION_TARGETS:
                self.current_calibration_target = target
                self.pending_messages.put(f"Captura de calibração iniciada para: {CALIBRATION_TARGET_LABELS[target]}")

    def add_calibration_sample(self, target: str, raw_point: Tuple[float, float]) -> int:
        with self.lock:
            if target not in CALIBRATION_TARGETS:
                return 0
            self.calibration.target_samples[target].append(raw_point)
            count = len(self.calibration.target_samples[target])
            needed = self.config.calibration_samples_per_target
            if count >= needed:
                self.finalize_calibration_target(target)
                self.current_calibration_target = None
            return count

    def finalize_calibration_target(self, target: str) -> None:
        samples = self.calibration.target_samples.get(target, [])
        if not samples:
            return
        med = rolling_median_points(samples)
        if target == "center":
            self.calibration.raw_center = med
        elif target == "left":
            self.calibration.raw_left = med
        elif target == "right":
            self.calibration.raw_right = med
        elif target == "up":
            self.calibration.raw_up = med
        elif target == "down":
            self.calibration.raw_down = med

        complete = all(
            len(self.calibration.target_samples[t]) >= self.config.calibration_samples_per_target
            for t in CALIBRATION_TARGETS
        )
        self.calibration.completed = complete
        self.calibration.updated_at = now_ts()
        self.pending_messages.put(f"Calibração registrada para: {CALIBRATION_TARGET_LABELS[target]}")
        if complete:
            self.pending_messages.put("Calibração completa.")

    def export_measurements_df(self) -> pd.DataFrame:
        with self.lock:
            rows = []
            items = list(self.measurements)[-self.config.max_export_points :]
            for m in items:
                rows.append(
                    {
                        "timestamp": m.timestamp,
                        "fps_estimate": m.fps_estimate,
                        "face_found": m.face_found,
                        "confidence": m.confidence,
                        "raw_gaze_x": m.raw_gaze_x,
                        "raw_gaze_y": m.raw_gaze_y,
                        "smooth_gaze_x": m.smooth_gaze_x,
                        "smooth_gaze_y": m.smooth_gaze_y,
                        "screen_x": m.screen_x,
                        "screen_y": m.screen_y,
                        "ear_left": m.ear_left,
                        "ear_right": m.ear_right,
                        "blink_strength": m.blink_strength,
                        "blink_count": m.blink_count,
                        "blink_state": m.blink_state,
                        "command": m.command,
                        "gaze_vec_x": m.gaze_vector_3d[0],
                        "gaze_vec_y": m.gaze_vector_3d[1],
                        "gaze_vec_z": m.gaze_vector_3d[2],
                        "eye_width_left_px": m.eye_width_left_px,
                        "eye_width_right_px": m.eye_width_right_px,
                        "iris_radius_left_px": m.iris_radius_left_px,
                        "iris_radius_right_px": m.iris_radius_right_px,
                        "notes": m.notes,
                    }
                )
            return pd.DataFrame(rows)


# ============================================================================
# RASTREADOR DA ÍRIS
# ============================================================================

class IrisTrackerEngine:
    """
    Engine principal do rastreio.

    A lógica aqui prioriza robustez em ambiente Streamlit:
    - não usa janelas nativas do OpenCV;
    - trabalha em BGR/RGB puro dentro do frame;
    - usa MediaPipe refine_landmarks para íris;
    - gera uma coordenada normalizada suave para o olhar.
    """

    def __init__(self, runtime: RuntimeState):
        self.runtime = runtime
        self.face_mesh = MP_FACE_MESH.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.prev_smooth_gaze: Optional[Tuple[float, float]] = None
        self.prev_timestamp = now_ts()
        self.fps_estimate = DEFAULT_FPS_ESTIMATE
        cfg = runtime.config
        self.blink = BlinkInterpreter(
            threshold=cfg.blink_threshold,
            double_window_ms=cfg.blink_double_window_ms,
            cooldown_ms=cfg.blink_cooldown_ms,
        )

    def update_config_dependent_modules(self) -> None:
        cfg = self.runtime.config
        self.blink.threshold = cfg.blink_threshold
        self.blink.double_window_ms = cfg.blink_double_window_ms
        self.blink.cooldown_ms = cfg.blink_cooldown_ms

    def _update_fps(self) -> float:
        t = now_ts()
        dt = max(t - self.prev_timestamp, 1e-6)
        current = 1.0 / dt
        self.fps_estimate = ema(self.fps_estimate, current, 0.90)
        self.prev_timestamp = t
        return self.fps_estimate

    def _make_empty_measurement(self) -> IrisMeasurement:
        return IrisMeasurement(timestamp=now_ts(), fps_estimate=self.fps_estimate)

    def process(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, IrisMeasurement, Dict[str, Any]]:
        self.update_config_dependent_modules()
        cfg = self.runtime.config

        frame_bgr = crop_to_aspect_ratio(frame_bgr, cfg.frame_width, cfg.frame_height)
        if cfg.draw_mirror:
            frame_bgr = cv2.flip(frame_bgr, 1)

        proc_bgr = preprocess_frame_for_tracking(frame_bgr, cfg)
        rgb = to_rgb(proc_bgr)
        h, w = rgb.shape[:2]

        fps_est = self._update_fps()
        measurement = self._make_empty_measurement()
        measurement.fps_estimate = fps_est

        results = self.face_mesh.process(rgb)
        annotated = frame_bgr.copy()
        debug: Dict[str, Any] = {"frame_w": w, "frame_h": h, "fps": fps_est}

        if not results.multi_face_landmarks:
            measurement.face_found = False
            self._draw_status_panel(annotated, measurement)
            return annotated, measurement, debug

        face_landmarks = results.multi_face_landmarks[0]
        pts = mp_landmarks_to_np(face_landmarks, w, h)

        face_box = compute_face_box(pts, w, h)
        measurement.face_box = tuple(map(int, face_box))

        # Centros dos olhos e tamanhos.
        left_eye_center, eye_width_left = compute_eye_center_and_size(pts, LEFT_EYE_CONTOUR, LEFT_EYE_OUTER, LEFT_EYE_INNER)
        right_eye_center, eye_width_right = compute_eye_center_and_size(pts, RIGHT_EYE_CONTOUR, RIGHT_EYE_OUTER, RIGHT_EYE_INNER)
        measurement.left_eye_center = left_eye_center
        measurement.right_eye_center = right_eye_center
        measurement.eye_width_left_px = eye_width_left
        measurement.eye_width_right_px = eye_width_right

        # Íris.
        left_iris_pts = pick_points(pts, LEFT_IRIS)
        right_iris_pts = pick_points(pts, RIGHT_IRIS)
        left_iris_center, left_iris_radius, left_ellipse = fit_ellipse_or_mean(left_iris_pts)
        right_iris_center, right_iris_radius, right_ellipse = fit_ellipse_or_mean(right_iris_pts)
        measurement.left_iris_center = left_iris_center
        measurement.right_iris_center = right_iris_center
        measurement.iris_radius_left_px = left_iris_radius
        measurement.iris_radius_right_px = right_iris_radius

        # EAR.
        ear_left = compute_ear(pts, LEFT_BLINK_EAR)
        ear_right = compute_ear(pts, RIGHT_BLINK_EAR)
        measurement.ear_left = ear_left
        measurement.ear_right = ear_right
        ear_avg = 0.5 * (ear_left + ear_right)
        smoothed_blink, command, blink_count, blink_state = self.blink.update(ear_avg, alpha=cfg.blink_smoothing)
        measurement.blink_strength = smoothed_blink
        measurement.command = command
        measurement.blink_count = blink_count
        measurement.blink_state = blink_state

        # Razão relativa da íris em cada olho.
        left_ratio_x, left_ratio_y = compute_relative_iris_ratio(
            left_iris_center,
            tuple(pts[LEFT_EYE_OUTER]),
            tuple(pts[LEFT_EYE_INNER]),
            tuple(pts[LEFT_EYE_TOP]),
            tuple(pts[LEFT_EYE_BOTTOM]),
        )
        right_ratio_x, right_ratio_y = compute_relative_iris_ratio(
            right_iris_center,
            tuple(pts[RIGHT_EYE_OUTER]),
            tuple(pts[RIGHT_EYE_INNER]),
            tuple(pts[RIGHT_EYE_TOP]),
            tuple(pts[RIGHT_EYE_BOTTOM]),
        )
        measurement.left_ratio_x = left_ratio_x
        measurement.left_ratio_y = left_ratio_y
        measurement.right_ratio_x = right_ratio_x
        measurement.right_ratio_y = right_ratio_y

        # Combinação dos dois olhos em uma coordenada bruta centralizada em 0.
        raw_x = ((left_ratio_x - 0.5) + (right_ratio_x - 0.5)) * 0.5
        raw_y = ((left_ratio_y - 0.5) + (right_ratio_y - 0.5)) * 0.5

        # Deadzone para reduzir tremor micro.
        if abs(raw_x) < cfg.gaze_deadzone:
            raw_x = 0.0
        if abs(raw_y) < cfg.gaze_deadzone:
            raw_y = 0.0

        measurement.raw_gaze_x = raw_x
        measurement.raw_gaze_y = raw_y

        smooth = ema_point(self.prev_smooth_gaze, (raw_x, raw_y), cfg.smoothing)
        self.prev_smooth_gaze = smooth
        measurement.smooth_gaze_x = smooth[0]
        measurement.smooth_gaze_y = smooth[1]

        # Mapeamento para tela.
        calib = self.runtime.calibration
        if calib.completed:
            screen_x, screen_y = map_raw_to_screen(smooth[0], smooth[1], calib)
        else:
            screen_x = clamp(0.5 + smooth[0] * 2.0, 0.0, 1.0)
            screen_y = clamp(0.5 + smooth[1] * 2.0, 0.0, 1.0)

        measurement.screen_x = screen_x
        measurement.screen_y = screen_y

        # Vetor 3D pseudo geométrico.
        gaze_vec = normalize_vec3(np.array([smooth[0] * 1.4, smooth[1] * 1.4, 1.0], dtype=np.float32))
        measurement.gaze_vector_3d = (float(gaze_vec[0]), float(gaze_vec[1]), float(gaze_vec[2]))

        # Confiança.
        conf = estimate_confidence(face_box, eye_width_left, eye_width_right, left_iris_radius, right_iris_radius, cfg)
        measurement.confidence = conf
        measurement.face_found = conf >= cfg.score_min_confidence

        if measurement.face_found:
            self._handle_runtime_side_effects(measurement)

        self._draw_annotations(
            annotated=annotated,
            points=pts,
            left_iris_pts=left_iris_pts,
            right_iris_pts=right_iris_pts,
            left_ellipse=left_ellipse,
            right_ellipse=right_ellipse,
            measurement=measurement,
        )
        self._draw_status_panel(annotated, measurement)

        debug.update(
            {
                "left_ratio_x": left_ratio_x,
                "left_ratio_y": left_ratio_y,
                "right_ratio_x": right_ratio_x,
                "right_ratio_y": right_ratio_y,
                "raw_x": raw_x,
                "raw_y": raw_y,
                "screen_x": screen_x,
                "screen_y": screen_y,
                "confidence": conf,
            }
        )

        return annotated, measurement, debug

    def _handle_runtime_side_effects(self, measurement: IrisMeasurement) -> None:
        target = self.runtime.current_calibration_target
        if target is not None:
            self.runtime.add_calibration_sample(target, (measurement.smooth_gaze_x, measurement.smooth_gaze_y))

    def _draw_annotations(
        self,
        annotated: np.ndarray,
        points: np.ndarray,
        left_iris_pts: np.ndarray,
        right_iris_pts: np.ndarray,
        left_ellipse: Optional[Tuple[Any, Any, Any]],
        right_ellipse: Optional[Tuple[Any, Any, Any]],
        measurement: IrisMeasurement,
    ) -> None:
        cfg = self.runtime.config
        h, w = annotated.shape[:2]

        face_box = measurement.face_box
        if cfg.show_eye_boxes:
            x, y, fw, fh = face_box
            cv2.rectangle(annotated, (x, y), (x + fw, y + fh), COLOR_CYAN, 1, cv2.LINE_AA)

            lx, ly, lw, lh = limit_bbox(bbox_from_points(pick_points(points, LEFT_EYE_CONTOUR), margin=5), w, h)
            rx, ry, rw, rh = limit_bbox(bbox_from_points(pick_points(points, RIGHT_EYE_CONTOUR), margin=5), w, h)
            cv2.rectangle(annotated, (lx, ly), (lx + lw, ly + lh), COLOR_BLUE, 1, cv2.LINE_AA)
            cv2.rectangle(annotated, (rx, ry), (rx + rw, ry + rh), COLOR_BLUE, 1, cv2.LINE_AA)

        if cfg.show_mesh:
            for pt in points.astype(np.int32)[::3]:
                cv2.circle(annotated, (pt[0], pt[1]), 1, (100, 100, 100), -1, cv2.LINE_AA)

        if cfg.show_iris_points:
            for pt in left_iris_pts.astype(np.int32):
                cv2.circle(annotated, (pt[0], pt[1]), 2, COLOR_GREEN, -1, cv2.LINE_AA)
            for pt in right_iris_pts.astype(np.int32):
                cv2.circle(annotated, (pt[0], pt[1]), 2, COLOR_GREEN, -1, cv2.LINE_AA)
            cv2.circle(annotated, as_int_pt(measurement.left_iris_center), 3, COLOR_ORANGE, -1, cv2.LINE_AA)
            cv2.circle(annotated, as_int_pt(measurement.right_iris_center), 3, COLOR_ORANGE, -1, cv2.LINE_AA)
            cv2.circle(annotated, as_int_pt(measurement.left_eye_center), 3, COLOR_MAGENTA, -1, cv2.LINE_AA)
            cv2.circle(annotated, as_int_pt(measurement.right_eye_center), 3, COLOR_MAGENTA, -1, cv2.LINE_AA)

        if left_ellipse is not None:
            cv2.ellipse(annotated, left_ellipse, COLOR_YELLOW, 1, cv2.LINE_AA)
        if right_ellipse is not None:
            cv2.ellipse(annotated, right_ellipse, COLOR_YELLOW, 1, cv2.LINE_AA)

        if cfg.show_vectors:
            left_center = as_int_pt(measurement.left_eye_center)
            right_center = as_int_pt(measurement.right_eye_center)
            left_iris = as_int_pt(measurement.left_iris_center)
            right_iris = as_int_pt(measurement.right_iris_center)
            cv2.line(annotated, left_center, left_iris, COLOR_ORANGE, 2, cv2.LINE_AA)
            cv2.line(annotated, right_center, right_iris, COLOR_ORANGE, 2, cv2.LINE_AA)

            screen_pt = (int(measurement.screen_x * (w - 1)), int(measurement.screen_y * (h - 1)))
            draw_crosshair(annotated, screen_pt, size=14, color=COLOR_RED)
            cv2.circle(annotated, screen_pt, 10, COLOR_RED, 2, cv2.LINE_AA)

    def _draw_status_panel(self, annotated: np.ndarray, measurement: IrisMeasurement) -> None:
        cfg = self.runtime.config
        panel_w = 300
        panel_h = 154
        draw_transparent_panel(annotated, (10, 10, panel_w, panel_h), COLOR_PANEL, alpha=0.52)

        if cfg.show_debug_text:
            put_text_box(annotated, f"Face: {'OK' if measurement.face_found else '---'}", (18, 34), COLOR_GREEN if measurement.face_found else COLOR_RED)
            put_text_box(annotated, f"Conf: {measurement.confidence:.2f}", (18, 58), COLOR_TEXT)
            put_text_box(annotated, f"FPS: {measurement.fps_estimate:.1f}", (18, 82), COLOR_TEXT)
            put_text_box(annotated, f"Raw: ({measurement.raw_gaze_x:+.3f}, {measurement.raw_gaze_y:+.3f})", (18, 106), COLOR_TEXT)
            put_text_box(annotated, f"Tela: ({measurement.screen_x:.3f}, {measurement.screen_y:.3f})", (18, 130), COLOR_TEXT)
            put_text_box(annotated, f"Blink: {measurement.blink_state} | {measurement.command}", (18, 154), COLOR_YELLOW)


# ============================================================================
# PROCESSADOR PARA STREAMLIT-WEBRTC
# ============================================================================

class StreamlitIrisProcessor(VideoProcessorBase):
    def __init__(self) -> None:
        self.runtime: Optional[RuntimeState] = None
        self.engine: Optional[IrisTrackerEngine] = None

    def set_runtime(self, runtime: RuntimeState) -> None:
        self.runtime = runtime
        self.engine = IrisTrackerEngine(runtime)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        if self.runtime is None or self.engine is None:
            img = frame.to_ndarray(format="bgr24")
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        img = frame.to_ndarray(format="bgr24")
        annotated, measurement, debug = self.engine.process(img)
        self.runtime.add_measurement(measurement, to_rgb(annotated), debug=debug)
        return av.VideoFrame.from_ndarray(annotated, format="bgr24")


# ============================================================================
# RELATÓRIO PDF
# ============================================================================

def generate_pdf_report(runtime: RuntimeState) -> bytes:
    with runtime.lock:
        stats = runtime.stats
        measurement = runtime.last_measurement
        heatmap_rgb = runtime.last_heatmap_rgb.copy()
        calib = runtime.calibration
        session_name = runtime.session_name
        df = runtime.export_measurements_df()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.textColor = colors.HexColor("#1F2937")
    title_style.fontName = "Helvetica-Bold"

    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#111827"),
    )

    story: List[Any] = []
    story.append(Paragraph("Relatório de Rastreamento da Íris", title_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"Sessão: <b>{session_name}</b>", body_style))
    story.append(Paragraph(f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}", body_style))
    story.append(Spacer(1, 0.25 * cm))

    duration_sec = max(now_ts() - stats.start_time, 0.0)
    summary_data = [
        ["Duração (s)", f"{duration_sec:.1f}", "Frames", str(stats.total_frames)],
        ["Frames válidos", str(stats.valid_frames), "Razão de detecção", f"{stats.face_detect_ratio:.2%}"],
        ["FPS médio", f"{stats.avg_fps:.1f}", "Confiança média", f"{stats.avg_confidence:.2f}"],
        ["Piscadas", str(stats.total_blinks), "Comando simples", str(stats.single_blink_commands)],
        ["Comando duplo", str(stats.double_blink_commands), "Último comando", measurement.command],
        ["Média X tela", f"{stats.avg_screen_x:.3f}", "Média Y tela", f"{stats.avg_screen_y:.3f}"],
    ]

    summary_table = Table(summary_data, colWidths=[4.0 * cm, 3.0 * cm, 4.0 * cm, 4.0 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.35 * cm))

    calib_lines = [
        f"Centro bruto: ({calib.raw_center[0]:+.4f}, {calib.raw_center[1]:+.4f})",
        f"Esquerda bruta: ({calib.raw_left[0]:+.4f}, {calib.raw_left[1]:+.4f})",
        f"Direita bruta: ({calib.raw_right[0]:+.4f}, {calib.raw_right[1]:+.4f})",
        f"Cima bruto: ({calib.raw_up[0]:+.4f}, {calib.raw_up[1]:+.4f})",
        f"Baixo bruto: ({calib.raw_down[0]:+.4f}, {calib.raw_down[1]:+.4f})",
        f"Calibração completa: {'Sim' if calib.completed else 'Não'}",
    ]
    story.append(Paragraph("<b>Calibração</b>", body_style))
    for line in calib_lines:
        story.append(Paragraph(line, body_style))
    story.append(Spacer(1, 0.35 * cm))

    if heatmap_rgb.size > 0:
        img_bytes = encode_png_bytes(heatmap_rgb)
        if img_bytes:
            img = Image.open(io.BytesIO(img_bytes))
            max_w = 15.5 * cm
            max_h = 8.8 * cm
            width, height = img.size
            scale = min(max_w / width, max_h / height)
            reader = ImageReader(io.BytesIO(img_bytes))
            story.append(Paragraph("<b>Mapa de calor do olhar</b>", body_style))
            story.append(Spacer(1, 0.15 * cm))
            story.append(
                Table(
                    [[reader]],
                    colWidths=[width * scale],
                    rowHeights=[height * scale],
                    style=TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF"))]),
                )
            )
            story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("<b>Resumo textual</b>", body_style))
    story.append(
        Paragraph(
            (
                "Este relatório resume uma sessão de rastreamento ocular baseada em landmarks de íris do MediaPipe, "
                "com suavização temporal, detecção de piscadas e projeção do olhar em coordenadas normalizadas de tela. "
                "O mapa de calor destaca as regiões mais observadas ao longo da sessão."
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    if not df.empty:
        story.append(Paragraph("<b>Amostra de medições</b>", body_style))
        sample = df.tail(12).copy()
        sample["timestamp"] = sample["timestamp"].map(lambda v: f"{v:.3f}")
        sample["screen_x"] = sample["screen_x"].map(lambda v: f"{v:.3f}")
        sample["screen_y"] = sample["screen_y"].map(lambda v: f"{v:.3f}")
        sample["confidence"] = sample["confidence"].map(lambda v: f"{v:.2f}")
        sample["fps_estimate"] = sample["fps_estimate"].map(lambda v: f"{v:.1f}")
        sample = sample[["timestamp", "fps_estimate", "confidence", "screen_x", "screen_y", "command"]]
        sample_data = [sample.columns.tolist()] + sample.values.tolist()
        sample_table = Table(sample_data, repeatRows=1)
        sample_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(sample_table)

    doc.build(story)
    return buffer.getvalue()


# ============================================================================
# EXPORTAÇÕES AUXILIARES
# ============================================================================

def export_csv_bytes(runtime: RuntimeState) -> bytes:
    df = runtime.export_measurements_df()
    if df.empty:
        return b""
    return df.to_csv(index=False).encode("utf-8")


def save_runtime_snapshot(runtime: RuntimeState) -> Dict[str, str]:
    with runtime.lock:
        session_name = runtime.session_name or DEFAULT_SESSION_NAME
        session_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_name)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.join(runtime.export_dir, f"{session_slug}_{timestamp}")
        frame_path = base + "_frame.png"
        heatmap_path = base + "_heatmap.png"
        json_path = base + "_summary.json"
        csv_path = base + "_points.csv"
        pdf_path = base + "_report.pdf"

        frame_rgb = runtime.last_frame_rgb.copy()
        heatmap_rgb = runtime.last_heatmap_rgb.copy()
        summary = {
            "session_name": runtime.session_name,
            "stats": asdict(runtime.stats),
            "calibration": asdict(runtime.calibration),
            "last_measurement": asdict(runtime.last_measurement),
            "command_log": list(runtime.command_log),
        }
        df = runtime.export_measurements_df()
        pdf_bytes = generate_pdf_report(runtime)

    if frame_rgb.size > 0:
        cv2.imwrite(frame_path, to_bgr(frame_rgb))
    if heatmap_rgb.size > 0:
        cv2.imwrite(heatmap_path, to_bgr(heatmap_rgb))
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(safe_json_dumps(summary))
    if not df.empty:
        df.to_csv(csv_path, index=False)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    return {
        "frame": frame_path,
        "heatmap": heatmap_path,
        "json": json_path,
        "csv": csv_path if os.path.exists(csv_path) else "",
        "pdf": pdf_path,
    }


# ============================================================================
# UI DO STREAMLIT
# ============================================================================

def init_streamlit_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)


RUNTIME_REGISTRY: Dict[str, RuntimeState] = {}


def get_or_create_runtime(key: str) -> RuntimeState:
    if key not in RUNTIME_REGISTRY:
        RUNTIME_REGISTRY[key] = RuntimeState()
    return RUNTIME_REGISTRY[key]


def build_config_sidebar(runtime: RuntimeState) -> None:
    st.sidebar.header("Configurações do rastreamento")
    cfg = runtime.config

    frame_width = st.sidebar.selectbox("Largura do frame", [640, 800, 960, 1280], index=[640, 800, 960, 1280].index(cfg.frame_width) if cfg.frame_width in [640, 800, 960, 1280] else 0)
    frame_height = st.sidebar.selectbox("Altura do frame", [480, 600, 720], index=[480, 600, 720].index(cfg.frame_height) if cfg.frame_height in [480, 600, 720] else 0)
    smoothing = st.sidebar.slider("Suavização do olhar", 0.0, 0.98, float(cfg.smoothing), 0.01)
    blink_smoothing = st.sidebar.slider("Suavização da piscada", 0.0, 0.95, float(cfg.blink_smoothing), 0.01)
    blink_threshold = st.sidebar.slider("Limiar EAR de piscada", 0.08, 0.40, float(cfg.blink_threshold), 0.005)
    blink_double_window_ms = st.sidebar.slider("Janela de piscada dupla (ms)", 250, 1200, int(cfg.blink_double_window_ms), 10)
    blink_cooldown_ms = st.sidebar.slider("Cooldown de comando (ms)", 100, 800, int(cfg.blink_cooldown_ms), 10)
    gaze_deadzone = st.sidebar.slider("Zona morta do olhar", 0.0, 0.10, float(cfg.gaze_deadzone), 0.005)

    st.sidebar.subheader("Pré-processamento")
    enhance_contrast = st.sidebar.checkbox("Aumentar contraste", value=cfg.enhance_contrast)
    use_hist_eq = st.sidebar.checkbox("Equalização global", value=cfg.use_hist_eq)
    gamma = st.sidebar.slider("Gamma", 0.5, 2.2, float(cfg.gamma), 0.05)
    clahe_clip_limit = st.sidebar.slider("CLAHE clip limit", 0.5, 8.0, float(cfg.clahe_clip_limit), 0.1)
    clahe_grid_size = st.sidebar.slider("CLAHE grid", 2, 16, int(cfg.clahe_grid_size), 1)

    st.sidebar.subheader("Heatmap")
    heatmap_width = st.sidebar.slider("Heatmap largura", 24, 128, int(cfg.heatmap_width), 4)
    heatmap_height = st.sidebar.slider("Heatmap altura", 18, 96, int(cfg.heatmap_height), 3)

    st.sidebar.subheader("Exibição")
    show_mesh = st.sidebar.checkbox("Mostrar mesh", value=cfg.show_mesh)
    show_iris_points = st.sidebar.checkbox("Mostrar pontos da íris", value=cfg.show_iris_points)
    show_eye_boxes = st.sidebar.checkbox("Mostrar caixas dos olhos", value=cfg.show_eye_boxes)
    show_vectors = st.sidebar.checkbox("Mostrar vetores", value=cfg.show_vectors)
    show_debug_text = st.sidebar.checkbox("Mostrar texto de debug", value=cfg.show_debug_text)
    show_heatmap_preview = st.sidebar.checkbox("Mostrar heatmap preview", value=cfg.show_heatmap_preview)
    draw_mirror = st.sidebar.checkbox("Espelhar selfie", value=cfg.draw_mirror)

    st.sidebar.subheader("Calibração")
    calibration_samples_per_target = st.sidebar.slider("Amostras por alvo", 8, 60, int(cfg.calibration_samples_per_target), 1)
    score_min_confidence = st.sidebar.slider("Confiança mínima", 0.05, 0.95, float(cfg.score_min_confidence), 0.01)
    score_min_face_width_px = st.sidebar.slider("Largura mínima do rosto (px)", 30, 200, int(cfg.score_min_face_width_px), 1)
    score_min_eye_width_px = st.sidebar.slider("Largura mínima do olho (px)", 5, 40, int(cfg.score_min_eye_width_px), 1)

    st.sidebar.subheader("Registro")
    record_raw_points = st.sidebar.checkbox("Registrar pontos para CSV", value=cfg.record_raw_points)
    save_frame_snapshots = st.sidebar.checkbox("Salvar snapshots automaticamente", value=cfg.save_frame_snapshots)
    max_export_points = st.sidebar.slider("Máximo de pontos exportáveis", 500, 30000, int(cfg.max_export_points), 500)

    new_cfg = TrackerConfig(
        frame_width=frame_width,
        frame_height=frame_height,
        smoothing=smoothing,
        blink_smoothing=blink_smoothing,
        heatmap_width=heatmap_width,
        heatmap_height=heatmap_height,
        blink_threshold=blink_threshold,
        blink_double_window_ms=blink_double_window_ms,
        blink_cooldown_ms=blink_cooldown_ms,
        gaze_deadzone=gaze_deadzone,
        show_mesh=show_mesh,
        show_iris_points=show_iris_points,
        show_eye_boxes=show_eye_boxes,
        show_vectors=show_vectors,
        show_debug_text=show_debug_text,
        show_heatmap_preview=show_heatmap_preview,
        enhance_contrast=enhance_contrast,
        use_hist_eq=use_hist_eq,
        gamma=gamma,
        clahe_clip_limit=clahe_clip_limit,
        clahe_grid_size=clahe_grid_size,
        calibration_samples_per_target=calibration_samples_per_target,
        draw_mirror=draw_mirror,
        score_min_face_width_px=score_min_face_width_px,
        score_min_eye_width_px=score_min_eye_width_px,
        score_min_confidence=score_min_confidence,
        record_raw_points=record_raw_points,
        save_frame_snapshots=save_frame_snapshots,
        max_export_points=max_export_points,
    )
    runtime.update_config(new_cfg)


def render_intro() -> None:
    st.title("👁️ Rastreamento da Íris com Streamlit")
    st.markdown(
        """
        Este app usa **MediaPipe Face Mesh + streamlit-webrtc** para rastrear a íris pela webcam,
        estimar a direção do olhar, detectar piscadas e gerar **mapa de calor + PDF**.

        Ele foi estruturado para evitar os problemas clássicos de Streamlit Cloud com OpenCV:
        - sem `cv2.imshow`
        - sem `tkinter`
        - sem captura de janelas nativas
        - com `opencv-python-headless`
        """
    )


def render_live_metrics(runtime: RuntimeState) -> None:
    with runtime.lock:
        m = runtime.last_measurement
        s = runtime.stats
        current_target = runtime.current_calibration_target
        calib = runtime.calibration

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Face", "OK" if m.face_found else "---")
    c2.metric("Confiança", f"{m.confidence:.2f}")
    c3.metric("FPS", f"{m.fps_estimate:.1f}")
    c4.metric("Piscadas", f"{m.blink_count}")
    c5.metric("Comando", m.command)

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Tela X", f"{m.screen_x:.3f}")
    c7.metric("Tela Y", f"{m.screen_y:.3f}")
    c8.metric("EAR Esq.", f"{m.ear_left:.3f}")
    c9.metric("EAR Dir.", f"{m.ear_right:.3f}")

    if current_target:
        count = len(calib.target_samples[current_target])
        st.info(f"Capturando calibração: **{CALIBRATION_TARGET_LABELS[current_target]}** ({count}/{runtime.config.calibration_samples_per_target})")
    elif calib.completed:
        st.success("Calibração completa.")
    else:
        st.warning("Calibração ainda não concluída.")

    if s.total_frames > 0:
        st.caption(
            f"Frames: {s.total_frames} | Válidos: {s.valid_frames} | Detecção: {s.face_detect_ratio:.1%} | "
            f"FPS médio: {s.avg_fps:.1f} | Confiança média: {s.avg_confidence:.2f}"
        )


def render_calibration_controls(runtime: RuntimeState) -> None:
    st.subheader("Calibração")
    st.markdown(
        "Olhe para cada direção e clique no botão correspondente por alguns segundos para coletar amostras."
    )

    cols = st.columns(5)
    for i, target in enumerate(CALIBRATION_TARGETS):
        label = CALIBRATION_TARGET_LABELS[target]
        if cols[i].button(label, use_container_width=True):
            runtime.request_calibration_capture(target)

    c1, c2 = st.columns(2)
    if c1.button("Resetar calibração", use_container_width=True):
        with runtime.lock:
            runtime.calibration = CalibrationProfile()
            runtime.current_calibration_target = None
        st.toast("Calibração resetada")
    if c2.button("Parar captura atual", use_container_width=True):
        with runtime.lock:
            runtime.current_calibration_target = None
        st.toast("Captura interrompida")

    with runtime.lock:
        calib = runtime.calibration
        rows = []
        for target in CALIBRATION_TARGETS:
            rows.append(
                {
                    "alvo": CALIBRATION_TARGET_LABELS[target],
                    "amostras": len(calib.target_samples[target]),
                    "mediana_x": rolling_median_points(calib.target_samples[target])[0] if calib.target_samples[target] else 0.0,
                    "mediana_y": rolling_median_points(calib.target_samples[target])[1] if calib.target_samples[target] else 0.0,
                }
            )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_heatmap_preview(runtime: RuntimeState) -> None:
    with runtime.lock:
        heat = runtime.last_heatmap_rgb.copy()
        cfg = runtime.config

    st.subheader("Mapa de calor")
    if heat.size == 0 or not cfg.show_heatmap_preview:
        st.info("O heatmap aparecerá quando houver pontos suficientes.")
        return
    st.image(heat, channels="RGB", use_container_width=True)


def render_debug_panels(runtime: RuntimeState) -> None:
    with runtime.lock:
        m = runtime.last_measurement
        debug = runtime.last_debug.copy()
        df = runtime.export_measurements_df()

    tab1, tab2, tab3 = st.tabs(["Última leitura", "Debug bruto", "Tabela de pontos"])
    with tab1:
        st.json(asdict(m))
    with tab2:
        st.json(debug)
    with tab3:
        if df.empty:
            st.info("Ainda não há dados suficientes.")
        else:
            st.dataframe(df.tail(300), use_container_width=True)


def render_export_controls(runtime: RuntimeState) -> None:
    st.subheader("Exportação")
    with runtime.lock:
        runtime.session_name = st.text_input("Nome da sessão", value=runtime.session_name)

    col1, col2, col3, col4 = st.columns(4)

    csv_bytes = export_csv_bytes(runtime)
    pdf_bytes = generate_pdf_report(runtime)

    with runtime.lock:
        heat_png = encode_png_bytes(runtime.last_heatmap_rgb) if runtime.last_heatmap_rgb.size > 0 else b""
        frame_png = encode_png_bytes(runtime.last_frame_rgb) if runtime.last_frame_rgb.size > 0 else b""

    col1.download_button(
        "Baixar CSV",
        data=csv_bytes if csv_bytes else b"timestamp\n",
        file_name=f"{runtime.session_name}_pontos.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col2.download_button(
        "Baixar PDF",
        data=pdf_bytes,
        file_name=f"{runtime.session_name}_relatorio.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    col3.download_button(
        "Baixar heatmap PNG",
        data=heat_png if heat_png else b"",
        file_name=f"{runtime.session_name}_heatmap.png",
        mime="image/png",
        use_container_width=True,
    )
    col4.download_button(
        "Baixar frame PNG",
        data=frame_png if frame_png else b"",
        file_name=f"{runtime.session_name}_frame.png",
        mime="image/png",
        use_container_width=True,
    )

    if st.button("Salvar tudo em /mnt/data", use_container_width=True):
        paths = save_runtime_snapshot(runtime)
        st.success("Arquivos salvos no ambiente atual.")
        st.json(paths)


def render_command_log(runtime: RuntimeState) -> None:
    st.subheader("Log de comandos por piscada")
    with runtime.lock:
        log = list(runtime.command_log)
    if not log:
        st.info("Nenhum comando detectado ainda.")
        return
    df = pd.DataFrame(log, columns=["timestamp", "command"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    st.dataframe(df.iloc[::-1], use_container_width=True, hide_index=True)


def render_session_controls(runtime: RuntimeState) -> None:
    st.subheader("Controle da sessão")
    c1, c2, c3 = st.columns(3)
    if c1.button("Limpar sessão", use_container_width=True):
        runtime.clear_session()
    with runtime.lock:
        current_state = runtime.recording_enabled
    if c2.button("Pausar/Retomar gravação", use_container_width=True):
        with runtime.lock:
            runtime.recording_enabled = not runtime.recording_enabled
        st.toast("Gravação alterada")
    with runtime.lock:
        runtime.save_frame_snapshots = c3.checkbox("Snapshots automáticos", value=runtime.config.save_frame_snapshots)

    while not runtime.pending_messages.empty():
        try:
            st.toast(runtime.pending_messages.get_nowait())
        except queue.Empty:
            break


def render_instructions() -> None:
    with st.expander("Como rodar no Streamlit Cloud"):
        st.markdown(
            """
            1. Suba o arquivo `iris_streamlit_app.py` no seu repositório.
            2. Suba também o `requirements.txt` gerado junto.
            3. No Streamlit Cloud, aponte o app principal para `iris_streamlit_app.py`.
            4. Libere a permissão da webcam no navegador.
            5. Se a webcam não iniciar, atualize a página e verifique permissão do navegador.

            Observações:
            - use **opencv-python-headless** em vez de opencv-python;
            - webcam ao vivo funciona melhor com **streamlit-webrtc**;
            - em Python muito novo, algumas versões de MediaPipe podem falhar.
            """
        )


def render_app(runtime: RuntimeState) -> None:
    render_intro()
    build_config_sidebar(runtime)
    render_instructions()

    st.markdown("---")
    st.subheader("Webcam ao vivo")

    ctx = webrtc_streamer(
        key=f"iris-tracker-{id(runtime)}",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
        video_processor_factory=StreamlitIrisProcessor,
    )

    if ctx.video_processor:
        processor = ctx.video_processor
        if isinstance(processor, StreamlitIrisProcessor):
            processor.set_runtime(runtime)

    render_live_metrics(runtime)

    col_left, col_right = st.columns([1.05, 0.95])
    with col_left:
        render_calibration_controls(runtime)
        render_session_controls(runtime)
        render_command_log(runtime)
    with col_right:
        render_heatmap_preview(runtime)

    st.markdown("---")
    render_export_controls(runtime)

    st.markdown("---")
    render_debug_panels(runtime)


# ============================================================================
# BLOCO EXTRA: FUNÇÕES DE APOIO ESTENDIDAS
# ============================================================================
# As funções abaixo ampliam a base do projeto e ajudam em manutenção, testes,
# serialização, inspeção, normalização e visualização. Elas também servem para
# deixar o arquivo completo e pronto para futuras extensões do Simulacro.


def measurement_to_compact_dict(m: IrisMeasurement) -> Dict[str, Any]:
    return {
        "t": m.timestamp,
        "fps": m.fps_estimate,
        "ok": m.face_found,
        "c": m.confidence,
        "rx": m.raw_gaze_x,
        "ry": m.raw_gaze_y,
        "sx": m.screen_x,
        "sy": m.screen_y,
        "cmd": m.command,
        "bc": m.blink_count,
    }


def measurements_to_json_lines(measurements: List[IrisMeasurement]) -> str:
    lines = []
    for m in measurements:
        lines.append(json.dumps(measurement_to_compact_dict(m), ensure_ascii=False))
    return "\n".join(lines)


def compact_stats_text(stats: SessionStats) -> str:
    duration = max(now_ts() - stats.start_time, 0.0)
    return (
        f"Duração: {duration:.1f}s | Frames: {stats.total_frames} | "
        f"Válidos: {stats.valid_frames} | FPS médio: {stats.avg_fps:.1f} | "
        f"Confiança média: {stats.avg_confidence:.2f} | Piscadas: {stats.total_blinks}"
    )


def build_gaze_path_image(runtime: RuntimeState, width: int = 800, height: int = 450) -> np.ndarray:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (18, 18, 18)
    with runtime.lock:
        items = list(runtime.measurements)
    if len(items) < 2:
        put_text_box(canvas, "Poucos pontos para trilha do olhar", (20, 30), COLOR_TEXT)
        return canvas
    pts = []
    for m in items:
        pts.append((int(m.screen_x * (width - 1)), int(m.screen_y * (height - 1))))
    for i in range(1, len(pts)):
        alpha = i / max(len(pts) - 1, 1)
        color = (
            int(50 + 150 * alpha),
            int(80 + 120 * alpha),
            int(230 - 120 * alpha),
        )
        cv2.line(canvas, pts[i - 1], pts[i], color, 2, cv2.LINE_AA)
    for pt in pts[:: max(len(pts) // 60, 1)]:
        cv2.circle(canvas, pt, 3, COLOR_YELLOW, -1, cv2.LINE_AA)
    draw_crosshair(canvas, pts[-1], size=10, color=COLOR_RED)
    put_text_box(canvas, "Trilha do olhar", (20, 30), COLOR_TEXT)
    return canvas


def build_blink_timeline(runtime: RuntimeState, width: int = 800, height: int = 220) -> np.ndarray:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (14, 14, 14)
    with runtime.lock:
        items = list(runtime.measurements)
    if len(items) < 2:
        put_text_box(canvas, "Poucos dados para timeline", (20, 30), COLOR_TEXT)
        return canvas
    ears = np.array([(m.ear_left + m.ear_right) * 0.5 for m in items], dtype=np.float32)
    min_v = float(np.min(ears))
    max_v = float(np.max(ears))
    span = max(max_v - min_v, 1e-6)
    pts = []
    for i, val in enumerate(ears):
        x = int(i / max(len(ears) - 1, 1) * (width - 1))
        y = int((1.0 - (val - min_v) / span) * (height - 30)) + 10
        pts.append((x, y))
    for i in range(1, len(pts)):
        cv2.line(canvas, pts[i - 1], pts[i], COLOR_GREEN, 2, cv2.LINE_AA)
    put_text_box(canvas, f"EAR médio | min={min_v:.3f} max={max_v:.3f}", (20, 30), COLOR_TEXT)
    return canvas


def build_confidence_timeline(runtime: RuntimeState, width: int = 800, height: int = 220) -> np.ndarray:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (14, 14, 14)
    with runtime.lock:
        items = list(runtime.measurements)
    if len(items) < 2:
        put_text_box(canvas, "Poucos dados para timeline", (20, 30), COLOR_TEXT)
        return canvas
    vals = np.array([m.confidence for m in items], dtype=np.float32)
    pts = []
    for i, val in enumerate(vals):
        x = int(i / max(len(vals) - 1, 1) * (width - 1))
        y = int((1.0 - val) * (height - 30)) + 10
        pts.append((x, y))
    for i in range(1, len(pts)):
        cv2.line(canvas, pts[i - 1], pts[i], COLOR_CYAN, 2, cv2.LINE_AA)
    put_text_box(canvas, f"Confiança | média={float(np.mean(vals)):.2f}", (20, 30), COLOR_TEXT)
    return canvas


def build_dashboard_images(runtime: RuntimeState) -> Dict[str, np.ndarray]:
    with runtime.lock:
        frame = runtime.last_frame_rgb.copy()
        heat = runtime.last_heatmap_rgb.copy()
    images = {
        "frame": frame,
        "heatmap": heat,
        "path": build_gaze_path_image(runtime),
        "blink": build_blink_timeline(runtime),
        "confidence": build_confidence_timeline(runtime),
    }
    return images


def render_analysis_gallery(runtime: RuntimeState) -> None:
    st.subheader("Galeria analítica")
    imgs = build_dashboard_images(runtime)
    c1, c2 = st.columns(2)
    with c1:
        if imgs["frame"].size > 0:
            st.image(imgs["frame"], caption="Último frame", channels="RGB", use_container_width=True)
        st.image(imgs["path"], caption="Trilha do olhar", channels="RGB", use_container_width=True)
    with c2:
        if imgs["heatmap"].size > 0:
            st.image(imgs["heatmap"], caption="Mapa de calor", channels="RGB", use_container_width=True)
        st.image(imgs["blink"], caption="Timeline EAR", channels="RGB", use_container_width=True)
        st.image(imgs["confidence"], caption="Timeline de confiança", channels="RGB", use_container_width=True)


def render_advanced_metrics(runtime: RuntimeState) -> None:
    with runtime.lock:
        df = runtime.export_measurements_df()
    st.subheader("Métricas avançadas")
    if df.empty:
        st.info("Ainda não há dados suficientes para métricas avançadas.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Desvio X", f"{df['screen_x'].std():.4f}" if len(df) > 1 else "0.0000")
    col2.metric("Desvio Y", f"{df['screen_y'].std():.4f}" if len(df) > 1 else "0.0000")
    col3.metric("Frames exportáveis", str(len(df)))

    if len(df) > 5:
        corr = df[["screen_x", "screen_y", "confidence", "fps_estimate"]].corr(numeric_only=True)
        st.write("Correlação")
        st.dataframe(corr, use_container_width=True)


def render_full_dashboard(runtime: RuntimeState) -> None:
    st.markdown("---")
    render_analysis_gallery(runtime)
    st.markdown("---")
    render_advanced_metrics(runtime)


# ============================================================================
# FERRAMENTAS DE PERSISTÊNCIA OPCIONAIS
# ============================================================================

def save_calibration_profile(runtime: RuntimeState, path: str) -> None:
    with runtime.lock:
        payload = asdict(runtime.calibration)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_calibration_profile(runtime: RuntimeState, path: str) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    calib = CalibrationProfile()
    calib.target_samples = payload.get("target_samples", calib.target_samples)
    calib.raw_center = tuple(payload.get("raw_center", calib.raw_center))
    calib.raw_left = tuple(payload.get("raw_left", calib.raw_left))
    calib.raw_right = tuple(payload.get("raw_right", calib.raw_right))
    calib.raw_up = tuple(payload.get("raw_up", calib.raw_up))
    calib.raw_down = tuple(payload.get("raw_down", calib.raw_down))
    calib.completed = bool(payload.get("completed", calib.completed))
    calib.updated_at = float(payload.get("updated_at", calib.updated_at))
    with runtime.lock:
        runtime.calibration = calib
    return True


def render_persistence_controls(runtime: RuntimeState) -> None:
    st.subheader("Persistência")
    c1, c2 = st.columns(2)
    default_calib_path = os.path.join("/mnt/data", f"{runtime.session_name}_calibracao.json")
    calib_path = c1.text_input("Arquivo de calibração", value=default_calib_path)
    if c1.button("Salvar calibração", use_container_width=True):
        save_calibration_profile(runtime, calib_path)
        st.success(f"Calibração salva em {calib_path}")
    if c2.button("Carregar calibração", use_container_width=True):
        ok = load_calibration_profile(runtime, calib_path)
        if ok:
            st.success("Calibração carregada")
        else:
            st.error("Arquivo não encontrado")


# ============================================================================
# BLOCO ADICIONAL DE UTILIDADES MATEMÁTICAS
# ============================================================================
# Este bloco existe para dar base a futuras expansões 3D e manter o arquivo rico.


def rotation_matrix_from_euler(yaw: float, pitch: float, roll: float) -> np.ndarray:
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=np.float32)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=np.float32)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=np.float32)
    return rz @ ry @ rx


def project_vector_to_image(vec3: np.ndarray, width: int, height: int, scale: float = 180.0) -> Tuple[int, int]:
    vec3 = normalize_vec3(vec3)
    x = int(width * 0.5 + vec3[0] * scale)
    y = int(height * 0.5 + vec3[1] * scale)
    return x, y


def pseudo_head_pose(points: np.ndarray) -> Tuple[float, float, float]:
    """
    Estimativa muito simples de orientação facial relativa.
    Não substitui solvePnP, mas é leve e suficiente para debug.
    """
    left = points[FACE_LEFT]
    right = points[FACE_RIGHT]
    nose = points[NOSE_TIP]
    forehead = points[FOREHEAD]
    chin = points[CHIN]

    face_center = (left + right + forehead + chin) * 0.25
    horiz = right - left
    vert = chin - forehead
    yaw = math.atan2(float(nose[0] - face_center[0]), max(float(np.linalg.norm(horiz)), 1e-6)) * 3.0
    pitch = math.atan2(float(nose[1] - face_center[1]), max(float(np.linalg.norm(vert)), 1e-6)) * 3.0
    roll = math.atan2(float(horiz[1]), max(float(horiz[0]), 1e-6))
    return yaw, pitch, roll


def compose_gaze_with_head(gaze: Tuple[float, float, float], yaw: float, pitch: float, roll: float) -> Tuple[float, float, float]:
    R = rotation_matrix_from_euler(yaw, pitch, roll)
    g = normalize_vec3(np.array(gaze, dtype=np.float32))
    out = normalize_vec3(R @ g)
    return float(out[0]), float(out[1]), float(out[2])


def render_pose_estimate(runtime: RuntimeState) -> None:
    st.subheader("Estimativa geométrica")
    with runtime.lock:
        last = runtime.last_measurement
        frame = runtime.last_frame_rgb.copy()
    if frame.size == 0:
        st.info("Aguardando frame.")
        return
    vec = np.array(last.gaze_vector_3d, dtype=np.float32)
    x, y = project_vector_to_image(vec, frame.shape[1], frame.shape[0])
    overlay = frame.copy()
    center = (frame.shape[1] // 2, frame.shape[0] // 2)
    cv2.line(overlay, center, (x, y), COLOR_RED, 3, cv2.LINE_AA)
    draw_crosshair(overlay, center, size=12, color=COLOR_CYAN)
    draw_crosshair(overlay, (x, y), size=12, color=COLOR_RED)
    st.image(overlay, channels="RGB", use_container_width=True)
    st.caption(f"Vetor 3D atual: ({vec[0]:+.3f}, {vec[1]:+.3f}, {vec[2]:+.3f})")


# ============================================================================
# DIAGNÓSTICO DE AMBIENTE
# ============================================================================

def render_environment_diagnostics() -> None:
    st.subheader("Diagnóstico")
    info = {
        "python_executable": os.sys.executable,
        "cwd": os.getcwd(),
        "opencv_version": cv2.__version__,
        "numpy_version": np.__version__,
        "streamlit_webrtc_loaded": True,
        "mediapipe_loaded": True,
    }
    st.json(info)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    init_streamlit_page()
    runtime_key = st.session_state.get("runtime_key")
    if runtime_key is None:
        runtime_key = str(uuid.uuid4())
        st.session_state["runtime_key"] = runtime_key
    runtime = get_or_create_runtime(runtime_key)

    render_app(runtime)
    render_full_dashboard(runtime)
    render_persistence_controls(runtime)
    render_pose_estimate(runtime)
    render_environment_diagnostics()


if __name__ == "__main__":
    main()
