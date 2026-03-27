import os
import math
import time
import json
import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pygame
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60

EYE_CAMERA_INDEX = 0
CAPTURE_W = 640
CAPTURE_H = 480

# Ajustes de sensibilidade do olhar.
# Se o cursor andar para o lado errado, troque True/False.
INVERT_X = True
INVERT_Y = False
GAZE_GAIN_X = 420.0
GAZE_GAIN_Y = 320.0
SMOOTHING = 0.18

BLINK_MIN_DURATION = 0.045
BLINK_MAX_DURATION = 0.40
DOUBLE_BLINK_WINDOW = 0.45

DWELL_SECONDS_TO_OPEN_INFO = 0.55
REPORT_DIR = "relatorios_gaze"
ASSET_DIR = "quadros"


# ============================================================
# UTILITÁRIOS
# ============================================================
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_vec(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / ((p2y - p1y) + 1e-9) + p1x
                    else:
                        xinters = p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


# ============================================================
# DADOS DA GALERIA
# ============================================================
@dataclass
class Painting:
    pid: str
    title: str
    artist: str
    year: str
    medium: str
    description: str
    wall: str
    center: Tuple[float, float, float]
    size: Tuple[float, float]
    bg_color: Tuple[int, int, int]
    fg_color: Tuple[int, int, int]
    accent_color: Tuple[int, int, int]
    dwell_time: float = 0.0
    gaze_hits: int = 0
    screen_poly: List[Tuple[float, float]] = field(default_factory=list)
    visible: bool = False


def default_paintings() -> List[Painting]:
    return [
        Painting(
            pid="q1",
            title="Memória Suspensa",
            artist="Simulacro Lab",
            year="2026",
            medium="Arte digital generativa",
            description="Composição abstrata pensada para testes de foco visual e permanência do olhar.",
            wall="back",
            center=(-3.3, 0.2, 10.8),
            size=(1.8, 1.35),
            bg_color=(72, 43, 119),
            fg_color=(255, 224, 130),
            accent_color=(255, 92, 141),
        ),
        Painting(
            pid="q2",
            title="Campo de Profundidade",
            artist="Simulacro Lab",
            year="2026",
            medium="Pintura algorítmica",
            description="Estudo de perspectiva, ruído cromático e camadas de profundidade em uma sala virtual.",
            wall="back",
            center=(0.0, 0.15, 10.8),
            size=(2.1, 1.45),
            bg_color=(16, 79, 120),
            fg_color=(250, 247, 200),
            accent_color=(84, 239, 196),
        ),
        Painting(
            pid="q3",
            title="Ruído Museológico",
            artist="Simulacro Lab",
            year="2026",
            medium="Arte computacional",
            description="Painel experimental voltado para navegação ocular e teste de leitura de metadados.",
            wall="back",
            center=(3.4, 0.2, 10.8),
            size=(1.8, 1.35),
            bg_color=(118, 35, 66),
            fg_color=(252, 232, 196),
            accent_color=(255, 181, 71),
        ),
        Painting(
            pid="q4",
            title="Eixo Popular",
            artist="Simulacro Lab",
            year="2026",
            medium="Mixed media digital",
            description="Quadro lateral usado para simular inspeção com aproximação e leitura contextual.",
            wall="left",
            center=(-6.2, 0.0, 7.8),
            size=(1.9, 1.3),
            bg_color=(34, 110, 79),
            fg_color=(255, 239, 181),
            accent_color=(255, 94, 87),
        ),
        Painting(
            pid="q5",
            title="Inventário Fluido",
            artist="Simulacro Lab",
            year="2026",
            medium="Visualização conceitual",
            description="Estrutura visual de catalogação, fluxo e foco aplicada a uma parede lateral.",
            wall="left",
            center=(-6.2, -0.2, 4.5),
            size=(1.7, 1.2),
            bg_color=(73, 63, 125),
            fg_color=(227, 243, 255),
            accent_color=(253, 121, 168),
        ),
        Painting(
            pid="q6",
            title="Camada Espectral",
            artist="Simulacro Lab",
            year="2026",
            medium="Estudo IR/X-Ray imaginado",
            description="Quadro para demonstrar zoom controlado por piscadas e leitura de detalhes no foco.",
            wall="right",
            center=(6.2, 0.0, 7.8),
            size=(1.9, 1.3),
            bg_color=(104, 54, 46),
            fg_color=(255, 241, 220),
            accent_color=(115, 226, 220),
        ),
        Painting(
            pid="q7",
            title="Mapa de Atenção",
            artist="Simulacro Lab",
            year="2026",
            medium="Arte informacional",
            description="Painel lateral final usado para gerar o mapa de calor da sessão ocular.",
            wall="right",
            center=(6.2, -0.15, 4.4),
            size=(1.7, 1.2),
            bg_color=(28, 84, 138),
            fg_color=(246, 244, 211),
            accent_color=(255, 159, 67),
        ),
    ]


# ============================================================
# RASTREADOR OCULAR
# Baseado na lógica do código enviado pelo usuário:
# - busca da região mais escura
# - threshold em múltiplos níveis
# - contorno mais plausível
# - ajuste de elipse da pupila
# - projeção do vetor de olhar para uma tela externa
# ============================================================
class EyeTracker:
    def __init__(self, camera_index: int, screen_size: Tuple[int, int]):
        self.camera_index = camera_index
        self.screen_w, self.screen_h = screen_size
        self.cap = None

        self.smoothed_gaze = np.array([self.screen_w * 0.5, self.screen_h * 0.5], dtype=np.float32)
        self.last_debug_frame: Optional[np.ndarray] = None
        self.last_pupil_center: Optional[Tuple[float, float]] = None
        self.last_quality: float = 0.0
        self.last_axes: Tuple[float, float] = (30.0, 30.0)

        # calibração neutra
        self.calibrating = False
        self.calibration_points: List[Tuple[float, float]] = []
        self.calibration_axes: List[Tuple[float, float]] = []
        self.calibration_target = 25
        self.neutral_center: Optional[np.ndarray] = None
        self.neutral_radius: float = 18.0

        # blink detection
        self.eye_was_closed = False
        self.eye_closed_since: Optional[float] = None
        self.pending_single_blink_at: Optional[float] = None
        self.blink_count = 0
        self.double_blink_count = 0
        self.single_blink_count = 0

        self.backend = cv2.CAP_MSMF if os.name == "nt" else cv2.CAP_ANY

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.camera_index, self.backend)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        if not self.cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir a câmera ocular no índice {self.camera_index}.")

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        try:
            cv2.destroyWindow("Eye Tracker Debug")
        except cv2.error:
            pass

    def start_calibration(self) -> None:
        self.calibrating = True
        self.calibration_points.clear()
        self.calibration_axes.clear()

    @staticmethod
    def crop_to_aspect_ratio(image: np.ndarray, width: int = CAPTURE_W, height: int = CAPTURE_H) -> np.ndarray:
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

    @staticmethod
    def apply_binary_threshold(gray: np.ndarray, darkest_pixel_value: int, added_threshold: int) -> np.ndarray:
        threshold = darkest_pixel_value + added_threshold
        _, thresholded = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        return thresholded

    @staticmethod
    def get_darkest_area(image: np.ndarray) -> Tuple[int, int]:
        ignore_bounds = 20
        image_skip_size = 10
        search_area = 20
        internal_skip_size = 5

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_sum = float("inf")
        darkest_point = (image.shape[1] // 2, image.shape[0] // 2)

        for y in range(ignore_bounds, gray.shape[0] - ignore_bounds, image_skip_size):
            for x in range(ignore_bounds, gray.shape[1] - ignore_bounds, image_skip_size):
                current_sum = 0
                num_pixels = 0
                for dy in range(0, search_area, internal_skip_size):
                    if y + dy >= gray.shape[0]:
                        break
                    for dx in range(0, search_area, internal_skip_size):
                        if x + dx >= gray.shape[1]:
                            break
                        current_sum += int(gray[y + dy, x + dx])
                        num_pixels += 1
                if num_pixels > 0 and current_sum < min_sum:
                    min_sum = current_sum
                    darkest_point = (x + search_area // 2, y + search_area // 2)
        return darkest_point

    @staticmethod
    def mask_outside_square(image: np.ndarray, center: Tuple[int, int], size: int) -> np.ndarray:
        x, y = center
        half = size // 2
        mask = np.zeros_like(image)
        left = max(0, x - half)
        top = max(0, y - half)
        right = min(image.shape[1], x + half)
        bottom = min(image.shape[0], y + half)
        mask[top:bottom, left:right] = 255
        return cv2.bitwise_and(image, mask)

    @staticmethod
    def filter_contours_by_area_and_return_largest(contours: List[np.ndarray], pixel_thresh: int, ratio_thresh: float) -> List[np.ndarray]:
        max_area = 0.0
        largest_contour = None
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < pixel_thresh:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if w == 0 or h == 0:
                continue
            length_to_width_ratio = max(w / h, h / w)
            if length_to_width_ratio <= ratio_thresh and area > max_area:
                max_area = area
                largest_contour = contour
        return [largest_contour] if largest_contour is not None else []

    @staticmethod
    def contour_score(binary_image: np.ndarray, contour: np.ndarray) -> float:
        if contour is None or len(contour) < 5:
            return 0.0
        ellipse = cv2.fitEllipse(contour)
        mask = np.zeros_like(binary_image)
        cv2.ellipse(mask, ellipse, 255, -1)
        ellipse_area = np.sum(mask == 255)
        if ellipse_area == 0:
            return 0.0
        filled = np.sum((binary_image == 255) & (mask == 255)) / ellipse_area
        area = max(cv2.contourArea(contour), 1.0)
        (_, _), (ma, mi), _ = ellipse
        ratio = min(ma, mi) / (max(ma, mi) + 1e-9)
        return float(filled * area * ratio)

    def detect_pupil(self, frame: np.ndarray) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]], float, np.ndarray]:
        frame = self.crop_to_aspect_ratio(frame)
        debug = frame.copy()
        darkest_point = self.get_darkest_area(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        darkest_value = int(gray[darkest_point[1], darkest_point[0]])

        threshold_images = []
        for added in (5, 15, 25):
            thr = self.apply_binary_threshold(gray, darkest_value, added)
            thr = self.mask_outside_square(thr, darkest_point, 250)
            thr = cv2.dilate(thr, np.ones((5, 5), np.uint8), iterations=2)
            threshold_images.append(thr)

        best_contour = None
        best_score = 0.0
        best_thr = None

        for thr in threshold_images:
            contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reduced = self.filter_contours_by_area_and_return_largest(contours, 250, 3.2)
            if reduced and len(reduced[0]) >= 5:
                score = self.contour_score(thr, reduced[0])
                if score > best_score:
                    best_score = score
                    best_contour = reduced[0]
                    best_thr = thr

        cv2.circle(debug, darkest_point, 5, (0, 255, 255), -1)
        cv2.rectangle(
            debug,
            (max(0, darkest_point[0] - 125), max(0, darkest_point[1] - 125)),
            (min(debug.shape[1] - 1, darkest_point[0] + 125), min(debug.shape[0] - 1, darkest_point[1] + 125)),
            (255, 180, 0),
            1,
        )

        if best_contour is None or len(best_contour) < 5:
            cv2.putText(debug, "PUPILA NAO ENCONTRADA", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
            return None, None, 0.0, debug

        ellipse = cv2.fitEllipse(best_contour)
        (cx, cy), (ma, mi), angle = ellipse
        center = (float(cx), float(cy))
        axes = (float(ma), float(mi))

        cv2.ellipse(debug, ellipse, (80, 255, 80), 2)
        cv2.circle(debug, (int(cx), int(cy)), 3, (255, 255, 0), -1)
        cv2.line(debug, (int(cx), int(cy)), darkest_point, (255, 120, 60), 1)

        quality = best_score
        if best_thr is not None:
            small_thr = cv2.cvtColor(cv2.resize(best_thr, (200, 150)), cv2.COLOR_GRAY2BGR)
            debug[10:160, debug.shape[1] - 210:debug.shape[1] - 10] = small_thr
            cv2.putText(debug, "Threshold", (debug.shape[1] - 200, 178), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)

        cv2.putText(debug, f"Centro: ({int(cx)}, {int(cy)})", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        cv2.putText(debug, f"Eixos: {ma:.1f}/{mi:.1f}", (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 230, 120), 2)
        cv2.putText(debug, f"Qualidade: {quality:.1f}", (10, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)

        return center, axes, quality, debug

    def map_gaze_to_screen(self, pupil_center: Tuple[float, float], axes: Tuple[float, float]) -> Tuple[float, float]:
        pupil = np.array(pupil_center, dtype=np.float32)
        avg_radius = max(8.0, float(np.mean(axes)) * 0.25)

        if self.calibrating:
            self.calibration_points.append((float(pupil[0]), float(pupil[1])))
            self.calibration_axes.append((float(axes[0]), float(axes[1])))
            if len(self.calibration_points) >= self.calibration_target:
                self.neutral_center = np.mean(np.array(self.calibration_points, dtype=np.float32), axis=0)
                self.neutral_radius = max(
                    8.0,
                    float(np.mean([np.mean(a) for a in self.calibration_axes])) * 0.25,
                )
                self.calibrating = False

        if self.neutral_center is None:
            return float(self.smoothed_gaze[0]), float(self.smoothed_gaze[1])

        delta = (pupil - self.neutral_center) / max(self.neutral_radius, 1.0)
        dx = -delta[0] if INVERT_X else delta[0]
        dy = -delta[1] if INVERT_Y else delta[1]

        target_x = self.screen_w * 0.5 + dx * GAZE_GAIN_X
        target_y = self.screen_h * 0.5 + dy * GAZE_GAIN_Y
        target_x = clamp(target_x, 0, self.screen_w - 1)
        target_y = clamp(target_y, 0, self.screen_h - 1)

        self.smoothed_gaze[0] = lerp(float(self.smoothed_gaze[0]), float(target_x), SMOOTHING)
        self.smoothed_gaze[1] = lerp(float(self.smoothed_gaze[1]), float(target_y), SMOOTHING)
        return float(self.smoothed_gaze[0]), float(self.smoothed_gaze[1])

    def update_blink_state(self, pupil_found: bool, now: float) -> Optional[str]:
        event = None

        if not pupil_found and not self.eye_was_closed:
            self.eye_was_closed = True
            self.eye_closed_since = now
        elif pupil_found and self.eye_was_closed:
            closed_duration = 0.0 if self.eye_closed_since is None else now - self.eye_closed_since
            self.eye_was_closed = False
            self.eye_closed_since = None
            if BLINK_MIN_DURATION <= closed_duration <= BLINK_MAX_DURATION:
                self.blink_count += 1
                if self.pending_single_blink_at is not None and (now - self.pending_single_blink_at) <= DOUBLE_BLINK_WINDOW:
                    self.pending_single_blink_at = None
                    self.double_blink_count += 1
                    event = "double"
                else:
                    self.pending_single_blink_at = now

        if self.pending_single_blink_at is not None and (now - self.pending_single_blink_at) > DOUBLE_BLINK_WINDOW:
            self.pending_single_blink_at = None
            self.single_blink_count += 1
            event = "single"

        return event

    def process(self) -> Dict[str, object]:
        if self.cap is None:
            raise RuntimeError("Câmera não inicializada.")

        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Falha ao ler frame da câmera ocular.")

        frame = cv2.flip(frame, 1)
        pupil_center, axes, quality, debug = self.detect_pupil(frame)
        now = time.time()

        blink_event = self.update_blink_state(pupil_center is not None, now)
        gaze_point = (float(self.smoothed_gaze[0]), float(self.smoothed_gaze[1]))

        if pupil_center is not None and axes is not None:
            self.last_pupil_center = pupil_center
            self.last_axes = axes
            self.last_quality = quality
            gaze_point = self.map_gaze_to_screen(pupil_center, axes)
            cv2.putText(debug, f"Gaze: ({int(gaze_point[0])}, {int(gaze_point[1])})", (10, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 255, 220), 2)
        else:
            cv2.putText(debug, "Gaze congelado", (10, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 255), 2)

        if self.calibrating:
            msg = f"CALIBRANDO... {len(self.calibration_points)}/{self.calibration_target}"
            cv2.putText(debug, msg, (10, debug.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 220, 0), 2)
        elif self.neutral_center is None:
            cv2.putText(debug, "Pressione C para calibrar olhando para o centro", (10, debug.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
        else:
            cv2.putText(debug, "Calibrado", (10, debug.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

        if blink_event == "double":
            cv2.putText(debug, "DUPLO PISCAR", (260, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 120, 255), 2)
        elif blink_event == "single":
            cv2.putText(debug, "PISCAR SIMPLES", (260, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 180, 0), 2)

        self.last_debug_frame = debug
        return {
            "gaze_point": gaze_point,
            "pupil_found": pupil_center is not None,
            "blink_event": blink_event,
            "debug_frame": debug,
            "quality": quality,
        }


# ============================================================
# GALERIA 3D
# ============================================================
class Gallery3D:
    def __init__(self, screen: pygame.Surface, paintings: List[Painting]):
        self.screen = screen
        self.paintings = paintings
        self.room_width = 14.0
        self.room_height = 5.0
        self.room_depth = 13.0

        self.camera_default = np.array([0.0, 0.2, -1.9], dtype=np.float32)
        self.camera_pos = self.camera_default.copy()
        self.camera_target = self.camera_default.copy()

        self.zoom = 1.0
        self.zoom_target = 1.0
        self.focus_pid: Optional[str] = None
        self.hover_pid: Optional[str] = None
        self.active_info_pid: Optional[str] = None
        self.hover_started_at: Optional[float] = None

        self.font_title = pygame.font.SysFont("arial", 24, bold=True)
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_info = pygame.font.SysFont("arial", 22)
        self.font_hud = pygame.font.SysFont("consolas", 18)

        self.last_frame_rgb = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)

    def get_focal_length(self) -> float:
        return 700.0 * self.zoom

    def get_focus_target(self, painting: Optional[Painting]) -> np.ndarray:
        if painting is None or self.zoom_target <= 1.01:
            return self.camera_default.copy()
        cx, cy, cz = painting.center
        target = np.array([cx * 0.22, cy * 0.18, cz - 4.7], dtype=np.float32)
        target[2] = min(target[2], 6.3)
        return target

    def set_zoom_in(self) -> None:
        self.zoom_target = min(2.6, self.zoom_target + 0.35)
        if self.hover_pid is not None:
            self.focus_pid = self.hover_pid

    def set_zoom_out(self) -> None:
        self.zoom_target = max(1.0, self.zoom_target - 0.35)
        if self.zoom_target <= 1.02:
            self.focus_pid = None

    def update_camera(self, dt: float) -> None:
        self.zoom = lerp(self.zoom, self.zoom_target, min(1.0, dt * 4.5))
        focus_painting = next((p for p in self.paintings if p.pid == self.focus_pid), None)
        self.camera_target = self.get_focus_target(focus_painting)
        self.camera_pos = lerp_vec(self.camera_pos, self.camera_target, min(1.0, dt * 3.2))

    def project_point(self, point: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
        px, py, pz = point
        camx, camy, camz = self.camera_pos
        x = px - camx
        y = py - camy
        z = pz - camz
        if z <= 0.12:
            return None
        f = self.get_focal_length()
        sx = SCREEN_W * 0.5 + (x / z) * f
        sy = SCREEN_H * 0.5 - (y / z) * f
        return sx, sy, z

    def painting_corners(self, painting: Painting) -> List[Tuple[float, float, float]]:
        cx, cy, cz = painting.center
        w, h = painting.size
        hw = w * 0.5
        hh = h * 0.5

        if painting.wall == "back":
            return [
                (cx - hw, cy + hh, cz),
                (cx + hw, cy + hh, cz),
                (cx + hw, cy - hh, cz),
                (cx - hw, cy - hh, cz),
            ]
        if painting.wall == "left":
            x = cx
            return [
                (x, cy + hh, cz - hw),
                (x, cy + hh, cz + hw),
                (x, cy - hh, cz + hw),
                (x, cy - hh, cz - hw),
            ]
        # right
        x = cx
        return [
            (x, cy + hh, cz + hw),
            (x, cy + hh, cz - hw),
            (x, cy - hh, cz - hw),
            (x, cy - hh, cz + hw),
        ]

    def draw_room(self) -> None:
        self.screen.fill((8, 10, 18))

        ceiling = [(-7, 2.4, 1.0), (7, 2.4, 1.0), (7, 2.4, 12.0), (-7, 2.4, 12.0)]
        floor = [(-7, -2.2, 1.0), (7, -2.2, 1.0), (7, -2.2, 12.0), (-7, -2.2, 12.0)]
        left_wall = [(-7, 2.4, 1.0), (-7, 2.4, 12.0), (-7, -2.2, 12.0), (-7, -2.2, 1.0)]
        right_wall = [(7, 2.4, 1.0), (7, 2.4, 12.0), (7, -2.2, 12.0), (7, -2.2, 1.0)]
        back_wall = [(-7, 2.4, 12.0), (7, 2.4, 12.0), (7, -2.2, 12.0), (-7, -2.2, 12.0)]

        self.draw_quad(ceiling, (25, 28, 42))
        self.draw_quad(left_wall, (20, 24, 35))
        self.draw_quad(right_wall, (20, 24, 35))
        self.draw_quad(back_wall, (38, 43, 58))
        self.draw_quad(floor, (14, 15, 20))

        for i in range(-6, 7, 2):
            self.draw_line_3d((i, -2.2, 1.0), (i, -2.2, 12.0), (35, 37, 45), 1)
        for z in np.linspace(1.0, 12.0, 9):
            self.draw_line_3d((-7, -2.2, float(z)), (7, -2.2, float(z)), (30, 32, 40), 1)

        self.draw_line_3d((-7, 2.4, 1.0), (-7, -2.2, 1.0), (62, 66, 82), 2)
        self.draw_line_3d((7, 2.4, 1.0), (7, -2.2, 1.0), (62, 66, 82), 2)
        self.draw_line_3d((-7, 2.4, 12.0), (-7, -2.2, 12.0), (62, 66, 82), 2)
        self.draw_line_3d((7, 2.4, 12.0), (7, -2.2, 12.0), (62, 66, 82), 2)

    def draw_quad(self, points3d: List[Tuple[float, float, float]], color: Tuple[int, int, int]) -> None:
        pts = []
        for p in points3d:
            proj = self.project_point(p)
            if proj is None:
                return
            pts.append((proj[0], proj[1]))
        pygame.draw.polygon(self.screen, color, pts)

    def draw_line_3d(self, p1: Tuple[float, float, float], p2: Tuple[float, float, float], color: Tuple[int, int, int], width: int = 1) -> None:
        a = self.project_point(p1)
        b = self.project_point(p2)
        if a is None or b is None:
            return
        pygame.draw.line(self.screen, color, (a[0], a[1]), (b[0], b[1]), width)

    def draw_paintings(self) -> None:
        painted = []
        for painting in self.paintings:
            corners = self.painting_corners(painting)
            projected = []
            z_acc = 0.0
            ok = True
            for c in corners:
                proj = self.project_point(c)
                if proj is None:
                    ok = False
                    break
                projected.append((proj[0], proj[1]))
                z_acc += proj[2]
            if not ok:
                painting.visible = False
                painting.screen_poly = []
                continue
            painting.visible = True
            painting.screen_poly = projected
            avg_z = z_acc / 4.0
            painted.append((avg_z, painting))

        # desenha do fundo para frente
        painted.sort(key=lambda item: item[0], reverse=True)
        for _, painting in painted:
            self.draw_single_painting(painting)

    def draw_single_painting(self, painting: Painting) -> None:
        poly = painting.screen_poly
        if len(poly) != 4:
            return

        frame_color = tuple(min(255, c + 25) for c in painting.bg_color)
        inner_color = painting.bg_color
        accent_color = painting.accent_color

        pygame.draw.polygon(self.screen, frame_color, poly)
        pygame.draw.polygon(self.screen, (10, 10, 12), poly, 2)

        inner_poly = self.inset_polygon(poly, 8)
        if len(inner_poly) == 4:
            pygame.draw.polygon(self.screen, inner_color, inner_poly)
            self.draw_abstract_art(inner_poly, painting)

        centroid = np.mean(np.array(poly), axis=0)
        title_surf = self.font_small.render(painting.title, True, painting.fg_color)
        rect = title_surf.get_rect(center=(int(centroid[0]), int(centroid[1])))
        self.screen.blit(title_surf, rect)

        if painting.pid == self.hover_pid:
            pygame.draw.polygon(self.screen, accent_color, poly, 4)
        elif painting.pid == self.active_info_pid:
            pygame.draw.polygon(self.screen, (255, 230, 120), poly, 4)

    def draw_abstract_art(self, poly: List[Tuple[float, float]], painting: Painting) -> None:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        minx, maxx = int(min(xs)), int(max(xs))
        miny, maxy = int(min(ys)), int(max(ys))
        w = max(10, maxx - minx)
        h = max(10, maxy - miny)

        clip_rect = pygame.Rect(minx, miny, w, h)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        # ondas / camadas
        for i in range(6):
            color = (
                int((painting.accent_color[0] + i * 18) % 255),
                int((painting.accent_color[1] + i * 9) % 255),
                int((painting.accent_color[2] + i * 15) % 255),
            )
            y = miny + int((i + 1) * h / 7)
            amp = max(4, h // 10)
            pts = []
            for x in range(minx - 20, maxx + 21, 12):
                phase = (x * 0.04) + i * 0.6
                yy = y + int(math.sin(phase) * amp)
                pts.append((x, yy))
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, color, False, pts, 3)

        # formas centrais
        cx = (minx + maxx) // 2
        cy = (miny + maxy) // 2
        pygame.draw.circle(self.screen, painting.fg_color, (cx, cy), max(6, min(w, h) // 7), 2)
        pygame.draw.circle(self.screen, painting.accent_color, (cx + w // 7, cy - h // 10), max(4, min(w, h) // 10), 2)
        pygame.draw.line(self.screen, painting.fg_color, (minx + 10, maxy - 10), (maxx - 10, miny + 10), 2)

        self.screen.set_clip(previous_clip)

    @staticmethod
    def inset_polygon(poly: List[Tuple[float, float]], inset: float) -> List[Tuple[float, float]]:
        arr = np.array(poly, dtype=np.float32)
        center = np.mean(arr, axis=0)
        out = []
        for p in arr:
            v = center - p
            n = np.linalg.norm(v)
            if n < 1e-6:
                out.append(tuple(p))
            else:
                out.append(tuple(p + v / n * inset))
        return out

    def update_hover(self, gaze_point: Tuple[float, float], dt: float, now: float) -> Optional[Painting]:
        hovered: Optional[Painting] = None
        for painting in self.paintings:
            if painting.visible and point_in_polygon(gaze_point, painting.screen_poly):
                hovered = painting
                break

        self.hover_pid = hovered.pid if hovered is not None else None

        if hovered is None:
            self.hover_started_at = None
            return None

        hovered.gaze_hits += 1
        hovered.dwell_time += dt

        if self.active_info_pid == hovered.pid:
            return hovered

        if self.hover_started_at is None or self.active_info_pid != hovered.pid:
            if self.active_info_pid != hovered.pid:
                self.hover_started_at = now

        if self.hover_started_at is not None and (now - self.hover_started_at) >= DWELL_SECONDS_TO_OPEN_INFO:
            self.active_info_pid = hovered.pid
        return hovered

    def draw_hud(self, gaze_point: Tuple[float, float], tracker: EyeTracker, session_seconds: float) -> None:
        gx, gy = int(gaze_point[0]), int(gaze_point[1])
        pygame.draw.circle(self.screen, (255, 120, 120), (gx, gy), 9, 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (gx, gy), 2)

        hud_bg = pygame.Surface((360, 126), pygame.SRCALPHA)
        hud_bg.fill((8, 10, 18, 170))
        self.screen.blit(hud_bg, (14, 14))

        lines = [
            f"Olhar: {gx}, {gy}",
            f"Zoom: {self.zoom:.2f}x",
            f"Piscadas: {tracker.blink_count}  |  Simples: {tracker.single_blink_count}  |  Duplas: {tracker.double_blink_count}",
            f"Sessão: {session_seconds:0.1f}s",
            "C = calibrar  |  R = gerar PDF  |  ESC = sair",
        ]
        for i, text in enumerate(lines):
            surf = self.font_hud.render(text, True, (230, 235, 245))
            self.screen.blit(surf, (28, 26 + i * 22))

        info_text = "Olhe para um quadro para abrir as informações"
        if self.hover_pid:
            info_text = f"Quadro em foco: {self.hover_pid}"
        info_surf = self.font_hud.render(info_text, True, (255, 220, 130))
        self.screen.blit(info_surf, (28, 26 + len(lines) * 22))

    def draw_info_panel(self) -> None:
        if self.active_info_pid is None:
            return
        painting = next((p for p in self.paintings if p.pid == self.active_info_pid), None)
        if painting is None:
            return

        panel = pygame.Surface((450, 220), pygame.SRCALPHA)
        panel.fill((12, 14, 25, 205))
        pygame.draw.rect(panel, painting.accent_color, panel.get_rect(), 3, border_radius=18)
        pygame.draw.rect(panel, (255, 255, 255, 20), pygame.Rect(10, 10, 430, 200), 1, border_radius=16)

        title = self.font_title.render(painting.title, True, (255, 245, 215))
        meta = self.font_info.render(f"{painting.artist}  |  {painting.year}", True, (200, 225, 255))
        medium = self.font_small.render(painting.medium, True, (255, 210, 140))

        panel.blit(title, (22, 18))
        panel.blit(meta, (22, 56))
        panel.blit(medium, (22, 92))

        wrapped = self.wrap_text(painting.description, self.font_small, 398)
        y = 126
        for line in wrapped[:4]:
            surf = self.font_small.render(line, True, (235, 235, 238))
            panel.blit(surf, (22, y))
            y += 24

        stats = self.font_small.render(f"Tempo de observação: {painting.dwell_time:.1f}s", True, (170, 255, 210))
        panel.blit(stats, (22, 188))
        self.screen.blit(panel, (SCREEN_W - 470, 22))

    @staticmethod
    def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            test = word if not current else current + " " + word
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def render(self, gaze_point: Tuple[float, float], tracker: EyeTracker, session_seconds: float) -> None:
        self.draw_room()
        self.draw_paintings()
        self.draw_info_panel()
        self.draw_hud(gaze_point, tracker, session_seconds)
        frame_data = pygame.surfarray.array3d(self.screen)
        self.last_frame_rgb = np.transpose(frame_data, (1, 0, 2)).copy()


# ============================================================
# RELATÓRIO PDF
# ============================================================
class SessionReport:
    def __init__(self):
        self.gaze_points: List[Tuple[float, float, float]] = []
        self.painting_log: List[Dict[str, object]] = []
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.generated_paths: Dict[str, str] = {}

    def add_gaze(self, x: float, y: float, painting_id: Optional[str]) -> None:
        now = time.time()
        self.gaze_points.append((now, x, y))
        self.painting_log.append({"t": now, "painting_id": painting_id})

    def finalize(self) -> None:
        self.end_time = time.time()

    def session_duration(self) -> float:
        end = self.end_time if self.end_time is not None else time.time()
        return max(0.0, end - self.start_time)

    def build_heatmap_png(self, screenshot_rgb: np.ndarray, out_path: str) -> str:
        ensure_dir(os.path.dirname(out_path))
        if not self.gaze_points:
            blank = screenshot_rgb.copy()
            plt.figure(figsize=(12.8, 7.2))
            plt.imshow(blank)
            plt.axis("off")
            plt.tight_layout()
            plt.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0)
            plt.close()
            return out_path

        height, width = screenshot_rgb.shape[:2]
        heat = np.zeros((height, width), dtype=np.float32)

        for _, x, y in self.gaze_points:
            xi = int(clamp(x, 0, width - 1))
            yi = int(clamp(y, 0, height - 1))
            heat[yi, xi] += 1.0

        heat = cv2.GaussianBlur(heat, (0, 0), sigmaX=35, sigmaY=35)
        if float(np.max(heat)) > 0:
            heat = heat / float(np.max(heat))

        plt.figure(figsize=(12.8, 7.2))
        plt.imshow(screenshot_rgb)
        plt.imshow(heat, cmap="jet", alpha=0.52)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0)
        plt.close()
        return out_path

    def build_csv(self, out_path: str) -> str:
        ensure_dir(os.path.dirname(out_path))
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "x", "y"])
            for row in self.gaze_points:
                writer.writerow(row)
        return out_path

    def build_json(self, out_path: str, paintings: List[Painting], tracker: EyeTracker) -> str:
        ensure_dir(os.path.dirname(out_path))
        payload = {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.session_duration(),
            "gaze_samples": len(self.gaze_points),
            "blink_total": tracker.blink_count,
            "single_blinks": tracker.single_blink_count,
            "double_blinks": tracker.double_blink_count,
            "paintings": [
                {
                    "pid": p.pid,
                    "title": p.title,
                    "dwell_time": p.dwell_time,
                    "gaze_hits": p.gaze_hits,
                }
                for p in paintings
            ],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return out_path

    def build_pdf(
        self,
        out_path: str,
        heatmap_path: str,
        paintings: List[Painting],
        tracker: EyeTracker,
    ) -> str:
        ensure_dir(os.path.dirname(out_path))

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        page_w, page_h = A4
        y = page_h - 40

        c.setFont("Helvetica-Bold", 18)
        c.drawString(40, y, "Relatório de mapa de calor ocular - Sala 3D")
        y -= 28

        c.setFont("Helvetica", 11)
        c.drawString(40, y, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        y -= 18
        c.drawString(40, y, f"Duração da sessão: {self.session_duration():.1f} s")
        y -= 18
        c.drawString(40, y, f"Amostras de gaze: {len(self.gaze_points)}")
        y -= 18
        c.drawString(40, y, f"Piscadas totais: {tracker.blink_count} | Simples: {tracker.single_blink_count} | Duplas: {tracker.double_blink_count}")
        y -= 26

        ranking = sorted(paintings, key=lambda p: p.dwell_time, reverse=True)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Quadros mais observados")
        y -= 18
        c.setFont("Helvetica", 10)
        for p in ranking[:5]:
            c.drawString(48, y, f"- {p.title} ({p.pid}) | tempo: {p.dwell_time:.1f}s | hits: {p.gaze_hits}")
            y -= 15
        y -= 8

        img = ImageReader(heatmap_path)
        c.drawImage(img, 40, 180, width=520, height=292, preserveAspectRatio=True, mask='auto')

        c.setFont("Helvetica", 9)
        c.drawString(40, 162, "O mapa de calor mostra as regiões onde o olhar permaneceu por mais tempo dentro da sala 3D.")
        c.drawString(40, 148, "Dupla piscada aproxima o quadro observado; piscada simples afasta a câmera.")

        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, page_h - 40, "Detalhamento dos quadros")
        y = page_h - 72
        c.setFont("Helvetica", 10)
        for p in ranking:
            block = [
                f"{p.pid} - {p.title}",
                f"Artista: {p.artist} | Ano: {p.year} | Técnica: {p.medium}",
                f"Tempo observado: {p.dwell_time:.1f}s | Hits: {p.gaze_hits}",
                f"Descrição: {p.description}",
            ]
            for line in block:
                for wrapped in self.wrap_for_pdf(line, 92):
                    c.drawString(40, y, wrapped)
                    y -= 13
                    if y < 60:
                        c.showPage()
                        c.setFont("Helvetica", 10)
                        y = page_h - 40
            y -= 8

        c.save()
        return out_path

    @staticmethod
    def wrap_for_pdf(text: str, max_chars: int) -> List[str]:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = word if not current else current + " " + word
            if len(test) <= max_chars:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines


# ============================================================
# APP PRINCIPAL
# ============================================================
class EyeGalleryApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sala 3D com Eye Tracking")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.paintings = default_paintings()
        self.gallery = Gallery3D(self.screen, self.paintings)
        self.tracker = EyeTracker(EYE_CAMERA_INDEX, (SCREEN_W, SCREEN_H))
        self.report = SessionReport()
        self.running = True
        self.status_message = "Pressione C para calibrar olhando para o centro da tela"
        self.message_until = time.time() + 6.0

    def set_status(self, text: str, seconds: float = 2.5) -> None:
        self.status_message = text
        self.message_until = time.time() + seconds

    def draw_status_bar(self) -> None:
        if time.time() > self.message_until:
            return
        bar = pygame.Surface((SCREEN_W, 34), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 165))
        self.screen.blit(bar, (0, SCREEN_H - 34))
        surf = pygame.font.SysFont("arial", 20, bold=True).render(self.status_message, True, (255, 245, 190))
        self.screen.blit(surf, (18, SCREEN_H - 28))

    def save_report(self) -> Dict[str, str]:
        ensure_dir(REPORT_DIR)
        self.report.finalize()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(REPORT_DIR, f"sala_{stamp}.png")
        heatmap_path = os.path.join(REPORT_DIR, f"heatmap_{stamp}.png")
        csv_path = os.path.join(REPORT_DIR, f"gaze_{stamp}.csv")
        json_path = os.path.join(REPORT_DIR, f"sessao_{stamp}.json")
        pdf_path = os.path.join(REPORT_DIR, f"relatorio_{stamp}.pdf")

        cv2.imwrite(screenshot_path, cv2.cvtColor(self.gallery.last_frame_rgb, cv2.COLOR_RGB2BGR))
        self.report.build_heatmap_png(self.gallery.last_frame_rgb, heatmap_path)
        self.report.build_csv(csv_path)
        self.report.build_json(json_path, self.paintings, self.tracker)
        self.report.build_pdf(pdf_path, heatmap_path, self.paintings, self.tracker)

        outputs = {
            "screenshot": os.path.abspath(screenshot_path),
            "heatmap": os.path.abspath(heatmap_path),
            "csv": os.path.abspath(csv_path),
            "json": os.path.abspath(json_path),
            "pdf": os.path.abspath(pdf_path),
        }
        self.set_status(f"Relatório salvo em: {outputs['pdf']}", 5.0)
        return outputs

    def run(self) -> None:
        self.tracker.open()
        self.tracker.start_calibration()
        self.set_status("Olhe para o centro da tela durante a calibração", 5.0)

        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                now = time.time()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                            self.running = False
                        elif event.key == pygame.K_c:
                            self.tracker.start_calibration()
                            self.set_status("Calibrando: mantenha o olhar no centro", 3.5)
                        elif event.key == pygame.K_r:
                            outputs = self.save_report()
                            print("Relatório gerado:")
                            for k, v in outputs.items():
                                print(f"  {k}: {v}")

                tracker_state = self.tracker.process()
                gaze_point = tracker_state["gaze_point"]
                blink_event = tracker_state["blink_event"]

                if blink_event == "double":
                    self.gallery.set_zoom_in()
                    self.set_status("Dupla piscada: zoom aproximando", 1.6)
                elif blink_event == "single":
                    self.gallery.set_zoom_out()
                    self.set_status("Piscada simples: zoom afastando", 1.6)

                self.gallery.update_camera(dt)
                hovered = self.gallery.update_hover(gaze_point, dt, now)
                if hovered is not None and self.gallery.active_info_pid == hovered.pid:
                    self.set_status(f"Informações abertas: {hovered.title}", 1.2)

                self.report.add_gaze(gaze_point[0], gaze_point[1], self.gallery.hover_pid)

                session_seconds = time.time() - self.report.start_time
                self.gallery.render(gaze_point, self.tracker, session_seconds)
                self.draw_status_bar()
                pygame.display.flip()

                debug_frame = tracker_state["debug_frame"]
                cv2.imshow("Eye Tracker Debug", debug_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.running = False

        finally:
            outputs = self.save_report()
            print("\nArquivos gerados ao encerrar:")
            for k, v in outputs.items():
                print(f"{k}: {v}")
            self.tracker.close()
            pygame.quit()


if __name__ == "__main__":
    print("Iniciando sala 3D com eye tracking...")
    print("Controles:")
    print("  C   = recalibrar olhando para o centro")
    print("  R   = gerar relatório PDF na hora")
    print("  ESC = sair")
    app = EyeGalleryApp()
    app.run()
