# app_gaze_streamlit.py
import streamlit as st
import cv2
import numpy as np
import mediapipe as mp
import plotly.graph_objects as go
import time

st.set_page_config(layout="wide", page_title="Gaze-Controlled 3D Ball")

# -----------------------
# Helpers / Constants
# -----------------------
mp_face_mesh = mp.solutions.face_mesh
FACE_MESH = mp_face_mesh.FaceMesh(static_image_mode=False,
                                  max_num_faces=1,
                                  refine_landmarks=True,  # required to get iris landmarks
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

# Common MediaPipe face mesh indices (typical)
# eye contour indices (for center estimation)
LEFT_EYE_IDX = [33, 133, 160, 159, 158, 157, 173, 144, 145, 153, 154, 155]
RIGHT_EYE_IDX = [362, 263, 387, 386, 385, 384, 398, 381, 382, 380, 373, 374]

# iris indices usually (refine_landmarks=True provides these)
LEFT_IRIS_IDX = [468, 469, 470, 471]
RIGHT_IRIS_IDX = [473, 474, 475, 476]

# Mapping params
GAIN = 1.3  # how aggressively gaze moves the ball
FPS_TARGET = 20

# -----------------------
# UI
# -----------------------
st.title("Controle de Bola 3D com Rastreamento de Íris (Streamlit + MediaPipe)")
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("#### Webcam")
    run_button = st.button("Iniciar / Parar Captura")
    calibrate_button = st.button("Calibrar (olhe para o centro por 2s)")
    st.markdown("**Instruções:** permita a webcam, olhe para o centro durante calibração.\n\nSe o rastreamento falhar, verifique luz e posição da câmera.")
    cam_frame = st.image([])

with col2:
    st.markdown("#### Bola 3D controlada pelo olhar")
    plotly_chart = st.plotly_chart({}, use_container_width=True)
    st.markdown("Mapa de gaze: a posição da bola segue o olhar (x = esquerda/direita, y = cima/baixo).")

# Session state
if "running" not in st.session_state:
    st.session_state.running = False
if "calib" not in st.session_state:
    st.session_state.calib = np.array([0.0, 0.0])
if "has_calib" not in st.session_state:
    st.session_state.has_calib = False
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()

# Toggle running
if run_button:
    st.session_state.running = not st.session_state.running

# Calibration
if calibrate_button:
    st.session_state.has_calib = False
    st.info("Calibrando: olhe para o centro da câmera... Segure por 2 segundos.")
    # We'll capture calibration in the loop below by setting a flag
    st.session_state.do_calib = True

# Initialize camera capture when running
if st.session_state.running:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        st.error("Não foi possível abrir a webcam. Verifique permissões e dispositivo.")
        st.session_state.running = False
    else:
        # Set small resolution to improve speed
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Utility: compute mean of landmarks by indices
def landmark_mean(landmarks, idx_list, w, h):
    pts = []
    for idx in idx_list:
        lm = landmarks[idx]
        pts.append((int(lm.x * w), int(lm.y * h)))
    pts = np.array(pts)
    return pts.mean(axis=0), pts, pts.astype(int)

# Utility: draw overlay on frame
def draw_overlay(frame, left_eye_pts=None, right_eye_pts=None, left_iris=None, right_iris=None):
    out = frame.copy()
    if left_eye_pts is not None:
        cv2.polylines(out, [left_eye_pts], isClosed=True, color=(0,255,0), thickness=1)
    if right_eye_pts is not None:
        cv2.polylines(out, [right_eye_pts], isClosed=True, color=(0,255,0), thickness=1)
    if left_iris is not None:
        for (x,y) in left_iris:
            cv2.circle(out, (x,y), 1, (0,0,255), -1)
    if right_iris is not None:
        for (x,y) in right_iris:
            cv2.circle(out, (x,y), 1, (0,0,255), -1)
    return out

# Utility: update plotly sphere
def plot_ball(x=0.0, y=0.0, z=0.0):
    # create sphere mesh
    u = np.linspace(0, 2 * np.pi, 40)
    v = np.linspace(0, np.pi, 20)
    xu = 0.25 * np.outer(np.cos(u), np.sin(v)) + x
    yu = 0.25 * np.outer(np.sin(u), np.sin(v)) + y
    zu = 0.25 * np.outer(np.ones(np.size(u)), np.cos(v)) + z

    fig = go.Figure(data=[
        go.Surface(x=xu, y=yu, z=zu, showscale=False, opacity=0.9)
    ])
    fig.update_layout(scene=dict(
        xaxis=dict(range=[-1.5,1.5], visible=False),
        yaxis=dict(range=[-1.5,1.5], visible=False),
        zaxis=dict(range=[-1.0,1.0], visible=False),
        aspectmode="manual", aspectratio=dict(x=1,y=1,z=0.7)
    ), margin=dict(l=0,r=0,t=0,b=0))
    return fig

# Initial display
plotly_chart.plotly_chart = plotly_chart  # keep attribute for later (no-op)

# Main loop
if st.session_state.running:
    try:
        do_calib_local = hasattr(st.session_state, "do_calib") and st.session_state.do_calib
        calib_samples = []
        # run loop until user stops
        while st.session_state.running:
            # Throttle FPS
            now = time.time()
            dt = now - st.session_state.last_time
            if dt < 1.0 / FPS_TARGET:
                time.sleep(max(0, 1.0 / FPS_TARGET - dt))
            st.session_state.last_time = time.time()

            ret, frame = cap.read()
            if not ret:
                st.warning("Falha ao ler frame da webcam")
                break
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = FACE_MESH.process(rgb)

            gaze_x = 0.0
            gaze_y = 0.0
            valid = False

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark

                # compute eye centers and iris centers
                try:
                    left_eye_center, left_eye_pts, left_eye_pts_int = landmark_mean(landmarks, LEFT_EYE_IDX, w, h)
                    right_eye_center, right_eye_pts, right_eye_pts_int = landmark_mean(landmarks, RIGHT_EYE_IDX, w, h)

                    # iris (refined landmarks present when refine_landmarks=True)
                    left_iris_center, left_iris_pts, left_iris_pts_int = landmark_mean(landmarks, LEFT_IRIS_IDX, w, h)
                    right_iris_center, right_iris_pts, right_iris_pts_int = landmark_mean(landmarks, RIGHT_IRIS_IDX, w, h)

                    # relative offsets of iris center inside eye bounding metric
                    left_eye_w = np.linalg.norm(left_eye_pts_int[0] - left_eye_pts_int[1]) if len(left_eye_pts_int) > 1 else (w*0.1)
                    right_eye_w = np.linalg.norm(right_eye_pts_int[0] - right_eye_pts_int[1]) if len(right_eye_pts_int) > 1 else (w*0.1)
                    left_offset = (left_iris_center - left_eye_center) / max(left_eye_w, 1e-6)
                    right_offset = (right_iris_center - right_eye_center) / max(right_eye_w, 1e-6)

                    # combine both eyes
                    offset = (left_offset + right_offset) / 2.0  # [dx, dy] in normalized eye units
                    # map to gaze in [-1,1]; invert y because image coords increase downwards
                    gaze_x = np.clip(offset[0] * GAIN, -1.0, 1.0)
                    gaze_y = np.clip(-offset[1] * GAIN, -1.0, 1.0)
                    valid = True

                    # overlay
                    out = draw_overlay(frame, left_eye_pts_int, right_eye_pts_int, left_iris_pts_int, right_iris_pts_int)

                except Exception as e:
                    out = frame.copy()
                    # if something failed, just show frame
                    # (don't raise - continue)
                    # print(e)  # debug if needed

            else:
                out = frame.copy()

            # Calibration capture
            if do_calib_local:
                if valid:
                    calib_samples.append(np.array([gaze_x, gaze_y]))
                # collect for 2 seconds
                if len(calib_samples) >= int(FPS_TARGET * 2):
                    avg = np.mean(calib_samples, axis=0)
                    st.session_state.calib = avg
                    st.session_state.has_calib = True
                    st.session_state.do_calib = False
                    do_calib_local = False
                    st.success("Calibração concluída.")
                else:
                    st.info("Calibrando... aguarde.")
            # If already calibrated, subtract baseline
            if st.session_state.has_calib and valid:
                gaze_x = gaze_x - st.session_state.calib[0]
                gaze_y = gaze_y - st.session_state.calib[1]
                # clip again
                gaze_x = float(np.clip(gaze_x, -1.2, 1.2))
                gaze_y = float(np.clip(gaze_y, -1.2, 1.2))

            # Map gaze to 3D coordinates for sphere:
            # x: left (-1) to right (1)
            # y: down (-1) to up (1)
            # z: small depth based on magnitude of offset (for subtle parallax)
            z = -0.2 * (abs(gaze_x) + abs(gaze_y))  # go slightly "in" when extreme
            fig = plot_ball(x=gaze_x, y=gaze_y, z=z)
            plotly_chart.plotly_chart(fig, use_container_width=True)

            # show frame
            cam_frame.image(cv2.cvtColor(out, cv2.COLOR_BGR2RGB), channels="RGB")

            # flush Streamlit events (allows button to be responsive)
            if not st.session_state.running:
                break

        # cleanup
        cap.release()

    except Exception as e:
        st.exception(f"Ocorreu um erro durante a captura: {e}")
        if 'cap' in locals() and cap.isOpened():
            cap.release()
else:
    # show initial empty sphere
    fig0 = plot_ball(0.0, 0.0, 0.0)
    plotly_chart.plotly_chart(fig0, use_container_width=True)
    cam_frame.image(np.zeros((480,640,3), dtype=np.uint8))

# Footer note
st.markdown("---")
st.markdown("**Observações / Limitações:**")
st.markdown("""
- O app usa estimativa simples: média dos *landmarks* de íris e centro do olho. Isso é robusto para protótipos, mas não alcança precisão clínica.
- Em ambientes com pouca luz, reflexos ou câmeras com baixa resolução, o rastreamento pode falhar.
- Dependendo da versão do MediaPipe, os índices de *landmarks* para íris podem variar; se o traçado não aparecer, habilite `refine_landmarks=True` (já ativado) ou ajuste `LEFT_IRIS_IDX`/`RIGHT_IRIS_IDX`.
- Para maior precisão, substitua a estratégia por *head pose estimation* + modelo geométrico do globo ocular (solvePnP) ou redes profundas treinadas.
- O app inclui uma calibração simples (olhar para o centro) que melhora o comportamento.
""")
