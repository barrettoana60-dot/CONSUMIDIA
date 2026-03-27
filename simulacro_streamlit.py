import cv2
import numpy as np
import mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase

# Configuração da página
st.set_page_config(page_title="Gaze Tracking 3D", layout="wide")
st.title("👁️ Rastreio de Íris e Intersecção 3D")

# --- PARÂMETROS GLOBAIS ---
FOCAL_LENGTH = 1000 
# Modelo 3D genérico para Pose da Cabeça (Parâmetro 1 e 3)
FACE_3D_POINTS = np.array([
    (0.0, 0.0, 0.0),             # Nariz
    (0.0, -330.0, -65.0),        # Queixo
    (-225.0, 170.0, -135.0),     # Olho Esquerdo
    (225.0, 170.0, -135.0),      # Olho Direito
    (-150.0, -150.0, -125.0),    # Boca Esquerda
    (150.0, -150.0, -125.0)      # Boca Direita
], dtype=np.float64)

# --- INICIALIZAÇÃO DO MEDIAPIPE ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True, # ESSENCIAL: Habilita Íris (Parâmetro 2)
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

class GazeTransformer(VideoTransformerBase):
    def __init__(self):
        self.calib_points = 0

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        h, w, _ = img.shape
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        results = face_mesh.process(rgb_img)
        
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                # 1. DETERMINAR CENTROS (FACE LANDMARKS)
                face_2d = []
                for idx in [1, 152, 33, 263, 61, 291]:
                    lm = face_landmarks.landmark[idx]
                    face_2d.append([lm.x * w, lm.y * h])
                face_2d = np.array(face_2d, dtype=np.float64)

                # Matriz da Câmera
                cam_matrix = np.array([[FOCAL_LENGTH, 0, w/2], [0, FOCAL_LENGTH, h/2], [0, 0, 1]], dtype="double")
                dist_coeffs = np.zeros((4, 1), dtype="double")

                # 2. DETERMINAR CENTROS DA ÍRIS (PUPIL/IRIS CENTERS)
                # Landmark 468 = Íris Esquerda, 473 = Íris Direita
                iris_l = face_landmarks.landmark[468]
                iris_r = face_landmarks.landmark[473]
                
                # 3. PROJECT RAYS (Cubo de Rotação)
                success, rvec, tvec = cv2.solvePnP(FACE_3D_POINTS, face_2d, cam_matrix, dist_coeffs)
                rmat, _ = cv2.Rodrigues(rvec)

                # Visualizar Matriz de Rotação (Cubo)
                self.draw_cube(img, rvec, tvec, cam_matrix, dist_coeffs)

                # 4. COMPUTE INTERSECTION (Intersecção no plano Z)
                gaze_dir = rmat[:, 2] # Vetor Z da face
                origin = tvec.flatten()
                
                z_plane = 500.0 # Distância virtual do monitor
                if gaze_dir[2] != 0:
                    t = (z_plane - origin[2]) / gaze_dir[2]
                    intersection = origin + t * gaze_dir
                    
                    # 5. BIND REAL MONITOR TO VIRTUAL
                    # Desenha o ponto de colisão projetado na tela
                    ix, iy = int(intersection[0] + w/2), int(intersection[1] + h/2)
                    cv2.circle(img, (ix, iy), 10, (0, 255, 0), -1)
                    cv2.putText(img, "PONTO NO MONITOR", (ix+15, iy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Desenha íris
                cv2.circle(img, (int(iris_l.x*w), int(iris_l.y*h)), 2, (255, 255, 0), -1)
                cv2.circle(img, (int(iris_r.x*w), int(iris_r.y*h)), 2, (255, 255, 0), -1)

        return img

    def draw_cube(self, img, rvec, tvec, cam_matrix, dist_coeffs):
        size = 50
        box_3d = np.array([[-size,-size,size],[size,-size,size],[size,size,size],[-size,size,size],
                          [-size,-size,-size],[size,-size,-size],[size,size,-size],[-size,size,-size]], dtype=np.float32)
        pts_2d, _ = cv2.projectPoints(box_3d, rvec, tvec, cam_matrix, dist_coeffs)
        pts_2d = np.int32(pts_2d).reshape(-1, 2)
        for i, j in zip(range(4), range(4,8)): cv2.line(img, tuple(pts_2d[i]), tuple(pts_2d[j]), (255,0,0), 2)
        cv2.drawContours(img, [pts_2d[:4]], -1, (0,255,0), 2)
        cv2.drawContours(img, [pts_2d[4:]], -1, (0,0,255), 2)

# --- 6. MULTI POINT CALIBRATION (Interface) ---
st.sidebar.header("Calibração e Controle")
if st.sidebar.button("Limpar Calibração"):
    st.session_state.calib = []

st.write("Aponte o rosto para o monitor. O ponto verde simula sua intersecção de olhar.")

webrtc_streamer(key="gaze-tracker", video_transformer_factory=GazeTransformer)

st.info("Nota: Para calibração precisa, mantenha a cabeça estável e use iluminação frontal.")
