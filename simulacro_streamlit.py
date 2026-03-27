import random
import math
import numpy as np
import os
import time
import streamlit as st
from PIL import Image
import tempfile

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
locked_model_center_avg = prev_model_center_avg

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
# FUNÇÕES DE PROCESSAMENTO DE IMAGEM
# ==========================================

def crop_to_aspect_ratio(image, width=640, height=480):
    """Corta a imagem para manter uma proporção específica antes de redimensionar."""
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
    """Aplica limiarização binária à imagem."""
    threshold = darkestPixelValue + addedThreshold
    _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    return thresholded_image


def get_darkest_area(image):
    """Encontra uma área quadrada de pixels escuros na imagem (posição da pupila)."""
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
    """Mascara todos os pixels fora de um quadrado definido pelo centro e tamanho."""
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
    """Otimiza contornos filtrando pontos com base no ângulo em relação ao centroide."""
    if len(contours) < 1:
        return contours

    all_contours = np.concatenate(contours[0], axis=0)
    spacing = max(1, int(len(all_contours) / 25))
    filtered_points = []
    centroid = np.mean(all_contours, axis=0)
    cos_threshold = np.cos(np.radians(60))

    for i in range(0, len(all_contours), 1):
        current_point = all_contours[i]
        prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
        next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]

        vec1 = prev_point - current_point
        vec2 = next_point - current_point

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            continue

        with np.errstate(invalid='ignore'):
            angle = np.arccos(np.clip(np.dot(vec1, vec2) / (norm1 * norm2), -1.0, 1.0))

        vec_to_centroid = centroid - current_point

        if np.dot(vec_to_centroid, (vec1 + vec2) / 2) >= cos_threshold:
            filtered_points.append(current_point)

    if len(filtered_points) == 0:
        return np.array([], dtype=np.int32).reshape((-1, 1, 2))

    return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))


def filter_contours_by_area_and_return_largest(contours, pixel_thresh, ratio_thresh):
    """Retorna o maior contorno que não seja extremamente longo ou alto."""
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
    """Verifica quantos pixels do contorno estão sob uma elipse levemente espessada."""
    if len(contour) < 5:
        return [0, 0, None]

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
    """Verifica a qualidade da elipse ajustada ao contorno."""
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
    ellipse_goodness[2] = min(ellipse[1][1] / ellipse[1][0], ellipse[1][0] / ellipse[1][1]) if ellipse[1][0] != 0 else 0

    return ellipse_goodness


# ==========================================
# INTERSEÇÃO DE LINHAS E RAYTRACING
# ==========================================

def find_line_intersection(ellipse1, ellipse2):
    """Calcula a interseção de duas linhas ortogonais às elipses fornecidas."""
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
    """Remove as interseções mais antigas para manter apenas as últimas M."""
    if len(intersections) <= maximum_intersections:
        return intersections
    return intersections[-maximum_intersections:]


def compute_average_intersection(frame, ray_lines, N, M, spacing):
    """
    Seleciona N linhas aleatórias, calcula interseções,
    armazena e retorna o ponto médio.
    """
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

    if not intersections:
        return None

    avg_x = np.mean([pt[0] for pt in stored_intersections])
    avg_y = np.mean([pt[1] for pt in stored_intersections])

    return (int(avg_x), int(avg_y))


def update_and_average_point(point_list, new_point, N):
    """Adiciona novo ponto à lista e retorna a média dos últimos N pontos."""
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
    """
    Calcula a direção do olhar 3D a partir das coordenadas da pupila
    e do centro da esfera ocular.
    Retorna:
        sphere_center (np.ndarray): posição 3D do centro da esfera
        gaze_direction (np.ndarray): vetor 3D normalizado da direção do olhar
    """
    global last_sphere_center, last_gaze_dir, calibrated_sphere_center

    viewport_width = screen_width
    viewport_height = screen_height

    fov_y_deg = 45.0
    aspect_ratio = viewport_width / viewport_height
    far_clip = 100.0

    camera_position = np.array([0.0, 0.0, 3.0])

    fov_y_rad = np.radians(fov_y_deg)
    half_height_far = np.tan(fov_y_rad / 2) * far_clip
    half_width_far = half_height_far * aspect_ratio

    ndc_x = (2.0 * x) / viewport_width - 1.0
    ndc_y = 1.0 - (2.0 * y) / viewport_height

    far_x = ndc_x * half_width_far
    far_y = ndc_y * half_height_far
    far_z = camera_position[2] - far_clip
    far_point = np.array([far_x, far_y, far_z])

    ray_origin = camera_position
    ray_direction = far_point - camera_position
    ray_direction /= np.linalg.norm(ray_direction)
    ray_direction = -ray_direction

    inner_radius = 1.0 / 1.05
    sphere_offset_x = (center_x / screen_width) * 2.0 - 1.0
    sphere_offset_y = 1.0 - (center_y / screen_height) * 2.0
    sphere_center = np.array([sphere_offset_x * 1.5, sphere_offset_y * 1.5, 0.0])

    origin = ray_origin
    direction = -ray_direction
    L = origin - sphere_center

    a = np.dot(direction, direction)
    b = 2 * np.dot(direction, L)
    c_val = np.dot(L, L) - inner_radius ** 2

    discriminant = b ** 2 - 4 * a * c_val

    t = None

    if discriminant < 0:
        t = -np.dot(direction, L) / np.dot(direction, direction)
    else:
        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

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
    norm_il = np.linalg.norm(intersection_local)
    if norm_il < 1e-9:
        return None, None

    target_direction = intersection_local / norm_il

    circle_local_center = np.array([0.0, 0.0, inner_radius])
    circle_local_center /= np.linalg.norm(circle_local_center)

    rotation_axis = np.cross(circle_local_center, target_direction)
    rotation_axis_norm = np.linalg.norm(rotation_axis)

    if rotation_axis_norm < 1e-6:
        return sphere_center, circle_local_center

    rotation_axis /= rotation_axis_norm
    dot_val = np.clip(np.dot(circle_local_center, target_direction), -1.0, 1.0)
    angle_rad = np.arccos(dot_val)

    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    t_ = 1 - cos_a
    x_, y_, z_ = rotation_axis

    rotation_matrix = np.array([
        [t_ * x_ * x_ + cos_a,       t_ * x_ * y_ - sin_a * z_,  t_ * x_ * z_ + sin_a * y_],
        [t_ * x_ * y_ + sin_a * z_,  t_ * y_ * y_ + cos_a,       t_ * y_ * z_ - sin_a * x_],
        [t_ * x_ * z_ - sin_a * y_,  t_ * y_ * z_ + sin_a * x_,  t_ * z_ * z_ + cos_a]
    ])

    gaze_local = np.array([0.0, 0.0, inner_radius])
    gaze_rotated = rotation_matrix @ gaze_local
    gaze_norm = np.linalg.norm(gaze_rotated)
    if gaze_norm < 1e-9:
        return None, None
    gaze_rotated /= gaze_norm

    last_sphere_center = sphere_center.copy()
    last_gaze_dir = gaze_rotated.copy()

    if calibrated_sphere_center is not None:
        sphere_center_out = calibrated_sphere_center
    else:
        sphere_center_out = sphere_center

    return sphere_center_out, gaze_rotated


# ==========================================
# ROTAÇÃO ENTRE VETORES
# ==========================================

def rotation_from_a_to_b(a, b):
    """Computa matriz de rotação R tal que R @ a = b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)

    v = np.cross(a, b)
    c = np.dot(a, b)

    if np.linalg.norm(v) < 1e-6:
        if c > 0:
            return np.eye(3, dtype=np.float32)
        else:
            axis = np.array([1.0, 0.0, 0.0])
            if abs(a[0]) > 0.9:
                axis = np.array([0.0, 1.0, 0.0])
            v = np.cross(a, axis)
            v = v / np.linalg.norm(v)
            s = np.linalg.norm(v)
    else:
        s = np.linalg.norm(v)
        v = v / s

    vx, vy, vz = v
    K = np.array([
        [0,   -vz,  vy],
        [vz,   0,  -vx],
        [-vy,  vx,  0]
    ], dtype=np.float32)

    if s < 1e-9:
        return np.eye(3, dtype=np.float32)

    R = np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1 - c) / (s ** 2))
    return R


def update_gaze_circle_from_current_gaze():
    """Usa o último vetor de olhar para atualizar a posição do círculo na câmera externa."""
    global circle_x, circle_y, last_gaze_dir, calibrated, R_gaze_to_cam

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


def calibrate_gaze_to_external():
    """Calibra o vetor de olhar para apontar ao centro da câmera externa."""
    global calibrated, R_gaze_to_cam, calibrated_sphere_center
    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg

    if last_gaze_dir is None or last_sphere_center is None:
        return False

    forward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    R_gaze_to_cam = rotation_from_a_to_b(last_gaze_dir, forward)

    calibrated_sphere_center = last_sphere_center.copy()
    sphere_center_locked_2d = True
    locked_model_center_avg = prev_model_center_avg
    calibrated = True

    return True


# ==========================================
# PROCESSAMENTO PRINCIPAL DE FRAMES
# ==========================================

def process_frames_internal(
    thresholded_image_strict,
    thresholded_image_medium,
    thresholded_image_relaxed,
    frame,
    gray_frame,
    darkest_point
):
    """
    Processa os frames com diferentes níveis de threshold,
    detecta a elipse da pupila e calcula o vetor de gaze.
    Retorna o frame anotado e o retângulo girado final (elipse).
    """
    global ray_lines, max_rays, prev_model_center_avg, max_observed_distance
    global sphere_center_locked_2d, locked_model_center_avg

    kernel_size = 5
    kernel = np.ones((kernel_size, kernel_size), np.uint8)

    image_array = [thresholded_image_relaxed, thresholded_image_medium, thresholded_image_strict]
    name_array = ["relaxed", "medium", "strict"]

    final_contours = []
    goodness = 0
    final_image = image_array[0]
    final_rotated_rect = None
    center_x, center_y = None, None
    total_pixels = [0, 0, None]

    for i in range(1, 4):
        dilated_image = cv2.dilate(image_array[i - 1], kernel, iterations=2)
        contours, _ = cv2.findContours(dilated_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        reduced_contours = filter_contours_by_area_and_return_largest(contours, 1000, 3)

        local_center_x, local_center_y = None, None

        if len(reduced_contours) > 0 and reduced_contours[0] is not None and len(reduced_contours[0]) > 5:
            current_goodness = check_ellipse_goodness(dilated_image, reduced_contours[0], False)
            ellipse = cv2.fitEllipse(reduced_contours[0])
            local_center_x, local_center_y = map(int, ellipse[0])

            current_total_pixels = check_contour_pixels(reduced_contours[0], dilated_image.shape, False)

            if current_total_pixels[0] > 0:
                final_goodness = (
                    current_goodness[0]
                    * current_total_pixels[0]
                    * current_total_pixels[0]
                    * current_total_pixels[1]
                )

                if final_goodness > goodness:
                    goodness = final_goodness
                    total_pixels = current_total_pixels
                    final_contours = reduced_contours
                    final_image = dilated_image
                    center_x, center_y = local_center_x, local_center_y

    # Otimiza contornos e ajusta elipse final
    if final_contours:
        optimized = optimize_contours_by_angle(final_contours, gray_frame)

        if optimized is not None and len(optimized) > 5:
            try:
                ellipse = cv2.fitEllipse(optimized)
                final_rotated_rect = ellipse
                ray_lines.append(final_rotated_rect)

                if len(ray_lines) > max_rays:
                    ray_lines = ray_lines[-(max_rays):]
            except Exception:
                pass

    # Determina o centro médio do modelo (esfera ocular)
    model_center_average = (320, 240)
    model_center = compute_average_intersection(frame, ray_lines, 5, 1500, 5)

    if not sphere_center_locked_2d:
        if model_center is not None:
            model_center_average = update_and_average_point(model_centers, model_center, 200)
        else:
            model_center_average = prev_model_center_avg

        if model_center_average is not None and model_center_average[0] != 0:
            prev_model_center_avg = model_center_average
            locked_model_center_avg = model_center_average
    else:
        model_center_average = locked_model_center_avg

    if model_center_average is None:
        model_center_average = (320, 240)

    # Calcula distância máxima observada (raio adaptativo)
    if len(model_centers) >= 100 and center_x is not None and center_y is not None:
        distance = math.sqrt(
            (center_x - model_center_average[0]) ** 2 +
            (center_y - model_center_average[1]) ** 2
        )
        if distance > max_observed_distance:
            max_observed_distance = distance

    max_observed_distance_draw = max(max_observed_distance, 202)

    # Desenha esfera (círculo) e centro
    cv2.circle(frame, model_center_average, int(max_observed_distance_draw), (255, 50, 50), 2)
    cv2.circle(frame, model_center_average, 8, (255, 255, 0), -1)

    # Desenha linha do centro ao centro da pupila
    if final_rotated_rect is not None and center_x is not None and center_y is not None:
        cv2.line(frame, model_center_average, (center_x, center_y), (255, 150, 50), 2)
        cv2.ellipse(frame, final_rotated_rect, (20, 255, 255), 2)

        # Vetor de olhar estendido
        dx = center_x - model_center_average[0]
        dy = center_y - model_center_average[1]
        extended_x = int(model_center_average[0] + 2 * dx)
        extended_y = int(model_center_average[1] + 2 * dy)
        cv2.line(frame, (center_x, center_y), (extended_x, extended_y), (200, 255, 0), 3)

    # Calcula vetor de gaze 3D
    sphere_center_3d = None
    gaze_direction = None

    if center_x is not None and center_y is not None:
        sphere_center_3d, gaze_direction = compute_gaze_vector(
            center_x, center_y,
            model_center_average[0], model_center_average[1]
        )

    # Exibe informações do gaze no frame
    if sphere_center_3d is not None and gaze_direction is not None:
        origin_text = f"Origin: ({sphere_center_3d[0]:.2f}, {sphere_center_3d[1]:.2f}, {sphere_center_3d[2]:.2f})"
        dir_text    = f"Dir: ({gaze_direction[0]:.2f}, {gaze_direction[1]:.2f}, {gaze_direction[2]:.2f})"

        cv2.putText(frame, origin_text, (12, frame.shape[0] - 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(frame, dir_text, (12, frame.shape[0] - 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(frame, origin_text, (10, frame.shape[0] - 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
        cv2.putText(frame, dir_text, (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

    return frame, final_rotated_rect, sphere_center_3d, gaze_direction, model_center_average, center_x, center_y


def process_single_frame(frame):
    """
    Pipeline completo para um único frame:
    crop → darkest area → threshold → detect → draw.
    Retorna o frame anotado e dados de rastreamento.
    """
    frame = crop_to_aspect_ratio(frame)
    darkest_point = get_darkest_area(frame)

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    darkest_pixel_value = gray_frame[darkest_point[1], darkest_point[0]]

    thresholded_strict  = apply_binary_threshold(gray_frame, darkest_pixel_value, 5)
    thresholded_strict  = mask_outside_square(thresholded_strict, darkest_point, 250)

    thresholded_medium  = apply_binary_threshold(gray_frame, darkest_pixel_value, 15)
    thresholded_medium  = mask_outside_square(thresholded_medium, darkest_point, 250)

    thresholded_relaxed = apply_binary_threshold(gray_frame, darkest_pixel_value, 25)
    thresholded_relaxed = mask_outside_square(thresholded_relaxed, darkest_point, 250)

    result = process_frames_internal(
        thresholded_strict,
        thresholded_medium,
        thresholded_relaxed,
        frame,
        gray_frame,
        darkest_point
    )

    return result


# ==========================================
# STREAMLIT — INTERFACE PRINCIPAL
# ==========================================

def reset_globals():
    """Reinicia todos os globals para uma nova sessão de rastreamento."""
    global ray_lines, model_centers, prev_model_center_avg, max_observed_distance
    global last_sphere_center, last_gaze_dir, calibrated
    global calibrated_sphere_center, sphere_center_locked_2d
    global locked_model_center_avg, circle_x, circle_y, stored_intersections

    ray_lines = []
    model_centers = []
    prev_model_center_avg = (320, 240)
    max_observed_distance = 0
    last_sphere_center = None
    last_gaze_dir = None
    calibrated = False
    calibrated_sphere_center = None
    sphere_center_locked_2d = False
    locked_model_center_avg = (320, 240)
    circle_x = EXT_CX
    circle_y = EXT_CY
    stored_intersections = []


def main():
    st.set_page_config(page_title="Orlosky Eye Tracker 3D", layout="wide")

    st.markdown("""
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: bold;
        color: #00ccff;
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #aaaaaa;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .metric-box {
        background-color: #1e1e2e;
        border-radius: 10px;
        padding: 10px;
        margin: 5px 0;
        font-family: monospace;
        font-size: 0.85rem;
        color: #00ff88;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">🎯 Orlosky Eye Tracker 3D</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Rastreamento ocular com estimativa de vetor de gaze 3D via Streamlit</div>', unsafe_allow_html=True)

    # Sidebar — controles
    st.sidebar.header("⚙️ Configurações")

    source_option = st.sidebar.radio(
        "Fonte de entrada",
        ["📷 Webcam ao vivo", "🎞︎ Arquivo de vídeo"]
    )

    flip_frame = st.sidebar.checkbox("Inverter frame verticalmente", value=True)
    show_threshold = st.sidebar.checkbox("Mostrar imagem limiarizada", value=False)
    calibrate_btn = st.sidebar.button("🎯 Calibrar olhar (fixe olho no centro)")
    reset_btn = st.sidebar.button("🔄 Resetar rastreamento")
    stop_btn = st.sidebar.button("⏹️ Parar")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Instruções:**")
    st.sidebar.markdown("1. Selecione a fonte de vídeo")
    st.sidebar.markdown("2. Clique em **Iniciar**")
    st.sidebar.markdown("3. Fixe o olhar no centro e clique em **Calibrar**")
    st.sidebar.markdown("4. O vetor de gaze será calculado em tempo real")

    # Upload de vídeo (se modo arquivo)
    video_file = None
    if source_option == "🎞︎ Arquivo de vídeo":
        video_file = st.sidebar.file_uploader(
            "Envie um vídeo (.mp4, .avi, .mov)",
            type=["mp4", "avi", "mov"]
        )

    start_btn = st.sidebar.button("▶️ Iniciar rastreamento")

    # Layout principal
    col1, col2 = st.columns([3, 1])

    with col1:
        frame_placeholder = st.empty()

    with col2:
        st.markdown("### 📊 Dados do Rastreamento")
        pupil_info = st.empty()
        sphere_info = st.empty()
        gaze_info   = st.empty()
        fps_info    = st.empty()
        status_box  = st.empty()

    # Sessão de estado
    if "running" not in st.session_state:
        st.session_state.running = False
    if "calibrated_done" not in st.session_state:
        st.session_state.calibrated_done = False

    if reset_btn:
        reset_globals()
        st.session_state.running = False
        st.session_state.calibrated_done = False
        status_box.info("🔄 Rastreamento reiniciado.")

    if calibrate_btn:
        success = calibrate_gaze_to_external()
        if success:
            st.session_state.calibrated_done = True
            status_box.success("✅ Calibração concluída com sucesso!")
        else:
            status_box.warning("⚠️ Nenhum vetor de gaze disponível ainda. Aguarde alguns frames.")

    if start_btn:
        st.session_state.running = True
        reset_globals()

    if stop_btn:
        st.session_state.running = False
        status_box.info("⏹️ Rastreamento pausado.")

    # Loop principal de rastreamento
    if st.session_state.running:
        status_box.success("🟢 Rastreamento ativo...")

        # Inicializa captura de vídeo
        cap = None

        if source_option == "📷 Webcam ao vivo":
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                st.error("❌ Não foi possível abrir a webcam. Verifique se ela está conectada e disponível.")
                st.session_state.running = False
                return

        elif source_option == "🎞︎ Arquivo de vídeo":
            if video_file is None:
                st.warning("⚠️ Envie um arquivo de vídeo antes de iniciar.")
                st.session_state.running = False
                return

            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tfile.write(video_file.read())
            tfile.flush()
            cap = cv2.VideoCapture(tfile.name)

            if not cap.isOpened():
                st.error("❌ Não foi possível abrir o arquivo de vídeo.")
                st.session_state.running = False
                return

        frame_count = 0
        t_start = time.time()

        while st.session_state.running:
            ret, raw_frame = cap.read()
            if not ret:
                status_box.info("📽️ Fim do vídeo ou erro na leitura.")
                break

            # Inverte o frame se necessário
            if flip_frame:
                raw_frame = cv2.flip(raw_frame, 0)

            # Processa o frame completo
            try:
                (
                    annotated_frame,
                    final_ellipse,
                    sphere_center_3d,
                    gaze_dir,
                    model_center_avg,
                    pupil_x,
                    pupil_y
                ) = process_single_frame(raw_frame)
            except Exception as e:
                status_box.error(f"Erro no processamento: {e}")
                break

            # Converte frame BGR → RGB para exibição no Streamlit
            display_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            frame_placeholder.image(display_frame, use_column_width=True)

            # Exibe imagem limiarizada (opcional)
            if show_threshold:
                gray_tmp = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                dp = get_darkest_area(raw_frame)
                dpv = gray_tmp[dp[1], dp[0]]
                thresh_vis = apply_binary_threshold(gray_tmp, dpv, 15)
                thresh_vis = mask_outside_square(thresh_vis, dp, 250)
                frame_placeholder.image(thresh_vis, caption="Imagem Limiarizada (Médio)", use_column_width=True)

            # Atualiza painel de dados
            frame_count += 1
            elapsed = time.time() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0

            fps_info.markdown(f"**FPS:** `{fps:.1f}`  |  **Frames:** `{frame_count}`")

            if pupil_x is not None and pupil_y is not None:
                pupil_info.markdown(f"""
                <div class="metric-box">
                🔵 <b>Pupila detectada</b><br>
                X: {pupil_x} px &nbsp;|&nbsp; Y: {pupil_y} px<br>
                Centro esfera: ({model_center_avg[0]}, {model_center_avg[1]})
                </div>
                """, unsafe_allow_html=True)
            else:
                pupil_info.markdown("""
                <div class="metric-box">
                ⚠️ <b>Pupila não detectada</b>
                </div>
                """, unsafe_allow_html=True)

            if sphere_center_3d is not None:
                sphere_info.markdown(f"""
                <div class="metric-box">
                🌐 <b>Centro da Esfera 3D</b><br>
                X: {sphere_center_3d[0]:.3f}<br>
                Y: {sphere_center_3d[1]:.3f}<br>
                Z: {sphere_center_3d[2]:.3f}
                </div>
                """, unsafe_allow_html=True)

            if gaze_dir is not None:
                gaze_info.markdown(f"""
                <div class="metric-box">
                👁️ <b>Vetor de Gaze 3D</b><br>
                X: {gaze_dir[0]:.3f}<br>
                Y: {gaze_dir[1]:.3f}<br>
                Z: {gaze_dir[2]:.3f}<br>
                <br>
                🎯 Calibrado: {"✅ Sim" if st.session_state.calibrated_done else "❌ Não"}
                </div>
                """, unsafe_allow_html=True)

            # Pequena pausa para não travar o servidor
            time.sleep(0.01)

        if cap is not None:
            cap.release()

        st.session_state.running = False
        status_box.info("⏹️ Rastreamento encerrado.")

    else:
        frame_placeholder.markdown("""
        <div style='text-align:center; padding: 60px; background:#111; border-radius:12px;'>
            <h2 style='color:#555;'>👁️ Aguardando início...</h2>
            <p style='color:#444;'>Selecione a fonte de vídeo e clique em <b>Iniciar rastreamento</b></p>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
