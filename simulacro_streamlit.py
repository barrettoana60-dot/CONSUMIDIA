import cv2
import random
import math
import numpy as np
import os
import tkinter as tk
from tkinter import ttk, filedialog
import sys
import time

try:
    import gl_sphere
    GL_SPHERE_AVAILABLE = True
except ImportError:
    GL_SPHERE_AVAILABLE = False
    print("gl_sphere module not found. OpenGL rendering will be disabled.")

ray_lines = [] 
model_centers = []
max_rays = 100
prev_model_center_avg = (320,240)
max_observed_distance = 0  # Initialize adaptive radius

# --- Gaze → external camera projection globals ---
last_sphere_center = None
last_gaze_dir = None

calibrated = False
R_gaze_to_cam = np.eye(3, dtype=np.float32)  # rotation from gaze-space to external cam space
calibrated_sphere_center = None 

sphere_center_locked_2d = False
locked_model_center_avg = prev_model_center_avg

# External camera / screen params (for 640x480)
EXT_WIDTH = 640
EXT_HEIGHT = 480
EXT_CX = EXT_WIDTH // 2
EXT_CY = EXT_HEIGHT // 2

# Locking for 2D sphere center in the eye image
sphere_center_locked_2d = False
locked_model_center_avg = prev_model_center_avg

# Approximate focal length in pixels (simple pinhole model)
EXT_FX = 600.0
EXT_FY = 600.0

# Current red circle position on external camera
circle_x = EXT_CX
circle_y = EXT_CY


# Function to detect available cameras
def detect_cameras(max_cams=10):
    available_cameras = []
    for i in range(max_cams):
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        cap.set(cv2.CAP_PROP_FPS, 30)
        if cap.isOpened():
            available_cameras.append(i)
            cap.release()
    return available_cameras

# Crop the image to maintain a specific aspect ratio (width:height) before resizing.
def crop_to_aspect_ratio(image, width=640, height=480):
    current_height, current_width = image.shape[:2]
    desired_ratio = width / height
    current_ratio = current_width / current_height

    if current_ratio > desired_ratio:
        # Current image is too wide
        new_width = int(desired_ratio * current_height)
        offset = (current_width - new_width) // 2
        cropped_img = image[:, offset:offset + new_width]
    else:
        # Current image is too tall
        new_height = int(current_width / desired_ratio)
        offset = (current_height - new_height) // 2
        cropped_img = image[offset:offset + new_height, :]

    return cv2.resize(cropped_img, (width, height))

# Apply thresholding to an image
def apply_binary_threshold(image, darkestPixelValue, addedThreshold):
    threshold = darkestPixelValue + addedThreshold
    _, thresholded_image = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    return thresholded_image

# Finds a square area of dark pixels in the image
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

# Mask all pixels outside a square defined by center and size
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

    # Holds the candidate points
    all_contours = np.concatenate(contours[0], axis=0)

    # Set spacing based on size of contours
    spacing = int(len(all_contours)/25)  # Spacing between sampled points

    # Temporary array for result
    filtered_points = []
    
    # Calculate centroid of the original contours
    centroid = np.mean(all_contours, axis=0)
    
    # Create an image of the same size as the original image
    point_image = image.copy()
    
    skip = 0
    
    # Loop through each point in the all_contours array
    for i in range(0, len(all_contours), 1):
    
        # Get three points: current point, previous point, and next point
        current_point = all_contours[i]
        prev_point = all_contours[i - spacing] if i - spacing >= 0 else all_contours[-spacing]
        next_point = all_contours[i + spacing] if i + spacing < len(all_contours) else all_contours[spacing]
        
        # Calculate vectors between points
        vec1 = prev_point - current_point
        vec2 = next_point - current_point
        
        with np.errstate(invalid='ignore'):
            # Calculate angles between vectors
            angle = np.arccos(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

        
        # Calculate vector from current point to centroid
        vec_to_centroid = centroid - current_point
        
        # Check if angle is oriented towards centroid
        # Calculate the cosine of the desired angle threshold (e.g., 80 degrees)
        cos_threshold = np.cos(np.radians(60))  # Convert angle to radians
        
        if np.dot(vec_to_centroid, (vec1+vec2)/2) >= cos_threshold:
            filtered_points.append(current_point)
    
    return np.array(filtered_points, dtype=np.int32).reshape((-1, 1, 2))

# Returns the largest contour that is not extremely long or tall
def filter_contours_by_area_and_return_largest(contours, pixel_thresh, ratio_thresh):
    max_area = 0
    largest_contour = None

    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= pixel_thresh:
            x, y, w, h = cv2.boundingRect(contour)
            length_to_width_ratio = max(w / h, h / w)
            if length_to_width_ratio <= ratio_thresh:
                if area > max_area:
                    max_area = area
                    largest_contour = contour

    return [largest_contour] if largest_contour is not None else []
#Fits an ellipse to the optimized contours and draws it on the image.
def fit_and_draw_ellipses(image, optimized_contours, color):
    if len(optimized_contours) >= 5:
        # Ensure the data is in the correct shape (n, 1, 2) for cv2.fitEllipse
        contour = np.array(optimized_contours, dtype=np.int32).reshape((-1, 1, 2))

        # Fit ellipse
        ellipse = cv2.fitEllipse(contour)

        # Draw the ellipse
        cv2.ellipse(image, ellipse, color, 2)  # Draw with green color and thickness of 2

        return image
    else:
        print("Not enough points to fit an ellipse.")
        return image

#checks how many pixels in the contour fall under a slightly thickened ellipse
#also returns that number of pixels divided by the total pixels on the contour border
#assists with checking ellipse goodness    
def check_contour_pixels(contour, image_shape, debug_mode_on):
    # Check if the contour can be used to fit an ellipse (requires at least 5 points)
    if len(contour) < 5:
        return [0, 0]  # Not enough points to fit an ellipse
    
    # Create an empty mask for the contour
    contour_mask = np.zeros(image_shape, dtype=np.uint8)
    # Draw the contour on the mask, filling it
    cv2.drawContours(contour_mask, [contour], -1, (255), 1)
   
    # Fit an ellipse to the contour and create a mask for the ellipse
    ellipse_mask_thick = np.zeros(image_shape, dtype=np.uint8)
    ellipse_mask_thin = np.zeros(image_shape, dtype=np.uint8)
    ellipse = cv2.fitEllipse(contour)
    
    # Draw the ellipse with a specific thickness
    cv2.ellipse(ellipse_mask_thick, ellipse, (255), 10) #capture more for absolute
    cv2.ellipse(ellipse_mask_thin, ellipse, (255), 4) #capture fewer for ratio

    # Calculate the overlap of the contour mask and the thickened ellipse mask
    overlap_thick = cv2.bitwise_and(contour_mask, ellipse_mask_thick)
    overlap_thin = cv2.bitwise_and(contour_mask, ellipse_mask_thin)
    
    # Count the number of non-zero (white) pixels in the overlap
    absolute_pixel_total_thick = np.sum(overlap_thick > 0)#compute with thicker border
    absolute_pixel_total_thin = np.sum(overlap_thin > 0)#compute with thicker border
    
    # Compute the ratio of pixels under the ellipse to the total pixels on the contour border
    total_border_pixels = np.sum(contour_mask > 0)
    
    ratio_under_ellipse = absolute_pixel_total_thin / total_border_pixels if total_border_pixels > 0 else 0
    
    return [absolute_pixel_total_thick, ratio_under_ellipse, overlap_thin]

#outside of this method, select the ellipse with the highest percentage of pixels under the ellipse 
#TODO for efficiency, work with downscaled or cropped images
def check_ellipse_goodness(binary_image, contour, debug_mode_on):
    ellipse_goodness = [0,0,0] #covered pixels, edge straightness stdev, skewedness   
    # Check if the contour can be used to fit an ellipse (requires at least 5 points)
    if len(contour) < 5:
        print("length of contour was 0")
        return 0  # Not enough points to fit an ellipse
    
    # Fit an ellipse to the contour
    ellipse = cv2.fitEllipse(contour)
    
    # Create a mask with the same dimensions as the binary image, initialized to zero (black)
    mask = np.zeros_like(binary_image)
    
    # Draw the ellipse on the mask with white color (255)
    cv2.ellipse(mask, ellipse, (255), -1)
    
    # Calculate the number of pixels within the ellipse
    ellipse_area = np.sum(mask == 255)
    
    # Calculate the number of white pixels within the ellipse
    covered_pixels = np.sum((binary_image == 255) & (mask == 255))
    
    # Calculate the percentage of covered white pixels within the ellipse
    if ellipse_area == 0:
        print("area was 0")
        return ellipse_goodness  # Avoid division by zero if the ellipse area is somehow zero
    
    #percentage of covered pixels to number of pixels under area
    ellipse_goodness[0] = covered_pixels / ellipse_area
    
    #skew of the ellipse (less skewed is better?) - may not need this
    axes_lengths = ellipse[1]  # This is a tuple (minor_axis_length, major_axis_length)
    major_axis_length = axes_lengths[1]
    minor_axis_length = axes_lengths[0]
    ellipse_goodness[2] = min(ellipse[1][1]/ellipse[1][0], ellipse[1][0]/ellipse[1][1])
    
    return ellipse_goodness

# Process frames for pupil detection
def process_frames(thresholded_image_strict, thresholded_image_medium, thresholded_image_relaxed, frame, gray_frame, darkest_point, debug_mode_on, render_cv_window):
    global ray_lines
    global max_rays
    global prev_model_center_avg
    global max_observed_distance

    kernel_size = 5
    kernel = np.ones((kernel_size, kernel_size), np.uint8)

    dilated_image = cv2.dilate(thresholded_image_medium, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    reduced_contours = filter_contours_by_area_and_return_largest(contours, 1000, 3)

    final_rotated_rect = ((0,0),(0,0),0)

    image_array = [thresholded_image_relaxed, thresholded_image_medium, thresholded_image_strict] #holds images
    name_array = ["relaxed", "medium", "strict"] #for naming windows
    final_image = image_array[0] #holds return array
    final_contours = [] #holds final contours
    ellipse_reduced_contours = [] #holds an array of the best contour points from the fitting process
    goodness = 0 #goodness value for best ellipse
    best_array = 0 
    kernel_size = 5  # Size of the kernel (5x5)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    gray_copy1 = gray_frame.copy()
    gray_copy2 = gray_frame.copy()
    gray_copy3 = gray_frame.copy()
    gray_copies = [gray_copy1, gray_copy2, gray_copy3]
    final_goodness = 0
    
    #iterate through binary images and see which fits the ellipse best
    for i in range(1,4):
        # Dilate the binary image
        dilated_image = cv2.dilate(image_array[i-1], kernel, iterations=2)#medium
        
        # Find contours
        contours, hierarchy = cv2.findContours(dilated_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Create an empty image to draw contours
        contour_img2 = np.zeros_like(dilated_image)
        reduced_contours = filter_contours_by_area_and_return_largest(contours, 1000, 3)

        #initialize variables
        center_x, center_y = None, None

        if len(reduced_contours) > 0 and len(reduced_contours[0]) > 5:
            current_goodness = check_ellipse_goodness(dilated_image, reduced_contours[0], debug_mode_on)
            ellipse = cv2.fitEllipse(reduced_contours[0])
            center_x, center_y = map(int, ellipse[0]) 
            if debug_mode_on: #show contours 
                cv2.imshow(name_array[i-1] + " threshold", gray_copies[i-1])
                
            #in total pixels, first element is pixel total, next is ratio
            total_pixels = check_contour_pixels(reduced_contours[0], dilated_image.shape, debug_mode_on)                 
            
            cv2.ellipse(gray_copies[i-1], ellipse, (255, 0, 0), 2)  # Draw with specified color and thickness of 2
            font = cv2.FONT_HERSHEY_SIMPLEX  # Font type
            
            final_goodness = current_goodness[0]*total_pixels[0]*total_pixels[0]*total_pixels[1]

        if final_goodness > 0 and final_goodness > goodness: 
            goodness = final_goodness
            ellipse_reduced_contours = total_pixels[2]
            best_image = image_array[i-1]
            final_contours = reduced_contours
            final_image = dilated_image

    test_frame = frame.copy()
    
    final_contours = [optimize_contours_by_angle(final_contours, gray_frame)]
    
    final_rotated_rect = None

    if final_contours and not isinstance(final_contours[0], list) and len(final_contours[0] > 5):
        ellipse = cv2.fitEllipse(final_contours[0])
        final_rotated_rect = ellipse

        # Store the new ray in the list
        ray_lines.append(final_rotated_rect)
        # **Prune rays if list exceeds max_rays**
        if len(ray_lines) > max_rays:
            num_to_remove = len(ray_lines) - max_rays
            ray_lines = ray_lines[num_to_remove:]  # Keep only the last `max_rays` elements

    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg

    model_center_average = (320,240)

    model_center = compute_average_intersection(frame, ray_lines, 5, 1500, 5)

    if not sphere_center_locked_2d:
        # Normal behavior: keep updating running average while unlocked
        if model_center is not None:
            model_center_average = update_and_average_point(model_centers, model_center, 200)
        else:
            model_center_average = prev_model_center_avg

        # If we got something sensible, remember it as the last good value
        if model_center_average[0] != 0:
            prev_model_center_avg = model_center_average
            locked_model_center_avg = model_center_average
    else:
        # Once locked, always use the frozen center
        model_center_average = locked_model_center_avg

    
    # Example safety check
    if center_x is None or center_y is None or model_center_average[0] is None or model_center_average[1] is None:
        return  # or skip this frame

    # Calculate the distance only if model_centers has at least 100 values
    if len(model_centers) >= 100 and center_x is not None:
        distance = math.sqrt((center_x - model_center_average[0]) ** 2 + (center_y - model_center_average[1]) ** 2)
        if distance > max_observed_distance:
            max_observed_distance = distance
            
    max_observed_distance = 202

    # Draw reference lines/ellipses
    cv2.circle(frame, model_center_average, int(max_observed_distance), (255, 50, 50), 2)  # Draw eye sphere (circle)
    cv2.circle(frame, model_center_average, 8, (255, 255, 0), -1)  # Draw eye center



    if final_rotated_rect is not None and center_x is not None and center_y is not None:
        cv2.line(frame, model_center_average, (center_x, center_y), (255, 150, 50), 2)  # # Draw line from eye center to ellipse center
        
    cv2.ellipse(frame, final_rotated_rect, (20, 255, 255), 2) #draw final ellipse on image

    # Calculate the extended endpoint of gaze line
    if final_rotated_rect is not None and center_x is not None and center_y is not None:
        # Compute the vector from model_center_average to center_x, center_y
        dx = center_x - model_center_average[0]
        dy = center_y - model_center_average[1]

        # Scale the vector by 1.2x
        extended_x = int(model_center_average[0] + 2 * dx)
        extended_y = int(model_center_average[1] + 2 * dy)

        # Draw the extended gaze line
        cv2.line(frame, (center_x, center_y), (extended_x, extended_y), (200, 255, 0), 3) 




    if render_cv_window:
        cv2.imshow("Best Thresholded Image Contours on Frame", frame)


    if GL_SPHERE_AVAILABLE:
        gl_image = gl_sphere.update_sphere_rotation(center_x, center_y, model_center_average[0], model_center_average[1])
    #cv2.circle(frame, (center_x, center_y), 22, (255, 255, 0), -1)  # Draw intersection center

    # Call the function
    center, direction = compute_gaze_vector(center_x, center_y, model_center_average[0], model_center_average[1])

    if center is not None and direction is not None:
        origin_text = f"Origin: ({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f})"
        dir_text    = f"Direction: ({direction[0]:.2f}, {direction[1]:.2f}, {direction[2]:.2f})"

        # Set bottom-left corner for drawing text
        text_origin = (12, frame.shape[0] - 38)  # 40 pixels from bottom
        text_dir    = (12, frame.shape[0] - 13)  # 15 pixels from bottom
        text_origin2 = (10, frame.shape[0] - 40)  # 40 pixels from bottom
        text_dir2    = (10, frame.shape[0] - 15)  # 15 pixels from bottom

        # Draw shadow text on the frame
        cv2.putText(frame, origin_text, text_origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(frame, dir_text, text_dir, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        # Draw text on the frame
        cv2.putText(frame, origin_text, text_origin2, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        cv2.putText(frame, dir_text, text_dir2, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    if center is not None and direction is not None:
        print(f"Sphere Center:   ({center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f})")
        print(f"Gaze Direction:  ({direction[0]:.3f}, {direction[1]:.3f}, {direction[2]:.3f})")
    else:
        print("No valid intersection found.")

    cv2.imshow("Frame with Ellipse and Rays", frame)

    if GL_SPHERE_AVAILABLE:
        if gl_image is not None:
            blended = cv2.addWeighted(frame, 0.6, gl_image, 0.4, 0)
            cv2.imshow("Eye Tracker + Sphere", blended)

    return final_rotated_rect

def update_and_average_point(point_list, new_point, N):
    """
    Adds a new point to the list, keeps only the last N points, 
    and returns the average of those points.
    
    Parameters:
    - point_list: Global list storing past points [(x1, y1), (x2, y2), ...]
    - new_point: Tuple (x, y) representing the new point to add.
    - N: Maximum number of points to keep in the list.
    
    Returns:
    - (avg_x, avg_y): The average point as a tuple of integers.
    - None if the list is empty.
    """
    point_list.append(new_point)  # Add new point

    if len(point_list) > N:
        point_list.pop(0)  # Remove the oldest point to maintain size N

    if not point_list:
        return None  # No points available

    avg_x = int(np.mean([p[0] for p in point_list]))
    avg_y = int(np.mean([p[1] for p in point_list]))

    return (avg_x, avg_y)

def draw_orthogonal_ray(image, ellipse, length=100, color=(0, 255, 0), thickness=1):
    """
    Draws a ray passing through the center of an ellipse orthogonally to its major axis.
    
    Parameters:
    - image: The OpenCV image to draw on.
    - ellipse: A tuple ((cx, cy), (major_axis, minor_axis), angle) representing the fitted ellipse.
    - length: Length of the ray to draw on each side of the ellipse center.
    - color: Color of the line in BGR format (default: green).
    - thickness: Thickness of the line (default: 2).
    """

    (cx, cy), (major_axis, minor_axis), angle = ellipse
    
    # Convert angle to radians
    angle_rad = np.deg2rad(angle)
    
    # Compute the normal vector at the ellipse center (perpendicular to surface)
    normal_dx = (minor_axis / 2) * np.cos(angle_rad)  # Minor axis component
    normal_dy = (minor_axis / 2) * np.sin(angle_rad)

    # Compute start and end points of the orthogonal ray
    pt1 = (int(cx - length * normal_dx / (minor_axis / 2)), int(cy - length * normal_dy / (minor_axis / 2)))
    pt2 = (int(cx + length * normal_dx / (minor_axis / 2)), int(cy + length * normal_dy / (minor_axis / 2)))

    # Draw the ray
    cv2.line(image, pt1, pt2, color, thickness)

    return image 

stored_intersections = []  # Stores all past intersections

def compute_average_intersection(frame, ray_lines, N, M, spacing):
    """
    Selects N random lines from the list, highlights them in red on the frame,
    computes their intersections, stores them, and prunes stored intersections when exceeding M.

    Parameters:
    - frame: The OpenCV frame to draw on.
    - ray_lines: List of ellipse tuples ((cx, cy), (major_axis, minor_axis), angle).
    - N: Number of random lines to select for intersection calculation.
    - M: Maximum number of stored intersections before pruning.

    Returns:
    - (avg_x, avg_y): Average intersection point of selected lines.
    """
    global stored_intersections

    if len(ray_lines) < 2 or N < 2:
        return (0, 0)  # Need at least 2 lines to find intersections

    # Get frame dimensions dynamically
    height, width = frame.shape[:2]

    # Select N unique random lines
    selected_lines = random.sample(ray_lines, min(N, len(ray_lines)))

    intersections = []

    # Highlight selected rays in red
    #for ray in selected_lines:
    #    draw_orthogonal_ray(frame, ray, color=(0, 0, 255), thickness=2)  # Red lines

    # Compute intersections for each pair of selected lines
    for i in range(len(selected_lines) - 1):
        line1 = selected_lines[i]
        line2 = selected_lines[i + 1]

        angle1 = line1[2]  # Extract angle from ellipse tuple
        angle2 = line2[2]  # Extract angle from ellipse tuple

        if abs(angle1 - angle2) >= 2:  # Ensure lines differ by at least 2 degrees
            intersection = find_line_intersection(line1, line2)
            
            # Ensure the intersection is within the frame bounds before adding
            if intersection and (0 <= intersection[0] < width) and (0 <= intersection[1] < height):
                intersections.append(intersection)
                stored_intersections.append(intersection)  # Store valid intersections
        #else:
        #    print(f"Skipped intersection: Angle difference too small ({abs(angle1 - angle2):.2f}°)")

    # Prune intersections if stored list exceeds M
    if len(stored_intersections) > M:
        stored_intersections = prune_intersections(stored_intersections, M)

    # Draw all stored intersections on the frame
    #for pt in stored_intersections:
    #    cv2.circle(frame, pt, 3, (255, 255, 255), -1)  # White dot for every past intersection

    if not intersections:
        return None  # No valid intersections found

    # Compute the average intersection point
    avg_x = np.mean([pt[0] for pt in stored_intersections])
    avg_y = np.mean([pt[1] for pt in stored_intersections])


    return (int(avg_x), int(avg_y))

#Removes the oldest intersections to ensure only the last M intersections remain.
def prune_intersections(intersections, maximum_intersections):

    if len(intersections) <= maximum_intersections:
        return intersections  # No need to prune if within the limit

    # Keep only the last M intersections
    pruned_intersections = intersections[-maximum_intersections:]

    return pruned_intersections

def rotation_from_a_to_b(a, b):
    """
    Compute rotation matrix R such that R @ a = b
    using Rodrigues' rotation formula.
    """
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)

    v = np.cross(a, b)
    c = np.dot(a, b)

    if np.linalg.norm(v) < 1e-6:
        # Vectors are parallel or nearly so
        if c > 0:
            return np.eye(3, dtype=np.float32)
        else:
            # 180-degree flip: choose any axis orthogonal to a
            axis = np.array([1.0, 0.0, 0.0])
            if abs(a[0]) > 0.9:
                axis = np.array([0.0, 1.0, 0.0])
            v = np.cross(a, axis)
            v = v / np.linalg.norm(v)
            s = np.linalg.norm(v)
    else:
        s = np.linalg.norm(v)
        v = v / s

    # Skew-symmetric cross-product matrix
    vx, vy, vz = v
    K = np.array([
        [0,    -vz,  vy],
        [vz,    0,  -vx],
        [-vy,  vx,   0 ]
    ], dtype=np.float32)

    R = np.eye(3, dtype=np.float32) + K * s + (K @ K) * ((1 - c) / (s ** 2))
    return R

def update_gaze_circle_from_current_gaze():
    """
    Use the latest gaze vector to update the circle position on the external camera.
    Assumes we have calibrated R_gaze_to_cam that maps gaze_dir to external cam space.
    """
    global circle_x, circle_y, last_gaze_dir, calibrated

    if not calibrated or last_gaze_dir is None:
        return

    # Rotate gaze into external camera coordinate system
    g = R_gaze_to_cam @ last_gaze_dir

    # Avoid weird cases where gaze points behind the camera
    if g[2] <= 1e-6:
        return

    # Simple pinhole projection onto 2D
    u = EXT_CX + EXT_FX * (g[0] / g[2])
    v = EXT_CY - EXT_FY * (g[1] / g[2])

    # Clamp to screen bounds
    u = int(np.clip(u, 0, EXT_WIDTH - 1))
    v = int(np.clip(v, 0, EXT_HEIGHT - 1))

    circle_x, circle_y = u, v

def find_line_intersection(ellipse1, ellipse2):
    """
    Computes the intersection of two lines that are orthogonal to the surface of given ellipses.
    
    Parameters:
    - ellipse1, ellipse2: Ellipse tuples ((cx, cy), (major_axis, minor_axis), angle).
    
    Returns:
    - (x, y): Intersection point of the two lines, or None if parallel.
    """

    (cx1, cy1), (_, minor_axis1), angle1 = ellipse1
    (cx2, cy2), (_, minor_axis2), angle2 = ellipse2

    # Convert angles to radians
    angle1_rad = np.deg2rad(angle1)
    angle2_rad = np.deg2rad(angle2)

    # Compute direction vectors for the two lines
    dx1, dy1 = (minor_axis1 / 2) * np.cos(angle1_rad), (minor_axis1 / 2) * np.sin(angle1_rad)
    dx2, dy2 = (minor_axis2 / 2) * np.cos(angle2_rad), (minor_axis2 / 2) * np.sin(angle2_rad)

    # Line equations in parametric form:
    # (x1, y1) + t1 * (dx1, dy1) = (x2, y2) + t2 * (dx2, dy2)
    A = np.array([[dx1, -dx2], [dy1, -dy2]])
    B = np.array([cx2 - cx1, cy2 - cy1])

    # Solve for t1, t2 using linear algebra (if the determinant is nonzero)
    if np.linalg.det(A) == 0:
        return None  # Lines are parallel and do not intersect

    t1, t2 = np.linalg.solve(A, B)

    # Compute intersection point
    intersection_x = cx1 + t1 * dx1
    intersection_y = cy1 + t1 * dy1

    return (int(intersection_x), int(intersection_y))

def compute_gaze_vector(x, y, center_x, center_y, screen_width=640, screen_height=480):
    """Compute 3D gaze direction from pupil and sphere center screen coordinates.
    Returns:
        sphere_center (np.ndarray): 3D position of the sphere center in world space
        gaze_direction (np.ndarray): Normalized 3D direction vector from sphere center
    """

    # Get viewport dimensions
    viewport_width = screen_width
    viewport_height = screen_height

    # Define camera and projection settings
    fov_y_deg = 45.0
    aspect_ratio = viewport_width / viewport_height
    far_clip = 100.0

    # Camera position is fixed at z = 3
    camera_position = np.array([0.0, 0.0, 3.0])

    # Compute size of far plane in world units
    fov_y_rad = np.radians(fov_y_deg)
    half_height_far = np.tan(fov_y_rad / 2) * far_clip
    half_width_far = half_height_far * aspect_ratio

    # Convert screen (x, y) to normalized device coordinates [-1, 1]
    ndc_x = (2.0 * x) / viewport_width - 1.0
    ndc_y = 1.0 - (2.0 * y) / viewport_height

    # Project pupil center to far plane coordinates in world space
    far_x = ndc_x * half_width_far
    far_y = ndc_y * half_height_far
    far_z = camera_position[2] - far_clip
    far_point = np.array([far_x, far_y, far_z])

    # Compute ray direction from camera to far plane point
    ray_origin = camera_position
    ray_direction = far_point - camera_position
    ray_direction /= np.linalg.norm(ray_direction)
    ray_direction = -ray_direction

    # Sphere radius and center offset
    inner_radius = 1.0 / 1.05
    sphere_offset_x = (center_x / screen_width) * 2.0 - 1.0
    sphere_offset_y = 1.0 - (center_y / screen_height) * 2.0
    sphere_center = np.array([sphere_offset_x * 1.5, sphere_offset_y * 1.5, 0.0])

    # Compute intersection with sphere
    origin = ray_origin
    direction = -ray_direction
    L = origin - sphere_center

    a = np.dot(direction, direction)
    b = 2 * np.dot(direction, L)
    c = np.dot(L, L) - inner_radius**2

    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        # Compute the closest point to the sphere (tangent point approximation)
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

    # Final intersection point
    intersection_point = origin + t * direction
    intersection_local = intersection_point - sphere_center
    target_direction = intersection_local / np.linalg.norm(intersection_local)

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

    # Final intersection point
    intersection_point = origin + t * direction

    # Convert to local space relative to sphere center
    intersection_local = intersection_point - sphere_center
    target_direction = intersection_local / np.linalg.norm(intersection_local)

    # Local green ring direction
    circle_local_center = np.array([0.0, 0.0, inner_radius])
    circle_local_center /= np.linalg.norm(circle_local_center)

    # Compute rotation to align local +Z to target
    rotation_axis = np.cross(circle_local_center, target_direction)
    rotation_axis_norm = np.linalg.norm(rotation_axis)
    if rotation_axis_norm < 1e-6:
        return sphere_center, circle_local_center

    rotation_axis /= rotation_axis_norm
    dot = np.dot(circle_local_center, target_direction)
    dot = np.clip(dot, -1.0, 1.0)
    angle_rad = np.arccos(dot)

    # Rotation matrix from axis-angle
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    t_ = 1 - c
    x_, y_, z_ = rotation_axis

    rotation_matrix = np.array([
        [t_*x_*x_ + c, t_*x_*y_ - s*z_, t_*x_*z_ + s*y_],
        [t_*x_*y_ + s*z_, t_*y_*y_ + c, t_*y_*z_ - s*x_],
        [t_*x_*z_ - s*y_, t_*y_*z_ + s*x_, t_*z_*z_ + c]
    ])

     # Rotate +Z vector to get gaze direction
    gaze_local = np.array([0.0, 0.0, inner_radius])
    gaze_rotated = rotation_matrix @ gaze_local
    gaze_rotated /= np.linalg.norm(gaze_rotated)

    # --- Choose which sphere center to output: fixed (after calibration) or current ---
    global last_sphere_center, last_gaze_dir, calibrated_sphere_center
    last_sphere_center = sphere_center.copy()
    last_gaze_dir = gaze_rotated.copy()

    if calibrated_sphere_center is not None:
        sphere_center_out = calibrated_sphere_center
    else:
        sphere_center_out = sphere_center

    # --- Write to file (overwrite every frame) ---
    file_path = "gaze_vector.txt"

    def is_file_available(path):
        try:
            with open(path, "a"):
                return True
        except IOError:
            return False

    if is_file_available(file_path):
        try:
            with open(file_path, "w") as f:
                # Use sphere_center_out (fixed after calibration) for logging
                all_values = np.concatenate((sphere_center_out, gaze_rotated))
                csv_line = ",".join(f"{v:.6f}" for v in all_values)
                f.write(csv_line + "\n")
        except Exception as e:
            print("Write error:", e)
    else:
        print("File is currently in use. Skipping write.")

    return sphere_center_out, gaze_rotated

def on_mouse_frame_with_rays(event, x, y, flags, param):
    """
    Left-click on 'Frame with Ellipse and Rays' to manually set the eye sphere center.
    This behaves like pressing 'c': it locks the 2D center and fixes the 3D origin
    using the latest computed sphere center.
    """
    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg
    global calibrated_sphere_center, calibrated, last_sphere_center

    if event == cv2.EVENT_LBUTTONDOWN:
        # Lock the 2D center to the clicked point
        locked_model_center_avg = (x, y)
        prev_model_center_avg = locked_model_center_avg
        sphere_center_locked_2d = True

        # If we have a valid latest 3D sphere center, fix that too
        if last_sphere_center is not None:
            calibrated_sphere_center = last_sphere_center.copy()
            calibrated = True
            print("Manual sphere center set at 2D:", locked_model_center_avg)
            print("Fixed eye origin (sphere center 3D):", calibrated_sphere_center)
        else:
            print("Manual 2D center set at:", locked_model_center_avg,
                  "but no 3D sphere center available yet.")


def calibrate_gaze_to_external():
    global calibrated, R_gaze_to_cam, calibrated_sphere_center
    global sphere_center_locked_2d, locked_model_center_avg, prev_model_center_avg

    if last_gaze_dir is None or last_sphere_center is None:
        print("Calibration failed: no gaze vector / origin available yet.")
        return

    # We want R * last_gaze_dir = [0, 0, 1] (external cam forward)
    forward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    R_gaze_to_cam = rotation_from_a_to_b(last_gaze_dir, forward)

    # Fix the eyeball sphere center in 3D
    calibrated_sphere_center = last_sphere_center.copy()

    # Lock the 2D sphere center in the eye image
    sphere_center_locked_2d = True
    locked_model_center_avg = prev_model_center_avg
    print("2D sphere center locked at:", locked_model_center_avg)

    calibrated = True
    print("Calibration complete.")
    print("Fixed eye origin (sphere center 3D):", calibrated_sphere_center)





# Finds the pupil in an individual frame and returns the center point
def process_frame(frame):

    # Crop and resize frame
    frame = crop_to_aspect_ratio(frame)

    #find the darkest point
    darkest_point = get_darkest_area(frame)

    # Convert to grayscale to handle pixel value operations
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    darkest_pixel_value = gray_frame[darkest_point[1], darkest_point[0]]
    
    # apply thresholding operations at different levels
    # at least one should give us a good ellipse segment
    thresholded_image_strict = apply_binary_threshold(gray_frame, darkest_pixel_value, 5)#lite
    thresholded_image_strict = mask_outside_square(thresholded_image_strict, darkest_point, 250)

    thresholded_image_medium = apply_binary_threshold(gray_frame, darkest_pixel_value, 15)#medium
    thresholded_image_medium = mask_outside_square(thresholded_image_medium, darkest_point, 250)
    
    thresholded_image_relaxed = apply_binary_threshold(gray_frame, darkest_pixel_value, 25)#heavy
    thresholded_image_relaxed = mask_outside_square(thresholded_image_relaxed, darkest_point, 250)
    
    #take the three images thresholded at different levels and process them
    final_rotated_rect = process_frames(thresholded_image_strict, thresholded_image_medium, thresholded_image_relaxed, frame, gray_frame, darkest_point, False, False)
    
    return final_rotated_rect


# Process video from the selected eye camera + external camera preview
def process_camera():
    global selected_camera, circle_x, circle_y, calibrated

    cam_index = int(selected_camera.get())

    # ---- Eye camera (existing) ----
    eye_cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not eye_cap.isOpened():
        print(f"Error: Could not open eye camera at index {cam_index}.")
        return

    # ---- External camera (new) ----
    external_index = cam_index   # adjust if needed
    external_cap = cv2.VideoCapture(1, cv2.CAP_MSMF)

    if external_cap.isOpened():
        external_cap.set(cv2.CAP_PROP_FRAME_WIDTH, EXT_WIDTH)
        external_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, EXT_HEIGHT)
        print(f"External camera opened at index {external_index} ({EXT_WIDTH}x{EXT_HEIGHT}).")
    else:
        print(f"Warning: Could not open external camera at index {external_index}.")
        external_cap = None

    # Initial red circle at center (for calibration)
    circle_x, circle_y = EXT_CX, EXT_CY
    calibrated = False

    # Make sure the eye-frame window exists and hook mouse callback
    cv2.namedWindow("Frame with Ellipse and Rays")
    cv2.setMouseCallback("Frame with Ellipse and Rays", on_mouse_frame_with_rays)

    while True:
        # ----- Eye camera frame -----
        ret_eye, eye_frame = eye_cap.read()
        if not ret_eye:
            print("Failed to read frame from eye camera.")
            break

        cv2.imshow("Original Eye Frame", eye_frame)

        # Flip + process for ellipse / gaze vector
        eye_frame_flipped = cv2.flip(eye_frame, 0)
        process_frame(eye_frame_flipped)  # this updates last_gaze_dir via compute_gaze_vector

        # ----- External camera frame -----
        if external_cap is not None:
            ret_ext, ext_frame = external_cap.read()
            if ret_ext:
                ext_frame_resized = cv2.resize(ext_frame, (EXT_WIDTH, EXT_HEIGHT))

                # If calibrated, update circle based on current gaze
                if calibrated:
                    update_gaze_circle_from_current_gaze()

                # Draw small red circle representing gaze on external view
                cv2.circle(ext_frame_resized, (circle_x, circle_y), 8, (0, 0, 255), -1)

                cv2.imshow("External Camera (Gaze)", ext_frame_resized)
            else:
                print("Failed to read frame from external camera.")

        # ----- Key controls -----
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            # Pause until another key press
            cv2.waitKey(0)
        elif key == ord('c'):
            # Calibrate so current gaze ray hits the center of the external screen
            calibrate_gaze_to_external()

    # Cleanup
    eye_cap.release()
    if external_cap is not None:
        external_cap.release()
    cv2.destroyAllWindows()


# Process a selected video file
def process_video():
    video_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi")])

    if not video_path:
        return  # User canceled selection

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Error: Could not open video file.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        process_frame(frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            cv2.waitKey(0)

    cap.release()
    cv2.destroyAllWindows()
    

# GUI for selecting camera or video
def selection_gui():
    global selected_camera
    cameras = detect_cameras()

    # Create Tkinter window
    root = tk.Tk()
    root.title("Select Input Source")
    tk.Label(root, text="Orlosky Eye Tracker 3D", font=("Arial", 12, "bold")).pack(pady=10)

    tk.Label(root, text="Select Camera:").pack(pady=5)

    selected_camera = tk.StringVar()
    selected_camera.set(str(cameras[0]) if cameras else "No cameras found")

    camera_dropdown = ttk.Combobox(root, textvariable=selected_camera, values=[str(cam) for cam in cameras])
    camera_dropdown.pack(pady=5)

    tk.Button(root, text="Start Camera", command=lambda: [root.destroy(), process_camera()]).pack(pady=5)
    tk.Button(root, text="Browse Video", command=lambda: [root.destroy(), process_video()]).pack(pady=5)

    if GL_SPHERE_AVAILABLE:
        # Start GL sphere window once
        app = gl_sphere.start_gl_window() 

    root.mainloop()



# ======================================================================
# GALERIA 3D CONTROLADA PELO RASTREAMENTO OCULAR
# ----------------------------------------------------------------------
# Esta seção substitui o tracking facial por rastreamento ocular como
# entrada principal da galeria. A base do tracking ocular acima foi
# mantida e aqui ela passa a controlar:
#   - direção principal do cursor/gaze na galeria
#   - foco da obra por permanência olhando
#   - informações genéricas ao focar a obra
#   - 1 piscada = afasta
#   - 2 piscadas rápidas = aproxima
# O zoom manual também continua via teclado (+ / -).
# ======================================================================

from dataclasses import dataclass, field

GALLERY_WIDTH = 1280
GALLERY_HEIGHT = 720
GALLERY_CX = GALLERY_WIDTH // 2
GALLERY_CY = GALLERY_HEIGHT // 2

ARTWORKS = [
    {
        "id": 1,
        "title": "Luz e Ruído",
        "artist": "Arquivo Experimental",
        "year": "2024",
        "wall": "Esquerda",
        "genre": "Arte generativa",
        "desc": "Composição genérica com camadas de cor, contraste suave e leitura contemplativa.",
        "color": (88, 175, 255),
        "wall_key": "left",
        "slot": -1.25,
        "depth": 0.92,
    },
    {
        "id": 2,
        "title": "Mapa de Matéria",
        "artist": "Coleção de Estudos",
        "year": "2023",
        "wall": "Esquerda",
        "genre": "Abstração",
        "desc": "Obra de caráter analítico com textura visual, ritmo geométrico e atmosfera fria.",
        "color": (118, 110, 244),
        "wall_key": "left",
        "slot": -0.20,
        "depth": 1.06,
    },
    {
        "id": 3,
        "title": "Campo Central",
        "artist": "Série Museológica",
        "year": "2025",
        "wall": "Fundo",
        "genre": "Pintura digital",
        "desc": "Peça central com enquadramento amplo, massa de cor dominante e leitura frontal.",
        "color": (93, 210, 180),
        "wall_key": "back",
        "slot": -1.10,
        "depth": 0.88,
    },
    {
        "id": 4,
        "title": "Janela de Sinais",
        "artist": "Acervo Base",
        "year": "2022",
        "wall": "Fundo",
        "genre": "Composição mista",
        "desc": "Estrutura visual em camadas com áreas de foco contrastadas e narrativa aberta.",
        "color": (241, 192, 64),
        "wall_key": "back",
        "slot": 0.00,
        "depth": 0.80,
    },
    {
        "id": 5,
        "title": "Fragmento Orbital",
        "artist": "Estudo de Forma",
        "year": "2024",
        "wall": "Fundo",
        "genre": "Abstração geométrica",
        "desc": "Painel com eixo central, densidade moderada de elementos e leitura limpa.",
        "color": (255, 140, 100),
        "wall_key": "back",
        "slot": 1.12,
        "depth": 0.93,
    },
    {
        "id": 6,
        "title": "Velatura Azul",
        "artist": "Coleção de Referência",
        "year": "2021",
        "wall": "Direita",
        "genre": "Pintura contemporânea",
        "desc": "Superfície visual com gradação de luz, leve ruído cromático e sensação de profundidade.",
        "color": (120, 200, 255),
        "wall_key": "right",
        "slot": -1.15,
        "depth": 1.08,
    },
    {
        "id": 7,
        "title": "Topografia da Cor",
        "artist": "Arquivo Curatorial",
        "year": "2020",
        "wall": "Direita",
        "genre": "Arte digital",
        "desc": "Composição de leitura lateral com variação de planos e massa de cor concentrada.",
        "color": (210, 120, 255),
        "wall_key": "right",
        "slot": 0.05,
        "depth": 0.96,
    },
]

def clamp(v, a, b):
    return max(a, min(b, v))

def lerp(a, b, t):
    return a + (b - a) * t

def mix_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

def draw_text(img, text, org, color=(235, 242, 255), scale=0.55, thickness=1, shadow=True):
    x, y = int(org[0]), int(org[1])
    if shadow:
        cv2.putText(img, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)

@dataclass
class BlinkState:
    phase: str = "open"
    close_frames: int = 0
    open_frames: int = 0
    close_ts: float = 0.0
    pending_single_ts: float = 0.0
    last_event_ts: float = 0.0
    debug: str = "idle"
    min_close_frames: int = 2
    min_open_frames: int = 2
    min_ms: int = 70
    max_ms: int = 520
    double_window_ms: int = 560
    debounce_ms: int = 160

@dataclass
class GalleryState:
    gaze_x: float = GALLERY_CX
    gaze_y: float = GALLERY_CY
    smooth_x: float = GALLERY_CX
    smooth_y: float = GALLERY_CY
    cursor_visible: bool = False
    hovered_id: int | None = None
    selected_id: int | None = None
    hover_started_ts: float = 0.0
    hover_progress: float = 0.0
    dwell_ms: int = 820
    zoom_level: int = 1
    zoom_steps: list = field(default_factory=lambda: [0.82, 1.00, 1.18, 1.40, 1.70])
    camera_pan: float = 0.0
    camera_tilt: float = 0.0
    last_message: str = "Aguardando calibração ocular"
    blink: BlinkState = field(default_factory=BlinkState)
    render_map: dict = field(default_factory=dict)
    last_blink_label: str = "Pronto"
    status: str = "Sem calibração"
    weak_tracking: bool = False
    last_focus_ts: float = 0.0

class EyeControlledGallery:
    def __init__(self):
        self.state = GalleryState()
        self.window_name = "Galeria 3D - Eye Tracker"
        self.info_window_name = "Painel da Obra"
        self.last_frame = np.zeros((GALLERY_HEIGHT, GALLERY_WIDTH, 3), dtype=np.uint8)
        self.last_render_ts = time.time()

    def set_status(self, msg):
        self.state.status = msg

    def set_message(self, msg):
        self.state.last_message = msg

    def zoom_in(self, reason="zoom_in"):
        old = self.state.zoom_level
        self.state.zoom_level = min(len(self.state.zoom_steps) - 1, self.state.zoom_level + 1)
        if self.state.zoom_level != old:
            self.set_message(f"Aproximando ({reason})")
            self.state.last_blink_label = "Aproxima"
        else:
            self.set_message("Zoom máximo")

    def zoom_out(self, reason="zoom_out"):
        old = self.state.zoom_level
        self.state.zoom_level = max(0, self.state.zoom_level - 1)
        if self.state.zoom_level != old:
            self.set_message(f"Afastando ({reason})")
            self.state.last_blink_label = "Afasta"
        else:
            self.set_message("Zoom mínimo")

    def selected_artwork(self):
        aid = self.state.selected_id or self.state.hovered_id
        if aid is None:
            return None
        for art in ARTWORKS:
            if art["id"] == aid:
                return art
        return None

    def update_gaze(self, gx, gy, calibrated_ok):
        if calibrated_ok:
            x = (gx / max(1, EXT_WIDTH)) * GALLERY_WIDTH
            y = (gy / max(1, EXT_HEIGHT)) * GALLERY_HEIGHT
            self.state.cursor_visible = True
            self.state.gaze_x = clamp(x, 0, GALLERY_WIDTH - 1)
            self.state.gaze_y = clamp(y, 0, GALLERY_HEIGHT - 1)
            self.state.status = "Calibrado"
        else:
            self.state.cursor_visible = False
            self.state.gaze_x = GALLERY_CX
            self.state.gaze_y = GALLERY_CY
            self.state.status = "Sem calibração"

        self.state.smooth_x = lerp(self.state.smooth_x, self.state.gaze_x, 0.30)
        self.state.smooth_y = lerp(self.state.smooth_y, self.state.gaze_y, 0.30)

        nx = (self.state.smooth_x / GALLERY_WIDTH) * 2.0 - 1.0
        ny = (self.state.smooth_y / GALLERY_HEIGHT) * 2.0 - 1.0
        self.state.camera_pan = lerp(self.state.camera_pan, nx * 0.85, 0.12)
        self.state.camera_tilt = lerp(self.state.camera_tilt, ny * 0.35, 0.12)

    def _register_blink(self, now_ms):
        b = self.state.blink
        if (now_ms - b.last_event_ts) < b.debounce_ms:
            b.debug = "debounced"
            return

        if b.pending_single_ts and (now_ms - b.pending_single_ts) <= b.double_window_ms:
            b.pending_single_ts = 0
            b.last_event_ts = now_ms
            b.debug = "double"
            self.state.last_blink_label = "2 piscadas"
            self.zoom_in("duplo blink")
            return

        b.pending_single_ts = now_ms
        b.last_event_ts = now_ms
        b.debug = "single_wait"
        self.state.last_blink_label = "1 piscada"

    def update_blink(self, ellipse_ok):
        b = self.state.blink
        now_ms = int(time.time() * 1000)

        if ellipse_ok:
            b.open_frames += 1
            if b.phase == "open":
                b.close_frames = 0
        else:
            b.close_frames += 1
            b.open_frames = 0

        if b.phase == "open" and b.close_frames >= b.min_close_frames:
            b.phase = "closed"
            b.close_ts = now_ms
            b.debug = "closed"
        elif b.phase == "closed" and b.open_frames >= b.min_open_frames:
            duration = now_ms - b.close_ts
            b.phase = "open"
            b.close_frames = 0
            b.open_frames = 0
            if b.min_ms <= duration <= b.max_ms:
                self._register_blink(now_ms)
            else:
                b.debug = f"ignored_{duration}"

        if b.pending_single_ts and (now_ms - b.pending_single_ts) > b.double_window_ms:
            b.pending_single_ts = 0
            b.debug = "single_fire"
            self.state.last_blink_label = "1 piscada"
            self.zoom_out("blink único")

    def _project_artwork(self, art):
        zoom = self.state.zoom_steps[self.state.zoom_level]
        pan = self.state.camera_pan
        tilt = self.state.camera_tilt

        wall = art["wall_key"]
        slot = art["slot"]
        depth = art["depth"]

        # Fatores de profundidade e deslocamento.
        base_scale = zoom / depth
        if wall == "back":
            cx = GALLERY_CX + (slot * 225 - pan * 240) * base_scale
            cy = GALLERY_CY - 20 + tilt * 18
            w = int(118 * base_scale)
            h = int(154 * base_scale)
            rect = (int(cx - w / 2), int(cy - h / 2), w, h)
            quad = np.array([
                [rect[0], rect[1]],
                [rect[0] + rect[2], rect[1]],
                [rect[0] + rect[2], rect[1] + rect[3]],
                [rect[0], rect[1] + rect[3]],
            ], dtype=np.int32)
        elif wall == "left":
            cx = 250 + slot * 82 - pan * 150
            cy = GALLERY_CY - 15 + slot * 8 + tilt * 12
            w = int(92 * base_scale)
            h = int(132 * base_scale)
            rect = (int(cx - w / 2), int(cy - h / 2), w, h)
            skew = int(max(16, w * 0.30))
            quad = np.array([
                [rect[0] + skew, rect[1]],
                [rect[0] + rect[2], rect[1] + 6],
                [rect[0] + rect[2] - skew, rect[1] + rect[3]],
                [rect[0], rect[1] + rect[3] - 6],
            ], dtype=np.int32)
        else:  # right
            cx = GALLERY_WIDTH - 250 + slot * 82 - pan * 150
            cy = GALLERY_CY - 10 + slot * 8 + tilt * 12
            w = int(92 * base_scale)
            h = int(132 * base_scale)
            rect = (int(cx - w / 2), int(cy - h / 2), w, h)
            skew = int(max(16, w * 0.30))
            quad = np.array([
                [rect[0], rect[1] + 6],
                [rect[0] + rect[2] - skew, rect[1]],
                [rect[0] + rect[2], rect[1] + rect[3] - 6],
                [rect[0] + skew, rect[1] + rect[3]],
            ], dtype=np.int32)

        return rect, quad, base_scale

    def _update_hover(self):
        gx, gy = self.state.smooth_x, self.state.smooth_y
        closest = None
        closest_d = 1e9

        for aid, data in self.state.render_map.items():
            rect = data["rect"]
            x, y, w, h = rect
            inflate = 26
            inside = (x - inflate) <= gx <= (x + w + inflate) and (y - inflate) <= gy <= (y + h + inflate)
            cx = x + w * 0.5
            cy = y + h * 0.5
            d = ((gx - cx) ** 2 + (gy - cy) ** 2) ** 0.5
            if inside:
                closest = aid
                closest_d = d
                break
            if d < closest_d:
                closest = aid
                closest_d = d

        if closest is not None and closest_d <= 120:
            if self.state.hovered_id != closest:
                self.state.hovered_id = closest
                self.state.hover_started_ts = time.time()
                self.state.hover_progress = 0.0
            else:
                elapsed_ms = (time.time() - self.state.hover_started_ts) * 1000.0
                self.state.hover_progress = clamp(elapsed_ms / self.state.dwell_ms, 0.0, 1.0)
                if elapsed_ms >= self.state.dwell_ms:
                    self.state.selected_id = closest
                    self.state.last_focus_ts = time.time()
        else:
            self.state.hovered_id = None
            self.state.hover_started_ts = 0.0
            self.state.hover_progress = 0.0

    def _draw_background(self, img):
        for y in range(GALLERY_HEIGHT):
            t = y / max(1, GALLERY_HEIGHT - 1)
            c = mix_color((5, 12, 28), (13, 20, 38), t)
            cv2.line(img, (0, y), (GALLERY_WIDTH, y), c, 1)

        # brilho superior
        overlay = img.copy()
        cv2.ellipse(overlay, (int(GALLERY_WIDTH * 0.22), 0), (430, 180), 0, 0, 180, (60, 100, 160), -1)
        cv2.ellipse(overlay, (int(GALLERY_WIDTH * 0.82), GALLERY_HEIGHT), (320, 160), 0, 180, 360, (70, 40, 120), -1)
        cv2.addWeighted(overlay, 0.13, img, 0.87, 0, img)

    def _draw_room(self, img):
        pan_px = int(self.state.camera_pan * 58)
        # teto
        ceiling = np.array([[140 - pan_px, 110], [GALLERY_WIDTH - 140 - pan_px, 110], [GALLERY_WIDTH - 260 - pan_px, 220], [260 - pan_px, 220]], np.int32)
        left_wall = np.array([[140 - pan_px, 110], [260 - pan_px, 220], [260 - pan_px, GALLERY_HEIGHT - 130], [110 - pan_px, GALLERY_HEIGHT - 40]], np.int32)
        right_wall = np.array([[GALLERY_WIDTH - 140 - pan_px, 110], [GALLERY_WIDTH - 260 - pan_px, 220], [GALLERY_WIDTH - 260 - pan_px, GALLERY_HEIGHT - 130], [GALLERY_WIDTH - 110 - pan_px, GALLERY_HEIGHT - 40]], np.int32)
        back_wall = np.array([[260 - pan_px, 220], [GALLERY_WIDTH - 260 - pan_px, 220], [GALLERY_WIDTH - 260 - pan_px, GALLERY_HEIGHT - 130], [260 - pan_px, GALLERY_HEIGHT - 130]], np.int32)
        floor = np.array([[260 - pan_px, GALLERY_HEIGHT - 130], [GALLERY_WIDTH - 260 - pan_px, GALLERY_HEIGHT - 130], [GALLERY_WIDTH - 110 - pan_px, GALLERY_HEIGHT - 40], [110 - pan_px, GALLERY_HEIGHT - 40]], np.int32)

        cv2.fillConvexPoly(img, ceiling, (16, 22, 38))
        cv2.fillConvexPoly(img, left_wall, (20, 28, 46))
        cv2.fillConvexPoly(img, right_wall, (20, 28, 46))
        cv2.fillConvexPoly(img, back_wall, (28, 35, 54))
        cv2.fillConvexPoly(img, floor, (14, 18, 28))

        cv2.polylines(img, [ceiling, left_wall, right_wall, back_wall, floor], True, (70, 86, 120), 1, cv2.LINE_AA)

        # linhas de profundidade/parallax
        for i in range(6):
            t = i / 5.0
            x1 = int(260 - pan_px + t * 90)
            x2 = int(GALLERY_WIDTH - 260 - pan_px - t * 90)
            y = int(220 + t * (GALLERY_HEIGHT - 350))
            cv2.line(img, (x1, y), (x2, y), (34, 44, 66), 1, cv2.LINE_AA)

        # painéis translúcidos de profundidade
        for idx in range(3):
            depth_t = 0.25 + idx * 0.2
            par = int(pan_px * (0.4 + idx * 0.18))
            alpha = 0.05 + idx * 0.03
            panel = np.array([
                [300 - par + idx * 30, 240 + idx * 18],
                [GALLERY_WIDTH - 300 - par - idx * 30, 240 + idx * 18],
                [GALLERY_WIDTH - 330 - par - idx * 28, GALLERY_HEIGHT - 160 + idx * 8],
                [330 - par + idx * 28, GALLERY_HEIGHT - 160 + idx * 8],
            ], np.int32)
            overlay = img.copy()
            cv2.fillConvexPoly(overlay, panel, (90 + idx * 20, 110, 150 + idx * 25))
            cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    def _draw_artwork(self, img, art, rect, quad, scale):
        x, y, w, h = rect
        hovered = art["id"] == self.state.hovered_id
        selected = art["id"] == self.state.selected_id
        accent = art["color"]

        shadow = quad.copy()
        shadow[:, 0] += 8
        shadow[:, 1] += 10
        cv2.fillConvexPoly(img, shadow, (10, 10, 16))

        frame_color = (223, 228, 235) if (hovered or selected) else (185, 190, 205)
        fill_color = mix_color(accent, (245, 246, 248), 0.28 if selected else 0.18)

        cv2.fillConvexPoly(img, quad, (28, 30, 38))
        inner = quad.copy().astype(np.float32)
        center = np.mean(inner, axis=0)
        inner = center + (inner - center) * 0.86
        inner = inner.astype(np.int32)
        cv2.fillConvexPoly(img, inner, fill_color)
        cv2.polylines(img, [quad], True, frame_color, 3 if selected else 2, cv2.LINE_AA)
        cv2.polylines(img, [inner], True, (250, 250, 250), 1, cv2.LINE_AA)

        # arte interna simples
        xi, yi, wi, hi = cv2.boundingRect(inner)
        for i in range(5):
            yy = yi + int((i + 1) * hi / 6)
            cv2.line(img, (xi + 12, yy), (xi + wi - 14, yy - int((i - 2) * 2)), mix_color(accent, (255, 255, 255), 0.4), 2, cv2.LINE_AA)

        cv2.circle(img, (xi + wi // 2, yi + hi // 2), int(min(wi, hi) * 0.14), mix_color(accent, (255, 255, 255), 0.15), -1, cv2.LINE_AA)
        cv2.circle(img, (xi + wi // 2, yi + hi // 2), int(min(wi, hi) * 0.14), mix_color(accent, (255, 255, 255), 0.65), 2, cv2.LINE_AA)

        # legenda curta na parede
        label_y = y + h + 20
        draw_text(img, art["title"], (x, label_y), scale=0.46 if scale < 1.2 else 0.52, thickness=1)
        draw_text(img, art["artist"], (x, label_y + 18), color=(145, 170, 210), scale=0.42, thickness=1)

        if hovered or selected:
            panel_w = 320
            panel_h = 104
            px = int(clamp(x + w * 0.5 - panel_w * 0.5, 18, GALLERY_WIDTH - panel_w - 18))
            py = int(clamp(y - panel_h - 18, 18, GALLERY_HEIGHT - panel_h - 18))
            panel = img.copy()
            cv2.rectangle(panel, (px, py), (px + panel_w, py + panel_h), (12, 18, 30), -1)
            cv2.rectangle(panel, (px, py), (px + panel_w, py + panel_h), accent, 1)
            cv2.addWeighted(panel, 0.82, img, 0.18, 0, img)
            draw_text(img, art["title"], (px + 12, py + 24), scale=0.62, thickness=1)
            draw_text(img, f'{art["artist"]} · {art["year"]} · {art["genre"]}', (px + 12, py + 46), color=(130, 200, 255), scale=0.45, thickness=1)
            desc = art["desc"]
            draw_text(img, desc[:52], (px + 12, py + 70), color=(188, 201, 218), scale=0.42, thickness=1)
            if len(desc) > 52:
                draw_text(img, desc[52:104], (px + 12, py + 90), color=(188, 201, 218), scale=0.42, thickness=1)

    def render(self):
        img = np.zeros((GALLERY_HEIGHT, GALLERY_WIDTH, 3), dtype=np.uint8)
        self._draw_background(img)
        self._draw_room(img)

        render_entries = []
        self.state.render_map = {}
        for art in ARTWORKS:
            rect, quad, scale = self._project_artwork(art)
            render_entries.append((art["depth"], art, rect, quad, scale))

        # mais distante primeiro
        for _, art, rect, quad, scale in sorted(render_entries, key=lambda x: x[0], reverse=True):
            self.state.render_map[art["id"]] = {"rect": rect, "quad": quad, "scale": scale}
            self._draw_artwork(img, art, rect, quad, scale)

        self._update_hover()

        # cursor do olhar
        if self.state.cursor_visible:
            gx, gy = int(self.state.smooth_x), int(self.state.smooth_y)
            cv2.circle(img, (gx, gy), 16, (240, 248, 255), 2, cv2.LINE_AA)
            cv2.circle(img, (gx, gy), 6, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (gx, gy), 28, (90, 173, 226), 1, cv2.LINE_AA)

        # HUD
        draw_text(img, "Galeria 3D - Eye Tracker", (22, 34), scale=0.82, thickness=2)
        draw_text(img, f"Status: {self.state.status}", (22, 60), color=(130, 245, 170), scale=0.52, thickness=1)
        draw_text(img, f"Zoom: {self.state.zoom_level+1}/{len(self.state.zoom_steps)}", (22, 84), color=(180, 195, 220), scale=0.48, thickness=1)
        draw_text(img, f"Blink: {self.state.last_blink_label}", (22, 106), color=(255, 205, 120), scale=0.48, thickness=1)
        draw_text(img, self.state.last_message, (22, GALLERY_HEIGHT - 26), color=(168, 180, 205), scale=0.50, thickness=1)

        # barra de permanência
        bx, by, bw, bh = 22, 126, 220, 10
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (34, 42, 60), -1)
        fill = int(bw * self.state.hover_progress)
        cv2.rectangle(img, (bx, by), (bx + fill, by + bh), (93, 173, 226), -1)
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (110, 126, 166), 1)
        draw_text(img, "Foco por permanência", (bx, by - 8), color=(150, 168, 200), scale=0.42, thickness=1)

        art = self.selected_artwork()
        info = np.zeros((210, 400, 3), dtype=np.uint8)
        info[:] = (12, 16, 26)
        cv2.rectangle(info, (0, 0), (399, 209), (74, 86, 116), 1)
        if art is not None:
            draw_text(info, art["title"], (14, 28), scale=0.70, thickness=2)
            draw_text(info, f'{art["artist"]} · {art["year"]}', (14, 54), color=(130, 200, 255), scale=0.50, thickness=1)
            draw_text(info, f'Parede: {art["wall"]}', (14, 84), scale=0.48, thickness=1)
            draw_text(info, f'Categoria: {art["genre"]}', (14, 108), scale=0.48, thickness=1)
            desc1 = art["desc"][:48]
            desc2 = art["desc"][48:96]
            draw_text(info, desc1, (14, 142), color=(192, 204, 218), scale=0.46, thickness=1)
            if desc2:
                draw_text(info, desc2, (14, 166), color=(192, 204, 218), scale=0.46, thickness=1)
        else:
            draw_text(info, "Nenhuma obra selecionada", (14, 28), scale=0.62, thickness=2)
            draw_text(info, "Olhe para um quadro por alguns instantes.", (14, 60), color=(190, 202, 220), scale=0.48, thickness=1)
            draw_text(info, "1 piscada = afasta", (14, 96), color=(255, 200, 120), scale=0.48, thickness=1)
            draw_text(info, "2 piscadas = aproxima", (14, 120), color=(255, 200, 120), scale=0.48, thickness=1)
            draw_text(info, "Teclas: C calibrar, + / - zoom, Q sair", (14, 154), color=(145, 170, 210), scale=0.44, thickness=1)

        self.last_frame = img
        return img, info

    def show(self):
        img, info = self.render()
        cv2.imshow(self.window_name, img)
        cv2.imshow(self.info_window_name, info)

def process_camera():
    global selected_camera, circle_x, circle_y, calibrated

    cam_index = int(selected_camera.get())
    eye_cap = cv2.VideoCapture(cam_index, cv2.CAP_MSMF)
    if not eye_cap.isOpened():
        print(f"Error: Could not open eye camera at index {cam_index}.")
        return

    # câmera externa opcional: tenta próxima câmera primeiro
    external_cap = None
    for ext_idx in [cam_index + 1, 1, 0]:
        if ext_idx == cam_index:
            continue
        cap = cv2.VideoCapture(ext_idx, cv2.CAP_MSMF)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, EXT_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, EXT_HEIGHT)
            external_cap = cap
            print(f"External camera opened at index {ext_idx} ({EXT_WIDTH}x{EXT_HEIGHT}).")
            break
        cap.release()

    if external_cap is None:
        print("Warning: external camera not available. Gallery control still works after calibration.")

    circle_x, circle_y = EXT_CX, EXT_CY
    calibrated = False

    gallery = EyeControlledGallery()
    gallery.set_message("Pressione C para calibrar o olhar no centro da galeria")

    cv2.namedWindow("Frame with Ellipse and Rays")
    cv2.setMouseCallback("Frame with Ellipse and Rays", on_mouse_frame_with_rays)

    while True:
        ret_eye, eye_frame = eye_cap.read()
        if not ret_eye:
            print("Failed to read frame from eye camera.")
            break

        cv2.imshow("Original Eye Frame", eye_frame)

        eye_frame_flipped = cv2.flip(eye_frame, 0)
        ellipse = process_frame(eye_frame_flipped)
        ellipse_ok = ellipse is not None

        if calibrated:
            update_gaze_circle_from_current_gaze()

        gallery.update_gaze(circle_x, circle_y, calibrated)
        gallery.update_blink(ellipse_ok)
        gallery.show()

        if external_cap is not None:
            ret_ext, ext_frame = external_cap.read()
            if ret_ext:
                ext_frame_resized = cv2.resize(ext_frame, (EXT_WIDTH, EXT_HEIGHT))
                if calibrated:
                    cv2.circle(ext_frame_resized, (circle_x, circle_y), 8, (0, 0, 255), -1)
                draw_text(ext_frame_resized, "Preview externo", (12, 26), scale=0.55, thickness=1)
                cv2.imshow("External Camera (Gaze)", ext_frame_resized)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            cv2.waitKey(0)
        elif key == ord('c'):
            calibrate_gaze_to_external()
            gallery.set_status("Calibrado")
            gallery.set_message("Calibração concluída. Olhe para os quadros.")
        elif key in (ord('+'), ord('=')):
            gallery.zoom_in("teclado")
        elif key in (ord('-'), ord('_')):
            gallery.zoom_out("teclado")
        elif key == ord('r'):
            calibrated = False
            circle_x, circle_y = EXT_CX, EXT_CY
            gallery.set_status("Sem calibração")
            gallery.set_message("Calibração resetada")

    eye_cap.release()
    if external_cap is not None:
        external_cap.release()
    cv2.destroyAllWindows()

def process_video():
    video_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi")])
    if not video_path:
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video file.")
        return

    gallery = EyeControlledGallery()
    gallery.set_message("Vídeo carregado. Use C para calibrar se houver gaze estável.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        ellipse = process_frame(frame)
        gallery.update_gaze(circle_x, circle_y, calibrated)
        gallery.update_blink(ellipse is not None)
        gallery.show()

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            calibrate_gaze_to_external()
            gallery.set_status("Calibrado")
        elif key in (ord('+'), ord('=')):
            gallery.zoom_in("teclado")
        elif key in (ord('-'), ord('_')):
            gallery.zoom_out("teclado")

    cap.release()
    cv2.destroyAllWindows()

def selection_gui():
    global selected_camera
    cameras = detect_cameras()

    root = tk.Tk()
    root.title("Galeria 3D com Eye Tracking")
    root.geometry("420x260")
    root.configure(bg="#0b1220")

    tk.Label(root, text="Galeria 3D + Rastreamento Ocular", font=("Arial", 14, "bold"), fg="white", bg="#0b1220").pack(pady=12)
    tk.Label(root, text="Núcleo de gaze baseado no código ocular enviado.\nSem tracking facial da outra versão.", font=("Arial", 10), fg="#b7c6e0", bg="#0b1220").pack(pady=4)

    tk.Label(root, text="Selecione a câmera do olho:", fg="white", bg="#0b1220").pack(pady=8)

    selected_camera = tk.StringVar()
    selected_camera.set(str(cameras[0]) if cameras else "0")

    camera_dropdown = ttk.Combobox(root, textvariable=selected_camera, values=[str(cam) for cam in cameras] if cameras else ["0"])
    camera_dropdown.pack(pady=6)

    help_text = (
        "C = calibrar\n"
        "+ / - = zoom manual\n"
        "1 piscada = afasta\n"
        "2 piscadas = aproxima\n"
        "Q = sair"
    )
    tk.Label(root, text=help_text, fg="#9eb4d9", bg="#0b1220", justify="left").pack(pady=10)

    tk.Button(root, text="Iniciar câmera", width=24, command=lambda: [root.destroy(), process_camera()]).pack(pady=6)
    tk.Button(root, text="Abrir vídeo", width=24, command=lambda: [root.destroy(), process_video()]).pack(pady=4)

    root.mainloop()

if __name__ == "__main__":
    selection_gui()
