# app.py
import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode, ClientSettings
import av
import cv2
import numpy as np
import mediapipe as mp
import time
from typing import Tuple

st.set_page_config(page_title="Simulacro — Iris Gaze 3D (WebRTC)", layout="wide")
st.title("Simulacro — Controle de Bola 3D com Rastreamento de Íris (WebRTC)")

# -------------------------
# UI CONTROLS
# -------------------------
col1, col2 = st.columns([1, 1])
with col1:
    st.markdown("**Controles**")
    start_stop = st.button("Iniciar / Parar")
    calibrate_btn = st.button("Calibrar (olhe para o centro por 2s)")
    st.markdown("Observação: permita acesso à webcam no navegador.")
with col2:
    st.markdown("**Status**")
    status_text = st.empty()
    calib_status = st.empty()

# -------------------------
# WebRTC client settings
# -------------------------
# Default ICE/STUN may be fine for Streamlit Cloud
CLIENT_SETTINGS = ClientSettings(
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    media_stream_constraints={"video": True, "audio": False},
)

# -------------------------
# Face mesh / indices
# -------------------------
LEFT_EYE_IDX = [33, 133]   # coarse center points for left eye contour (approx)
RIGHT_EYE_IDX = [362, 263] # coarse center points for right eye contour
LEFT_IRIS_IDX = [468, 469, 470, 471]
RIGHT_IRIS_IDX = [473, 474, 475, 476]

# -------------------------
# Helper drawing: shaded sphere (2.5D)
# -------------------------
def draw_shaded_ball(frame: np.ndarray, cx: int, cy: int, radius: int = 40) -> None:
    """
    Draw a simple shaded ball (gradient circle) at (cx,cy) onto frame in-place.
    """
    h, w = frame.shape[:2]
    # bounding box
    x0 = max(0, cx - radius)
    x1 = min(w, cx + radius)
    y0 = max(0, cy - radius)
    y1 = min(h, cy + radius)

    ys, xs = np.mgrid[y0:y1, x0:x1]
    dx = xs - cx
    dy = ys - cy
    dist = np.sqrt(dx**2 + dy**2)
    mask = dist <= radius

    if not mask.any():
        return

    # normalised distance 0..1
    nd = np.zeros_like(dist, dtype=np.float32)
    nd[mask] = dist[mask] / float(radius)

    # simple lighting: brighter at top-left
    light = 0.8 - 0.6 * nd  # base brightness
    # specular highlight
    spec = np.exp(- ( (dx/ (radius*0.5))**2 + (dy/(radius*0.5))**2 ) )
    spec = (spec - spec.min()) / (spec.max() - spec.min() + 1e-9)

    # color (blue-ish)
    base_color = np.array([40, 140, 255], dtype=np.float32)  # BGR
    shaded = (base_color * light[..., None]) + (255 * spec[..., None] * 0.6)

    region = frame[y0:y1, x0:x1].astype(np.float32)
    # blend only where mask
    mask3 = np.repeat(mask[:, :, None], 3, axis=2)
    blended = region.copy()
    blended[mask3] = 0.6 * blended[mask3] + 0.4 * shaded[mask3]
    frame[y0:y1, x0:x1] = blended.astype(np.uint8)

# -------------------------
# Video transformer
# -------------------------
class GazeTransformer(VideoTransformerBase):
    def __init__(self):
        # MediaPipe FaceMesh (init heavy; keep single instance)
        self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.gain = 3.5
        self.calibrating = False
        self.calib_start_time = None
        self.calib_samples = []
        self.calib_offset = np.array([0.0, 0.0])
        self.calibrated = False
        self.last_gaze = (0.0, 0.0)  # normalized -1..1

    def __del__(self):
        try:
            self.mp_face_mesh.close()
        except Exception:
            pass

    def landmark_mean(self, landmarks, indices, w, h) -> Tuple[float, float]:
        pts = []
        for i in indices:
            lm = landmarks[i]
            pts.append([lm.x * w, lm.y * h])
        if len(pts) == 0:
            return (0.0, 0.0)
        m = np.mean(np.array(pts), axis=0)
        return float(m[0]), float(m[1])

    def transform(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = self.mp_face_mesh.process(rgb)
        gaze_x = 0.0
        gaze_y = 0.0
        valid = False

        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0].landmark
            # eye centers
            lx, ly = self.landmark_mean(lm, LEFT_EYE_IDX, w, h)
            rx, ry = self.landmark_mean(lm, RIGHT_EYE_IDX, w, h)
            lix, liy = self.landmark_mean(lm, LEFT_IRIS_IDX, w, h)
            rix, riy = self.landmark_mean(lm, RIGHT_IRIS_IDX, w, h)

            eye_center = np.array([(lx + rx) / 2.0, (ly + ry) / 2.0])
            iris_center = np.array([(lix + rix) / 2.0, (liy + riy) / 2.0])

            # offset in normalized eye-width units
            eye_width = np.linalg.norm(np.array([lx, ly]) - np.array([rx, ry])) + 1e-6
            offset = (iris_center - eye_center) / eye_width

            gaze_x = float(np.clip(offset[0] * self.gain, -1.0, 1.0))
            gaze_y = float(np.clip(-offset[1] * self.gain, -1.0, 1.0))
            valid = True
            self.last_gaze = (gaze_x, gaze_y)

            # Draw landmarks (optional, for debugging)
            for (px, py) in ([ (int(lix), int(liy)), (int(rix), int(riy)) ]):
                cv2.circle(img, (px, py), 2, (0,0,255), -1)
            # draw eye centers
            for (px, py) in ([ (int(lx), int(ly)), (int(rx), int(ry)) ]):
                cv2.circle(img, (px, py), 2, (0,255,0), -1)

        # Calibration handling (triggered from main thread by setting transformer.calibrating True)
        if self.calibrating:
            # collect for 2 seconds
            if self.calib_start_time is None:
                self.calib_start_time = time.time()
                self.calib_samples = []
            if valid:
                self.calib_samples.append(np.array([gaze_x, gaze_y]))
            if time.time() - self.calib_start_time >= 2.0:
                if len(self.calib_samples) > 0:
                    self.calib_offset = np.mean(self.calib_samples, axis=0)
                    self.calibrated = True
                self.calibrating = False
                self.calib_start_time = None

        # Apply calibration offset
        if self.calibrated and valid:
            gaze_x = gaze_x - float(self.calib_offset[0])
            gaze_y = gaze_y - float(self.calib_offset[1])
            # clip again
            gaze_x = float(np.clip(gaze_x, -1.2, 1.2))
            gaze_y = float(np.clip(gaze_y, -1.2, 1.2))
            self.last_gaze = (gaze_x, gaze_y)

        # Map normalized gaze (-1..1) to pixel coordinates for ball position
        # center of frame -> (w/2, h/2), left->-1, right->+1
        ball_x = int(w/2 + (w/2 - 40) * gaze_x)
        ball_y = int(h/2 + (h/2 - 40) * gaze_y)

        # Draw the shaded ball
        draw_shaded_ball(img, ball_x, ball_y, radius=int(min(w,h)*0.08))

        # Optionally show a small reticle for gaze center
        cv2.circle(img, (ball_x, ball_y), 4, (255,255,255), -1)

        # Put status text
        status = "Calibrated" if self.calibrated else ("Calibrating..." if self.calibrating else "Not calibrated")
        cv2.putText(img, f"Gaze: {self.last_gaze[0]:+.2f},{self.last_gaze[1]:+.2f} | {status}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240,240,240), 2, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# -------------------------
# Launch WebRTC streamer
# -------------------------
webrtc_ctx = webrtc_streamer(
    key="gaze",
    mode=WebRtcMode.SENDRECV,
    client_settings=CLIENT_SETTINGS,
    video_processor_factory=GazeTransformer,
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,
)

# -------------------------
# Buttons interaction logic
# -------------------------
# Toggle start/stop
if start_stop:
    if webrtc_ctx.state.playing:
        webrtc_ctx.stop()
    else:
        webrtc_ctx.start()

# Calibrate button: signal transformer to calibrate
if calibrate_btn:
    if webrtc_ctx.video_transformer:
        webrtc_ctx.video_transformer.calibrating = True
        webrtc_ctx.video_transformer.calibrated = False
        webrtc_ctx.video_transformer.calib_samples = []
        webrtc_ctx.video_transformer.calib_start_time = None

# Display text status
if webrtc_ctx.state.playing:
    status_text.info("WebRTC: ativo — webcam conectada")
else:
    status_text.warning("WebRTC: inativo")

# Show calibration status from transformer (if available)
if webrtc_ctx.video_transformer:
    t = webrtc_ctx.video_transformer
    if t.calibrating:
        calib_status.info("Calibrando... olhe para o centro por 2s")
    elif t.calibrated:
        calib_status.success("Calibração concluída")
    else:
        calib_status.info("Não calibrado")

# Optional: show last gaze numeric readout
if webrtc_ctx.video_transformer:
    gx, gy = webrtc_ctx.video_transformer.last_gaze
    st.write(f"Última gaze (norm): x={gx:.3f}, y={gy:.3f}")
