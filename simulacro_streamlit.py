import streamlit as st
import cv2
import numpy as np
import mediapipe as mp
import plotly.graph_objects as go

st.set_page_config(layout="wide")

st.title("Controle 3D com Iris Tracking")

# =============================
# INIT
# =============================

if "run" not in st.session_state:
    st.session_state.run = False

if "cap" not in st.session_state:
    st.session_state.cap = None

if st.button("Iniciar"):
    st.session_state.run = True
    st.session_state.cap = cv2.VideoCapture(0)

if st.button("Parar"):
    st.session_state.run = False
    if st.session_state.cap:
        st.session_state.cap.release()
        st.session_state.cap = None

frame_placeholder = st.empty()
plot_placeholder = st.empty()

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True
)

LEFT_EYE_IDX = [33, 133]
RIGHT_EYE_IDX = [362, 263]
LEFT_IRIS_IDX = [468,469,470,471]
RIGHT_IRIS_IDX = [473,474,475,476]

def landmark_mean(landmarks, indices, w, h):
    pts = []
    for i in indices:
        lm = landmarks[i]
        pts.append([lm.x * w, lm.y * h])
    return np.mean(pts, axis=0)

def create_sphere(x, y):
    u = np.linspace(0, 2*np.pi, 30)
    v = np.linspace(0, np.pi, 15)
    xs = 0.3*np.outer(np.cos(u), np.sin(v)) + x
    ys = 0.3*np.outer(np.sin(u), np.sin(v)) + y
    zs = 0.3*np.outer(np.ones(np.size(u)), np.cos(v))
    fig = go.Figure(data=[go.Surface(x=xs, y=ys, z=zs, showscale=False)])
    fig.update_layout(
        scene=dict(
            xaxis=dict(range=[-1,1], visible=False),
            yaxis=dict(range=[-1,1], visible=False),
            zaxis=dict(range=[-1,1], visible=False)
        ),
        margin=dict(l=0,r=0,t=0,b=0)
    )
    return fig

# =============================
# MAIN LOOP CONTROLLED
# =============================

if st.session_state.run and st.session_state.cap:

    ret, frame = st.session_state.cap.read()

    if ret:
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        gaze_x, gaze_y = 0, 0

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark

            left_eye = landmark_mean(landmarks, LEFT_EYE_IDX, w, h)
            right_eye = landmark_mean(landmarks, RIGHT_EYE_IDX, w, h)
            left_iris = landmark_mean(landmarks, LEFT_IRIS_IDX, w, h)
            right_iris = landmark_mean(landmarks, RIGHT_IRIS_IDX, w, h)

            eye_center = (left_eye + right_eye)/2
            iris_center = (left_iris + right_iris)/2

            offset = (iris_center - eye_center)/w

            gaze_x = np.clip(offset[0]*4, -1, 1)
            gaze_y = np.clip(-offset[1]*4, -1, 1)

        fig = create_sphere(gaze_x, gaze_y)
        plot_placeholder.plotly_chart(fig, use_container_width=True)

        frame_placeholder.image(rgb)

    st.experimental_rerun()
