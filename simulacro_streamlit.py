from __future__ import annotations

import math
import random
import threading
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import av
import cv2
import numpy as np
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer


Point2D = Tuple[int, int]
Ellipse = Tuple[Tuple[float, float], Tuple[float, float], float]


@dataclass
class TrackerConfig:
    width: int = 640
    height: int = 480
    strict_offset: int = 5
    medium_offset: int = 15
    relaxed_offset: int = 25
    roi_size: int = 250
    kernel_size: int = 5
    min_contour_area: int = 1000
    ratio_thresh: float = 3.0
    max_rays: int = 120
    ray_sample_n: int = 5
    max_intersections: int = 1500
    min_angle_diff_deg: float = 2.0
    smoothing_window: int = 200
    circle_scale: float = 2.0
    pinhole_fx_ratio: float = 0.95
    pinhole_fy_ratio: float = 0.95
    heatmap_decay: float = 0.995
    show_debug_overlay: bool = True


class IrisTracker3D:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with threading.Lock():
            pass
        self.ray_lines: Deque[Ellipse] = deque(maxlen=120)
        self.model_centers: Deque[Point2D] = deque(maxlen=400)
        self.stored_intersections: Deque[Point2D] = deque(maxlen=1500)
        self.prev_model_center_avg: Point2D = (320, 240)
        self.locked_model_center_avg: Point2D = self.prev_model_center_avg
        self.sphere_center_locked_2d: bool = False
        self.last_sphere_center: Optional[np.ndarray] = None
        self.last_gaze_dir: Optional[np.ndarray] = None
        self.calibrated_sphere_center: Optional[np.ndarray] = None
        self.R_gaze_to_screen: np.ndarray = np.eye(3, dtype=np.float32)
        self.center_calibrated: bool = False
        self.latest_result: Dict[str, object] = {}
        self.latest_raw_uv: Optional[Point2D] = None
        self.latest_mapped_uv: Optional[Point2D] = None
        self.affine_2d: Optional[np.ndarray] = None
        self.multi_points_raw: Dict[str, Point2D] = {}
        self.multi_points_target: Dict[str, Point2D] = {}
        self.heatmap: Optional[np.ndarray] = None
        self.latest_frame_size: Point2D = (640, 480)

    @staticmethod
    def crop_to_aspect_ratio(image: np.ndarray, width: int, height: int) -> np.ndarray:
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

        return cv2.resize(cropped_img, (width, height), interpolation=cv2.INTER_AREA)

    @staticmethod
    def apply_binary_threshold(image: np.ndarray, darkest_pixel_value: int, added_threshold: int) -> np.ndarray:
        threshold = int(darkest_pixel_value) + int(added_threshold)
        _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
        return thresholded_image

    @staticmethod
    def get_darkest_area(image: np.ndarray) -> Optional[Point2D]:
        ignore_bounds = 20
        image_skip_size = 10
        search_area = 20
        internal_skip_size = 5

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_sum = float("inf")
        darkest_point: Optional[Point2D] = None

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
    def mask_outside_square(image: np.ndarray, center: Point2D, size: int) -> np.ndarray:
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
    def filter_contours_by_area_and_return_largest(
        contours: List[np.ndarray], pixel_thresh: int, ratio_thresh: float
    ) -> List[np.ndarray]:
        max_area = 0.0
        largest_contour = None
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= pixel_thresh:
                x, y, w, h = cv2.boundingRect(contour)
                if w == 0 or h == 0:
                    continue
                length_to_width_ratio = max(w / h, h / w)
                if length_to_width_ratio <= ratio_thresh and area > max_area:
                    max_area = area
                    largest_contour = contour
        return [largest_contour] if largest_contour is not None else []

    @staticmethod
    def optimize_contours_by_angle(contours: List[np.ndarray], image: np.ndarray) -> np.ndarray:
        if len(contours) < 1 or contours[0] is None or len(contours[0]) == 0:
            return np.empty((0, 1, 2), dtype=np.int32)

        all_contours = np.concatenate(contours[0], axis=0)
        if len(all_contours) < 5:
            return np.empty((0, 1, 2), dtype=np.int32)

        spacing = max(1, int(len(all_contours) / 25))
        filtered_points = []
        centroid = np.mean(all_contours, axis=0)
        _ = image  # only to keep parity with the original signature

        for i in range(0, len(all_contours), 1):
            current_point = all_contours[i]
            prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
            next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

            vec1 = prev_point - current_point
            vec2 = next_point - current_point
            vec_to_centroid = centroid - current_point
            mean_dir = (vec1 + vec2) / 2.0

            if np.linalg.norm(mean_dir) < 1e-6:
                continue

            cos_threshold = np.cos(np.radians(60))
            if float(np.dot(vec_to_centroid, mean_dir)) >= cos_threshold:
                filtered_points.append(current_point)

        if len(filtered_points) < 5:
            return np.empty((0, 1, 2), dtype=np.int32)

        return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))

    @staticmethod
    def check_contour_pixels(contour: np.ndarray, image_shape: Tuple[int, int]) -> List[object]:
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
        absolute_pixel_total_thin = int(np.sum(overlap_thin > 0))
        total_border_pixels = int(np.sum(contour_mask > 0))
        ratio_under_ellipse = absolute_pixel_total_thin / total_border_pixels if total_border_pixels > 0 else 0.0

        return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]

    @staticmethod
    def check_ellipse_goodness(binary_image: np.ndarray, contour: np.ndarray) -> List[float]:
        ellipse_goodness = [0.0, 0.0, 0.0]
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
        if ellipse[1][0] > 0 and ellipse[1][1] > 0:
            ellipse_goodness[2] = min(ellipse[1][1] / ellipse[1][0], ellipse[1][0] / ellipse[1][1])
        return ellipse_goodness

    @staticmethod
    def find_line_intersection(ellipse1: Ellipse, ellipse2: Ellipse) -> Optional[Point2D]:
        (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
        (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

        angle1_rad = np.deg2rad(angle1)
        angle2_rad = np.deg2rad(angle2)

        dx1, dy1 = (minor_axis1 / 2) * np.cos(angle1_rad), (minor_axis1 / 2) * np.sin(angle1_rad)
        dx2, dy2 = (minor_axis2 / 2) * np.cos(angle2_rad), (minor_axis2 / 2) * np.sin(angle2_rad)

        A = np.array([[dx1, -dx2], [dy1, -dy2]], dtype=np.float32)
        B = np.array([cx2 - cx1, cy2 - cy1], dtype=np.float32)

        if abs(float(np.linalg.det(A))) < 1e-6:
            return None

        t1, _ = np.linalg.solve(A, B)
        intersection_x = cx1 + t1 * dx1
        intersection_y = cy1 + t1 * dy1
        return (int(intersection_x), int(intersection_y))

    def compute_average_intersection(
        self, frame: np.ndarray, ray_sample_n: int, max_intersections: int, min_angle_diff_deg: float
    ) -> Optional[Point2D]:
        if len(self.ray_lines) < 2 or ray_sample_n < 2:
            return None

        height, width = frame.shape[:2]
        selected_lines = random.sample(list(self.ray_lines), min(ray_sample_n, len(self.ray_lines)))
        intersections: List[Point2D] = []

        for i in range(len(selected_lines) - 1):
            line1 = selected_lines[i]
            line2 = selected_lines[i + 1]
            angle1 = float(line1[2])
            angle2 = float(line2[2])
            if abs(angle1 - angle2) < min_angle_diff_deg:
                continue

            intersection = self.find_line_intersection(line1, line2)
            if intersection is None:
                continue

            if 0 <= intersection[0] < width and 0 <= intersection[1] < height:
                intersections.append(intersection)
                self.stored_intersections.append(intersection)

        while len(self.stored_intersections) > max_intersections:
            self.stored_intersections.popleft()

        if not intersections or len(self.stored_intersections) == 0:
            return None

        avg_x = int(np.mean([pt[0] for pt in self.stored_intersections]))
        avg_y = int(np.mean([pt[1] for pt in self.stored_intersections]))
        return (avg_x, avg_y)

    @staticmethod
    def rotation_from_a_to_b(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        a = a / np.linalg.norm(a)
        b = b / np.linalg.norm(b)
        v = np.cross(a, b)
        c = float(np.dot(a, b))

        if np.linalg.norm(v) < 1e-6:
            if c > 0:
                return np.eye(3, dtype=np.float32)
            axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            if abs(a[0]) > 0.9:
                axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            v = np.cross(a, axis)
            v = v / np.linalg.norm(v)
            s = float(np.linalg.norm(v))
        else:
            s = float(np.linalg.norm(v))
            v = v / s

        vx, vy, vz = v
        K = np.array(
            [
                [0, -vz, vy],
                [vz, 0, -vx],
                [-vy, vx, 0],
            ],
            dtype=np.float32,
        )
        return np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1 - c) / (s ** 2))

    def compute_gaze_vector(
        self, pupil_x: int, pupil_y: int, center_x: int, center_y: int, screen_width: int, screen_height: int
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        viewport_width = float(screen_width)
        viewport_height = float(screen_height)

        fov_y_deg = 45.0
        aspect_ratio = viewport_width / viewport_height
        far_clip = 100.0
        camera_position = np.array([0.0, 0.0, 3.0], dtype=np.float32)

        fov_y_rad = np.radians(fov_y_deg)
        half_height_far = np.tan(fov_y_rad / 2) * far_clip
        half_width_far = half_height_far * aspect_ratio

        ndc_x = (2.0 * pupil_x) / viewport_width - 1.0
        ndc_y = 1.0 - (2.0 * pupil_y) / viewport_height

        far_x = ndc_x * half_width_far
        far_y = ndc_y * half_height_far
        far_z = camera_position[2] - far_clip
        far_point = np.array([far_x, far_y, far_z], dtype=np.float32)

        ray_origin = camera_position
        ray_direction = far_point - camera_position
        ray_direction /= np.linalg.norm(ray_direction)
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
            t = -float(np.dot(direction, L)) / max(float(np.dot(direction, direction)), 1e-6)
            intersection_point = origin + t * direction
        else:
            sqrt_disc = float(np.sqrt(discriminant))
            t1 = (-b - sqrt_disc) / (2 * a)
            t2 = (-b + sqrt_disc) / (2 * a)
            candidates = [val for val in (t1, t2) if val > 0]
            if not candidates:
                return None, None
            t = min(candidates)
            intersection_point = origin + t * direction

        intersection_local = intersection_point - sphere_center
        norm = float(np.linalg.norm(intersection_local))
        if norm < 1e-6:
            return None, None
        target_direction = intersection_local / norm

        circle_local_center = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
        circle_local_center /= np.linalg.norm(circle_local_center)

        rotation_axis = np.cross(circle_local_center, target_direction)
        rotation_axis_norm = float(np.linalg.norm(rotation_axis))
        if rotation_axis_norm < 1e-6:
            gaze_rotated = circle_local_center
        else:
            rotation_axis /= rotation_axis_norm
            dot = float(np.clip(np.dot(circle_local_center, target_direction), -1.0, 1.0))
            angle_rad = float(np.arccos(dot))
            c_ = float(np.cos(angle_rad))
            s_ = float(np.sin(angle_rad))
            t_ = 1 - c_
            x_, y_, z_ = rotation_axis
            rotation_matrix = np.array(
                [
                    [t_ * x_ * x_ + c_, t_ * x_ * y_ - s_ * z_, t_ * x_ * z_ + s_ * y_],
                    [t_ * x_ * y_ + s_ * z_, t_ * y_ * y_ + c_, t_ * y_ * z_ - s_ * x_],
                    [t_ * x_ * z_ - s_ * y_, t_ * y_ * z_ + s_ * x_, t_ * z_ * z_ + c_],
                ],
                dtype=np.float32,
            )
            gaze_local = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
            gaze_rotated = rotation_matrix @ gaze_local
            gaze_rotated /= np.linalg.norm(gaze_rotated)

        self.last_sphere_center = sphere_center.copy()
        self.last_gaze_dir = gaze_rotated.copy()

        if self.calibrated_sphere_center is not None:
            sphere_center_out = self.calibrated_sphere_center.copy()
        else:
            sphere_center_out = sphere_center.copy()

        return sphere_center_out, gaze_rotated

    def project_gaze_to_uv(self, gaze_dir: np.ndarray, width: int, height: int, cfg: TrackerConfig) -> Optional[Point2D]:
        g = gaze_dir.copy()
        if self.center_calibrated:
            g = self.R_gaze_to_screen @ g

        if g[2] <= 1e-6:
            return None

        fx = width * cfg.pinhole_fx_ratio
        fy = height * cfg.pinhole_fy_ratio
        u = width / 2 + fx * (float(g[0]) / float(g[2]))
        v = height / 2 - fy * (float(g[1]) / float(g[2]))
        u = int(np.clip(u, 0, width - 1))
        v = int(np.clip(v, 0, height - 1))
        self.latest_raw_uv = (u, v)

        if self.affine_2d is not None:
            vec = np.array([u, v, 1.0], dtype=np.float32)
            mapped = self.affine_2d @ vec
            u = int(np.clip(mapped[0], 0, width - 1))
            v = int(np.clip(mapped[1], 0, height - 1))

        self.latest_mapped_uv = (u, v)
        return (u, v)

    def calibrate_center_now(self) -> str:
        if self.last_gaze_dir is None or self.last_sphere_center is None:
            return "Ainda não há vetor de olhar suficiente para calibrar."

        forward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        self.R_gaze_to_screen = self.rotation_from_a_to_b(self.last_gaze_dir, forward)
        self.calibrated_sphere_center = self.last_sphere_center.copy()
        self.center_calibrated = True
        self.sphere_center_locked_2d = True
        self.locked_model_center_avg = self.prev_model_center_avg
        return "Calibração central concluída."

    def lock_current_center(self) -> str:
        self.sphere_center_locked_2d = True
        self.locked_model_center_avg = self.prev_model_center_avg
        return f"Centro 2D travado em {self.locked_model_center_avg}."

    def unlock_current_center(self) -> str:
        self.sphere_center_locked_2d = False
        return "Centro 2D destravado."

    def clear_all_calibration(self) -> str:
        self.center_calibrated = False
        self.R_gaze_to_screen = np.eye(3, dtype=np.float32)
        self.calibrated_sphere_center = None
        self.affine_2d = None
        self.multi_points_raw.clear()
        self.multi_points_target.clear()
        self.sphere_center_locked_2d = False
        return "Calibração central e multiponto removidas."

    def add_multi_calibration_point(self, label: str, target: Point2D) -> str:
        if self.latest_raw_uv is None:
            return "Ainda não há ponto bruto do olhar para salvar."
        self.multi_points_raw[label] = self.latest_raw_uv
        self.multi_points_target[label] = target
        return f"Ponto '{label}' salvo. bruto={self.latest_raw_uv} alvo={target}"

    def solve_multi_calibration(self) -> str:
        if len(self.multi_points_raw) < 3:
            return "São necessários ao menos 3 pontos para resolver a calibração multiponto."

        labels = sorted(self.multi_points_raw.keys())
        src = np.array([self.multi_points_raw[k] for k in labels], dtype=np.float32)
        dst = np.array([self.multi_points_target[k] for k in labels], dtype=np.float32)

        affine, inliers = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=10.0)
        if affine is None:
            if len(src) >= 3:
                affine = cv2.getAffineTransform(src[:3], dst[:3])
            else:
                return "Não foi possível ajustar a calibração multiponto."

        self.affine_2d = affine.astype(np.float32)
        inlier_count = int(inliers.sum()) if inliers is not None else len(src)
        return f"Calibração multiponto resolvida com {inlier_count}/{len(src)} pontos válidos."

    def reset_heatmap(self) -> None:
        if self.heatmap is not None:
            self.heatmap[:] = 0

    def update_heatmap(self, uv: Optional[Point2D], width: int, height: int, cfg: TrackerConfig) -> None:
        if uv is None:
            return
        if self.heatmap is None or self.heatmap.shape != (height, width):
            self.heatmap = np.zeros((height, width), dtype=np.float32)

        self.heatmap *= cfg.heatmap_decay
        cv2.circle(self.heatmap, uv, 18, 1.0, -1)
        cv2.GaussianBlur(self.heatmap, (0, 0), 7, dst=self.heatmap)

    def get_heatmap_bgr(self) -> Optional[np.ndarray]:
        if self.heatmap is None or float(self.heatmap.max()) <= 1e-9:
            return None

        normalized = self.heatmap / max(float(self.heatmap.max()), 1e-6)
        heat_u8 = np.uint8(np.clip(normalized * 255.0, 0, 255))
        heat_color = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET)
        return heat_color

    def process_frame(self, frame: np.ndarray, cfg: TrackerConfig) -> np.ndarray:
        frame = self.crop_to_aspect_ratio(frame, cfg.width, cfg.height)
        self.latest_frame_size = (cfg.width, cfg.height)

        darkest_point = self.get_darkest_area(frame)
        if darkest_point is None:
            return frame

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        darkest_pixel_value = int(gray_frame[darkest_point[1], darkest_point[0]])

        thresholded_image_strict = self.apply_binary_threshold(gray_frame, darkest_pixel_value, cfg.strict_offset)
        thresholded_image_strict = self.mask_outside_square(thresholded_image_strict, darkest_point, cfg.roi_size)

        thresholded_image_medium = self.apply_binary_threshold(gray_frame, darkest_pixel_value, cfg.medium_offset)
        thresholded_image_medium = self.mask_outside_square(thresholded_image_medium, darkest_point, cfg.roi_size)

        thresholded_image_relaxed = self.apply_binary_threshold(gray_frame, darkest_pixel_value, cfg.relaxed_offset)
        thresholded_image_relaxed = self.mask_outside_square(thresholded_image_relaxed, darkest_point, cfg.roi_size)

        image_array = [thresholded_image_relaxed, thresholded_image_medium, thresholded_image_strict]
        kernel = np.ones((cfg.kernel_size, cfg.kernel_size), np.uint8)

        final_contours: List[np.ndarray] = []
        final_rotated_rect: Optional[Ellipse] = None
        best_score = -1.0
        best_center: Optional[Point2D] = None

        for binary in image_array:
            dilated = cv2.dilate(binary, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reduced_contours = self.filter_contours_by_area_and_return_largest(
                contours, cfg.min_contour_area, cfg.ratio_thresh
            )
            if len(reduced_contours) == 0 or reduced_contours[0] is None or len(reduced_contours[0]) <= 5:
                continue

            current_goodness = self.check_ellipse_goodness(dilated, reduced_contours[0])
            ellipse = cv2.fitEllipse(reduced_contours[0])
            total_pixels = self.check_contour_pixels(reduced_contours[0], dilated.shape)
            score = float(current_goodness[0]) * float(total_pixels[0]) * float(total_pixels[0]) * max(float(total_pixels[1]), 1e-6)

            if score > best_score:
                best_score = score
                final_contours = reduced_contours
                best_center = tuple(map(int, ellipse[0]))

        pupil_x = pupil_y = None
        if final_contours:
            optimized = self.optimize_contours_by_angle(final_contours, gray_frame)
            if isinstance(optimized, np.ndarray) and len(optimized) > 5:
                ellipse = cv2.fitEllipse(optimized)
                final_rotated_rect = ellipse
                pupil_x, pupil_y = map(int, ellipse[0])
                self.ray_lines.append(final_rotated_rect)
                while len(self.ray_lines) > cfg.max_rays:
                    self.ray_lines.popleft()
        elif best_center is not None:
            pupil_x, pupil_y = best_center

        model_center = self.compute_average_intersection(
            frame, cfg.ray_sample_n, cfg.max_intersections, cfg.min_angle_diff_deg
        )

        if not self.sphere_center_locked_2d:
            if model_center is not None:
                self.model_centers.append(model_center)
                avg_x = int(np.mean([p[0] for p in self.model_centers]))
                avg_y = int(np.mean([p[1] for p in self.model_centers]))
                model_center_average = (avg_x, avg_y)
            else:
                model_center_average = self.prev_model_center_avg

            if model_center_average[0] != 0:
                self.prev_model_center_avg = model_center_average
                self.locked_model_center_avg = model_center_average
        else:
            model_center_average = self.locked_model_center_avg

        if pupil_x is None or pupil_y is None:
            return frame

        if len(self.model_centers) >= 10:
            distances = [
                math.hypot(pupil_x - center[0], pupil_y - center[1])
                for center in list(self.model_centers)[-100:]
            ]
            adaptive_radius = max(60, int(np.percentile(distances, 95)))
        else:
            adaptive_radius = 120

        cv2.rectangle(
            frame,
            (max(0, darkest_point[0] - cfg.roi_size // 2), max(0, darkest_point[1] - cfg.roi_size // 2)),
            (min(cfg.width - 1, darkest_point[0] + cfg.roi_size // 2), min(cfg.height - 1, darkest_point[1] + cfg.roi_size // 2)),
            (90, 90, 90),
            1,
        )
        cv2.circle(frame, darkest_point, 4, (0, 255, 255), -1)
        cv2.circle(frame, model_center_average, adaptive_radius, (255, 50, 50), 2)
        cv2.circle(frame, model_center_average, 8, (255, 255, 0), -1)
        cv2.circle(frame, (pupil_x, pupil_y), 5, (255, 255, 255), -1)

        if final_rotated_rect is not None:
            cv2.ellipse(frame, final_rotated_rect, (20, 255, 255), 2)
            cv2.line(frame, model_center_average, (pupil_x, pupil_y), (255, 150, 50), 2)

            dx = pupil_x - model_center_average[0]
            dy = pupil_y - model_center_average[1]
            extended_x = int(model_center_average[0] + cfg.circle_scale * dx)
            extended_y = int(model_center_average[1] + cfg.circle_scale * dy)
            cv2.line(frame, (pupil_x, pupil_y), (extended_x, extended_y), (200, 255, 0), 3)

        sphere_center, gaze_dir = self.compute_gaze_vector(
            pupil_x, pupil_y, model_center_average[0], model_center_average[1], cfg.width, cfg.height
        )

        gaze_uv = None
        if sphere_center is not None and gaze_dir is not None:
            gaze_uv = self.project_gaze_to_uv(gaze_dir, cfg.width, cfg.height, cfg)
            self.update_heatmap(gaze_uv, cfg.width, cfg.height, cfg)
            if gaze_uv is not None:
                cv2.circle(frame, gaze_uv, 8, (0, 0, 255), -1)

        if cfg.show_debug_overlay and sphere_center is not None and gaze_dir is not None:
            origin_text = f"Origem: ({sphere_center[0]:.2f}, {sphere_center[1]:.2f}, {sphere_center[2]:.2f})"
            dir_text = f"Direcao: ({gaze_dir[0]:.2f}, {gaze_dir[1]:.2f}, {gaze_dir[2]:.2f})"
            raw_text = f"Bruto: {self.latest_raw_uv if self.latest_raw_uv else 'None'}"
            map_text = f"Mapeado: {self.latest_mapped_uv if self.latest_mapped_uv else 'None'}"
            status = []
            status.append("Centro OK" if self.center_calibrated else "Centro OFF")
            status.append("Multi OK" if self.affine_2d is not None else "Multi OFF")
            status.append("2D travado" if self.sphere_center_locked_2d else "2D livre")
            status_text = " | ".join(status)

            for idx, text in enumerate([origin_text, dir_text, raw_text, map_text, status_text]):
                y = frame.shape[0] - 75 + idx * 15
                cv2.putText(frame, text, (11, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
                cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 1)

        self.latest_result = {
            "darkest_point": darkest_point,
            "pupil_center": (pupil_x, pupil_y),
            "model_center": model_center_average,
            "sphere_center": sphere_center,
            "gaze_dir": gaze_dir,
            "raw_uv": self.latest_raw_uv,
            "mapped_uv": self.latest_mapped_uv,
            "center_calibrated": self.center_calibrated,
            "has_multi_calibration": self.affine_2d is not None,
        }
        return frame


TRACKER = IrisTracker3D()
CONFIG_LOCK = threading.Lock()
CURRENT_CONFIG = TrackerConfig()


def get_config() -> TrackerConfig:
    with CONFIG_LOCK:
        return CURRENT_CONFIG


def set_config(cfg: TrackerConfig) -> None:
    global CURRENT_CONFIG
    with CONFIG_LOCK:
        CURRENT_CONFIG = cfg
        TRACKER.ray_lines = deque(TRACKER.ray_lines, maxlen=cfg.max_rays)
        TRACKER.stored_intersections = deque(TRACKER.stored_intersections, maxlen=cfg.max_intersections)


TARGET_LABELS = {
    "TL": lambda w, h: (int(w * 0.10), int(h * 0.10)),
    "TR": lambda w, h: (int(w * 0.90), int(h * 0.10)),
    "BL": lambda w, h: (int(w * 0.10), int(h * 0.90)),
    "BR": lambda w, h: (int(w * 0.90), int(h * 0.90)),
    "C": lambda w, h: (int(w * 0.50), int(h * 0.50)),
}


def video_frame_callback(frame: av.VideoFrame) -> av.VideoFrame:
    image = frame.to_ndarray(format="bgr24")
    cfg = get_config()
    processed = TRACKER.process_frame(image, cfg)
    return av.VideoFrame.from_ndarray(processed, format="bgr24")


def render_sidebar() -> None:
    st.sidebar.header("Controles do rastreador")

    cfg = TrackerConfig(
        width=st.sidebar.select_slider("Largura", options=[320, 480, 640, 800], value=640),
        height=st.sidebar.select_slider("Altura", options=[240, 360, 480, 600], value=480),
        strict_offset=st.sidebar.slider("Threshold strict", 0, 30, 5),
        medium_offset=st.sidebar.slider("Threshold medium", 0, 40, 15),
        relaxed_offset=st.sidebar.slider("Threshold relaxed", 0, 60, 25),
        roi_size=st.sidebar.slider("Tamanho da ROI", 120, 360, 250),
        kernel_size=st.sidebar.select_slider("Kernel morfológico", options=[3, 5, 7, 9], value=5),
        min_contour_area=st.sidebar.slider("Área mínima do contorno", 100, 5000, 1000, step=50),
        ratio_thresh=st.sidebar.slider("Razão máxima largura/altura", 1.1, 6.0, 3.0, step=0.1),
        max_rays=st.sidebar.slider("Máximo de raios", 20, 300, 120),
        ray_sample_n=st.sidebar.slider("Raios por interseção", 2, 20, 5),
        max_intersections=st.sidebar.slider("Máximo de interseções", 50, 3000, 1500, step=50),
        min_angle_diff_deg=st.sidebar.slider("Diferença angular mínima", 0.5, 20.0, 2.0, step=0.5),
        smoothing_window=st.sidebar.slider("Janela de suavização", 10, 400, 200),
        circle_scale=st.sidebar.slider("Escala da linha do olhar", 1.0, 4.0, 2.0, step=0.1),
        pinhole_fx_ratio=st.sidebar.slider("Projeção FX", 0.2, 2.0, 0.95, step=0.05),
        pinhole_fy_ratio=st.sidebar.slider("Projeção FY", 0.2, 2.0, 0.95, step=0.05),
        heatmap_decay=st.sidebar.slider("Decaimento do heatmap", 0.900, 1.000, 0.995, step=0.001),
        show_debug_overlay=st.sidebar.toggle("Mostrar overlay técnico", value=True),
    )
    set_config(cfg)

    st.sidebar.subheader("Calibração")
    if st.sidebar.button("Calibrar centro agora", use_container_width=True):
        st.sidebar.success(TRACKER.calibrate_center_now())

    cols = st.sidebar.columns(2)
    if cols[0].button("Travar centro 2D", use_container_width=True):
        cols[0].success(TRACKER.lock_current_center())
    if cols[1].button("Destravar centro 2D", use_container_width=True):
        cols[1].success(TRACKER.unlock_current_center())

    if st.sidebar.button("Limpar calibrações", use_container_width=True):
        st.sidebar.warning(TRACKER.clear_all_calibration())

    if st.sidebar.button("Resetar tracker", use_container_width=True):
        TRACKER.reset()
        st.sidebar.info("Tracker resetado.")

    if st.sidebar.button("Resetar heatmap", use_container_width=True):
        TRACKER.reset_heatmap()
        st.sidebar.info("Heatmap resetado.")

    st.sidebar.subheader("Calibração multiponto")
    w, h = cfg.width, cfg.height
    cols = st.sidebar.columns(2)
    messages = []
    buttons = [
        (cols[0], "Salvar TL", "TL"),
        (cols[1], "Salvar TR", "TR"),
    ]
    for col, label, key in buttons:
        if col.button(label, use_container_width=True):
            messages.append(TRACKER.add_multi_calibration_point(key, TARGET_LABELS[key](w, h)))

    cols = st.sidebar.columns(2)
    buttons = [
        (cols[0], "Salvar BL", "BL"),
        (cols[1], "Salvar BR", "BR"),
    ]
    for col, label, key in buttons:
        if col.button(label, use_container_width=True):
            messages.append(TRACKER.add_multi_calibration_point(key, TARGET_LABELS[key](w, h)))

    if st.sidebar.button("Salvar Centro", use_container_width=True):
        messages.append(TRACKER.add_multi_calibration_point("C", TARGET_LABELS["C"](w, h)))

    if st.sidebar.button("Resolver multiponto", use_container_width=True):
        messages.append(TRACKER.solve_multi_calibration())

    for msg in messages:
        st.sidebar.info(msg)

    if TRACKER.multi_points_raw:
        st.sidebar.caption(f"Pontos salvos: {sorted(TRACKER.multi_points_raw.keys())}")


def render_status() -> None:
    result = TRACKER.latest_result
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pupila", str(result.get("pupil_center", "-")))
    col2.metric("Centro ocular 2D", str(result.get("model_center", "-")))
    col3.metric("Bruto", str(result.get("raw_uv", "-")))
    col4.metric("Mapeado", str(result.get("mapped_uv", "-")))

    with st.expander("Resumo técnico"):
        st.json(
            {
                "center_calibrated": bool(result.get("center_calibrated", False)),
                "has_multi_calibration": bool(result.get("has_multi_calibration", False)),
                "sphere_center": (
                    result.get("sphere_center").tolist() if isinstance(result.get("sphere_center"), np.ndarray) else None
                ),
                "gaze_dir": result.get("gaze_dir").tolist() if isinstance(result.get("gaze_dir"), np.ndarray) else None,
                "stored_rays": len(TRACKER.ray_lines),
                "stored_intersections": len(TRACKER.stored_intersections),
            }
        )


def render_heatmap_section() -> None:
    st.subheader("Heatmap do olhar")
    heatmap_bgr = TRACKER.get_heatmap_bgr()
    if heatmap_bgr is None:
        st.info("O heatmap aparecerá depois que o olhar começar a ser projetado.")
        return

    heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)
    st.image(heatmap_rgb, caption="Mapa de calor acumulado", use_container_width=True)

    success, png_bytes = cv2.imencode(".png", heatmap_bgr)
    if success:
        st.download_button(
            "Baixar heatmap PNG",
            data=png_bytes.tobytes(),
            file_name="heatmap_iris.png",
            mime="image/png",
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="Rastreamento de Íris 3D", layout="wide")
    st.title("Rastreamento de íris/pupila em Streamlit")
    st.write(
        "Esta versão foi adaptada para web. Ela mantém a lógica do seu código: limiarização da pupila, "
        "ajuste de elipse, projeção de raios, interseção para estimar o centro da esfera ocular, "
        "vetor de olhar 3D e calibração central/multiponto."
    )
    st.caption(
        "Uso: clique em START, permita a câmera, olhe para o centro e clique em 'Calibrar centro agora'. "
        "Depois, se quiser mais precisão, salve TL/TR/BL/BR/C e resolva o multiponto."
    )

    render_sidebar()

    rtc_ctx = webrtc_streamer(
        key="iris-tracker-3d",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={
            "video": {"width": {"ideal": get_config().width}, "height": {"ideal": get_config().height}},
            "audio": False,
        },
        video_frame_callback=video_frame_callback,
        async_processing=True,
    )

    if rtc_ctx.state.playing:
        st.success("Câmera ativa.")
    else:
        st.info("Clique em START para iniciar a câmera.")

    render_status()
    render_heatmap_section()


if __name__ == "__main__":
    main()
