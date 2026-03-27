import os
import io
import time
import math
import json
import uuid
import threading
from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List, Optional, Tuple

import av
import cv2
import numpy as np
import streamlit as st
import mediapipe as mp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from streamlit_webrtc import WebRtcMode, RTCConfiguration, VideoProcessorBase, webrtc_streamer


# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "Sala 3D com Rastreamento Ocular"
EXPORT_DIR = "exports"
REPORT_DIR = "relatorios"
ASSETS_DIR = "assets_quadros"
CANVAS_W = 960
CANVAS_H = 540
EYE_DEBUG_W = 640
EYE_DEBUG_H = 480
ROOM_HALF_WIDTH = 5.0
ROOM_HALF_HEIGHT = 3.0
ROOM_DEPTH = 9.0
DEFAULT_FOCAL = 820.0
RTC_CONFIGURATION = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
FONT = cv2.FONT_HERSHEY_SIMPLEX

os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

mp_face_mesh = mp.solutions.face_mesh

RIGHT_EYE_POINTS = [33, 133, 159, 145, 158, 153, 160, 144]
LEFT_EYE_POINTS = [362, 263, 386, 374, 385, 380, 387, 373]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_IRIS = [474, 475, 476, 477]


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class Painting:
    pid: str
    title: str
    artist: str
    year: str
    description: str
    wall: str  # front, left, right
    center: Tuple[float, float, float]
    size: Tuple[float, float]
    image_path: str


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    session_id: str = field(default_factory=lambda: time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    selected_pid: Optional[str] = None
    hovered_pid: Optional[str] = None
    fixating_pid: Optional[str] = None
    fixation_started_at: float = 0.0
    zoom_level: float = 1.0
    blink_pending_at: Optional[float] = None
    last_blink_at: Optional[float] = None
    last_blink_state_closed: bool = False
    eye_closed_started_at: Optional[float] = None
    calibration_center: Optional[Tuple[float, float]] = None
    smoothed_pupil: Optional[Tuple[float, float]] = None
    smoothed_gaze_norm: Tuple[float, float] = (0.0, 0.0)
    latest_gallery_frame: Optional[np.ndarray] = None
    latest_eye_frame: Optional[np.ndarray] = None
    latest_gallery_point: Optional[Tuple[int, int]] = None
    latest_tracking_quality: float = 0.0
    latest_status: str = "Aguardando câmera"
    heatmap: np.ndarray = field(default_factory=lambda: np.zeros((CANVAS_H, CANVAS_W), dtype=np.float32))
    events: List[Dict] = field(default_factory=list)


STATE = SharedState()


# ============================================================
# DEFAULT ASSETS
# ============================================================
def _safe_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def generate_placeholder_image(path: str, title: str, accent: Tuple[int, int, int]) -> None:
    if os.path.exists(path):
        return
    img = Image.new("RGB", (900, 700), (18, 22, 30))
    draw = ImageDraw.Draw(img)
    font_big = _safe_font(56)
    font_mid = _safe_font(32)
    font_small = _safe_font(24)

    for y in range(700):
        alpha = y / 699.0
        c = tuple(int((1 - alpha) * 25 + alpha * accent[i]) for i in range(3))
        draw.line([(0, y), (900, y)], fill=c)

    draw.rounded_rectangle((40, 40, 860, 660), radius=28, outline=(245, 245, 245), width=5)
    draw.text((80, 110), title, font=font_big, fill=(255, 255, 255))
    draw.text((80, 240), "Experiência imersiva com olhar", font=font_mid, fill=(235, 235, 235))
    draw.text((80, 310), "Quadro placeholder gerado automaticamente", font=font_small, fill=(220, 220, 220))
    for i in range(5):
        x0 = 120 + i * 120
        draw.ellipse((x0, 500, x0 + 60, 560), outline=(255, 255, 255), width=4)
    img.save(path, quality=95)


DEFAULT_PAINTINGS = [
    {
        "pid": "q1",
        "title": "Memória da Luz",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Composição abstrata com foco em luz, presença e permanência do olhar.",
        "wall": "front",
        "center": (-2.0, 1.5, ROOM_DEPTH),
        "size": (1.9, 1.35),
        "image_path": os.path.join(ASSETS_DIR, "quadro_01.jpg"),
        "accent": (92, 145, 220),
    },
    {
        "pid": "q2",
        "title": "Pulso Urbano",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Leitura visual sobre ritmo, contraste e densidade da cidade contemporânea.",
        "wall": "front",
        "center": (2.0, 1.5, ROOM_DEPTH),
        "size": (1.9, 1.35),
        "image_path": os.path.join(ASSETS_DIR, "quadro_02.jpg"),
        "accent": (200, 70, 70),
    },
    {
        "pid": "q3",
        "title": "Horizonte Sintético",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Paisagem híbrida entre natureza e geometria calculada.",
        "wall": "left",
        "center": (-ROOM_HALF_WIDTH, 1.5, 6.6),
        "size": (1.7, 1.2),
        "image_path": os.path.join(ASSETS_DIR, "quadro_03.jpg"),
        "accent": (65, 180, 140),
    },
    {
        "pid": "q4",
        "title": "Arquivo do Silêncio",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Camadas escuras e detalhes mínimos para observação prolongada.",
        "wall": "left",
        "center": (-ROOM_HALF_WIDTH, 1.5, 3.8),
        "size": (1.7, 1.2),
        "image_path": os.path.join(ASSETS_DIR, "quadro_04.jpg"),
        "accent": (100, 100, 120),
    },
    {
        "pid": "q5",
        "title": "Campo de Ecos",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Exploração de repetição, profundidade e vibração cromática.",
        "wall": "right",
        "center": (ROOM_HALF_WIDTH, 1.5, 6.6),
        "size": (1.7, 1.2),
        "image_path": os.path.join(ASSETS_DIR, "quadro_05.jpg"),
        "accent": (215, 160, 75),
    },
    {
        "pid": "q6",
        "title": "Dobra do Tempo",
        "artist": "Coleção Demo",
        "year": "2026",
        "description": "Plano visual que sugere deslocamento temporal e mudança de foco.",
        "wall": "right",
        "center": (ROOM_HALF_WIDTH, 1.5, 3.8),
        "size": (1.7, 1.2),
        "image_path": os.path.join(ASSETS_DIR, "quadro_06.jpg"),
        "accent": (160, 95, 195),
    },
]


def ensure_default_assets() -> List[Painting]:
    paintings: List[Painting] = []
    for item in DEFAULT_PAINTINGS:
        generate_placeholder_image(item["image_path"], item["title"], item["accent"])
        paintings.append(
            Painting(
                pid=item["pid"],
                title=item["title"],
                artist=item["artist"],
                year=item["year"],
                description=item["description"],
                wall=item["wall"],
                center=item["center"],
                size=item["size"],
                image_path=item["image_path"],
            )
        )
    return paintings


PAINTINGS = ensure_default_assets()
PAINTING_BY_ID = {p.pid: p for p in PAINTINGS}
TEXTURE_CACHE: Dict[str, np.ndarray] = {}

RUNTIME_CONFIG = {
    "eye_side": "right",
    "dwell_seconds": 1.1,
    "blink_threshold": 0.17,
    "smoothing_alpha": 0.22,
}


# ============================================================
# TRACKER UTILS (adaptados do código enviado)
# ============================================================
def crop_to_aspect_ratio(image: np.ndarray, width: int = 640, height: int = 480) -> np.ndarray:
    current_height, current_width = image.shape[:2]
    desired_ratio = width / height
    current_ratio = current_width / current_height

    if current_ratio > desired_ratio:
        new_width = int(desired_ratio * current_height)
        offset = (current_width - new_width) // 2
        cropped_img = image[:, offset:offset + new_width]
    else:
        new_height = int(current_width / desired_ratio)
        offset = (current_height - new_height) // 2
        cropped_img = image[offset:offset + new_height, :]

    return cv2.resize(cropped_img, (width, height))


def apply_binary_threshold(image: np.ndarray, darkest_pixel_value: int, added_threshold: int) -> np.ndarray:
    threshold = darkest_pixel_value + added_threshold
    _, thresholded = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    return thresholded


def get_darkest_area(image: np.ndarray) -> Tuple[int, int]:
    ignore_bounds = 8
    image_skip = 6
    search_area = 18
    internal_skip = 3

    min_sum = float("inf")
    darkest_point = (image.shape[1] // 2, image.shape[0] // 2)

    for y in range(ignore_bounds, image.shape[0] - ignore_bounds, image_skip):
        for x in range(ignore_bounds, image.shape[1] - ignore_bounds, image_skip):
            current_sum = 0
            count = 0
            for dy in range(0, search_area, internal_skip):
                for dx in range(0, search_area, internal_skip):
                    yy = min(image.shape[0] - 1, y + dy)
                    xx = min(image.shape[1] - 1, x + dx)
                    current_sum += int(image[yy, xx])
                    count += 1
            if count and current_sum < min_sum:
                min_sum = current_sum
                darkest_point = (x + search_area // 2, y + search_area // 2)
    return darkest_point


def mask_outside_square(image: np.ndarray, center: Tuple[int, int], size: int) -> np.ndarray:
    x, y = center
    half = size // 2
    mask = np.zeros_like(image)
    x1 = max(0, x - half)
    y1 = max(0, y - half)
    x2 = min(image.shape[1], x + half)
    y2 = min(image.shape[0], y + half)
    mask[y1:y2, x1:x2] = 255
    return cv2.bitwise_and(image, mask)


def filter_contours_by_area_and_return_largest(contours, pixel_thresh: int, ratio_thresh: float):
    max_area = 0
    largest = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= pixel_thresh:
            x, y, w, h = cv2.boundingRect(contour)
            if w == 0 or h == 0:
                continue
            ratio = max(w / h, h / w)
            if ratio <= ratio_thresh and area > max_area:
                max_area = area
                largest = contour
    return [largest] if largest is not None else []


def check_contour_pixels(contour, image_shape) -> Tuple[int, float, np.ndarray]:
    if len(contour) < 5:
        return (0, 0.0, np.zeros(image_shape, dtype=np.uint8))

    contour_mask = np.zeros(image_shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, 255, 1)
    ellipse = cv2.fitEllipse(contour)
    ellipse_mask_thick = np.zeros(image_shape, dtype=np.uint8)
    ellipse_mask_thin = np.zeros(image_shape, dtype=np.uint8)
    cv2.ellipse(ellipse_mask_thick, ellipse, 255, 8)
    cv2.ellipse(ellipse_mask_thin, ellipse, 255, 3)
    overlap_thick = cv2.bitwise_and(contour_mask, ellipse_mask_thick)
    overlap_thin = cv2.bitwise_and(contour_mask, ellipse_mask_thin)
    absolute_total_thick = int(np.sum(overlap_thick > 0))
    absolute_total_thin = int(np.sum(overlap_thin > 0))
    border_total = int(np.sum(contour_mask > 0))
    ratio = absolute_total_thin / border_total if border_total > 0 else 0.0
    return absolute_total_thick, ratio, overlap_thin


def check_ellipse_goodness(binary_image: np.ndarray, contour) -> Tuple[float, float, float]:
    goodness = [0.0, 0.0, 0.0]
    if contour is None or len(contour) < 5:
        return tuple(goodness)
    ellipse = cv2.fitEllipse(contour)
    mask = np.zeros_like(binary_image)
    cv2.ellipse(mask, ellipse, 255, -1)
    ellipse_area = int(np.sum(mask == 255))
    if ellipse_area <= 0:
        return tuple(goodness)
    covered_pixels = int(np.sum((binary_image == 255) & (mask == 255)))
    goodness[0] = covered_pixels / ellipse_area
    a, b = ellipse[1]
    if a > 0 and b > 0:
        goodness[2] = min(a / b, b / a)
    return tuple(goodness)


def detect_pupil_ellipse(eye_bgr: np.ndarray) -> Tuple[Optional[Tuple], Dict]:
    eye_gray = cv2.cvtColor(eye_bgr, cv2.COLOR_BGR2GRAY)
    eye_gray = cv2.GaussianBlur(eye_gray, (5, 5), 0)
    darkest_point = get_darkest_area(eye_gray)
    darkest_pixel = int(eye_gray[darkest_point[1], darkest_point[0]])

    binary_images = [
        mask_outside_square(apply_binary_threshold(eye_gray, darkest_pixel, 5), darkest_point, min(eye_gray.shape) - 4),
        mask_outside_square(apply_binary_threshold(eye_gray, darkest_pixel, 12), darkest_point, min(eye_gray.shape) - 4),
        mask_outside_square(apply_binary_threshold(eye_gray, darkest_pixel, 20), darkest_point, min(eye_gray.shape) - 4),
    ]

    best = None
    best_score = -1.0
    best_bin = None
    for binary in binary_images:
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(binary, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        reduced = filter_contours_by_area_and_return_largest(contours, 30, 4.0)
        if not reduced:
            continue
        contour = reduced[0]
        if contour is None or len(contour) < 5:
            continue
        cov, ratio, _ = check_contour_pixels(contour, dilated.shape)
        ellipse_goodness = check_ellipse_goodness(dilated, contour)
        score = ellipse_goodness[0] * max(1.0, cov) * max(0.2, ratio)
        if score > best_score:
            best_score = score
            best = cv2.fitEllipse(contour)
            best_bin = dilated

    debug = {
        "darkest_point": darkest_point,
        "darkest_pixel": darkest_pixel,
        "quality": float(max(0.0, best_score)),
        "threshold": best_bin,
    }
    return best, debug


# ============================================================
# FACE / EYE MESH
# ============================================================
def lm_to_px(landmark, width: int, height: int) -> Tuple[int, int]:
    return int(landmark.x * width), int(landmark.y * height)


def compute_eye_crop(frame_bgr: np.ndarray, landmarks, indices: List[int], pad: int = 14):
    h, w = frame_bgr.shape[:2]
    points = np.array([lm_to_px(landmarks[i], w, h) for i in indices], dtype=np.int32)
    x, y, ww, hh = cv2.boundingRect(points)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(w, x + ww + pad)
    y2 = min(h, y + hh + pad)
    crop = frame_bgr[y1:y2, x1:x2].copy()
    return crop, (x1, y1, x2, y2), points


def distance(p1, p2) -> float:
    return float(np.linalg.norm(np.array(p1, dtype=np.float32) - np.array(p2, dtype=np.float32)))


def compute_ear(landmarks, side: str, width: int, height: int) -> float:
    if side == "right":
        pts = {idx: lm_to_px(landmarks[idx], width, height) for idx in [33, 133, 159, 145, 158, 153]}
        horiz = distance(pts[33], pts[133])
        v1 = distance(pts[159], pts[145])
        v2 = distance(pts[158], pts[153])
    else:
        pts = {idx: lm_to_px(landmarks[idx], width, height) for idx in [362, 263, 386, 374, 385, 380]}
        horiz = distance(pts[362], pts[263])
        v1 = distance(pts[386], pts[374])
        v2 = distance(pts[385], pts[380])
    if horiz <= 1e-6:
        return 0.0
    return (v1 + v2) / (2.0 * horiz)


# ============================================================
# GALLERY 3D
# ============================================================
def load_texture(path: str) -> np.ndarray:
    if path not in TEXTURE_CACHE:
        img = cv2.imread(path)
        if img is None:
            img = np.full((700, 900, 3), 120, dtype=np.uint8)
        TEXTURE_CACHE[path] = img
    return TEXTURE_CACHE[path]


def project_point(point: np.ndarray, cam_pos: np.ndarray, focal: float, canvas_w: int, canvas_h: int):
    rel = point - cam_pos
    z = rel[2]
    if z <= 0.05:
        return None
    x = rel[0] / z
    y = rel[1] / z
    u = int(canvas_w / 2 + focal * x)
    v = int(canvas_h / 2 - focal * y)
    return (u, v)


def quad_from_painting(painting: Painting, cam_pos: np.ndarray, focal: float):
    cx, cy, cz = painting.center
    w2 = painting.size[0] / 2.0
    h2 = painting.size[1] / 2.0

    if painting.wall == "front":
        corners = [
            np.array([cx - w2, cy + h2, cz], dtype=np.float32),
            np.array([cx + w2, cy + h2, cz], dtype=np.float32),
            np.array([cx + w2, cy - h2, cz], dtype=np.float32),
            np.array([cx - w2, cy - h2, cz], dtype=np.float32),
        ]
    elif painting.wall == "left":
        corners = [
            np.array([cx, cy + h2, cz - w2], dtype=np.float32),
            np.array([cx, cy + h2, cz + w2], dtype=np.float32),
            np.array([cx, cy - h2, cz + w2], dtype=np.float32),
            np.array([cx, cy - h2, cz - w2], dtype=np.float32),
        ]
    else:  # right
        corners = [
            np.array([cx, cy + h2, cz + w2], dtype=np.float32),
            np.array([cx, cy + h2, cz - w2], dtype=np.float32),
            np.array([cx, cy - h2, cz - w2], dtype=np.float32),
            np.array([cx, cy - h2, cz + w2], dtype=np.float32),
        ]

    proj = [project_point(c, cam_pos, focal, CANVAS_W, CANVAS_H) for c in corners]
    if any(p is None for p in proj):
        return None
    return np.array(proj, dtype=np.float32)


def render_textured_quad(canvas: np.ndarray, texture: np.ndarray, quad: np.ndarray, alpha: float = 1.0):
    src_h, src_w = texture.shape[:2]
    src = np.array([[0, 0], [src_w - 1, 0], [src_w - 1, src_h - 1], [0, src_h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, quad.astype(np.float32))
    warped = cv2.warpPerspective(texture, M, (canvas.shape[1], canvas.shape[0]))
    mask = np.zeros((canvas.shape[0], canvas.shape[1]), dtype=np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    if alpha >= 0.999:
        canvas[mask == 255] = warped[mask == 255]
    else:
        blended = cv2.addWeighted(canvas, 1 - alpha, warped, alpha, 0)
        canvas[mask == 255] = blended[mask == 255]


def draw_room(canvas: np.ndarray, cam_pos: np.ndarray, focal: float):
    floor = [
        np.array([-ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
    ]
    ceiling = [
        np.array([-ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
    ]
    left = [
        np.array([-ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
    ]
    right = [
        np.array([ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, 1.0], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
    ]
    back = [
        np.array([-ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
        np.array([-ROOM_HALF_WIDTH, -ROOM_HALF_HEIGHT, ROOM_DEPTH], dtype=np.float32),
    ]

    planes = [
        (floor, (60, 58, 56)),
        (ceiling, (38, 40, 46)),
        (left, (54, 56, 66)),
        (right, (54, 56, 66)),
        (back, (46, 48, 54)),
    ]

    for pts3d, color in planes:
        pts2d = [project_point(p, cam_pos, focal, CANVAS_W, CANVAS_H) for p in pts3d]
        if any(p is None for p in pts2d):
            continue
        poly = np.array(pts2d, dtype=np.int32)
        cv2.fillConvexPoly(canvas, poly, color)
        cv2.polylines(canvas, [poly], True, (90, 90, 96), 2, cv2.LINE_AA)


def gaze_ray_from_norm(gaze_norm: Tuple[float, float]) -> Tuple[np.ndarray, np.ndarray]:
    x, y = gaze_norm
    direction = np.array([x, y, 1.0], dtype=np.float32)
    direction /= max(1e-6, np.linalg.norm(direction))
    origin = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    return origin, direction


def intersect_wall(origin: np.ndarray, direction: np.ndarray, wall: str):
    eps = 1e-6
    if wall == "front":
        if abs(direction[2]) < eps:
            return None
        t = ROOM_DEPTH / direction[2]
        if t <= 0:
            return None
        p = origin + t * direction
        if -ROOM_HALF_WIDTH <= p[0] <= ROOM_HALF_WIDTH and -ROOM_HALF_HEIGHT <= p[1] <= ROOM_HALF_HEIGHT:
            return p
    elif wall == "left":
        if abs(direction[0]) < eps:
            return None
        t = (-ROOM_HALF_WIDTH) / direction[0]
        if t <= 0:
            return None
        p = origin + t * direction
        if 0.5 <= p[2] <= ROOM_DEPTH and -ROOM_HALF_HEIGHT <= p[1] <= ROOM_HALF_HEIGHT:
            return p
    elif wall == "right":
        if abs(direction[0]) < eps:
            return None
        t = (ROOM_HALF_WIDTH) / direction[0]
        if t <= 0:
            return None
        p = origin + t * direction
        if 0.5 <= p[2] <= ROOM_DEPTH and -ROOM_HALF_HEIGHT <= p[1] <= ROOM_HALF_HEIGHT:
            return p
    return None


def painting_hit_test(gaze_norm: Tuple[float, float]) -> Optional[str]:
    origin, direction = gaze_ray_from_norm(gaze_norm)
    candidates = []
    for wall in ["front", "left", "right"]:
        hit = intersect_wall(origin, direction, wall)
        if hit is None:
            continue
        candidates.append((np.linalg.norm(hit - origin), wall, hit))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    _, wall, hit = candidates[0]

    for painting in PAINTINGS:
        if painting.wall != wall:
            continue
        cx, cy, cz = painting.center
        w, h = painting.size
        if wall == "front":
            if abs(hit[0] - cx) <= w / 2 and abs(hit[1] - cy) <= h / 2:
                return painting.pid
        elif wall in ("left", "right"):
            if abs(hit[2] - cz) <= w / 2 and abs(hit[1] - cy) <= h / 2:
                return painting.pid
    return None


def render_gallery(gaze_norm: Tuple[float, float], hovered_pid: Optional[str], selected_pid: Optional[str], zoom_level: float):
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    canvas[:] = (18, 19, 24)
    cam_z = -5.4 + (zoom_level - 1.0) * 1.8
    cam_pos = np.array([0.0, 0.0, cam_z], dtype=np.float32)
    focal = DEFAULT_FOCAL * (0.98 + 0.18 * (zoom_level - 1.0))

    draw_room(canvas, cam_pos, focal)

    quads = []
    for p in PAINTINGS:
        quad = quad_from_painting(p, cam_pos, focal)
        if quad is None:
            continue
        center3d = np.array(p.center, dtype=np.float32)
        depth = float(np.linalg.norm(center3d - cam_pos))
        quads.append((depth, p, quad))

    quads.sort(key=lambda x: x[0], reverse=True)

    for _, painting, quad in quads:
        texture = load_texture(painting.image_path)
        alpha = 1.0
        render_textured_quad(canvas, texture, quad, alpha=alpha)
        border_color = (220, 220, 220)
        thickness = 2
        if painting.pid == hovered_pid:
            border_color = (80, 255, 180)
            thickness = 4
        if painting.pid == selected_pid:
            border_color = (40, 220, 255)
            thickness = 6
        cv2.polylines(canvas, [quad.astype(np.int32)], True, border_color, thickness, cv2.LINE_AA)

    gx = int((gaze_norm[0] * 0.5 + 0.5) * (CANVAS_W - 1))
    gy = int((-gaze_norm[1] * 0.5 + 0.5) * (CANVAS_H - 1))
    gx = int(np.clip(gx, 0, CANVAS_W - 1))
    gy = int(np.clip(gy, 0, CANVAS_H - 1))

    cv2.circle(canvas, (gx, gy), 18, (40, 220, 255), 2, cv2.LINE_AA)
    cv2.circle(canvas, (gx, gy), 3, (255, 255, 255), -1, cv2.LINE_AA)

    title = "Sala 3D por rastreamento ocular"
    cv2.putText(canvas, title, (24, 34), FONT, 0.9, (245, 245, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "2 piscadas = zoom | 1 piscada = afastar | Fixe o olhar no quadro para abrir infos", (24, 62), FONT, 0.55, (220, 220, 220), 1, cv2.LINE_AA)

    if selected_pid and selected_pid in PAINTING_BY_ID:
        p = PAINTING_BY_ID[selected_pid]
        panel = canvas.copy()
        cv2.rectangle(panel, (20, CANVAS_H - 148), (CANVAS_W - 20, CANVAS_H - 20), (8, 10, 15), -1)
        cv2.addWeighted(panel, 0.35, canvas, 0.65, 0, canvas)
        cv2.rectangle(canvas, (20, CANVAS_H - 148), (CANVAS_W - 20, CANVAS_H - 20), (70, 92, 130), 2)
        cv2.putText(canvas, f"{p.title} | {p.artist} | {p.year}", (38, CANVAS_H - 112), FONT, 0.78, (255, 255, 255), 2, cv2.LINE_AA)
        lines = wrap_text(p.description, 78)
        yy = CANVAS_H - 84
        for line in lines[:3]:
            cv2.putText(canvas, line, (38, yy), FONT, 0.58, (228, 228, 228), 1, cv2.LINE_AA)
            yy += 26

    return canvas, (gx, gy)


# ============================================================
# LOGIC
# ============================================================
def wrap_text(text: str, max_chars: int) -> List[str]:
    words = text.split()
    lines = []
    line = []
    count = 0
    for word in words:
        extra = len(word) + (1 if line else 0)
        if count + extra > max_chars:
            lines.append(" ".join(line))
            line = [word]
            count = len(word)
        else:
            line.append(word)
            count += extra
    if line:
        lines.append(" ".join(line))
    return lines


def smooth_point(prev: Optional[Tuple[float, float]], new: Tuple[float, float], alpha: float = 0.22):
    if prev is None:
        return new
    return ((1 - alpha) * prev[0] + alpha * new[0], (1 - alpha) * prev[1] + alpha * new[1])


def pupil_to_gaze_norm(pupil_roi: Tuple[float, float], roi_shape: Tuple[int, int], calibration_center: Optional[Tuple[float, float]]):
    w, h = roi_shape
    px, py = pupil_roi
    if calibration_center is None:
        cx, cy = w / 2.0, h / 2.0
    else:
        cx, cy = calibration_center
    dx = (px - cx) / max(1.0, w * 0.35)
    dy = (py - cy) / max(1.0, h * 0.35)
    gx = float(np.clip(dx * 1.4, -1.15, 1.15))
    gy = float(np.clip(-dy * 1.2, -1.0, 1.0))
    return gx, gy


def update_fixation_and_selection(shared: SharedState, hovered_pid: Optional[str], dwell_seconds: float, now_ts: float):
    if hovered_pid != shared.fixating_pid:
        shared.fixating_pid = hovered_pid
        shared.fixation_started_at = now_ts
        return
    if hovered_pid and (now_ts - shared.fixation_started_at) >= dwell_seconds:
        if shared.selected_pid != hovered_pid:
            shared.selected_pid = hovered_pid
            p = PAINTING_BY_ID[hovered_pid]
            shared.events.append(
                {
                    "timestamp": now_ts,
                    "event": "select_painting",
                    "painting_id": p.pid,
                    "painting_title": p.title,
                    "zoom_level": round(shared.zoom_level, 3),
                }
            )


def register_blink(shared: SharedState, now_ts: float):
    if shared.blink_pending_at is None:
        shared.blink_pending_at = now_ts
    else:
        if now_ts - shared.blink_pending_at <= 0.65:
            shared.zoom_level = min(2.2, shared.zoom_level + 0.22)
            shared.events.append(
                {"timestamp": now_ts, "event": "double_blink_zoom_in", "zoom_level": round(shared.zoom_level, 3)}
            )
            shared.latest_status = "Zoom aproximado por 2 piscadas"
            shared.blink_pending_at = None
        else:
            shared.blink_pending_at = now_ts


def resolve_single_blink(shared: SharedState, now_ts: float):
    if shared.blink_pending_at is None:
        return
    if now_ts - shared.blink_pending_at > 0.65:
        shared.zoom_level = max(1.0, shared.zoom_level - 0.18)
        shared.events.append(
            {"timestamp": now_ts, "event": "single_blink_zoom_out", "zoom_level": round(shared.zoom_level, 3)}
        )
        shared.latest_status = "Zoom afastado por 1 piscada"
        shared.blink_pending_at = None


def draw_eye_debug(frame: np.ndarray, bbox: Tuple[int, int, int, int], ellipse, pupil_global: Tuple[int, int], quality: float, ear: float, side: str):
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), (90, 160, 255), 2)
    if ellipse is not None:
        ellipse_center = (int(ellipse[0][0] + x1), int(ellipse[0][1] + y1))
        ellipse_axes = (ellipse[1][0], ellipse[1][1])
        ellipse_angle = ellipse[2]
        cv2.ellipse(frame, (ellipse_center, ellipse_axes, ellipse_angle), (0, 255, 120), 2)
    cv2.circle(frame, pupil_global, 4, (255, 255, 255), -1)
    cv2.putText(frame, f"Olho: {side}", (12, 28), FONT, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, f"Qualidade: {quality:.2f}", (12, 54), FONT, 0.65, (0, 255, 120), 2, cv2.LINE_AA)
    cv2.putText(frame, f"EAR/piscada: {ear:.3f}", (12, 80), FONT, 0.65, (240, 220, 90), 2, cv2.LINE_AA)


# ============================================================
# REPORT EXPORT
# ============================================================
def heatmap_to_png_bytes(heatmap: np.ndarray) -> bytes:
    fig = plt.figure(figsize=(11, 6), dpi=150)
    ax = fig.add_subplot(111)
    ax.set_title("Mapa de calor do olhar na sala", fontsize=14)
    ax.imshow(np.zeros((heatmap.shape[0], heatmap.shape[1], 3), dtype=np.uint8) + 15)
    ax.imshow(heatmap, cmap="inferno", alpha=0.88)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def export_csv_and_pdf(shared: SharedState) -> Tuple[str, str]:
    ts = time.strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(EXPORT_DIR, f"gaze_events_{ts}.csv")
    pdf_path = os.path.join(REPORT_DIR, f"relatorio_heatmap_{ts}.pdf")

    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("timestamp,event,painting_id,painting_title,zoom_level,gaze_x,gaze_y,tracking_quality\n")
        for ev in shared.events:
            f.write(
                f"{ev.get('timestamp','')},{ev.get('event','')},{ev.get('painting_id','')},{ev.get('painting_title','')},"
                f"{ev.get('zoom_level','')},{ev.get('gaze_x','')},{ev.get('gaze_y','')},{ev.get('tracking_quality','')}\n"
            )

    heatmap_png = heatmap_to_png_bytes(shared.heatmap)
    packet = io.BytesIO(heatmap_png)
    pdf = pdf_canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, height - 50, "Relatório de rastreamento ocular")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, height - 76, f"Sessão: {shared.session_id}")
    pdf.drawString(40, height - 94, f"Eventos registrados: {len(shared.events)}")
    pdf.drawString(40, height - 112, f"Zoom final: {shared.zoom_level:.2f}")
    selected_name = PAINTING_BY_ID[shared.selected_pid].title if shared.selected_pid in PAINTING_BY_ID else "Nenhum"
    pdf.drawString(40, height - 130, f"Último quadro selecionado: {selected_name}")

    img = ImageReader(packet)
    pdf.drawImage(img, 40, 180, width=width - 80, height=320, preserveAspectRatio=True, mask="auto")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, 156, "Resumo")
    pdf.setFont("Helvetica", 10)
    summary_lines = [
        "O mapa de calor mostra as regiões mais observadas na sala virtual.",
        "Eventos de piscada simples reduzem o zoom; piscadas duplas aumentam o zoom.",
        "A seleção do quadro acontece por fixação do olhar por tempo suficiente.",
    ]
    yy = 138
    for line in summary_lines:
        pdf.drawString(40, yy, line)
        yy -= 16

    pdf.showPage()
    pdf.save()
    return csv_path, pdf_path


# ============================================================
# VIDEO PROCESSOR
# ============================================================
class EyeGalleryProcessor(VideoProcessorBase):
    def __init__(self):
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = crop_to_aspect_ratio(img, EYE_DEBUG_W, EYE_DEBUG_H)
        now_ts = time.time()

        side = str(RUNTIME_CONFIG.get("eye_side", "right"))
        dwell_seconds = float(RUNTIME_CONFIG.get("dwell_seconds", 1.1))
        blink_threshold = float(RUNTIME_CONFIG.get("blink_threshold", 0.17))
        smoothing = float(RUNTIME_CONFIG.get("smoothing_alpha", 0.22))

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)
        eye_frame = img.copy()
        gaze_norm = (0.0, 0.0)
        hovered_pid = None
        tracking_quality = 0.0
        status = "Rosto não detectado"

        if result.multi_face_landmarks:
            landmarks = result.multi_face_landmarks[0].landmark
            indices = RIGHT_EYE_POINTS if side == "right" else LEFT_EYE_POINTS
            crop, bbox, _ = compute_eye_crop(img, landmarks, indices)
            if crop.size > 0:
                ellipse, debug = detect_pupil_ellipse(crop)
                tracking_quality = float(debug.get("quality", 0.0))
                ear = compute_ear(landmarks, side, img.shape[1], img.shape[0])
                pupil_local = (crop.shape[1] / 2.0, crop.shape[0] / 2.0)

                if ellipse is not None:
                    pupil_local = (float(ellipse[0][0]), float(ellipse[0][1]))
                    with STATE.lock:
                        STATE.smoothed_pupil = smooth_point(STATE.smoothed_pupil, pupil_local, alpha=smoothing)
                        pupil_smoothed = STATE.smoothed_pupil
                        gaze_norm = pupil_to_gaze_norm(pupil_smoothed, (crop.shape[1], crop.shape[0]), STATE.calibration_center)
                        STATE.smoothed_gaze_norm = gaze_norm
                else:
                    with STATE.lock:
                        gaze_norm = STATE.smoothed_gaze_norm

                pupil_smoothed = STATE.smoothed_pupil or pupil_local
                pupil_global = (int(bbox[0] + pupil_smoothed[0]), int(bbox[1] + pupil_smoothed[1]))
                draw_eye_debug(eye_frame, bbox, ellipse, pupil_global, tracking_quality, ear, side)

                with STATE.lock:
                    if ear < blink_threshold:
                        status = "Piscando"
                        if not STATE.last_blink_state_closed:
                            STATE.eye_closed_started_at = now_ts
                        STATE.last_blink_state_closed = True
                    else:
                        status = "Rastreando olho"
                        if STATE.last_blink_state_closed:
                            duration = now_ts - (STATE.eye_closed_started_at or now_ts)
                            if 0.04 <= duration <= 0.6:
                                register_blink(STATE, now_ts)
                            STATE.eye_closed_started_at = None
                        STATE.last_blink_state_closed = False

                    resolve_single_blink(STATE, now_ts)
                    hovered_pid = painting_hit_test(gaze_norm)
                    STATE.hovered_pid = hovered_pid
                    update_fixation_and_selection(STATE, hovered_pid, dwell_seconds, now_ts)
                    gallery, gallery_pt = render_gallery(gaze_norm, hovered_pid, STATE.selected_pid, STATE.zoom_level)
                    STATE.latest_gallery_frame = gallery.copy()
                    STATE.latest_eye_frame = eye_frame.copy()
                    STATE.latest_gallery_point = gallery_pt
                    STATE.latest_tracking_quality = tracking_quality
                    STATE.latest_status = status
                    gx, gy = gallery_pt
                    cv2.circle(gallery, (gx, gy), 28, (70, 255, 140), 1, cv2.LINE_AA)
                    STATE.heatmap[gy, gx] += 1.0
                    STATE.events.append(
                        {
                            "timestamp": now_ts,
                            "event": "gaze_sample",
                            "painting_id": hovered_pid or "",
                            "painting_title": PAINTING_BY_ID[hovered_pid].title if hovered_pid in PAINTING_BY_ID else "",
                            "zoom_level": round(STATE.zoom_level, 3),
                            "gaze_x": gx,
                            "gaze_y": gy,
                            "tracking_quality": round(tracking_quality, 4),
                        }
                    )

                cv2.putText(eye_frame, f"Gaze norm: ({gaze_norm[0]:+.2f}, {gaze_norm[1]:+.2f})", (12, 108), FONT, 0.64, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.circle(eye_frame, pupil_global, 10, (60, 255, 160), 2, cv2.LINE_AA)
                if hovered_pid and hovered_pid in PAINTING_BY_ID:
                    cv2.putText(eye_frame, f"Alvo: {PAINTING_BY_ID[hovered_pid].title}", (12, 136), FONT, 0.62, (80, 255, 180), 2, cv2.LINE_AA)
            else:
                ear = 0.0
        else:
            with STATE.lock:
                resolve_single_blink(STATE, now_ts)

        with STATE.lock:
            gallery = STATE.latest_gallery_frame if STATE.latest_gallery_frame is not None else np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)

        eye_resized = cv2.resize(eye_frame, (640, 480))
        gallery_resized = cv2.resize(gallery, (960, 540))
        eye_pad = np.full((540, 640, 3), 10, dtype=np.uint8)
        eye_pad[30:510, :, :] = eye_resized
        combined = np.hstack([eye_pad, gallery_resized])
        cv2.putText(combined, "Olho / rastreador", (18, 24), FONT, 0.8, (245, 245, 245), 2, cv2.LINE_AA)
        cv2.putText(combined, f"Status: {status}", (18, 530), FONT, 0.65, (230, 230, 230), 2, cv2.LINE_AA)
        return av.VideoFrame.from_ndarray(combined, format="bgr24")


# ============================================================
# STREAMLIT UI
# ============================================================
def reset_session_state():
    with STATE.lock:
        STATE.selected_pid = None
        STATE.hovered_pid = None
        STATE.fixating_pid = None
        STATE.fixation_started_at = 0.0
        STATE.zoom_level = 1.0
        STATE.blink_pending_at = None
        STATE.last_blink_at = None
        STATE.last_blink_state_closed = False
        STATE.eye_closed_started_at = None
        STATE.calibration_center = None
        STATE.smoothed_pupil = None
        STATE.smoothed_gaze_norm = (0.0, 0.0)
        STATE.latest_gallery_frame = None
        STATE.latest_eye_frame = None
        STATE.latest_gallery_point = None
        STATE.latest_tracking_quality = 0.0
        STATE.latest_status = "Sessão reiniciada"
        STATE.heatmap.fill(0)
        STATE.events.clear()


st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.caption("Versão para Streamlit Cloud: sem Tkinter, sem janelas OpenCV, sem OpenGL externo.")

with st.sidebar:
    st.header("Controles")
    eye_side = st.selectbox("Olho analisado", options=["right", "left"], index=0)
    dwell_seconds = st.slider("Tempo de fixação para abrir info", 0.4, 2.5, 1.1, 0.1)
    blink_threshold = st.slider("Limite de piscada (EAR)", 0.10, 0.35, 0.17, 0.01)
    smoothing_alpha = st.slider("Suavização do olhar", 0.05, 0.6, 0.22, 0.01)
    RUNTIME_CONFIG.update({
        "eye_side": eye_side,
        "dwell_seconds": dwell_seconds,
        "blink_threshold": blink_threshold,
        "smoothing_alpha": smoothing_alpha,
    })

    if st.button("Calibrar centro agora"):
        with STATE.lock:
            if STATE.smoothed_pupil is not None:
                STATE.calibration_center = STATE.smoothed_pupil
                STATE.latest_status = "Centro calibrado com a posição atual da pupila"
            else:
                STATE.latest_status = "Ainda não há pupila detectada para calibrar"

    if st.button("Reiniciar sessão"):
        reset_session_state()

    st.markdown("---")
    st.subheader("Exportação")
    if st.button("Gerar CSV + PDF"):
        with STATE.lock:
            csv_path, pdf_path = export_csv_and_pdf(STATE)
            st.success("Arquivos gerados")
            st.session_state["last_csv_path"] = csv_path
            st.session_state["last_pdf_path"] = pdf_path

    if st.session_state.get("last_csv_path") and os.path.exists(st.session_state["last_csv_path"]):
        with open(st.session_state["last_csv_path"], "rb") as f:
            st.download_button("Baixar CSV", data=f.read(), file_name=os.path.basename(st.session_state["last_csv_path"]))
    if st.session_state.get("last_pdf_path") and os.path.exists(st.session_state["last_pdf_path"]):
        with open(st.session_state["last_pdf_path"], "rb") as f:
            st.download_button("Baixar PDF", data=f.read(), file_name=os.path.basename(st.session_state["last_pdf_path"]))

left, right = st.columns([1.35, 1.0])
with left:
    st.markdown("### Câmera ao vivo")
    webrtc_streamer(
        key="eye-gallery-stream",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=EyeGalleryProcessor,
        async_processing=True,
    )

with right:
    st.markdown("### Estado atual")
    with STATE.lock:
        selected = PAINTING_BY_ID.get(STATE.selected_pid) if STATE.selected_pid else None
        hovered = PAINTING_BY_ID.get(STATE.hovered_pid) if STATE.hovered_pid else None
        st.metric("Status", STATE.latest_status)
        st.metric("Qualidade do rastreio", f"{STATE.latest_tracking_quality:.2f}")
        st.metric("Zoom", f"{STATE.zoom_level:.2f}")
        st.metric("Quadro em foco", hovered.title if hovered else "Nenhum")
        if selected:
            st.success(f"Selecionado: {selected.title}")
            st.write(f"**Artista:** {selected.artist}")
            st.write(f"**Ano:** {selected.year}")
            st.write(selected.description)
            st.image(selected.image_path, caption=selected.title, use_container_width=True)
        else:
            st.info("Olhe fixamente para um quadro para abrir as informações dele.")

st.markdown("### Quadros disponíveis")
cols = st.columns(3)
for idx, painting in enumerate(PAINTINGS):
    with cols[idx % 3]:
        st.image(painting.image_path, caption=f"{painting.title} — {painting.wall}", use_container_width=True)
        st.write(f"**{painting.artist}** · {painting.year}")
        st.write(painting.description)

st.markdown("### Observações")
st.write(
    "Este app usa um rastreador de pupila por região mais escura + threshold + contorno + fitEllipse, "
    "com MediaPipe apenas para localizar o olho de forma robusta. A sala é renderizada em perspectiva dentro do próprio frame, "
    "o que evita Pygame, Tkinter e janelas nativas no Streamlit Cloud."
)
