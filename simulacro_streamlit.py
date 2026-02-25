import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode
import av
import cv2
import numpy as np
import mediapipe as mp
import time

st.set_page_config(page_title="Simulacro Iris 3D", layout="wide")
st.title("Simulacro — Controle 3D com Íris")

# --------------------------
# MediaPipe setup
# --------------------------
mp_face_mesh = mp.solutions.face_mesh

LEFT_IRIS = [468, 469, 470, 471]
RIGHT_IRIS = [473, 474, 475, 476]
LEFT_EYE = [33, 133]
RIGHT_EYE = [362, 263]

# --------------------------
# Função da esfera 3D fake
# --------------------------
def draw_ball(frame, x, y, r=40):
    h, w = frame.shape[:2]
    for i in range(r, 0, -1):
        color = (int(255 * (i/r)), 100, 255)
        cv2.circle(frame, (x, y), i, color, -1)

# --------------------------
# Classe de vídeo
# --------------------------
class IrisTracker(VideoTransformerBase):
    def __init__(self):
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True
        )
        self.gaze = (0, 0)
        self.calibrated = False
        self.offset = np.array([0.0, 0.0])

    def get_center(self, landmarks, idx, w, h):
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in idx]
        return np.mean(pts, axis=0)

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        res = self.face_mesh.process(rgb)

        if res.multi_face_landmarks:
            lm = res.multi_face_landmarks[0].landmark

            lx, ly = self.get_center(lm, LEFT_EYE, w, h)
            rx, ry = self.get_center(lm, RIGHT_EYE, w, h)

            lix, liy = self.get_center(lm, LEFT_IRIS, w, h)
            rix, riy = self.get_center(lm, RIGHT_IRIS, w, h)

            eye_center = np.array([(lx+rx)/2, (ly+ry)/2])
            iris_center = np.array([(lix+rix)/2, (liy+riy)/2])

            eye_width = np.linalg.norm([lx-rx, ly-ry]) + 1e-6
            offset = (iris_center - eye_center) / eye_width

            gx = np.clip(offset[0]*3, -1, 1)
            gy = np.clip(-offset[1]*3, -1, 1)

            if self.calibrated:
                gx -= self.offset[0]
                gy -= self.offset[1]

            self.gaze = (gx, gy)

        # mover bola
        cx = int(w/2 + self.gaze[0]*(w/2-60))
        cy = int(h/2 + self.gaze[1]*(h/2-60))

        draw_ball(img, cx, cy, 50)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --------------------------
# WebRTC
# --------------------------
ctx = webrtc_streamer(
    key="iris",
    mode=WebRtcMode.SENDRECV,
    video_processor_factory=IrisTracker,
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,
)

# --------------------------
# Interface
# --------------------------
if ctx.video_transformer:
    gaze = ctx.video_transformer.gaze
    st.write(f"Gaze X: {gaze[0]:.2f} | Gaze Y: {gaze[1]:.2f}")

    if st.button("Calibrar centro"):
        ctx.video_transformer.offset = np.array(gaze)
        ctx.video_transformer.calibrated = True
        st.success("Calibrado!")
