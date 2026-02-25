import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="👁️ Iris Ball 3D",
    page_icon="👁️",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controles")
    ball_radius = st.slider("Raio base da bola",       25,  100, 52)
    smoothing   = st.slider("Suavização",               1,   30,  7)
    amplify     = st.slider("Amplificação do olhar",   10,   50, 26)
    pop_effect  = st.slider("Efeito 'saindo da tela'", 0,   60,  35)
    blur_amount = st.slider("Desfoque do fundo",        0,   20,  9)

    st.markdown("### 🎨 Cor da Bola")
    ball_color  = st.color_picker("Cor base", "#2277ff")

    st.markdown("### 🎯 Opções Visuais")
    show_mesh   = st.checkbox("Malha facial",          value=True)
    show_iris   = st.checkbox("Pontos da íris",        value=True)
    show_shadow = st.checkbox("Sombra no vídeo",       value=True)
    show_glow   = st.checkbox("Halo de luz",           value=True)

    st.markdown("---")
    st.markdown("""
**Renderização:**  
Canvas 2D multi-pass com:
- Esfera Phong + Blinn specular
- Depth-of-field simulado (offscreen blur)
- Efeito parallax Z (bola cresce ao centro)
- Sombra dinâmica projetada no vídeo
- Halo volumétrico com bloom

**Zero WebRTC** — roda 100% no browser.
    """)

cfg = {
    "ballRadius" : ball_radius,
    "smoothing"  : smoothing,
    "amplify"    : amplify / 10.0,
    "popEffect"  : pop_effect,
    "blurAmount" : blur_amount,
    "ballColor"  : ball_color,
    "showMesh"   : str(show_mesh).lower(),
    "showIris"   : str(show_iris).lower(),
    "showShadow" : str(show_shadow).lower(),
    "showGlow"   : str(show_glow).lower(),
}

st.markdown("# 👁️ Iris Ball 3D — Depth of Field")
st.markdown("Mova os olhos para controlar a bola. Ela **sai da tela** e o fundo fica desfocado.")

HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#050510; display:flex; flex-direction:column; align-items:center; font-family:'Segoe UI',sans-serif; }}

  #wrap {{
    position:relative;
    margin-top:10px;
    border-radius:16px;
    overflow:hidden;
    box-shadow: 0 0 60px #2277ff44, 0 0 20px #0008;
    border: 1.5px solid #2277ff33;
  }}

  /* The three stacked canvases */
  canvas {{ position:absolute; top:0; left:0; border-radius:16px; }}
  #cVideo  {{ position:relative; }}   /* base layer  */
  #cBlur   {{ pointer-events:none; }} /* blur overlay */
  #cBall   {{ pointer-events:none; }} /* ball layer   */

  #hud {{
    margin:8px 0 4px;
    display:flex; gap:18px;
    color:#aac4ff; font-size:13px;
    background:#0e0e20; border-radius:8px;
    padding:5px 16px; border:1px solid #2244aa44;
  }}
  .hi {{ display:flex; align-items:center; gap:5px; }}
  #dot {{ width:9px;height:9px;border-radius:50%;background:#ff3333;transition:background .3s; }}

  #loader {{
    color:#7eb8f7; font-size:15px; padding:28px 60px;
    background:#0e0e20; border-radius:14px; border:1px solid #333388;
    text-align:center;
  }}
  video {{ display:none; }}
</style>
</head>
<body>

<div id="loader">⏳ Carregando MediaPipe FaceMesh…</div>

<div id="wrap" style="display:none">
  <canvas id="cVideo"></canvas>
  <canvas id="cBlur"></canvas>
  <canvas id="cBall"></canvas>
</div>

<div id="hud" style="display:none">
  <div class="hi"><span id="dot"></span><span id="stTxt">Iniciando…</span></div>
  <div class="hi">X: <b id="hX">—</b></div>
  <div class="hi">Y: <b id="hY">—</b></div>
  <div class="hi">Z: <b id="hZ">—</b></div>
  <div class="hi">FPS: <b id="hFps">—</b></div>
</div>

<video id="vid" autoplay playsinline></video>

<!-- MediaPipe CDN -->
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js"       crossorigin="anonymous"></script>

<script>
// ── Config ───────────────────────────────────────────────────────────────────
const CFG = {{
  ballRadius : {cfg["ballRadius"]},
  smoothing  : {cfg["smoothing"]},
  amplify    : {cfg["amplify"]},
  popEffect  : {cfg["popEffect"]},
  blurAmount : {cfg["blurAmount"]},
  ballColor  : "{cfg["ballColor"]}",
  showMesh   : {cfg["showMesh"]},
  showIris   : {cfg["showIris"]},
  showShadow : {cfg["showShadow"]},
  showGlow   : {cfg["showGlow"]},
}};

// ── Landmark indices ──────────────────────────────────────────────────────────
const LEFT_IRIS  = [474,475,476,477];
const RIGHT_IRIS = [469,470,471,472];
const FACE_OVAL  = [10,338,297,332,284,251,389,356,454,323,361,288,
                    397,365,379,378,400,377,152,148,176,149,150,136,
                    172,58,132,93,234,127,162,21,54,103,67,109];
const LEFT_EYE   = [362,382,381,380,374,373,390,249,263,466,388,387,386,385,384,398];
const RIGHT_EYE  = [33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246];

// ── Canvas setup ──────────────────────────────────────────────────────────────
const vid    = document.getElementById("vid");
const cVideo = document.getElementById("cVideo");
const cBlur  = document.getElementById("cBlur");
const cBall  = document.getElementById("cBall");
const ctxV   = cVideo.getContext("2d");
const ctxBl  = cBlur.getContext("2d");
const ctxB   = cBall.getContext("2d");

const W = 640, H = 480;
[cVideo, cBlur, cBall].forEach(c => {{ c.width = W; c.height = H; }});
document.getElementById("wrap").style.width  = W + "px";
document.getElementById("wrap").style.height = H + "px";

// ── Ball state ────────────────────────────────────────────────────────────────
let bx = W/2, by = H/2, bz = 0;   // z: 0=screen plane, 1=fully out
let frameN=0, lastFT=performance.now(), fps=0, detected=false;

// ── Offscreen canvas for blur pass ───────────────────────────────────────────
const offscreen = document.createElement("canvas");
offscreen.width = W; offscreen.height = H;
const octx = offscreen.getContext("2d");

// ── Hex → RGB ─────────────────────────────────────────────────────────────────
function hexRgb(h) {{
  return {{
    r: parseInt(h.slice(1,3),16),
    g: parseInt(h.slice(3,5),16),
    b: parseInt(h.slice(5,7),16),
  }};
}}

// ── Draw DOF background blur ──────────────────────────────────────────────────
function drawBlurredBg(blurPx) {{
  ctxBl.clearRect(0,0,W,H);
  if (blurPx <= 0) return;

  // Stack multiple semi-transparent shifted copies → cheap box blur simulation
  const steps = 8;
  ctxBl.globalAlpha = 0.18;
  for (let i = 0; i < steps; i++) {{
    const angle = (i / steps) * Math.PI * 2;
    const d = blurPx * 0.5;
    ctxBl.drawImage(cVideo, Math.cos(angle)*d, Math.sin(angle)*d);
  }}
  // One opaque center pass to anchor colors
  ctxBl.globalAlpha = 0.55;
  ctxBl.drawImage(cVideo, 0, 0);
  ctxBl.globalAlpha = 1;

  // Vignette — dark edges to focus attention on center
  const vignette = ctxBl.createRadialGradient(W/2,H/2, H*0.2, W/2,H/2, H*0.85);
  vignette.addColorStop(0, "rgba(0,0,0,0)");
  vignette.addColorStop(1, "rgba(0,0,10,0.72)");
  ctxBl.fillStyle = vignette;
  ctxBl.fillRect(0,0,W,H);
}}

// ── Draw projected shadow on video layer ─────────────────────────────────────
function drawGroundShadow(cx, cy, r, z) {{
  if (!CFG.showShadow) return;
  const sy = cy + r * 0.9 + z * 18;     // shadow drops as ball "rises"
  const sx = cx + r * 0.15;
  const scaleX = 1.15 + z * 0.3;
  const scaleY = 0.28 - z * 0.08;
  const alpha  = 0.45 - z * 0.3;
  if (alpha <= 0) return;

  ctxV.save();
  ctxV.globalAlpha = alpha;
  const grad = ctxV.createRadialGradient(sx, sy, 0, sx, sy, r * scaleX);
  grad.addColorStop(0,   "rgba(0,0,0,0.9)");
  grad.addColorStop(0.5, "rgba(0,0,0,0.4)");
  grad.addColorStop(1,   "rgba(0,0,0,0)");
  ctxV.scale(1, scaleY / scaleX);
  const sy2 = sy * (scaleX / scaleY);
  ctxV.beginPath();
  ctxV.arc(sx, sy2, r * scaleX, 0, Math.PI*2);
  ctxV.fillStyle = grad;
  ctxV.fill();
  ctxV.restore();
}}

// ── Draw volumetric glow halo ─────────────────────────────────────────────────
function drawGlow(cx, cy, r, col, z) {{
  if (!CFG.showGlow) return;
  const {{r:cr, g:cg, b:cb}} = hexRgb(col);
  const glowR = r * (2.2 + z * 1.4);
  const alpha = 0.22 + z * 0.18;

  // Outer bloom
  const g1 = ctxB.createRadialGradient(cx,cy,r*0.5, cx,cy,glowR);
  g1.addColorStop(0,   `rgba(${{cr}},${{cg}},${{cb}},${{alpha.toFixed(2)}})`);
  g1.addColorStop(0.4, `rgba(${{cr}},${{cg}},${{cb}},${{(alpha*0.4).toFixed(2)}})`);
  g1.addColorStop(1,   `rgba(${{cr}},${{cg}},${{cb}},0)`);
  ctxB.beginPath();
  ctxB.arc(cx, cy, glowR, 0, Math.PI*2);
  ctxB.fillStyle = g1;
  ctxB.fill();

  // Tight inner ring glow
  const g2 = ctxB.createRadialGradient(cx,cy,r*0.8, cx,cy,r*1.5);
  g2.addColorStop(0, `rgba(${{Math.min(255,cr+80)}},${{Math.min(255,cg+80)}},${{Math.min(255,cb+100)}},0.35)`);
  g2.addColorStop(1, `rgba(${{cr}},${{cg}},${{cb}},0)`);
  ctxB.beginPath();
  ctxB.arc(cx, cy, r*1.5, 0, Math.PI*2);
  ctxB.fillStyle = g2;
  ctxB.fill();
}}

// ── Draw the real 3D Phong-shaded sphere ─────────────────────────────────────
function drawSphere(cx, cy, r, col, z) {{
  const {{r:cr, g:cg, b:cb}} = hexRgb(col);

  // ── Light position (upper-left, slightly toward viewer) ──
  const lx = cx - r * 0.55;
  const ly = cy - r * 0.55;

  // ── Ambient occlusion dark base ──
  ctxB.beginPath();
  ctxB.arc(cx, cy, r, 0, Math.PI*2);
  ctxB.fillStyle = `rgb(${{Math.max(0,cr-100)}},${{Math.max(0,cg-100)}},${{Math.max(0,cb-100)}})`;
  ctxB.fill();

  // ── Diffuse layer (Lambertian-ish radial from light) ──
  const diffuse = ctxB.createRadialGradient(lx, ly, r*0.01, cx, cy, r*1.05);
  diffuse.addColorStop(0,    `rgb(${{Math.min(255,cr+55)}},${{Math.min(255,cg+55)}},${{Math.min(255,cb+55)}})`);
  diffuse.addColorStop(0.45, `rgb(${{cr}},${{cg}},${{cb}})`);
  diffuse.addColorStop(0.75, `rgb(${{Math.max(0,cr-60)}},${{Math.max(0,cg-60)}},${{Math.max(0,cb-60)}})`);
  diffuse.addColorStop(1,    `rgb(${{Math.max(0,cr-110)}},${{Math.max(0,cg-110)}},${{Math.max(0,cb-110)}})`);
  ctxB.beginPath();
  ctxB.arc(cx, cy, r, 0, Math.PI*2);
  ctxB.fillStyle = diffuse;
  ctxB.fill();

  // ── Rim / back-light (blue-ish glow on dark side) ──
  const rim = ctxB.createRadialGradient(cx+r*0.4, cy+r*0.4, r*0.3, cx, cy, r*1.02);
  rim.addColorStop(0,   "rgba(0,0,0,0)");
  rim.addColorStop(0.7, "rgba(0,0,0,0)");
  rim.addColorStop(0.88,`rgba(${{Math.min(255,cr-30)}},${{Math.min(255,cg-10)}},${{Math.min(255,cb+80)}},0.55)`);
  rim.addColorStop(1,   "rgba(0,0,0,0)");
  ctxB.beginPath();
  ctxB.arc(cx, cy, r, 0, Math.PI*2);
  ctxB.fillStyle = rim;
  ctxB.fill();

  // ── Fresnel edge (subtle white ring) ──
  ctxB.beginPath();
  ctxB.arc(cx, cy, r, 0, Math.PI*2);
  ctxB.strokeStyle = `rgba(200,220,255,0.35)`;
  ctxB.lineWidth   = r * 0.045;
  ctxB.stroke();

  // ── Clip to sphere for highlights ──
  ctxB.save();
  ctxB.beginPath();
  ctxB.arc(cx, cy, r, 0, Math.PI*2);
  ctxB.clip();

  // ── Primary specular (Blinn): sharp white hotspot ──
  const sx1 = lx + r*0.06;
  const sy1 = ly + r*0.06;
  const sg1 = ctxB.createRadialGradient(sx1, sy1, 0, sx1, sy1, r*0.42);
  sg1.addColorStop(0,   "rgba(255,255,255,0.98)");
  sg1.addColorStop(0.18,"rgba(255,255,255,0.72)");
  sg1.addColorStop(0.45,"rgba(255,255,255,0.18)");
  sg1.addColorStop(1,   "rgba(255,255,255,0)");
  ctxB.beginPath();
  ctxB.arc(sx1, sy1, r*0.42, 0, Math.PI*2);
  ctxB.fillStyle = sg1;
  ctxB.fill();

  // ── Secondary specular: soft diffuse glow ──
  const sg2 = ctxB.createRadialGradient(lx+r*0.1, ly+r*0.1, 0, lx, ly, r*0.75);
  sg2.addColorStop(0,   "rgba(255,255,255,0.35)");
  sg2.addColorStop(0.5, "rgba(255,255,255,0.08)");
  sg2.addColorStop(1,   "rgba(255,255,255,0)");
  ctxB.beginPath();
  ctxB.arc(lx, ly, r*0.75, 0, Math.PI*2);
  ctxB.fillStyle = sg2;
  ctxB.fill();

  // ── Small tack highlight (tiny mirror point) ──
  const thx = lx + r*0.02, thy = ly + r*0.02;
  const tg = ctxB.createRadialGradient(thx,thy,0, thx,thy,r*0.12);
  tg.addColorStop(0,   "rgba(255,255,255,1)");
  tg.addColorStop(0.4, "rgba(255,255,255,0.6)");
  tg.addColorStop(1,   "rgba(255,255,255,0)");
  ctxB.beginPath();
  ctxB.arc(thx, thy, r*0.12, 0, Math.PI*2);
  ctxB.fillStyle = tg;
  ctxB.fill();

  ctxB.restore();

  // ── Contact shadow ring at base (pseudo-AO under ball) ──
  const aog = ctxB.createRadialGradient(cx,cy+r*0.82, r*0.1, cx, cy+r*0.82, r*0.7);
  aog.addColorStop(0,   "rgba(0,0,0,0.28)");
  aog.addColorStop(1,   "rgba(0,0,0,0)");
  ctxB.beginPath();
  ctxB.ellipse(cx, cy+r*0.82, r*0.7, r*0.22, 0, 0, Math.PI*2);
  ctxB.fillStyle = aog;
  ctxB.fill();
}}

// ── Draw face mesh overlays ───────────────────────────────────────────────────
function drawMesh(lms) {{
  if (!CFG.showMesh) return;
  // Oval
  ctxV.beginPath();
  FACE_OVAL.forEach((idx,i) => {{
    i===0 ? ctxV.moveTo(lms[idx].x*W, lms[idx].y*H)
           : ctxV.lineTo(lms[idx].x*W, lms[idx].y*H);
  }});
  ctxV.closePath();
  ctxV.strokeStyle = "rgba(60,80,180,0.45)";
  ctxV.lineWidth = 1.2;
  ctxV.stroke();

  // Eye contours
  [LEFT_EYE, RIGHT_EYE].forEach(eye => {{
    ctxV.beginPath();
    eye.forEach((idx,i) => {{
      i===0 ? ctxV.moveTo(lms[idx].x*W, lms[idx].y*H)
             : ctxV.lineTo(lms[idx].x*W, lms[idx].y*H);
    }});
    ctxV.closePath();
    ctxV.strokeStyle = "rgba(0,200,180,0.5)";
    ctxV.lineWidth = 1;
    ctxV.stroke();
  }});
}}

function drawIrisPts(lms) {{
  if (!CFG.showIris) return;
  [...LEFT_IRIS, ...RIGHT_IRIS].forEach(idx => {{
    ctxV.beginPath();
    ctxV.arc(lms[idx].x*W, lms[idx].y*H, 3.5, 0, Math.PI*2);
    ctxV.fillStyle = "#00ffaa";
    ctxV.fill();
  }});
}}

// ── FPS ───────────────────────────────────────────────────────────────────────
function tickFps() {{
  frameN++;
  const now = performance.now();
  if (now - lastFT >= 1000) {{
    fps = frameN; frameN = 0; lastFT = now;
    document.getElementById("hFps").textContent = fps;
  }}
}}

// ── Main render callback ──────────────────────────────────────────────────────
function onResults(res) {{
  // 1. Draw mirrored video on base canvas
  ctxV.save();
  ctxV.translate(W,0); ctxV.scale(-1,1);
  ctxV.drawImage(res.image, 0, 0, W, H);
  ctxV.restore();

  if (res.multiFaceLandmarks && res.multiFaceLandmarks.length > 0) {{
    detected = true;
    const lms = res.multiFaceLandmarks[0];

    drawMesh(lms);
    drawIrisPts(lms);

    // Iris center (already mirrored because canvas is flipped)
    const irisMid = (idxs) => {{
      let sx=0,sy=0;
      idxs.forEach(i=>{{ sx+=lms[i].x; sy+=lms[i].y; }});
      return [W - sx/idxs.length*W, sy/idxs.length*H];
    }};
    const [lx,ly] = irisMid(LEFT_IRIS);
    const [rx,ry] = irisMid(RIGHT_IRIS);
    const rawX = (lx+rx)/2, rawY = (ly+ry)/2;

    // Amplify from center
    let nx = Math.max(-1, Math.min(1, ((rawX/W)-0.5)*CFG.amplify));
    let ny = Math.max(-1, Math.min(1, ((rawY/H)-0.5)*CFG.amplify));
    const tX = (nx+1)/2*W;
    const tY = (ny+1)/2*H;

    // Z-axis: ball "pops out" more when gaze is near center
    const distFromCenter = Math.sqrt(nx*nx + ny*ny);
    const targetZ = Math.max(0, 1 - distFromCenter * 1.6);

    // EMA smooth
    const a = 1/CFG.smoothing;
    bx += a*(tX-bx); by += a*(tY-by); bz += a*(targetZ-bz);

    document.getElementById("dot").style.background = "#00ff88";
    document.getElementById("stTxt").textContent    = "TRACKING";
    document.getElementById("hX").textContent  = Math.round(bx);
    document.getElementById("hY").textContent  = Math.round(by);
    document.getElementById("hZ").textContent  = bz.toFixed(2);
  }} else {{
    detected = false;
    document.getElementById("dot").style.background = "#ff3333";
    document.getElementById("stTxt").textContent    = "Procurando rosto…";
  }}

  // 2. Dynamic radius and blur based on Z
  const popScale  = 1 + bz * (CFG.popEffect / 100);
  const dynRadius = CFG.ballRadius * popScale;
  const dynBlur   = CFG.blurAmount * (0.2 + bz * 0.8); // blurs MORE when ball is "close"

  // 3. Projected shadow BEFORE blur pass
  drawGroundShadow(bx, by, dynRadius, bz);

  // 4. Blur overlay pass
  drawBlurredBg(dynBlur);

  // 5. Ball layer — clear then draw
  ctxB.clearRect(0,0,W,H);
  drawGlow(bx, by, dynRadius, CFG.ballColor, bz);
  drawSphere(bx, by, dynRadius, CFG.ballColor, bz);

  tickFps();
}}

// ── Init MediaPipe ────────────────────────────────────────────────────────────
const faceMesh = new FaceMesh({{
  locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${{f}}`
}});
faceMesh.setOptions({{
  maxNumFaces: 1,
  refineLandmarks: true,
  minDetectionConfidence: 0.5,
  minTrackingConfidence: 0.5,
}});
faceMesh.onResults(onResults);

const camera = new Camera(vid, {{
  onFrame: async () => {{ await faceMesh.send({{image: vid}}); }},
  width: W, height: H,
}});

camera.start().then(() => {{
  document.getElementById("loader").style.display = "none";
  document.getElementById("wrap").style.display   = "block";
  document.getElementById("hud").style.display    = "flex";
}}).catch(err => {{
  document.getElementById("loader").innerHTML =
    `<span style="color:#ff6677">❌ Câmera: ${{err.message}}</span>`;
}});
</script>
</body>
</html>
"""

components.html(HTML, height=620, scrolling=False)

st.markdown("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("### 🔮 Efeito 3D Real")
    st.markdown(
        "A esfera usa shading **Phong + Blinn** com camadas separadas: "
        "ambient occlusion, difusão lambertiana, rim light azulado, "
        "Fresnel edge, specular primário, specular suave e tack highlight."
    )
with c2:
    st.markdown("### 📷 Depth of Field")
    st.markdown(
        "O background é desfocado com um **blur multi-pass radial** no Canvas. "
        "Quanto mais a bola está 'na frente' (olhar central), maior o desfoque, "
        "simulando a profundidade de campo de uma lente real."
    )
with c3:
    st.markdown("### 🚀 Efeito Z-Axis")
    st.markdown(
        "Quando o olhar está no **centro da tela**, a bola 'avança' para fora "
        "ficando maior, com mais glow e sombra mais fraca — "
        "como se estivesse saindo fisicamente do monitor."
    )
