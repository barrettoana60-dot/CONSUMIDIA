import streamlit as st
import cv2
import numpy as np
import mediapipe as mp
import plotly.graph_objects as go
import time

st.set_page_config(layout="wide", page_title="Gaze 3D Controller")

# ==============================
# CONFIG
# ==============================
FPS = 30
GAIN = 4.0

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

LEFT_EYE_IDX = [33, 133]
RIGHT_EYE_IDX = [362, 263]

LEFT_IRIS_IDX = [468, 469, 470, 471]
RIGHT_IRIS_IDX = [473, 474, 475, 476]

# ==============================
# SESSION STATE
# ==============================
if "running" not in st.session_state:
    st.session_state.running = False

if "calibrated" not in st.session_state:
    st.session_state.calibrated = False

if "calib_offset" not in st.session_state:
    st.session_state.calib_offset = np.array([0.0, 0.0])

# ==============================
# FUNCTIONS
# ==============================
def landmark_mean(landmarks, indices, w, h):
    pts = []
    for i in indices:
        lm = landmarks[i]
        pts.append([lm.x * w, lm.y * h])
    return np.mean(np.array(pts), axis=0)

def create_sphere(x, y, z):
    u = np.linspace(0, 2 * np.pi, 40)
    v = np.linspace(0, np.pi, 20)

    xs = 0.3 * np.outer(np.cos(u), np.sin(v)) + x
    ys = 0.3 * np.outer(np.sin(u), np.sin(v)) + y
    zs = 0.3 * np.outer(np.ones(np.size(u)), np.cos(v)) + z

    fig = go.Figure(data=[go.Surface(x=xs, y=ys, z=zs, showscale=False)])
    fig.update_layout(
        scene=dict(
            xaxis=dict(range=[-1.5, 1.5], visible=False),
            yaxis=dict(range=[-1.5, 1.5], visible=False),
            zaxis=dict(range=[-1.5, 1.5], visible=False)
        ),
        margin=dict(l=0, r=0, t=0, b=0)
    )
    return fig

# ==============================
# UI
# ==============================
st.title("Controle 3D com Rastreamento de Íris")

col1, col2 = st.columns(2)

with col1:
    if st.button("Iniciar / Parar"):
        st.session_state.running = not st.session_state.running

    if st.button("Calibrar (olhe para o centro)"):
        st.session_state.calibrated = False
        st.session_state.calib_samples = []
        st.session_state.start_calib_time = time.time()

    frame_placeholder = st.empty()

with col2:
    plot_placeholder = st.empty()

# ==============================
# MAIN LOOP CONTROLADO
# ==============================
if st.session_state.running:

    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()

    if ret:
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        gaze_x, gaze_y = 0.0, 0.0

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark

            left_eye = landmark_mean(landmarks, LEFT_EYE_IDX, w, h)
            right_eye = landmark_mean(landmarks, RIGHT_EYE_IDX, w, h)

            left_iris = landmark_mean(landmarks, LEFT_IRIS_IDX, w, h)
            right_iris = landmark_mean(landmarks, RIGHT_IRIS_IDX, w, h)

            eye_center = (left_eye + right_eye) / 2
            iris_center = (left_iris + right_iris) / 2

            offset = (iris_center - eye_center) / w

            gaze_x = float(np.clip(offset[0] * GAIN, -1, 1))
            gaze_y = float(np.clip(-offset[1] * GAIN, -1, 1))

            # =========================
            # CALIBRATION
            # =========================
            if not st.session_state.calibrated:
                if time.time() - st.session_state.start_calib_time < 2:
                    st.session_state.calib_samples.append([gaze_x, gaze_y])
                else:
                    st.session_state.calib_offset = np.mean(
                        st.session_state.calib_samples, axis=0
                    )
                    st.session_state.calibrated = True

            if st.session_state.calibrated:
                gaze_x -= st.session_state.calib_offset[0]
                gaze_y -= st.session_state.calib_offset[1]

        fig = create_sphere(gaze_x, gaze_y, 0)
        plot_placeholder.plotly_chart(fig, use_container_width=True)

        frame_placeholder.image(rgb)

    cap.release()

    time.sleep(1 / FPS)
    st.rerun()

else:
    fig = create_sphere(0, 0, 0)
    plot_placeholder.plotly_chart(fig, use_container_width=True)
