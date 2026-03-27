import cv2
import numpy as np
import streamlit as st
import time
import math
import random

# ==========================
# CONFIGURAÇÃO BÁSICA
# ==========================

st.set_page_config(page_title="Orlosky Eye Tracker 3D", layout="wide")
st.title("🎯 Orlosky Eye Tracker 3D (versão Web simplificada)")
st.write("""
Este é um rastreador ocular experimental adaptado para **Streamlit**.
Exibe os frames processados no navegador, sem janelas externas (Tkinter/OpenCV).
""")

# ==========================
# FUNÇÕES AUXILIARES
# ==========================

def crop_to_aspect_ratio(image, width=640, height=480):
    """Corta e redimensiona mantendo proporção."""
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

def get_darkest_area(image):
    """Encontra a área mais escura (possível posição da pupila)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    min_sum = float('inf')
    darkest_point = (gray.shape[1] // 2, gray.shape[0] // 2)

    step = 10
    size = 20
    for y in range(20, gray.shape[0] - 20, step):
        for x in range(20, gray.shape[1] - 20, step):
            region = gray[y:y + size, x:x + size]
            s = np.sum(region)
            if s < min_sum:
                min_sum = s
                darkest_point = (x + size // 2, y + size // 2)

    return darkest_point

def apply_binary_threshold(image, darkest_value, offset):
    """Aplica limiarização para destacar a pupila."""
    thresh = darkest_value + offset
    _, binary = cv2.threshold(image, thresh, 255, cv2.THRESH_BINARY_INV)
    return binary

def find_pupil(frame):
    """Detecta a pupila aproximada no frame."""
    frame = crop_to_aspect_ratio(frame)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    darkest_point = get_darkest_area(frame)
    darkest_val = gray[darkest_point[1], darkest_point[0]]

    # threshold médio
    thresh = apply_binary_threshold(gray, darkest_val, 15)
    thresh = cv2.medianBlur(thresh, 5)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return frame, None

    largest = max(contours, key=cv2.contourArea)
    if len(largest) < 5:
        return frame, None

    ellipse = cv2.fitEllipse(largest)
    (cx, cy), (ma, mi), angle = ellipse

    # desenha o resultado
    vis = frame.copy()
    cv2.ellipse(vis, ellipse, (0, 255, 255), 2)
    cv2.circle(vis, (int(cx), int(cy)), 6, (255, 0, 0), -1)
    cv2.circle(vis, darkest_point, 5, (0, 0, 255), -1)

    return vis, (int(cx), int(cy))

# ==========================
# INTERFACE STREAMLIT
# ==========================

st.sidebar.header("⚙️ Controles")
source = st.sidebar.selectbox("Selecione a fonte de vídeo", ["Câmera (webcam)", "Arquivo de vídeo"])

start_button = st.sidebar.button("▶️ Iniciar rastreamento")
stop_placeholder = st.sidebar.empty()

frame_container = st.empty()
info_placeholder = st.empty()

if start_button:
    if source == "Câmera (webcam)":
        cap = cv2.VideoCapture(0)
        st.sidebar.success("📷 Capturando da webcam...")
    else:
        file = st.sidebar.file_uploader("Envie um vídeo", type=["mp4", "avi", "mov"])
        if file is None:
            st.warning("Envie um vídeo para continuar.")
            st.stop()
        tfile = open("temp_video.mp4", "wb")
        tfile.write(file.read())
        cap = cv2.VideoCapture("temp_video.mp4")
        st.sidebar.success("🎞︎ Reproduzindo vídeo enviado...")

    start_time = time.time()
    frame_count = 0

    stop = False
    stop_button = stop_placeholder.button("⏹️ Parar rastreamento")

    while cap.isOpened() and not stop:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        processed_frame, pupil_center = find_pupil(frame)

        # Informações sobre a detecção
        if pupil_center:
            info_placeholder.markdown(
                f"**Centro da pupila:** {pupil_center[0]}, {pupil_center[1]}"
            )

        frame_container.image(processed_frame, channels="BGR")

        # controle de FPS e parada
        if stop_placeholder.button("⏹️ Parar rastreamento"):
            stop = True
            break

    cap.release()
    st.sidebar.info("✅ Rastreamento finalizado.")
else:
    st.info("Clique em **Iniciar rastreamento** para começar.")
