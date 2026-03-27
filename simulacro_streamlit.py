
"""
eye_gallery_3d.py

Sala 3D com quadros interativos guiados por rastreamento ocular.
- Detecção de pupila com elipse semelhante ao código-base enviado
- Sala 3D com quadros clicáveis pelo olhar
- Exibe informações do quadro quando o usuário fixa o olhar
- 2 piscadas rápidas: zoom no quadro
- 1 piscada: afasta o zoom
- Gera relatório em PDF com mapa de calor do olhar
- Salva CSV de eventos de gaze / piscadas / seleções

Autor: OpenAI
"""

from __future__ import annotations

import math
import os
import sys
import time
import csv
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

import cv2
import numpy as np

# Pygame + OpenGL
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, QUIT, KEYDOWN, K_ESCAPE

try:
    from OpenGL.GL import (
        glBegin, glEnd, glVertex3f, glColor3f, glColor4f, glEnable, glDisable,
        glMatrixMode, glLoadIdentity, glTranslatef, glRotatef, glClear, glClearColor,
        glPushMatrix, glPopMatrix, glTexCoord2f, glVertex2f, glViewport,
        glBlendFunc, glGenTextures, glBindTexture, glTexParameteri, glTexImage2D,
        glDeleteTextures, glWindowPos2d, glDrawPixels, GL_QUADS, GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT, GL_PROJECTION, GL_MODELVIEW, GL_DEPTH_TEST, GL_BLEND,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_TEXTURE_2D, GL_LINEAR, GL_RGBA,
        GL_UNSIGNED_BYTE, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER
    )
    from OpenGL.GLU import gluPerspective, gluLookAt
    OPENGL_AVAILABLE = True
except Exception:
    OPENGL_AVAILABLE = False

# Matplotlib / PDF
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

###############################################################################
# CONFIGURAÇÕES
###############################################################################

WINDOW_W = 1400
WINDOW_H = 820

EYE_FRAME_W = 640
EYE_FRAME_H = 480

HEATMAP_W = 1600
HEATMAP_H = 900

SELECTION_HOLD_SECONDS = 1.1
DOUBLE_BLINK_MAX_GAP = 0.65
SINGLE_BLINK_MIN_DURATION = 0.04
SINGLE_BLINK_MAX_DURATION = 0.45
BLINK_EAR_THRESHOLD = 0.20  # fallback se usar face mesh
PUPIL_DARK_THRESHOLD_OFFSET = (5, 15, 25)
USE_MEDIAPIPE_FOR_BLINK = False  # pode ativar se tiver mediapipe

REPORT_DIR = "relatorios"
EXPORT_DIR = "exports"
TEXTURE_DIR = "quadros"

###############################################################################
# UTILIDADES GERAIS
###############################################################################

def ensure_dirs() -> None:
    for path in [REPORT_DIR, EXPORT_DIR, TEXTURE_DIR]:
        os.makedirs(path, exist_ok=True)

def now_str() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def vec_length(v: Tuple[float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2)

###############################################################################
# DADOS DOS QUADROS
###############################################################################

@dataclass
class PaintingInfo:
    title: str
    artist: str
    year: str
    description: str
    file_path: str
    wall: str
    center: Tuple[float, float, float]
    size: Tuple[float, float]
    normal: Tuple[float, float, float]

@dataclass
class GazeEvent:
    timestamp: float
    wall_hit: Optional[str]
    painting_title: Optional[str]
    world_hit: Optional[Tuple[float, float, float]]
    room_uv: Optional[Tuple[float, float]]
    pupil_center: Optional[Tuple[int, int]]
    eye_center: Optional[Tuple[int, int]]
    blink_state: bool
    action: Optional[str] = None

###############################################################################
# PARTE 1 — RASTREAMENTO OCULAR BASEADO NA ELIPSE DO CÓDIGO ENVIADO
###############################################################################

class EyeTrackerEllipse:
    """
    Rastreador ocular usando a mesma ideia do código enviado:
    - busca a área mais escura
    - testa thresholds
    - extrai contorno
    - ajusta elipse na pupila
    - calcula centro do "olho/esfera" com interseção média
    - produz vetor de olhar aproximado
    """

    def __init__(self) -> None:
        self.ray_lines: List[Tuple[Tuple[float, float], Tuple[float, float], float]] = []
        self.model_centers: List[Tuple[int, int]] = []
        self.stored_intersections: List[Tuple[int, int]] = []
        self.max_rays = 100
        self.prev_model_center_avg = (EYE_FRAME_W // 2, EYE_FRAME_H // 2)
        self.max_observed_distance = 180
        self.last_pupil_center: Optional[Tuple[int, int]] = None
        self.last_eye_center: Optional[Tuple[int, int]] = None
        self.last_valid_ellipse = None
        self.last_vector: Optional[np.ndarray] = None
        self.last_world_yaw_pitch = (0.0, 0.0)
        self.calibrated_center = None
        self.center_locked = False
        self.locked_center = self.prev_model_center_avg

        self.blink_closed = False
        self.blink_start_ts = 0.0
        self.last_blink_ts = 0.0
        self.blink_count_window: List[float] = []
        self.double_blink_flag = False
        self.single_blink_flag = False

        self.closed_frame_counter = 0
        self.open_frame_counter = 0

        self.last_debug_frame = None

        self.face_mesh = None
        if USE_MEDIAPIPE_FOR_BLINK:
            try:
                import mediapipe as mp
                self.mp = mp
                self.face_mesh = self.mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
            except Exception:
                self.face_mesh = None

    ###########################################################################
    # Funções adaptadas do código base
    ###########################################################################

    def crop_to_aspect_ratio(self, image: np.ndarray, width: int = EYE_FRAME_W, height: int = EYE_FRAME_H) -> np.ndarray:
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

    def apply_binary_threshold(self, image: np.ndarray, darkest_pixel_value: int, added_threshold: int) -> np.ndarray:
        threshold = int(darkest_pixel_value) + int(added_threshold)
        _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
        return thresholded_image

    def get_darkest_area(self, image: np.ndarray) -> Optional[Tuple[int, int]]:
        ignore_bounds = 20
        image_skip_size = 10
        search_area = 20
        internal_skip_size = 5

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_sum = float("inf")
        darkest_point = None

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
                        current_sum += int(gray[y + dy][x + dx])
                        num_pixels += 1

                if num_pixels > 0 and current_sum < min_sum:
                    min_sum = current_sum
                    darkest_point = (x + search_area // 2, y + search_area // 2)

        return darkest_point

    def mask_outside_square(self, image: np.ndarray, center: Tuple[int, int], size: int) -> np.ndarray:
        x, y = center
        half_size = size // 2

        mask = np.zeros_like(image)
        top_left_x = max(0, x - half_size)
        top_left_y = max(0, y - half_size)
        bottom_right_x = min(image.shape[1], x + half_size)
        bottom_right_y = min(image.shape[0], y + half_size)
        mask[top_left_y:bottom_right_y, top_left_x:bottom_right_x] = 255
        return cv2.bitwise_and(image, mask)

    def filter_contours_by_area_and_return_largest(
        self, contours: List[np.ndarray], pixel_thresh: int, ratio_thresh: float
    ) -> List[np.ndarray]:
        max_area = 0
        largest_contour = None

        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= pixel_thresh:
                x, y, w, h = cv2.boundingRect(contour)
                if h == 0 or w == 0:
                    continue
                length_to_width_ratio = max(w / h, h / w)
                if length_to_width_ratio <= ratio_thresh:
                    if area > max_area:
                        max_area = area
                        largest_contour = contour

        return [largest_contour] if largest_contour is not None else []

    def optimize_contours_by_angle(self, contours: List[np.ndarray], image: np.ndarray) -> np.ndarray:
        if len(contours) < 1 or contours[0] is None:
            return np.array([], dtype=np.int32).reshape((-1, 1, 2))

        all_contours = np.concatenate(contours[0], axis=0)
        if len(all_contours) < 10:
            return contours[0]

        spacing = max(1, int(len(all_contours) / 25))
        filtered_points = []
        centroid = np.mean(all_contours, axis=0)

        for i in range(0, len(all_contours)):
            current_point = all_contours[i]
            prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
            next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

            vec1 = prev_point - current_point
            vec2 = next_point - current_point

            denom = (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            if denom == 0:
                continue

            with np.errstate(invalid="ignore"):
                _angle = np.arccos(np.clip(np.dot(vec1, vec2) / denom, -1.0, 1.0))

            vec_to_centroid = centroid - current_point
            cos_threshold = np.cos(np.radians(60))

            avg_vec = (vec1 + vec2) / 2.0
            if np.linalg.norm(avg_vec) == 0:
                continue

            if np.dot(vec_to_centroid, avg_vec) >= cos_threshold:
                filtered_points.append(current_point)

        if not filtered_points:
            return contours[0]

        return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))

    def check_contour_pixels(self, contour: np.ndarray, image_shape: Tuple[int, int], debug_mode_on: bool = False):
        if contour is None or len(contour) < 5:
            return [0, 0, np.zeros(image_shape, dtype=np.uint8)]

        contour_mask = np.zeros(image_shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, 1)

        ellipse_mask_thick = np.zeros(image_shape, dtype=np.uint8)
        ellipse_mask_thin = np.zeros(image_shape, dtype=np.uint8)

        ellipse = cv2.fitEllipse(contour)
        cv2.ellipse(ellipse_mask_thick, ellipse, 255, 10)
        cv2.ellipse(ellipse_mask_thin, ellipse, 255, 4)

        overlap_thick = cv2.bitwise_and(contour_mask, ellipse_mask_thick)
        overlap_thin = cv2.bitwise_and(contour_mask, ellipse_mask_thin)

        absolute_pixel_total_thick = int(np.sum(overlap_thick > 0))
        absolute_pixel_total_thin = int(np.sum(overlap_thin > 0))
        total_border_pixels = int(np.sum(contour_mask > 0))
        ratio_under_ellipse = absolute_pixel_total_thin / total_border_pixels if total_border_pixels > 0 else 0

        return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]

    def check_ellipse_goodness(self, binary_image: np.ndarray, contour: np.ndarray, debug_mode_on: bool = False):
        ellipse_goodness = [0, 0, 0]
        if contour is None or len(contour) < 5:
            return ellipse_goodness

        ellipse = cv2.fitEllipse(contour)

        mask = np.zeros_like(binary_image)
        cv2.ellipse(mask, ellipse, 255, -1)

        ellipse_area = int(np.sum(mask == 255))
        covered_pixels = int(np.sum((binary_image == 255) & (mask == 255)))

        if ellipse_area == 0:
            return ellipse_goodness

        ellipse_goodness[0] = covered_pixels / ellipse_area
        a0, a1 = ellipse[1]
        if a0 == 0 or a1 == 0:
            ellipse_goodness[2] = 0
        else:
            ellipse_goodness[2] = min(a1 / a0, a0 / a1)
        return ellipse_goodness

    def update_and_average_point(self, point_list: List[Tuple[int, int]], new_point: Tuple[int, int], n: int):
        point_list.append(new_point)
        if len(point_list) > n:
            point_list.pop(0)

        if not point_list:
            return None

        avg_x = int(np.mean([p[0] for p in point_list]))
        avg_y = int(np.mean([p[1] for p in point_list]))
        return (avg_x, avg_y)

    def find_line_intersection(self, ellipse1, ellipse2):
        (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
        (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

        angle1_rad = np.deg2rad(angle1)
        angle2_rad = np.deg2rad(angle2)

        dx1, dy1 = (minor_axis1 / 2) * np.cos(angle1_rad), (minor_axis1 / 2) * np.sin(angle1_rad)
        dx2, dy2 = (minor_axis2 / 2) * np.cos(angle2_rad), (minor_axis2 / 2) * np.sin(angle2_rad)

        A = np.array([[dx1, -dx2], [dy1, -dy2]], dtype=np.float64)
        B = np.array([cx2 - cx1, cy2 - cy1], dtype=np.float64)

        det = np.linalg.det(A)
        if abs(det) < 1e-8:
            return None

        t1, t2 = np.linalg.solve(A, B)
        intersection_x = cx1 + t1 * dx1
        intersection_y = cy1 + t1 * dy1
        return (int(intersection_x), int(intersection_y))

    def prune_intersections(self, intersections: List[Tuple[int, int]], maximum_intersections: int):
        if len(intersections) <= maximum_intersections:
            return intersections
        return intersections[-maximum_intersections:]

    def compute_average_intersection(self, frame: np.ndarray, ray_lines, n: int, m: int, spacing: int):
        if len(ray_lines) < 2 or n < 2:
            return None

        height, width = frame.shape[:2]
        selected_lines = list(ray_lines)[-min(n, len(ray_lines)):]
        intersections = []

        for i in range(len(selected_lines) - 1):
            line1 = selected_lines[i]
            line2 = selected_lines[i + 1]

            angle1 = line1[2]
            angle2 = line2[2]

            if abs(angle1 - angle2) >= 2:
                intersection = self.find_line_intersection(line1, line2)
                if intersection and (0 <= intersection[0] < width) and (0 <= intersection[1] < height):
                    intersections.append(intersection)
                    self.stored_intersections.append(intersection)

        if len(self.stored_intersections) > m:
            self.stored_intersections = self.prune_intersections(self.stored_intersections, m)

        if not self.stored_intersections:
            return None

        avg_x = np.mean([pt[0] for pt in self.stored_intersections])
        avg_y = np.mean([pt[1] for pt in self.stored_intersections])

        return (int(avg_x), int(avg_y))

    ###########################################################################
    # Blink detection
    ###########################################################################

    def _compute_eye_aspect_ratio_mediapipe(self, frame_bgr: np.ndarray) -> Optional[float]:
        if self.face_mesh is None:
            return None

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None

        lm = result.multi_face_landmarks[0].landmark
        h, w = frame_bgr.shape[:2]

        # Right eye approximate points
        idx = {
            "p1": 33, "p4": 133,
            "p2": 160, "p6": 144,
            "p3": 158, "p5": 153,
        }

        pts = {}
        for k, i in idx.items():
            pts[k] = np.array([lm[i].x * w, lm[i].y * h], dtype=np.float32)

        horiz = np.linalg.norm(pts["p1"] - pts["p4"])
        vert1 = np.linalg.norm(pts["p2"] - pts["p6"])
        vert2 = np.linalg.norm(pts["p3"] - pts["p5"])

        if horiz == 0:
            return None
        ear = (vert1 + vert2) / (2.0 * horiz)
        return float(ear)

    def _compute_darkness_closure_signal(self, gray_frame: np.ndarray) -> float:
        """
        Fallback simples: mede quanta textura escura/contraste existe na região central.
        Quando o olho fecha, a região da pupila some e o sinal muda abruptamente.
        """
        h, w = gray_frame.shape[:2]
        x1, x2 = int(w * 0.25), int(w * 0.75)
        y1, y2 = int(h * 0.25), int(h * 0.75)
        roi = gray_frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0

        dark_pixels = np.sum(roi < 60)
        grad_x = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.mean(np.sqrt(grad_x ** 2 + grad_y ** 2))
        signal = float(dark_pixels / max(1, roi.size) + mag / 255.0)
        return signal

    def update_blink_state(self, frame_bgr: np.ndarray, ts: float) -> bool:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blink_now = False

        ear = self._compute_eye_aspect_ratio_mediapipe(frame_bgr)
        if ear is not None:
            closed = ear < BLINK_EAR_THRESHOLD
        else:
            closure_signal = self._compute_darkness_closure_signal(gray)
            # Heurística: se não há pupila detectada por vários frames, trata como fechamento
            no_pupil = self.last_pupil_center is None
            closed = no_pupil and closure_signal < 0.25

        if closed:
            self.closed_frame_counter += 1
            self.open_frame_counter = 0
        else:
            self.open_frame_counter += 1
            self.closed_frame_counter = 0

        if not self.blink_closed and self.closed_frame_counter >= 2:
            self.blink_closed = True
            self.blink_start_ts = ts

        if self.blink_closed and self.open_frame_counter >= 2:
            duration = ts - self.blink_start_ts
            self.blink_closed = False

            if SINGLE_BLINK_MIN_DURATION <= duration <= SINGLE_BLINK_MAX_DURATION:
                self.blink_count_window.append(ts)
                self.blink_count_window = [b for b in self.blink_count_window if ts - b <= DOUBLE_BLINK_MAX_GAP]

                if len(self.blink_count_window) >= 2:
                    self.double_blink_flag = True
                    self.single_blink_flag = False
                    self.blink_count_window.clear()
                else:
                    self.single_blink_flag = True
                blink_now = True

        return blink_now

    def consume_blink_actions(self) -> Tuple[bool, bool]:
        dbl = self.double_blink_flag
        sgl = self.single_blink_flag
        self.double_blink_flag = False
        self.single_blink_flag = False
        return dbl, sgl

    ###########################################################################
    # Vetor de olhar
    ###########################################################################

    def compute_gaze_vector(
        self, x: int, y: int, center_x: int, center_y: int,
        screen_width: int = EYE_FRAME_W, screen_height: int = EYE_FRAME_H
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        viewport_width = screen_width
        viewport_height = screen_height

        fov_y_deg = 45.0
        aspect_ratio = viewport_width / viewport_height
        far_clip = 100.0
        camera_position = np.array([0.0, 0.0, 3.0], dtype=np.float32)

        fov_y_rad = np.radians(fov_y_deg)
        half_height_far = np.tan(fov_y_rad / 2) * far_clip
        half_width_far = half_height_far * aspect_ratio

        ndc_x = (2.0 * x) / viewport_width - 1.0
        ndc_y = 1.0 - (2.0 * y) / viewport_height

        far_x = ndc_x * half_width_far
        far_y = ndc_y * half_height_far
        far_z = camera_position[2] - far_clip
        far_point = np.array([far_x, far_y, far_z], dtype=np.float32)

        ray_origin = camera_position
        ray_direction = far_point - camera_position
        norm = np.linalg.norm(ray_direction)
        if norm == 0:
            return None, None
        ray_direction /= norm
        ray_direction = -ray_direction

        inner_radius = 1.0 / 1.05
        sphere_offset_x = (center_x / screen_width) * 2.0 - 1.0
        sphere_offset_y = 1.0 - (center_y / screen_height) * 2.0
        sphere_center = np.array([sphere_offset_x * 1.5, sphere_offset_y * 1.5, 0.0], dtype=np.float32)

        origin = ray_origin
        direction = -ray_direction
        L = origin - sphere_center

        a = np.dot(direction, direction)
        b = 2 * np.dot(direction, L)
        c = np.dot(L, L) - inner_radius ** 2

        discriminant = b ** 2 - 4 * a * c
        if discriminant < 0:
            return sphere_center, None

        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

        t = None
        if t1 > 0 and t2 > 0:
            t = min(t1, t2)
        elif t1 > 0:
            t = t1
        elif t2 > 0:
            t = t2

        if t is None:
            return sphere_center, None

        intersection_point = origin + t * direction
        intersection_local = intersection_point - sphere_center
        norm_local = np.linalg.norm(intersection_local)
        if norm_local == 0:
            return sphere_center, None
        target_direction = intersection_local / norm_local
        return sphere_center, target_direction

    ###########################################################################
    # Frame principal
    ###########################################################################

    def process_frame(self, frame_bgr: np.ndarray) -> Dict[str, object]:
        """
        Retorna:
        {
            'frame_debug': ...,
            'pupil_center': (x,y) | None,
            'eye_center': (x,y) | None,
            'gaze_yaw_pitch': (yaw,pitch),
            'blink_detected': bool,
            'ellipse': ellipse | None,
        }
        """
        ts = time.time()

        frame = self.crop_to_aspect_ratio(frame_bgr, EYE_FRAME_W, EYE_FRAME_H)
        frame = cv2.flip(frame, 0)

        darkest_point = self.get_darkest_area(frame)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        blink_now = self.update_blink_state(frame, ts)

        if darkest_point is None:
            self.last_pupil_center = None
            self.last_debug_frame = frame
            return {
                "frame_debug": frame,
                "pupil_center": None,
                "eye_center": self.last_eye_center,
                "gaze_yaw_pitch": self.last_world_yaw_pitch,
                "blink_detected": blink_now,
                "ellipse": None,
            }

        darkest_pixel_value = int(gray_frame[darkest_point[1], darkest_point[0]])

        strict = self.apply_binary_threshold(gray_frame, darkest_pixel_value, PUPIL_DARK_THRESHOLD_OFFSET[0])
        medium = self.apply_binary_threshold(gray_frame, darkest_pixel_value, PUPIL_DARK_THRESHOLD_OFFSET[1])
        relaxed = self.apply_binary_threshold(gray_frame, darkest_pixel_value, PUPIL_DARK_THRESHOLD_OFFSET[2])

        strict = self.mask_outside_square(strict, darkest_point, 250)
        medium = self.mask_outside_square(medium, darkest_point, 250)
        relaxed = self.mask_outside_square(relaxed, darkest_point, 250)

        kernel = np.ones((5, 5), np.uint8)
        image_array = [relaxed, medium, strict]

        final_image = None
        final_contours = []
        best_score = -1.0
        best_ellipse = None
        pupil_center = None

        for img in image_array:
            dilated = cv2.dilate(img, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reduced = self.filter_contours_by_area_and_return_largest(contours, 1000, 3)

            if not reduced or reduced[0] is None or len(reduced[0]) <= 5:
                continue

            current_goodness = self.check_ellipse_goodness(dilated, reduced[0])
            total_pixels = self.check_contour_pixels(reduced[0], dilated.shape[:2])

            if len(total_pixels) < 3:
                continue

            score = current_goodness[0] * (total_pixels[0] ** 2) * max(1e-6, total_pixels[1])

            if score > best_score:
                best_score = score
                optimized = self.optimize_contours_by_angle(reduced, gray_frame)
                if optimized is not None and len(optimized) >= 5:
                    try:
                        ellipse = cv2.fitEllipse(optimized)
                    except cv2.error:
                        ellipse = None
                else:
                    ellipse = None

                if ellipse is not None:
                    best_ellipse = ellipse
                    final_contours = [optimized]
                    final_image = dilated
                    pupil_center = (int(ellipse[0][0]), int(ellipse[0][1]))

        debug_frame = frame.copy()
        eye_center = self.last_eye_center

        if best_ellipse is not None and pupil_center is not None:
            self.last_valid_ellipse = best_ellipse
            self.ray_lines.append(best_ellipse)
            if len(self.ray_lines) > self.max_rays:
                self.ray_lines = self.ray_lines[-self.max_rays:]

            model_center = self.compute_average_intersection(debug_frame, self.ray_lines, 5, 1500, 5)

            if not self.center_locked:
                if model_center is not None:
                    eye_center = self.update_and_average_point(self.model_centers, model_center, 200)
                else:
                    eye_center = self.prev_model_center_avg

                if eye_center is not None and eye_center[0] != 0:
                    self.prev_model_center_avg = eye_center
                    self.locked_center = eye_center
            else:
                eye_center = self.locked_center

            if eye_center is None:
                eye_center = self.prev_model_center_avg

            self.last_eye_center = eye_center
            self.last_pupil_center = pupil_center

            distance = math.sqrt((pupil_center[0] - eye_center[0]) ** 2 + (pupil_center[1] - eye_center[1]) ** 2)
            self.max_observed_distance = max(self.max_observed_distance, min(230, distance))

            cv2.circle(debug_frame, eye_center, int(self.max_observed_distance), (255, 50, 50), 2)
            cv2.circle(debug_frame, eye_center, 8, (255, 255, 0), -1)
            cv2.line(debug_frame, eye_center, pupil_center, (255, 150, 50), 2)
            cv2.ellipse(debug_frame, best_ellipse, (20, 255, 255), 2)

            dx = pupil_center[0] - eye_center[0]
            dy = pupil_center[1] - eye_center[1]
            extended_x = int(eye_center[0] + 2 * dx)
            extended_y = int(eye_center[1] + 2 * dy)
            cv2.line(debug_frame, pupil_center, (extended_x, extended_y), (200, 255, 0), 3)

            sphere_center, direction = self.compute_gaze_vector(
                pupil_center[0], pupil_center[1], eye_center[0], eye_center[1]
            )

            if direction is not None:
                self.last_vector = direction
                yaw = float(np.degrees(np.arctan2(direction[0], max(1e-6, direction[2]))))
                pitch = float(np.degrees(np.arctan2(direction[1], max(1e-6, direction[2]))))
                self.last_world_yaw_pitch = (yaw, pitch)

                cv2.putText(
                    debug_frame,
                    f"Yaw: {yaw:+.2f}  Pitch: {pitch:+.2f}",
                    (10, EYE_FRAME_H - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )
        else:
            self.last_pupil_center = None

        if darkest_point is not None:
            cv2.circle(debug_frame, darkest_point, 4, (255, 0, 255), -1)

        self.last_debug_frame = debug_frame
        return {
            "frame_debug": debug_frame,
            "pupil_center": self.last_pupil_center,
            "eye_center": self.last_eye_center,
            "gaze_yaw_pitch": self.last_world_yaw_pitch,
            "blink_detected": blink_now,
            "ellipse": best_ellipse,
        }

###############################################################################
# PARTE 2 — SALA 3D
###############################################################################

class TextureManager:
    def __init__(self) -> None:
        self.textures: Dict[str, int] = {}

    def load_texture(self, path: str) -> int:
        if path in self.textures:
            return self.textures[path]

        if not os.path.exists(path):
            surf = pygame.Surface((512, 512), pygame.SRCALPHA)
            surf.fill((200, 200, 200, 255))
            pygame.draw.rect(surf, (50, 50, 50), surf.get_rect(), 8)
            pygame.font.init()
            font = pygame.font.SysFont("Arial", 28)
            txt = font.render("Imagem ausente", True, (30, 30, 30))
            surf.blit(txt, (120, 235))
        else:
            surf = pygame.image.load(path).convert_alpha()

        img_data = pygame.image.tostring(surf, "RGBA", True)
        width, height = surf.get_width(), surf.get_height()

        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
        glBindTexture(GL_TEXTURE_2D, 0)

        self.textures[path] = tex_id
        return tex_id

    def cleanup(self) -> None:
        for tex in self.textures.values():
            try:
                glDeleteTextures([tex])
            except Exception:
                pass
        self.textures.clear()

class Camera3D:
    def __init__(self) -> None:
        self.base_pos = np.array([0.0, 1.5, 8.0], dtype=np.float32)
        self.pos = self.base_pos.copy()
        self.yaw = 0.0
        self.pitch = 0.0
        self.zoom_target = None
        self.zoom_factor = 0.0
        self.default_look = np.array([0.0, 1.5, 0.0], dtype=np.float32)

    def update_from_gaze(self, gaze_yaw_pitch: Tuple[float, float]) -> None:
        gaze_yaw, gaze_pitch = gaze_yaw_pitch

        self.yaw = lerp(self.yaw, clamp(gaze_yaw * 1.6, -45, 45), 0.12)
        self.pitch = lerp(self.pitch, clamp(-gaze_pitch * 1.2, -25, 20), 0.12)

        if self.zoom_target is None:
            self.zoom_factor = lerp(self.zoom_factor, 0.0, 0.1)

    def set_zoom_target(self, point: Tuple[float, float, float]) -> None:
        self.zoom_target = np.array(point, dtype=np.float32)

    def zoom_in(self) -> None:
        self.zoom_factor = clamp(self.zoom_factor + 0.20, 0.0, 1.0)

    def zoom_out(self) -> None:
        self.zoom_factor = clamp(self.zoom_factor - 0.22, 0.0, 1.0)
        if self.zoom_factor <= 0.02:
            self.zoom_target = None
            self.zoom_factor = 0.0

    def apply_view(self) -> None:
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)

        forward = np.array([
            math.sin(rad_yaw) * math.cos(rad_pitch),
            math.sin(rad_pitch),
            -math.cos(rad_yaw) * math.cos(rad_pitch)
        ], dtype=np.float32)

        base_look = self.pos + forward * 5.0

        if self.zoom_target is not None:
            target_cam = self.zoom_target - forward * 1.8 + np.array([0.0, 0.1, 0.0], dtype=np.float32)
            self.pos = self.pos * (1.0 - 0.08 * (0.3 + self.zoom_factor)) + target_cam * (0.08 * (0.3 + self.zoom_factor))
            look_at = self.zoom_target
        else:
            self.pos = self.pos * 0.92 + self.base_pos * 0.08
            look_at = base_look

        gluLookAt(
            float(self.pos[0]), float(self.pos[1]), float(self.pos[2]),
            float(look_at[0]), float(look_at[1]), float(look_at[2]),
            0, 1, 0
        )

class GalleryRoom:
    def __init__(self, paintings: List[PaintingInfo]) -> None:
        self.paintings = paintings
        self.texture_manager = TextureManager()
        self.active_painting: Optional[PaintingInfo] = None
        self.hover_painting: Optional[PaintingInfo] = None
        self.hover_start: float = 0.0
        self.selection_progress: float = 0.0

        self.room_bounds = {
            "xmin": -7.0, "xmax": 7.0,
            "ymin": 0.0, "ymax": 4.2,
            "zmin": -7.0, "zmax": 7.0,
        }

    def _draw_textured_quad_centered(self, center, size, texture_id, normal):
        cx, cy, cz = center
        w, h = size
        hw, hh = w / 2.0, h / 2.0
        nx, ny, nz = normal

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_QUADS)

        if abs(nx) > 0.5:  # parede esquerda/direita
            x = cx
            glTexCoord2f(0, 0); glVertex3f(x, cy - hh, cz - hw)
            glTexCoord2f(1, 0); glVertex3f(x, cy - hh, cz + hw)
            glTexCoord2f(1, 1); glVertex3f(x, cy + hh, cz + hw)
            glTexCoord2f(0, 1); glVertex3f(x, cy + hh, cz - hw)
        else:  # parede frontal/fundo
            z = cz
            glTexCoord2f(0, 0); glVertex3f(cx - hw, cy - hh, z)
            glTexCoord2f(1, 0); glVertex3f(cx + hw, cy - hh, z)
            glTexCoord2f(1, 1); glVertex3f(cx + hw, cy + hh, z)
            glTexCoord2f(0, 1); glVertex3f(cx - hw, cy + hh, z)

        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)
        glDisable(GL_TEXTURE_2D)

    def draw_room(self) -> None:
        # Chão
        glColor3f(0.28, 0.28, 0.30)
        glBegin(GL_QUADS)
        glVertex3f(-7, 0, -7)
        glVertex3f(7, 0, -7)
        glVertex3f(7, 0, 7)
        glVertex3f(-7, 0, 7)
        glEnd()

        # Teto
        glColor3f(0.18, 0.18, 0.20)
        glBegin(GL_QUADS)
        glVertex3f(-7, 4.2, -7)
        glVertex3f(-7, 4.2, 7)
        glVertex3f(7, 4.2, 7)
        glVertex3f(7, 4.2, -7)
        glEnd()

        # Paredes
        walls = [
            ((-7, 0, -7), (-7, 4.2, -7), (-7, 4.2, 7), (-7, 0, 7), (0.52, 0.52, 0.56)),  # esquerda
            ((7, 0, -7), (7, 0, 7), (7, 4.2, 7), (7, 4.2, -7), (0.50, 0.50, 0.54)),        # direita
            ((-7, 0, -7), (7, 0, -7), (7, 4.2, -7), (-7, 4.2, -7), (0.58, 0.58, 0.62)),    # fundo
            ((-7, 0, 7), (-7, 4.2, 7), (7, 4.2, 7), (7, 0, 7), (0.60, 0.60, 0.64)),         # frente
        ]
        for p1, p2, p3, p4, color in walls:
            glColor3f(*color)
            glBegin(GL_QUADS)
            glVertex3f(*p1)
            glVertex3f(*p2)
            glVertex3f(*p3)
            glVertex3f(*p4)
            glEnd()

    def draw_paintings(self) -> None:
        for painting in self.paintings:
            tex_id = self.texture_manager.load_texture(painting.file_path)
            self._draw_textured_quad_centered(painting.center, painting.size, tex_id, painting.normal)

            # moldura
            cx, cy, cz = painting.center
            w, h = painting.size
            border = 0.10
            glColor3f(0.20, 0.12, 0.02)
            self._draw_frame_border(cx, cy, cz, w + border, h + border, painting.normal)

            # destaque do hover
            if self.hover_painting and self.hover_painting.title == painting.title:
                glColor4f(1.0, 0.9, 0.2, 0.35)
                self._draw_frame_border(cx, cy, cz, w + border + 0.05, h + border + 0.05, painting.normal)

    def _draw_frame_border(self, cx, cy, cz, w, h, normal) -> None:
        hw, hh = w / 2.0, h / 2.0
        nx, ny, nz = normal

        if abs(nx) > 0.5:
            x = cx + (0.01 if nx > 0 else -0.01)
            glBegin(GL_QUADS)
            # topo
            glVertex3f(x, cy + hh, cz - hw)
            glVertex3f(x, cy + hh - 0.08, cz - hw)
            glVertex3f(x, cy + hh - 0.08, cz + hw)
            glVertex3f(x, cy + hh, cz + hw)
            # base
            glVertex3f(x, cy - hh + 0.08, cz - hw)
            glVertex3f(x, cy - hh, cz - hw)
            glVertex3f(x, cy - hh, cz + hw)
            glVertex3f(x, cy - hh + 0.08, cz + hw)
            # esquerda
            glVertex3f(x, cy - hh, cz - hw)
            glVertex3f(x, cy + hh, cz - hw)
            glVertex3f(x, cy + hh, cz - hw + 0.08)
            glVertex3f(x, cy - hh, cz - hw + 0.08)
            # direita
            glVertex3f(x, cy - hh, cz + hw - 0.08)
            glVertex3f(x, cy + hh, cz + hw - 0.08)
            glVertex3f(x, cy + hh, cz + hw)
            glVertex3f(x, cy - hh, cz + hw)
            glEnd()
        else:
            z = cz + (0.01 if nz > 0 else -0.01)
            glBegin(GL_QUADS)
            # topo
            glVertex3f(cx - hw, cy + hh, z)
            glVertex3f(cx - hw, cy + hh - 0.08, z)
            glVertex3f(cx + hw, cy + hh - 0.08, z)
            glVertex3f(cx + hw, cy + hh, z)
            # base
            glVertex3f(cx - hw, cy - hh + 0.08, z)
            glVertex3f(cx - hw, cy - hh, z)
            glVertex3f(cx + hw, cy - hh, z)
            glVertex3f(cx + hw, cy - hh + 0.08, z)
            # esquerda
            glVertex3f(cx - hw, cy - hh, z)
            glVertex3f(cx - hw, cy + hh, z)
            glVertex3f(cx - hw + 0.08, cy + hh, z)
            glVertex3f(cx - hw + 0.08, cy - hh, z)
            # direita
            glVertex3f(cx + hw - 0.08, cy - hh, z)
            glVertex3f(cx + hw - 0.08, cy + hh, z)
            glVertex3f(cx + hw, cy + hh, z)
            glVertex3f(cx + hw, cy - hh, z)
            glEnd()

    def intersect_ray_with_room(self, ray_origin: np.ndarray, ray_dir: np.ndarray):
        """
        Retorna:
        {
            'point': np.ndarray,
            'wall': 'left'|'right'|'front'|'back'|None
        }
        """
        hits = []

        # left x=-7
        if abs(ray_dir[0]) > 1e-6:
            t = (-7 - ray_origin[0]) / ray_dir[0]
            if t > 0:
                p = ray_origin + t * ray_dir
                if 0 <= p[1] <= 4.2 and -7 <= p[2] <= 7:
                    hits.append((t, p, "left"))

            t = (7 - ray_origin[0]) / ray_dir[0]
            if t > 0:
                p = ray_origin + t * ray_dir
                if 0 <= p[1] <= 4.2 and -7 <= p[2] <= 7:
                    hits.append((t, p, "right"))

        if abs(ray_dir[2]) > 1e-6:
            t = (-7 - ray_origin[2]) / ray_dir[2]
            if t > 0:
                p = ray_origin + t * ray_dir
                if -7 <= p[0] <= 7 and 0 <= p[1] <= 4.2:
                    hits.append((t, p, "back"))

            t = (7 - ray_origin[2]) / ray_dir[2]
            if t > 0:
                p = ray_origin + t * ray_dir
                if -7 <= p[0] <= 7 and 0 <= p[1] <= 4.2:
                    hits.append((t, p, "front"))

        if not hits:
            return {"point": None, "wall": None}

        hits.sort(key=lambda x: x[0])
        return {"point": hits[0][1], "wall": hits[0][2]}

    def ray_to_world(self, camera: Camera3D) -> Tuple[np.ndarray, np.ndarray]:
        # gera um raio central da câmera
        rad_yaw = math.radians(camera.yaw)
        rad_pitch = math.radians(camera.pitch)
        forward = np.array([
            math.sin(rad_yaw) * math.cos(rad_pitch),
            math.sin(rad_pitch),
            -math.cos(rad_yaw) * math.cos(rad_pitch)
        ], dtype=np.float32)
        norm = np.linalg.norm(forward)
        if norm == 0:
            forward = np.array([0, 0, -1], dtype=np.float32)
        else:
            forward /= norm
        return camera.pos.copy(), forward

    def pick_painting(self, world_hit_point: Optional[np.ndarray], wall: Optional[str]) -> Optional[PaintingInfo]:
        if world_hit_point is None or wall is None:
            return None

        x, y, z = float(world_hit_point[0]), float(world_hit_point[1]), float(world_hit_point[2])

        for painting in self.paintings:
            if painting.wall != wall:
                continue

            cx, cy, cz = painting.center
            w, h = painting.size

            if wall in ("front", "back"):
                if (cx - w/2) <= x <= (cx + w/2) and (cy - h/2) <= y <= (cy + h/2):
                    return painting
            elif wall in ("left", "right"):
                if (cz - w/2) <= z <= (cz + w/2) and (cy - h/2) <= y <= (cy + h/2):
                    return painting
        return None

    def update_gaze_selection(self, painting: Optional[PaintingInfo], now_ts: float) -> Optional[PaintingInfo]:
        self.hover_painting = painting

        if painting is None:
            self.hover_start = 0.0
            self.selection_progress = 0.0
            return None

        if self.active_painting and painting.title == self.active_painting.title:
            self.selection_progress = 1.0
            return self.active_painting

        if self.hover_start == 0.0 or (self.hover_painting and self.active_painting and self.hover_painting.title != painting.title):
            self.hover_start = now_ts

        elapsed = now_ts - self.hover_start
        self.selection_progress = clamp(elapsed / SELECTION_HOLD_SECONDS, 0.0, 1.0)

        if elapsed >= SELECTION_HOLD_SECONDS:
            self.active_painting = painting
            return painting
        return None

###############################################################################
# PARTE 3 — HEATMAP E RELATÓRIO PDF
###############################################################################

class HeatmapRecorder:
    def __init__(self, width: int = HEATMAP_W, height: int = HEATMAP_H) -> None:
        self.width = width
        self.height = height
        self.map = np.zeros((height, width), dtype=np.float32)
        self.events: List[GazeEvent] = []

    def _wall_to_uv(self, wall: str, point: np.ndarray) -> Tuple[float, float]:
        x, y, z = float(point[0]), float(point[1]), float(point[2])

        if wall == "front":
            u = (x + 7.0) / 14.0
            v = 1.0 - (y / 4.2)
            return u * 0.25 + 0.75, v * 0.5
        if wall == "back":
            u = (x + 7.0) / 14.0
            v = 1.0 - (y / 4.2)
            return u * 0.25 + 0.25, v * 0.5
        if wall == "left":
            u = (z + 7.0) / 14.0
            v = 1.0 - (y / 4.2)
            return u * 0.25 + 0.0, v * 0.5
        if wall == "right":
            u = (z + 7.0) / 14.0
            v = 1.0 - (y / 4.2)
            return u * 0.25 + 0.5, v * 0.5
        return 0.5, 0.5

    def add(self, event: GazeEvent) -> None:
        self.events.append(event)
        if event.wall_hit is None or event.world_hit is None:
            return

        point = np.array(event.world_hit, dtype=np.float32)
        u, v = self._wall_to_uv(event.wall_hit, point)
        px = int(clamp(u, 0.0, 0.9999) * self.width)
        py = int(clamp(v, 0.0, 0.9999) * self.height)

        self._draw_gaussian(px, py, radius=22, strength=1.2)

    def _draw_gaussian(self, x: int, y: int, radius: int = 24, strength: float = 1.0) -> None:
        xmin = max(0, x - radius)
        xmax = min(self.width, x + radius + 1)
        ymin = max(0, y - radius)
        ymax = min(self.height, y + radius + 1)

        xs = np.arange(xmin, xmax) - x
        ys = np.arange(ymin, ymax) - y
        xx, yy = np.meshgrid(xs, ys)
        kernel = np.exp(-(xx**2 + yy**2) / (2 * (radius / 2.2) ** 2)) * strength
        self.map[ymin:ymax, xmin:xmax] += kernel.astype(np.float32)

    def save_csv(self, csv_path: str) -> None:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "wall_hit", "painting_title",
                "world_hit_x", "world_hit_y", "world_hit_z",
                "room_u", "room_v",
                "pupil_x", "pupil_y",
                "eye_x", "eye_y",
                "blink_state", "action"
            ])
            for e in self.events:
                wx, wy, wz = (e.world_hit if e.world_hit else (None, None, None))
                ru, rv = (e.room_uv if e.room_uv else (None, None))
                px, py = (e.pupil_center if e.pupil_center else (None, None))
                ex, ey = (e.eye_center if e.eye_center else (None, None))
                writer.writerow([
                    e.timestamp, e.wall_hit, e.painting_title,
                    wx, wy, wz, ru, rv, px, py, ex, ey, int(e.blink_state), e.action
                ])

    def generate_report(self, pdf_path: str, screenshots: List[np.ndarray], paintings: List[PaintingInfo]) -> None:
        total_fixations = len([e for e in self.events if e.painting_title])
        unique_paintings = sorted({e.painting_title for e in self.events if e.painting_title})
        action_counts = {}
        for e in self.events:
            if e.action:
                action_counts[e.action] = action_counts.get(e.action, 0) + 1

        with PdfPages(pdf_path) as pdf:
            # Página 1 - Resumo
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle("Relatório de Rastreamento Ocular - Sala 3D", fontsize=18, fontweight="bold")
            ax = fig.add_axes([0.06, 0.10, 0.88, 0.80])
            ax.axis("off")

            summary_text = (
                f"Data/Hora: {now_str()}\n\n"
                f"Eventos registrados: {len(self.events)}\n"
                f"Fixações em quadros: {total_fixations}\n"
                f"Quadros observados: {len(unique_paintings)}\n"
                f"Quadros distintos: {', '.join(unique_paintings) if unique_paintings else 'Nenhum'}\n\n"
                f"Ações:\n"
                f"- zoom_in: {action_counts.get('zoom_in', 0)}\n"
                f"- zoom_out: {action_counts.get('zoom_out', 0)}\n"
                f"- info_select: {action_counts.get('info_select', 0)}\n"
            )
            ax.text(0.02, 0.95, summary_text, va="top", fontsize=13)
            pdf.savefig(fig, dpi=180)
            plt.close(fig)

            # Página 2 - Heatmap
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle("Mapa de Calor do Olhar", fontsize=18, fontweight="bold")
            ax = fig.add_axes([0.05, 0.08, 0.90, 0.80])
            heat = self.map.copy()
            if np.max(heat) > 0:
                heat = heat / np.max(heat)

            ax.imshow(heat, cmap="inferno")
            ax.set_title("Distribuição espacial das fixações")
            ax.set_axis_off()
            pdf.savefig(fig, dpi=180)
            plt.close(fig)

            # Página 3 - Top quadros
            counts = {}
            for e in self.events:
                if e.painting_title:
                    counts[e.painting_title] = counts.get(e.painting_title, 0) + 1

            titles = list(counts.keys())
            values = list(counts.values())

            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle("Quadros Mais Observados", fontsize=18, fontweight="bold")
            ax = fig.add_axes([0.08, 0.13, 0.84, 0.72])
            if titles:
                ax.bar(titles, values)
                ax.set_ylabel("Eventos/fixações")
                ax.tick_params(axis="x", rotation=25)
            else:
                ax.text(0.5, 0.5, "Sem dados suficientes", ha="center", va="center", fontsize=16)
                ax.set_axis_off()
            pdf.savefig(fig, dpi=180)
            plt.close(fig)

            # Páginas com screenshots
            for idx, shot in enumerate(screenshots[:6], start=1):
                fig = plt.figure(figsize=(11.69, 8.27))
                fig.suptitle(f"Captura da Sessão #{idx}", fontsize=18, fontweight="bold")
                ax = fig.add_axes([0.04, 0.05, 0.92, 0.84])
                ax.imshow(cv2.cvtColor(shot, cv2.COLOR_BGR2RGB))
                ax.set_axis_off()
                pdf.savefig(fig, dpi=180)
                plt.close(fig)

            # Páginas com metadados dos quadros
            for painting in paintings:
                fig = plt.figure(figsize=(11.69, 8.27))
                fig.suptitle(f"Ficha do Quadro - {painting.title}", fontsize=18, fontweight="bold")
                ax = fig.add_axes([0.05, 0.08, 0.90, 0.80])
                ax.axis("off")

                text = (
                    f"Título: {painting.title}\n"
                    f"Artista: {painting.artist}\n"
                    f"Ano: {painting.year}\n"
                    f"Parede: {painting.wall}\n"
                    f"Centro 3D: {painting.center}\n\n"
                    f"Descrição:\n{painting.description}\n"
                )
                ax.text(0.03, 0.95, text, va="top", fontsize=13)
                pdf.savefig(fig, dpi=180)
                plt.close(fig)

###############################################################################
# PARTE 4 — HUD / OVERLAY
###############################################################################

def draw_cv_overlay(frame: np.ndarray, texts: List[str], x: int = 10, y: int = 25) -> np.ndarray:
    out = frame.copy()
    yy = y
    for txt in texts:
        cv2.putText(out, txt, (x+1, yy+1), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
        cv2.putText(out, txt, (x, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        yy += 28
    return out

def build_info_card_surface(painting: Optional[PaintingInfo], progress: float, zoom_factor: float) -> pygame.Surface:
    width, height = 520, 240
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((18, 18, 22, 220))
    pygame.draw.rect(surf, (240, 240, 240, 180), (0, 0, width-1, height-1), 2, border_radius=14)

    pygame.font.init()
    title_font = pygame.font.SysFont("Arial", 28, bold=True)
    font = pygame.font.SysFont("Arial", 22)
    small = pygame.font.SysFont("Arial", 18)

    if painting is None:
        title = title_font.render("Olhe para um quadro", True, (255, 255, 255))
        surf.blit(title, (22, 18))
        lines = [
            "Fixe o olhar para abrir as informações.",
            "Duas piscadas rápidas: zoom.",
            "Uma piscada: afasta o zoom.",
            f"Progresso de seleção: {int(progress * 100)}%",
            f"Zoom atual: {zoom_factor:.2f}",
        ]
        yy = 68
        for line in lines:
            t = font.render(line, True, (220, 220, 220))
            surf.blit(t, (22, yy))
            yy += 32
        return surf

    title = title_font.render(painting.title, True, (255, 255, 255))
    meta = font.render(f"{painting.artist} • {painting.year}", True, (225, 225, 225))
    desc_lines = wrap_text(painting.description, 56)

    surf.blit(title, (22, 18))
    surf.blit(meta, (22, 58))

    yy = 96
    for line in desc_lines[:4]:
        t = small.render(line, True, (210, 210, 210))
        surf.blit(t, (22, yy))
        yy += 24

    footer = small.render(
        f"Parede: {painting.wall} | Progresso: {int(progress * 100)}% | Zoom: {zoom_factor:.2f}",
        True,
        (255, 220, 120),
    )
    surf.blit(footer, (22, height - 34))
    return surf

def wrap_text(text: str, max_chars: int) -> List[str]:
    words = text.split()
    lines = []
    current = []
    current_len = 0

    for word in words:
        extra = len(word) + (1 if current else 0)
        if current_len + extra <= max_chars:
            current.append(word)
            current_len += extra
        else:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)

    if current:
        lines.append(" ".join(current))
    return lines

def draw_pygame_surface_as_overlay(surface: pygame.Surface, x: int, y: int) -> None:
    data = pygame.image.tostring(surface, "RGBA", True)
    glDisable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glWindowPos2d(x, y)
    glDrawPixels(surface.get_width(), surface.get_height(), GL_RGBA, GL_UNSIGNED_BYTE, data)
    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)

###############################################################################
# PARTE 5 — APP PRINCIPAL
###############################################################################

class EyeGallery3DApp:
    def __init__(self) -> None:
        ensure_dirs()

        self.paintings = self._build_default_paintings()
        self.gallery = GalleryRoom(self.paintings)
        self.eye_tracker = EyeTrackerEllipse()
        self.heatmap = HeatmapRecorder()
        self.camera = Camera3D()

        self.eye_cap = None
        self.running = True
        self.screenshots: List[np.ndarray] = []
        self.last_shot_ts = 0.0

        self.csv_path = os.path.join(EXPORT_DIR, f"gaze_events_{now_str()}.csv")
        self.pdf_path = os.path.join(REPORT_DIR, f"relatorio_heatmap_{now_str()}.pdf")

        self.info_card_surface = None
        self.status_text = "Iniciando..."
        self.last_selected_title = None

    def _build_default_paintings(self) -> List[PaintingInfo]:
        """
        Você pode trocar os caminhos pelos seus arquivos reais.
        """
        return [
            PaintingInfo(
                title="Abstração Vermelha",
                artist="Coleção Digital",
                year="2026",
                description="Composição abstrata com ênfase em movimento, calor cromático e ritmo visual.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_01.jpg"),
                wall="back",
                center=(-4.0, 2.0, -6.96),
                size=(2.3, 1.5),
                normal=(0.0, 0.0, 1.0),
            ),
            PaintingInfo(
                title="Geometria Azul",
                artist="Coleção Digital",
                year="2026",
                description="Estudo geométrico com contraste entre planos frios, profundidade e simetria estrutural.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_02.jpg"),
                wall="back",
                center=(0.0, 2.0, -6.96),
                size=(2.3, 1.5),
                normal=(0.0, 0.0, 1.0),
            ),
            PaintingInfo(
                title="Paisagem Sintética",
                artist="Coleção Digital",
                year="2026",
                description="Paisagem generativa que mistura horizonte digital, névoa volumétrica e relevo artificial.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_03.jpg"),
                wall="back",
                center=(4.0, 2.0, -6.96),
                size=(2.3, 1.5),
                normal=(0.0, 0.0, 1.0),
            ),
            PaintingInfo(
                title="Ritmo Urbano",
                artist="Coleção Digital",
                year="2026",
                description="Cena urbana fragmentada em módulos visuais, com leitura dinâmica e pulsação arquitetônica.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_04.jpg"),
                wall="left",
                center=(-6.96, 2.0, -2.8),
                size=(2.0, 1.4),
                normal=(1.0, 0.0, 0.0),
            ),
            PaintingInfo(
                title="Figura e Luz",
                artist="Coleção Digital",
                year="2026",
                description="Estudo figurativo com foco em sombras suaves, presença corporal e contraste dramático.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_05.jpg"),
                wall="left",
                center=(-6.96, 2.0, 2.8),
                size=(2.0, 1.4),
                normal=(1.0, 0.0, 0.0),
            ),
            PaintingInfo(
                title="Memória Verde",
                artist="Coleção Digital",
                year="2026",
                description="Campo cromático orgânico com textura respirável, evocando natureza, tempo e sedimentação.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_06.jpg"),
                wall="right",
                center=(6.96, 2.0, -2.8),
                size=(2.0, 1.4),
                normal=(-1.0, 0.0, 0.0),
            ),
            PaintingInfo(
                title="Topologia Dourada",
                artist="Coleção Digital",
                year="2026",
                description="Estruturas douradas em fluxo contínuo, explorando materialidade, brilho e organização espacial.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_07.jpg"),
                wall="right",
                center=(6.96, 2.0, 2.8),
                size=(2.0, 1.4),
                normal=(-1.0, 0.0, 0.0),
            ),
            PaintingInfo(
                title="Vórtice de Dados",
                artist="Coleção Digital",
                year="2026",
                description="Visualização poética de dados em espiral, sugerindo densidade, aceleração e análise informacional.",
                file_path=os.path.join(TEXTURE_DIR, "quadro_08.jpg"),
                wall="front",
                center=(0.0, 2.0, 6.96),
                size=(2.5, 1.6),
                normal=(0.0, 0.0, -1.0),
            ),
        ]

    def init_cameras(self, eye_index: int = 0) -> None:
        self.eye_cap = cv2.VideoCapture(eye_index)
        self.eye_cap.set(cv2.CAP_PROP_FRAME_WIDTH, EYE_FRAME_W)
        self.eye_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, EYE_FRAME_H)

        if not self.eye_cap.isOpened():
            raise RuntimeError(
                "Não foi possível abrir a câmera do olho. "
                "Troque o índice em init_cameras() ou conecte a câmera correta."
            )

    def init_opengl(self) -> None:
        if not OPENGL_AVAILABLE:
            raise RuntimeError("PyOpenGL não está instalado ou não está disponível no ambiente.")

        pygame.init()
        pygame.display.set_mode((WINDOW_W, WINDOW_H), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("Sala 3D com Rastreamento Ocular")
        glViewport(0, 0, WINDOW_W, WINDOW_H)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(60.0, WINDOW_W / WINDOW_H, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glClearColor(0.05, 0.05, 0.07, 1.0)

    def process_eye_camera(self) -> Dict[str, object]:
        ret, frame = self.eye_cap.read()
        if not ret:
            return {
                "frame_debug": np.zeros((EYE_FRAME_H, EYE_FRAME_W, 3), dtype=np.uint8),
                "pupil_center": None,
                "eye_center": None,
                "gaze_yaw_pitch": (0.0, 0.0),
                "blink_detected": False,
                "ellipse": None,
            }

        result = self.eye_tracker.process_frame(frame)
        return result

    def update_logic(self, eye_result: Dict[str, object]) -> None:
        gaze_yaw_pitch = eye_result["gaze_yaw_pitch"]
        pupil_center = eye_result["pupil_center"]
        eye_center = eye_result["eye_center"]
        blink_state = bool(self.eye_tracker.blink_closed)

        self.camera.update_from_gaze(gaze_yaw_pitch)

        ray_origin, ray_dir = self.gallery.ray_to_world(self.camera)
        hit = self.gallery.intersect_ray_with_room(ray_origin, ray_dir)
        hit_point = hit["point"]
        hit_wall = hit["wall"]

        hovered = self.gallery.pick_painting(hit_point, hit_wall)
        selected = self.gallery.update_gaze_selection(hovered, time.time())

        action = None
        if selected is not None and self.last_selected_title != selected.title:
            self.last_selected_title = selected.title
            action = "info_select"
            self.camera.set_zoom_target(selected.center)
            self.status_text = f"Quadro selecionado: {selected.title}"
        elif selected is None and hovered is None:
            self.last_selected_title = None

        dbl, sgl = self.eye_tracker.consume_blink_actions()

        if dbl and self.gallery.active_painting is not None:
            self.camera.set_zoom_target(self.gallery.active_painting.center)
            self.camera.zoom_in()
            self.status_text = f"Zoom in: {self.gallery.active_painting.title}"
            action = "zoom_in"

        if sgl:
            self.camera.zoom_out()
            self.status_text = "Zoom out"
            action = "zoom_out"

        room_uv = None
        if hit_point is not None and hit_wall is not None:
            room_uv = self.heatmap._wall_to_uv(hit_wall, hit_point)

        event = GazeEvent(
            timestamp=time.time(),
            wall_hit=hit_wall,
            painting_title=(hovered.title if hovered else None),
            world_hit=(tuple(map(float, hit_point)) if hit_point is not None else None),
            room_uv=room_uv,
            pupil_center=pupil_center,
            eye_center=eye_center,
            blink_state=blink_state,
            action=action,
        )
        self.heatmap.add(event)

        if time.time() - self.last_shot_ts > 6.0:
            shot = eye_result["frame_debug"]
            if isinstance(shot, np.ndarray):
                self.screenshots.append(shot.copy())
            self.last_shot_ts = time.time()

        # Preview auxiliar com mira
        debug = eye_result["frame_debug"].copy()
        texts = [
            f"Status: {self.status_text}",
            f"Quadro em foco: {hovered.title if hovered else 'nenhum'}",
            f"Selecionado: {self.gallery.active_painting.title if self.gallery.active_painting else 'nenhum'}",
            f"Progresso: {int(self.gallery.selection_progress * 100)}%",
            "2 piscadas = zoom | 1 piscada = afastar | ESC = sair e gerar PDF",
        ]
        debug = draw_cv_overlay(debug, texts)
        cv2.imshow("Eye Tracking Debug", debug)

    def render(self) -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.camera.apply_view()
        self.gallery.draw_room()
        self.gallery.draw_paintings()

        info_surface = build_info_card_surface(
            self.gallery.active_painting if self.gallery.active_painting else self.gallery.hover_painting,
            self.gallery.selection_progress,
            self.camera.zoom_factor,
        )
        draw_pygame_surface_as_overlay(info_surface, 30, 30)
        pygame.display.flip()

    def run(self) -> None:
        self.init_opengl()
        self.init_cameras(0)

        clock = pygame.time.Clock()

        while self.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    self.running = False
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self.running = False

            eye_result = self.process_eye_camera()
            self.update_logic(eye_result)
            self.render()

            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False

            clock.tick(60)

        self.shutdown()

    def shutdown(self) -> None:
        try:
            self.heatmap.save_csv(self.csv_path)
            self.heatmap.generate_report(self.pdf_path, self.screenshots, self.paintings)
        except Exception as e:
            print(f"Erro ao gerar exportações: {e}")

        if self.eye_cap is not None:
            self.eye_cap.release()
        self.gallery.texture_manager.cleanup()
        cv2.destroyAllWindows()
        pygame.quit()

        print(f"\nCSV salvo em: {self.csv_path}")
        print(f"PDF salvo em: {self.pdf_path}")

###############################################################################
# PARTE 6 — GERAÇÃO DE IMAGENS DE EXEMPLO DOS QUADROS
###############################################################################

def maybe_generate_placeholder_images() -> None:
    ensure_dirs()
    targets = [
        ("quadro_01.jpg", (180, 50, 50), "Abstração\nVermelha"),
        ("quadro_02.jpg", (40, 90, 180), "Geometria\nAzul"),
        ("quadro_03.jpg", (130, 160, 180), "Paisagem\nSintética"),
        ("quadro_04.jpg", (70, 70, 70), "Ritmo\nUrbano"),
        ("quadro_05.jpg", (200, 180, 160), "Figura\n& Luz"),
        ("quadro_06.jpg", (60, 140, 80), "Memória\nVerde"),
        ("quadro_07.jpg", (190, 150, 40), "Topologia\nDourada"),
        ("quadro_08.jpg", (100, 60, 150), "Vórtice\nDados"),
    ]

    for fname, color, label in targets:
        path = os.path.join(TEXTURE_DIR, fname)
        if os.path.exists(path):
            continue

        img = np.zeros((768, 1024, 3), dtype=np.uint8)
        img[:] = color

        for i in range(0, img.shape[1], 24):
            cv2.line(img, (i, 0), (img.shape[1] - i // 2, img.shape[0]), (255, 255, 255), 1)

        cv2.rectangle(img, (40, 40), (img.shape[1] - 40, img.shape[0] - 40), (20, 20, 20), 14)
        y = 280
        for line in label.split("\n"):
            cv2.putText(img, line, (150, y), cv2.FONT_HERSHEY_SIMPLEX, 2.4, (255, 255, 255), 6, cv2.LINE_AA)
            y += 100

        cv2.imwrite(path, img)

###############################################################################
# PARTE 7 — MAIN
###############################################################################

def main():
    maybe_generate_placeholder_images()
    app = EyeGallery3DApp()
    app.run()

if __name__ == "__main__":
    main()
