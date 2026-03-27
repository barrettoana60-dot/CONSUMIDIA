
import argparse
import math
import os
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

import cv2
import numpy as np
import pygame
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# =============================================================================
# Utilidades matemáticas
# =============================================================================

EPS = 1e-8


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_vec(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return a + (b - a) * t


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < EPS:
        return v.copy()
    return v / n


def rotation_from_a_to_b(a, b):
    """
    Calcula matriz de rotação R tal que R @ a = b.
    Baseado na mesma ideia usada no código base do usuário.
    """
    a = normalize(np.asarray(a, dtype=np.float32))
    b = normalize(np.asarray(b, dtype=np.float32))

    v = np.cross(a, b)
    c = float(np.dot(a, b))

    if np.linalg.norm(v) < 1e-6:
        if c > 0.0:
            return np.eye(3, dtype=np.float32)
        axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(a[0]) > 0.9:
            axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        v = np.cross(a, axis)
        v = normalize(v)
        s = np.linalg.norm(v)
    else:
        s = np.linalg.norm(v)
        v = v / s

    vx, vy, vz = v
    K = np.array([
        [0, -vz, vy],
        [vz, 0, -vx],
        [-vy, vx, 0],
    ], dtype=np.float32)

    if s < 1e-6:
        return np.eye(3, dtype=np.float32)

    R = np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1.0 - c) / (s ** 2 + EPS))
    return R.astype(np.float32)


# =============================================================================
# Estruturas do cenário
# =============================================================================

@dataclass
class Painting:
    id: str
    title: str
    artist: str
    year: int
    description: str
    wall: str
    center: np.ndarray
    width: float
    height: float
    color: Tuple[int, int, int]
    info_lines: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.info_lines:
            self.info_lines = [
                f"Título: {self.title}",
                f"Artista: {self.artist}",
                f"Ano: {self.year}",
                self.description,
            ]

    def corners(self) -> np.ndarray:
        cx, cy, cz = self.center.astype(float)
        w2 = self.width / 2.0
        h2 = self.height / 2.0

        if self.wall in ("front", "back"):
            return np.array([
                [cx - w2, cy - h2, cz],
                [cx + w2, cy - h2, cz],
                [cx + w2, cy + h2, cz],
                [cx - w2, cy + h2, cz],
            ], dtype=np.float32)
        elif self.wall in ("left", "right"):
            return np.array([
                [cx, cy - h2, cz - w2],
                [cx, cy - h2, cz + w2],
                [cx, cy + h2, cz + w2],
                [cx, cy + h2, cz - w2],
            ], dtype=np.float32)
        else:
            raise ValueError(f"Parede inválida: {self.wall}")


@dataclass
class HitInfo:
    painting: Optional[Painting]
    point: Optional[np.ndarray]
    distance: float = 1e9


class GalleryRoom:
    def __init__(self):
        self.room_min = np.array([-7.0, 0.0, -12.0], dtype=np.float32)
        self.room_max = np.array([7.0, 4.0, 2.0], dtype=np.float32)
        self.paintings: List[Painting] = self._build_paintings()
        self.floor_color = (52, 52, 62)
        self.ceiling_color = (42, 42, 52)
        self.wall_color = (88, 88, 102)
        self.trim_color = (125, 115, 95)

    def _build_paintings(self) -> List[Painting]:
        return [
            Painting(
                id="Q1",
                title="Origem do Olhar",
                artist="Sistema Ocular IA",
                year=2026,
                description="Quadro técnico sobre rastreamento ocular, vetores e foco.",
                wall="front",
                center=np.array([-4.2, 2.1, -11.6], dtype=np.float32),
                width=2.2,
                height=1.5,
                color=(210, 92, 92),
            ),
            Painting(
                id="Q2",
                title="Mapa de Atenção",
                artist="Visual Analytics",
                year=2026,
                description="Representação do comportamento visual em forma de calor.",
                wall="front",
                center=np.array([0.0, 2.15, -11.6], dtype=np.float32),
                width=2.6,
                height=1.7,
                color=(92, 184, 210),
            ),
            Painting(
                id="Q3",
                title="Esfera e Pupila",
                artist="Modelo Geométrico",
                year=2026,
                description="Interpretação geométrica do centro ocular e da pupila.",
                wall="front",
                center=np.array([4.2, 2.05, -11.6], dtype=np.float32),
                width=2.2,
                height=1.45,
                color=(148, 209, 96),
            ),
            Painting(
                id="Q4",
                title="Raios de Interseção",
                artist="Intersections Lab",
                year=2026,
                description="Quadro lateral mostrando o cruzamento de raios estimados.",
                wall="left",
                center=np.array([-6.9, 2.1, -5.0], dtype=np.float32),
                width=2.4,
                height=1.55,
                color=(188, 142, 66),
            ),
            Painting(
                id="Q5",
                title="Blink Commands",
                artist="HCI Museum",
                year=2026,
                description="Dupla piscada aproxima, piscada única afasta da obra.",
                wall="right",
                center=np.array([6.9, 2.0, -6.0], dtype=np.float32),
                width=2.5,
                height=1.55,
                color=(128, 120, 220),
            ),
        ]

    def intersect_painting(self, ray_origin: np.ndarray, ray_dir: np.ndarray) -> HitInfo:
        best = HitInfo(painting=None, point=None, distance=1e9)

        for p in self.paintings:
            if p.wall == "front":
                plane_z = p.center[2]
                if abs(ray_dir[2]) < EPS:
                    continue
                t = (plane_z - ray_origin[2]) / ray_dir[2]
                if t <= 0:
                    continue
                point = ray_origin + ray_dir * t
                if (abs(point[0] - p.center[0]) <= p.width / 2.0 and
                        abs(point[1] - p.center[1]) <= p.height / 2.0):
                    d = float(np.linalg.norm(point - ray_origin))
                    if d < best.distance:
                        best = HitInfo(painting=p, point=point, distance=d)

            elif p.wall == "left" or p.wall == "right":
                plane_x = p.center[0]
                if abs(ray_dir[0]) < EPS:
                    continue
                t = (plane_x - ray_origin[0]) / ray_dir[0]
                if t <= 0:
                    continue
                point = ray_origin + ray_dir * t
                if (abs(point[2] - p.center[2]) <= p.width / 2.0 and
                        abs(point[1] - p.center[1]) <= p.height / 2.0):
                    d = float(np.linalg.norm(point - ray_origin))
                    if d < best.distance:
                        best = HitInfo(painting=p, point=point, distance=d)

        return best


# =============================================================================
# Renderização 3D em software (perspectiva manual)
# =============================================================================

class Software3DRenderer:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.bg = (18, 18, 24)
        self.fov = math.radians(66.0)
        self.near = 0.1
        self.far = 200.0

    def project(self, point_world: np.ndarray, cam_pos: np.ndarray, cam_rot: np.ndarray):
        """
        cam_rot: matriz 3x3 câmera->mundo; usamos transposta para mundo->câmera.
        Convenção: câmera olha para -Z.
        """
        rel = point_world - cam_pos
        cam = cam_rot.T @ rel

        z_forward = -cam[2]
        if z_forward <= self.near:
            return None

        aspect = self.width / max(self.height, 1)
        f = 1.0 / math.tan(self.fov / 2.0)

        ndc_x = (cam[0] * f / aspect) / z_forward
        ndc_y = (cam[1] * f) / z_forward

        screen_x = int((ndc_x + 1.0) * 0.5 * self.width)
        screen_y = int((1.0 - ndc_y) * 0.5 * self.height)
        return screen_x, screen_y, z_forward

    def project_many(self, points_world, cam_pos, cam_rot):
        projected = []
        depths = []
        for p in points_world:
            pr = self.project(np.asarray(p, dtype=np.float32), cam_pos, cam_rot)
            if pr is None:
                return None, None
            projected.append((pr[0], pr[1]))
            depths.append(pr[2])
        return projected, float(np.mean(depths))

    def draw_polygon(self, surf, pts_2d, color, outline=None, width=0):
        if len(pts_2d) >= 3:
            pygame.draw.polygon(surf, color, pts_2d, width)
            if outline is not None and width == 0:
                pygame.draw.polygon(surf, outline, pts_2d, 2)

    def render_room(self, surf, room: GalleryRoom, cam_pos: np.ndarray, cam_rot: np.ndarray,
                    focused_painting: Optional[Painting], hover_t: float):
        surf.fill(self.bg)

        xmin, ymin, zmin = room.room_min
        xmax, ymax, zmax = room.room_max

        corners = {
            "fbl": np.array([xmin, ymin, zmin], dtype=np.float32),
            "fbr": np.array([xmax, ymin, zmin], dtype=np.float32),
            "ftl": np.array([xmin, ymax, zmin], dtype=np.float32),
            "ftr": np.array([xmax, ymax, zmin], dtype=np.float32),
            "bbl": np.array([xmin, ymin, zmax], dtype=np.float32),
            "bbr": np.array([xmax, ymin, zmax], dtype=np.float32),
            "btl": np.array([xmin, ymax, zmax], dtype=np.float32),
            "btr": np.array([xmax, ymax, zmax], dtype=np.float32),
        }

        surfaces = [
            ("floor", [corners["fbl"], corners["fbr"], corners["bbr"], corners["bbl"]], room.floor_color),
            ("ceiling", [corners["ftl"], corners["ftr"], corners["btr"], corners["btl"]], room.ceiling_color),
            ("front", [corners["fbl"], corners["fbr"], corners["ftr"], corners["ftl"]], room.wall_color),
            ("left", [corners["fbl"], corners["bbl"], corners["btl"], corners["ftl"]], tuple(max(0, c - 10) for c in room.wall_color)),
            ("right", [corners["fbr"], corners["bbr"], corners["btr"], corners["ftr"]], tuple(max(0, c - 6) for c in room.wall_color)),
            ("back", [corners["bbl"], corners["bbr"], corners["btr"], corners["btl"]], tuple(max(0, c - 20) for c in room.wall_color)),
        ]

        draw_items = []

        for name, poly3d, color in surfaces:
            pts2d, depth = self.project_many(poly3d, cam_pos, cam_rot)
            if pts2d is not None:
                draw_items.append((depth, "poly", pts2d, color, (32, 32, 38), name))

        for p in room.paintings:
            corners3d = p.corners()
            pts2d, depth = self.project_many(corners3d, cam_pos, cam_rot)
            if pts2d is None:
                continue

            border = (240, 230, 210)
            fill = p.color
            outline = border
            if focused_painting and focused_painting.id == p.id:
                pulse = 0.55 + 0.45 * hover_t
                fill = tuple(int(clamp(c + 40 * pulse, 0, 255)) for c in p.color)
                outline = (255, 255, 120)

            draw_items.append((depth - 0.005, "frame_shadow", pts2d, (0, 0, 0), None, p))
            draw_items.append((depth - 0.002, "painting", pts2d, fill, outline, p))

            # Moldura interna
            inner = self._shrink_polygon(pts2d, 0.86)
            draw_items.append((depth - 0.001, "inner", inner, tuple(int(c * 0.33) for c in fill), (24, 24, 24), p))

        draw_items.sort(key=lambda item: item[0], reverse=True)

        for _, kind, pts2d, color, outline, payload in draw_items:
            if kind == "frame_shadow":
                shadow = [(x + 4, y + 4) for x, y in pts2d]
                self.draw_polygon(surf, shadow, (0, 0, 0))
            else:
                self.draw_polygon(surf, pts2d, color, outline=outline)

        # Rodapés decorativos na parede
        self._draw_trim(surf, room, cam_pos, cam_rot)

    def _draw_trim(self, surf, room, cam_pos, cam_rot):
        xmin, _, zmin = room.room_min
        xmax, _, zmax = room.room_max
        trim_h = 0.32
        y0 = 0.05
        y1 = y0 + trim_h

        trim_polys = [
            [np.array([xmin, y0, zmin]), np.array([xmax, y0, zmin]), np.array([xmax, y1, zmin]), np.array([xmin, y1, zmin])],
            [np.array([xmin, y0, zmin]), np.array([xmin, y0, zmax]), np.array([xmin, y1, zmax]), np.array([xmin, y1, zmin])],
            [np.array([xmax, y0, zmin]), np.array([xmax, y0, zmax]), np.array([xmax, y1, zmax]), np.array([xmax, y1, zmin])],
        ]

        items = []
        for poly in trim_polys:
            pts2d, depth = self.project_many(poly, cam_pos, cam_rot)
            if pts2d is not None:
                items.append((depth, pts2d))
        items.sort(key=lambda x: x[0], reverse=True)
        for _, pts2d in items:
            self.draw_polygon(surf, pts2d, room.trim_color, outline=(70, 56, 45))

    @staticmethod
    def _shrink_polygon(pts, scale=0.9):
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        out = []
        for x, y in pts:
            out.append((int(cx + (x - cx) * scale), int(cy + (y - cy) * scale)))
        return out


# =============================================================================
# Rastreamento ocular: adaptação do cálculo enviado pelo usuário
# =============================================================================

ray_lines = []
model_centers = []
stored_intersections = []
max_rays = 100
prev_model_center_avg = (320, 240)
max_observed_distance = 202
sphere_center_locked_2d = False
locked_model_center_avg = prev_model_center_avg


def crop_to_aspect_ratio(image, width=640, height=480):
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


def apply_binary_threshold(image, darkest_pixel_value, added_threshold):
    threshold = int(darkest_pixel_value + added_threshold)
    _, thresholded = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    return thresholded


def get_darkest_area(image):
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
                    current_sum += int(gray[y + dy, x + dx])
                    num_pixels += 1

            if num_pixels > 0 and current_sum < min_sum:
                min_sum = current_sum
                darkest_point = (x + search_area // 2, y + search_area // 2)

    if darkest_point is None:
        darkest_point = (gray.shape[1] // 2, gray.shape[0] // 2)
    return darkest_point


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


def optimize_contours_by_angle(contours, image):
    if len(contours) < 1 or contours[0] is None or len(contours[0]) < 5:
        return contours

    all_contours = np.concatenate(contours[0], axis=0)
    if len(all_contours) < 12:
        return np.array(all_contours, dtype=np.int32).reshape((-1, 1, 2))

    spacing = max(1, int(len(all_contours) / 25))
    filtered_points = []

    centroid = np.mean(all_contours, axis=0)

    for i in range(0, len(all_contours)):
        current_point = all_contours[i]
        prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
        next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

        vec1 = prev_point - current_point
        vec2 = next_point - current_point

        denom = (np.linalg.norm(vec1) * np.linalg.norm(vec2)) + EPS
        dot = float(np.dot(vec1.ravel(), vec2.ravel()))
        angle_cos = clamp(dot / denom, -1.0, 1.0)
        _ = math.acos(angle_cos)

        vec_to_centroid = centroid - current_point
        cos_threshold = math.cos(math.radians(60.0))

        direction = (vec1 + vec2) / 2.0
        dot2 = float(np.dot(vec_to_centroid.ravel(), direction.ravel()))
        if dot2 >= cos_threshold:
            filtered_points.append(current_point)

    if not filtered_points:
        filtered_points = list(all_contours)
    return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))


def filter_contours_by_area_and_return_largest(contours, pixel_thresh, ratio_thresh):
    max_area = 0
    largest_contour = None

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < pixel_thresh:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        if w == 0 or h == 0:
            continue
        ratio = max(w / h, h / w)
        if ratio <= ratio_thresh and area > max_area:
            max_area = area
            largest_contour = contour

    return [largest_contour] if largest_contour is not None else []


def check_contour_pixels(contour, image_shape):
    if contour is None or len(contour) < 5:
        return [0, 0.0, np.zeros(image_shape, dtype=np.uint8)]

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
    total_border_pixels = int(np.sum(contour_mask > 0))
    ratio_under_ellipse = absolute_pixel_total_thick / max(total_border_pixels, 1)

    return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]


def check_ellipse_goodness(binary_image, contour):
    ellipse_goodness = [0.0, 0.0, 0.0]
    if contour is None or len(contour) < 5:
        return ellipse_goodness

    ellipse = cv2.fitEllipse(contour)
    mask = np.zeros_like(binary_image)
    cv2.ellipse(mask, ellipse, 255, -1)

    ellipse_area = int(np.sum(mask == 255))
    covered_pixels = int(np.sum((binary_image == 255) & (mask == 255)))
    if ellipse_area <= 0:
        return ellipse_goodness

    ellipse_goodness[0] = covered_pixels / max(ellipse_area, 1)
    axes_lengths = ellipse[1]
    if axes_lengths[0] > 0 and axes_lengths[1] > 0:
        ellipse_goodness[2] = min(axes_lengths[1] / axes_lengths[0], axes_lengths[0] / axes_lengths[1])

    return ellipse_goodness


def update_and_average_point(point_list, new_point, N):
    point_list.append(new_point)
    if len(point_list) > N:
        point_list.pop(0)

    if not point_list:
        return None

    avg_x = int(np.mean([p[0] for p in point_list]))
    avg_y = int(np.mean([p[1] for p in point_list]))
    return avg_x, avg_y


def find_line_intersection(ellipse1, ellipse2):
    (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
    (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

    angle1_rad = np.deg2rad(angle1)
    angle2_rad = np.deg2rad(angle2)

    dx1, dy1 = (minor_axis1 / 2.0) * np.cos(angle1_rad), (minor_axis1 / 2.0) * np.sin(angle1_rad)
    dx2, dy2 = (minor_axis2 / 2.0) * np.cos(angle2_rad), (minor_axis2 / 2.0) * np.sin(angle2_rad)

    A = np.array([[dx1, -dx2], [dy1, -dy2]], dtype=np.float32)
    B = np.array([cx2 - cx1, cy2 - cy1], dtype=np.float32)

    det = float(np.linalg.det(A))
    if abs(det) < 1e-8:
        return None

    t1, _ = np.linalg.solve(A, B)
    ix = cx1 + t1 * dx1
    iy = cy1 + t1 * dy1
    return int(ix), int(iy)


def prune_intersections(intersections, maximum_intersections):
    if len(intersections) <= maximum_intersections:
        return intersections
    return intersections[-maximum_intersections:]


def compute_average_intersection(frame, ray_lines_list, N, M):
    global stored_intersections

    if len(ray_lines_list) < 2 or N < 2:
        return None

    height, width = frame.shape[:2]
    N = min(N, len(ray_lines_list))
    selected_indices = np.random.choice(len(ray_lines_list), size=N, replace=False)
    selected_lines = [ray_lines_list[i] for i in selected_indices]

    intersections = []

    for i in range(len(selected_lines) - 1):
        line1 = selected_lines[i]
        line2 = selected_lines[i + 1]
        angle1 = line1[2]
        angle2 = line2[2]

        if abs(angle1 - angle2) >= 2.0:
            intersection = find_line_intersection(line1, line2)
            if intersection is not None:
                if 0 <= intersection[0] < width and 0 <= intersection[1] < height:
                    intersections.append(intersection)
                    stored_intersections.append(intersection)

    if len(stored_intersections) > M:
        stored_intersections = prune_intersections(stored_intersections, M)

    if not stored_intersections:
        return None

    avg_x = int(np.mean([pt[0] for pt in stored_intersections]))
    avg_y = int(np.mean([pt[1] for pt in stored_intersections]))
    return avg_x, avg_y


def compute_gaze_vector(x, y, center_x, center_y, screen_width=640, screen_height=480):
    """
    Adaptado do cálculo enviado pelo usuário.
    Retorna:
      sphere_center_out, gaze_rotated
    """
    viewport_width = screen_width
    viewport_height = screen_height

    fov_y_deg = 45.0
    aspect_ratio = viewport_width / viewport_height
    far_clip = 100.0

    camera_position = np.array([0.0, 0.0, 3.0], dtype=np.float32)

    fov_y_rad = np.radians(fov_y_deg)
    half_height_far = np.tan(fov_y_rad / 2.0) * far_clip
    half_width_far = half_height_far * aspect_ratio

    ndc_x = (2.0 * x) / viewport_width - 1.0
    ndc_y = 1.0 - (2.0 * y) / viewport_height

    far_x = ndc_x * half_width_far
    far_y = ndc_y * half_height_far
    far_z = camera_position[2] - far_clip
    far_point = np.array([far_x, far_y, far_z], dtype=np.float32)

    ray_origin = camera_position
    ray_direction = far_point - camera_position
    ray_direction = normalize(ray_direction)
    ray_direction = -ray_direction

    inner_radius = 1.0 / 1.05
    sphere_offset_x = (center_x / screen_width) * 2.0 - 1.0
    sphere_offset_y = 1.0 - (center_y / screen_height) * 2.0
    sphere_center = np.array([sphere_offset_x * 1.5, sphere_offset_y * 1.5, 0.0], dtype=np.float32)

    origin = ray_origin
    direction = -ray_direction
    L = origin - sphere_center

    a = float(np.dot(direction, direction))
    b = float(2 * np.dot(direction, L))
    c = float(np.dot(L, L) - inner_radius**2)

    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        t = -float(np.dot(direction, L)) / (float(np.dot(direction, direction)) + EPS)
        intersection_point = origin + t * direction
        intersection_local = intersection_point - sphere_center
        target_direction = normalize(intersection_local)
    else:
        sqrt_disc = math.sqrt(max(discriminant, 0.0))
        t1 = (-b - sqrt_disc) / (2 * a + EPS)
        t2 = (-b + sqrt_disc) / (2 * a + EPS)

        t = None
        if t1 > 0 and t2 > 0:
            t = min(t1, t2)
        elif t1 > 0:
            t = t1
        elif t2 > 0:
            t = t2
        if t is None:
            return None, None

        intersection_point = origin + t * direction
        intersection_local = intersection_point - sphere_center
        target_direction = normalize(intersection_local)

    circle_local_center = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
    circle_local_center = normalize(circle_local_center)

    rotation_axis = np.cross(circle_local_center, target_direction)
    rotation_axis_norm = np.linalg.norm(rotation_axis)

    if rotation_axis_norm < 1e-6:
        return sphere_center, circle_local_center

    rotation_axis = rotation_axis / rotation_axis_norm
    dot = float(np.clip(np.dot(circle_local_center, target_direction), -1.0, 1.0))
    angle_rad = math.acos(dot)

    c0 = math.cos(angle_rad)
    s0 = math.sin(angle_rad)
    t0 = 1.0 - c0
    x0, y0, z0 = rotation_axis

    rotation_matrix = np.array([
        [t0 * x0 * x0 + c0, t0 * x0 * y0 - s0 * z0, t0 * x0 * z0 + s0 * y0],
        [t0 * x0 * y0 + s0 * z0, t0 * y0 * y0 + c0, t0 * y0 * z0 - s0 * x0],
        [t0 * x0 * z0 - s0 * y0, t0 * y0 * z0 + s0 * x0, t0 * z0 * z0 + c0],
    ], dtype=np.float32)

    gaze_local = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
    gaze_rotated = rotation_matrix @ gaze_local
    gaze_rotated = normalize(gaze_rotated)

    return sphere_center, gaze_rotated


class EyeTracker:
    def __init__(self, camera_index: int = 0, preview: bool = False):
        self.camera_index = camera_index
        self.preview = preview
        self.cap = None
        self.thread = None
        self.running = False
        self.lock = threading.Lock()

        self.latest_frame = None
        self.latest_debug_frame = None
        self.gaze_vector = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        self.sphere_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.pupil_center_2d = (320, 240)
        self.eye_center_2d = (320, 240)
        self.ellipse = None
        self.ellipse_found = False
        self.confidence = 0.0
        self.frame_count = 0
        self.fps = 0.0
        self._fps_t0 = time.time()
        self._fps_count = 0

        # Blink
        self.closed_frames = 0
        self.open_frames = 0
        self.last_blink_time = 0.0
        self.last_blinks: List[float] = []
        self.single_blink_flag = False
        self.double_blink_flag = False
        self.total_blinks = 0
        self.total_double_blinks = 0

        # calibração do olhar para a tela
        self.calibrated = False
        self.R_gaze_to_screen = np.eye(3, dtype=np.float32)

        # suavização
        self.smooth_gaze = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        self.smooth_strength = 0.22

    def start(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir a câmera {self.camera_index}")
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        if self.cap is not None:
            self.cap.release()
        if self.preview:
            cv2.destroyAllWindows()

    def calibrate_center(self):
        with self.lock:
            current = self.smooth_gaze.copy()
        target = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        self.R_gaze_to_screen = rotation_from_a_to_b(current, target)
        self.calibrated = True

    def consume_single_blink(self) -> bool:
        with self.lock:
            v = self.single_blink_flag
            self.single_blink_flag = False
            return v

    def consume_double_blink(self) -> bool:
        with self.lock:
            v = self.double_blink_flag
            self.double_blink_flag = False
            return v

    def get_state(self):
        with self.lock:
            return {
                "gaze_vector": self.smooth_gaze.copy(),
                "sphere_center": self.sphere_center.copy(),
                "ellipse_found": self.ellipse_found,
                "ellipse": self.ellipse,
                "pupil_center_2d": self.pupil_center_2d,
                "eye_center_2d": self.eye_center_2d,
                "confidence": self.confidence,
                "fps": self.fps,
                "total_blinks": self.total_blinks,
                "total_double_blinks": self.total_double_blinks,
            }

    def get_screen_gaze(self):
        with self.lock:
            g = self.smooth_gaze.copy()
        if self.calibrated:
            g = self.R_gaze_to_screen @ g
        g = normalize(g)
        return g

    def _register_blink(self, blink_time: float):
        self.total_blinks += 1
        self.last_blinks.append(blink_time)
        self.last_blinks = [t for t in self.last_blinks if blink_time - t <= 0.80]

        if len(self.last_blinks) >= 2 and (self.last_blinks[-1] - self.last_blinks[-2]) <= 0.65:
            self.double_blink_flag = True
            self.total_double_blinks += 1
            self.last_blinks = []
        else:
            self.single_blink_flag = True

    def _update_blink_logic(self, ellipse_found: bool):
        now = time.time()

        if ellipse_found:
            self.open_frames += 1
            if 2 <= self.closed_frames <= 8:
                self._register_blink(now)
            self.closed_frames = 0
        else:
            self.closed_frames += 1
            self.open_frames = 0

        # evita consumir piscada única imediatamente caso venha uma segunda
        if self.single_blink_flag and self.double_blink_flag:
            self.single_blink_flag = False

        if self.single_blink_flag and self.last_blinks:
            # Aguarda pequena janela para ver se vira dupla piscada
            if now - self.last_blinks[-1] < 0.32:
                pass

    def _run(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue

            result = self._process_frame(frame)

            with self.lock:
                self.latest_frame = frame
                self.latest_debug_frame = result.get("debug_frame")
                self.gaze_vector = result["gaze_vector"]
                self.sphere_center = result["sphere_center"]
                self.ellipse_found = result["ellipse_found"]
                self.ellipse = result["ellipse"]
                self.pupil_center_2d = result["pupil_center"]
                self.eye_center_2d = result["eye_center"]
                self.confidence = result["confidence"]

                self.smooth_gaze = normalize(lerp_vec(self.smooth_gaze, self.gaze_vector, self.smooth_strength))

                self._fps_count += 1
                dt = time.time() - self._fps_t0
                if dt >= 1.0:
                    self.fps = self._fps_count / dt
                    self._fps_t0 = time.time()
                    self._fps_count = 0

            self._update_blink_logic(result["ellipse_found"])

            if self.preview and result.get("debug_frame") is not None:
                cv2.imshow("Eye Tracker Preview", result["debug_frame"])
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    self.running = False
                    break

    def _process_frame(self, frame):
        global ray_lines, model_centers, prev_model_center_avg

        frame = crop_to_aspect_ratio(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        darkest_point = get_darkest_area(frame)
        darkest_pixel_value = gray[darkest_point[1], darkest_point[0]]

        thr_strict = apply_binary_threshold(gray, darkest_pixel_value, 5)
        thr_medium = apply_binary_threshold(gray, darkest_pixel_value, 15)
        thr_relaxed = apply_binary_threshold(gray, darkest_pixel_value, 25)

        thr_strict = mask_outside_square(thr_strict, darkest_point, 250)
        thr_medium = mask_outside_square(thr_medium, darkest_point, 250)
        thr_relaxed = mask_outside_square(thr_relaxed, darkest_point, 250)

        images = [thr_relaxed, thr_medium, thr_strict]
        best_score = -1.0
        best_ellipse = None
        best_center = None
        best_contour = None

        kernel = np.ones((5, 5), np.uint8)

        for img in images:
            dilated = cv2.dilate(img, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reduced = filter_contours_by_area_and_return_largest(contours, 1000, 3)

            if len(reduced) == 0 or reduced[0] is None or len(reduced[0]) < 5:
                continue

            contour = reduced[0]
            goodness = check_ellipse_goodness(dilated, contour)
            contour_pixels = check_contour_pixels(contour, dilated.shape)
            score = goodness[0] * max(contour_pixels[0], 1) * max(contour_pixels[1], 0.01)

            if score > best_score:
                best_score = score
                best_contour = contour
                best_ellipse = cv2.fitEllipse(contour)
                best_center = tuple(map(int, best_ellipse[0]))

        debug_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        cv2.circle(debug_frame, darkest_point, 5, (0, 0, 255), -1)

        ellipse_found = best_ellipse is not None
        confidence = float(best_score) if best_score > 0 else 0.0
        pupil_center = (320, 240)
        eye_center = prev_model_center_avg
        gaze_vector = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        sphere_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        if ellipse_found:
            optimized = optimize_contours_by_angle([best_contour], gray)
            if optimized is not None and len(optimized) >= 5:
                best_ellipse = cv2.fitEllipse(optimized)

            pupil_center = tuple(map(int, best_ellipse[0]))
            ray_lines.append(best_ellipse)
            if len(ray_lines) > max_rays:
                ray_lines = ray_lines[-max_rays:]

            model_center = compute_average_intersection(frame, ray_lines, 5, 1500)
            if model_center is not None:
                model_center_avg = update_and_average_point(model_centers, model_center, 200)
                if model_center_avg is not None:
                    prev_model_center_avg = model_center_avg
            eye_center = prev_model_center_avg

            sc, gv = compute_gaze_vector(
                pupil_center[0],
                pupil_center[1],
                eye_center[0],
                eye_center[1],
                screen_width=640,
                screen_height=480,
            )
            if sc is not None and gv is not None:
                sphere_center = sc
                gaze_vector = gv

            cv2.ellipse(debug_frame, best_ellipse, (20, 255, 255), 2)
            cv2.circle(debug_frame, pupil_center, 5, (0, 255, 0), -1)
            cv2.circle(debug_frame, eye_center, 6, (255, 200, 0), -1)
            cv2.line(debug_frame, eye_center, pupil_center, (255, 120, 40), 2)

            dx = pupil_center[0] - eye_center[0]
            dy = pupil_center[1] - eye_center[1]
            ext = (int(eye_center[0] + dx * 2.0), int(eye_center[1] + dy * 2.0))
            cv2.line(debug_frame, pupil_center, ext, (0, 255, 180), 2)

        cv2.putText(debug_frame, f"Conf: {confidence:.1f}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 220, 50), 2)
        cv2.putText(debug_frame, f"Ellipse: {'OK' if ellipse_found else 'NO'}", (10, 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 220, 50), 2)

        return {
            "gaze_vector": gaze_vector.astype(np.float32),
            "sphere_center": sphere_center.astype(np.float32),
            "ellipse_found": ellipse_found,
            "ellipse": best_ellipse,
            "pupil_center": pupil_center,
            "eye_center": eye_center,
            "confidence": confidence,
            "debug_frame": debug_frame,
        }


# =============================================================================
# Heatmap e relatório PDF
# =============================================================================

class HeatmapReport:
    def __init__(self, width: int, height: int, room: GalleryRoom):
        self.width = width
        self.height = height
        self.room = room
        self.heatmap = np.zeros((height, width), dtype=np.float32)
        self.painting_times: Dict[str, float] = {p.id: 0.0 for p in room.paintings}
        self.painting_hits: Dict[str, int] = {p.id: 0 for p in room.paintings}
        self.painting_titles: Dict[str, str] = {p.id: p.title for p in room.paintings}
        self.session_start = time.time()
        self.last_frame_time = time.time()
        self.last_background_frame = None
        self.total_samples = 0

    def add_gaze(self, x: int, y: int, focused: Optional[Painting], dt: float):
        if 0 <= x < self.width and 0 <= y < self.height:
            self._splat(x, y, sigma=22, amount=1.0)
            self.total_samples += 1

        if focused is not None:
            self.painting_times[focused.id] += dt
            self.painting_hits[focused.id] += 1

    def set_background_frame(self, surf: pygame.Surface):
        arr = pygame.surfarray.array3d(surf)
        arr = np.transpose(arr, (1, 0, 2))
        self.last_background_frame = arr.copy()

    def _splat(self, x: int, y: int, sigma=16, amount=1.0):
        radius = sigma * 3
        x0 = max(0, x - radius)
        x1 = min(self.width, x + radius + 1)
        y0 = max(0, y - radius)
        y1 = min(self.height, y + radius + 1)

        xs = np.arange(x0, x1) - x
        ys = np.arange(y0, y1) - y
        xv, yv = np.meshgrid(xs, ys)
        kernel = np.exp(-(xv**2 + yv**2) / (2.0 * sigma**2))
        self.heatmap[y0:y1, x0:x1] += kernel.astype(np.float32) * amount

    def save_pdf(self, pdf_path: str, blink_count: int, double_blinks: int):
        session_duration = max(1.0, time.time() - self.session_start)
        most_viewed_id = max(self.painting_times, key=lambda k: self.painting_times[k])
        most_viewed_title = self.painting_titles[most_viewed_id]
        most_viewed_seconds = self.painting_times[most_viewed_id]

        heat = self.heatmap.copy()
        if heat.max() > 0:
            heat = heat / heat.max()

        with PdfPages(pdf_path) as pdf:
            # Página 1: resumo
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.patch.set_facecolor("white")
            plt.axis("off")
            plt.text(0.05, 0.92, "Relatório de Mapa de Calor - Sala 3D Controlada pelo Olhar",
                     fontsize=22, fontweight="bold")
            plt.text(0.05, 0.84, f"Duração da sessão: {session_duration:.1f} s", fontsize=14)
            plt.text(0.05, 0.79, f"Amostras de olhar: {self.total_samples}", fontsize=14)
            plt.text(0.05, 0.74, f"Piscadas detectadas: {blink_count}", fontsize=14)
            plt.text(0.05, 0.69, f"Duplas piscadas: {double_blinks}", fontsize=14)
            plt.text(0.05, 0.62, f"Quadro mais observado: {most_viewed_title}", fontsize=16)
            plt.text(0.05, 0.57, f"Tempo acumulado: {most_viewed_seconds:.2f} s", fontsize=14)

            lines = [
                "Interações:",
                "- olhar em um quadro exibe informações",
                "- dupla piscada aproxima a obra",
                "- piscada única afasta / sai do zoom",
                "",
                "Observação:",
                "O mapa de calor abaixo usa as posições do cursor de olhar ao longo da sessão.",
            ]
            y = 0.48
            for line in lines:
                plt.text(0.05, y, line, fontsize=13)
                y -= 0.05

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Página 2: heatmap
            fig, ax = plt.subplots(figsize=(12, 7))
            ax.set_title("Mapa de calor do olhar na sala", fontsize=18)
            if self.last_background_frame is not None:
                ax.imshow(self.last_background_frame)
                ax.imshow(heat, cmap="jet", alpha=0.52, extent=[0, self.width, self.height, 0])
            else:
                ax.imshow(heat, cmap="jet")
            ax.set_xlim([0, self.width])
            ax.set_ylim([self.height, 0])
            ax.set_xlabel("X da janela")
            ax.set_ylabel("Y da janela")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

            # Página 3: análise por quadro
            labels = [self.painting_titles[k] for k in self.painting_times.keys()]
            values = [self.painting_times[k] for k in self.painting_times.keys()]
            hits = [self.painting_hits[k] for k in self.painting_times.keys()]

            fig, axes = plt.subplots(2, 1, figsize=(12, 9))
            axes[0].bar(labels, values)
            axes[0].set_title("Tempo acumulado por quadro (s)")
            axes[0].tick_params(axis="x", rotation=20)

            axes[1].bar(labels, hits)
            axes[1].set_title("Quantidade de amostras por quadro")
            axes[1].tick_params(axis="x", rotation=20)
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


# =============================================================================
# App principal da sala 3D
# =============================================================================

class EyeGazeGalleryApp:
    def __init__(self, camera_index=0, preview=False):
        pygame.init()
        pygame.font.init()

        self.width = 1280
        self.height = 720
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Sala 3D por Rastreamento Ocular")
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("Segoe UI", 30, bold=True)
        self.font_body = pygame.font.SysFont("Segoe UI", 22)
        self.font_small = pygame.font.SysFont("Segoe UI", 18)

        self.renderer = Software3DRenderer(self.width, self.height)
        self.room = GalleryRoom()
        self.report = HeatmapReport(self.width, self.height, self.room)
        self.tracker = EyeTracker(camera_index=camera_index, preview=preview)

        self.running = True
        self.calibration_message = "Pressione C olhando para o centro da sala para calibrar."
        self.cam_pos = np.array([0.0, 1.65, 1.2], dtype=np.float32)
        self.cam_rot = np.eye(3, dtype=np.float32)

        self.current_hover: Optional[Painting] = None
        self.hover_strength = 0.0
        self.hover_start_time = 0.0
        self.zoomed_painting: Optional[Painting] = None
        self.zoom_anim = 0.0

        self.cursor_x = self.width // 2
        self.cursor_y = self.height // 2
        self.cursor_visible = True

        self.session_message = "Olhe para um quadro para ver detalhes."
        self.last_message_time = time.time()
        self.last_dt = 1.0 / 60.0

        self.inspect_card_alpha = 0.0

    def set_message(self, msg: str):
        self.session_message = msg
        self.last_message_time = time.time()

    def _gaze_to_room_ray(self, gaze_vec: np.ndarray):
        g = normalize(gaze_vec.astype(np.float32))

        if g[2] <= 0.05:
            g[2] = 0.05
            g = normalize(g)

        # Após calibração, g aponta "para a frente" com +Z; no mundo da sala, frente é -Z.
        ray_dir_world = normalize(np.array([g[0], g[1], -g[2]], dtype=np.float32))
        ray_origin = self.cam_pos.copy()
        return ray_origin, ray_dir_world

    def _gaze_to_screen_cursor(self, gaze_vec: np.ndarray):
        g = normalize(gaze_vec.astype(np.float32))
        f = (self.width * 0.5) / math.tan(self.renderer.fov / 2.0)
        z = max(0.15, float(g[2]))
        x = int(self.width / 2 + f * (g[0] / z))
        y = int(self.height / 2 - f * (g[1] / z))
        x = int(clamp(x, 0, self.width - 1))
        y = int(clamp(y, 0, self.height - 1))
        return x, y

    def _draw_cursor(self, surf):
        if not self.cursor_visible:
            return
        x, y = self.cursor_x, self.cursor_y
        pygame.draw.circle(surf, (255, 80, 80), (x, y), 10, 2)
        pygame.draw.circle(surf, (255, 80, 80), (x, y), 2)

    def _draw_hud(self, surf, tracker_state):
        pad = 14
        panel = pygame.Surface((420, 150), pygame.SRCALPHA)
        panel.fill((10, 10, 16, 180))
        surf.blit(panel, (12, 12))

        fps_text = self.font_small.render(f"FPS câmera: {tracker_state['fps']:.1f}", True, (230, 230, 230))
        conf_text = self.font_small.render(f"Confiança: {tracker_state['confidence']:.1f}", True, (230, 230, 230))
        blink_text = self.font_small.render(
            f"Piscadas: {tracker_state['total_blinks']} | Duplas: {tracker_state['total_double_blinks']}",
            True, (230, 230, 230)
        )
        cal_text = self.font_small.render(
            "Calibrado" if self.tracker.calibrated else "Sem calibração",
            True,
            (130, 255, 130) if self.tracker.calibrated else (255, 170, 80),
        )

        surf.blit(fps_text, (24, 24))
        surf.blit(conf_text, (24, 52))
        surf.blit(blink_text, (24, 80))
        surf.blit(cal_text, (24, 108))

        msg_bg = pygame.Surface((self.width - 24, 44), pygame.SRCALPHA)
        msg_bg.fill((10, 10, 16, 145))
        surf.blit(msg_bg, (12, self.height - 56))

        message = self.session_message
        if time.time() - self.last_message_time > 5.0 and self.current_hover is None and self.zoomed_painting is None:
            message = "Olhe para um quadro. Dupla piscada aproxima, piscada única afasta."
        msg_text = self.font_body.render(message, True, (245, 245, 245))
        surf.blit(msg_text, (24, self.height - 48))

        if not self.tracker.calibrated:
            t = self.font_body.render(self.calibration_message, True, (255, 240, 120))
            surf.blit(t, (24, self.height - 88))

    def _draw_info_panel(self, surf, painting: Painting):
        panel_w = 430
        panel_h = 220
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((8, 8, 14, 220))

        title = self.font_title.render(painting.title, True, (255, 255, 255))
        artist = self.font_body.render(f"{painting.artist} · {painting.year}", True, (220, 220, 220))
        pid = self.font_small.render(f"ID: {painting.id}", True, (160, 210, 255))

        panel.blit(title, (18, 16))
        panel.blit(artist, (18, 58))
        panel.blit(pid, (18, 88))

        y = 122
        for line in self._wrap_text(painting.description, self.font_small, panel_w - 36):
            txt = self.font_small.render(line, True, (230, 230, 230))
            panel.blit(txt, (18, y))
            y += 24

        panel.blit(self.font_small.render("Dupla piscada para aproximar", True, (255, 225, 120)), (18, panel_h - 48))
        panel.blit(self.font_small.render("Piscada única para afastar", True, (255, 225, 120)), (18, panel_h - 24))

        surf.blit(panel, (self.width - panel_w - 18, 18))

    def _draw_zoom_card(self, surf, painting: Painting):
        self.inspect_card_alpha = lerp(self.inspect_card_alpha, 1.0, 0.14)
        alpha = int(clamp(self.inspect_card_alpha * 255, 0, 255))

        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(180 * self.zoom_anim)))
        surf.blit(overlay, (0, 0))

        card_w = int(920 * (0.8 + 0.2 * self.zoom_anim))
        card_h = int(520 * (0.8 + 0.2 * self.zoom_anim))
        card_x = (self.width - card_w) // 2
        card_y = (self.height - card_h) // 2

        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card.fill((18, 18, 24, alpha))

        margin = 34
        frame_rect = pygame.Rect(margin, margin, int(card_w * 0.48), card_h - 2 * margin)
        info_rect = pygame.Rect(frame_rect.right + 28, margin, card_w - frame_rect.width - 3 * margin, card_h - 2 * margin)

        pygame.draw.rect(card, (250, 244, 232), frame_rect, border_radius=8)
        inner = frame_rect.inflate(-24, -24)
        pygame.draw.rect(card, painting.color, inner, border_radius=6)
        pygame.draw.rect(card, (28, 28, 32), inner.inflate(-20, -20), border_radius=5)

        card.blit(self.font_title.render(painting.title, True, (255, 255, 255)), (info_rect.x, info_rect.y))
        card.blit(self.font_body.render(f"{painting.artist} · {painting.year}", True, (220, 220, 220)), (info_rect.x, info_rect.y + 44))
        card.blit(self.font_small.render(f"Quadro {painting.id}", True, (160, 210, 255)), (info_rect.x, info_rect.y + 78))

        y = info_rect.y + 122
        for line in self._wrap_text(painting.description, self.font_body, info_rect.width - 6):
            card.blit(self.font_body.render(line, True, (235, 235, 235)), (info_rect.x, y))
            y += 30

        tips = [
            "Modo zoom ativo",
            "Piscada única para afastar",
            "Continue olhando para analisar a obra",
        ]
        y += 24
        for tip in tips:
            card.blit(self.font_small.render(tip, True, (255, 230, 130)), (info_rect.x, y))
            y += 26

        pygame.draw.rect(card, (255, 255, 255, alpha), card.get_rect(), 2, border_radius=16)
        surf.blit(card, (card_x, card_y))

    @staticmethod
    def _wrap_text(text, font, max_width):
        words = text.split()
        lines = []
        current = ""
        for w in words:
            test = w if not current else current + " " + w
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines

    def _update_focus(self, gaze_vec, dt):
        ray_origin, ray_dir = self._gaze_to_room_ray(gaze_vec)
        hit = self.room.intersect_painting(ray_origin, ray_dir)

        self.cursor_x, self.cursor_y = self._gaze_to_screen_cursor(gaze_vec)

        if hit.painting is not None:
            if self.current_hover is None or self.current_hover.id != hit.painting.id:
                self.current_hover = hit.painting
                self.hover_start_time = time.time()
                self.set_message(f"Foco em {hit.painting.title}")
            self.hover_strength = min(1.0, self.hover_strength + dt * 2.0)
        else:
            self.hover_strength = max(0.0, self.hover_strength - dt * 2.4)
            if self.hover_strength <= 0.02:
                self.current_hover = None

        self.report.add_gaze(self.cursor_x, self.cursor_y, self.current_hover, dt)

    def _handle_blinks(self):
        if self.tracker.consume_double_blink():
            if self.current_hover is not None:
                self.zoomed_painting = self.current_hover
                self.set_message(f"Zoom em {self.current_hover.title}")
            else:
                self.set_message("Dupla piscada detectada, mas nenhum quadro estava em foco.")

        # Piscada única só afasta se não tiver ocorrido dupla na janela curta
        if self.tracker.consume_single_blink():
            if self.zoomed_painting is not None:
                self.set_message(f"Saindo do zoom de {self.zoomed_painting.title}")
                self.zoomed_painting = None
            else:
                self.set_message("Piscada única detectada.")

    def run(self):
        self.tracker.start()
        self.set_message("Sistema iniciado. Pressione C olhando para o centro para calibrar.")

        try:
            while self.running:
                dt = self.clock.tick(60) / 1000.0
                self.last_dt = dt

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            self.running = False
                        elif event.key == pygame.K_c:
                            self.tracker.calibrate_center()
                            self.set_message("Calibração concluída.")
                        elif event.key == pygame.K_SPACE:
                            # atalho manual: alterna zoom
                            if self.current_hover is not None:
                                self.zoomed_painting = self.current_hover
                                self.set_message(f"Zoom manual em {self.current_hover.title}")
                        elif event.key == pygame.K_BACKSPACE:
                            self.zoomed_painting = None
                            self.set_message("Zoom removido.")

                tracker_state = self.tracker.get_state()
                gaze_vec = self.tracker.get_screen_gaze()
                self._update_focus(gaze_vec, dt)
                self._handle_blinks()

                if self.zoomed_painting is not None:
                    self.zoom_anim = min(1.0, self.zoom_anim + dt * 3.0)
                else:
                    self.zoom_anim = max(0.0, self.zoom_anim - dt * 3.2)
                    if self.zoom_anim <= 0.01:
                        self.inspect_card_alpha = 0.0

                self.renderer.render_room(
                    self.screen,
                    self.room,
                    self.cam_pos,
                    self.cam_rot,
                    self.current_hover,
                    self.hover_strength,
                )

                self._draw_cursor(self.screen)

                if self.current_hover is not None and self.zoomed_painting is None:
                    self._draw_info_panel(self.screen, self.current_hover)

                if self.zoom_anim > 0.01 and self.zoomed_painting is not None:
                    self._draw_zoom_card(self.screen, self.zoomed_painting)

                self._draw_hud(self.screen, tracker_state)
                pygame.display.flip()

                self.report.set_background_frame(self.screen)

        finally:
            self.tracker.stop()
            out_pdf = os.path.abspath("relatorio_mapa_calor.pdf")
            self.report.save_pdf(
                out_pdf,
                blink_count=self.tracker.total_blinks,
                double_blinks=self.tracker.total_double_blinks,
            )
            print(f"Relatório salvo em: {out_pdf}")
            pygame.quit()


# =============================================================================
# Entrada principal
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Sala 3D com rastreamento ocular e relatório PDF")
    parser.add_argument("--camera", type=int, default=0, help="Índice da câmera do olho")
    parser.add_argument("--preview", action="store_true", help="Exibe preview OpenCV do rastreamento")
    return parser.parse_args()


def main():
    args = parse_args()
    app = EyeGazeGalleryApp(camera_index=args.camera, preview=args.preview)
    app.run()


if __name__ == "__main__":
    main()
