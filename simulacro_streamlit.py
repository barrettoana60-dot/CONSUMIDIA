import cv2
import math
import time
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================
EYE_W = 640
EYE_H = 480
ROOM_W = 1280
ROOM_H = 720
WINDOW_EYE = "Simulacro - Rastreio Ocular"
WINDOW_ROOM = "Simulacro - Sala 3D"


# ============================================================
# UTILITÁRIOS
# ============================================================
def clamp(value, vmin, vmax):
    return max(vmin, min(vmax, value))


def now():
    return time.perf_counter()


def draw_text(img, text, org, scale=0.6, color=(255, 255, 255), thickness=1, bg=True):
    x, y = org
    font = cv2.FONT_HERSHEY_SIMPLEX
    if bg:
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        cv2.rectangle(img, (x - 4, y - th - 6), (x + tw + 4, y + 4), (0, 0, 0), -1)
    cv2.putText(img, text, org, font, scale, color, thickness, cv2.LINE_AA)


# ============================================================
# MODELOS DE DADOS
# ============================================================
@dataclass
class Painting:
    pid: str
    title: str
    author: str
    year: str
    description: str
    wall: str
    center: Tuple[float, float, float]
    size: Tuple[float, float]  # largura, altura em unidades 3D
    color: Tuple[int, int, int]
    attention_seconds: float = 0.0
    hits: int = 0
    last_seen_ts: float = 0.0


@dataclass
class BlinkInterpreter:
    double_window: float = 0.45
    pending_single_ts: Optional[float] = None
    blink_counter: int = 0

    def register_blink(self) -> Optional[str]:
        t = now()
        if self.pending_single_ts is None:
            self.pending_single_ts = t
            self.blink_counter = 1
            return None

        if t - self.pending_single_ts <= self.double_window:
            self.pending_single_ts = None
            self.blink_counter = 0
            return "double"

        self.pending_single_ts = t
        self.blink_counter = 1
        return None

    def update(self) -> Optional[str]:
        if self.pending_single_ts is None:
            return None
        if now() - self.pending_single_ts > self.double_window:
            self.pending_single_ts = None
            self.blink_counter = 0
            return "single"
        return None


@dataclass
class SessionStats:
    start_time: float = field(default_factory=now)
    total_frames: int = 0
    tracked_frames: int = 0
    blink_single: int = 0
    blink_double: int = 0
    zoom_changes: int = 0
    report_path: str = "simulacro_relatorio.pdf"

    def duration(self) -> float:
        return max(0.0, now() - self.start_time)


# ============================================================
# RASTREADOR OCULAR
# Baseado na lógica do código enviado: busca da região mais escura,
# threshold adaptativo, contornos, ajuste de elipse e centro esférico.
# ============================================================
class EyeTracker:
    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.ray_lines: List[Tuple] = []
        self.model_centers: List[Tuple[int, int]] = []
        self.stored_intersections: List[Tuple[int, int]] = []

        self.max_rays = 120
        self.prev_model_center_avg = (EYE_W // 2, EYE_H // 2)
        self.gaze_pt = np.array([screen_w // 2, screen_h // 2], dtype=np.float32)
        self.raw_gaze_pt = np.array([screen_w // 2, screen_h // 2], dtype=np.float32)

        self.neutral_vector = np.array([0.0, 0.0], dtype=np.float32)
        self.has_calibration = False
        self.gain_x = 2.6
        self.gain_y = 2.2
        self.smooth_alpha = 0.24

        self.last_valid = False
        self.closed_frames = 0
        self.min_closed_frames = 2
        self.max_closed_frames = 16
        self.blinks_detected = 0

        self.debug_last_ellipse = None
        self.debug_pupil_center = None
        self.debug_eye_center = None
        self.debug_last_score = 0.0

    # -------- Funções adaptadas do código-base --------
    @staticmethod
    def crop_to_aspect_ratio(image, width=EYE_W, height=EYE_H):
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
    def apply_binary_threshold(image, darkest_pixel_value, added_threshold):
        threshold = darkest_pixel_value + added_threshold
        _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
        return thresholded_image

    @staticmethod
    def get_darkest_area(image):
        ignore_bounds = 20
        image_skip_size = 10
        search_area = 20
        internal_skip_size = 5

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_sum = float("inf")
        darkest_point = (gray.shape[1] // 2, gray.shape[0] // 2)

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
    def mask_outside_square(image, center, size):
        x, y = center
        half_size = size // 2
        mask = np.zeros_like(image)
        top_left_x = max(0, x - half_size)
        top_left_y = max(0, y - half_size)
        bottom_right_x = min(image.shape[1], x + half_size)
        bottom_right_y = min(image.shape[0], y + half_size)
        mask[top_left_y:bottom_right_y, top_left_x:bottom_right_x] = 255
        return cv2.bitwise_and(image, mask)

    @staticmethod
    def filter_contours_by_area_and_return_largest(contours, pixel_thresh, ratio_thresh):
        max_area = 0
        largest_contour = None
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= pixel_thresh:
                x, y, w, h = cv2.boundingRect(contour)
                if h == 0 or w == 0:
                    continue
                length_to_width_ratio = max(w / h, h / w)
                if length_to_width_ratio <= ratio_thresh and area > max_area:
                    max_area = area
                    largest_contour = contour
        return [largest_contour] if largest_contour is not None else []

    @staticmethod
    def optimize_contours_by_angle(contours, image):
        if len(contours) < 1 or contours[0] is None or len(contours[0]) < 6:
            return contours[0] if contours else np.array([], dtype=np.int32)

        all_contours = np.concatenate(contours[0], axis=0)
        spacing = max(1, int(len(all_contours) / 25))
        filtered_points = []
        centroid = np.mean(all_contours, axis=0)

        for i in range(len(all_contours)):
            current_point = all_contours[i]
            prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
            next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

            vec1 = prev_point - current_point
            vec2 = next_point - current_point
            denom = (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            if denom < 1e-6:
                continue
            cosang = np.dot(vec1, vec2) / denom
            cosang = np.clip(cosang, -1.0, 1.0)
            _ = np.arccos(cosang)
            vec_to_centroid = centroid - current_point
            cos_threshold = np.cos(np.radians(60))
            direction = (vec1 + vec2) / 2.0
            if np.dot(vec_to_centroid, direction) >= cos_threshold:
                filtered_points.append(current_point)

        if not filtered_points:
            return contours[0]
        return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))

    @staticmethod
    def check_contour_pixels(contour, image_shape):
        if contour is None or len(contour) < 5:
            return [0, 0.0, None]

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
        ratio_under_ellipse = absolute_pixel_total_thin / total_border_pixels if total_border_pixels > 0 else 0.0

        return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]

    @staticmethod
    def check_ellipse_goodness(binary_image, contour):
        if contour is None or len(contour) < 5:
            return [0.0, 0.0, 0.0]

        ellipse = cv2.fitEllipse(contour)
        mask = np.zeros_like(binary_image)
        cv2.ellipse(mask, ellipse, 255, -1)
        ellipse_area = int(np.sum(mask == 255))
        covered_pixels = int(np.sum((binary_image == 255) & (mask == 255)))
        if ellipse_area == 0:
            return [0.0, 0.0, 0.0]

        goodness = covered_pixels / float(ellipse_area)
        axis1, axis2 = ellipse[1]
        skew = min(axis2 / axis1, axis1 / axis2) if axis1 > 1e-6 and axis2 > 1e-6 else 0.0
        return [goodness, 0.0, skew]

    @staticmethod
    def find_line_intersection(ellipse1, ellipse2):
        (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
        (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

        angle1_rad = np.deg2rad(angle1)
        angle2_rad = np.deg2rad(angle2)

        dx1, dy1 = (minor_axis1 / 2) * np.cos(angle1_rad), (minor_axis1 / 2) * np.sin(angle1_rad)
        dx2, dy2 = (minor_axis2 / 2) * np.cos(angle2_rad), (minor_axis2 / 2) * np.sin(angle2_rad)

        A = np.array([[dx1, -dx2], [dy1, -dy2]], dtype=np.float32)
        B = np.array([cx2 - cx1, cy2 - cy1], dtype=np.float32)

        if abs(np.linalg.det(A)) < 1e-6:
            return None

        t1, _ = np.linalg.solve(A, B)
        intersection_x = cx1 + t1 * dx1
        intersection_y = cy1 + t1 * dy1
        return (int(intersection_x), int(intersection_y))

    def prune_intersections(self, maximum_intersections):
        if len(self.stored_intersections) <= maximum_intersections:
            return
        self.stored_intersections = self.stored_intersections[-maximum_intersections:]

    def update_and_average_point(self, point_list, new_point, N):
        point_list.append(new_point)
        if len(point_list) > N:
            point_list.pop(0)
        avg_x = int(np.mean([p[0] for p in point_list]))
        avg_y = int(np.mean([p[1] for p in point_list]))
        return (avg_x, avg_y)

    def compute_average_intersection(self, frame, ray_lines, N=6, M=1500):
        if len(ray_lines) < 2 or N < 2:
            return None

        height, width = frame.shape[:2]
        count = min(N, len(ray_lines))
        idx = np.random.choice(len(ray_lines), size=count, replace=False)
        selected_lines = [ray_lines[i] for i in idx]
        intersections = []

        for i in range(len(selected_lines) - 1):
            line1 = selected_lines[i]
            line2 = selected_lines[i + 1]
            angle1 = line1[2]
            angle2 = line2[2]
            if abs(angle1 - angle2) < 2:
                continue
            inter = self.find_line_intersection(line1, line2)
            if inter and 0 <= inter[0] < width and 0 <= inter[1] < height:
                intersections.append(inter)
                self.stored_intersections.append(inter)

        if len(self.stored_intersections) > M:
            self.prune_intersections(M)

        if not self.stored_intersections:
            return None

        avg_x = np.mean([pt[0] for pt in self.stored_intersections])
        avg_y = np.mean([pt[1] for pt in self.stored_intersections])
        return (int(avg_x), int(avg_y))

    # -------- Rastreamento de um frame --------
    def process_frame(self, frame):
        frame = self.crop_to_aspect_ratio(frame, EYE_W, EYE_H)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        darkest_point = self.get_darkest_area(frame)
        darkest_pixel_value = int(gray_frame[darkest_point[1], darkest_point[0]])

        thresholded_strict = self.apply_binary_threshold(gray_frame, darkest_pixel_value, 5)
        thresholded_strict = self.mask_outside_square(thresholded_strict, darkest_point, 250)

        thresholded_medium = self.apply_binary_threshold(gray_frame, darkest_pixel_value, 15)
        thresholded_medium = self.mask_outside_square(thresholded_medium, darkest_point, 250)

        thresholded_relaxed = self.apply_binary_threshold(gray_frame, darkest_pixel_value, 25)
        thresholded_relaxed = self.mask_outside_square(thresholded_relaxed, darkest_point, 250)

        thresholds = [thresholded_relaxed, thresholded_medium, thresholded_strict]
        best_score = 0.0
        best_ellipse = None
        best_contour = None

        kernel = np.ones((5, 5), np.uint8)
        for th in thresholds:
            dilated = cv2.dilate(th, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reduced = self.filter_contours_by_area_and_return_largest(contours, 1000, 3)
            if not reduced or reduced[0] is None or len(reduced[0]) < 5:
                continue

            contour = reduced[0]
            ellipse_goodness = self.check_ellipse_goodness(dilated, contour)
            contour_pixels = self.check_contour_pixels(contour, dilated.shape)
            score = ellipse_goodness[0] * (contour_pixels[0] ** 2) * max(contour_pixels[1], 1e-6)

            if score > best_score:
                best_score = score
                best_ellipse = cv2.fitEllipse(contour)
                best_contour = contour

        debug = frame.copy()
        pupil_valid = False
        pupil_center = None
        eye_center = self.prev_model_center_avg

        if best_contour is not None and len(best_contour) >= 5:
            optimized = self.optimize_contours_by_angle([best_contour], gray_frame)
            if optimized is not None and len(optimized) >= 5:
                best_ellipse = cv2.fitEllipse(optimized)
                self.ray_lines.append(best_ellipse)
                if len(self.ray_lines) > self.max_rays:
                    self.ray_lines = self.ray_lines[-self.max_rays:]

                model_center = self.compute_average_intersection(frame, self.ray_lines, N=6, M=1800)
                if model_center is not None:
                    eye_center = self.update_and_average_point(self.model_centers, model_center, 200)
                    self.prev_model_center_avg = eye_center
                else:
                    eye_center = self.prev_model_center_avg

                cx, cy = map(int, best_ellipse[0])
                pupil_center = (cx, cy)
                pupil_valid = True

                cv2.ellipse(debug, best_ellipse, (30, 255, 120), 2)
                cv2.circle(debug, pupil_center, 4, (0, 255, 255), -1)
                cv2.circle(debug, eye_center, 5, (255, 255, 0), -1)
                cv2.line(debug, eye_center, pupil_center, (0, 200, 255), 2)
                radius = int(max(20, min(220, np.linalg.norm(np.array(pupil_center) - np.array(eye_center)) * 2.2)))
                cv2.circle(debug, eye_center, radius, (255, 80, 80), 1)

        blink_event = self._update_blink_state(pupil_valid)
        gaze_info = self._compute_gaze(pupil_center, eye_center, pupil_valid)

        self.debug_last_ellipse = best_ellipse
        self.debug_pupil_center = pupil_center
        self.debug_eye_center = eye_center
        self.debug_last_score = best_score

        self._draw_debug(debug, darkest_point, gaze_info, pupil_valid)

        return {
            "eye_frame": debug,
            "pupil_valid": pupil_valid,
            "pupil_center": pupil_center,
            "eye_center": eye_center,
            "screen_gaze": tuple(self.gaze_pt.astype(int)),
            "raw_screen_gaze": tuple(self.raw_gaze_pt.astype(int)),
            "blink_event": blink_event,
            "score": best_score,
            "darkest_point": darkest_point,
        }

    def _compute_gaze(self, pupil_center, eye_center, pupil_valid):
        if not pupil_valid or pupil_center is None:
            return {
                "vector": np.array([0.0, 0.0], dtype=np.float32),
                "relative": np.array([0.0, 0.0], dtype=np.float32),
            }

        vec = np.array([
            float(pupil_center[0] - eye_center[0]),
            float(pupil_center[1] - eye_center[1]),
        ], dtype=np.float32)

        if not self.has_calibration:
            self.neutral_vector = vec.copy()
            self.has_calibration = True

        relative = vec - self.neutral_vector
        norm_x = relative[0] / 70.0
        norm_y = relative[1] / 55.0

        sx = self.screen_w * 0.5 + (norm_x * self.gain_x) * (self.screen_w * 0.5)
        sy = self.screen_h * 0.5 + (norm_y * self.gain_y) * (self.screen_h * 0.45)

        sx = clamp(sx, 0, self.screen_w - 1)
        sy = clamp(sy, 0, self.screen_h - 1)

        self.raw_gaze_pt = np.array([sx, sy], dtype=np.float32)
        self.gaze_pt = (1.0 - self.smooth_alpha) * self.gaze_pt + self.smooth_alpha * self.raw_gaze_pt

        return {
            "vector": vec,
            "relative": relative,
        }

    def _update_blink_state(self, pupil_valid):
        event = None
        if pupil_valid:
            if self.closed_frames >= self.min_closed_frames and self.closed_frames <= self.max_closed_frames:
                self.blinks_detected += 1
                event = "blink"
            self.closed_frames = 0
            self.last_valid = True
        else:
            self.closed_frames += 1
            self.last_valid = False
        return event

    def calibrate_center(self):
        if self.debug_pupil_center is not None and self.debug_eye_center is not None:
            vec = np.array([
                float(self.debug_pupil_center[0] - self.debug_eye_center[0]),
                float(self.debug_pupil_center[1] - self.debug_eye_center[1]),
            ], dtype=np.float32)
            self.neutral_vector = vec.copy()
            self.has_calibration = True

    def _draw_debug(self, debug, darkest_point, gaze_info, pupil_valid):
        cv2.circle(debug, darkest_point, 6, (255, 80, 255), 1)
        draw_text(debug, "C = calibrar centro", (10, 26), 0.62)
        draw_text(debug, "Q = sair | R = gerar PDF", (10, 52), 0.62)
        draw_text(debug, "1 piscada = afastar | 2 piscadas = zoom", (10, 78), 0.62)
        draw_text(debug, f"Rastreio: {'OK' if pupil_valid else 'SEM PUPILA'}", (10, 104), 0.62, (60, 255, 60) if pupil_valid else (60, 60, 255))
        draw_text(debug, f"Score elipse: {self.debug_last_score:.1f}", (10, 130), 0.62)
        draw_text(debug, f"Olhar em tela: {int(self.gaze_pt[0])}, {int(self.gaze_pt[1])}", (10, 156), 0.62)
        draw_text(debug, f"Vec relativo: {gaze_info['relative'][0]:.1f}, {gaze_info['relative'][1]:.1f}", (10, 182), 0.62)


# ============================================================
# SALA 3D
# ============================================================
class GalleryRoom:
    def __init__(self, width=ROOM_W, height=ROOM_H):
        self.width = width
        self.height = height
        self.cx = width / 2.0
        self.cy = height / 2.0
        self.focal_base = 720.0
        self.zoom = 1.0
        self.camera_offset = np.array([0.0, 0.0], dtype=np.float32)
        self.target_camera_offset = np.array([0.0, 0.0], dtype=np.float32)
        self.focus_pid: Optional[str] = None
        self.focus_hold: float = 0.0
        self.last_frame_time = now()

        self.paintings = self._build_paintings()
        self.last_projected: Dict[str, np.ndarray] = {}

    def _build_paintings(self):
        return [
            Painting(
                pid="Q1",
                title="Memória em Camadas",
                author="Acervo Simulacro",
                year="2026",
                description="Composição digital sobre documentação museológica, textura, profundidade e preservação.",
                wall="back",
                center=(-2.4, 0.8, 10.8),
                size=(2.1, 1.4),
                color=(205, 120, 80),
            ),
            Painting(
                pid="Q2",
                title="Cartografia do Olhar",
                author="Acervo Simulacro",
                year="2026",
                description="Quadro focado na ideia de visão guiada, campo de atenção e interação sem toque.",
                wall="back",
                center=(0.0, 0.6, 10.8),
                size=(2.3, 1.5),
                color=(90, 180, 220),
            ),
            Painting(
                pid="Q3",
                title="Profundidade e Vestígio",
                author="Acervo Simulacro",
                year="2026",
                description="Experimento visual que simula leitura material, sombra e volume sobre o acervo.",
                wall="back",
                center=(2.5, 0.9, 10.8),
                size=(2.0, 1.3),
                color=(130, 90, 200),
            ),
            Painting(
                pid="Q4",
                title="Atlas do Patrimônio",
                author="Acervo Simulacro",
                year="2026",
                description="Mapa visual de circulação de informação, autoria e conexão entre objetos culturais.",
                wall="left",
                center=(-5.4, 0.5, 7.5),
                size=(2.2, 1.4),
                color=(95, 155, 90),
            ),
            Painting(
                pid="Q5",
                title="Núcleo da Obra",
                author="Acervo Simulacro",
                year="2026",
                description="Investigação sobre camadas documentais, ficha, imagem e análise em uma só visualização.",
                wall="right",
                center=(5.4, 0.4, 7.1),
                size=(2.1, 1.4),
                color=(220, 170, 70),
            ),
            Painting(
                pid="Q6",
                title="Arquivo Vivo",
                author="Acervo Simulacro",
                year="2026",
                description="Quadro conceitual sobre reuso de dados, participação pública e inteligência de interface.",
                wall="left",
                center=(-5.4, -0.8, 9.3),
                size=(2.0, 1.3),
                color=(70, 180, 170),
            ),
        ]

    def set_focus(self, pid: Optional[str]):
        self.focus_pid = pid
        if pid is None:
            self.target_camera_offset[:] = 0.0
            return

        p = next((x for x in self.paintings if x.pid == pid), None)
        if p is None:
            self.target_camera_offset[:] = 0.0
            return

        # Move a câmera suavemente em direção ao quadro focado.
        tx = -p.center[0] * 0.22
        ty = -p.center[1] * 0.18
        self.target_camera_offset = np.array([tx, ty], dtype=np.float32)

    def zoom_in(self):
        self.zoom = min(2.3, self.zoom + 0.22)

    def zoom_out(self):
        self.zoom = max(1.0, self.zoom - 0.20)
        if self.zoom <= 1.02:
            self.focus_pid = None
            self.target_camera_offset[:] = 0.0

    def _project(self, point3d):
        x, y, z = point3d
        z = max(0.7, z)
        f = self.focal_base * self.zoom
        x = x + float(self.camera_offset[0])
        y = y + float(self.camera_offset[1])
        sx = self.cx + f * (x / z)
        sy = self.cy - f * (y / z)
        return np.array([sx, sy], dtype=np.float32)

    def _quad_points(self, p: Painting, inset=0.0):
        w, h = p.size
        w = max(0.1, w - inset * 2)
        h = max(0.1, h - inset * 2)
        cx, cy, cz = p.center

        if p.wall == "back":
            pts = [
                (cx - w / 2, cy + h / 2, cz),
                (cx + w / 2, cy + h / 2, cz),
                (cx + w / 2, cy - h / 2, cz),
                (cx - w / 2, cy - h / 2, cz),
            ]
        elif p.wall == "left":
            pts = [
                (cx, cy + h / 2, cz - w / 2),
                (cx, cy + h / 2, cz + w / 2),
                (cx, cy - h / 2, cz + w / 2),
                (cx, cy - h / 2, cz - w / 2),
            ]
        else:  # right
            pts = [
                (cx, cy + h / 2, cz + w / 2),
                (cx, cy + h / 2, cz - w / 2),
                (cx, cy - h / 2, cz - w / 2),
                (cx, cy - h / 2, cz + w / 2),
            ]
        return np.array([self._project(pt) for pt in pts], dtype=np.int32)

    def _draw_room_shell(self, img):
        back = np.array([
            self._project((-6.0, 3.0, 12.0)),
            self._project((6.0, 3.0, 12.0)),
            self._project((6.0, -3.0, 12.0)),
            self._project((-6.0, -3.0, 12.0)),
        ], dtype=np.int32)
        left = np.array([
            self._project((-6.0, 3.0, 4.0)),
            self._project((-6.0, 3.0, 12.0)),
            self._project((-6.0, -3.0, 12.0)),
            self._project((-6.0, -3.0, 4.0)),
        ], dtype=np.int32)
        right = np.array([
            self._project((6.0, 3.0, 12.0)),
            self._project((6.0, 3.0, 4.0)),
            self._project((6.0, -3.0, 4.0)),
            self._project((6.0, -3.0, 12.0)),
        ], dtype=np.int32)
        floor = np.array([
            self._project((-6.0, -3.0, 4.0)),
            self._project((6.0, -3.0, 4.0)),
            self._project((6.0, -3.0, 12.0)),
            self._project((-6.0, -3.0, 12.0)),
        ], dtype=np.int32)
        ceiling = np.array([
            self._project((-6.0, 3.0, 12.0)),
            self._project((6.0, 3.0, 12.0)),
            self._project((6.0, 3.0, 4.0)),
            self._project((-6.0, 3.0, 4.0)),
        ], dtype=np.int32)

        cv2.fillConvexPoly(img, left, (44, 44, 62))
        cv2.fillConvexPoly(img, right, (38, 38, 54))
        cv2.fillConvexPoly(img, back, (55, 55, 74))
        cv2.fillConvexPoly(img, floor, (28, 26, 36))
        cv2.fillConvexPoly(img, ceiling, (22, 22, 32))

        # guias de perspectiva no chão
        for gx in np.linspace(-5.0, 5.0, 9):
            p1 = tuple(self._project((gx, -3.0, 4.0)).astype(int))
            p2 = tuple(self._project((gx, -3.0, 12.0)).astype(int))
            cv2.line(img, p1, p2, (52, 50, 70), 1, cv2.LINE_AA)
        for gz in np.linspace(4.0, 12.0, 9):
            p1 = tuple(self._project((-6.0, -3.0, gz)).astype(int))
            p2 = tuple(self._project((6.0, -3.0, gz)).astype(int))
            cv2.line(img, p1, p2, (52, 50, 70), 1, cv2.LINE_AA)

    def _draw_painting(self, img, p: Painting, active=False, focused=False):
        outer = self._quad_points(p, inset=0.0)
        inner = self._quad_points(p, inset=0.10)
        self.last_projected[p.pid] = inner.copy()

        border_color = (235, 235, 235) if active else (190, 190, 200)
        if focused:
            border_color = (50, 220, 255)

        cv2.fillConvexPoly(img, outer, (38, 30, 20))
        cv2.fillConvexPoly(img, inner, p.color)
        cv2.polylines(img, [outer], True, border_color, 3, cv2.LINE_AA)
        cv2.polylines(img, [inner], True, (245, 245, 245), 1, cv2.LINE_AA)

        center2d = np.mean(inner, axis=0).astype(int)
        label_scale = max(0.4, min(0.72, 0.9 * self.zoom / max(1.0, p.center[2] / 8.0)))
        draw_text(img, p.title[:22], (center2d[0] - 80, center2d[1]), label_scale, (255, 255, 255), 1, bg=False)

        # brilho simples
        gloss = inner.copy().astype(np.int32)
        gloss[:, 0] = gloss[:, 0] - 10
        gloss[:, 1] = gloss[:, 1] - 6
        gloss[:, 0] = np.clip(gloss[:, 0], 0, self.width - 1)
        gloss[:, 1] = np.clip(gloss[:, 1], 0, self.height - 1)
        overlay = img.copy()
        cv2.fillConvexPoly(overlay, gloss, (255, 255, 255))
        cv2.addWeighted(overlay, 0.06, img, 0.94, 0, img)

    def painting_under_gaze(self, gaze_pt: Tuple[int, int]) -> Optional[str]:
        x, y = gaze_pt
        for p in self.paintings:
            quad = self.last_projected.get(p.pid)
            if quad is None or len(quad) < 4:
                continue
            if cv2.pointPolygonTest(quad.astype(np.float32), (float(x), float(y)), False) >= 0:
                return p.pid
        return None

    def update_attention(self, active_pid: Optional[str], dt: float):
        for p in self.paintings:
            if p.pid == active_pid:
                p.attention_seconds += dt
                if now() - p.last_seen_ts > 0.25:
                    p.hits += 1
                p.last_seen_ts = now()

    def draw(self, gaze_pt: Tuple[int, int], info_pid: Optional[str], dwell_ratio: float):
        current_time = now()
        dt = current_time - self.last_frame_time
        self.last_frame_time = current_time

        self.camera_offset = self.camera_offset * 0.88 + self.target_camera_offset * 0.12

        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._draw_room_shell(img)

        info_painting = None
        active_painting = self.painting_under_gaze(gaze_pt)
        if info_pid is not None:
            info_painting = next((p for p in self.paintings if p.pid == info_pid), None)
        if active_painting is None and self.focus_pid is not None:
            active_painting = self.focus_pid

        draw_order = sorted(self.paintings, key=lambda p: p.center[2], reverse=True)
        for p in draw_order:
            self._draw_painting(img, p, active=(p.pid == active_painting), focused=(p.pid == self.focus_pid))

        self.update_attention(active_painting, dt)

        # cursor do olhar
        gx, gy = gaze_pt
        cv2.circle(img, (gx, gy), 12, (0, 0, 0), 2)
        cv2.circle(img, (gx, gy), 8, (50, 220, 255), 2)
        cv2.line(img, (gx - 18, gy), (gx + 18, gy), (50, 220, 255), 1)
        cv2.line(img, (gx, gy - 18), (gx, gy + 18), (50, 220, 255), 1)

        draw_text(img, "Olhe para um quadro para ver detalhes", (26, 32), 0.72)
        draw_text(img, f"Zoom: {self.zoom:.2f}x", (26, 60), 0.72)

        if active_painting is not None and dwell_ratio < 1.0:
            draw_text(img, f"Fixando olhar... {int(dwell_ratio * 100)}%", (26, 90), 0.72, (255, 210, 80))

        if info_painting is not None:
            self._draw_info_panel(img, info_painting)

        return img

    def _draw_info_panel(self, img, p: Painting):
        overlay = img.copy()
        x1, y1 = self.width - 420, 40
        x2, y2 = self.width - 30, 280
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (8, 8, 15), -1)
        cv2.addWeighted(overlay, 0.82, img, 0.18, 0, img)
        cv2.rectangle(img, (x1, y1), (x2, y2), (80, 220, 255), 2)

        draw_text(img, p.title, (x1 + 16, y1 + 34), 0.82, (255, 255, 255), 2, bg=False)
        draw_text(img, f"Autor: {p.author}", (x1 + 16, y1 + 68), 0.66, (220, 220, 220), 1, bg=False)
        draw_text(img, f"Ano: {p.year}", (x1 + 16, y1 + 96), 0.66, (220, 220, 220), 1, bg=False)
        draw_text(img, f"Parede: {p.wall}", (x1 + 16, y1 + 124), 0.66, (220, 220, 220), 1, bg=False)

        lines = textwrap.wrap(p.description, width=43)
        yy = y1 + 160
        for line in lines[:4]:
            draw_text(img, line, (x1 + 16, yy), 0.62, (235, 235, 235), 1, bg=False)
            yy += 28


# ============================================================
# RELATÓRIO PDF
# ============================================================
class HeatmapReport:
    def __init__(self, width=ROOM_W, height=ROOM_H):
        self.width = width
        self.height = height
        self.map = np.zeros((height, width), dtype=np.float32)
        self.last_room_frame = np.zeros((height, width, 3), dtype=np.uint8)
        self.gaze_samples = 0

    def add_gaze(self, gaze_pt: Tuple[int, int], valid=True):
        if not valid:
            return
        x, y = gaze_pt
        if not (0 <= x < self.width and 0 <= y < self.height):
            return

        radius = 28
        xs = max(0, x - radius)
        xe = min(self.width, x + radius + 1)
        ys = max(0, y - radius)
        ye = min(self.height, y + radius + 1)

        yy, xx = np.mgrid[ys:ye, xs:xe]
        sigma = radius / 2.2
        gauss = np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2)))
        self.map[ys:ye, xs:xe] += gauss.astype(np.float32)
        self.gaze_samples += 1

    def update_room_frame(self, frame):
        self.last_room_frame = frame.copy()

    def save_pdf(self, pdf_path: str, paintings: List[Painting], stats: SessionStats):
        heat = self.map.copy()
        if np.max(heat) > 0:
            heat = heat / np.max(heat)

        rgb_room = cv2.cvtColor(self.last_room_frame, cv2.COLOR_BGR2RGB)

        with PdfPages(pdf_path) as pdf:
            # Página 1: resumo
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.patch.set_facecolor("white")
            plt.axis("off")
            plt.text(0.03, 0.92, "Relatório de Mapa de Calor - Simulacro", fontsize=22, weight="bold")
            plt.text(0.03, 0.86, f"Duração da sessão: {stats.duration():.1f} s", fontsize=13)
            plt.text(0.03, 0.82, f"Frames totais: {stats.total_frames}", fontsize=13)
            plt.text(0.03, 0.78, f"Frames com pupila rastreada: {stats.tracked_frames}", fontsize=13)
            plt.text(0.03, 0.74, f"Piscadas simples (afastar): {stats.blink_single}", fontsize=13)
            plt.text(0.03, 0.70, f"Piscadas duplas (zoom): {stats.blink_double}", fontsize=13)
            plt.text(0.03, 0.66, f"Mudanças de zoom: {stats.zoom_changes}", fontsize=13)
            plt.text(0.03, 0.60, f"Amostras de olhar acumuladas: {self.gaze_samples}", fontsize=13)
            plt.text(
                0.03,
                0.51,
                "O relatório mostra onde o olhar permaneceu com maior intensidade na sala 3D e\n"
                "quanto tempo cada quadro recebeu de atenção. Áreas em vermelho representam\n"
                "maior concentração do olhar.",
                fontsize=13,
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Página 2: heatmap sobre a sala
            fig = plt.figure(figsize=(13, 7.3))
            plt.imshow(rgb_room)
            plt.imshow(heat, cmap="jet", alpha=np.clip(heat * 0.85, 0, 0.85))
            plt.title("Mapa de calor do olhar sobre a sala 3D", fontsize=18)
            plt.axis("off")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Página 3: barras por quadro
            titles = [p.title for p in paintings]
            attention = [p.attention_seconds for p in paintings]
            hits = [p.hits for p in paintings]

            fig = plt.figure(figsize=(12, 8))
            ax1 = fig.add_subplot(211)
            ax1.bar(titles, attention)
            ax1.set_title("Tempo de atenção por quadro (segundos)")
            ax1.set_ylabel("segundos")
            ax1.tick_params(axis="x", rotation=25)

            ax2 = fig.add_subplot(212)
            ax2.bar(titles, hits)
            ax2.set_title("Número de ativações por quadro")
            ax2.set_ylabel("ativações")
            ax2.tick_params(axis="x", rotation=25)
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Página 4: tabela-resumo
            fig = plt.figure(figsize=(12, 8))
            plt.axis("off")
            rows = [[p.pid, p.title, p.author, p.year, f"{p.attention_seconds:.1f}", p.hits] for p in paintings]
            table = plt.table(
                cellText=rows,
                colLabels=["ID", "Quadro", "Autor", "Ano", "Tempo (s)", "Ativações"],
                cellLoc="left",
                loc="center",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1.7)
            plt.title("Resumo por quadro", fontsize=18, pad=20)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


# ============================================================
# APLICAÇÃO PRINCIPAL
# ============================================================
class SimulacroApp:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.eye_tracker = EyeTracker(ROOM_W, ROOM_H)
        self.gallery = GalleryRoom(ROOM_W, ROOM_H)
        self.report = HeatmapReport(ROOM_W, ROOM_H)
        self.blink_interpreter = BlinkInterpreter(double_window=0.43)
        self.stats = SessionStats()

        self.last_pid: Optional[str] = None
        self.pid_hold_start: Optional[float] = None
        self.info_pid: Optional[str] = None
        self.dwell_time = 0.75
        self.last_report_message = ""
        self.manual_help = True

    def open_camera(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_MSMF)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        return cap

    def generate_report(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = f"simulacro_relatorio_{ts}.pdf"
        self.report.save_pdf(pdf_path, self.gallery.paintings, self.stats)
        self.stats.report_path = pdf_path
        self.last_report_message = f"PDF salvo em: {pdf_path}"
        return pdf_path

    def _handle_blink_logic(self, blink_event, active_pid):
        if blink_event == "blink":
            result = self.blink_interpreter.register_blink()
            if result == "double":
                self.gallery.zoom_in()
                self.stats.zoom_changes += 1
                self.stats.blink_double += 1
                if active_pid is not None:
                    self.gallery.set_focus(active_pid)
            return

        pending = self.blink_interpreter.update()
        if pending == "single":
            self.gallery.zoom_out()
            self.stats.zoom_changes += 1
            self.stats.blink_single += 1
            if self.gallery.zoom <= 1.05:
                self.gallery.set_focus(None)

    def _update_dwell(self, active_pid: Optional[str]):
        t = now()
        dwell_ratio = 0.0
        if active_pid is None:
            self.last_pid = None
            self.pid_hold_start = None
            self.info_pid = None if self.gallery.zoom <= 1.03 else self.gallery.focus_pid
            return dwell_ratio

        if self.last_pid != active_pid:
            self.last_pid = active_pid
            self.pid_hold_start = t
            self.info_pid = None
            return 0.0

        if self.pid_hold_start is None:
            self.pid_hold_start = t
            return 0.0

        elapsed = t - self.pid_hold_start
        dwell_ratio = min(1.0, elapsed / self.dwell_time)
        if elapsed >= self.dwell_time:
            self.info_pid = active_pid
        return dwell_ratio

    def _draw_status_overlay(self, room_frame):
        y = ROOM_H - 88
        draw_text(room_frame, "Comandos: C calibrar | R gerar PDF | Q sair", (24, y), 0.66)
        draw_text(room_frame, "Olhe fixamente para um quadro para abrir as informações", (24, y + 28), 0.66)
        if self.last_report_message:
            draw_text(room_frame, self.last_report_message, (24, y - 28), 0.66, (80, 255, 120))

    def run(self):
        cap = self.open_camera()
        if not cap.isOpened():
            raise RuntimeError("Não foi possível abrir a câmera. Verifique o índice ou o dispositivo.")

        cv2.namedWindow(WINDOW_EYE, cv2.WINDOW_NORMAL)
        cv2.namedWindow(WINDOW_ROOM, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_EYE, 920, 690)
        cv2.resizeWindow(WINDOW_ROOM, 1280, 720)

        prev_time = now()

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            self.stats.total_frames += 1

            eye_result = self.eye_tracker.process_frame(frame)
            pupil_valid = eye_result["pupil_valid"]
            if pupil_valid:
                self.stats.tracked_frames += 1

            gaze_pt = eye_result["screen_gaze"]
            active_pid = self.gallery.painting_under_gaze(gaze_pt)
            dwell_ratio = self._update_dwell(active_pid)

            self._handle_blink_logic(eye_result["blink_event"], active_pid)

            room_frame = self.gallery.draw(gaze_pt, self.info_pid, dwell_ratio)
            self._draw_status_overlay(room_frame)

            # heatmap
            self.report.add_gaze(gaze_pt, valid=pupil_valid)
            self.report.update_room_frame(room_frame)

            # feedback visual das piscadas
            if eye_result["blink_event"] == "blink":
                draw_text(room_frame, "Piscada detectada", (ROOM_W - 260, ROOM_H - 32), 0.72, (255, 230, 80))

            cv2.imshow(WINDOW_EYE, eye_result["eye_frame"])
            cv2.imshow(WINDOW_ROOM, room_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("c"):
                self.eye_tracker.calibrate_center()
                self.last_report_message = "Centro do olhar recalibrado."
            elif key == ord("r"):
                path = self.generate_report()
                self.last_report_message = f"PDF gerado: {path}"
            elif key == ord("z"):
                self.gallery.zoom_in()
            elif key == ord("x"):
                self.gallery.zoom_out()

            # pequeno limitador para estabilidade
            current = now()
            elapsed = current - prev_time
            prev_time = current
            _ = elapsed

        cap.release()
        cv2.destroyAllWindows()

        # Gera relatório automático ao encerrar, se ainda não existir um nesta sessão.
        if not self.stats.report_path or not self.stats.report_path.endswith(".pdf"):
            self.generate_report()
        elif self.stats.report_path == "simulacro_relatorio.pdf":
            self.generate_report()


def main():
    print("Iniciando Simulacro - Sala 3D com rastreamento ocular...")
    print("Com base no pipeline de pupila/elipse do código-base enviado.")
    print("Teclas: C calibrar | R gerar PDF | Q sair | Z/X zoom manual")
    app = SimulacroApp(camera_index=0)
    app.run()


if __name__ == "__main__":
    main()
