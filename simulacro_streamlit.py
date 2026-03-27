import time
import threading
import tempfile
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

import av
import cv2
import mediapipe as mp
import numpy as np
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from scipy.ndimage import gaussian_filter
from streamlit_webrtc import WebRtcMode, webrtc_streamer


st.set_page_config(page_title="Rastreamento Ocular no Streamlit", layout="wide")


LEFT_EYE_H = (33, 133)
RIGHT_EYE_H = (362, 263)
LEFT_EYE_V = (159, 145)
RIGHT_EYE_V = (386, 374)
LEFT_EAR_IDX = (33, 160, 158, 133, 153, 144)
RIGHT_EAR_IDX = (362, 385, 387, 263, 373, 380)
LEFT_IRIS = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]


@dataclass
class BlinkConfig:
    ear_threshold: float = 0.21
    min_blink_ms: int = 60
    max_blink_ms: int = 450
    double_blink_gap_ms: int = 700


class EyeTrackerProcessor:
    def __init__(self):
        self.lock = threading.Lock()
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.heatmap = None
        self.last_frame_shape = None
        self.gaze_point = None
        self.gaze_smooth = deque(maxlen=8)
        self.last_action = "Nenhuma"
        self.single_blinks = 0
        self.double_blinks = 0
        self.total_blinks = 0
        self.face_found = False
        self.blink_cfg = BlinkConfig()
        self.eye_closed = False
        self.eye_closed_since = None
        self.pending_single_ts = None
        self.calibration_center = None
        self.last_metrics = {
            "ear": 0.0,
            "gaze_x": 0.5,
            "gaze_y": 0.5,
            "timestamp": time.time(),
        }

    def reset(self):
        with self.lock:
            self.heatmap = None
            self.gaze_point = None
            self.gaze_smooth.clear()
            self.last_action = "Resetado"
            self.single_blinks = 0
            self.double_blinks = 0
            self.total_blinks = 0
            self.eye_closed = False
            self.eye_closed_since = None
            self.pending_single_ts = None
            self.calibration_center = None

    def calibrate(self):
        with self.lock:
            if self.gaze_point is not None:
                self.calibration_center = self.gaze_point
                self.last_action = "Calibrado"

    def get_snapshot(self):
        with self.lock:
            heatmap = None if self.heatmap is None else self.heatmap.copy()
            return {
                "heatmap": heatmap,
                "last_frame_shape": self.last_frame_shape,
                "gaze_point": self.gaze_point,
                "last_action": self.last_action,
                "single_blinks": self.single_blinks,
                "double_blinks": self.double_blinks,
                "total_blinks": self.total_blinks,
                "face_found": self.face_found,
                "metrics": dict(self.last_metrics),
            }

    @staticmethod
    def _pt(landmarks, idx, w, h):
        lm = landmarks[idx]
        return np.array([lm.x * w, lm.y * h], dtype=np.float32)

    @staticmethod
    def _dist(a, b):
        return float(np.linalg.norm(a - b))

    def _ear(self, landmarks, indices, w, h):
        p1 = self._pt(landmarks, indices[0], w, h)
        p2 = self._pt(landmarks, indices[1], w, h)
        p3 = self._pt(landmarks, indices[2], w, h)
        p4 = self._pt(landmarks, indices[3], w, h)
        p5 = self._pt(landmarks, indices[4], w, h)
        p6 = self._pt(landmarks, indices[5], w, h)
        vertical = self._dist(p2, p6) + self._dist(p3, p5)
        horizontal = 2.0 * self._dist(p1, p4)
        if horizontal <= 1e-6:
            return 0.0
        return vertical / horizontal

    def _iris_center(self, landmarks, iris_idx, w, h):
        pts = np.array([self._pt(landmarks, i, w, h) for i in iris_idx], dtype=np.float32)
        return np.mean(pts, axis=0)

    def _ratio(self, value, start, end):
        denom = end - start
        if abs(denom) < 1e-6:
            return 0.5
        return float(np.clip((value - start) / denom, 0.0, 1.0))

    def _estimate_gaze(self, landmarks, w, h):
        left_iris = self._iris_center(landmarks, LEFT_IRIS, w, h)
        right_iris = self._iris_center(landmarks, RIGHT_IRIS, w, h)

        l_left = self._pt(landmarks, LEFT_EYE_H[0], w, h)
        l_right = self._pt(landmarks, LEFT_EYE_H[1], w, h)
        r_left = self._pt(landmarks, RIGHT_EYE_H[0], w, h)
        r_right = self._pt(landmarks, RIGHT_EYE_H[1], w, h)

        l_up = self._pt(landmarks, LEFT_EYE_V[0], w, h)
        l_down = self._pt(landmarks, LEFT_EYE_V[1], w, h)
        r_up = self._pt(landmarks, RIGHT_EYE_V[0], w, h)
        r_down = self._pt(landmarks, RIGHT_EYE_V[1], w, h)

        gx_left = self._ratio(left_iris[0], l_left[0], l_right[0])
        gx_right = self._ratio(right_iris[0], r_right[0], r_left[0])
        gy_left = self._ratio(left_iris[1], l_up[1], l_down[1])
        gy_right = self._ratio(right_iris[1], r_up[1], r_down[1])

        gx = float(np.clip((gx_left + gx_right) / 2.0, 0.0, 1.0))
        gy = float(np.clip((gy_left + gy_right) / 2.0, 0.0, 1.0))

        px = int(gx * (w - 1))
        py = int(gy * (h - 1))
        return px, py, gx, gy, left_iris, right_iris

    def _update_blinks(self, ear_avg):
        now_ms = int(time.time() * 1000)
        cfg = self.blink_cfg

        if ear_avg < cfg.ear_threshold:
            if not self.eye_closed:
                self.eye_closed = True
                self.eye_closed_since = now_ms
            return

        if self.eye_closed:
            duration = now_ms - (self.eye_closed_since or now_ms)
            self.eye_closed = False
            self.eye_closed_since = None

            if cfg.min_blink_ms <= duration <= cfg.max_blink_ms:
                self.total_blinks += 1
                if self.pending_single_ts and (now_ms - self.pending_single_ts) <= cfg.double_blink_gap_ms:
                    self.double_blinks += 1
                    self.pending_single_ts = None
                    self.last_action = "Pisca dupla -> afastar"
                else:
                    self.pending_single_ts = now_ms

        if self.pending_single_ts and (now_ms - self.pending_single_ts) > cfg.double_blink_gap_ms:
            self.single_blinks += 1
            self.pending_single_ts = None
            self.last_action = "Pisca simples -> aproximar"

    def _draw_heatmap_overlay(self, frame):
        if self.heatmap is None:
            return frame

        hm = gaussian_filter(self.heatmap.astype(np.float32), sigma=15)
        if np.max(hm) <= 0:
            return frame

        hm = hm / np.max(hm)
        hm_u8 = np.uint8(np.clip(hm * 255, 0, 255))
        colored = cv2.applyColorMap(hm_u8, cv2.COLORMAP_JET)
        return cv2.addWeighted(frame, 0.72, colored, 0.28, 0)

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        annotated = img.copy()

        with self.lock:
            self.last_frame_shape = (h, w)
            if self.heatmap is None or self.heatmap.shape != (h, w):
                self.heatmap = np.zeros((h, w), dtype=np.float32)

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        face_found = bool(results.multi_face_landmarks)
        with self.lock:
            self.face_found = face_found

        if face_found:
            landmarks = results.multi_face_landmarks[0].landmark
            left_ear = self._ear(landmarks, LEFT_EAR_IDX, w, h)
            right_ear = self._ear(landmarks, RIGHT_EAR_IDX, w, h)
            ear_avg = (left_ear + right_ear) / 2.0

            px, py, gx, gy, left_iris, right_iris = self._estimate_gaze(landmarks, w, h)
            self.gaze_smooth.append((px, py))
            smooth_x = int(np.mean([p[0] for p in self.gaze_smooth]))
            smooth_y = int(np.mean([p[1] for p in self.gaze_smooth]))

            with self.lock:
                if self.calibration_center is not None:
                    dx = smooth_x - self.calibration_center[0]
                    dy = smooth_y - self.calibration_center[1]
                    smooth_x = int(np.clip(w / 2 + dx * 1.35, 0, w - 1))
                    smooth_y = int(np.clip(h / 2 + dy * 1.35, 0, h - 1))

                self.gaze_point = (smooth_x, smooth_y)
                y0 = max(0, smooth_y - 15)
                y1 = min(h, smooth_y + 16)
                x0 = max(0, smooth_x - 15)
                x1 = min(w, smooth_x + 16)
                self.heatmap[y0:y1, x0:x1] += 1.0
                self.last_metrics = {
                    "ear": float(ear_avg),
                    "gaze_x": float(gx),
                    "gaze_y": float(gy),
                    "timestamp": time.time(),
                }
                self._update_blinks(ear_avg)

            cv2.circle(annotated, (int(left_iris[0]), int(left_iris[1])), 4, (0, 255, 255), -1)
            cv2.circle(annotated, (int(right_iris[0]), int(right_iris[1])), 4, (0, 255, 255), -1)
            cv2.circle(annotated, (smooth_x, smooth_y), 10, (0, 0, 255), 2)
            cv2.line(annotated, (w // 2, h // 2), (smooth_x, smooth_y), (255, 200, 0), 2)

            status = [
                f"EAR: {ear_avg:.3f}",
                f"Gaze: ({smooth_x}, {smooth_y})",
                f"Singles: {self.single_blinks}",
                f"Duplos: {self.double_blinks}",
                f"Acao: {self.last_action}",
            ]
        else:
            status = [
                "Rosto nao detectado",
                f"Singles: {self.single_blinks}",
                f"Duplos: {self.double_blinks}",
                f"Acao: {self.last_action}",
            ]

        annotated = self._draw_heatmap_overlay(annotated)

        y = 28
        for text in status:
            cv2.putText(annotated, text, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
            cv2.putText(annotated, text, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            y += 28

        cv2.drawMarker(annotated, (w // 2, h // 2), (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
        return av.VideoFrame.from_ndarray(annotated, format="bgr24")


@st.cache_resource

def get_ice_servers():
    return {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}


def heatmap_to_bgr(snapshot):
    heatmap = snapshot.get("heatmap")
    if heatmap is None:
        return None

    hm = gaussian_filter(heatmap.astype(np.float32), sigma=20)
    if np.max(hm) <= 0:
        return None

    hm = hm / np.max(hm)
    hm_u8 = np.uint8(np.clip(hm * 255, 0, 255))
    colored = cv2.applyColorMap(hm_u8, cv2.COLORMAP_JET)

    gaze = snapshot.get("gaze_point")
    if gaze is not None:
        cv2.circle(colored, gaze, 10, (255, 255, 255), 2)

    return colored


def build_pdf(snapshot):
    colored = heatmap_to_bgr(snapshot)
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = tmp_pdf.name
    tmp_pdf.close()

    c = canvas.Canvas(pdf_path, pagesize=A4)
    page_w, page_h = A4
    c.setTitle("Relatorio de Rastreamento Ocular")

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, page_h - 40, "Relatorio de Rastreamento Ocular")
    c.setFont("Helvetica", 11)
    c.drawString(40, page_h - 65, f"Piscadas simples: {snapshot['single_blinks']}")
    c.drawString(40, page_h - 82, f"Piscadas duplas: {snapshot['double_blinks']}")
    c.drawString(40, page_h - 99, f"Piscadas totais: {snapshot['total_blinks']}")
    c.drawString(40, page_h - 116, f"Ultima acao: {snapshot['last_action']}")
    c.drawString(40, page_h - 133, f"Rosto detectado: {'Sim' if snapshot['face_found'] else 'Nao'}")

    metrics = snapshot.get("metrics", {})
    c.drawString(40, page_h - 150, f"EAR medio: {metrics.get('ear', 0.0):.4f}")
    c.drawString(40, page_h - 167, f"Gaze normalizado X: {metrics.get('gaze_x', 0.0):.4f}")
    c.drawString(40, page_h - 184, f"Gaze normalizado Y: {metrics.get('gaze_y', 0.0):.4f}")

    if colored is not None:
        tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img_path = tmp_img.name
        tmp_img.close()
        cv2.imwrite(img_path, colored)
        c.drawImage(ImageReader(img_path), 40, 120, width=520, height=390, preserveAspectRatio=True, mask='auto')

    c.showPage()
    c.save()
    return pdf_path


def main():
    st.title("Rastreamento ocular no Streamlit")
    st.caption("Versao adaptada para navegador, sem tkinter e sem cv2.imshow.")

    with st.expander("O que foi corrigido"):
        st.markdown(
            """
- O `SyntaxError` acontece porque havia texto solto depois de `selection_gui()` no fim do arquivo.
- `tkinter`, `cv2.imshow()` e `cv2.VideoCapture()` local nao sao a melhor base para Streamlit Cloud.
- Esta versao usa **WebRTC no navegador** para capturar webcam em tempo real.
- Para Streamlit Cloud, prefira **`opencv-python-headless`** em vez de `opencv-python`.
            """
        )

    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### Camera ao vivo")
        ctx = webrtc_streamer(
            key="eye-tracker",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=get_ice_servers(),
            media_stream_constraints={"video": True, "audio": False},
            video_processor_factory=EyeTrackerProcessor,
            async_processing=True,
        )

    with col2:
        st.markdown("### Controles")
        st.write("1. Clique em **START** abaixo da camera.")
        st.write("2. Autorize a webcam no navegador.")
        st.write("3. Olhe para a tela para alimentar o mapa de calor.")
        st.write("4. Pisca simples = aproximar | pisca dupla = afastar.")

        snapshot = None
        if ctx and ctx.video_processor:
            snapshot = ctx.video_processor.get_snapshot()

            c1, c2 = st.columns(2)
            if c1.button("Calibrar centro"):
                ctx.video_processor.calibrate()
                snapshot = ctx.video_processor.get_snapshot()
            if c2.button("Resetar"):
                ctx.video_processor.reset()
                snapshot = ctx.video_processor.get_snapshot()

            st.metric("Piscadas simples", snapshot["single_blinks"])
            st.metric("Piscadas duplas", snapshot["double_blinks"])
            st.metric("Piscadas totais", snapshot["total_blinks"])
            st.metric("EAR medio", f"{snapshot['metrics'].get('ear', 0.0):.3f}")
            st.write(f"**Ultima acao:** {snapshot['last_action']}")
            st.write(f"**Rosto detectado:** {'Sim' if snapshot['face_found'] else 'Nao'}")

            heatmap_img = heatmap_to_bgr(snapshot)
            if heatmap_img is not None:
                st.image(cv2.cvtColor(heatmap_img, cv2.COLOR_BGR2RGB), caption="Mapa de calor acumulado")

            if st.button("Gerar PDF do relatorio"):
                pdf_path = build_pdf(snapshot)
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "Baixar relatorio em PDF",
                        data=f.read(),
                        file_name="relatorio_rastreamento_ocular.pdf",
                        mime="application/pdf",
                    )
        else:
            st.info("Inicie a camera para habilitar calibracao, mapa de calor e PDF.")

    st.markdown("### Requerimentos")
    st.code(
        """streamlit
streamlit-webrtc
opencv-python-headless
numpy
mediapipe
scipy
av
reportlab""",
        language="text",
    )


if __name__ == "__main__":
    main()
