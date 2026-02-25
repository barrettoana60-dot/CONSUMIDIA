import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="👁️ Iris Ball Tracker 3D",
    page_icon="👁️",
    layout="wide",
)

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controles")
    ball_radius  = st.slider("Raio da Bola",              20,  120,  50)
    smoothing    = st.slider("Suavização (0=fluido)",     1,   30,   8)
    amplify      = st.slider("Amplificação do olhar",     10,  50,   28)
    show_mesh    = st.checkbox("Mostrar malha facial",    value=True)
    show_iris    = st.checkbox("Mostrar pontos da íris",  value=True)
    dark_bg      = st.checkbox("Fundo escuro no canvas",  value=False)

    st.markdown("### 🎨 Cor da Bola")
    ball_color = st.color_picker("Cor base", "#4488ff")

    st.markdown("---")
    st.markdown("""
**Tecnologia:**
- 🧠 MediaPipe FaceMesh **JavaScript** (roda no browser)
- 📷 Acesso direto à câmera via `getUserMedia`
- 🎨 Renderização com Canvas 2D
- ✅ Sem WebRTC, sem servidor, sem STUN/TURN

**Dica:** Mova só os olhos, mantendo a cabeça parada!
    """)

# ── Build config to pass into JS ──────────────────────────────────────────────
cfg = {
    "ballRadius":  ball_radius,
    "smoothing":   smoothing,
    "amplify":     amplify / 10.0,
    "showMesh":    str(show_mesh).lower(),
    "showIris":    str(show_iris).lower(),
    "darkBg":      str(dark_bg).lower(),
    "ballColor":   ball_color,
}

# ── Main title ────────────────────────────────────────────────────────────────
st.markdown("# 👁️ Iris Ball Tracker 3D")
st.markdown(
    "Controle a bola 3D **apenas com o movimento dos seus olhos**. "
    "Tudo roda no seu browser — sem latência de rede."
)

# ── HTML/JS Component ─────────────────────────────────────────────────────────
html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0d0d1a; font-family: 'Segoe UI', sans-serif; }}

  #wrapper {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 10px;
  }}

  #canvasContainer {{
    position: relative;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 0 30px #4488ff55;
    border: 2px solid #4a4aff55;
  }}

  #outputCanvas {{
    display: block;
    border-radius: 12px;
  }}

  #videoEl {{
    display: none;
  }}

  #hud {{
    display: flex;
    gap: 20px;
    color: #aac4ff;
    font-size: 13px;
    background: #1a1a2e;
    border-radius: 8px;
    padding: 6px 18px;
    border: 1px solid #333366;
  }}

  #statusDot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #ff4444;
    display: inline-block;
    margin-right: 6px;
    transition: background 0.3s;
  }}

  #loadingMsg {{
    color: #7eb8f7;
    font-size: 15px;
    padding: 20px;
    text-align: center;
  }}

  .hud-item {{ display: flex; align-items: center; gap: 5px; }}
</style>
</head>
<body>
<div id="wrapper">
  <div id="loadingMsg">⏳ Carregando MediaPipe FaceMesh...</div>
  <div id="canvasContainer" style="display:none">
    <canvas id="outputCanvas"></canvas>
  </div>
  <div id="hud" style="display:none">
    <div class="hud-item"><span id="statusDot"></span><span id="statusTxt">Iniciando...</span></div>
    <div class="hud-item">👁️ X: <b id="hudX">—</b></div>
    <div class="hud-item">👁️ Y: <b id="hudY">—</b></div>
    <div class="hud-item">FPS: <b id="hudFps">—</b></div>
  </div>
  <video id="videoEl" autoplay playsinline></video>
</div>

<!-- MediaPipe via CDN -->
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/drawing_utils/drawing_utils.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js" crossorigin="anonymous"></script>

<script>
// ── Config from Python ───────────────────────────────────────────────────────
const CFG = {{
  ballRadius : {cfg["ballRadius"]},
  smoothing  : {cfg["smoothing"]},
  amplify    : {cfg["amplify"]},
  showMesh   : {cfg["showMesh"]},
  showIris   : {cfg["showIris"]},
  darkBg     : {cfg["darkBg"]},
  ballColor  : "{cfg["ballColor"]}",
}};

// ── State ────────────────────────────────────────────────────────────────────
let ballX = 0, ballY = 0;
let frameCount = 0, lastFpsTime = performance.now();
let fps = 0, detected = false;

const LEFT_IRIS  = [474, 475, 476, 477];
const RIGHT_IRIS = [469, 470, 471, 472];
const FACE_OVAL  = [10,338,297,332,284,251,389,356,454,323,361,
                    288,397,365,379,378,400,377,152,148,176,149,
                    150,136,172,58,132,93,234,127,162,21,54,103,67,109];

// ── DOM refs ─────────────────────────────────────────────────────────────────
const video   = document.getElementById("videoEl");
const canvas  = document.getElementById("outputCanvas");
const ctx2d   = canvas.getContext("2d");
const loadMsg = document.getElementById("loadingMsg");
const container = document.getElementById("canvasContainer");
const hud     = document.getElementById("hud");
const statusDot = document.getElementById("statusDot");
const statusTxt = document.getElementById("statusTxt");
const hudX    = document.getElementById("hudX");
const hudY    = document.getElementById("hudY");
const hudFps  = document.getElementById("hudFps");

// ── 3D Ball ──────────────────────────────────────────────────────────────────
function hexToRgb(hex) {{
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return {{r,g,b}};
}}

function draw3dBall(x, y, radius, colorHex) {{
  const {{r,g,b}} = hexToRgb(colorHex);
  const cx = Math.max(radius, Math.min(canvas.width  - radius, x));
  const cy = Math.max(radius, Math.min(canvas.height - radius, y));

  // Shadow
  ctx2d.save();
  ctx2d.globalAlpha = 0.35;
  ctx2d.beginPath();
  ctx2d.ellipse(cx + radius*0.2, cy + radius*0.85, radius*1.1, radius*0.3, 0, 0, Math.PI*2);
  ctx2d.fillStyle = "#000";
  ctx2d.fill();
  ctx2d.restore();

  // Main sphere gradient
  const grad = ctx2d.createRadialGradient(
    cx - radius*0.3, cy - radius*0.3, radius*0.05,
    cx,             cy,               radius
  );
  grad.addColorStop(0,   `rgb(${{Math.min(255,r+100)}},${{Math.min(255,g+100)}},${{Math.min(255,b+100)}})`);
  grad.addColorStop(0.4, `rgb(${{r}},${{g}},${{b}})`);
  grad.addColorStop(1,   `rgb(${{Math.max(0,r-80)}},${{Math.max(0,g-80)}},${{Math.max(0,b-80)}})`);

  ctx2d.beginPath();
  ctx2d.arc(cx, cy, radius, 0, Math.PI*2);
  ctx2d.fillStyle = grad;
  ctx2d.fill();

  // Rim light
  ctx2d.beginPath();
  ctx2d.arc(cx, cy, radius, 0, Math.PI*2);
  ctx2d.strokeStyle = `rgba(${{Math.min(255,r+80)}},${{Math.min(255,g+80)}},255,0.6)`;
  ctx2d.lineWidth = 2;
  ctx2d.stroke();

  // Primary specular
  const sg1 = ctx2d.createRadialGradient(
    cx - radius*0.35, cy - radius*0.35, 0,
    cx - radius*0.35, cy - radius*0.35, radius*0.45
  );
  sg1.addColorStop(0,   "rgba(255,255,255,0.9)");
  sg1.addColorStop(0.4, "rgba(255,255,255,0.3)");
  sg1.addColorStop(1,   "rgba(255,255,255,0)");
  ctx2d.beginPath();
  ctx2d.arc(cx - radius*0.35, cy - radius*0.35, radius*0.45, 0, Math.PI*2);
  ctx2d.fillStyle = sg1;
  ctx2d.fill();

  // Secondary soft glow
  const sg2 = ctx2d.createRadialGradient(
    cx - radius*0.2, cy - radius*0.2, 0,
    cx - radius*0.2, cy - radius*0.2, radius*0.7
  );
  sg2.addColorStop(0,   "rgba(200,220,255,0.4)");
  sg2.addColorStop(1,   "rgba(200,220,255,0)");
  ctx2d.beginPath();
  ctx2d.arc(cx - radius*0.2, cy - radius*0.2, radius*0.7, 0, Math.PI*2);
  ctx2d.fillStyle = sg2;
  ctx2d.fill();
}}

// ── Face Mesh drawing ────────────────────────────────────────────────────────
function drawFaceOval(lms, W, H) {{
  if (!CFG.showMesh) return;
  ctx2d.beginPath();
  FACE_OVAL.forEach((idx, i) => {{
    const lm = lms[idx];
    const x = lm.x * W, y = lm.y * H;
    i === 0 ? ctx2d.moveTo(x,y) : ctx2d.lineTo(x,y);
  }});
  ctx2d.closePath();
  ctx2d.strokeStyle = "rgba(80,80,200,0.55)";
  ctx2d.lineWidth = 1;
  ctx2d.stroke();
}}

function drawIrisDots(lms, W, H) {{
  if (!CFG.showIris) return;
  [...LEFT_IRIS, ...RIGHT_IRIS].forEach(idx => {{
    ctx2d.beginPath();
    ctx2d.arc(lms[idx].x * W, lms[idx].y * H, 3, 0, Math.PI*2);
    ctx2d.fillStyle = "#00ffaa";
    ctx2d.fill();
  }});
}}

// ── FPS counter ───────────────────────────────────────────────────────────────
function updateFps() {{
  frameCount++;
  const now = performance.now();
  if (now - lastFpsTime >= 1000) {{
    fps = frameCount;
    frameCount = 0;
    lastFpsTime = now;
    hudFps.textContent = fps;
  }}
}}

// ── MediaPipe callback ───────────────────────────────────────────────────────
function onResults(results) {{
  const W = canvas.width, H = canvas.height;

  // Draw video frame (mirrored)
  ctx2d.save();
  ctx2d.scale(-1, 1);
  ctx2d.drawImage(results.image, -W, 0, W, H);
  ctx2d.restore();

  if (CFG.darkBg) {{
    ctx2d.fillStyle = "rgba(10,10,26,0.45)";
    ctx2d.fillRect(0, 0, W, H);
  }}

  if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {{
    detected = true;
    const lms = results.multiFaceLandmarks[0];

    drawFaceOval(lms, W, H);
    drawIrisDots(lms, W, H);

    // Compute iris centers
    const irisCenter = (indices) => {{
      let sx=0, sy=0;
      indices.forEach(i => {{ sx += lms[i].x; sy += lms[i].y; }});
      return [sx/indices.length * W, sy/indices.length * H];
    }};

    const [lx,ly] = irisCenter(LEFT_IRIS);
    const [rx,ry] = irisCenter(RIGHT_IRIS);

    // Mirror X because we flipped the canvas draw
    const rawX = W - (lx + rx) / 2;
    const rawY = (ly + ry) / 2;

    // Amplify from center
    let nx = ((rawX / W) - 0.5) * CFG.amplify;
    let ny = ((rawY / H) - 0.5) * CFG.amplify;
    nx = Math.max(-1, Math.min(1, nx));
    ny = Math.max(-1, Math.min(1, ny));

    const targetX = (nx + 1) / 2 * W;
    const targetY = (ny + 1) / 2 * H;

    // EMA smoothing
    const alpha = 1 / CFG.smoothing;
    ballX += alpha * (targetX - ballX);
    ballY += alpha * (targetY - ballY);

    // HUD
    statusDot.style.background = "#00ff88";
    statusTxt.textContent = "TRACKING";
    hudX.textContent = Math.round(ballX);
    hudY.textContent = Math.round(ballY);

  }} else {{
    detected = false;
    statusDot.style.background = "#ff4444";
    statusTxt.textContent = "Procurando rosto...";
  }}

  draw3dBall(ballX, ballY, CFG.ballRadius, CFG.ballColor);
  updateFps();
}}

// ── Init MediaPipe ────────────────────────────────────────────────────────────
const faceMesh = new FaceMesh({{
  locateFile: (file) =>
    `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${{file}}`
}});

faceMesh.setOptions({{
  maxNumFaces: 1,
  refineLandmarks: true,        // ← habilita íris (469-477)
  minDetectionConfidence: 0.5,
  minTrackingConfidence: 0.5,
}});

faceMesh.onResults(onResults);

// ── Camera ────────────────────────────────────────────────────────────────────
const camera = new Camera(video, {{
  onFrame: async () => {{
    await faceMesh.send({{image: video}});
  }},
  width: 640,
  height: 480,
}});

camera.start().then(() => {{
  // Resize canvas to video
  video.addEventListener("loadedmetadata", () => {{
    canvas.width  = video.videoWidth  || 640;
    canvas.height = video.videoHeight || 480;
    ballX = canvas.width  / 2;
    ballY = canvas.height / 2;
  }});

  loadMsg.style.display   = "none";
  container.style.display = "block";
  hud.style.display       = "flex";
}}).catch(err => {{
  loadMsg.innerHTML = `<span style="color:#ff6666">❌ Erro ao acessar câmera:<br>${{err.message}}</span>`;
}});
</script>
</body>
</html>
"""

components.html(html_code, height=600, scrolling=False)

# ── Info columns ──────────────────────────────────────────────────────────────
st.markdown("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("### 🧠 Como funciona")
    st.markdown(
        "MediaPipe FaceMesh detecta **478 pontos** no rosto. "
        "Os índices **469–477** são exclusivos da íris esquerda e direita. "
        "A posição média das duas íris é mapeada para a posição da bola na tela."
    )
with c2:
    st.markdown("### ✅ Por que funciona no Streamlit Cloud")
    st.markdown(
        "Toda a lógica roda **no seu browser** via JavaScript. "
        "Não há streaming de vídeo para o servidor, sem WebRTC, sem STUN/TURN. "
        "A câmera é acessada localmente pelo `getUserMedia`."
    )
with c3:
    st.markdown("### 🎮 Dicas de uso")
    st.markdown(
        "Ajuste a **amplificação** se o movimento da bola parecer pequeno. "
        "Reduza a **suavização** para resposta mais rápida. "
        "Habilite o **fundo escuro** para realçar a bola contra o vídeo."
    )
