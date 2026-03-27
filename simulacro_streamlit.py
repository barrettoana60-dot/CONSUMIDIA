import io
import math
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import av
import cv2
import mediapipe as mp
import numpy as np
import streamlit as st
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image
from streamlit_autorefresh import st_autorefresh
from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer


st.set_page_config(
    page_title="Simulacro Eye Gallery",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded",
)


SCENE_W = 1280
SCENE_H = 720


PAINTINGS = [
    {
        "id": "q1",
        "title": "Memória Costeira",
        "artist": "Acervo Experimental",
        "year": "2026",
        "wall": "left",
        "center": (-3.98, 1.70, 2.20),
        "size": (1.20, 0.85),
        "summary": "Estudo visual sobre memória, território e paisagem litorânea.",
        "details": [
            "Técnica: impressão pigmentada sobre suporte rígido",
            "Tema: patrimônio, memória social e espacialidade",
            "Leitura curatorial: relações entre paisagem e pertencimento",
        ],
    },
    {
        "id": "q2",
        "title": "Topografia Afetiva",
        "artist": "Coletivo Simulacro",
        "year": "2026",
        "wall": "left",
        "center": (-3.98, 1.65, 5.10),
        "size": (1.25, 0.95),
        "summary": "Camadas cromáticas que evocam mapas, trajetos e deslocamentos.",
        "details": [
            "Material: composição digital em camadas",
            "Cor dominante: tons frios com acentos quentes",
            "Uso sugerido: mediação e leitura de atenção visual",
        ],
    },
    {
        "id": "q3",
        "title": "Núcleo de Luz",
        "artist": "Laboratório de Imagem",
        "year": "2026",
        "wall": "front",
        "center": (0.0, 1.72, 9.55),
        "size": (1.55, 1.05),
        "summary": "Peça central da sala, focada em profundidade, contraste e centralidade.",
        "details": [
            "Disposição: parede de fundo",
            "Objetivo: funcionar como âncora visual da cena",
            "Interação: ótimo alvo para testes de dwell e zoom",
        ],
    },
    {
        "id": "q4",
        "title": "Vestígios de Matéria",
        "artist": "Arquivo Sensível",
        "year": "2025",
        "wall": "right",
        "center": (3.98, 1.70, 2.55),
        "size": (1.15, 0.82),
        "summary": "Texturas e microestruturas inspiradas em observação material.",
        "details": [
            "Técnica: composição digital + textura procedural",
            "Interesse: leitura de superfície e ritmo",
            "Aplicação: demonstração de inspeção visual",
        ],
    },
    {
        "id": "q5",
        "title": "Campo de Perspectiva",
        "artist": "Unidade Experimental",
        "year": "2026",
        "wall": "right",
        "center": (3.98, 1.65, 5.35),
        "size": (1.20, 0.90),
        "summary": "Obra construída para testar percepção de profundidade e parallax.",
        "details": [
            "Estrutura: composição geométrica em vários planos",
            "Função: medir fixação do olhar",
            "Interação: destaque em experiências com mapa de calor",
        ],
    },
]


LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_EYE_H = (33, 133)
RIGHT_EYE_H = (362, 263)
LEFT_EYE_V = (159, 145)
RIGHT_EYE_V = (386, 374)
LEFT_EYE_TOP_BOTTOM = (159, 145)
RIGHT_EYE_TOP_BOTTOM = (386, 374)


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    gaze_norm: Tuple[float, float] = (0.5, 0.5)
    face_detected: bool = False
    blink_count_total: int = 0
    zoom_level: float = 1.0
    active_painting_id: Optional[str] = None
    focus_started_at: Optional[float] = None
    focus_seconds_by_painting: Dict[str, float] = field(default_factory=dict)
    blink_timestamps: List[float] = field(default_factory=list)
    pending_single_blink_ts: Optional[float] = None
    zoom_events: List[Tuple[float, str, float]] = field(default_factory=list)
    eye_contact_samples: int = 0
    gaze_samples_norm: List[Tuple[float, float, float]] = field(default_factory=list)
    session_started_at: float = field(default_factory=time.time)
    last_info_title: str = "Nenhum quadro selecionado"
    last_info_body: str = "Olhe para um quadro por alguns instantes para abrir a ficha rápida."
    current_blink_ratio: float = 0.0
    calibration_offset: Tuple[float, float] = (0.0, 0.0)
    last_rendered_scene: Optional[np.ndarray] = None
    last_scene_cursor: Tuple[int, int] = (SCENE_W // 2, SCENE_H // 2)
    debug_text: str = "Aguardando câmera"


STATE = SharedState()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def now_ts() -> float:
    return time.time()


def make_painting_texture(meta: dict, width: int = 420, height: int = 300) -> np.ndarray:
    seed = sum(ord(c) for c in meta["id"])
    rng = np.random.default_rng(seed)
    img = np.zeros((height, width, 3), dtype=np.uint8)

    c1 = np.array(rng.integers(40, 180, size=3), dtype=np.uint8)
    c2 = np.array(rng.integers(80, 230, size=3), dtype=np.uint8)
    c3 = np.array(rng.integers(30, 120, size=3), dtype=np.uint8)

    for y in range(height):
        t = y / max(1, height - 1)
        color = (1 - t) * c1 + t * c2
        img[y, :, :] = color.astype(np.uint8)

    for _ in range(80):
        x1 = int(rng.integers(0, width))
        y1 = int(rng.integers(0, height))
        x2 = int(clamp(x1 + int(rng.integers(-120, 120)), 0, width - 1))
        y2 = int(clamp(y1 + int(rng.integers(-80, 80)), 0, height - 1))
        col = tuple(int(v) for v in rng.integers(100, 255, size=3))
        cv2.line(img, (x1, y1), (x2, y2), col, int(rng.integers(1, 4)))

    for _ in range(12):
        cx = int(rng.integers(0, width))
        cy = int(rng.integers(0, height))
        r = int(rng.integers(16, 58))
        col = tuple(int(v) for v in (0.5 * c3 + 0.5 * rng.integers(120, 255, size=3)).astype(np.uint8))
        cv2.circle(img, (cx, cy), r, col, -1)
        cv2.circle(img, (cx, cy), max(4, r // 2), (255, 255, 255), 2)

    cv2.rectangle(img, (8, 8), (width - 8, height - 8), (245, 245, 245), 4)
    cv2.rectangle(img, (18, 18), (width - 18, height - 18), (20, 20, 20), 1)
    cv2.putText(img, meta["title"], (24, height - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (15, 15, 15), 3, cv2.LINE_AA)
    cv2.putText(img, meta["title"], (24, height - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (248, 248, 248), 1, cv2.LINE_AA)
    cv2.putText(img, f"{meta['artist']} | {meta['year']}", (24, height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(img, f"{meta['artist']} | {meta['year']}", (24, height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (250, 250, 250), 1, cv2.LINE_AA)
    return img


TEXTURES = {meta["id"]: make_painting_texture(meta) for meta in PAINTINGS}


def point_from_landmark(landmark, width: int, height: int) -> np.ndarray:
    return np.array([landmark.x * width, landmark.y * height], dtype=np.float32)


def average_points(points: List[np.ndarray]) -> np.ndarray:
    if not points:
        return np.zeros(2, dtype=np.float32)
    return np.mean(np.stack(points, axis=0), axis=0)


class EyeTrackerProcessor(VideoProcessorBase):
    def __init__(self):
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.prev_smoothed = np.array([0.5, 0.5], dtype=np.float32)
        self.closed_frames = 0
        self.eye_closed = False
        self.last_frame_ts = now_ts()

    def _blink_ratio(self, landmarks, w: int, h: int) -> float:
        left_h = np.linalg.norm(point_from_landmark(landmarks[LEFT_EYE_H[0]], w, h) - point_from_landmark(landmarks[LEFT_EYE_H[1]], w, h))
        right_h = np.linalg.norm(point_from_landmark(landmarks[RIGHT_EYE_H[0]], w, h) - point_from_landmark(landmarks[RIGHT_EYE_H[1]], w, h))
        left_v = np.linalg.norm(point_from_landmark(landmarks[LEFT_EYE_V[0]], w, h) - point_from_landmark(landmarks[LEFT_EYE_V[1]], w, h))
        right_v = np.linalg.norm(point_from_landmark(landmarks[RIGHT_EYE_V[0]], w, h) - point_from_landmark(landmarks[RIGHT_EYE_V[1]], w, h))
        left_ratio = left_v / max(left_h, 1e-6)
        right_ratio = right_v / max(right_h, 1e-6)
        return float((left_ratio + right_ratio) / 2.0)

    def _estimate_gaze(self, landmarks, w: int, h: int) -> Tuple[float, float]:
        left_iris_center = average_points([point_from_landmark(landmarks[i], w, h) for i in LEFT_IRIS])
        right_iris_center = average_points([point_from_landmark(landmarks[i], w, h) for i in RIGHT_IRIS])

        left_inner = point_from_landmark(landmarks[133], w, h)
        left_outer = point_from_landmark(landmarks[33], w, h)
        right_inner = point_from_landmark(landmarks[362], w, h)
        right_outer = point_from_landmark(landmarks[263], w, h)

        left_top = point_from_landmark(landmarks[159], w, h)
        left_bottom = point_from_landmark(landmarks[145], w, h)
        right_top = point_from_landmark(landmarks[386], w, h)
        right_bottom = point_from_landmark(landmarks[374], w, h)

        left_x = (left_iris_center[0] - left_outer[0]) / max(left_inner[0] - left_outer[0], 1e-6)
        right_x = (right_iris_center[0] - right_inner[0]) / max(right_outer[0] - right_inner[0], 1e-6)

        left_y = (left_iris_center[1] - left_top[1]) / max(left_bottom[1] - left_top[1], 1e-6)
        right_y = (right_iris_center[1] - right_top[1]) / max(right_bottom[1] - right_top[1], 1e-6)

        gaze_x = float(np.mean([left_x, 1.0 - right_x]))
        gaze_y = float(np.mean([left_y, right_y]))

        gaze_x = clamp((gaze_x - 0.48) * 1.65 + 0.5, 0.0, 1.0)
        gaze_y = clamp((gaze_y - 0.5) * 1.75 + 0.5, 0.0, 1.0)
        return gaze_x, gaze_y

    def _handle_blinks(self, blink_ratio: float):
        ts = now_ts()
        blink_threshold = 0.16
        min_closed_frames = 2

        with STATE.lock:
            STATE.current_blink_ratio = blink_ratio

        if blink_ratio < blink_threshold:
            self.closed_frames += 1
            if self.closed_frames >= min_closed_frames:
                self.eye_closed = True
        else:
            if self.eye_closed:
                self.eye_closed = False
                self.closed_frames = 0
                with STATE.lock:
                    STATE.blink_count_total += 1
                    STATE.blink_timestamps = [t for t in STATE.blink_timestamps if ts - t <= 1.0]
                    STATE.blink_timestamps.append(ts)
                    if len(STATE.blink_timestamps) >= 2 and ts - STATE.blink_timestamps[-2] <= 0.9:
                        STATE.zoom_level = clamp(STATE.zoom_level + 0.25, 0.75, 2.2)
                        STATE.zoom_events.append((ts, "zoom_in", STATE.zoom_level))
                        STATE.pending_single_blink_ts = None
                        STATE.blink_timestamps.clear()
                    else:
                        STATE.pending_single_blink_ts = ts
            else:
                self.closed_frames = 0

        with STATE.lock:
            pending = STATE.pending_single_blink_ts
            if pending is not None and ts - pending > 0.85:
                STATE.zoom_level = clamp(STATE.zoom_level - 0.20, 0.75, 2.2)
                STATE.zoom_events.append((ts, "zoom_out", STATE.zoom_level))
                STATE.pending_single_blink_ts = None
                STATE.blink_timestamps.clear()

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = self.mesh.process(rgb)

        if result.multi_face_landmarks:
            landmarks = result.multi_face_landmarks[0].landmark
            gaze_x, gaze_y = self._estimate_gaze(landmarks, w, h)
            blink_ratio = self._blink_ratio(landmarks, w, h)
            self._handle_blinks(blink_ratio)

            with STATE.lock:
                off_x, off_y = STATE.calibration_offset
                gaze_x = clamp(gaze_x + off_x, 0.0, 1.0)
                gaze_y = clamp(gaze_y + off_y, 0.0, 1.0)
                alpha = 0.23
                self.prev_smoothed[0] = lerp(float(self.prev_smoothed[0]), gaze_x, alpha)
                self.prev_smoothed[1] = lerp(float(self.prev_smoothed[1]), gaze_y, alpha)
                STATE.gaze_norm = (float(self.prev_smoothed[0]), float(self.prev_smoothed[1]))
                STATE.face_detected = True
                STATE.eye_contact_samples += 1
                STATE.gaze_samples_norm.append((ts := now_ts(), STATE.gaze_norm[0], STATE.gaze_norm[1]))
                if len(STATE.gaze_samples_norm) > 8000:
                    STATE.gaze_samples_norm = STATE.gaze_samples_norm[-8000:]
                STATE.debug_text = f"Face detectada | gaze=({STATE.gaze_norm[0]:.2f}, {STATE.gaze_norm[1]:.2f}) | blink={blink_ratio:.3f}"

            left_iris = average_points([point_from_landmark(landmarks[i], w, h) for i in LEFT_IRIS]).astype(int)
            right_iris = average_points([point_from_landmark(landmarks[i], w, h) for i in RIGHT_IRIS]).astype(int)
            cv2.circle(img, tuple(left_iris), 5, (0, 255, 0), 2)
            cv2.circle(img, tuple(right_iris), 5, (0, 255, 0), 2)
            cv2.putText(img, "Eye tracking ativo", (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (20, 235, 20), 2, cv2.LINE_AA)
            cv2.putText(img, "Piscar 2x = zoom | Piscar 1x = afastar", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        else:
            with STATE.lock:
                STATE.face_detected = False
                STATE.debug_text = "Nenhum rosto detectado"
            cv2.putText(img, "Aproxime o rosto e mantenha os olhos visiveis", (18, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


def rotation_matrix_yaw_pitch(yaw: float, pitch: float) -> np.ndarray:
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    rot_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    rot_x = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=np.float32)
    return rot_x @ rot_y


def project_point(point: np.ndarray, cam_pos: np.ndarray, yaw: float, pitch: float, focal: float, width: int, height: int) -> Optional[Tuple[int, int, float]]:
    rel = point - cam_pos
    rot = rotation_matrix_yaw_pitch(yaw, pitch)
    cam = rot @ rel
    z = float(cam[2])
    if z <= 0.10:
        return None
    x2d = int(width / 2 + focal * (cam[0] / z))
    y2d = int(height / 2 - focal * (cam[1] / z))
    return x2d, y2d, z


def polygon_from_3d(corners: List[np.ndarray], cam_pos: np.ndarray, yaw: float, pitch: float, focal: float, width: int, height: int) -> Optional[np.ndarray]:
    pts = []
    for c in corners:
        p = project_point(c, cam_pos, yaw, pitch, focal, width, height)
        if p is None:
            return None
        pts.append([p[0], p[1]])
    return np.array(pts, dtype=np.int32)


def painting_corners(meta: dict) -> List[np.ndarray]:
    cx, cy, cz = meta["center"]
    pw, ph = meta["size"]
    hw = pw / 2.0
    hh = ph / 2.0

    if meta["wall"] == "left":
        return [
            np.array([cx, cy + hh, cz - hw], dtype=np.float32),
            np.array([cx, cy + hh, cz + hw], dtype=np.float32),
            np.array([cx, cy - hh, cz + hw], dtype=np.float32),
            np.array([cx, cy - hh, cz - hw], dtype=np.float32),
        ]
    if meta["wall"] == "right":
        return [
            np.array([cx, cy + hh, cz + hw], dtype=np.float32),
            np.array([cx, cy + hh, cz - hw], dtype=np.float32),
            np.array([cx, cy - hh, cz - hw], dtype=np.float32),
            np.array([cx, cy - hh, cz + hw], dtype=np.float32),
        ]
    return [
        np.array([cx - hw, cy + hh, cz], dtype=np.float32),
        np.array([cx + hw, cy + hh, cz], dtype=np.float32),
        np.array([cx + hw, cy - hh, cz], dtype=np.float32),
        np.array([cx - hw, cy - hh, cz], dtype=np.float32),
    ]


def paste_texture_on_quad(canvas: np.ndarray, texture: np.ndarray, quad: np.ndarray):
    if quad is None or len(quad) != 4:
        return
    h, w = texture.shape[:2]
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    dst = quad.astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(texture, M, (canvas.shape[1], canvas.shape[0]))
    mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    mask3 = cv2.merge([mask, mask, mask])
    np.copyto(canvas, np.where(mask3 > 0, warped, canvas))


def draw_room_background(canvas: np.ndarray, cam_pos: np.ndarray, yaw: float, pitch: float, focal: float):
    w = canvas.shape[1]
    h = canvas.shape[0]

    world = {
        "floor": [np.array([-4, 0, 0]), np.array([4, 0, 0]), np.array([4, 0, 10]), np.array([-4, 0, 10])],
        "ceiling": [np.array([-4, 3.3, 0]), np.array([4, 3.3, 0]), np.array([4, 3.3, 10]), np.array([-4, 3.3, 10])],
        "left": [np.array([-4, 0, 0]), np.array([-4, 3.3, 0]), np.array([-4, 3.3, 10]), np.array([-4, 0, 10])],
        "right": [np.array([4, 0, 0]), np.array([4, 3.3, 0]), np.array([4, 3.3, 10]), np.array([4, 0, 10])],
        "front": [np.array([-4, 0, 10]), np.array([4, 0, 10]), np.array([4, 3.3, 10]), np.array([-4, 3.3, 10])],
    }

    colors = {
        "floor": (70, 42, 18),
        "ceiling": (45, 45, 55),
        "left": (58, 60, 78),
        "right": (58, 60, 78),
        "front": (76, 78, 92),
    }

    order = ["ceiling", "front", "left", "right", "floor"]
    for key in order:
        poly = polygon_from_3d(world[key], cam_pos, yaw, pitch, focal, w, h)
        if poly is not None:
            cv2.fillConvexPoly(canvas, poly, colors[key])
            cv2.polylines(canvas, [poly], True, (120, 120, 138), 2, cv2.LINE_AA)

    for z in np.linspace(1.0, 9.6, 9):
        left = project_point(np.array([-4, 0.02, z]), cam_pos, yaw, pitch, focal, w, h)
        right = project_point(np.array([4, 0.02, z]), cam_pos, yaw, pitch, focal, w, h)
        if left and right:
            cv2.line(canvas, (left[0], left[1]), (right[0], right[1]), (95, 72, 42), 2, cv2.LINE_AA)

    for x in np.linspace(-3.5, 3.5, 8):
        near = project_point(np.array([x, 0.02, 0.25]), cam_pos, yaw, pitch, focal, w, h)
        far = project_point(np.array([x, 0.02, 9.8]), cam_pos, yaw, pitch, focal, w, h)
        if near and far:
            cv2.line(canvas, (near[0], near[1]), (far[0], far[1]), (90, 64, 34), 1, cv2.LINE_AA)

    # luminárias
    for z in [2.0, 5.2, 8.3]:
        p1 = polygon_from_3d(
            [
                np.array([-0.6, 3.18, z - 0.16]),
                np.array([0.6, 3.18, z - 0.16]),
                np.array([0.6, 3.18, z + 0.16]),
                np.array([-0.6, 3.18, z + 0.16]),
            ],
            cam_pos,
            yaw,
            pitch,
            focal,
            w,
            h,
        )
        if p1 is not None:
            cv2.fillConvexPoly(canvas, p1, (210, 210, 180))
            cv2.polylines(canvas, [p1], True, (250, 250, 235), 1, cv2.LINE_AA)

    overlay = canvas.copy()
    for radius, alpha in [(180, 0.05), (260, 0.04), (360, 0.03)]:
        cv2.circle(overlay, (w // 2, 70), radius, (255, 250, 220), -1)
        canvas[:] = cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0)


def scene_cursor_from_gaze(gaze_norm: Tuple[float, float]) -> Tuple[int, int]:
    x = int(clamp(gaze_norm[0], 0.0, 1.0) * (SCENE_W - 1))
    y = int(clamp(gaze_norm[1], 0.0, 1.0) * (SCENE_H - 1))
    return x, y


def update_focus_state(active_id: Optional[str]):
    ts = now_ts()
    with STATE.lock:
        previous = STATE.active_painting_id
        if previous == active_id:
            if active_id and STATE.focus_started_at is None:
                STATE.focus_started_at = ts
        else:
            if previous and STATE.focus_started_at is not None:
                STATE.focus_seconds_by_painting[previous] = STATE.focus_seconds_by_painting.get(previous, 0.0) + (ts - STATE.focus_started_at)
            STATE.active_painting_id = active_id
            STATE.focus_started_at = ts if active_id else None

        if active_id:
            meta = next((p for p in PAINTINGS if p["id"] == active_id), None)
            if meta:
                dwell = ts - (STATE.focus_started_at or ts)
                STATE.last_info_title = meta["title"]
                if dwell >= 0.55:
                    STATE.last_info_body = (
                        f"{meta['artist']} ({meta['year']}) — {meta['summary']}\n\n"
                        + "\n".join(meta["details"])
                    )
                else:
                    STATE.last_info_body = "Fixe o olhar por ~0,6 s para abrir a ficha rápida do quadro."
        else:
            STATE.last_info_title = "Nenhum quadro selecionado"
            STATE.last_info_body = "Olhe para um quadro por alguns instantes para abrir a ficha rápida."


def render_scene() -> np.ndarray:
    with STATE.lock:
        gaze_norm = STATE.gaze_norm
        zoom = STATE.zoom_level
        face_ok = STATE.face_detected

    canvas = np.zeros((SCENE_H, SCENE_W, 3), dtype=np.uint8)
    canvas[:] = (16, 16, 22)

    yaw = (gaze_norm[0] - 0.5) * 0.22
    pitch = -(gaze_norm[1] - 0.5) * 0.12
    cam_pos = np.array([(gaze_norm[0] - 0.5) * 0.75, 1.58 + (0.5 - gaze_norm[1]) * 0.15, -2.35], dtype=np.float32)
    focal = 860.0 * zoom

    draw_room_background(canvas, cam_pos, yaw, pitch, focal)

    # suportes / molduras
    cursor = scene_cursor_from_gaze(gaze_norm)
    selected_id = None
    selected_dwell_ready = False

    projected = []
    for meta in PAINTINGS:
        corners = painting_corners(meta)
        quad = polygon_from_3d(corners, cam_pos, yaw, pitch, focal, SCENE_W, SCENE_H)
        if quad is None:
            continue
        depth_est = float(np.mean([project_point(c, cam_pos, yaw, pitch, focal, SCENE_W, SCENE_H)[2] for c in corners if project_point(c, cam_pos, yaw, pitch, focal, SCENE_W, SCENE_H) is not None]))
        projected.append((depth_est, meta, quad))

    projected.sort(key=lambda x: x[0], reverse=True)

    for _, meta, quad in projected:
        shadow = quad + np.array([8, 8], dtype=np.int32)
        cv2.fillConvexPoly(canvas, shadow, (15, 15, 15))
        frame_poly = quad.copy()
        cv2.fillConvexPoly(canvas, frame_poly, (30, 28, 24))
        inner = frame_poly.astype(np.float32)
        center = np.mean(inner, axis=0)
        inner = (center + (inner - center) * 0.90).astype(np.int32)
        paste_texture_on_quad(canvas, TEXTURES[meta["id"]], inner)
        cv2.polylines(canvas, [frame_poly], True, (210, 180, 120), 5, cv2.LINE_AA)
        cv2.polylines(canvas, [frame_poly], True, (245, 232, 188), 1, cv2.LINE_AA)

        if cv2.pointPolygonTest(frame_poly, cursor, False) >= 0:
            selected_id = meta["id"]

    update_focus_state(selected_id)

    with STATE.lock:
        active_id = STATE.active_painting_id
        active_since = STATE.focus_started_at
    if active_id and active_since:
        selected_dwell_ready = (now_ts() - active_since) >= 0.55

    for _, meta, quad in projected:
        if meta["id"] == selected_id:
            color = (40, 255, 210) if selected_dwell_ready else (50, 200, 255)
            cv2.polylines(canvas, [quad], True, color, 6, cv2.LINE_AA)
            label_pos = tuple(np.mean(quad, axis=0).astype(int))
            cv2.putText(canvas, meta["title"], (label_pos[0] - 85, label_pos[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(canvas, meta["title"], (label_pos[0] - 85, label_pos[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.78, color, 2, cv2.LINE_AA)

    if face_ok:
        cx, cy = cursor
        cv2.circle(canvas, (cx, cy), 18, (40, 245, 180), 2, cv2.LINE_AA)
        cv2.line(canvas, (cx - 12, cy), (cx + 12, cy), (40, 245, 180), 1, cv2.LINE_AA)
        cv2.line(canvas, (cx, cy - 12), (cx, cy + 12), (40, 245, 180), 1, cv2.LINE_AA)
    else:
        cv2.putText(canvas, "Sem rastreio ocular no momento", (36, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (40, 100, 255), 2, cv2.LINE_AA)

    panel = canvas.copy()
    cv2.rectangle(panel, (24, 24), (500, 184), (10, 10, 14), -1)
    canvas = cv2.addWeighted(panel, 0.38, canvas, 0.62, 0)
    cv2.rectangle(canvas, (24, 24), (500, 184), (200, 200, 200), 1)
    cv2.putText(canvas, "Galeria ocular 3D", (42, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.putText(canvas, "Olhe para um quadro para abrir informacoes", (42, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (210, 210, 210), 1, cv2.LINE_AA)
    cv2.putText(canvas, "2 piscadas = zoom | 1 piscada = afastar", (42, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (210, 210, 210), 1, cv2.LINE_AA)

    with STATE.lock:
        canvas_info_title = STATE.last_info_title
        zoom = STATE.zoom_level
        canvas_debug = STATE.debug_text
        STATE.last_rendered_scene = canvas.copy()
        STATE.last_scene_cursor = cursor

    cv2.putText(canvas, f"Selecionado: {canvas_info_title}", (42, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (100, 255, 220), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Zoom: {zoom:.2f}x", (42, 176), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (250, 220, 120), 1, cv2.LINE_AA)
    cv2.putText(canvas, canvas_debug[:70], (24, SCENE_H - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 210, 210), 1, cv2.LINE_AA)
    return canvas


def build_heatmap_overlay(scene: np.ndarray, gaze_samples: List[Tuple[float, float, float]]) -> np.ndarray:
    if scene is None:
        scene = np.zeros((SCENE_H, SCENE_W, 3), dtype=np.uint8)

    heat = np.zeros((SCENE_H, SCENE_W), dtype=np.float32)
    for _, gx, gy in gaze_samples:
        x = int(clamp(gx, 0.0, 1.0) * (SCENE_W - 1))
        y = int(clamp(gy, 0.0, 1.0) * (SCENE_H - 1))
        heat[y, x] += 1.0

    if np.max(heat) > 0:
        heat = cv2.GaussianBlur(heat, (0, 0), sigmaX=35, sigmaY=35)
        heat_norm = cv2.normalize(heat, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        heat_color = cv2.applyColorMap(heat_norm, cv2.COLORMAP_JET)
        overlay = cv2.addWeighted(scene, 0.55, heat_color, 0.45, 0)
        overlay[heat_norm < 10] = scene[heat_norm < 10]
        return overlay
    return scene.copy()


def build_report_pdf() -> bytes:
    with STATE.lock:
        scene = None if STATE.last_rendered_scene is None else STATE.last_rendered_scene.copy()
        gaze_samples = list(STATE.gaze_samples_norm)
        focus = dict(STATE.focus_seconds_by_painting)
        active = STATE.active_painting_id
        active_since = STATE.focus_started_at
        blink_total = STATE.blink_count_total
        zoom_events = list(STATE.zoom_events)
        session_started = STATE.session_started_at

    if active and active_since is not None:
        focus[active] = focus.get(active, 0.0) + (now_ts() - active_since)

    if scene is None:
        scene = render_scene()

    heatmap = build_heatmap_overlay(scene, gaze_samples)
    total_duration = max(1.0, now_ts() - session_started)

    label_map = {p["id"]: p["title"] for p in PAINTINGS}
    labels = [label_map[k] for k, _ in sorted(focus.items(), key=lambda kv: kv[1], reverse=True)]
    values = [v for _, v in sorted(focus.items(), key=lambda kv: kv[1], reverse=True)]

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle("Relatório de mapa de calor ocular — Galeria 3D", fontsize=18, fontweight="bold")
        ax = fig.add_subplot(121)
        ax.imshow(cv2.cvtColor(scene, cv2.COLOR_BGR2RGB))
        ax.set_title("Cena final")
        ax.axis("off")

        ax2 = fig.add_subplot(122)
        ax2.imshow(cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB))
        ax2.set_title("Mapa de calor do olhar")
        ax2.axis("off")

        fig.text(0.08, 0.08, f"Duração da sessão: {total_duration:.1f} s")
        fig.text(0.08, 0.05, f"Amostras de olhar: {len(gaze_samples)}")
        fig.text(0.36, 0.08, f"Piscadas detectadas: {blink_total}")
        fig.text(0.36, 0.05, f"Eventos de zoom: {len(zoom_events)}")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig = plt.figure(figsize=(11.69, 8.27))
        gs = fig.add_gridspec(2, 2)
        ax_bar = fig.add_subplot(gs[:, 0])
        ax_txt = fig.add_subplot(gs[0, 1])
        ax_events = fig.add_subplot(gs[1, 1])

        if labels:
            ax_bar.barh(labels[::-1], values[::-1])
            ax_bar.set_title("Tempo de foco por quadro (s)")
            ax_bar.set_xlabel("Segundos")
        else:
            ax_bar.text(0.5, 0.5, "Sem dados suficientes", ha="center", va="center")
            ax_bar.set_axis_off()

        ax_txt.axis("off")
        lines = [
            "Resumo automático:",
            f"- sessão total: {total_duration:.1f} s",
            f"- gaze samples: {len(gaze_samples)}",
            f"- piscadas: {blink_total}",
            f"- zoom events: {len(zoom_events)}",
            "",
            "Quadros analisados:",
        ]
        for p in PAINTINGS:
            sec = focus.get(p["id"], 0.0)
            lines.append(f"- {p['title']}: {sec:.1f} s")
        ax_txt.text(0.0, 1.0, "\n".join(lines), va="top", fontsize=11)

        ax_events.axis("off")
        if zoom_events:
            ev_lines = ["Eventos de zoom:"]
            base = session_started
            for ts, kind, level in zoom_events[-12:]:
                ev_lines.append(f"- {ts - base:6.1f}s | {kind} | nível {level:.2f}x")
        else:
            ev_lines = ["Eventos de zoom:", "- nenhum evento registrado"]
        ax_events.text(0.0, 1.0, "\n".join(ev_lines), va="top", fontsize=11)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    buf.seek(0)
    return buf.getvalue()


def reset_session():
    global STATE
    with STATE.lock:
        STATE.gaze_norm = (0.5, 0.5)
        STATE.face_detected = False
        STATE.blink_count_total = 0
        STATE.zoom_level = 1.0
        STATE.active_painting_id = None
        STATE.focus_started_at = None
        STATE.focus_seconds_by_painting = {}
        STATE.blink_timestamps = []
        STATE.pending_single_blink_ts = None
        STATE.zoom_events = []
        STATE.eye_contact_samples = 0
        STATE.gaze_samples_norm = []
        STATE.session_started_at = now_ts()
        STATE.last_info_title = "Nenhum quadro selecionado"
        STATE.last_info_body = "Olhe para um quadro por alguns instantes para abrir a ficha rápida."
        STATE.current_blink_ratio = 0.0
        STATE.last_rendered_scene = None
        STATE.last_scene_cursor = (SCENE_W // 2, SCENE_H // 2)
        STATE.debug_text = "Sessão reiniciada"


def set_center_calibration():
    with STATE.lock:
        gx, gy = STATE.gaze_norm
        STATE.calibration_offset = (0.5 - gx, 0.5 - gy)
        STATE.debug_text = f"Calibrado para centro: offset=({STATE.calibration_offset[0]:.3f}, {STATE.calibration_offset[1]:.3f})"


def clear_calibration():
    with STATE.lock:
        STATE.calibration_offset = (0.0, 0.0)
        STATE.debug_text = "Calibração zerada"


def app_sidebar():
    st.sidebar.title("Controles")
    st.sidebar.markdown("Use webcam, mantenha o rosto centralizado e os olhos visíveis.")

    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("Calibrar centro", use_container_width=True):
        set_center_calibration()
    if col_b.button("Zerar calib.", use_container_width=True):
        clear_calibration()

    if st.sidebar.button("Reiniciar sessão", use_container_width=True):
        reset_session()

    with STATE.lock:
        blink_total = STATE.blink_count_total
        zoom_level = STATE.zoom_level
        gaze = STATE.gaze_norm
        blink_ratio = STATE.current_blink_ratio
        debug_text = STATE.debug_text

    st.sidebar.metric("Zoom", f"{zoom_level:.2f}x")
    st.sidebar.metric("Piscadas", blink_total)
    st.sidebar.metric("Gaze X", f"{gaze[0]:.2f}")
    st.sidebar.metric("Gaze Y", f"{gaze[1]:.2f}")
    st.sidebar.caption(f"Blink ratio atual: {blink_ratio:.3f}")
    st.sidebar.code(debug_text)

    st.sidebar.markdown("### Gestos")
    st.sidebar.markdown("- **2 piscadas rápidas**: aproxima\n- **1 piscada isolada**: afasta\n- **olhar fixo ~0,6s**: abre informações do quadro")


reset_session_once = st.session_state.get("reset_session_once")
if reset_session_once is None:
    reset_session()
    st.session_state["reset_session_once"] = True

app_sidebar()

st.title("👁️ Simulacro — Galeria 3D controlada pelo olhar")
st.caption("Versão adaptada para Streamlit: sem tkinter, sem janelas OpenCV locais e pronta para rodar em repositório hospedado.")

st_autorefresh(interval=350, key="gallery_refresh")

left_col, right_col = st.columns([1.05, 1.25], gap="large")

with left_col:
    st.subheader("Câmera / rastreamento ocular")
    webrtc_streamer(
        key="eye-gallery-webrtc",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=EyeTrackerProcessor,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )
    st.info("Para melhor resultado, use boa iluminação e mantenha a webcam na altura dos olhos.")

with right_col:
    st.subheader("Sala 3D")
    scene = render_scene()
    st.image(scene, channels="BGR", use_container_width=True)

    with STATE.lock:
        title = STATE.last_info_title
        body = STATE.last_info_body
        focus = dict(STATE.focus_seconds_by_painting)
        active = STATE.active_painting_id
        since = STATE.focus_started_at

    if active and since is not None:
        focus[active] = focus.get(active, 0.0) + (now_ts() - since)

    st.markdown(f"### {title}")
    st.write(body)

    if focus:
        ranking = sorted(focus.items(), key=lambda kv: kv[1], reverse=True)
        human = []
        label_map = {p["id"]: p["title"] for p in PAINTINGS}
        for pid, sec in ranking:
            human.append(f"**{label_map.get(pid, pid)}** — {sec:.1f} s")
        st.markdown("**Tempo de foco acumulado:**  "+" | ".join(human[:5]))

st.divider()

report_col1, report_col2, report_col3 = st.columns([1, 1, 1.2])
with report_col1:
    if st.button("Gerar prévia do mapa de calor", use_container_width=True):
        with STATE.lock:
            last_scene = None if STATE.last_rendered_scene is None else STATE.last_rendered_scene.copy()
            gaze_samples = list(STATE.gaze_samples_norm)
        preview = build_heatmap_overlay(last_scene if last_scene is not None else scene, gaze_samples)
        st.session_state["heat_preview"] = preview

with report_col2:
    pdf_bytes = build_report_pdf()
    st.download_button(
        "Baixar relatório PDF",
        data=pdf_bytes,
        file_name="relatorio_mapa_calor_galeria_3d.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

with report_col3:
    st.markdown("O relatório PDF inclui a cena final, o mapa de calor, resumo da sessão, tempo de foco por quadro e eventos de zoom.")

preview = st.session_state.get("heat_preview")
if preview is not None:
    st.subheader("Prévia do mapa de calor")
    st.image(preview, channels="BGR", use_container_width=True)

st.markdown("---")
st.markdown(
    "**Observação importante:** esta versão foi adaptada para webcam comum em Streamlit. "
    "Para precisão igual à da foto com elipse verde sobre a pupila, o ideal é usar câmera ocular dedicada/IR e um app nativo em OpenCV."
)
