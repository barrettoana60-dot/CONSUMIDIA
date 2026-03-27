# REMOVIDO: import subprocess
# REMOVIDO: import sys

# REMOVIDO: def install_system_deps():
# REMOVIDO:     try:
# REMOVIDO:         subprocess.run(
# REMOVIDO:             ["apt-get", "install", "-y",
# REMOVIDO:              "libgl1-mesa-glx", # REMOVIDO
# REMOVIDO:              "libglib2.0-0"],
# REMOVIDO:             capture_output=True
# REMOVIDO:         )
# REMOVIDO:     except Exception:
# REMOVIDO:         pass

# REMOVIDO: install_system_deps() # REMOVIDO

import cv2
import numpy as np
import streamlit as st
import time
import math
import random
import tempfile
import os # Adicionado para os.remove

# ==========================================
# GLOBALS
# ==========================================

ray_lines = []
model_centers = []
max_rays = 100
prev_model_center_avg = (320, 240)
max_observed_distance = 0

last_sphere_center = None
last_gaze_dir = None

calibrated = False
R_gaze_to_cam = np.eye(3, dtype=np.float32)
calibrated_sphere_center = None

sphere_center_locked_2d = False
locked_model_center_avg = (320, 240)

EXT_WIDTH = 640
EXT_HEIGHT = 480
EXT_CX = EXT_WIDTH // 2
EXT_CY = EXT_HEIGHT // 2
EXT_FX = 600.0
EXT_FY = 600.0

circle_x = EXT_CX
circle_y = EXT_CY

stored_intersections = []

# ==========================================
# FUNÇÕES DE IMAGEM
# ==========================================

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
    darkest_point = (gray.shape[1] // 2, gray.shape[0] // 2)

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
        return np.array([], dtype=np.int32).reshape((-1, 1, 2))

    try:
        all_contours = np.concatenate(contours[0], axis=0)
    except Exception:
        return np.array([], dtype=np.int32).reshape((-1, 1, 2))

    spacing = max(1, int(len(all_contours) / 25))
    filtered_points = []
    centroid = np.mean(all_contours, axis=0)
    cos_threshold = np.cos(np.radians(60))

    for i in range(len(all_contours)):
        current_point = all_contours[i]
        prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
        next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

        vec1 = prev_point - current_point
        vec2 = next_point - current_point

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            continue

        vec_to_centroid = centroid - current_point

        if np.dot(vec_to_centroid, (vec1 + vec2) / 2) >= cos_threshold:
            filtered_points.append(current_point)

    if len(filtered_points) == 0:
        return np.array([], dtype=np.int32).reshape((-1, 1, 2))

    return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))


def filter_contours_by_area_and_return_largest(contours, pixel_thresh, ratio_thresh):
    max_area = 0
    largest_contour = None

    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= pixel_thresh:
            x, y, w, h = cv2.boundingRect(contour)
            if h == 0:
                continue
            length_to_width_ratio = max(w / h, h / w)
            if length_to_width_ratio <= ratio_thresh:
                if area > max_area:
                    max_area = area
                    largest_contour = contour

    return [largest_contour] if largest_contour is not None else []


def check_contour_pixels(contour, image_shape, debug_mode_on):
    if len(contour) < 5:
        return [0, 0, None]

    contour_mask = np.zeros(image_shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, 255, 1)

    ellipse_mask_thick = np.zeros(image_shape, dtype=np.uint8)
    ellipse_mask_thin  = np.zeros(image_shape, dtype=np.uint8)
    ellipse = cv2.fitEllipse(contour)

    cv2.ellipse(ellipse_mask_thick, ellipse, 255, 10)
    cv2.ellipse(ellipse_mask_thin,  ellipse, 255, 4)

    overlap_thick = cv2.bitwise_and(contour_mask, ellipse_mask_thick)
    overlap_thin  = cv2.bitwise_and(contour_mask, ellipse_mask_thin)

    absolute_pixel_total_thick = np.sum(overlap_thick > 0)
    total_border_pixels = np.sum(contour_mask > 0)
    ratio_under_ellipse = (
        np.sum(overlap_thin > 0) / total_border_pixels
        if total_border_pixels > 0 else 0
    )

    return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]


def check_ellipse_goodness(binary_image, contour, debug_mode_on):
    ellipse_goodness = [0, 0, 0]
    if len(contour) < 5:
        return ellipse_goodness

    ellipse = cv2.fitEllipse(contour)
    mask = np.zeros_like(binary_image)
    cv2.ellipse(mask, ellipse, 255, -1)

    ellipse_area   = np.sum(mask == 255)
    covered_pixels = np.sum((binary_image == 255) & (mask == 255))

    if ellipse_area == 0:
        return ellipse_goodness

    ellipse_goodness[0] = covered_pixels / ellipse_area
    if ellipse[1][0] != 0:
        ellipse_goodness[2] = min(
            ellipse[1][1] / ellipse[1][0],
            ellipse[1][0] / ellipse[1][1]
        )

    return ellipse_goodness


# ==========================================
# INTERSECÇÕES E RAYTRACING
# ==========================================

def find_line_intersection(ellipse1, ellipse2):
    (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
    (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

    angle1_rad = np.deg2rad(angle1)
    angle2_rad = np.deg2rad(angle2)

    dx1 = (minor_axis1 / 2) * np.cos(angle1_rad)
    dy1 = (minor_axis1 / 2) * np.sin(angle1_rad)
    dx2 = (minor_axis2 / 2) * np.cos(angle2_rad)
    dy2 = (minor_axis2 / 2) * np.sin(angle2_rad)

    A = np.array([[dx1, -dx2], [dy1, -dy2]])
    B = np.array([cx2 - cx1, cy2 - cy1])

    if abs(np.linalg.det(A)) < 1e-6:
        return None

    try:
        t1, t2 = np.linalg.solve(A, B)
    except np.linalg.LinAlgError:
        return None

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
        return None

    height, width = frame.shape[:2]
    selected_lines = random.sample(ray_lines, min(N, len(ray_lines)))
    intersections = []

    for i in range(len(selected_lines) - 1):
        line1 = selected_lines[i]
        line2 = selected_lines[i + 1]

        if abs(line1[2] - line2[2]) >= 2:
            intersection = find_line_intersection(line1, line2)
            if intersection and (0 <= intersection[0] < width) and (0 <= intersection[1] < height):
                intersections.append(intersection)
                stored_intersections.append(intersection)

    if len(stored_intersections) > M:
        stored_intersections = prune_intersections(stored_intersections, M)

    if not stored_intersections:
        return None

    avg_x = int(np.mean([pt[0] for pt in stored_intersections]))
    avg_y = int(np.mean([pt[1] for pt in stored_intersections]))

    return (avg_x, avg_y)


def update_and_average_point(point_list, new_point, N):
    point_list.append(new_point)
    if len(point_list) > N:
        point_list.pop(0)
    if not point_list:
        return None
    avg_x = int(np.mean([p[0] for p in point_list]))
    avg_y = int(np.mean([p[1] for p in point_list]))
    return (avg_x, avg_y)


# ==========================================
# VETOR DE GAZE 3D
# ==========================================

def compute_gaze_vector(x, y, center_x, center_y, screen_width=640, screen_height=480):
    global last_sphere_center, last_gaze_dir, calibrated_sphere_center

    fov_y_deg   = 45.0
    aspect_ratio = screen_width / screen_height
    far_clip    = 100.0
    camera_position = np.array([0.0, 0.0, 3.0])

    fov_y_rad       = np.radians(fov_y_deg)
    half_height_far = np.tan(fov_y_rad / 2) * far_clip
    half_width_far  = half_height_far * aspect_ratio

    ndc_x = (2.0 * x) / screen_width  - 1.0
    ndc_y = 1.0 - (2.0 * y) / screen_height

    far_point = np.array([
        ndc_x * half_width_far,
        ndc_y * half_height_far,
        camera_position[2] - far_clip
    ])

    ray_direction = far_point - camera_position
    ray_direction /= np.linalg.norm(ray_direction)
    ray_direction  = -ray_direction

    inner_radius   = 1.0 / 1.05
    sphere_offset_x = (center_x / screen_width)  * 2.0 - 1.0
    sphere_offset_y = 1.0 - (center_y / screen_height) * 2.0
    sphere_center  = np.array([sphere_offset_x * 1.5, sphere_offset_y * 1.5, 0.0])

    origin    = camera_position
    direction = -ray_direction
    L = origin - sphere_center

    a_coef = np.dot(direction, direction)
    b_coef = 2 * np.dot(direction, L)
    c_coef = np.dot(L, L) - inner_radius ** 2
    discriminant = b_coef ** 2 - 4 * a_coef * c_coef

    t = None
    if discriminant < 0:
        t = -np.dot(direction, L) / a_coef
    else:
        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b_coef - sqrt_disc) / (2 * a_coef)
        t2 = (-b_coef + sqrt_disc) / (2 * a_coef)
        if   t1 > 0 and t2 > 0: t = min(t1, t2)
        elif t1 > 0:             t = t1
        elif t2 > 0:             t = t2

    if t is None:
        return None, None

    intersection_point = origin + t * direction
    intersection_local = intersection_point - sphere_center
    norm_il = np.linalg.norm(intersection_local)
    if norm_il < 1e-9:
        return None, None

    target_direction   = intersection_local / norm_il
    circle_local_center = np.array([0.0, 0.0, inner_radius])
    circle_local_center /= np.linalg.norm(circle_local_center)

    rotation_axis      = np.cross(circle_local_center, target_direction)
    rotation_axis_norm = np.linalg.norm(rotation_axis)

    if rotation_axis_norm < 1e-6:
        return sphere_center, circle_local_center

    rotation_axis /= rotation_axis_norm
    dot_val   = np.clip(np.dot(circle_local_center, target_direction), -1.0, 1.0)
    angle_rad = np.arccos(dot_val)

    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    t_    = 1 - cos_a
    rx, ry, rz = rotation_axis

    rotation_matrix = np.array([
        [t_*rx*rx + cos_a,      t_*rx*ry - sin_a*rz,  t_*rx*rz + sin_a*ry],
        [t_*rx*ry + sin_a*rz,  t_*ry*ry + cos_a,      t_*ry*rz - sin_a*rx],
        [t_*rx*rz - sin_a*ry,  t_*ry*rz + sin_a*rx,  t_*rz*rz + cos_a   ]
    ])

    gaze_local   = np.array([0.0, 0.0, inner_radius])
    gaze_rotated = rotation_matrix @ gaze_local
    gaze_norm    = np.linalg.norm(gaze_rotated)

    if gaze_norm < 1e-9:
        return None, None

    gaze_rotated /= gaze_norm

    last_sphere_center = sphere_center.copy()
    last_gaze_dir      = gaze_rotated.copy()

    sphere_center_out = calibrated_sphere_center if calibrated_sphere_center is not None else sphere_center

    return sphere_center_out, gaze_rotated


# ==========================================
# CALIBRAÇÃO
# ==========================================

def rotation_from_a_to_b(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = np.dot(a, b)

    if np.linalg.norm(v) < 1e-6:
        if c > 0:
            return np.eye(3, dtype=np.float32)
        axis = np.array([1.0, 0.0, 0.0])
        if abs(a[0]) > 0.9:
            axis = np.array([0.0, 1.0, 0.0])
        v = np.cross(a, axis)
        v /= np.linalg.norm(v)
        s = np.linalg.norm(v)
    else:
        s = np.linalg.norm(v)
        v /= s

    if s < 1e-9:
        return np.eye(3, dtype=np.float32)

    vx, vy, vz = v
    K = np.array([
        [0,   -vz,  vy],
        [vz,   0,  -vx],
        [-vy,  vx,  0]
    ], dtype=np.float32)

    R = np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1 - c) / (s ** 2))
    return R


def calibrate_gaze_to_external():
    global calibrated, R_gaze_to_cam, calibrated_sphere_center
    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg

    if last_gaze_dir is None or last_sphere_center is None:
        return False

    forward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    R_gaze_to_cam = rotation_from_a_to_b(last_gaze_dir, forward)
    calibrated_sphere_center = last_sphere_center.copy()
    sphere_center_locked_2d  = True
    locked_model_center_avg  = prev_model_center_avg
    calibrated = True
    return True


def update_gaze_circle_from_current_gaze():
    global circle_x, circle_y

    if not calibrated or last_gaze_dir is None:
        return

    g = R_gaze_to_cam @ last_gaze_dir

    if g[2] <= 1e-6:
        return

    u = int(np.clip(EXT_CX + EXT_FX * (g[0] / g[2]), 0, EXT_WIDTH  - 1))
    v = int(np.clip(EXT_CY - EXT_FY * (g[1] / g[2]), 0, EXT_HEIGHT - 1))

    circle_x, circle_y = u, v


# ==========================================
# PIPELINE DE PROCESSAMENTO DO FRAME
# ==========================================

def process_single_frame(frame):
    global ray_lines, model_centers, prev_model_center_avg
    global max_observed_distance, sphere_center_locked_2d
    global locked_model_center_avg

    frame = crop_to_aspect_ratio(frame)
    darkest_point = get_darkest_area(frame)

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    darkest_pixel_value = gray_frame[darkest_point[1], darkest_point[0]]

    thresh_strict  = apply_binary_threshold(gray_frame, darkest_pixel_value, 5)
    thresh_strict  = mask_outside_square(thresh_strict,  darkest_point, 250)

    thresh_medium  = apply_binary_threshold(gray_frame, darkest_pixel_value, 15)
    thresh_medium  = mask_outside_square(thresh_medium,  darkest_point, 250)

    thresh_relaxed = apply_binary_threshold(gray_frame, darkest_pixel_value, 25)
    thresh_relaxed = mask_outside_square(thresh_relaxed, darkest_point, 250)

    image_array = [thresh_relaxed, thresh_medium, thresh_strict]
    kernel      = np.ones((5, 5), np.uint8)

    final_contours  = []
    goodness        = 0
    center_x        = None
    center_y        = None
    total_pixels    = [0, 0, None]
    final_rotated_rect = None

    for i in range(3):
        dilated   = cv2.dilate(image_array[i], kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        reduced   = filter_contours_by_area_and_return_largest(contours, 1000, 3)

        if reduced and reduced[0] is not None and len(reduced[0]) > 5:
            current_goodness = check_ellipse_goodness(dilated, reduced[0], False)
            ellipse          = cv2.fitEllipse(reduced[0])
            lx, ly           = map(int, ellipse[0])
            tp               = check_contour_pixels(reduced[0], dilated.shape, False)

            if tp[0] > 0:
                score = current_goodness[0] * tp[0] * tp[0] * tp[1]
                if score > goodness:
                    goodness       = score
                    total_pixels   = tp
                    final_contours = reduced
                    center_x, center_y = lx, ly

    # Otimização e ajuste final da elipse
    if final_contours:
        optimized = optimize_contours_by_angle(final_contours, gray_frame)
        if optimized is not None and len(optimized) > 5:
            try:
                ellipse = cv2.fitEllipse(optimized)
                final_rotated_rect = ellipse
                ray_lines.append(final_rotated_rect)
                if len(ray_lines) > max_rays:
                    ray_lines = ray_lines[-max_rays:]
            except Exception:
                pass

    # Centro médio da esfera
    model_center = compute_average_intersection(frame, ray_lines, 5, 1500, 5)
    model_center_average = (320, 240)

    if not sphere_center_locked_2d:
        if model_center is not None:
            model_center_average = update_and_average_point(model_centers, model_center, 200)
        else:
            model_center_average = prev_model_center_avg

        if model_center_average is not None and model_center_average[0] != 0:
            prev_model_center_avg   = model_center_average
            locked_model_center_avg = model_center_average
    else:
        model_center_average = locked_model_center_avg

    if model_center_average is None:
        model_center_average = (320, 240)

    # Raio adaptativo
    if len(model_centers) >= 100 and center_x is not None:
        dist = math.sqrt(
            (center_x - model_center_average[0]) ** 2 +
            (center_y - model_center_average[1]) ** 2
        )
        if dist > max_observed_distance:
            max_observed_distance = dist

    draw_radius = max(int(max_observed_distance), 202)

    # Anotações visuais no frame
    cv2.circle(frame, model_center_average, draw_radius, (255, 50, 50), 2)
    cv2.circle(frame, model_center_average, 8, (255, 255, 0), -1)

    if final_rotated_rect is not None and center_x is not None:
        cv2.line(frame, model_center_average, (center_x, center_y), (255, 150, 50), 2)
        cv2.ellipse(frame, final_rotated_rect, (20, 255, 255), 2)

        dx = center_x - model_center_average[0]
        dy = center_y - model_center_average[1]
        ext_x = int(model_center_average[0] + 2 * dx)
        ext_y = int(model_center_average[1] + 2 * dy)
        cv2.line(frame, (center_x, center_y), (ext_x, ext_y), (200, 255, 0), 3)

    # Gaze 3D
    sphere_center_3d = None
    gaze_dir         = None

    if center_x is not None and center_y is not None:
        sphere_center_3d, gaze_dir = compute_gaze_vector(
            center_x, center_y,
            model_center_average[0], model_center_average[1]
        )

    if sphere_center_3d is not None and gaze_dir is not None:
        o_txt = f"Origin: ({sphere_center_3d[0]:.2f}, {sphere_center_3d[1]:.2f}, {sphere_center_3d[2]:.2f})"
        d_txt = f"Dir:    ({gaze_dir[0]:.2f}, {gaze_dir[1]:.2f}, {gaze_dir[2]:.2f})"
        h = frame.shape[0]

        cv2.putText(frame, o_txt, (12, h - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,   0,   0), 3)
        cv2.putText(frame, d_txt, (12, h - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,   0,   0), 3)
        cv2.putText(frame, o_txt, (10, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255,   0), 2)
        cv2.putText(frame, d_txt, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255,   0), 2)

    return frame, final_rotated_rect, sphere_center_3d, gaze_dir, model_center_average, center_x, center_y


# ==========================================
# RESET GLOBALS
# ==========================================

def reset_globals():
    global ray_lines, model_centers, prev_model_center_avg, max_observed_distance
    global last_sphere_center, last_gaze_dir, calibrated, calibrated_sphere_center
    global sphere_center_locked_2d, locked_model_center_avg
    global circle_x, circle_y, stored_intersections

    ray_lines               = []
    model_centers           = []
    prev_model_center_avg   = (320, 240)
    max_observed_distance   = 0
    last_sphere_center      = None
    last_gaze_dir           = None
    calibrated              = False
    calibrated_sphere_center = None
    sphere_center_locked_2d = False
    locked_model_center_avg = (320, 240)
    circle_x                = EXT_CX
    circle_y                = EXT_CY
    stored_intersections    = []


# ==========================================
# STREAMLIT MAIN
# ==========================================

def main():
    st.set_page_config(page_title="Orlosky Eye Tracker 3D", layout="wide")

    st.markdown("""
    <style>
    .main-title { font-size:2rem; font-weight:bold; color:#00ccff; text-align:center; }
    .sub-title  { font-size:0.95rem; color:#aaa; text-align:center; margin-bottom:1.5rem; }
    .mbox {
        background:#1a1a2e; border-radius:8px; padding:10px;
        font-family:monospace; font-size:0.82rem; color:#00ff88; margin:4px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">🎯 Orlosky Eye Tracker 3D</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Rastreamento ocular com vetor de gaze 3D — via Streamlit</div>', unsafe_allow_html=True)

    # ---- Sidebar ----
    st.sidebar.header("⚙️ Configurações")

    source_opt = st.sidebar.radio("Fonte de entrada", ["📷 Webcam", "🎞︎ Arquivo de vídeo"])
    flip_v     = st.sidebar.checkbox("Inverter frame (vertical)", value=True)
    show_thr   = st.sidebar.checkbox("Mostrar threshold", value=False)

    video_file = None
    if source_opt == "🎞︎ Arquivo de vídeo":
        video_file = st.sidebar.file_uploader("Envie o vídeo", type=["mp4", "avi", "mov"])

    st.sidebar.markdown("---")
    col_s1, col_s2 = st.sidebar.columns(2)
    start_btn = col_s1.button("▶️ Iniciar")
    stop_btn  = col_s2.button("⏹️ Parar")

    col_s3, col_s4 = st.sidebar.columns(2)
    calib_btn = col_s3.button("🎯 Calibrar")
    reset_btn = col_s4.button("🔄 Reset")

    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    **Como usar:**
    1. Escolha a fonte de vídeo
    2. Clique **Iniciar**
    3. Fixe o olhar no centro e clique **Calibrar**
    4. O vetor de gaze é calculado em tempo real
    """)

    # ---- Session state ----
    if "running"        not in st.session_state: st.session_state.running        = False
    if "calibrated_ok"  not in st.session_state: st.session_state.calibrated_ok  = False

    # ---- Ações dos botões ----
    status = st.empty()

    if reset_btn:
        reset_globals()
        st.session_state.running       = False
        st.session_state.calibrated_ok = False
        status.info("🔄 Reiniciado.")

    if calib_btn:
        if calibrate_gaze_to_external():
            st.session_state.calibrated_ok = True
            status.success("✅ Calibração concluída!")
        else:
            status.warning("⚠️ Sem dados de gaze ainda. Aguarde alguns frames.")

    if stop_btn:
        st.session_state.running = False
        status.info("⏹️ Parado.")

    if start_btn:
        reset_globals()
        st.session_state.running       = True
        st.session_state.calibrated_ok = False

    # ---- Layout principal ----
    col_vid, col_data = st.columns([3, 1])

    with col_vid:
        frame_ph = st.empty()
        thr_ph   = st.empty()

    with col_data:
        st.markdown("### 📊 Dados")
        fps_ph    = st.empty()
        pupil_ph  = st.empty()
        sphere_ph = st.empty()
        gaze_ph   = st.empty()
        calib_ph  = st.empty()

    # ---- Loop de rastreamento ----
    if st.session_state.running:
        status.success("🟢 Rastreamento ativo...")

        cap = None
        tmp_path = None

        if source_opt == "📷 Webcam":
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                st.error("❌ Webcam não encontrada.")
                st.session_state.running = False
                return
        else:
            if video_file is None:
                st.warning("⚠️ Envie um vídeo.")
                st.session_state.running = False
                return
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tmp.write(video_file.read())
            tmp.flush()
            tmp_path = tmp.name
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                st.error("❌ Não foi possível abrir o vídeo.")
                st.session_state.running = False
                return

        frame_count = 0
        t0 = time.time()

        while st.session_state.running:
            ret, raw = cap.read()
            if not ret:
                status.info("📽️ Fim do vídeo ou erro na leitura.")
                break

            if flip_v:
                raw = cv2.flip(raw, 0)

            try:
                (
                    annotated, ellipse,
                    sc3d, gdir,
                    mca, px, py
                ) = process_single_frame(raw)
            except Exception as e:
                status.error(f"Erro no processamento: {e}")
                break

            # Exibe frame
            rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            frame_ph.image(rgb, use_column_width=True)

            # Threshold opcional
            if show_thr:
                g_tmp  = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
                dp_tmp = get_darkest_area(raw)
                dpv    = g_tmp[dp_tmp[1], dp_tmp[0]]
                th_vis = apply_binary_threshold(g_tmp, dpv, 15)
                th_vis = mask_outside_square(th_vis, dp_tmp, 250)
                thr_ph.image(th_vis, caption="Threshold médio")

            # Atualiza círculo de gaze na câmera externa
            if calibrated:
                update_gaze_circle_from_current_gaze()

            # Métricas
            frame_count += 1
            fps = frame_count / max(time.time() - t0, 1e-9)
            fps_ph.markdown(f"**FPS:** `{fps:.1f}` | **Frames:** `{frame_count}`")

            pupil_ph.markdown(f"""
            <div class="mbox">
            🔵 <b>Pupila</b><br>
            {"X: " + str(px) + " | Y: " + str(py) if px else "❌ Não detectada"}<br>
            Centro esfera 2D: {mca}
            </div>""", unsafe_allow_html=True)

            if sc3d is not None:
                sphere_ph.markdown(f"""
                <div class="mbox">
                🌐 <b>Esfera 3D</b><br>
                X: {sc3d[0]:.3f}<br>
                Y: {sc3d[1]:.3f}<br>
                Z: {sc3d[2]:.3f}
                </div>""", unsafe_allow_html=True)

            if gdir is not None:
                gaze_ph.markdown(f"""
                <div class="mbox">
                👁️ <b>Gaze 3D</b><br>
                X: {gdir[0]:.3f}<br>
                Y: {gdir[1]:.3f}<br>
                Z: {gdir[2]:.3f}
                </div>""", unsafe_allow_html=True)

            calib_ph.markdown(f"""
            <div class="mbox">
            🎯 Calibrado: {"✅ Sim" if st.session_state.calibrated_ok else "❌ Não"}
            </div>""", unsafe_allow_html=True)

            time.sleep(0.01)

        cap.release()
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

        st.session_state.running = False
        status.info("⏹️ Encerrado.")

    else:
        frame_ph = st.empty()
        frame_ph.markdown("""
        <div style='text-align:center;padding:80px;background:#111;border-radius:12px;'>
            <h2 style='color:#444;'>👁️ Aguardando início...</h2>
            <p style='color:#333;'>Selecione a fonte e clique em <b>Iniciar</b></p>
        </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
