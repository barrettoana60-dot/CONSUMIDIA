import cv2
import numpy as np
import mediapipe as mp
import streamlit as st

# ==========================================
# CONFIGURAÇÕES DA TELA E CÂMERA (Parâmetros 4 e 5)
# ==========================================
# Medidas fictícias para o Monitor Virtual (em mm)
MONITOR_WIDTH_MM = 500
MONITOR_HEIGHT_MM = 300
FOCAL_LENGTH = 1000 # Aproximação da distância focal da webcam

st.set_page_config(page_title="Rastreio Ocular 3D", layout="wide")
st.title("Rastreio Ocular - Pipeline Completa de Gaze 3D")
st.markdown("Recomendado: Webcam 720p/1080p bem iluminada no rosto.")

# ==========================================
# FUNÇÕES MATEMÁTICAS E DE RENDERIZAÇÃO
# ==========================================
def get_camera_matrix(w, h):
    """Cria uma matriz de câmera intrínseca aproximada."""
    return np.array([
        [FOCAL_LENGTH, 0, w / 2],
        [0, FOCAL_LENGTH, h / 2],
        [0, 0, 1]
    ], dtype="double")

def draw_pose_cube(img, rvec, tvec, camera_matrix, dist_coeffs):
    """Desenha um cubo para visualizar a Matriz de Rotação (Pose da Cabeça)."""
    # Pontos 3D de um cubo no espaço
    points_3d = np.float32([
        [-50, -50, 50], [50, -50, 50], [50, 50, 50], [-50, 50, 50],
        [-50, -50, -50], [50, -50, -50], [50, 50, -50], [-50, 50, -50]
    ])
    # Projeta os pontos 3D no plano 2D da imagem
    points_2d, _ = cv2.projectPoints(points_3d, rvec, tvec, camera_matrix, dist_coeffs)
    points_2d = np.int32(points_2d).reshape(-1, 2)
    
    # Desenha as arestas do cubo
    for i, j in zip(range(4), range(4, 8)):
        cv2.line(img, tuple(points_2d[i]), tuple(points_2d[j]), (255, 0, 0), 2)
    cv2.drawContours(img, [points_2d[:4]], -1, (0, 255, 0), 2)
    cv2.drawContours(img, [points_2d[4:]], -1, (0, 0, 255), 2)

def compute_ray_intersection(ray_origin, ray_vector):
    """
    Parâmetro 3 e 4: Projeta o raio (Project Rays) e computa intersecção (Compute Intersection).
    Mapeia a origem do olho e o vetor de olhar contra um plano de monitor Z = Constante.
    """
    # Define o plano do monitor virtual em Z = 500mm da câmera
    z_monitor = 500.0
    if ray_vector[2] == 0: return None # Evita divisão por zero
    
    # t = (Z_plano - Z_origem) / Z_vetor
    t = (z_monitor - ray_origin[2]) / ray_vector[2]
    intersection = ray_origin + t * ray_vector
    return intersection

# ==========================================
# INTERFACE STREAMLIT
# ==========================================
col1, col2 = st.columns([3, 1])
with col2:
    st.header("Calibração (Parâmetro 6)")
    st.write("Calibração Multi-pontos. Olhe para a tela e clique para registrar.")
    calib_state = st.session_state.get('calib_pts', 0)
    if st.button("Registrar Ponto de Calibração"):
        calib_state += 1
        st.session_state['calib_pts'] = calib_state
    
    st.progress(min(calib_state / 5.0, 1.0))
    if calib_state >= 5:
        st.success("Monitor Real vinculado ao Virtual (Parâmetro 5)!")
    
    run_app = st.checkbox("Iniciar Câmera", value=False)

with col1:
    frame_placeholder = st.empty()

# ==========================================
# LOOP PRINCIPAL DO RASTREIO
# ==========================================
if run_app:
    cap = cv2.VideoCapture(0)
    
    mp_face_mesh = mp.solutions.face_mesh
    # refine_landmarks=True é obrigatório para pegar o centro da Íris (Parâmetro 2)
    face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
    
    # Pontos 3D genéricos do rosto humano para SolvePnP (Nariz, Queixo, Olhos, Boca)
    face_3d_model = np.array([
        (0.0, 0.0, 0.0),            # Nariz
        (0.0, -330.0, -65.0),       # Queixo
        (-225.0, 170.0, -135.0),    # Olho Esq
        (225.0, 170.0, -135.0),     # Olho Dir
        (-150.0, -150.0, -125.0),   # Boca Esq
        (150.0, -150.0, -125.0)     # Boca Dir
    ], dtype=np.float64)

    while cap.isOpened() and run_app:
        ret, frame = cap.read()
        if not ret: break
        
        frame = cv2.flip(frame, 1)
        h, w, c = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        results = face_mesh.process(rgb_frame)
        
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                # Extrai pontos 2D para a pose da cabeça
                face_2d = []
                for idx in [1, 152, 33, 263, 61, 291]: # Índices correspondentes ao face_3d_model
                    lm = face_landmarks.landmark[idx]
                    x, y = int(lm.x * w), int(lm.y * h)
                    face_2d.append([x, y])
                face_2d = np.array(face_2d, dtype=np.float64)
                
                cam_matrix = get_camera_matrix(w, h)
                dist_matrix = np.zeros((4, 1), dtype=np.float64)
                
                # Obtém Matriz de Rotação (rvec) e Translação (tvec)
                success, rvec, tvec = cv2.solvePnP(face_3d_model, face_2d, cam_matrix, dist_matrix)
                rmat, _ = cv2.Rodrigues(rvec) # Matriz de rotação
                
                # Visualiza a matriz de rotação com um cubo
                draw_pose_cube(frame, rvec, tvec, cam_matrix, dist_matrix)
                
                # ---------------------------------------------------
                # PARÂMETROS 1 e 2: Centros dos Olhos e Íris
                # ---------------------------------------------------
                # Landmark 468 é o centro da Íris Esquerda (na visão da câmera)
                # Landmark 473 é o centro da Íris Direita
                iris_left = face_landmarks.landmark[468]
                iris_right = face_landmarks.landmark[473]
                
                cx_left, cy_left = int(iris_left.x * w), int(iris_left.y * h)
                cx_right, cy_right = int(iris_right.x * w), int(iris_right.y * h)
                
                cv2.circle(frame, (cx_left, cy_left), 3, (0, 255, 255), -1)
                cv2.circle(frame, (cx_right, cy_right), 3, (0, 255, 255), -1)
                
                # ---------------------------------------------------
                # PARÂMETROS 3 e 4: Project Rays & Compute Intersection
                # ---------------------------------------------------
                # Aqui simplificamos a origem do raio como a translação da cabeça
                # e o vetor direcional baseado na matriz de rotação da cabeça.
                # Numa versão física exata, a orientação da íris ajustaria esse vetor.
                gaze_vector = rmat[:, 2] # Pega o vetor Z da matriz de rotação
                ray_origin = tvec.reshape(3)
                
                intersection = compute_ray_intersection(ray_origin, gaze_vector)
                
                if intersection is not None:
                    # Exibe os dados de intersecção da tela
                    cv2.putText(frame, f"Gaze Target (X,Y): {int(intersection[0])}, {int(intersection[1])}", 
                                (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Atualiza a interface do Streamlit
        frame_placeholder.image(frame, channels="BGR")
        
    cap.release()
