"""
sala3d_real_eyetracker.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sala 3D + rastreamento ocular REAL (detecção de pupila via OpenCV)
Sem MediaPipe — usa câmera IR / câmera de olho diretamente.

Arquitetura:
  Thread 1 → EyeTracker  (captura câmera, detecta pupila, calcula gaze)
  Thread 2 → GazeServer  (HTTP localhost:PORT serve JSON com x,y,blink_ts)
  Main     → Streamlit UI + HTML/JS 3D room que consome o servidor

Uso:
  pip install streamlit opencv-python numpy
  streamlit run sala3d_real_eyetracker.py

Controles da Sala 3D:
  Olhar para obra ~1s  → dwell-click seleciona
  1 piscar             → zoom in na obra em foco
  2 piscadas rápidas   → zoom out / afasta
  Botão Calibrar       → calibra centro do olhar
  Modo Mouse           → fallback automático se câmera falhar
"""

import streamlit as st
import streamlit.components.v1 as components
import cv2
import threading
import numpy as np
import json
import time
import math
import random
import socket
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# ════════════════════════════════════════════════════════════════
#  SHARED GAZE STATE  (thread-safe)
# ════════════════════════════════════════════════════════════════

_gaze = {
    "x": 0.5,          # normalized [0,1]
    "y": 0.5,          # normalized [0,1]
    "active": False,   # tracker running
    "quality": 0.0,    # 0..1
    "blink_ts": 0.0,   # unix timestamp of last detected blink (0 = none)
    "calibrated": False,
    "pupil_x": 320,    # raw pixel
    "pupil_y": 240,
    "sphere_cx": 320,
    "sphere_cy": 240,
}
_gaze_lock = threading.Lock()

def g_get():
    with _gaze_lock:
        return dict(_gaze)

def g_set(**kw):
    with _gaze_lock:
        _gaze.update(kw)


# ════════════════════════════════════════════════════════════════
#  BLINK DETECTOR  (based on pupil detection failure runs)
# ════════════════════════════════════════════════════════════════

class BlinkDetector:
    """
    Detects blinks by counting consecutive frames where no pupil is found.
    A "blink" is: min_frames <= missing_run <= max_frames
    """
    def __init__(self, min_frames: int = 2, max_frames: int = 14):
        self.mn = min_frames
        self.mx = max_frames
        self._count = 0  # current no-detect run

    def update(self, pupil_found: bool) -> bool:
        """Call every processed frame. Returns True exactly once per blink."""
        if not pupil_found:
            self._count += 1
            return False
        run, self._count = self._count, 0
        return self.mn <= run <= self.mx


# ════════════════════════════════════════════════════════════════
#  GAZE CALIBRATOR
# ════════════════════════════════════════════════════════════════

class GazeCalibrator:
    """
    Stores the gaze direction when user is looking at screen center.
    Future directions are offset from this reference.
    """
    def __init__(self, gain_x: float = 2.4, gain_y: float = 2.0):
        self._center: np.ndarray | None = None
        self.gx = gain_x
        self.gy = gain_y

    def calibrate(self, gaze_dir: np.ndarray):
        self._center = gaze_dir.copy()

    def to_screen(self, gaze_dir: np.ndarray):
        if self._center is None:
            x = 0.5 + gaze_dir[0] * self.gx
            y = 0.5 - gaze_dir[1] * self.gy
        else:
            x = 0.5 + (gaze_dir[0] - self._center[0]) * self.gx
            y = 0.5 - (gaze_dir[1] - self._center[1]) * self.gy
        return float(np.clip(x, 0.02, 0.98)), float(np.clip(y, 0.02, 0.98))

    @property
    def is_calibrated(self):
        return self._center is not None


# ════════════════════════════════════════════════════════════════
#  EYE TRACKER CLASS
# ════════════════════════════════════════════════════════════════

class EyeTracker:
    """
    Full pupil-tracking pipeline (adapted from provided code).
    Runs in a background thread; pushes results to shared gaze state.
    """

    def __init__(self, camera_index: int = 0, flip_vertical: bool = True,
                 show_debug: bool = False):
        self.cam_idx = camera_index
        self.flip_v = flip_vertical
        self.debug = show_debug

        # Running state
        self._running = False
        self._thread: threading.Thread | None = None

        # Tracking accumulators
        self._ray_lines: list = []
        self._model_centers: list = []
        self._stored_isects: list = []
        self._max_rays = 100
        self._max_isects = 1500
        self._prev_sphere_2d = (320, 240)
        self._sphere_locked = False
        self._locked_sphere_2d = (320, 240)

        # 3D gaze state
        self._last_gaze_dir: np.ndarray | None = None
        self._last_sphere_3d: np.ndarray | None = None
        self._calib_sphere_3d: np.ndarray | None = None

        self.calibrator = GazeCalibrator()
        self.blink_det = BlinkDetector()

    # ── start / stop ──────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def calibrate_center(self):
        """Call when user is looking at the center of the screen."""
        if self._last_gaze_dir is not None:
            self.calibrator.calibrate(self._last_gaze_dir)
        if self._last_sphere_3d is not None:
            self._calib_sphere_3d = self._last_sphere_3d.copy()
        self._sphere_locked = True
        self._locked_sphere_2d = self._prev_sphere_2d
        g_set(calibrated=True)

    # ── image utilities ───────────────────────────────────────

    @staticmethod
    def _crop(image, w=640, h=480):
        ch, cw = image.shape[:2]
        r = w / h
        if cw / ch > r:
            nw = int(r * ch)
            off = (cw - nw) // 2
            img = image[:, off:off + nw]
        else:
            nh = int(cw / r)
            off = (ch - nh) // 2
            img = image[off:off + nh, :]
        return cv2.resize(img, (w, h))

    @staticmethod
    def _thresh(gray, darkest, added):
        _, t = cv2.threshold(gray, darkest + added, 255, cv2.THRESH_BINARY_INV)
        return t

    @staticmethod
    def _darkest_area(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ignore, skip, area, iskip = 20, 10, 20, 5
        min_sum = float('inf')
        pt = None
        for y in range(ignore, gray.shape[0] - ignore, skip):
            for x in range(ignore, gray.shape[1] - ignore, skip):
                s = n = 0
                for dy in range(0, area, iskip):
                    if y + dy >= gray.shape[0]: break
                    for dx in range(0, area, iskip):
                        if x + dx >= gray.shape[1]: break
                        s += gray[y + dy][x + dx]; n += 1
                if s < min_sum and n > 0:
                    min_sum, pt = s, (x + area // 2, y + area // 2)
        return pt

    @staticmethod
    def _mask_square(image, center, size):
        x, y = center; h = size // 2
        mask = np.zeros_like(image)
        mask[max(0, y - h):min(image.shape[0], y + h),
             max(0, x - h):min(image.shape[1], x + h)] = 255
        return cv2.bitwise_and(image, mask)

    @staticmethod
    def _filter_largest(contours, pix=1000, ratio=3):
        best, ba = None, 0
        for c in contours:
            area = cv2.contourArea(c)
            if area >= pix:
                bx, by, bw, bh = cv2.boundingRect(c)
                if max(bw / (bh or 1), bh / (bw or 1)) <= ratio and area > ba:
                    ba, best = area, c
        return [best] if best is not None else []

    @staticmethod
    def _optimize_contours(contours, image):
        if not contours:
            return contours
        pts = np.concatenate(contours[0], axis=0)
        sp = max(1, len(pts) // 25)
        cen = np.mean(pts, axis=0)
        out = []
        for i in range(len(pts)):
            cur = pts[i]
            prev = pts[i - sp] if i - sp >= 0 else pts[-sp]
            nxt  = pts[i + sp] if i + sp < len(pts) else pts[sp]
            v1, v2 = prev - cur, nxt - cur
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-9 or n2 < 1e-9:
                continue
            with np.errstate(invalid='ignore'):
                ang = np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1))
            if np.dot(cen - cur, (v1 + v2) / 2) >= np.cos(np.radians(60)):
                out.append(cur)
        return np.array(out, dtype=np.int32).reshape((-1, 1, 2)) if out else None

    @staticmethod
    def _check_contour_pixels(contour, shape):
        if len(contour) < 5:
            return [0, 0, None]
        cm = np.zeros(shape, np.uint8)
        cv2.drawContours(cm, [contour], -1, 255, 1)
        ell = cv2.fitEllipse(contour)
        thick = np.zeros(shape, np.uint8); cv2.ellipse(thick, ell, 255, 10)
        thin  = np.zeros(shape, np.uint8); cv2.ellipse(thin, ell, 255, 4)
        ov_t = cv2.bitwise_and(cm, thick)
        ov_n = cv2.bitwise_and(cm, thin)
        tot  = np.sum(cm > 0)
        return [np.sum(ov_t > 0), np.sum(ov_n > 0) / (tot or 1), ov_n]

    @staticmethod
    def _ellipse_goodness(binary, contour):
        if len(contour) < 5:
            return [0, 0, 0]
        ell = cv2.fitEllipse(contour)
        mask = np.zeros_like(binary)
        cv2.ellipse(mask, ell, 255, -1)
        area = np.sum(mask == 255)
        covered = np.sum((binary == 255) & (mask == 255))
        return [covered / (area or 1), 0,
                min(ell[1][1] / (ell[1][0] or 1), ell[1][0] / (ell[1][1] or 1))]

    # ── intersection computation ──────────────────────────────

    @staticmethod
    def _find_intersection(e1, e2):
        (cx1, cy1), (_, ma1), a1 = e1
        (cx2, cy2), (_, ma2), a2 = e2
        a1r, a2r = np.deg2rad(a1), np.deg2rad(a2)
        dx1, dy1 = (ma1 / 2) * np.cos(a1r), (ma1 / 2) * np.sin(a1r)
        dx2, dy2 = (ma2 / 2) * np.cos(a2r), (ma2 / 2) * np.sin(a2r)
        A = np.array([[dx1, -dx2], [dy1, -dy2]])
        B = np.array([cx2 - cx1, cy2 - cy1])
        if abs(np.linalg.det(A)) < 1e-9:
            return None
        t1, _ = np.linalg.solve(A, B)
        return (int(cx1 + t1 * dx1), int(cy1 + t1 * dy1))

    def _compute_avg_intersection(self, frame, rays, N=5):
        if len(rays) < 2:
            return None
        h, w = frame.shape[:2]
        sel = random.sample(rays, min(N, len(rays)))
        for i in range(len(sel) - 1):
            l1, l2 = sel[i], sel[i + 1]
            if abs(l1[2] - l2[2]) >= 2:
                pt = self._find_intersection(l1, l2)
                if pt and 0 <= pt[0] < w and 0 <= pt[1] < h:
                    self._stored_isects.append(pt)
        if len(self._stored_isects) > self._max_isects:
            self._stored_isects = self._stored_isects[-self._max_isects:]
        if not self._stored_isects:
            return None
        return (int(np.mean([p[0] for p in self._stored_isects])),
                int(np.mean([p[1] for p in self._stored_isects])))

    def _update_sphere_avg(self, pt, N=200):
        self._model_centers.append(pt)
        if len(self._model_centers) > N:
            self._model_centers.pop(0)
        return (int(np.mean([p[0] for p in self._model_centers])),
                int(np.mean([p[1] for p in self._model_centers])))

    # ── gaze vector ───────────────────────────────────────────

    def _compute_gaze_vector(self, px, py, cx, cy, sw=640, sh=480):
        fov = 45.0
        aspect = sw / sh
        far = 100.0
        cam = np.array([0., 0., 3.])
        hfar = np.tan(np.radians(fov / 2)) * far
        wfar = hfar * aspect
        ndc_x = 2. * px / sw - 1.
        ndc_y = 1. - 2. * py / sh
        fpt = np.array([ndc_x * wfar, ndc_y * hfar, cam[2] - far])
        rd  = -(fpt - cam); rd /= np.linalg.norm(rd)

        r = 1. / 1.05
        sc = np.array([(cx / sw) * 2. - 1., 1. - (cy / sh) * 2., 0.]) * 1.5

        L = cam - sc
        a = np.dot(rd, rd); b = 2 * np.dot(rd, L); c = np.dot(L, L) - r**2
        disc = b**2 - 4 * a * c

        if disc < 0:
            t = -np.dot(rd, L) / (np.dot(rd, rd) or 1e-9)
        else:
            sq = np.sqrt(disc)
            t1, t2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
            cands = [v for v in [t1, t2] if v > 0]
            if not cands:
                return None, None
            t = min(cands)

        ipt   = cam + t * rd
        local = ipt - sc
        tgt   = local / np.linalg.norm(local)
        fwd   = np.array([0., 0., r]); fwd /= np.linalg.norm(fwd)

        ax = np.cross(fwd, tgt)
        an = np.linalg.norm(ax)
        if an < 1e-6:
            return sc, fwd

        ax /= an
        ang = np.arccos(np.clip(np.dot(fwd, tgt), -1, 1))
        c_, s_ = np.cos(ang), np.sin(ang)
        t_ = 1 - c_
        vx, vy, vz = ax
        R = np.array([
            [t_*vx*vx+c_,      t_*vx*vy-s_*vz, t_*vx*vz+s_*vy],
            [t_*vx*vy+s_*vz,   t_*vy*vy+c_,    t_*vy*vz-s_*vx],
            [t_*vx*vz-s_*vy,   t_*vy*vz+s_*vx, t_*vz*vz+c_   ]
        ])
        gaze = R @ np.array([0., 0., r])
        gaze /= np.linalg.norm(gaze)

        self._last_gaze_dir = gaze.copy()
        self._last_sphere_3d = sc.copy()
        out_sc = self._calib_sphere_3d if self._calib_sphere_3d is not None else sc
        return out_sc, gaze

    # ── single-frame processing ───────────────────────────────

    def _process_eye_frame(self, frame):
        """
        Returns (ellipse, pupil_cx, pupil_cy, sphere_center_2d) or None.
        """
        frame = self._crop(frame)
        dp = self._darkest_area(frame)
        if dp is None:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        dv = int(gray[dp[1], dp[0]])

        imgs = [
            self._mask_square(self._thresh(gray, dv,  5), dp, 250),
            self._mask_square(self._thresh(gray, dv, 15), dp, 250),
            self._mask_square(self._thresh(gray, dv, 25), dp, 250),
        ]

        k = np.ones((5, 5), np.uint8)
        best_g, best_cont, best_ell = 0, None, None
        cx = cy = None

        for img in imgs:
            dil = cv2.dilate(img, k, iterations=2)
            conts, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            rc = self._filter_largest(conts)
            if not rc or len(rc[0]) <= 5:
                continue
            g  = self._ellipse_goodness(dil, rc[0])
            tp = self._check_contour_pixels(rc[0], dil.shape)
            fg = g[0] * tp[0] * tp[0] * tp[1]
            if fg > best_g:
                best_g, best_cont = fg, rc[0]
                ell = cv2.fitEllipse(rc[0])
                cx, cy = int(ell[0][0]), int(ell[0][1])
                best_ell = ell

        if best_cont is None or cx is None:
            return None

        # Refine with angle-optimized contours
        opt = self._optimize_contours([best_cont], gray)
        if opt is not None and len(opt) >= 5:
            try:
                best_ell = cv2.fitEllipse(opt)
                cx, cy = int(best_ell[0][0]), int(best_ell[0][1])
            except Exception:
                pass

        # Accumulate rays
        self._ray_lines.append(best_ell)
        if len(self._ray_lines) > self._max_rays:
            self._ray_lines = self._ray_lines[-self._max_rays:]

        # Sphere center (intersection of rays)
        mc = self._compute_avg_intersection(frame, self._ray_lines)

        if not self._sphere_locked:
            if mc is not None:
                sph_avg = self._update_sphere_avg(mc)
                self._prev_sphere_2d = sph_avg
                self._locked_sphere_2d = sph_avg
            else:
                sph_avg = self._prev_sphere_2d
        else:
            sph_avg = self._locked_sphere_2d

        return best_ell, cx, cy, sph_avg

    # ── debug overlay ─────────────────────────────────────────

    def _draw_debug(self, frame, ell, cx, cy, sph):
        if ell is not None:
            cv2.ellipse(frame, ell, (20, 255, 255), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 255, 255), -1)
        cv2.circle(frame, sph, 200, (255, 50, 50), 2)
        cv2.circle(frame, sph, 8, (255, 255, 0), -1)
        if ell is not None:
            cv2.line(frame, sph, (cx, cy), (255, 150, 50), 2)
            dx, dy = cx - sph[0], cy - sph[1]
            ext = (int(sph[0] + 2*dx), int(sph[1] + 2*dy))
            cv2.line(frame, (cx, cy), ext, (200, 255, 0), 3)
        cv2.imshow("Eye Tracker – Debug", frame)

    # ── main loop ─────────────────────────────────────────────

    def _run_loop(self):
        self._running = True
        cap = cv2.VideoCapture(self.cam_idx)
        if not cap.isOpened():
            g_set(active=False)
            self._running = False
            return

        g_set(active=True)

        while self._running:
            ret, frame = cap.read()
            if not ret:
                break

            if self.flip_v:
                frame = cv2.flip(frame, 0)

            result = self._process_eye_frame(frame)

            if result is not None:
                ell, px, py, sph = result
                _, gaze_dir = self._compute_gaze_vector(px, py, sph[0], sph[1])

                if gaze_dir is not None:
                    sx, sy = self.calibrator.to_screen(gaze_dir)
                    found = True
                    g_set(x=sx, y=sy, quality=1.0,
                          pupil_x=px, pupil_y=py,
                          sphere_cx=sph[0], sphere_cy=sph[1])
                else:
                    found = False

                if self.debug:
                    self._draw_debug(frame.copy(), ell, px, py, sph)
            else:
                found = False

            # Blink detection
            if self.blink_det.update(found):
                g_set(blink_ts=time.time())

            if not found:
                g_set(quality=0.0)

            if self.debug and cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        if self.debug:
            cv2.destroyAllWindows()
        g_set(active=False)
        self._running = False


# ════════════════════════════════════════════════════════════════
#  GAZE HTTP SERVER
# ════════════════════════════════════════════════════════════════

_tracker_instance: EyeTracker | None = None
_http_server: HTTPServer | None = None


class _GazeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = g_get()
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            cmd = json.loads(body)
            action = cmd.get('action', '')
            if action == 'calibrate' and _tracker_instance:
                _tracker_instance.calibrate_center()
            elif action == 'lock_sphere' and _tracker_instance:
                _tracker_instance._sphere_locked = True
                _tracker_instance._locked_sphere_2d = _tracker_instance._prev_sphere_2d
        except Exception:
            pass
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, *_):
        pass


def _find_free_port(start: int = 8765) -> int:
    for p in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', p)) != 0:
                return p
    return start


def _start_server(port: int):
    global _http_server
    try:
        _http_server = HTTPServer(('localhost', port), _GazeHandler)
        _http_server.serve_forever()
    except OSError:
        pass


def ensure_services(camera_index: int = 0, show_debug: bool = False) -> int:
    """
    Start eye tracker + HTTP server once per Streamlit session.
    Returns the port being served.
    """
    global _tracker_instance

    if 'gaze_port' not in st.session_state:
        port = _find_free_port(8765)
        st.session_state['gaze_port'] = port

        _tracker_instance = EyeTracker(camera_index=camera_index,
                                        show_debug=show_debug)
        _tracker_instance.start()

        threading.Thread(target=_start_server, args=(port,), daemon=True).start()
        time.sleep(0.4)

    return st.session_state['gaze_port']


# ════════════════════════════════════════════════════════════════
#  HTML / JS  3D ROOM
# ════════════════════════════════════════════════════════════════

def build_html(port: int) -> str:
    return f"""
<div id="root">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=IBM+Plex+Mono:wght@400;600&display=swap');
  :root{{
    --bg:#050c18;--text:#ddeeff;--muted:#6a8aac;
    --ok:#2ecc71;--warn:#e67e22;--danger:#e74c3c;
    --cyan:#41b3e8;--violet:#9b59b6;--gold:#f0c040;
    font-family:'Syne',system-ui,sans-serif;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  #root{{width:100%;min-height:1210px;color:var(--text);padding:16px;border-radius:20px;
    background:radial-gradient(ellipse 70% 35% at 15% 0%,rgba(65,179,232,.07) 0%,transparent 55%),
               radial-gradient(ellipse 55% 35% at 85% 100%,rgba(155,89,182,.07) 0%,transparent 55%),
               linear-gradient(180deg,#050c18 0%,#020709 100%);
    border:1px solid rgba(255,255,255,.04);overflow:hidden;}}
  /* topbar */
  .topbar{{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:14px;flex-wrap:wrap}}
  .headline h2{{font-size:22px;font-weight:800;letter-spacing:-.3px}}
  .headline p{{margin-top:4px;color:var(--muted);font-size:12.5px;line-height:1.5;max-width:740px}}
  .ctrls{{display:flex;flex-wrap:wrap;gap:7px}}
  .btn{{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:var(--text);
    padding:8px 13px;border-radius:11px;font-weight:700;font-size:12px;cursor:pointer;
    transition:.15s;font-family:'Syne',sans-serif;}}
  .btn:hover{{transform:translateY(-1px);border-color:rgba(65,179,232,.5);background:rgba(65,179,232,.1)}}
  .btn.p{{background:rgba(65,179,232,.16);border-color:rgba(65,179,232,.4)}}
  .btn.w{{background:rgba(230,126,34,.14);border-color:rgba(230,126,34,.4)}}
  .btn.v{{background:rgba(155,89,182,.14);border-color:rgba(155,89,182,.35)}}
  .btn.d{{background:rgba(231,76,60,.14);border-color:rgba(231,76,60,.35)}}
  /* layout */
  .layout{{display:grid;grid-template-columns:minmax(0,1.72fr) 320px;gap:13px;min-height:980px}}
  /* scene */
  .scene{{border:1px solid rgba(255,255,255,.06);border-radius:18px;overflow:hidden;
    position:relative;min-height:920px;box-shadow:0 24px 60px rgba(0,0,0,.35)}}
  #sh{{position:absolute;inset:0}}
  #room,#heat,#rev{{position:absolute;inset:0;width:100%;height:100%;display:block}}
  #heat,#rev{{pointer-events:none}}
  /* gaze cursor */
  #cur{{position:absolute;width:24px;height:24px;border:2px solid rgba(255,255,255,.9);border-radius:50%;
    box-shadow:0 0 0 5px rgba(65,179,232,.12),0 0 18px rgba(65,179,232,.28);
    transform:translate(-50%,-50%);pointer-events:none;z-index:6;left:50%;top:50%;
    transition:width .1s,height .1s,border-color .1s}}
  #cur::after{{content:"";position:absolute;inset:4px;border-radius:50%;background:rgba(255,255,255,.78)}}
  /* chips */
  .chip{{position:absolute;z-index:7;display:inline-flex;align-items:center;gap:6px;
    padding:7px 11px;border-radius:999px;background:rgba(5,12,24,.82);
    border:1px solid rgba(255,255,255,.07);color:var(--muted);font-size:11.5px;backdrop-filter:blur(12px)}}
  .chip strong{{color:var(--text)}}
  #stChip{{top:13px;left:13px}}
  #mdChip{{top:13px;left:178px}}
  #blChip{{top:13px;left:312px}}
  .dot{{width:8px;height:8px;border-radius:50%;background:var(--danger);box-shadow:0 0 12px rgba(231,76,60,.4)}}
  .dot.on{{background:var(--ok);box-shadow:0 0 12px rgba(46,204,113,.4)}}
  /* dwell meter */
  .meter{{position:absolute;top:13px;right:13px;z-index:7;width:190px;padding:9px 11px;
    border-radius:13px;background:rgba(5,12,24,.82);border:1px solid rgba(255,255,255,.07)}}
  .meter .lbl{{font-size:10.5px;color:var(--muted);margin-bottom:5px;font-family:'IBM Plex Mono',monospace}}
  .bar{{width:100%;height:7px;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden}}
  .bar>div{{width:0%;height:100%;border-radius:999px;background:linear-gradient(90deg,#41b3e8,#9b59b6);transition:width .04s}}
  /* blink flash */
  #bflash{{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);z-index:8;
    padding:7px 15px;border-radius:999px;background:rgba(5,12,24,.88);
    border:1px solid rgba(65,179,232,.3);font-size:11.5px;color:var(--muted);
    font-family:'IBM Plex Mono',monospace;opacity:0;transition:opacity .25s}}
  #bflash.show{{opacity:1}}
  /* pupil overlay info */
  #pnote{{position:absolute;left:13px;bottom:13px;z-index:7;max-width:62%;
    padding:8px 12px;border-radius:11px;background:rgba(5,12,24,.88);
    border:1px solid rgba(255,255,255,.06);color:var(--muted);font-size:11.5px;line-height:1.4}}
  /* quality ring */
  #qring{{position:absolute;bottom:13px;right:13px;z-index:7;width:54px;height:54px}}
  /* sidebar */
  .sidebar{{display:flex;flex-direction:column;gap:11px}}
  .card{{background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.065);
    border-radius:15px;padding:13px}}
  .card h3{{font-size:11.5px;font-weight:700;color:var(--muted);text-transform:uppercase;
    letter-spacing:.6px;margin-bottom:9px}}
  /* stats */
  .sg{{display:grid;grid-template-columns:1fr 1fr;gap:7px}}
  .st{{background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.055);border-radius:11px;padding:9px}}
  .st .k{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}}
  .st .v{{font-size:18px;font-weight:800;font-variant-numeric:tabular-nums}}
  .ml{{display:flex;justify-content:space-between;gap:6px;border-bottom:1px solid rgba(255,255,255,.04);
    padding:6px 0;color:var(--muted);font-size:11.5px}}
  .ml:last-child{{border-bottom:none}}
  .ml strong{{color:var(--text);font-size:11.5px}}
  /* selected art */
  #sTitle{{font-size:16px;font-weight:800;line-height:1.2;margin-bottom:3px}}
  #sArtist{{color:var(--cyan);font-size:11.5px;font-weight:700;margin-bottom:7px}}
  #sDesc{{color:var(--muted);line-height:1.5;font-size:12px}}
  /* blink guide */
  .bg{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:3px}}
  .bc{{background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.055);
    border-radius:10px;padding:8px;text-align:center}}
  .bc .ic{{font-size:16px;margin-bottom:2px}}
  .bc .bl{{font-size:11px;font-weight:700;margin-bottom:1px}}
  .bc .ds{{font-size:10.5px;color:var(--muted)}}
  /* artwork list */
  #aList{{display:grid;gap:7px;max-height:230px;overflow:auto}}
  #aList::-webkit-scrollbar{{width:3px}}
  #aList::-webkit-scrollbar-thumb{{background:rgba(255,255,255,.08);border-radius:3px}}
  .ar{{display:grid;grid-template-columns:11px 1fr auto;gap:7px;align-items:center;
    background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.055);
    border-radius:11px;padding:9px;cursor:pointer;transition:.13s}}
  .ar:hover{{border-color:rgba(65,179,232,.28);background:rgba(65,179,232,.05)}}
  .ab{{width:11px;height:11px;border-radius:50%}}
  .at{{font-size:12.5px;font-weight:700;margin-bottom:1px}}
  .as{{color:var(--muted);font-size:10.5px}}
  .badge{{font-size:9.5px;font-weight:700;color:#c5e3f7;background:rgba(65,179,232,.1);
    border:1px solid rgba(65,179,232,.18);padding:3px 7px;border-radius:999px;white-space:nowrap}}
  /* log */
  #log{{min-height:90px;max-height:140px;overflow:auto;border-radius:9px;padding:7px;
    background:rgba(2,5,12,.7);border:1px solid rgba(255,255,255,.05);
    color:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:10.5px;line-height:1.4;white-space:pre-wrap}}
  #log::-webkit-scrollbar{{width:2px}}
  #log::-webkit-scrollbar-thumb{{background:rgba(255,255,255,.08)}}
  .sn{{color:var(--muted);font-size:11px;line-height:1.4;margin-top:6px}}
  /* connection badge */
  #connBadge{{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;
    border-radius:999px;font-size:10.5px;font-family:'IBM Plex Mono',monospace;
    border:1px solid rgba(255,255,255,.08);color:var(--muted)}}
  #connBadge.conn{{border-color:rgba(46,204,113,.3);color:var(--ok)}}
  #connBadge.disc{{border-color:rgba(231,76,60,.3);color:var(--danger)}}
  /* pupil viz mini canvas */
  #pupilCanvas{{width:100%;aspect-ratio:4/3;border-radius:11px;
    background:#020709;border:1px solid rgba(255,255,255,.06);display:block}}
</style>

<!-- TOPBAR -->
<div class="topbar">
  <div class="headline">
    <h2>🔬 Sala 3D · Rastreamento Ocular Real</h2>
    <p>Detecção de pupila via OpenCV · <strong>1 piscar</strong> = zoom · <strong>2 piscadas rápidas</strong> = afasta · olhar ~1s = seleciona obra</p>
  </div>
  <div class="ctrls">
    <span id="connBadge" class="disc">⬤ desconectado</span>
    <button class="btn p" id="btnCal">⊕ Calibrar centro</button>
    <button class="btn w" id="btnLock">⊙ Travar esfera</button>
    <button class="btn v" id="btnHeat">⬡ Limpar mapa</button>
    <button class="btn"   id="btnPdf">↓ PDF</button>
    <button class="btn d" id="btnMouse">🖱 Forçar mouse</button>
  </div>
</div>

<!-- LAYOUT -->
<div class="layout">

  <!-- SCENE -->
  <div class="scene">
    <div id="sh">
      <canvas id="room"></canvas>
      <canvas id="heat"></canvas>
      <canvas id="rev"></canvas>
      <div id="cur"></div>
      <div class="chip" id="stChip"><span id="stDot" class="dot"></span><span id="stTxt">Aguardando</span></div>
      <div class="chip" id="mdChip">Modo: <strong id="mdTxt">Mouse</strong></div>
      <div class="chip" id="blChip">👁 <strong id="blTxt">Pronto</strong></div>
      <div class="meter"><div class="lbl">Dwell-click</div><div class="bar"><div id="dwFill"></div></div></div>
      <div id="bflash">👁 blink</div>
      <div id="pnote">Câmera de olho conectando na porta {port}… Ou use o mouse como fallback.</div>
      <svg id="qring" viewBox="0 0 54 54">
        <circle cx="27" cy="27" r="22" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="4"/>
        <circle id="qArc" cx="27" cy="27" r="22" fill="none" stroke="#41b3e8" stroke-width="4"
          stroke-linecap="round" stroke-dasharray="138.2" stroke-dashoffset="138.2"
          transform="rotate(-90 27 27)"/>
        <text x="27" y="32" text-anchor="middle" fill="#ddeeff" font-size="11" font-weight="700"
          font-family="IBM Plex Mono,monospace" id="qTxt">0%</text>
      </svg>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">

    <div class="card">
      <h3>Visualização da pupila</h3>
      <canvas id="pupilCanvas"></canvas>
      <div class="sn" style="margin-top:6px">Pupila detectada em tempo real pela câmera de olho</div>
    </div>

    <div class="card">
      <h3>Métricas</h3>
      <div class="sg">
        <div class="st"><div class="k">Tempo</div><div class="v" id="sTime">00:00</div></div>
        <div class="st"><div class="k">Fixações</div><div class="v" id="sFix">0</div></div>
        <div class="st"><div class="k">Amostras</div><div class="v" id="sPts">0</div></div>
        <div class="st"><div class="k">Obras vistas</div><div class="v" id="sArt">0</div></div>
      </div>
      <div class="ml"><span>Qualidade</span><strong id="sQ">—</strong></div>
      <div class="ml"><span>Hover atual</span><strong id="sHov">—</strong></div>
      <div class="ml"><span>Calibração</span><strong id="sCal">Pendente</strong></div>
      <div class="ml"><span>Zoom</span><strong id="sZoom">Normal</strong></div>
      <div class="ml"><span>Pupila (px)</span><strong id="sPupil">—</strong></div>
    </div>

    <div class="card">
      <h3>Obra em foco</h3>
      <div id="sTitle">Nenhuma obra selecionada</div>
      <div id="sArtist">Olhe ~1s ou pisque 1× para zoom</div>
      <div id="sDesc">A ficha aparece aqui após dwell ou blink. 2 piscadas rápidas afastam.</div>
    </div>

    <div class="card">
      <h3>Guia de blinks</h3>
      <div class="bg">
        <div class="bc"><div class="ic">😉</div><div class="bl">1 piscar</div><div class="ds">Zoom na obra</div></div>
        <div class="bc"><div class="ic">😮</div><div class="bl">2 piscadas rápidas</div><div class="ds">Afasta zoom</div></div>
      </div>
    </div>

    <div class="card">
      <h3>Obras da sala</h3>
      <div id="aList"></div>
    </div>

    <div class="card">
      <h3>Log</h3>
      <div id="log">Inicializando…</div>
    </div>

  </div>
</div>

<script>
(function(){{
'use strict';

// ─── DOM ───────────────────────────────────────────────────
const roomC   = document.getElementById('room');
const heatC   = document.getElementById('heat');
const revC    = document.getElementById('rev');
const scene   = document.querySelector('.scene');
const cur     = document.getElementById('cur');
const dwFill  = document.getElementById('dwFill');
const stDot   = document.getElementById('stDot');
const stTxt   = document.getElementById('stTxt');
const mdTxt   = document.getElementById('mdTxt');
const blTxt   = document.getElementById('blTxt');
const bflash  = document.getElementById('bflash');
const pnote   = document.getElementById('pnote');
const qArc    = document.getElementById('qArc');
const qTxt    = document.getElementById('qTxt');
const connBadge = document.getElementById('connBadge');
const sTime   = document.getElementById('sTime');
const sFix    = document.getElementById('sFix');
const sPts    = document.getElementById('sPts');
const sArt    = document.getElementById('sArt');
const sQ      = document.getElementById('sQ');
const sHov    = document.getElementById('sHov');
const sCal    = document.getElementById('sCal');
const sZoom   = document.getElementById('sZoom');
const sPupil  = document.getElementById('sPupil');
const selTitle= document.getElementById('sTitle');
const selArtist=document.getElementById('sArtist');
const selDesc = document.getElementById('sDesc');
const aList   = document.getElementById('aList');
const logBox  = document.getElementById('log');
const pupilC  = document.getElementById('pupilCanvas');
const pupilCtx= pupilC.getContext('2d');

const ctx   = roomC.getContext('2d');
const heatX = heatC.getContext('2d');
const revX  = revC.getContext('2d');

const PORT  = {port};
const API   = 'http://localhost:' + PORT;

// ─── UTILS ──────────────────────────────────────────────────
const clamp = (v,a,b) => Math.min(b,Math.max(a,v));
const lerp  = (a,b,t) => a+(b-a)*t;

function log(m){{
  const l='['+new Date().toLocaleTimeString()+'] '+m;
  logBox.textContent += '\\n'+l;
  logBox.scrollTop=logBox.scrollHeight;
}}
logBox.textContent='Sala carregada.';
window.addEventListener('error', e => log('ERR: '+(e.message||'?')));

// ─── STATE ──────────────────────────────────────────────────
const state = {{
  running:false, usingMouse:true,
  startedAt:null,
  sampleMs:80, lastSampleTs:0,
  hoverStart:0, dwellMs:1100,
  hoveredId:null, selectedId:null,
  fixations:0, inFix:false, stableFor:0, lastPx:null,
  heatPts:[], revPts:[], selections:[],
  seenIds:new Set(),
  // blink single/double
  lastBlinkTs:0, prevBlinkTs:0,
  pendingBlink:false, blinkTimer:null,
  // zoom
  zoom:{{ active:false, targetId:null, focus:0, focusTarget:0 }},
}};

const gaze = {{ x:.5, y:.5, targetX:.5, targetY:.5, velX:0, velY:0, quality:0 }};
const cam  = {{ x:0, y:1.65, z:-1.4, yaw:0, pitch:0, baseFov:700, fov:700 }};

// ─── ARTWORKS ───────────────────────────────────────────────
const artworks = [
  {{id:'a1',title:'Memórias de Superfície',artist:'Lívia Andrade',year:'2024',wall:'fundo',
    color:'#e74c3c',desc:'Pintura em camadas com relevo cromático e estratos de memória.',
    plane:'back', x:-2.8,y:2.1,z:9.85,w:1.7,h:1.2}},
  {{id:'a2',title:'Campo Sensível',artist:'Diego Marins',year:'2025',wall:'fundo',
    color:'#27ae60',desc:'Trabalho digital generativo com profundidade simulada.',
    plane:'back', x:0,y:2.2,z:9.85,w:1.7,h:1.2}},
  {{id:'a3',title:'Eco de Matéria',artist:'Marina Teles',year:'2026',wall:'fundo',
    color:'#f39c12',desc:'Objeto expandido que evoca microscopia e holografia.',
    plane:'back', x:2.8,y:2.05,z:9.85,w:1.7,h:1.2}},
  {{id:'a4',title:'Horizonte Índigo',artist:'Ciro Menezes',year:'2023',wall:'esquerda',
    color:'#8e44ad',desc:'Composição geométrica com ilusão de profundidade.',
    plane:'left', x:-4.85,y:2.1,z:6.1,w:1.6,h:1.1}},
  {{id:'a5',title:'Traço Latente',artist:'Rafaela Costa',year:'2022',wall:'direita',
    color:'#2980b9',desc:'Pintura que exige leitura periférica e foco seletivo.',
    plane:'right',x:4.85,y:2.05,z:5.7,w:1.6,h:1.1}},
];

let projArts = [];

// ─── UI HELPERS ─────────────────────────────────────────────
function setStatus(on,t){{ stDot.classList.toggle('on',!!on); stTxt.textContent=t; }}
function setMode(t){{ mdTxt.textContent=t; }}
function setQuality(q){{
  const v=Math.round(q*100);
  sQ.textContent=v+'%';
  qTxt.textContent=v+'%';
  const circ=138.2;
  qArc.style.strokeDashoffset=String(circ-(circ*q));
  qArc.style.stroke=q>.7?'var(--ok)':q>.35?'var(--warn)':'var(--danger)';
}}
function flashBlink(msg){{
  bflash.textContent=msg;
  bflash.classList.add('show');
  clearTimeout(bflash._t);
  bflash._t=setTimeout(()=>bflash.classList.remove('show'),1200);
}}
function setConnected(ok){{
  connBadge.className='connBadge '+(ok?'conn':'disc');
  connBadge.textContent=ok?'⬤ conectado':'⬤ desconectado';
}}

// ─── CANVAS RESIZE ──────────────────────────────────────────
function resize(){{
  const r=scene.getBoundingClientRect();
  const dpr=window.devicePixelRatio||1;
  [roomC,heatC,revC].forEach(c=>{{
    c.width=Math.floor(r.width*dpr);
    c.height=Math.floor(r.height*dpr);
    c.style.width=r.width+'px';c.style.height=r.height+'px';
  }});
  ctx.setTransform(dpr,0,0,dpr,0,0);
  heatX.setTransform(dpr,0,0,dpr,0,0);
  revX.setTransform(dpr,0,0,dpr,0,0);
  // Pupil canvas
  const pc=pupilC.getBoundingClientRect();
  pupilC.width=Math.floor(pc.width*dpr);
  pupilC.height=Math.floor(pc.height*dpr);
  pupilCtx.setTransform(dpr,0,0,dpr,0,0);
}}
window.addEventListener('resize',resize);

// ─── PROJECTION ─────────────────────────────────────────────
function proj(x,y,z){{
  const rx=x-cam.x,ry=y-cam.y,rz=z-cam.z;
  const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw);
  const cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
  const x1=rx*cy-rz*sy,z1=rx*sy+rz*cy;
  const y2=ry*cp-z1*sp,z2=ry*sp+z1*cp;
  if(z2<=.1)return null;
  const r=scene.getBoundingClientRect();
  const s=cam.fov/z2;
  return {{x:r.width/2+x1*s,y:r.height/2-y2*s,depth:z2,scale:s}};
}}

function poly(art){{
  const {{x,y,z,w,h,plane}}=art;
  if(plane==='back')return[proj(x-w/2,y-h/2,z),proj(x+w/2,y-h/2,z),proj(x+w/2,y+h/2,z),proj(x-w/2,y+h/2,z)];
  if(plane==='left')return[proj(x,y-h/2,z-w/2),proj(x,y-h/2,z+w/2),proj(x,y+h/2,z+w/2),proj(x,y+h/2,z-w/2)];
  return[proj(x,y-h/2,z+w/2),proj(x,y-h/2,z-w/2),proj(x,y+h/2,z-w/2),proj(x,y+h/2,z+w/2)];
}}

function drawPoly(pts,fill,stroke,lw){{
  if(!pts||pts.some(p=>!p))return;
  ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
  for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);
  ctx.closePath();
  if(fill){{ctx.fillStyle=fill;ctx.fill();}}
  if(stroke){{ctx.lineWidth=lw||1;ctx.strokeStyle=stroke;ctx.stroke();}}
}}

function ptIn(pt,ps){{
  let ins=false;
  for(let i=0,j=ps.length-1;i<ps.length;j=i++){{
    const xi=ps[i].x,yi=ps[i].y,xj=ps[j].x,yj=ps[j].y;
    if(((yi>pt.y)!==(yj>pt.y))&&(pt.x<(xj-xi)*(pt.y-yi)/((yj-yi)||1e-6)+xi))ins=!ins;
  }}
  return ins;
}}

// ─── HEATMAP ────────────────────────────────────────────────
function addHeat(xn,yn){{
  const r=scene.getBoundingClientRect();
  const px=xn*r.width,py=yn*r.height;
  state.heatPts.push({{x:px,y:py,ts:Date.now()}});
  if(state.heatPts.length>6000)state.heatPts.shift();

  const g=heatX.createRadialGradient(px,py,3,px,py,34);
  g.addColorStop(0,'rgba(231,76,60,.16)');g.addColorStop(.4,'rgba(243,156,18,.1)');
  g.addColorStop(.75,'rgba(46,204,113,.06)');g.addColorStop(1,'rgba(46,204,113,0)');
  heatX.fillStyle=g;heatX.beginPath();heatX.arc(px,py,34,0,Math.PI*2);heatX.fill();

  state.revPts.push({{x:px,y:py,life:1}});
  if(state.revPts.length>280)state.revPts.shift();
  sPts.textContent=String(state.heatPts.length);
  setQuality(gaze.quality);

  // fixation
  if(state.lastPx){{
    const d=Math.hypot(px-state.lastPx.x,py-state.lastPx.y);
    if(d<28){{state.stableFor+=state.sampleMs;if(state.stableFor>=260&&!state.inFix){{state.fixations++;state.inFix=true;sFix.textContent=String(state.fixations);}}}}
    else{{state.stableFor=0;state.inFix=false;}}
  }}
  state.lastPx={{x:px,y:py}};
}}

function clearHeat(){{
  const r=scene.getBoundingClientRect();
  heatX.clearRect(0,0,r.width,r.height);revX.clearRect(0,0,r.width,r.height);
  state.heatPts=[];state.revPts=[];state.fixations=0;state.inFix=false;
  state.stableFor=0;state.lastPx=null;sFix.textContent='0';sPts.textContent='0';
  log('Heatmap limpo.');
}}

function drawReveal(){{
  const r=scene.getBoundingClientRect();
  revX.clearRect(0,0,r.width,r.height);
  revX.fillStyle='rgba(2,5,12,.52)';revX.fillRect(0,0,r.width,r.height);
  revX.globalCompositeOperation='destination-out';
  state.revPts.forEach(p=>{{
    const rad=105+p.life*82;
    const g=revX.createRadialGradient(p.x,p.y,0,p.x,p.y,rad);
    g.addColorStop(0,'rgba(255,255,255,'+(0.19*p.life)+')');
    g.addColorStop(.45,'rgba(255,255,255,'+(0.11*p.life)+')');
    g.addColorStop(1,'rgba(255,255,255,0)');
    revX.fillStyle=g;revX.beginPath();revX.arc(p.x,p.y,rad,0,Math.PI*2);revX.fill();
    p.life*=.986;
  }});
  state.revPts=state.revPts.filter(p=>p.life>.07);
  revX.globalCompositeOperation='source-over';
}}

// ─── CURSOR SPRING ──────────────────────────────────────────
function updateCursor(){{
  gaze.velX=lerp(gaze.velX,gaze.targetX-gaze.x,.22);
  gaze.velY=lerp(gaze.velY,gaze.targetY-gaze.y,.22);
  gaze.x=clamp(gaze.x+gaze.velX*.38,.02,.98);
  gaze.y=clamp(gaze.y+gaze.velY*.38,.02,.98);
  cur.style.left=(gaze.x*100)+'%';
  cur.style.top=(gaze.y*100)+'%';
}}

// ─── ARTWORK HELPERS ────────────────────────────────────────
const artById = id => artworks.find(a=>a.id===id)||null;

function updateSelPanel(art){{
  if(!art){{selTitle.textContent='Nenhuma obra selecionada';
    selArtist.textContent='Olhe ~1s ou pisque 1× para zoom';
    selDesc.textContent='Ficha aparece após dwell ou blink. 2 piscadas rápidas = afasta.';return;}}
  selTitle.textContent=art.title;
  selArtist.textContent=art.artist+' · '+art.year+' · parede '+art.wall;
  selDesc.textContent=art.desc;
}}

function selectArtwork(art,src){{
  state.selectedId=art.id;state.zoom.active=true;
  state.zoom.targetId=art.id;state.zoom.focusTarget=1;
  sZoom.textContent='Zoom';updateSelPanel(art);
  if(!state.seenIds.has(art.id)){{state.seenIds.add(art.id);sArt.textContent=String(state.seenIds.size);}}
  state.selections.push({{id:art.id,title:art.title,ts:Date.now(),src}});
  log('Obra: "'+art.title+'" via '+src);
}}

function resetZoom(){{
  state.zoom.focusTarget=0;state.zoom.active=false;
  state.zoom.targetId=null;state.selectedId=null;
  sZoom.textContent='Normal';updateSelPanel(null);
}}

// ─── BLINK LOGIC (single / double) ──────────────────────────
function onSingleBlink(){{
  const hov=artById(state.hoveredId);
  if(hov){{selectArtwork(hov,'blink_1×');flashBlink('👁 zoom → "'+hov.title+'"');}}
  else if(state.zoom.focusTarget>0){{resetZoom();flashBlink('👁 zoom resetado');}}
}}

function onDoubleBlink(){{
  clearTimeout(state.blinkTimer);state.pendingBlink=false;
  if(state.zoom.focusTarget>0){{resetZoom();flashBlink('😮 afasta zoom');}}
  else flashBlink('😮 double blink');
}}

function handleBlink(ts){{
  const timeSince=ts-state.prevBlinkTs;
  if(state.pendingBlink && timeSince<0.5){{
    onDoubleBlink();state.prevBlinkTs=0;
  }} else {{
    state.prevBlinkTs=ts;state.pendingBlink=true;
    clearTimeout(state.blinkTimer);
    state.blinkTimer=setTimeout(()=>{{
      if(state.pendingBlink){{state.pendingBlink=false;onSingleBlink();}}
    }},520);
  }}
}}

// ─── GAZE SERVER POLLING ────────────────────────────────────
let _lastBlinkTs=0;
let _connFailed=0;
const _MAX_FAIL=4;

async function pollGaze(){{
  try{{
    const r=await fetch(API+'/gaze',{{cache:'no-store'}});
    const d=await r.json();

    _connFailed=0;
    setConnected(true);

    if(d.active){{
      if(!state.usingMouse){{
        gaze.targetX=d.x; gaze.targetY=d.y;
      }}
      gaze.quality=d.quality||0;
      setStatus(true,'Tracker ativo');setMode('Eye Tracker');
      sPupil.textContent='('+d.pupil_x+', '+d.pupil_y+')';

      // Draw pupil mini-view
      drawPupilMini(d.pupil_x, d.pupil_y, d.sphere_cx, d.sphere_cy);
    }} else {{
      setStatus(false,'Tracker inativo');
      gaze.quality=0;
    }}

    if(d.calibrated) sCal.textContent='Concluída';

    // Detect new blink from Python
    if(d.blink_ts && d.blink_ts>_lastBlinkTs+0.05){{
      _lastBlinkTs=d.blink_ts;
      handleBlink(d.blink_ts);
    }}
  }} catch(e){{
    _connFailed++;
    if(_connFailed>=_MAX_FAIL){{
      setConnected(false);
      if(!state.usingMouse){{
        setMode('Mouse (fallback)');state.usingMouse=true;
      }}
    }}
  }}
  setTimeout(pollGaze,50);
}}

// ─── MINI PUPIL VISUALIZER ──────────────────────────────────
function drawPupilMini(px,py,scx,scy){{
  const pc=pupilC.getBoundingClientRect();
  const w=pc.width, h=pc.height;
  const scale=w/640;
  pupilCtx.clearRect(0,0,w,h);
  pupilCtx.fillStyle='#020709';pupilCtx.fillRect(0,0,w,h);
  // Eye sphere circle
  pupilCtx.beginPath();pupilCtx.arc(scx*scale,scy*scale,202*scale,0,Math.PI*2);
  pupilCtx.strokeStyle='rgba(65,179,232,.5)';pupilCtx.lineWidth=1.5;pupilCtx.stroke();
  // Sphere center
  pupilCtx.beginPath();pupilCtx.arc(scx*scale,scy*scale,5*scale,0,Math.PI*2);
  pupilCtx.fillStyle='rgba(240,192,64,.9)';pupilCtx.fill();
  // Pupil
  pupilCtx.beginPath();pupilCtx.arc(px*scale,py*scale,8*scale,0,Math.PI*2);
  pupilCtx.fillStyle='rgba(46,204,113,.9)';pupilCtx.fill();
  // Gaze line
  const dx=px-scx,dy=py-scy;
  pupilCtx.beginPath();
  pupilCtx.moveTo(scx*scale,scy*scale);
  pupilCtx.lineTo((scx+dx*2)*scale,(scy+dy*2)*scale);
  pupilCtx.strokeStyle='rgba(200,255,0,.8)';pupilCtx.lineWidth=2;pupilCtx.stroke();
  // Labels
  pupilCtx.fillStyle='rgba(106,138,172,.8)';pupilCtx.font='9px IBM Plex Mono,monospace';
  pupilCtx.fillText('pupila',px*scale+9,py*scale-4);
  pupilCtx.fillText('esfera',scx*scale+9,scy*scale-4);
}}

// ─── HOVER / DWELL ──────────────────────────────────────────
function updateHoverDwell(now){{
  const r=scene.getBoundingClientRect();
  const gp={{x:gaze.x*r.width,y:gaze.y*r.height}};
  const hit=projArts.find(e=>ptIn(gp,e.poly));

  if(!hit){{
    if(state.hoveredId){{state.hoveredId=null;state.hoverStart=now;}}
    dwFill.style.width='0%';sHov.textContent='—';
    cur.style.width='24px';cur.style.height='24px';return;
  }}

  sHov.textContent=hit.art.title;
  if(state.hoveredId!==hit.art.id){{
    state.hoveredId=hit.art.id;state.hoverStart=now;
    cur.style.width='32px';cur.style.height='32px';
  }}
  const prog=clamp((now-state.hoverStart)/state.dwellMs,0,1);
  dwFill.style.width=(prog*100).toFixed(1)+'%';
  cur.style.borderColor=prog>.7?'rgba(46,204,113,.95)':'rgba(65,179,232,.95)';
  if(prog>=1){{selectArtwork(hit.art,'dwell');state.hoverStart=now+420;}}
}}

// ─── ROOM RENDERING ─────────────────────────────────────────
function drawArtwork(art,hl){{
  const pts=poly(art);
  if(!pts||pts.some(p=>!p))return null;
  const cx=(pts[0].x+pts[1].x+pts[2].x+pts[3].x)/4;
  const cy=(pts[0].y+pts[1].y+pts[2].y+pts[3].y)/4;
  drawPoly(pts,'rgba(65,50,35,.98)',hl?'rgba(65,179,232,.88)':'rgba(255,255,255,.1)',hl?2.5:1);
  const inn=pts.map(p=>{{return{{x:lerp(p.x,cx,.08),y:lerp(p.y,cy,.08)}}}});
  const g=ctx.createLinearGradient(inn[0].x,inn[0].y,inn[2].x,inn[2].y);
  g.addColorStop(0,art.color);g.addColorStop(1,'#08111e');
  drawPoly(inn,g,hl?'rgba(255,255,255,.2)':'rgba(255,255,255,.07)',1);
  ctx.fillStyle='rgba(255,255,255,.93)';ctx.font='bold 13px Syne,sans-serif';
  ctx.textAlign='center';ctx.fillText(art.title,cx,cy-4);
  ctx.fillStyle='rgba(200,215,255,.7)';ctx.font='11.5px Syne,sans-serif';
  ctx.fillText(art.artist,cx,cy+13);
  return pts;
}}

function drawPedestal(x,z,color){{
  const b=[proj(x-.52,0,z-.52),proj(x+.52,0,z-.52),proj(x+.52,0,z+.52),proj(x-.52,0,z+.52)];
  const t=[proj(x-.4,1.05,z-.4),proj(x+.4,1.05,z-.4),proj(x+.4,1.05,z+.4),proj(x-.4,1.05,z+.4)];
  if(b.some(p=>!p)||t.some(p=>!p))return;
  drawPoly([b[0],b[1],t[1],t[0]],'rgba(208,214,226,.82)','rgba(255,255,255,.1)',1);
  drawPoly([b[1],b[2],t[2],t[1]],'rgba(182,190,205,.84)','rgba(255,255,255,.1)',1);
  drawPoly([b[2],b[3],t[3],t[2]],'rgba(158,168,185,.86)','rgba(255,255,255,.1)',1);
  drawPoly(t,'rgba(230,234,242,.93)','rgba(255,255,255,.11)',1);
  const orb=proj(x,1.52,z);
  if(orb){{
    const rr=orb.scale*.17;
    const g=ctx.createRadialGradient(orb.x-rr*.35,orb.y-rr*.35,rr*.14,orb.x,orb.y,rr*1.6);
    g.addColorStop(0,color);g.addColorStop(1,'rgba(8,16,30,.1)');
    ctx.fillStyle=g;ctx.beginPath();ctx.arc(orb.x,orb.y,rr,0,Math.PI*2);ctx.fill();
  }}
}}

function drawRoom(){{
  const r=scene.getBoundingClientRect();
  ctx.clearRect(0,0,r.width,r.height);
  const bg=ctx.createLinearGradient(0,0,0,r.height);
  bg.addColorStop(0,'#050c18');bg.addColorStop(1,'#020709');
  ctx.fillStyle=bg;ctx.fillRect(0,0,r.width,r.height);

  const za=artById(state.zoom.targetId);
  state.zoom.focus=lerp(state.zoom.focus,state.zoom.focusTarget,.07);
  const gx=gaze.x-.5,gy=gaze.y-.5;
  let fx=0,fy=2.0,fz=8.5;
  if(za){{fx=za.x;fy=za.y;fz=za.z-(za.plane==='back'?1.9:0);}}
  const f=state.zoom.focus;
  cam.x  =lerp(gx*1.4,  fx*.2,f);
  cam.y  =lerp(1.65-gy*.5,fy-.12,f);
  cam.z  =lerp(-1.4,  fz-6.5,f);
  cam.yaw=lerp(gx*.55, fx*.018,f);
  cam.pitch=lerp(-gy*.16,-.025,f);
  cam.fov=lerp(cam.baseFov,cam.baseFov*1.6,f);

  const surfs=[
    {{c:[[-5,0,0],[5,0,0],[5,0,10],[-5,0,10]]   ,f:'rgba(18,28,46,.98)',s:'rgba(255,255,255,.035)'}},
    {{c:[[-5,4,0],[5,4,0],[5,4,10],[-5,4,10]]   ,f:'rgba(8,15,29,.9)', s:'rgba(255,255,255,.03)'}},
    {{c:[[-5,0,0],[-5,0,10],[-5,4,10],[-5,4,0]] ,f:'rgba(11,19,36,.94)',s:'rgba(255,255,255,.04)'}},
    {{c:[[5,0,0],[5,0,10],[5,4,10],[5,4,0]]     ,f:'rgba(10,18,34,.94)',s:'rgba(255,255,255,.04)'}},
    {{c:[[-5,0,10],[5,0,10],[5,4,10],[-5,4,10]] ,f:'rgba(13,22,40,.96)',s:'rgba(255,255,255,.04)'}},
  ];
  surfs.forEach(s=>drawPoly(s.c.map(p=>proj(...p)),s.f,s.s,1));

  for(let i=-4;i<=4;i++){{
    const a=proj(i,.001,.2),b=proj(i,.001,9.8);
    if(a&&b){{ctx.strokeStyle='rgba(255,255,255,.035)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}}
  }}
  for(let z=1;z<=10;z++){{
    const a=proj(-4.8,.001,z),b=proj(4.8,.001,z);
    if(a&&b){{ctx.strokeStyle='rgba(255,255,255,.03)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}}
  }}

  const sl=proj(gx*3,3.5,4.8);
  if(sl){{
    const g=ctx.createRadialGradient(sl.x,sl.y,0,sl.x,sl.y,r.width*.32);
    g.addColorStop(0,'rgba(65,179,232,.16)');g.addColorStop(.5,'rgba(65,179,232,.05)');
    g.addColorStop(1,'rgba(65,179,232,0)');
    ctx.fillStyle=g;ctx.beginPath();ctx.arc(sl.x,sl.y,r.width*.32,0,Math.PI*2);ctx.fill();
  }}

  drawPedestal(-1.8,3.0,'rgba(65,179,232,.9)');
  drawPedestal(1.8,3.35,'rgba(155,89,182,.9)');

  projArts=[];
  artworks.forEach(art=>{{
    const hl=state.hoveredId===art.id||state.selectedId===art.id||state.zoom.targetId===art.id;
    const p=drawArtwork(art,hl);
    if(p)projArts.push({{art,poly:p}});
  }});

  // crosshair
  const gp={{x:gaze.x*r.width,y:gaze.y*r.height}};
  ctx.strokeStyle='rgba(255,255,255,.07)';ctx.lineWidth=1;ctx.beginPath();
  ctx.moveTo(gp.x,0);ctx.lineTo(gp.x,r.height);
  ctx.moveTo(0,gp.y);ctx.lineTo(r.width,gp.y);ctx.stroke();
}}

// ─── CLOCK ──────────────────────────────────────────────────
setInterval(()=>{{
  if(!state.startedAt){{sTime.textContent='00:00';return;}}
  const s=Math.floor((Date.now()-state.startedAt)/1000);
  sTime.textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');
}},400);

// ─── MOUSE FALLBACK ─────────────────────────────────────────
scene.addEventListener('mousemove',ev=>{{
  if(!state.usingMouse)return;
  const r=scene.getBoundingClientRect();
  gaze.targetX=clamp((ev.clientX-r.left)/r.width,.02,.98);
  gaze.targetY=clamp((ev.clientY-r.top)/r.height,.02,.98);
}});
scene.addEventListener('click',()=>{{
  if(!state.usingMouse)return;
  const h=artById(state.hoveredId);
  if(h)selectArtwork(h,'click'); else if(state.zoom.focusTarget>0)resetZoom();
}});

// ─── BUTTONS ────────────────────────────────────────────────
document.getElementById('btnCal').addEventListener('click',async()=>{{
  try{{
    await fetch(API+'/gaze',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{action:'calibrate'}})}});
    sCal.textContent='Concluída';pnote.textContent='Calibração enviada ao tracker.';
    log('Calibração solicitada.');
  }}catch(e){{log('Erro calibração: '+e.message);}}
}});
document.getElementById('btnLock').addEventListener('click',async()=>{{
  try{{
    await fetch(API+'/gaze',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{action:'lock_sphere'}})}});
    log('Esfera ocular travada.');pnote.textContent='Esfera ocular travada.';
  }}catch(e){{log('Erro lock: '+e.message);}}
}});
document.getElementById('btnHeat').addEventListener('click',clearHeat);
document.getElementById('btnMouse').addEventListener('click',()=>{{
  state.usingMouse=!state.usingMouse;
  document.getElementById('btnMouse').textContent=state.usingMouse?'👁 Eye tracker':'🖱 Forçar mouse';
  setMode(state.usingMouse?'Mouse':'Eye Tracker');
  log(state.usingMouse?'Modo mouse ativado.':'Modo eye tracker ativado.');
}});
document.getElementById('btnPdf').addEventListener('click',exportPdf);

// ─── BUILD ARTWORK LIST ─────────────────────────────────────
function buildList(){{
  aList.innerHTML='';
  artworks.forEach(art=>{{
    const row=document.createElement('div'); row.className='ar';
    row.innerHTML='<div class="ab" style="background:'+art.color+'"></div>'+
      '<div><div class="at">'+art.title+'</div><div class="as">'+art.artist+' · '+art.year+'</div></div>'+
      '<div class="badge">'+art.wall+'</div>';
    row.addEventListener('click',()=>selectArtwork(art,'lista'));
    aList.appendChild(row);
  }});
}}

// ─── PDF EXPORT ─────────────────────────────────────────────
async function exportPdf(){{
  log('Exportando PDF…');
  const si=roomC.toDataURL('image/png',1);
  const hi=heatC.toDataURL('image/png',1);
  try{{
    await new Promise((res,rej)=>{{
      if(document.querySelector('script[data-jspdf]')){{res();return;}}
      const s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
      s.dataset.jspdf='1';s.onload=res;s.onerror=rej;document.head.appendChild(s);
    }});
    const jsPDF=window.jspdf?.jsPDF;
    if(!jsPDF)throw new Error('jsPDF não carregou');
    const pdf=new jsPDF('p','mm','a4');
    let y=16;
    pdf.setFillColor(5,12,24);pdf.rect(0,0,210,297,'F');
    pdf.setTextColor(221,238,255);pdf.setFont('helvetica','bold');pdf.setFontSize(16);
    pdf.text('Relatório Eye Tracker – Sala 3D',12,y);y+=8;
    pdf.setFont('helvetica','normal');pdf.setFontSize(10);pdf.setTextColor(106,138,172);
    pdf.text('Gerado: '+new Date().toLocaleString(),12,y);y+=9;
    pdf.setTextColor(221,238,255);pdf.setFontSize(11);
    [
      'Modo: Eye Tracker (pupila real / OpenCV)',
      'Amostras: '+state.heatPts.length,
      'Fixações: '+state.fixations,
      'Obras vistas: '+state.seenIds.size,
      'Qualidade estimada: '+Math.round(gaze.quality*100)+'%',
      'Zoom ativo: '+(state.zoom.focus>.15?'sim':'não'),
    ].forEach(l=>{{pdf.text(l,12,y);y+=5;}});
    y+=4;pdf.setFont('helvetica','bold');
    pdf.text('Cena + Heatmap',12,y);y+=3;
    pdf.addImage(si,'PNG',12,y,88,66,undefined,'FAST');
    pdf.addImage(hi,'PNG',108,y,88,66,undefined,'FAST');
    y+=72;pdf.setFont('helvetica','bold');pdf.text('Seleções',12,y);y+=6;
    pdf.setFont('helvetica','normal');
    if(!state.selections.length){{pdf.text('Nenhuma.',12,y);}}
    else{{
      const g={{}};state.selections.forEach(s=>{{g[s.id]=g[s.id]||{{title:s.title,n:0}};g[s.id].n++;}});
      Object.values(g).forEach(v=>{{pdf.text('• '+v.title+' ('+v.n+'×)',12,y);y+=5;}});
    }}
    pdf.save('relatorio_sala3d_eyetracker.pdf');
    log('PDF salvo.');
  }}catch(e){{log('Erro PDF: '+e.message);}}
}}

// ─── MAIN LOOP ──────────────────────────────────────────────
function tick(now){{
  requestAnimationFrame(tick);
  if(!state.startedAt)state.startedAt=Date.now();
  updateCursor(); drawRoom(); drawReveal();
  updateHoverDwell(now);
  const t=Date.now();
  if(t-state.lastSampleTs>=state.sampleMs){{state.lastSampleTs=t;addHeat(gaze.x,gaze.y);}}
  if(!state.hoveredId){{cur.style.width='24px';cur.style.height='24px';cur.style.borderColor='rgba(255,255,255,.9)';}}
}}

// ─── INIT ───────────────────────────────────────────────────
resize(); buildList(); updateSelPanel(null);
setMode('Mouse');setStatus(false,'Aguardando');
requestAnimationFrame(tick);
pollGaze();
log('Sala pronta. Polling tracker em localhost:'+PORT);

}})();
</script>
</div>
"""


# ════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(page_title="Sala 3D · Eye Tracker Real", layout="wide")

    st.title("🔬 Sala 3D com Rastreamento Ocular Real")
    st.caption("Detecção de pupila via OpenCV (sem MediaPipe). Câmera de olho ou fallback por mouse.")

    # ── sidebar config ────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Configuração")
        cam_idx = st.number_input("Índice da câmera de olho", min_value=0, max_value=9,
                                  value=0, step=1,
                                  help="Câmera 0 = padrão. Use um número maior se tiver câmera dedicada.")
        flip_v = st.checkbox("Inverter verticalmente (câmera IR)", value=True)
        debug  = st.checkbox("Mostrar janelas OpenCV de debug", value=False)

        st.markdown("---")
        st.markdown("""
**Blinks detectados pelo tracker Python:**
- Pupila desaparece 2–14 frames consecutivos → blink
- **1 piscar** = zoom in
- **2 piscadas rápidas** = zoom out

**Calibração:**  
Olhe para o centro da tela e clique **⊕ Calibrar centro**.

**Travar esfera:**  
Após detectar o olho, clique **⊙ Travar esfera** para fixar
o centro do modelo ocular.
""")
        st.markdown("---")
        st.caption(f"Câmera configurada: **{cam_idx}**")

        if st.button("🔄 Reiniciar tracker"):
            if 'gaze_port' in st.session_state:
                del st.session_state['gaze_port']
                if '_tracker_instance' in globals() and _tracker_instance:
                    _tracker_instance.stop()
            st.rerun()

    # ── start background services ─────────────────────────────
    port = ensure_services(camera_index=int(cam_idx), show_debug=debug)

    st.info(f"🔌 Servidor de gaze rodando em `localhost:{port}` · "
            f"Câmera de olho: índice **{cam_idx}**",
            icon="📡")

    # ── HTML component ────────────────────────────────────────
    components.html(build_html(port), height=1320, scrolling=True)

    # ── live metrics refresh ──────────────────────────────────
    with st.expander("📊 Estado do tracker (Python)", expanded=False):
        data = g_get()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gaze X", f"{data['x']:.3f}")
        c2.metric("Gaze Y", f"{data['y']:.3f}")
        c3.metric("Qualidade", f"{data['quality']*100:.0f}%")
        c4.metric("Tracker ativo", "✅" if data['active'] else "❌")

        st.json(data)

        if st.button("🔃 Atualizar"):
            st.rerun()


if __name__ == "__main__":
    main()
