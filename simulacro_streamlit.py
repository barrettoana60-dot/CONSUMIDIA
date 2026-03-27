import math
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import av
import cv2
import mediapipe as mp
import numpy as np
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Rastreamento de Pupila/Íris 3D",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .small-note {font-size: 0.92rem; opacity: 0.9;}
    .metric-box {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .target-wrap {
        width: 100%;
        aspect-ratio: 16/9;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.15);
        background:
            linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02)),
            radial-gradient(circle at 50% 50%, rgba(255,255,255,0.06), rgba(0,0,0,0.12));
        position: relative;
        overflow: hidden;
    }
    .target-dot {
        position: absolute;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #ff3b30;
        box-shadow: 0 0 0 8px rgba(255,59,48,0.12), 0 0 22px rgba(255,59,48,0.55);
        transform: translate(-50%, -50%);
    }
    .gaze-dot {
        position: absolute;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: #00e0ff;
        box-shadow: 0 0 0 8px rgba(0,224,255,0.12), 0 0 20px rgba(0,224,255,0.55);
        transform: translate(-50%, -50%);
    }
    .guide-grid {
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
        background-size: 12.5% 12.5%;
        pointer-events: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# LANDMARK SETS
# ============================================================
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_EYE_RING = [33, 133, 159, 145, 153, 154, 155, 173]
LEFT_EYE_RING = [362, 263, 386, 374, 380, 381, 382, 398]
RIGHT_EYE_CORNERS = (33, 133)
LEFT_EYE_CORNERS = (362, 263)
RIGHT_EYE_UP_DOWN = (159, 145)
LEFT_EYE_UP_DOWN = (386, 374)

HEAD_POSE_INDICES = [1, 152, 33, 263, 61, 291]
MODEL_POINTS_3D = np.array(
    [
        [0.0, 0.0, 0.0],          # nose tip
        [0.0, -63.6, -12.5],      # chin
        [-43.3, 32.7, -26.0],     # left eye outer corner
        [43.3, 32.7, -26.0],      # right eye outer corner
        [-28.9, -28.9, -24.1],    # left mouth corner
        [28.9, -28.9, -24.1],     # right mouth corner
    ],
    dtype=np.float64,
)

# Approximate eyeball centers in the canonical head model (millimeters).
LEFT_EYEBALL_CENTER_CANON = np.array([-29.0, 33.0, -34.0], dtype=np.float64)
RIGHT_EYEBALL_CENTER_CANON = np.array([29.0, 33.0, -34.0], dtype=np.float64)

CALIBRATION_POINTS = [
    (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
    (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
    (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
]


# ============================================================
# MATH HELPERS
# ============================================================
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-9:
        return v.copy()
    return v / n


def mean_points(points: np.ndarray, idxs: List[int]) -> np.ndarray:
    return np.mean(points[idxs], axis=0)


def project_points(points_3d: np.ndarray, rvec: np.ndarray, tvec: np.ndarray, camera_matrix: np.ndarray) -> np.ndarray:
    pts2d, _ = cv2.projectPoints(points_3d, rvec, tvec, camera_matrix, np.zeros((4, 1), dtype=np.float64))
    return pts2d.reshape(-1, 2)


def rotation_matrix_from_rvec(rvec: np.ndarray) -> np.ndarray:
    R, _ = cv2.Rodrigues(rvec)
    return R


def yaw_pitch_from_rotation(R: np.ndarray) -> Tuple[float, float]:
    forward = R @ np.array([0.0, 0.0, 1.0], dtype=np.float64)
    yaw = math.atan2(forward[0], max(1e-6, forward[2]))
    pitch = -math.atan2(forward[1], max(1e-6, math.sqrt(forward[0] ** 2 + forward[2] ** 2)))
    return yaw, pitch


def intersect_ray_with_plane(ray_origin: np.ndarray, ray_dir: np.ndarray, plane_z: float) -> Optional[np.ndarray]:
    dz = float(ray_dir[2])
    if abs(dz) < 1e-6:
        return None
    t = (plane_z - float(ray_origin[2])) / dz
    if t <= 0:
        return None
    return ray_origin + t * ray_dir


def eye_geometry(points_2d: np.ndarray, iris_idxs: List[int], ring_idxs: List[int], corner_idxs: Tuple[int, int], up_down_idxs: Tuple[int, int]):
    iris_center = mean_points(points_2d, iris_idxs)
    ring_center = mean_points(points_2d, ring_idxs)
    eye_width = float(np.linalg.norm(points_2d[corner_idxs[0]] - points_2d[corner_idxs[1]]))
    eye_height = float(np.linalg.norm(points_2d[up_down_idxs[0]] - points_2d[up_down_idxs[1]]))
    return iris_center, ring_center, eye_width, eye_height


def make_camera_matrix(width: int, height: int, focal_scale: float = 1.15) -> np.ndarray:
    focal = width * focal_scale
    return np.array(
        [
            [focal, 0.0, width / 2.0],
            [0.0, focal, height / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def fit_linear_calibration(samples: List[Tuple[np.ndarray, np.ndarray]]) -> Optional[np.ndarray]:
    if len(samples) < 5:
        return None
    X = np.array([s[0] for s in samples], dtype=np.float64)
    Y = np.array([s[1] for s in samples], dtype=np.float64)
    # Least-squares affine-like mapping with pose terms.
    coef, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    return coef


def apply_linear_calibration(feature_vec: np.ndarray, coef: Optional[np.ndarray]) -> np.ndarray:
    if coef is None:
        return feature_vec[:2].copy()
    out = feature_vec @ coef
    return np.array([clamp(out[0]), clamp(out[1])], dtype=np.float64)


def raw_feature_vector(raw_xy: np.ndarray, head_yaw: float, head_pitch: float) -> np.ndarray:
    return np.array([raw_xy[0], raw_xy[1], head_yaw, head_pitch, 1.0], dtype=np.float64)


def draw_pose_cube(frame: np.ndarray, rvec: np.ndarray, tvec: np.ndarray, camera_matrix: np.ndarray):
    cube = np.array(
        [
            [-40, -40, 60],
            [40, -40, 60],
            [40, 40, 60],
            [-40, 40, 60],
            [-40, -40, 140],
            [40, -40, 140],
            [40, 40, 140],
            [-40, 40, 140],
        ],
        dtype=np.float64,
    )
    pts = project_points(cube, rvec, tvec, camera_matrix).astype(int)
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    for a, b in edges:
        cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (60, 255, 220), 2, cv2.LINE_AA)


def draw_crosshair(frame: np.ndarray, pt: Tuple[int, int], color=(0, 224, 255), size: int = 10):
    x, y = int(pt[0]), int(pt[1])
    cv2.line(frame, (x - size, y), (x + size, y), color, 2, cv2.LINE_AA)
    cv2.line(frame, (x, y - size), (x, y + size), color, 2, cv2.LINE_AA)


# ============================================================
# SHARED STATE
# ============================================================
@dataclass
class SharedGazeState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    screen_width_cm: float = 53.0
    screen_height_cm: float = 30.0
    screen_distance_cm: float = 60.0
    screen_res_w: int = 1920
    screen_res_h: int = 1080

    face_found: bool = False
    raw_hit_xy: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.5], dtype=np.float64))
    centered_raw_xy: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.5], dtype=np.float64))
    calibrated_xy: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.5], dtype=np.float64))
    latest_feature_vec: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.5, 0.0, 0.0, 1.0], dtype=np.float64))
    head_yaw: float = 0.0
    head_pitch: float = 0.0
    last_status: str = "Aguardando vídeo"

    left_eye_center_3d: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    right_eye_center_3d: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    left_iris_center_2d: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    right_iris_center_2d: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    rotation_matrix: np.ndarray = field(default_factory=lambda: np.eye(3, dtype=np.float64))

    center_bias: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    calibration_samples: List[Tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    calibration_coef: Optional[np.ndarray] = None

    def set_screen(self, width_cm: float, height_cm: float, distance_cm: float, res_w: int, res_h: int):
        with self.lock:
            self.screen_width_cm = float(width_cm)
            self.screen_height_cm = float(height_cm)
            self.screen_distance_cm = float(distance_cm)
            self.screen_res_w = int(res_w)
            self.screen_res_h = int(res_h)

    def get_screen_mm(self) -> Tuple[float, float, float]:
        return self.screen_width_cm * 10.0, self.screen_height_cm * 10.0, self.screen_distance_cm * 10.0

    def capture_center(self):
        with self.lock:
            self.center_bias = self.raw_hit_xy - np.array([0.5, 0.5], dtype=np.float64)
            self.last_status = "Centro bruto capturado"

    def clear_center(self):
        with self.lock:
            self.center_bias = np.zeros(2, dtype=np.float64)
            self.last_status = "Centro bruto resetado"

    def capture_calibration(self, target_xy: Tuple[float, float]):
        with self.lock:
            target = np.array(target_xy, dtype=np.float64)
            self.calibration_samples.append((self.latest_feature_vec.copy(), target))
            self.last_status = f"Ponto de calibração capturado: {len(self.calibration_samples)}"
            coef = fit_linear_calibration(self.calibration_samples)
            if coef is not None:
                self.calibration_coef = coef
                self.last_status = f"Calibração ajustada com {len(self.calibration_samples)} ponto(s)"

    def reset_calibration(self):
        with self.lock:
            self.calibration_samples = []
            self.calibration_coef = None
            self.last_status = "Calibração resetada"

    def snapshot(self):
        with self.lock:
            return {
                "screen_width_cm": self.screen_width_cm,
                "screen_height_cm": self.screen_height_cm,
                "screen_distance_cm": self.screen_distance_cm,
                "screen_res_w": self.screen_res_w,
                "screen_res_h": self.screen_res_h,
                "face_found": self.face_found,
                "raw_hit_xy": self.raw_hit_xy.copy(),
                "centered_raw_xy": self.centered_raw_xy.copy(),
                "calibrated_xy": self.calibrated_xy.copy(),
                "head_yaw": self.head_yaw,
                "head_pitch": self.head_pitch,
                "center_bias": self.center_bias.copy(),
                "calibration_n": len(self.calibration_samples),
                "last_status": self.last_status,
                "rotation_matrix": self.rotation_matrix.copy(),
            }


STATE = SharedGazeState()


# ============================================================
# VIDEO PROCESSOR
# ============================================================
class GazeVideoProcessor:
    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def _estimate_head_pose(self, pts2d: np.ndarray, width: int, height: int):
        image_points = np.array([pts2d[i] for i in HEAD_POSE_INDICES], dtype=np.float64)
        cam = make_camera_matrix(width, height)
        ok, rvec, tvec = cv2.solvePnP(
            MODEL_POINTS_3D,
            image_points,
            cam,
            np.zeros((4, 1), dtype=np.float64),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return None, None, cam
        return rvec, tvec, cam

    def _eye_ray(self, iris_center: np.ndarray, eye_center_2d: np.ndarray, eye_width: float, eye_height: float, eyeball_center_3d: np.ndarray, R_head: np.ndarray):
        eye_width = max(eye_width, 1.0)
        eye_height = max(eye_height, 1.0)
        dx = (iris_center[0] - eye_center_2d[0]) / (eye_width / 2.0)
        dy = (iris_center[1] - eye_center_2d[1]) / (eye_height / 2.0)
        dx = float(np.clip(dx, -1.2, 1.2))
        dy = float(np.clip(dy, -1.2, 1.2))

        max_yaw = math.radians(35.0)
        max_pitch = math.radians(25.0)
        eye_yaw = dx * max_yaw
        eye_pitch = -dy * max_pitch

        local_dir = normalize(
            np.array(
                [
                    math.tan(eye_yaw),
                    math.tan(eye_pitch),
                    1.0,
                ],
                dtype=np.float64,
            )
        )
        cam_dir = normalize(R_head @ local_dir)
        return cam_dir, eye_yaw, eye_pitch

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            with STATE.lock:
                STATE.face_found = False
                STATE.last_status = "Rosto não detectado"
            cv2.putText(img, "Rosto nao detectado", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        face_landmarks = results.multi_face_landmarks[0].landmark
        pts2d = np.array([[lm.x * w, lm.y * h] for lm in face_landmarks], dtype=np.float64)

        rvec, tvec, cam = self._estimate_head_pose(pts2d, w, h)
        if rvec is None:
            with STATE.lock:
                STATE.face_found = False
                STATE.last_status = "Falha na pose da cabeca"
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        R_head = rotation_matrix_from_rvec(rvec)
        head_yaw, head_pitch = yaw_pitch_from_rotation(R_head)

        left_iris_center, left_eye_center_2d, left_eye_width, left_eye_height = eye_geometry(
            pts2d, LEFT_IRIS, LEFT_EYE_RING, LEFT_EYE_CORNERS, LEFT_EYE_UP_DOWN
        )
        right_iris_center, right_eye_center_2d, right_eye_width, right_eye_height = eye_geometry(
            pts2d, RIGHT_IRIS, RIGHT_EYE_RING, RIGHT_EYE_CORNERS, RIGHT_EYE_UP_DOWN
        )

        left_eye_center_3d = (R_head @ LEFT_EYEBALL_CENTER_CANON.reshape(3, 1) + tvec).reshape(3)
        right_eye_center_3d = (R_head @ RIGHT_EYEBALL_CENTER_CANON.reshape(3, 1) + tvec).reshape(3)

        left_ray_dir, _, _ = self._eye_ray(
            left_iris_center, left_eye_center_2d, left_eye_width, left_eye_height, left_eye_center_3d, R_head
        )
        right_ray_dir, _, _ = self._eye_ray(
            right_iris_center, right_eye_center_2d, right_eye_width, right_eye_height, right_eye_center_3d, R_head
        )

        screen_w_mm, screen_h_mm, screen_z_mm = STATE.get_screen_mm()
        left_hit = intersect_ray_with_plane(left_eye_center_3d, left_ray_dir, screen_z_mm)
        right_hit = intersect_ray_with_plane(right_eye_center_3d, right_ray_dir, screen_z_mm)

        if left_hit is None and right_hit is None:
            avg_hit = np.array([0.0, 0.0, screen_z_mm], dtype=np.float64)
        elif left_hit is None:
            avg_hit = right_hit
        elif right_hit is None:
            avg_hit = left_hit
        else:
            avg_hit = 0.5 * (left_hit + right_hit)

        raw_x = ((avg_hit[0] / (screen_w_mm / 2.0)) + 1.0) / 2.0
        raw_y = ((avg_hit[1] / (screen_h_mm / 2.0)) + 1.0) / 2.0
        raw_xy = np.array([clamp(raw_x), clamp(raw_y)], dtype=np.float64)

        with STATE.lock:
            centered_raw = raw_xy - STATE.center_bias
            centered_raw = np.array([clamp(centered_raw[0]), clamp(centered_raw[1])], dtype=np.float64)
            feature_vec = raw_feature_vector(centered_raw, head_yaw, head_pitch)
            calibrated_xy = apply_linear_calibration(feature_vec, STATE.calibration_coef)

            STATE.face_found = True
            STATE.raw_hit_xy = raw_xy
            STATE.centered_raw_xy = centered_raw
            STATE.calibrated_xy = calibrated_xy
            STATE.latest_feature_vec = feature_vec
            STATE.left_eye_center_3d = left_eye_center_3d
            STATE.right_eye_center_3d = right_eye_center_3d
            STATE.left_iris_center_2d = left_iris_center
            STATE.right_iris_center_2d = right_iris_center
            STATE.rotation_matrix = R_head
            STATE.head_yaw = head_yaw
            STATE.head_pitch = head_pitch
            STATE.last_status = "Rastreamento ativo"

        # OVERLAY -------------------------------------------------
        draw_pose_cube(img, rvec, tvec, cam)

        # Iris centers and eye centers on image
        cv2.circle(img, tuple(np.int32(left_iris_center)), 5, (0, 255, 0), -1, cv2.LINE_AA)
        cv2.circle(img, tuple(np.int32(right_iris_center)), 5, (0, 255, 0), -1, cv2.LINE_AA)
        cv2.circle(img, tuple(np.int32(left_eye_center_2d)), 4, (255, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(img, tuple(np.int32(right_eye_center_2d)), 4, (255, 0, 255), -1, cv2.LINE_AA)

        # Ray visualization from the 3D eye centers
        ray_pts_3d = np.array(
            [
                left_eye_center_3d,
                left_eye_center_3d + left_ray_dir * 180.0,
                right_eye_center_3d,
                right_eye_center_3d + right_ray_dir * 180.0,
            ],
            dtype=np.float64,
        )
        ray_pts_2d = project_points(ray_pts_3d, np.zeros((3, 1), dtype=np.float64), np.zeros((3, 1), dtype=np.float64), cam).astype(int)
        cv2.line(img, tuple(ray_pts_2d[0]), tuple(ray_pts_2d[1]), (255, 180, 0), 2, cv2.LINE_AA)
        cv2.line(img, tuple(ray_pts_2d[2]), tuple(ray_pts_2d[3]), (255, 180, 0), 2, cv2.LINE_AA)

        # Crosshair on virtual-screen estimate for debugging text
        with STATE.lock:
            dbg_xy = STATE.calibrated_xy.copy()
            dbg_raw = STATE.centered_raw_xy.copy()

        text_lines = [
            f"Raw centered: ({dbg_raw[0]:.3f}, {dbg_raw[1]:.3f})",
            f"Calibrated: ({dbg_xy[0]:.3f}, {dbg_xy[1]:.3f})",
            f"Head yaw/pitch: ({math.degrees(head_yaw):.1f} deg, {math.degrees(head_pitch):.1f} deg)",
            "Cube = rotation matrix visualized on head pose",
        ]
        y0 = 28
        for i, line in enumerate(text_lines):
            cv2.putText(img, line, (16, y0 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (240, 240, 240), 2, cv2.LINE_AA)

        draw_crosshair(img, (int(left_iris_center[0]), int(left_iris_center[1])), color=(0, 255, 0), size=8)
        draw_crosshair(img, (int(right_iris_center[0]), int(right_iris_center[1])), color=(0, 255, 0), size=8)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


# ============================================================
# UI HELPERS
# ============================================================
def render_target_screen(target_xy: Optional[Tuple[float, float]], gaze_xy: Tuple[float, float]) -> str:
    tx, ty = (target_xy if target_xy is not None else (None, None))
    gx, gy = gaze_xy
    target_html = ""
    if tx is not None and ty is not None:
        target_html = f'<div class="target-dot" style="left:{tx*100:.2f}%; top:{ty*100:.2f}%;"></div>'
    gaze_html = f'<div class="gaze-dot" style="left:{gx*100:.2f}%; top:{gy*100:.2f}%;"></div>'
    return f'''
    <div class="target-wrap">
        <div class="guide-grid"></div>
        {target_html}
        {gaze_html}
    </div>
    '''


def matrix_to_html(R: np.ndarray) -> str:
    rows = []
    for r in R:
        rows.append("[" + ", ".join(f"{v:+0.3f}" for v in r) + "]")
    return "<br>".join(rows)


# ============================================================
# SIDEBAR / SETTINGS
# ============================================================
st.title("Rastreamento de Pupila/Íris 3D para Streamlit")
st.caption(
    "App completo com: 1) centros dos olhos, 2) centros da pupila/íris, 3) projeção de raios, 4) interseção com o plano da tela, 5) binding do monitor real para monitor virtual e 6) calibração multiponto."
)

with st.sidebar:
    st.header("Tela / Monitor")
    screen_width_cm = st.number_input("Largura física do monitor (cm)", min_value=20.0, max_value=120.0, value=53.0, step=0.5)
    screen_height_cm = st.number_input("Altura física do monitor (cm)", min_value=12.0, max_value=80.0, value=30.0, step=0.5)
    screen_distance_cm = st.number_input("Distância olhos -> tela (cm)", min_value=20.0, max_value=120.0, value=60.0, step=0.5)
    screen_res_w = st.number_input("Resolução horizontal (px)", min_value=640, max_value=7680, value=1920, step=10)
    screen_res_h = st.number_input("Resolução vertical (px)", min_value=360, max_value=4320, value=1080, step=10)
    if st.button("Aplicar parâmetros da tela", use_container_width=True):
        STATE.set_screen(screen_width_cm, screen_height_cm, screen_distance_cm, int(screen_res_w), int(screen_res_h))

    st.divider()
    st.markdown(
        """
        **Webcam recomendada**
        - 720p ou 1080p
        - 30 fps ou mais
        - câmera na altura do rosto
        - iluminação frontal estável
        - sem contraluz
        """
    )

snapshot = STATE.snapshot()

col_a, col_b = st.columns([1.35, 1.0], gap="large")

with col_a:
    st.subheader("Vídeo em tempo real")
    webrtc_streamer(
        key="gaze-tracker",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=GazeVideoProcessor,
        async_processing=True,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    )
    st.markdown(
        "<div class='small-note'>Olhe para o ponto vermelho durante a calibração. O ponto azul representa a estimativa atual na tela virtual.</div>",
        unsafe_allow_html=True,
    )

with col_b:
    st.subheader("Tela virtual")

    if "cal_idx" not in st.session_state:
        st.session_state.cal_idx = 0

    current_target = None
    if 0 <= st.session_state.cal_idx < len(CALIBRATION_POINTS):
        current_target = CALIBRATION_POINTS[st.session_state.cal_idx]

    st.markdown(
        render_target_screen(current_target, tuple(snapshot["calibrated_xy"])),
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Capturar centro bruto", use_container_width=True):
            STATE.capture_center()
        if st.button("Resetar centro bruto", use_container_width=True):
            STATE.clear_center()
    with c2:
        if st.button("Capturar ponto atual", use_container_width=True):
            if current_target is not None:
                STATE.capture_calibration(current_target)
                st.session_state.cal_idx = min(st.session_state.cal_idx + 1, len(CALIBRATION_POINTS))
        if st.button("Resetar calibração", use_container_width=True):
            STATE.reset_calibration()
            st.session_state.cal_idx = 0

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("Voltar um ponto", use_container_width=True):
            st.session_state.cal_idx = max(0, st.session_state.cal_idx - 1)
    with nav2:
        if st.button("Pular ponto", use_container_width=True):
            st.session_state.cal_idx = min(len(CALIBRATION_POINTS), st.session_state.cal_idx + 1)

    st.markdown(f"**Próximo ponto:** {st.session_state.cal_idx + 1 if st.session_state.cal_idx < len(CALIBRATION_POINTS) else 'fim'} / {len(CALIBRATION_POINTS)}")

    st.markdown("### Estado")
    st.markdown(f"<div class='metric-box'><b>Status:</b> {snapshot['last_status']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-box'><b>Face detectada:</b> {'Sim' if snapshot['face_found'] else 'Não'}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-box'><b>Amostras de calibração:</b> {snapshot['calibration_n']}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='metric-box'><b>Olhar bruto corrigido:</b> ({snapshot['centered_raw_xy'][0]:.3f}, {snapshot['centered_raw_xy'][1]:.3f})</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-box'><b>Olhar calibrado:</b> ({snapshot['calibrated_xy'][0]:.3f}, {snapshot['calibrated_xy'][1]:.3f})</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-box'><b>Pixel estimado:</b> ({int(snapshot['calibrated_xy'][0]*snapshot['screen_res_w'])}, {int(snapshot['calibrated_xy'][1]*snapshot['screen_res_h'])})</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='metric-box'><b>Yaw/Pitch da cabeça:</b> ({math.degrees(snapshot['head_yaw']):.2f}°, {math.degrees(snapshot['head_pitch']):.2f}°)</div>",
        unsafe_allow_html=True,
    )

st.divider()

left_info, right_info = st.columns(2, gap="large")
with left_info:
    st.subheader("Matriz de rotação atual")
    st.markdown(f"<div class='metric-box' style='font-family: monospace'>{matrix_to_html(snapshot['rotation_matrix'])}</div>", unsafe_allow_html=True)

with right_info:
    st.subheader("Como o algoritmo funciona")
    st.markdown(
        """
        1. Detecta landmarks faciais refinados da Face Mesh com íris.
        2. Calcula o centro 2D de cada íris/pupila e o centro geométrico de cada olho.
        3. Estima a pose da cabeça por `solvePnP`.
        4. Usa centros 3D aproximados dos globos oculares no modelo canônico da face.
        5. Projeta um raio de cada olho com base no desvio da íris dentro da abertura ocular.
        6. Intersecta os dois raios com o plano do monitor virtual.
        7. Corrige o centro bruto e depois ajusta a saída por calibração multiponto.
        """
    )

st.divider()
st.subheader("Observações importantes")
st.markdown(
    """
