import cv2
import random
import math
import numpy as np
import tkinter as tk
from tkinter import ttk
import time
from dataclasses import dataclass

# =========================================================
# SIMULACRO + RASTREAMENTO OCULAR INTEGRADO
# =========================================================
# Este arquivo integra o pipeline de rastreamento ocular enviado pelo usuário
# (darkest area + threshold + ellipse + compute_gaze_vector)
# com uma galeria interativa do projeto Simulacro.
#
# Controles:
#   Q  -> sair
#   C  -> recalibrar o centro do olhar
#   R  -> resetar zoom e seleção
#   P  -> pausar / continuar
#
# Regras de blink nesta versão:
#   1 piscada  -> afasta
#   2 piscadas rápidas -> aproxima
#
# Fluxo:
#   - o rastreador ocular calcula um ponto de gaze 2D
#   - esse ponto vira o cursor da galeria
#   - manter o olhar ~0.9s sobre um quadro seleciona a obra
#   - 2 piscadas rápidas aproximam a obra em foco
#   - 1 piscada afasta
# =========================================================

# --------------------------
# Globais do rastreador ocular original
# --------------------------
ray_lines = []
model_centers = []
max_rays = 100
prev_model_center_avg = (320, 240)
max_observed_distance = 0
stored_intersections = []

last_sphere_center = None
last_gaze_dir = None
calibrated = False
R_gaze_to_cam = np.eye(3, dtype=np.float32)
calibrated_sphere_center = None
sphere_center_locked_2d = False
locked_model_center_avg = prev_model_center_avg

EXT_WIDTH = 1280
EXT_HEIGHT = 720
EXT_CX = EXT_WIDTH // 2
EXT_CY = EXT_HEIGHT // 2
EXT_FX = 950.0
EXT_FY = 950.0
circle_x = EXT_CX
circle_y = EXT_CY

# --------------------------
# Helpers gerais
# --------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t


# --------------------------
# Funções originais do código enviado
# --------------------------
def detect_cameras(max_cams=10):
    available_cameras = []
    for i in range(max_cams):
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        cap.set(cv2.CAP_PROP_FPS, 30)
        if cap.isOpened():
            available_cameras.append(i)
            cap.release()
    return available_cameras


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


def apply_binary_threshold(image, darkestPixelValue, addedThreshold):
    threshold = darkestPixelValue + addedThreshold
    _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    return thresholded_image


def get_darkest_area(image):
    ignoreBounds = 20
    imageSkipSize = 10
    searchArea = 20
    internalSkipSize = 5

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    min_sum = float('inf')
    darkest_point = None

    for y in range(ignoreBounds, gray.shape[0] - ignoreBounds, imageSkipSize):
        for x in range(ignoreBounds, gray.shape[1] - ignoreBounds, imageSkipSize):
            current_sum = 0
            num_pixels = 0
            for dy in range(0, searchArea, internalSkipSize):
                if y + dy >= gray.shape[0]:
                    break
                for dx in range(0, searchArea, internalSkipSize):
                    if x + dx >= gray.shape[1]:
                        break
                    current_sum += gray[y + dy][x + dx]
                    num_pixels += 1

            if current_sum < min_sum and num_pixels > 0:
                min_sum = current_sum
                darkest_point = (x + searchArea // 2, y + searchArea // 2)

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
    if len(contours) < 1:
        return contours

    all_contours = np.concatenate(contours[0], axis=0)
    if len(all_contours) < 10:
        return np.array(all_contours, dtype=np.int32).reshape((-1, 1, 2))

    spacing = max(1, int(len(all_contours) / 25))
    filtered_points = []
    centroid = np.mean(all_contours, axis=0)

    for i in range(0, len(all_contours), 1):
        current_point = all_contours[i]
        prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
        next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

        vec1 = prev_point - current_point
        vec2 = next_point - current_point

        with np.errstate(invalid='ignore'):
            denom = (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            if denom <= 1e-6:
                continue
            _ = np.arccos(np.clip(np.dot(vec1, vec2) / denom, -1.0, 1.0))

        vec_to_centroid = centroid - current_point
        cos_threshold = np.cos(np.radians(60))

        mean_vec = (vec1 + vec2) / 2
        if np.dot(vec_to_centroid, mean_vec) >= cos_threshold:
            filtered_points.append(current_point)

    if not filtered_points:
        filtered_points = all_contours

    return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))


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
            if length_to_width_ratio <= ratio_thresh:
                if area > max_area:
                    max_area = area
                    largest_contour = contour

    return [largest_contour] if largest_contour is not None else []


def check_contour_pixels(contour, image_shape, debug_mode_on):
    if len(contour) < 5:
        return [0, 0, np.zeros(image_shape, dtype=np.uint8)]

    contour_mask = np.zeros(image_shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, (255), 1)

    ellipse_mask_thick = np.zeros(image_shape, dtype=np.uint8)
    ellipse_mask_thin = np.zeros(image_shape, dtype=np.uint8)
    ellipse = cv2.fitEllipse(contour)

    cv2.ellipse(ellipse_mask_thick, ellipse, (255), 10)
    cv2.ellipse(ellipse_mask_thin, ellipse, (255), 4)

    overlap_thick = cv2.bitwise_and(contour_mask, ellipse_mask_thick)
    overlap_thin = cv2.bitwise_and(contour_mask, ellipse_mask_thin)

    absolute_pixel_total_thick = np.sum(overlap_thick > 0)
    absolute_pixel_total_thin = np.sum(overlap_thin > 0)

    total_border_pixels = np.sum(contour_mask > 0)
    ratio_under_ellipse = absolute_pixel_total_thin / total_border_pixels if total_border_pixels > 0 else 0

    return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]


def check_ellipse_goodness(binary_image, contour, debug_mode_on):
    ellipse_goodness = [0, 0, 0]
    if len(contour) < 5:
        return ellipse_goodness

    ellipse = cv2.fitEllipse(contour)
    mask = np.zeros_like(binary_image)
    cv2.ellipse(mask, ellipse, (255), -1)

    ellipse_area = np.sum(mask == 255)
    covered_pixels = np.sum((binary_image == 255) & (mask == 255))

    if ellipse_area == 0:
        return ellipse_goodness

    ellipse_goodness[0] = covered_pixels / ellipse_area
    axes_lengths = ellipse[1]
    a0, a1 = axes_lengths[0], axes_lengths[1]
    if a0 <= 1e-6 or a1 <= 1e-6:
        ellipse_goodness[2] = 0
    else:
        ellipse_goodness[2] = min(a1 / a0, a0 / a1)

    return ellipse_goodness


def update_and_average_point(point_list, new_point, N):
    point_list.append(new_point)
    if len(point_list) > N:
        point_list.pop(0)

    if not point_list:
        return None

    avg_x = int(np.mean([p[0] for p in point_list]))
    avg_y = int(np.mean([p[1] for p in point_list]))
    return (avg_x, avg_y)


def draw_orthogonal_ray(image, ellipse, length=100, color=(0, 255, 0), thickness=1):
    (cx, cy), (major_axis, minor_axis), angle = ellipse
    angle_rad = np.deg2rad(angle)
    normal_dx = (minor_axis / 2) * np.cos(angle_rad)
    normal_dy = (minor_axis / 2) * np.sin(angle_rad)

    minor_half = max(minor_axis / 2, 1e-6)
    pt1 = (int(cx - length * normal_dx / minor_half), int(cy - length * normal_dy / minor_half))
    pt2 = (int(cx + length * normal_dx / minor_half), int(cy + length * normal_dy / minor_half))
    cv2.line(image, pt1, pt2, color, thickness)
    return image


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


def prune_intersections(intersections, maximum_intersections):
    if len(intersections) <= maximum_intersections:
        return intersections
    return intersections[-maximum_intersections:]


def compute_average_intersection(frame, ray_lines, N, M, spacing):
    global stored_intersections

    if len(ray_lines) < 2 or N < 2:
        return (0, 0)

    height, width = frame.shape[:2]
    selected_lines = random.sample(ray_lines, min(N, len(ray_lines)))
    intersections = []

    for i in range(len(selected_lines) - 1):
        line1 = selected_lines[i]
        line2 = selected_lines[i + 1]
        angle1 = line1[2]
        angle2 = line2[2]

        if abs(angle1 - angle2) >= 2:
            intersection = find_line_intersection(line1, line2)
            if intersection and (0 <= intersection[0] < width) and (0 <= intersection[1] < height):
                intersections.append(intersection)
                stored_intersections.append(intersection)

    if len(stored_intersections) > M:
        stored_intersections = prune_intersections(stored_intersections, M)

    if not intersections or not stored_intersections:
        return None

    avg_x = np.mean([pt[0] for pt in stored_intersections])
    avg_y = np.mean([pt[1] for pt in stored_intersections])
    return (int(avg_x), int(avg_y))


def rotation_from_a_to_b(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)

    v = np.cross(a, b)
    c = np.dot(a, b)

    if np.linalg.norm(v) < 1e-6:
        if c > 0:
            return np.eye(3, dtype=np.float32)
        axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(a[0]) > 0.9:
            axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        v = np.cross(a, axis)
        v = v / np.linalg.norm(v)
        s = np.linalg.norm(v)
    else:
        s = np.linalg.norm(v)
        v = v / s

    vx, vy, vz = v
    K = np.array([
        [0, -vz, vy],
        [vz, 0, -vx],
        [-vy, vx, 0]
    ], dtype=np.float32)

    if s <= 1e-6:
        return np.eye(3, dtype=np.float32)

    R = np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1 - c) / (s ** 2))
    return R


def update_gaze_circle_from_current_gaze():
    global circle_x, circle_y, last_gaze_dir, calibrated

    if not calibrated or last_gaze_dir is None:
        return

    g = R_gaze_to_cam @ last_gaze_dir
    if g[2] <= 1e-6:
        return

    u = EXT_CX + EXT_FX * (g[0] / g[2])
    v = EXT_CY - EXT_FY * (g[1] / g[2])

    u = int(np.clip(u, 0, EXT_WIDTH - 1))
    v = int(np.clip(v, 0, EXT_HEIGHT - 1))

    circle_x, circle_y = u, v


def compute_gaze_vector(x, y, center_x, center_y, screen_width=640, screen_height=480):
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
    ray_direction /= np.linalg.norm(ray_direction)
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
        t = -np.dot(direction, L) / np.dot(direction, direction)
        intersection_point = origin + t * direction
        intersection_local = intersection_point - sphere_center
        target_direction = intersection_local / np.linalg.norm(intersection_local)
    else:
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
            return None, None

        intersection_point = origin + t * direction
        intersection_local = intersection_point - sphere_center
        target_direction = intersection_local / np.linalg.norm(intersection_local)

    circle_local_center = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
    circle_local_center /= np.linalg.norm(circle_local_center)

    rotation_axis = np.cross(circle_local_center, target_direction)
    rotation_axis_norm = np.linalg.norm(rotation_axis)
    if rotation_axis_norm < 1e-6:
        gaze_rotated = circle_local_center.copy()
    else:
        rotation_axis /= rotation_axis_norm
        dot = np.dot(circle_local_center, target_direction)
        dot = np.clip(dot, -1.0, 1.0)
        angle_rad = np.arccos(dot)

        cc = np.cos(angle_rad)
        ss = np.sin(angle_rad)
        tt = 1 - cc
        x_, y_, z_ = rotation_axis

        rotation_matrix = np.array([
            [tt * x_ * x_ + cc, tt * x_ * y_ - ss * z_, tt * x_ * z_ + ss * y_],
            [tt * x_ * y_ + ss * z_, tt * y_ * y_ + cc, tt * y_ * z_ - ss * x_],
            [tt * x_ * z_ - ss * y_, tt * y_ * z_ + ss * x_, tt * z_ * z_ + cc]
        ], dtype=np.float32)

        gaze_local = np.array([0.0, 0.0, inner_radius], dtype=np.float32)
        gaze_rotated = rotation_matrix @ gaze_local
        gaze_rotated /= np.linalg.norm(gaze_rotated)

    global last_sphere_center, last_gaze_dir, calibrated_sphere_center
    last_sphere_center = sphere_center.copy()
    last_gaze_dir = gaze_rotated.copy()

    sphere_center_out = calibrated_sphere_center if calibrated_sphere_center is not None else sphere_center
    return sphere_center_out, gaze_rotated


def calibrate_gaze_to_external():
    global calibrated, R_gaze_to_cam, calibrated_sphere_center
    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg

    if last_gaze_dir is None or last_sphere_center is None:
        print("Calibration failed: no gaze vector / origin available yet.")
        return

    forward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    R_gaze_to_cam = rotation_from_a_to_b(last_gaze_dir, forward)
    calibrated_sphere_center = last_sphere_center.copy()
    sphere_center_locked_2d = True
    locked_model_center_avg = prev_model_center_avg
    calibrated = True
    print("Calibration complete. 2D sphere center locked at:", locked_model_center_avg)


# --------------------------
# Resultados do frame
# --------------------------
@dataclass
class EyeFrameResult:
    ellipse: object = None
    center_x: int = None
    center_y: int = None
    eye_center: tuple = None
    gaze_dir: np.ndarray = None
    gaze_screen: tuple = None
    openness: float = 0.0
    confidence: float = 0.0
    debug_frame: np.ndarray = None
    threshold_frame: np.ndarray = None


# --------------------------
# Integração do rastreador com retorno estruturado
# --------------------------
def process_frames(thresholded_image_strict, thresholded_image_medium, thresholded_image_relaxed,
                   frame, gray_frame, darkest_point, debug_mode_on=False, render_cv_window=False):
    global ray_lines, max_rays, prev_model_center_avg, max_observed_distance
    global sphere_center_locked_2d, locked_model_center_avg, model_centers

    kernel = np.ones((5, 5), np.uint8)
    image_array = [thresholded_image_relaxed, thresholded_image_medium, thresholded_image_strict]

    final_image = image_array[0]
    final_contours = []
    final_rotated_rect = None
    goodness = 0
    best_center_x = None
    best_center_y = None
    best_openness = 0.0

    for binary_img in image_array:
        dilated_image = cv2.dilate(binary_img, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        reduced_contours = filter_contours_by_area_and_return_largest(contours, 1000, 3)

        if len(reduced_contours) > 0 and reduced_contours[0] is not None and len(reduced_contours[0]) >= 5:
            current_goodness = check_ellipse_goodness(dilated_image, reduced_contours[0], debug_mode_on)
            ellipse = cv2.fitEllipse(reduced_contours[0])
            center_x, center_y = map(int, ellipse[0])
            total_pixels = check_contour_pixels(reduced_contours[0], dilated_image.shape, debug_mode_on)
            current_score = current_goodness[0] * max(1, total_pixels[0]) * max(0.01, total_pixels[1])

            major_axis = max(ellipse[1][0], ellipse[1][1], 1e-6)
            minor_axis = min(ellipse[1][0], ellipse[1][1], 1e-6)
            openness = float(minor_axis / max(major_axis, 1e-6))

            if current_score > goodness:
                goodness = current_score
                final_contours = reduced_contours
                final_image = dilated_image
                final_rotated_rect = ellipse
                best_center_x = center_x
                best_center_y = center_y
                best_openness = openness

    debug_frame = frame.copy()
    model_center_average = (320, 240)

    if final_contours and final_contours[0] is not None:
        optimized = optimize_contours_by_angle(final_contours, gray_frame)
        if optimized is not None and len(optimized) >= 5:
            final_contours = [optimized]
            final_rotated_rect = cv2.fitEllipse(final_contours[0])
            best_center_x, best_center_y = map(int, final_rotated_rect[0])
            major_axis = max(final_rotated_rect[1][0], final_rotated_rect[1][1], 1e-6)
            minor_axis = min(final_rotated_rect[1][0], final_rotated_rect[1][1], 1e-6)
            best_openness = float(minor_axis / max(major_axis, 1e-6))

            ray_lines.append(final_rotated_rect)
            if len(ray_lines) > max_rays:
                num_to_remove = len(ray_lines) - max_rays
                ray_lines = ray_lines[num_to_remove:]

            model_center = compute_average_intersection(frame, ray_lines, 5, 1500, 5)
            if not sphere_center_locked_2d:
                if model_center is not None:
                    model_center_average = update_and_average_point(model_centers, model_center, 200)
                else:
                    model_center_average = prev_model_center_avg

                if model_center_average and model_center_average[0] != 0:
                    prev_model_center_avg = model_center_average
                    locked_model_center_avg = model_center_average
            else:
                model_center_average = locked_model_center_avg

            if len(model_centers) >= 20 and best_center_x is not None:
                distance = math.sqrt((best_center_x - model_center_average[0]) ** 2 + (best_center_y - model_center_average[1]) ** 2)
                if distance > max_observed_distance:
                    max_observed_distance = distance
            max_observed_distance = max(max_observed_distance, 160)

            cv2.circle(debug_frame, model_center_average, int(max_observed_distance), (255, 50, 50), 2)
            cv2.circle(debug_frame, model_center_average, 8, (255, 255, 0), -1)
            cv2.ellipse(debug_frame, final_rotated_rect, (20, 255, 255), 2)
            cv2.line(debug_frame, model_center_average, (best_center_x, best_center_y), (255, 150, 50), 2)

            dx = best_center_x - model_center_average[0]
            dy = best_center_y - model_center_average[1]
            extended_x = int(model_center_average[0] + 2 * dx)
            extended_y = int(model_center_average[1] + 2 * dy)
            cv2.line(debug_frame, (best_center_x, best_center_y), (extended_x, extended_y), (200, 255, 0), 3)

            center, direction = compute_gaze_vector(best_center_x, best_center_y,
                                                    model_center_average[0], model_center_average[1])
            gaze_screen = None
            if center is not None and direction is not None:
                local_x = float(direction[0])
                local_y = float(direction[1])
                gaze_x = clamp(0.5 + local_x * 0.95, 0.0, 1.0)
                gaze_y = clamp(0.5 - local_y * 0.95, 0.0, 1.0)
                gaze_screen = (gaze_x, gaze_y)

                origin_text = f"Origin: ({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f})"
                dir_text = f"Direction: ({direction[0]:.2f}, {direction[1]:.2f}, {direction[2]:.2f})"
                cv2.putText(debug_frame, origin_text, (10, debug_frame.shape[0] - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.putText(debug_frame, dir_text, (10, debug_frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                return EyeFrameResult(
                    ellipse=final_rotated_rect,
                    center_x=best_center_x,
                    center_y=best_center_y,
                    eye_center=model_center_average,
                    gaze_dir=direction,
                    gaze_screen=gaze_screen,
                    openness=best_openness,
                    confidence=float(min(1.0, goodness / 5000.0)),
                    debug_frame=debug_frame,
                    threshold_frame=final_image
                )

    cv2.putText(debug_frame, "Ellipse not found", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 90, 255), 2)
    return EyeFrameResult(debug_frame=debug_frame, threshold_frame=final_image, confidence=0.0)



def process_frame(frame):
    frame = crop_to_aspect_ratio(frame)
    darkest_point = get_darkest_area(frame)
    if darkest_point is None:
        return EyeFrameResult(debug_frame=frame.copy(), threshold_frame=frame.copy(), confidence=0.0)

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    darkest_pixel_value = gray_frame[darkest_point[1], darkest_point[0]]

    thresholded_image_strict = apply_binary_threshold(gray_frame, darkest_pixel_value, 5)
    thresholded_image_strict = mask_outside_square(thresholded_image_strict, darkest_point, 250)

    thresholded_image_medium = apply_binary_threshold(gray_frame, darkest_pixel_value, 15)
    thresholded_image_medium = mask_outside_square(thresholded_image_medium, darkest_point, 250)

    thresholded_image_relaxed = apply_binary_threshold(gray_frame, darkest_pixel_value, 25)
    thresholded_image_relaxed = mask_outside_square(thresholded_image_relaxed, darkest_point, 250)

    result = process_frames(thresholded_image_strict, thresholded_image_medium, thresholded_image_relaxed,
                            frame, gray_frame, darkest_point, False, False)
    return result


# --------------------------
# Simulacro / Galeria
# --------------------------
@dataclass
class Artwork:
    id: str
    title: str
    artist: str
    year: str
    material: str
    description: str
    color: tuple
    rect: tuple


ARTWORKS = [
    Artwork("a1", "Máscara Ritual", "Coleção Simulacro", "Séc. XIX", "Madeira e pigmento", "Peça de uso cerimonial com policromia e desgaste superficial visível.", (70, 160, 235), (110, 120, 230, 170)),
    Artwork("a2", "Vaso Arqueológico", "Acervo Experimental", "1200 d.C.", "Cerâmica", "Vaso com craquelês finos e variação tonal associada à queima e ao uso.", (178, 125, 70), (385, 105, 250, 190)),
    Artwork("a3", "Escultura Votiva", "Projeto Núcleo", "Séc. XVIII", "Bronze", "Escultura de pequena escala com oxidação controlada e base restaurada.", (148, 185, 92), (700, 115, 220, 180)),
    Artwork("a4", "Documento Iluminado", "Arquivo Simulacro", "1898", "Papel, tinta e ouro", "Documento histórico com margens ornamentadas e manchas de acidez.", (208, 162, 66), (125, 390, 250, 180)),
    Artwork("a5", "Joia Cerimonial", "Laboratório de Visualização", "Séc. XX", "Metal e pedra", "Peça de adorno com reflexos fortes, microfissuras e alto contraste óptico.", (184, 98, 172), (430, 405, 210, 165)),
    Artwork("a6", "Fóssil Preparado", "Gabinete Simulacro", "Pré-histórico", "Rocha sedimentar", "Fragmento fossilífero com relevo acentuado e camadas visíveis para leitura volumétrica.", (92, 188, 176), (725, 390, 240, 180)),
]


class BlinkController:
    def __init__(self):
        self.baseline = None
        self.closed = False
        self.closed_frames = 0
        self.open_frames = 0
        self.min_closed_frames = 2
        self.min_open_frames = 2
        self.last_blink_ts = 0.0
        self.cooldown_until = 0.0
        self.double_window = 0.48
        self.cooldown = 0.12
        self.last_action = "—"
        self.single_zoom_pending_reversal = False
        self.last_openness = 0.0

    def reset(self):
        self.__init__()

    def update(self, openness, valid_detection, now):
        # baseline enquanto o olho está visivelmente aberto
        if valid_detection and openness > 0.16:
            if self.baseline is None:
                self.baseline = openness
            else:
                self.baseline = self.baseline * 0.96 + openness * 0.04

        baseline = self.baseline if self.baseline is not None else 0.24
        close_thresh = baseline * 0.52
        open_thresh = baseline * 0.72

        # quando o olho some da detecção, isso também conta como fechamento
        eye_closed_signal = (not valid_detection) or (openness > 0 and openness < close_thresh)
        eye_open_signal = valid_detection and openness > open_thresh
        self.last_openness = openness

        event = None
        if eye_closed_signal:
            self.closed_frames += 1
            self.open_frames = 0
            if not self.closed and self.closed_frames >= self.min_closed_frames:
                self.closed = True
                self.closed_start = now
        elif eye_open_signal:
            self.open_frames += 1
            if self.closed and self.open_frames >= self.min_open_frames:
                dur = now - getattr(self, "closed_start", now)
                self.closed = False
                self.closed_frames = 0
                self.open_frames = 0
                if 0.05 <= dur <= 0.55:
                    event = self.register_blink(now)
            elif not self.closed:
                self.closed_frames = 0
        else:
            # zona intermediária: não força nada
            pass

        return event

    def register_blink(self, now):
        if now < self.cooldown_until:
            return None
        self.cooldown_until = now + self.cooldown

        dt = now - self.last_blink_ts if self.last_blink_ts > 0 else 999.0

        # 1º blink = afasta já
        # 2º blink rápido = desfaz o afasta e aproxima
        if dt <= self.double_window:
            self.last_blink_ts = 0.0
            self.single_zoom_pending_reversal = False
            self.last_action = "2 piscadas → aproxima"
            return "double"

        self.last_blink_ts = now
        self.single_zoom_pending_reversal = True
        self.last_action = "1 piscada → afasta"
        return "single"


class SimulacroScene:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.cursor_x = width * 0.5
        self.cursor_y = height * 0.5
        self.cursor_target_x = self.cursor_x
        self.cursor_target_y = self.cursor_y
        self.calib_offset_x = 0.0
        self.calib_offset_y = 0.0
        self.hover_id = None
        self.hover_start_ts = 0.0
        self.selected_id = None
        self.zoom = 0.0
        self.zoom_target = 0.0
        self.status_text = "Aguardando olhar"
        self.quality_text = "—"
        self.last_log = "Sistema pronto"
        self.fixations = 0
        self.samples = 0
        self.artworks_seen = set()
        self.last_blink_text = "—"
        self.paused = False

    def artwork_by_id(self, art_id):
        for art in ARTWORKS:
            if art.id == art_id:
                return art
        return None

    def reset_view(self):
        self.selected_id = None
        self.zoom_target = 0.0
        self.zoom = 0.0
        self.hover_id = None
        self.status_text = "Zoom resetado"

    def recalibrate_center(self, gaze):
        self.calib_offset_x = 0.5 - gaze[0]
        self.calib_offset_y = 0.5 - gaze[1]
        self.status_text = "Centro recalibrado"
        self.last_log = "Calibração do olhar atualizada"

    def set_gaze(self, gaze_xy, confidence):
        gx = clamp(gaze_xy[0] + self.calib_offset_x, 0.0, 1.0)
        gy = clamp(gaze_xy[1] + self.calib_offset_y, 0.0, 1.0)
        self.cursor_target_x = gx * self.width * 0.78
        self.cursor_target_y = gy * self.height
        self.cursor_x = lerp(self.cursor_x, self.cursor_target_x, 0.24)
        self.cursor_y = lerp(self.cursor_y, self.cursor_target_y, 0.24)
        self.samples += 1
        self.quality_text = f"{int(confidence * 100)}%"

    def update_selection(self, now):
        focused = None
        for art in ARTWORKS:
            x, y, w, h = art.rect
            # a zona da galeria ocupa 78% da largura; painel à direita
            x2 = x
            y2 = y
            if x2 <= self.cursor_x <= x2 + w and y2 <= self.cursor_y <= y2 + h:
                focused = art
                break

        if focused is None:
            self.hover_id = None
            self.hover_start_ts = now
            return 0.0

        self.artworks_seen.add(focused.id)
        if self.hover_id != focused.id:
            self.hover_id = focused.id
            self.hover_start_ts = now
            self.status_text = f"Hover: {focused.title}"
            self.fixations += 1

        dwell = clamp((now - self.hover_start_ts) / 0.90, 0.0, 1.0)
        if dwell >= 1.0:
            self.selected_id = focused.id
            self.status_text = f"Obra selecionada: {focused.title}"
        return dwell

    def apply_blink_event(self, event):
        if event == "single":
            self.zoom_target = max(0.0, self.zoom_target - 0.22)
            self.last_blink_text = "1 piscada → afasta"
            self.last_log = "Comando ocular: afastar"
        elif event == "double":
            target_art = self.artwork_by_id(self.hover_id) or self.artwork_by_id(self.selected_id)
            if target_art is not None:
                self.selected_id = target_art.id
            self.zoom_target = min(1.0, self.zoom_target + 0.28)
            self.last_blink_text = "2 piscadas → aproxima"
            self.last_log = "Comando ocular: aproximar"

    def draw(self, dwell_progress):
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # fundo
        for y in range(self.height):
            t = y / max(1, self.height - 1)
            color = np.array([
                int(7 * (1 - t) + 2 * t),
                int(17 * (1 - t) + 6 * t),
                int(34 * (1 - t) + 13 * t),
            ], dtype=np.uint8)
            canvas[y, :, :] = color

        gallery_w = int(self.width * 0.78)
        panel_x = gallery_w

        # luz ambiente
        cv2.circle(canvas, (int(gallery_w * 0.20), 80), 180, (65, 55, 18), -1)
        cv2.circle(canvas, (int(gallery_w * 0.72), 95), 220, (30, 40, 65), -1)

        # piso / parede
        cv2.rectangle(canvas, (0, 0), (gallery_w, self.height - 120), (24, 32, 46), -1)
        cv2.rectangle(canvas, (0, self.height - 120), (gallery_w, self.height), (18, 22, 28), -1)

        # grades no chão para sensação espacial
        for i in range(0, gallery_w, 60):
            cv2.line(canvas, (i, self.height - 120), (int(gallery_w / 2 + (i - gallery_w / 2) * 0.35), self.height), (38, 46, 55), 1)
        for j in range(0, 9):
            yy = int(self.height - 120 + j * 13)
            cv2.line(canvas, (0, yy), (gallery_w, yy), (34, 42, 52), 1)

        # câmera/zoom da obra selecionada
        self.zoom = lerp(self.zoom, self.zoom_target, 0.12)

        selected = self.artwork_by_id(self.selected_id)
        focus_bias_x = 0.0
        focus_bias_y = 0.0
        focus_scale = 1.0 + self.zoom * 0.52
        if selected is not None:
            sx, sy, sw, sh = selected.rect
            cx = sx + sw / 2
            cy = sy + sh / 2
            focus_bias_x = (gallery_w * 0.42 - cx) * self.zoom * 0.26
            focus_bias_y = (self.height * 0.42 - cy) * self.zoom * 0.22

        # desenha quadros
        for art in ARTWORKS:
            x, y, w, h = art.rect
            cx = x + w / 2
            cy = y + h / 2

            # parallax leve guiado pelo olhar
            px = (self.cursor_x / max(1, gallery_w) - 0.5) * 16
            py = (self.cursor_y / max(1, self.height) - 0.5) * 12

            scale = focus_scale if art.id == self.selected_id else (1.0 + self.zoom * 0.10)
            draw_w = int(w * scale)
            draw_h = int(h * scale)
            draw_x = int(cx - draw_w / 2 + focus_bias_x - px)
            draw_y = int(cy - draw_h / 2 + focus_bias_y - py)

            shadow_color = (8, 12, 18)
            cv2.rectangle(canvas, (draw_x + 14, draw_y + 14), (draw_x + draw_w + 14, draw_y + draw_h + 14), shadow_color, -1)
            cv2.rectangle(canvas, (draw_x - 12, draw_y - 12), (draw_x + draw_w + 12, draw_y + draw_h + 12), (72, 62, 48), -1)
            cv2.rectangle(canvas, (draw_x, draw_y), (draw_x + draw_w, draw_y + draw_h), (244, 240, 228), -1)
            cv2.rectangle(canvas, (draw_x + 10, draw_y + 10), (draw_x + draw_w - 10, draw_y + draw_h - 10), art.color, -1)

            # conteúdo da obra
            cv2.circle(canvas, (draw_x + draw_w // 2, draw_y + draw_h // 2), int(min(draw_w, draw_h) * 0.18), tuple(int(c * 0.75) for c in art.color), -1)
            cv2.line(canvas, (draw_x + 26, draw_y + draw_h - 36), (draw_x + draw_w - 26, draw_y + 34), (230, 230, 230), 2)
            cv2.putText(canvas, art.title, (draw_x + 18, draw_y + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (18, 24, 34), 2, cv2.LINE_AA)

            hl = art.id == self.hover_id or art.id == self.selected_id
            border_color = (245, 210, 90) if art.id == self.selected_id else ((110, 220, 255) if art.id == self.hover_id else (198, 190, 178))
            border_thick = 4 if hl else 2
            cv2.rectangle(canvas, (draw_x - 1, draw_y - 1), (draw_x + draw_w + 1, draw_y + draw_h + 1), border_color, border_thick)

        # painel lateral de informações
        cv2.rectangle(canvas, (panel_x, 0), (self.width, self.height), (8, 12, 20), -1)
        cv2.line(canvas, (panel_x, 0), (panel_x, self.height), (42, 62, 88), 2)

        def panel_text(text, pos, scale=0.6, color=(230, 240, 250), thick=1):
            cv2.putText(canvas, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

        panel_text("SIMULACRO", (panel_x + 20, 40), 0.9, (235, 242, 255), 2)
        panel_text("Controle por rastreamento ocular", (panel_x + 20, 68), 0.48, (140, 172, 210), 1)

        panel_text(f"Qualidade: {self.quality_text}", (panel_x + 20, 110), 0.55, (210, 225, 245), 1)
        panel_text(f"Fixações: {self.fixations}", (panel_x + 20, 136), 0.55, (210, 225, 245), 1)
        panel_text(f"Amostras: {self.samples}", (panel_x + 20, 162), 0.55, (210, 225, 245), 1)
        panel_text(f"Obras vistas: {len(self.artworks_seen)}", (panel_x + 20, 188), 0.55, (210, 225, 245), 1)

        panel_text("Blink", (panel_x + 20, 230), 0.72, (240, 245, 250), 2)
        panel_text(self.last_blink_text, (panel_x + 20, 258), 0.56, (110, 225, 180), 1)
        panel_text("1 piscada = afasta", (panel_x + 20, 284), 0.50, (180, 196, 214), 1)
        panel_text("2 piscadas = aproxima", (panel_x + 20, 307), 0.50, (180, 196, 214), 1)

        panel_text("Obra em foco", (panel_x + 20, 350), 0.72, (240, 245, 250), 2)
        selected = self.artwork_by_id(self.selected_id) or self.artwork_by_id(self.hover_id)
        if selected is None:
            panel_text("Nenhuma obra selecionada", (panel_x + 20, 383), 0.56, (200, 210, 225), 1)
            panel_text("Olhe para um quadro por ~0.9s", (panel_x + 20, 408), 0.50, (142, 166, 188), 1)
        else:
            panel_text(selected.title[:28], (panel_x + 20, 383), 0.64, (246, 232, 178), 2)
            panel_text(selected.artist[:34], (panel_x + 20, 410), 0.52, (204, 214, 234), 1)
            panel_text(f"Ano: {selected.year}", (panel_x + 20, 437), 0.50, (204, 214, 234), 1)
            panel_text(f"Material: {selected.material}", (panel_x + 20, 460), 0.50, (204, 214, 234), 1)
            wrapped = wrap_text(selected.description, 34)
            yy = 492
            for line in wrapped[:5]:
                panel_text(line, (panel_x + 20, yy), 0.49, (184, 196, 214), 1)
                yy += 24

        panel_text("Status", (panel_x + 20, 640), 0.72, (240, 245, 250), 2)
        panel_text(self.status_text[:38], (panel_x + 20, 668), 0.54, (210, 225, 245), 1)
        panel_text(self.last_log[:40], (panel_x + 20, 694), 0.48, (124, 172, 232), 1)

        # dwell meter
        meter_x = 22
        meter_y = 22
        meter_w = 220
        meter_h = 12
        cv2.rectangle(canvas, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (36, 46, 58), -1)
        fill_w = int(meter_w * dwell_progress)
        cv2.rectangle(canvas, (meter_x, meter_y), (meter_x + fill_w, meter_y + meter_h), (76, 205, 124), -1)
        cv2.rectangle(canvas, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (215, 225, 235), 1)
        cv2.putText(canvas, "Dwell", (meter_x, meter_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (214, 226, 242), 1, cv2.LINE_AA)

        # cursor ocular
        cursor_color = (80, 230, 120) if self.hover_id else (92, 194, 255)
        cv2.circle(canvas, (int(self.cursor_x), int(self.cursor_y)), 16, cursor_color, 2)
        cv2.circle(canvas, (int(self.cursor_x), int(self.cursor_y)), 4, cursor_color, -1)
        cv2.line(canvas, (int(self.cursor_x) - 24, int(self.cursor_y)), (int(self.cursor_x) + 24, int(self.cursor_y)), (120, 130, 140), 1)
        cv2.line(canvas, (int(self.cursor_x), int(self.cursor_y) - 24), (int(self.cursor_x), int(self.cursor_y) + 24), (120, 130, 140), 1)

        return canvas


def wrap_text(text, max_chars):
    words = text.split()
    lines = []
    current = []
    current_len = 0
    for word in words:
        add_len = len(word) + (1 if current else 0)
        if current_len + add_len <= max_chars:
            current.append(word)
            current_len += add_len
        else:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
    if current:
        lines.append(" ".join(current))
    return lines


# --------------------------
# GUI de seleção de câmera
# --------------------------
selected_camera = None

def selection_gui():
    global selected_camera
    cameras = detect_cameras()
    if not cameras:
        selected_camera = "0"
        return

    root = tk.Tk()
    root.title("Simulacro – Selecionar câmera do olho")
    root.geometry("420x210")
    root.configure(bg="#081018")

    title = tk.Label(root, text="Simulacro + Eye Tracking", font=("Arial", 14, "bold"), fg="#E8F0FF", bg="#081018")
    title.pack(pady=12)

    subtitle = tk.Label(root, text="Escolha a câmera do olho para iniciar.", font=("Arial", 10), fg="#9CB2D1", bg="#081018")
    subtitle.pack(pady=4)

    selected_camera = tk.StringVar()
    selected_camera.set(str(cameras[0]))

    combo = ttk.Combobox(root, textvariable=selected_camera, values=[str(cam) for cam in cameras], state="readonly")
    combo.pack(pady=16)

    def start():
        root.destroy()

    btn = tk.Button(root, text="Iniciar", command=start, bg="#4D8DFF", fg="white", relief="flat", padx=20, pady=8)
    btn.pack(pady=10)

    root.mainloop()


# --------------------------
# Loop principal integrado
# --------------------------
def run_integrated_simulacro():
    global selected_camera

    cam_index = int(selected_camera.get()) if hasattr(selected_camera, "get") else int(selected_camera or 0)
    cap = cv2.VideoCapture(cam_index, cv2.CAP_MSMF)
    if not cap.isOpened():
        print(f"Erro: não foi possível abrir a câmera {cam_index}.")
        return

    scene = SimulacroScene(EXT_WIDTH, EXT_HEIGHT)
    blink = BlinkController()
    last_result = None
    paused = False

    cv2.namedWindow("Original Eye Frame", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Frame with Ellipse and Rays", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Threshold", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Simulacro – Eye Control", cv2.WINDOW_NORMAL)

    cv2.resizeWindow("Original Eye Frame", 640, 480)
    cv2.resizeWindow("Frame with Ellipse and Rays", 640, 480)
    cv2.resizeWindow("Threshold", 640, 480)
    cv2.resizeWindow("Simulacro – Eye Control", 1280, 720)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("Falha ao ler a câmera.")
                break

            # mantém a mesma ideia do código do usuário, mas sem flip vertical estranho
            eye_frame = crop_to_aspect_ratio(frame)
            result = process_frame(eye_frame)
            last_result = result
            now = time.time()

            if result.gaze_screen is not None:
                scene.set_gaze(result.gaze_screen, result.confidence)

            dwell_progress = scene.update_selection(now)
            valid_detection = result.ellipse is not None and result.confidence > 0.03
            event = blink.update(result.openness, valid_detection, now)
            if event is not None:
                scene.apply_blink_event(event)

            scene_image = scene.draw(dwell_progress)

            # overlays de debug
            if result.ellipse is not None:
                major_axis = max(result.ellipse[1][0], result.ellipse[1][1])
                minor_axis = min(result.ellipse[1][0], result.ellipse[1][1])
                cv2.putText(result.debug_frame, f"Open: {result.openness:.3f}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (245, 240, 210), 2)
                cv2.putText(result.debug_frame, f"Axes: {minor_axis:.1f}/{major_axis:.1f}", (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (210, 230, 240), 1)
            cv2.putText(result.debug_frame, f"Blink: {blink.last_action}", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (100, 220, 140), 2)

            cv2.imshow("Original Eye Frame", eye_frame)
            cv2.imshow("Frame with Ellipse and Rays", result.debug_frame)

            threshold_vis = result.threshold_frame
            if len(threshold_vis.shape) == 2:
                threshold_vis = cv2.cvtColor(threshold_vis, cv2.COLOR_GRAY2BGR)
            cv2.imshow("Threshold", threshold_vis)
            cv2.imshow("Simulacro – Eye Control", scene_image)
        else:
            freeze = scene.draw(0.0)
            cv2.putText(freeze, "PAUSADO", (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (80, 220, 255), 3, cv2.LINE_AA)
            cv2.imshow("Simulacro – Eye Control", freeze)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            scene.reset_view()
            blink.reset()
        elif key == ord('c'):
            if last_result is not None and last_result.gaze_screen is not None:
                scene.recalibrate_center(last_result.gaze_screen)
                calibrate_gaze_to_external()
        elif key == ord('p'):
            paused = not paused

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    selection_gui()
    run_integrated_simulacro()
