import io
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import av
import cv2
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
try:
    from mediapipe.python.solutions import face_mesh as mp_face_mesh
except Exception:
    mp_face_mesh = None
import numpy as np
import streamlit as st
from streamlit_webrtc import RTCConfiguration, VideoProcessorBase, WebRtcMode, webrtc_streamer


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Galeria controlada pela íris",
    layout="wide",
    initial_sidebar_state="expanded",
)

if mp_face_mesh is None:
    st.error("Não foi possível carregar o MediaPipe Face Mesh. Use o requirements.txt enviado e Python compatível.")
    st.stop()


# ============================================================
# DADOS DA GALERIA
# ============================================================
PAINTINGS: List[Dict] = [
    {
        "id": "quadro_1",
        "title": "Mãe da Maré",
        "artist": "Acervo demonstrativo",
        "year": "2026",
        "description": "Quadro da parede esquerda. O foco da seleção é feito apenas pelo olhar e confirmado por tempo de fixação.",
        "box": (0.10, 0.24, 0.31, 0.66),
    },
    {
        "id": "quadro_2",
        "title": "Centro da Memória",
        "artist": "Acervo demonstrativo",
        "year": "2026",
        "description": "Quadro central. Quando o ponto de gaze permanece nele por alguns instantes, ele vira o quadro ativo.",
        "box": (0.39, 0.18, 0.61, 0.72),
    },
    {
        "id": "quadro_3",
        "title": "Rastro de Ancestralidade",
        "artist": "Acervo demonstrativo",
        "year": "2026",
        "description": "Quadro da parede direita. A navegação usa centros oculares, centros das íris, projeção de raios e calibração multiponto.",
        "box": (0.69, 0.24, 0.90, 0.66),
    },
]

CALIBRATION_TARGETS: List[Tuple[float, float]] = [
    (0.10, 0.10),
    (0.90, 0.10),
    (0.50, 0.50),
    (0.10, 0.90),
    (0.90, 0.90),
]

RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)


# ============================================================
# ESTRUTURAS DE ESTADO COMPARTILHADO
# ============================================================
@dataclass
class SelectionEvent:
    timestamp: float
    painting_id: str
    title: str


@dataclass
class SharedTrackerState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    latest_gaze_norm: Tuple[float, float] = (0.5, 0.5)
    latest_raw_point: Optional[np.ndarray] = None
    latest_left_eye_center: Optional[Tuple[float, float]] = None
    latest_right_eye_center: Optional[Tuple[float, float]] = None
    latest_left_iris_center: Optional[Tuple[float, float]] = None
    latest_right_iris_center: Optional[Tuple[float, float]] = None
    latest_face_ok: bool = False
    latest_status: str = "Aguardando vídeo"
    calibration_samples: List[Tuple[np.ndarray, Tuple[float, float]]] = field(default_factory=list)
    calibration_matrix: Optional[np.ndarray] = None
    current_target_index: int = 0
    gaze_history: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=9000))
    raw_history: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=9000))
    hover_painting_id: Optional[str] = None
    hover_started_at: Optional[float] = None
    selected_painting_id: Optional[str] = None
    selection_events: List[SelectionEvent] = field(default_factory=list)
    zoom_level: float = 1.0
    blink_closed: bool = False
    blink_closed_at: float = 0.0
    pending_single_blink_at: Optional[float] = None
    blink_message: str = "Sem piscadas detectadas"

    def reset_tracking(self) -> None:
        with self.lock:
            self.latest_gaze_norm = (0.5, 0.5)
            self.latest_raw_point = None
            self.latest_left_eye_center = None
            self.latest_right_eye_center = None
            self.latest_left_iris_center = None
            self.latest_right_iris_center = None
            self.latest_face_ok = False
            self.latest_status = "Aguardando vídeo"
            self.gaze_history.clear()
            self.raw_history.clear()
            self.hover_painting_id = None
            self.hover_started_at = None
            self.selected_painting_id = None
            self.selection_events = []
            self.zoom_level = 1.0
            self.blink_closed = False
            self.blink_closed_at = 0.0
            self.pending_single_blink_at = None
            self.blink_message = "Sem piscadas detectadas"

    def reset_calibration(self) -> None:
        with self.lock:
            self.calibration_samples = []
            self.calibration_matrix = None
            self.current_target_index = 0


# ============================================================
# UTILITÁRIOS DE GEOMETRIA E LANDMARKS
# ============================================================
LEFT_EYE_CORNERS = (33, 133)
RIGHT_EYE_CORNERS = (362, 263)
LEFT_EYE_LIDS = (159, 145)
RIGHT_EYE_LIDS = (386, 374)
LEFT_IRIS = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def mean_point(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    arr = np.array(points, dtype=np.float32)
    return float(np.mean(arr[:, 0])), float(np.mean(arr[:, 1]))


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def eye_aspect_ratio(
    upper: Tuple[float, float],
    lower: Tuple[float, float],
    outer: Tuple[float, float],
    inner: Tuple[float, float],
) -> float:
    horizontal = max(dist(outer, inner), 1e-6)
    vertical = dist(upper, lower)
    return vertical / horizontal


def get_landmark_xy(landmarks, idx: int, width: int, height: int) -> Tuple[float, float]:
    lm = landmarks[idx]
    return lm.x * width, lm.y * height


def fit_calibration_matrix(samples: List[Tuple[np.ndarray, Tuple[float, float]]]) -> Optional[np.ndarray]:
    if len(samples) < 3:
        return None

    x_rows = []
    y_rows = []
    for raw_feat, target in samples:
        x_rows.append([float(raw_feat[0]), float(raw_feat[1]), 1.0])
        y_rows.append([float(target[0]), float(target[1])])

    x_mat = np.array(x_rows, dtype=np.float32)
    y_mat = np.array(y_rows, dtype=np.float32)
    try:
        w, _, _, _ = np.linalg.lstsq(x_mat, y_mat, rcond=None)
        return w
    except np.linalg.LinAlgError:
        return None


def apply_calibration(raw_point: np.ndarray, calibration_matrix: Optional[np.ndarray]) -> Tuple[float, float]:
    if calibration_matrix is None:
        # fallback bruto: normalização simples do espaço do olho para tela
        gx = 0.5 + raw_point[0] * 0.9
        gy = 0.5 - raw_point[1] * 0.9
        return clamp(gx, 0.0, 1.0), clamp(gy, 0.0, 1.0)

    vec = np.array([float(raw_point[0]), float(raw_point[1]), 1.0], dtype=np.float32)
    pred = vec @ calibration_matrix
    return clamp(float(pred[0]), 0.0, 1.0), clamp(float(pred[1]), 0.0, 1.0)


def ray_intersection_on_plane(
    origin_xy: Tuple[float, float],
    iris_offset_xy: Tuple[float, float],
    plane_z: float = 1.2,
    gain: float = 1.35,
) -> np.ndarray:
    # origem no "espaço do olho"
    origin = np.array([origin_xy[0], origin_xy[1], 0.0], dtype=np.float32)
    direction = np.array(
        [iris_offset_xy[0] * gain, -iris_offset_xy[1] * gain, 1.0],
        dtype=np.float32,
    )
    direction /= max(np.linalg.norm(direction), 1e-6)
    t = plane_z / max(direction[2], 1e-6)
    point = origin + direction * t
    return point[:2]


def point_inside_box(point: Tuple[float, float], box: Tuple[float, float, float, float]) -> bool:
    x, y = point
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def painting_by_id(pid: Optional[str]) -> Optional[Dict]:
    if pid is None:
        return None
    for painting in PAINTINGS:
        if painting["id"] == pid:
            return painting
    return None


# ============================================================
# GERAÇÃO DO PDF
# ============================================================
def build_pdf_report(state: SharedTrackerState) -> bytes:
    with state.lock:
        gaze_points = list(state.gaze_history)
        selected = state.selected_painting_id
        zoom_level = state.zoom_level
        blink_message = state.blink_message
        selection_events = list(state.selection_events)
        calibration_ready = state.calibration_matrix is not None
        sample_count = len(state.calibration_samples)

    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_subplot(111)
        ax.axis("off")
        selected_p = painting_by_id(selected)
        selected_text = selected_p["title"] if selected_p else "Nenhum quadro selecionado"

        lines = [
            "Relatório de navegação por íris",
            "",
            f"Calibração pronta: {'sim' if calibration_ready else 'não'}",
            f"Pontos de calibração capturados: {sample_count}",
            f"Quadro selecionado: {selected_text}",
            f"Zoom atual: {zoom_level:.2f}x",
            f"Último evento de piscada: {blink_message}",
            f"Total de pontos de gaze gravados: {len(gaze_points)}",
            f"Total de seleções registradas: {len(selection_events)}",
            "",
            "Seleções registradas:",
        ]

        if selection_events:
            for event in selection_events[-12:]:
                hhmmss = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
                lines.append(f"- {hhmmss}: {event.title}")
        else:
            lines.append("- Nenhuma seleção até o momento")

        ax.text(0.05, 0.97, "\n".join(lines), va="top", ha="left", fontsize=12)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig2, ax2 = plt.subplots(figsize=(11, 6))
        ax2.set_title("Mapa de calor do olhar na parede virtual")
        ax2.set_xlim(0, 1)
        ax2.set_ylim(1, 0)
        ax2.set_xlabel("Tela virtual X")
        ax2.set_ylabel("Tela virtual Y")
        ax2.set_facecolor("#f4f1ea")

        for painting in PAINTINGS:
            x1, y1, x2, y2 = painting["box"]
            rect = plt.Rectangle(
                (x1, y1),
                x2 - x1,
                y2 - y1,
                fill=False,
                linewidth=2.0,
            )
            ax2.add_patch(rect)
            ax2.text((x1 + x2) / 2, y1 - 0.03, painting["title"], ha="center", va="bottom", fontsize=9)

        if gaze_points:
            xs = np.array([p[0] for p in gaze_points], dtype=np.float32)
            ys = np.array([p[1] for p in gaze_points], dtype=np.float32)
            heat, _, _ = np.histogram2d(xs, ys, bins=[40, 25], range=[[0, 1], [0, 1]])
            ax2.imshow(
                heat.T,
                origin="lower",
                extent=[0, 1, 0, 1],
                aspect="auto",
                alpha=0.65,
                cmap="inferno",
            )
            ax2.scatter(xs[-1:], ys[-1:], s=100, marker="x")

        pdf.savefig(fig2, bbox_inches="tight")
        plt.close(fig2)

    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# PROCESSADOR DE VÍDEO
# ============================================================
class IrisGalleryProcessor(VideoProcessorBase):
    shared_state: SharedTrackerState = None

    def __init__(self) -> None:
        self.state = self.__class__.shared_state
        if mp_face_mesh is None:
            raise RuntimeError("MediaPipe Face Mesh não pôde ser importado. Verifique o requirements.txt e a versão do Python.")
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.last_frame_ts = time.time()

    def _process_blinks(self, ear: float, now_ts: float) -> None:
        close_threshold = 0.17
        open_threshold = 0.21
        min_blink_duration = 0.05
        max_blink_duration = 0.45
        double_window = 0.55

        with self.state.lock:
            if self.state.pending_single_blink_at is not None:
                if now_ts - self.state.pending_single_blink_at > double_window:
                    self.state.zoom_level = max(0.70, self.state.zoom_level - 0.12)
                    self.state.blink_message = f"Piscada simples → afastou para {self.state.zoom_level:.2f}x"
                    self.state.pending_single_blink_at = None

            if ear < close_threshold and not self.state.blink_closed:
                self.state.blink_closed = True
                self.state.blink_closed_at = now_ts

            elif ear > open_threshold and self.state.blink_closed:
                duration = now_ts - self.state.blink_closed_at
                self.state.blink_closed = False

                if min_blink_duration <= duration <= max_blink_duration:
                    if (
                        self.state.pending_single_blink_at is not None
                        and (now_ts - self.state.pending_single_blink_at) <= double_window
                    ):
                        self.state.zoom_level = min(2.30, self.state.zoom_level + 0.25)
                        self.state.blink_message = f"Piscada dupla → aproximou para {self.state.zoom_level:.2f}x"
                        self.state.pending_single_blink_at = None
                    else:
                        self.state.pending_single_blink_at = now_ts

    def _update_selection(self, gaze_norm: Tuple[float, float], now_ts: float) -> None:
        hovered = None
        for painting in PAINTINGS:
            if point_inside_box(gaze_norm, painting["box"]):
                hovered = painting["id"]
                break

        with self.state.lock:
            if hovered != self.state.hover_painting_id:
                self.state.hover_painting_id = hovered
                self.state.hover_started_at = now_ts if hovered is not None else None
            elif hovered is not None and self.state.hover_started_at is not None:
                if now_ts - self.state.hover_started_at >= 0.80:
                    if self.state.selected_painting_id != hovered:
                        self.state.selected_painting_id = hovered
                        p = painting_by_id(hovered)
                        if p is not None:
                            self.state.selection_events.append(
                                SelectionEvent(timestamp=now_ts, painting_id=hovered, title=p["title"])
                            )

    def _draw_virtual_gallery(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]

        # parede simulada
        wall_color = (210, 220, 235)
        floor_color = (120, 105, 90)
        cv2.rectangle(image, (0, 0), (w, int(h * 0.78)), wall_color, -1)
        cv2.rectangle(image, (0, int(h * 0.78)), (w, h), floor_color, -1)

        with self.state.lock:
            gaze = self.state.latest_gaze_norm
            selected_id = self.state.selected_painting_id
            hover_id = self.state.hover_painting_id
            zoom_level = self.state.zoom_level
            cal_ready = self.state.calibration_matrix is not None
            target_index = self.state.current_target_index
            blink_msg = self.state.blink_message
            status = self.state.latest_status

        for painting in PAINTINGS:
            x1, y1, x2, y2 = painting["box"]
            pt1 = (int(x1 * w), int(y1 * h))
            pt2 = (int(x2 * w), int(y2 * h))

            frame_color = (50, 65, 120)
            inside_color = (240, 235, 210)
            thickness = 3

            if painting["id"] == selected_id:
                frame_color = (40, 170, 60)
                thickness = 5
            elif painting["id"] == hover_id:
                frame_color = (10, 180, 220)
                thickness = 4

            cv2.rectangle(image, pt1, pt2, frame_color, thickness)
            cv2.rectangle(
                image,
                (pt1[0] + 8, pt1[1] + 8),
                (pt2[0] - 8, pt2[1] - 8),
                inside_color,
                -1,
            )
            cv2.putText(
                image,
                painting["title"],
                (pt1[0] + 10, pt1[1] + 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (30, 30, 30),
                2,
                cv2.LINE_AA,
            )

        # alvo de calibração
        if not cal_ready and target_index < len(CALIBRATION_TARGETS):
            tx, ty = CALIBRATION_TARGETS[target_index]
            cx = int(tx * w)
            cy = int(ty * h)
            cv2.circle(image, (cx, cy), 16, (0, 0, 255), 2)
            cv2.line(image, (cx - 22, cy), (cx + 22, cy), (0, 0, 255), 2)
            cv2.line(image, (cx, cy - 22), (cx, cy + 22), (0, 0, 255), 2)
            cv2.putText(
                image,
                f"Olhe para o alvo {target_index + 1}/{len(CALIBRATION_TARGETS)} e capture na barra lateral",
                (16, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (0, 0, 180),
                2,
                cv2.LINE_AA,
            )

        gx = int(gaze[0] * w)
        gy = int(gaze[1] * h)
        cv2.circle(image, (gx, gy), 10, (0, 0, 255), -1)
        cv2.circle(image, (gx, gy), 22, (255, 255, 255), 2)

        selected = painting_by_id(selected_id)
        if selected is not None:
            panel_y1 = int(h * 0.80)
            panel_y2 = h - 12
            cv2.rectangle(image, (12, panel_y1), (w - 12, panel_y2), (18, 18, 18), -1)
            cv2.putText(
                image,
                f"Quadro ativo: {selected['title']} | {selected['artist']} | zoom {zoom_level:.2f}x",
                (24, panel_y1 + 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (230, 230, 230),
                2,
                cv2.LINE_AA,
            )
            desc = selected["description"][:95]
            cv2.putText(
                image,
                desc,
                (24, panel_y1 + 68),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.54,
                (180, 220, 255),
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            image,
            status,
            (16, h - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            blink_msg,
            (16, h - 44),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return image

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        image = frame.to_ndarray(format="bgr24")
        image = cv2.flip(image, 1)
        overlay = image.copy()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        now_ts = time.time()

        face_ok = False
        status_msg = "Rosto não detectado"

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            h, w = image.shape[:2]

            left_outer = get_landmark_xy(landmarks, LEFT_EYE_CORNERS[0], w, h)
            left_inner = get_landmark_xy(landmarks, LEFT_EYE_CORNERS[1], w, h)
            right_outer = get_landmark_xy(landmarks, RIGHT_EYE_CORNERS[0], w, h)
            right_inner = get_landmark_xy(landmarks, RIGHT_EYE_CORNERS[1], w, h)
            left_upper = get_landmark_xy(landmarks, LEFT_EYE_LIDS[0], w, h)
            left_lower = get_landmark_xy(landmarks, LEFT_EYE_LIDS[1], w, h)
            right_upper = get_landmark_xy(landmarks, RIGHT_EYE_LIDS[0], w, h)
            right_lower = get_landmark_xy(landmarks, RIGHT_EYE_LIDS[1], w, h)

            left_eye_center = mean_point([left_outer, left_inner, left_upper, left_lower])
            right_eye_center = mean_point([right_outer, right_inner, right_upper, right_lower])
            left_iris_center = mean_point([get_landmark_xy(landmarks, idx, w, h) for idx in LEFT_IRIS])
            right_iris_center = mean_point([get_landmark_xy(landmarks, idx, w, h) for idx in RIGHT_IRIS])

            left_eye_width = max(dist(left_outer, left_inner), 1e-6)
            right_eye_width = max(dist(right_outer, right_inner), 1e-6)
            left_eye_height = max(dist(left_upper, left_lower), 1e-6)
            right_eye_height = max(dist(right_upper, right_lower), 1e-6)

            left_offset = (
                (left_iris_center[0] - left_eye_center[0]) / left_eye_width,
                (left_iris_center[1] - left_eye_center[1]) / left_eye_height,
            )
            right_offset = (
                (right_iris_center[0] - right_eye_center[0]) / right_eye_width,
                (right_iris_center[1] - right_eye_center[1]) / right_eye_height,
            )

            left_origin = (
                (left_eye_center[0] / w) - 0.5,
                0.5 - (left_eye_center[1] / h),
            )
            right_origin = (
                (right_eye_center[0] / w) - 0.5,
                0.5 - (right_eye_center[1] / h),
            )

            left_plane_hit = ray_intersection_on_plane(left_origin, left_offset)
            right_plane_hit = ray_intersection_on_plane(right_origin, right_offset)
            raw_intersection = (left_plane_hit + right_plane_hit) / 2.0
            gaze_norm = apply_calibration(raw_intersection, None)

            with self.state.lock:
                if self.state.calibration_matrix is not None:
                    gaze_norm = apply_calibration(raw_intersection, self.state.calibration_matrix)
                self.state.latest_gaze_norm = gaze_norm
                self.state.latest_raw_point = raw_intersection.copy()
                self.state.latest_left_eye_center = left_eye_center
                self.state.latest_right_eye_center = right_eye_center
                self.state.latest_left_iris_center = left_iris_center
                self.state.latest_right_iris_center = right_iris_center
                self.state.latest_face_ok = True
                self.state.latest_status = "Rosto detectado | seleção por fixação | zoom por piscadas"
                self.state.gaze_history.append(gaze_norm)
                self.state.raw_history.append((float(raw_intersection[0]), float(raw_intersection[1])))

            avg_ear = 0.5 * (
                eye_aspect_ratio(left_upper, left_lower, left_outer, left_inner)
                + eye_aspect_ratio(right_upper, right_lower, right_outer, right_inner)
            )
            self._process_blinks(avg_ear, now_ts)
            self._update_selection(gaze_norm, now_ts)

            for pt in [left_eye_center, right_eye_center]:
                cv2.circle(overlay, (int(pt[0]), int(pt[1])), 5, (255, 255, 0), -1)
            for pt in [left_iris_center, right_iris_center]:
                cv2.circle(overlay, (int(pt[0]), int(pt[1])), 5, (0, 0, 255), -1)

            # desenha os raios aproximados
            def draw_ray(origin_xy, hit_xy, color):
                ox = int((origin_xy[0] + 0.5) * w)
                oy = int((0.5 - origin_xy[1]) * h)
                hx = int(clamp(0.5 + hit_xy[0], 0.0, 1.0) * w)
                hy = int(clamp(0.5 - hit_xy[1], 0.0, 1.0) * h)
                cv2.line(overlay, (ox, oy), (hx, hy), color, 2)

            draw_ray(left_origin, left_plane_hit, (0, 180, 255))
            draw_ray(right_origin, right_plane_hit, (0, 255, 180))

            status_msg = "OK"
            face_ok = True

        with self.state.lock:
            self.state.latest_face_ok = face_ok
            if not face_ok:
                self.state.latest_status = status_msg

        result = cv2.addWeighted(overlay, 0.45, self._draw_virtual_gallery(image.copy()), 0.55, 0)
        return av.VideoFrame.from_ndarray(result, format="bgr24")


# ============================================================
# INICIALIZAÇÃO DO ESTADO
# ============================================================
if "shared_tracker_state" not in st.session_state:
    st.session_state.shared_tracker_state = SharedTrackerState()

shared_state: SharedTrackerState = st.session_state.shared_tracker_state
IrisGalleryProcessor.shared_state = shared_state


# ============================================================
# AÇÕES DA SIDEBAR
# ============================================================
with st.sidebar:
    st.header("Calibração e controle")
    st.write(
        "Olhe para o alvo vermelho no vídeo e capture cada ponto. São 5 pontos: canto superior esquerdo, superior direito, centro, inferior esquerdo e inferior direito."
    )

    if st.button("Capturar ponto atual", use_container_width=True):
        with shared_state.lock:
            raw = None if shared_state.latest_raw_point is None else shared_state.latest_raw_point.copy()
            idx = shared_state.current_target_index
        if raw is not None and idx < len(CALIBRATION_TARGETS):
            with shared_state.lock:
                shared_state.calibration_samples.append((raw, CALIBRATION_TARGETS[idx]))
                shared_state.current_target_index += 1
                shared_state.calibration_matrix = fit_calibration_matrix(shared_state.calibration_samples)
        else:
            st.warning("Ainda não há um ponto bruto disponível. Ligue a câmera e deixe o rosto visível.")

    if st.button("Resetar calibração", use_container_width=True):
        shared_state.reset_calibration()

    if st.button("Resetar rastreamento", use_container_width=True):
        shared_state.reset_tracking()

    pdf_bytes = build_pdf_report(shared_state)
    st.download_button(
        "Baixar relatório PDF",
        data=pdf_bytes,
        file_name="relatorio_gaze_galeria.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

    with shared_state.lock:
        cal_ready = shared_state.calibration_matrix is not None
        current_target_idx = shared_state.current_target_index
        sample_count = len(shared_state.calibration_samples)
        selected_id = shared_state.selected_painting_id
        zoom_value = shared_state.zoom_level
        blink_msg = shared_state.blink_message

    st.metric("Pontos de calibração", f"{sample_count}/{len(CALIBRATION_TARGETS)}")
    st.metric("Calibração pronta", "Sim" if cal_ready else "Não")
    st.metric("Zoom", f"{zoom_value:.2f}x")
    st.caption(blink_msg)

    if current_target_idx < len(CALIBRATION_TARGETS):
        tx, ty = CALIBRATION_TARGETS[current_target_idx]
        st.info(f"Próximo alvo: ({tx:.2f}, {ty:.2f})")
    else:
        st.success("Todos os alvos foram capturados.")

    selected_p = painting_by_id(selected_id)
    if selected_p is not None:
        st.success(f"Quadro ativo: {selected_p['title']}")


# ============================================================
# LAYOUT PRINCIPAL
# ============================================================
st.title("Galeria em Streamlit controlada pela íris")
st.write(
    "Este app substitui a lógica de mouse por rastreamento ocular usando centros dos olhos, centros das íris, projeção de raios, interseção num plano virtual e calibração multiponto."
)

st.markdown(
    """
### Como usar
1. Ligue a webcam no componente abaixo.
2. Deixe o rosto frontal e bem iluminado.
3. Olhe para cada alvo vermelho e clique em **Capturar ponto atual** na barra lateral.
4. Depois da calibração, fixe o olhar sobre um quadro por cerca de 0,8 s para selecioná-lo.
5. Piscada simples afasta; piscada dupla aproxima.
6. Baixe o PDF com o mapa de calor quando quiser.
"""
)

ctx = webrtc_streamer(
    key="iris-gallery",
    mode=WebRtcMode.SENDRECV,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
    video_processor_factory=IrisGalleryProcessor,
    async_processing=True,
)

with shared_state.lock:
    face_ok = shared_state.latest_face_ok
    gaze = shared_state.latest_gaze_norm
    selected = painting_by_id(shared_state.selected_painting_id)
    left_eye = shared_state.latest_left_eye_center
    right_eye = shared_state.latest_right_eye_center
    left_iris = shared_state.latest_left_iris_center
    right_iris = shared_state.latest_right_iris_center
    status_text = shared_state.latest_status
    selection_count = len(shared_state.selection_events)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rosto detectado", "Sim" if face_ok else "Não")
c2.metric("Gaze X", f"{gaze[0]:.2f}")
c3.metric("Gaze Y", f"{gaze[1]:.2f}")
c4.metric("Seleções", str(selection_count))
st.caption(status_text)

st.subheader("Galeria virtual")
cols = st.columns(3)
for col, painting in zip(cols, PAINTINGS):
    is_selected = selected is not None and selected["id"] == painting["id"]
    box_text = f"área {painting['box'][0]:.2f}, {painting['box'][1]:.2f}, {painting['box'][2]:.2f}, {painting['box'][3]:.2f}"
    with col:
        st.markdown(
            f"### {'🟢 ' if is_selected else ''}{painting['title']}\n"
            f"**Autor:** {painting['artist']}  \n"
            f"**Ano:** {painting['year']}  \n"
            f"**Descrição:** {painting['description']}  \n"
            f"**Caixa virtual:** {box_text}"
        )

st.subheader("Diagnóstico geométrico do olho")
d1, d2 = st.columns(2)
with d1:
    st.write("**Centros dos olhos**")
    st.code(
        f"Olho esquerdo: {left_eye}\nOlho direito: {right_eye}",
        language="text",
    )
with d2:
    st.write("**Centros das íris**")
    st.code(
        f"Íris esquerda: {left_iris}\nÍris direita: {right_iris}",
        language="text",
    )

st.info(
    "Observação: o seu código original foi reescrito para Streamlit. Em vez de janelas desktop com tkinter/cv2.imshow, esta versão usa webcam em Streamlit e mantém a lógica em Python para olhar, calibrar, selecionar quadro e gerar heatmap."
)
