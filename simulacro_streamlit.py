import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="👁️ Iris Ball 3D",
    page_icon="👁️",
    layout="wide",
)

with st.sidebar:
    st.markdown("## ⚙️ Controles")
    ball_radius  = st.slider("Raio base da bola",        25, 100,  52)
    smoothing    = st.slider("Suavização",                1,  30,   7)
    amplify      = st.slider("Amplificação do olhar",    10,  50,  26)
    pop_effect   = st.slider("Efeito 'saindo da tela'",   0,  60,  35)
    blur_amount  = st.slider("Desfoque do fundo",         0,  20,   9)

    st.markdown("### 🎨 Cores")
    ball_color   = st.color_picker("Cor base da bola",  "#2277ff")

    st.markdown("### 👁️ Reações")
    blink_boost  = st.slider("Força do pulso no piscar",  0, 100, 60)
    orient_color = st.checkbox("Mudar cor pela direção",   value=True)
    trail_on     = st.checkbox("Rastro de movimento",      value=True)
    shock_on     = st.checkbox("Onda de choque no piscar", value=True)

    st.markdown("### 🎯 Visual")
    show_mesh    = st.checkbox("Malha facial",             value=True)
    show_iris    = st.checkbox("Pontos da íris",           value=True)
    show_shadow  = st.checkbox("Sombra projetada",         value=True)
    show_glow    = st.checkbox("Halo de luz",              value=True)

    st.markdown("---")
    st.markdown("""
**Reações implementadas:**

👁️ **Piscar** → pulso de escala + onda de choque

↔️ **Olhar esq/dir** → cor muda para vermelho/azul  
↕️ **Olhar cima/baixo** → cor muda para amarelo/verde  
🎯 **Centro** → bola avança (Z-axis pop)  
💨 **Movimento rápido** → rastro de partículas
    """)

cfg = {
    "ballRadius" : ball_radius,
    "smoothing"  : smoothing,
    "amplify"    : amplify / 10.0,
    "popEffect"  : pop_effect,
    "blurAmount" : blur_amount,
    "ballColor"  : ball_color,
    "blinkBoost" : blink_boost / 100.0,
    "orientColor": str(orient_color).lower(),
    "trailOn"    : str(trail_on).lower(),
    "shockOn"    : str(shock_on).lower(),
    "showMesh"   : str(show_mesh).lower(),
    "showIris"   : str(show_iris).lower(),
    "showShadow" : str(show_shadow).lower(),
    "showGlow"   : str(show_glow).lower(),
}

st.markdown("# 👁️ Iris Ball 3D — Blink & Gaze Reactions")
st.markdown("A bola reage ao **piscar**, à **direção do olhar** e à **orientação dos olhos**.")

HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#050510; display:flex; flex-direction:column; align-items:center;
          font-family:'Segoe UI',sans-serif; }}
  #wrap {{ position:relative; margin-top:10px; border-radius:16px; overflow:hidden;
           box-shadow:0 0 60px #2277ff44, 0 0 20px #0008; border:1.5px solid #2277ff33; }}
  canvas {{ position:absolute; top:0; left:0; border-radius:16px; }}
  #cVideo {{ position:relative; }}
  #cBlur, #cBall {{ pointer-events:none; }}
  #hud {{ margin:8px 0 4px; display:flex; gap:14px; flex-wrap:wrap; justify-content:center;
          color:#aac4ff; font-size:12px; background:#0e0e20; border-radius:8px;
          padding:5px 14px; border:1px solid #2244aa44; max-width:640px; }}
  .hi {{ display:flex; align-items:center; gap:4px; }}
  #dot {{ width:9px;height:9px;border-radius:50%;background:#ff3333;transition:background .3s; }}
  #loader {{ color:#7eb8f7; font-size:15px; padding:28px 60px;
             background:#0e0e20; border-radius:14px; border:1px solid #333388; text-align:center; }}
  #blinkBar {{ display:flex; align-items:center; gap:6px; }}
  #earL,#earR {{ width:44px; height:6px; background:#333; border-radius:3px; overflow:hidden; }}
  #earLFill,#earRFill {{ height:100%; width:100%; background:#00ffaa; border-radius:3px;
                          transition:width .05s; }}
  video {{ display:none; }}

  /* Reaction badge */
  #badge {{ position:fixed; top:12px; right:14px; background:#1a1a3a; border:1px solid #4488ff;
            border-radius:10px; padding:6px 14px; color:#fff; font-size:14px; font-weight:bold;
            opacity:0; transition:opacity .2s; pointer-events:none; z-index:999; }}
</style>
</head>
<body>

<div id="badge"></div>
<div id="loader">⏳ Carregando MediaPipe FaceMesh…</div>

<div id="wrap" style="display:none">
  <canvas id="cVideo"></canvas>
  <canvas id="cBlur"></canvas>
  <canvas id="cBall"></canvas>
</div>

<div id="hud" style="display:none">
  <div class="hi"><span id="dot"></span><span id="stTxt">Iniciando…</span></div>
  <div class="hi">X:<b id="hX">—</b></div>
  <div class="hi">Y:<b id="hY">—</b></div>
  <div class="hi">Z:<b id="hZ">—</b></div>
  <div class="hi">Dir:<b id="hDir">—</b></div>
  <div class="hi">FPS:<b id="hFps">—</b></div>
  <div class="hi" id="blinkBar">
    L<div id="earL"><div id="earLFill"></div></div>
    R<div id="earR"><div id="earRFill"></div></div>
    EAR
  </div>
  <div class="hi">Piscadas:<b id="hBlink">0</b></div>
</div>

<video id="vid" autoplay playsinline></video>

<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js"       crossorigin="anonymous"></script>

<script>
// ── Config ────────────────────────────────────────────────────────────────────
const CFG = {{
  ballRadius  : {cfg["ballRadius"]},
  smoothing   : {cfg["smoothing"]},
  amplify     : {cfg["amplify"]},
  popEffect   : {cfg["popEffect"]},
  blurAmount  : {cfg["blurAmount"]},
  ballColor   : "{cfg["ballColor"]}",
  blinkBoost  : {cfg["blinkBoost"]},
  orientColor : {cfg["orientColor"]},
  trailOn     : {cfg["trailOn"]},
  shockOn     : {cfg["shockOn"]},
  showMesh    : {cfg["showMesh"]},
  showIris    : {cfg["showIris"]},
  showShadow  : {cfg["showShadow"]},
  showGlow    : {cfg["showGlow"]},
}};

// ── Landmark indices ──────────────────────────────────────────────────────────
const LEFT_IRIS   = [474,475,476,477];
const RIGHT_IRIS  = [469,470,471,472];
const FACE_OVAL   = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,
                     379,378,400,377,152,148,176,149,150,136,172,58,132,93,
                     234,127,162,21,54,103,67,109];
const LEFT_EYE    = [362,382,381,380,374,373,390,249,263,466,388,387,386,385,384,398];
const RIGHT_EYE   = [33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246];

// EAR points: [p1-top, p2-top, p3-bot, p4-bot, p5-left, p6-right] (6-point standard)
// Using MediaPipe indices for left eye vertical/horizontal
const L_EAR_PTS = [386, 374, 387, 373, 362, 263]; // top1,bot1,top2,bot2,left,right
const R_EAR_PTS = [159, 145, 160, 144, 33,  133];

// ── Canvas ────────────────────────────────────────────────────────────────────
const W=640, H=480;
const vid    = document.getElementById("vid");
const cVideo = document.getElementById("cVideo");
const cBlur  = document.getElementById("cBlur");
const cBall  = document.getElementById("cBall");
const ctxV   = cVideo.getContext("2d");
const ctxBl  = cBlur.getContext("2d");
const ctxB   = cBall.getContext("2d");
[cVideo,cBlur,cBall].forEach(c=>{{ c.width=W; c.height=H; }});
document.getElementById("wrap").style.cssText += `width:${{W}}px;height:${{H}}px`;

// ── State ─────────────────────────────────────────────────────────────────────
let bx=W/2, by=H/2, bz=0;
let prevBx=W/2, prevBy=H/2;
let frameN=0, lastFT=performance.now(), fps=0;

// Blink state
let blinkCount   = 0;
let blinkCooldown= 0;        // frames until next blink can register
const EAR_THRESH = 0.18;     // below this = eye closed
let blinkScale   = 1.0;      // current pulse scale
let blinkScaleV  = 0;        // velocity of pulse

// Shockwave state
let shocks = [];              // array of {{x,y,r,maxR,alpha,color}}

// Trail state
let trail = [];               // array of {{x,y,r,alpha,color}}

// Gaze direction / color
let currentColor  = CFG.ballColor;
let targetColor   = CFG.ballColor;
let gazeDir       = "center";

// Orientation: roll angle of eye line
let rollAngle     = 0;
let tiltScale     = {{x:1, y:1}};   // squash/stretch based on tilt

// Badge timer
let badgeTimer = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────
function dist(a,b) {{
  const dx=a.x-b.x, dy=a.y-b.y;
  return Math.sqrt(dx*dx+dy*dy);
}}

function hexRgb(h) {{
  return {{ r:parseInt(h.slice(1,3),16), g:parseInt(h.slice(3,5),16), b:parseInt(h.slice(5,7),16) }};
}}

function rgbHex(r,g,b) {{
  return "#"+[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,"0")).join("");
}}

function lerpColor(a, b, t) {{
  const ca=hexRgb(a), cb=hexRgb(b);
  return rgbHex(ca.r+(cb.r-ca.r)*t, ca.g+(cb.g-ca.g)*t, ca.b+(cb.b-ca.b)*t);
}}

// ── EAR calculation ───────────────────────────────────────────────────────────
// EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)  (6-point Soukupova formula)
function calcEAR(lms, pts) {{
  const p = pts.map(i => ({{ x: lms[i].x*W, y: lms[i].y*H }}));
  const top1 = dist(p[0],p[1]);
  const top2 = dist(p[2],p[3]);
  const horiz= dist(p[4],p[5]);
  return (top1+top2) / (2*horiz + 1e-6);
}}

// ── Badge flash ───────────────────────────────────────────────────────────────
function showBadge(text, color="#4488ff") {{
  const b = document.getElementById("badge");
  b.textContent   = text;
  b.style.color   = color;
  b.style.borderColor = color;
  b.style.opacity = "1";
  badgeTimer = 45;
}}

// ── Direction color mapping ───────────────────────────────────────────────────
const DIR_COLORS = {{
  left   : "#ff4422",
  right  : "#2288ff",
  up     : "#ffdd00",
  down   : "#00dd66",
  center : CFG.ballColor,
}};

function getGazeDir(nx, ny) {{
  const absX = Math.abs(nx), absY = Math.abs(ny);
  if (absX < 0.25 && absY < 0.25) return "center";
  if (absX > absY) return nx < 0 ? "left" : "right";
  return ny < 0 ? "up" : "down";
}}

// ── Shockwave ─────────────────────────────────────────────────────────────────
function spawnShock(x,y,color) {{
  if (!CFG.shockOn) return;
  shocks.push({{ x, y, r:0, maxR: CFG.ballRadius*3.5, alpha:0.9, color }});
}}

function updateShocks() {{
  shocks = shocks.filter(s => s.alpha > 0.01);
  shocks.forEach(s => {{
    s.r    += (s.maxR - s.r) * 0.12;
    s.alpha *= 0.84;
  }});
}}

function drawShocks() {{
  shocks.forEach(s => {{
    const {{r:cr,g:cg,b:cb}} = hexRgb(s.color);
    ctxB.save();
    ctxB.globalAlpha = s.alpha;
    ctxB.beginPath();
    ctxB.arc(s.x, s.y, s.r, 0, Math.PI*2);
    ctxB.strokeStyle = `rgb(${{cr}},${{cg}},${{cb}})`;
    ctxB.lineWidth   = 3.5 * s.alpha;
    ctxB.shadowColor = `rgba(${{cr}},${{cg}},${{cb}},0.8)`;
    ctxB.shadowBlur  = 18;
    ctxB.stroke();
    ctxB.restore();
  }});
}}

// ── Trail ─────────────────────────────────────────────────────────────────────
function updateTrail(x,y,r,color) {{
  if (!CFG.trailOn) return;
  trail.push({{ x, y, r:r*0.65, alpha:0.55, color }});
  if (trail.length > 22) trail.shift();
  trail.forEach(t => {{ t.alpha *= 0.80; t.r *= 0.94; }});
  trail = trail.filter(t => t.alpha > 0.03);
}}

function drawTrail() {{
  if (!CFG.trailOn) return;
  trail.forEach((t,i) => {{
    const {{r:cr,g:cg,b:cb}} = hexRgb(t.color);
    ctxB.save();
    ctxB.globalAlpha = t.alpha;
    const g = ctxB.createRadialGradient(t.x,t.y,0, t.x,t.y, t.r);
    g.addColorStop(0,   `rgba(${{cr}},${{cg}},${{cb}},0.8)`);
    g.addColorStop(0.5, `rgba(${{cr}},${{cg}},${{cb}},0.3)`);
    g.addColorStop(1,   `rgba(${{cr}},${{cg}},${{cb}},0)`);
    ctxB.beginPath();
    ctxB.arc(t.x, t.y, t.r, 0, Math.PI*2);
    ctxB.fillStyle = g;
    ctxB.fill();
    ctxB.restore();
  }});
}}

// ── Ground shadow ─────────────────────────────────────────────────────────────
function drawGroundShadow(cx,cy,r,z) {{
  if (!CFG.showShadow) return;
  const sy = cy + r*0.9 + z*18;
  const sx = cx + r*0.15;
  const alpha = 0.45 - z*0.3;
  if (alpha<=0) return;
  ctxV.save();
  ctxV.globalAlpha = alpha;
  const grad = ctxV.createRadialGradient(sx,sy,0, sx,sy,r*1.3);
  grad.addColorStop(0,   "rgba(0,0,0,0.9)");
  grad.addColorStop(0.5, "rgba(0,0,0,0.35)");
  grad.addColorStop(1,   "rgba(0,0,0,0)");
  ctxV.scale(1, 0.25);
  ctxV.beginPath();
  ctxV.arc(sx, sy*4, r*1.3, 0, Math.PI*2);
  ctxV.fillStyle = grad;
  ctxV.fill();
  ctxV.restore();
}}

// ── DOF blur ──────────────────────────────────────────────────────────────────
function drawBlurredBg(blurPx) {{
  ctxBl.clearRect(0,0,W,H);
  if (blurPx<=0) return;
  ctxBl.globalAlpha = 0.18;
  for (let i=0;i<8;i++) {{
    const angle = (i/8)*Math.PI*2;
    ctxBl.drawImage(cVideo, Math.cos(angle)*blurPx*0.5, Math.sin(angle)*blurPx*0.5);
  }}
  ctxBl.globalAlpha = 0.55;
  ctxBl.drawImage(cVideo,0,0);
  ctxBl.globalAlpha = 1;
  const vig = ctxBl.createRadialGradient(W/2,H/2,H*0.2, W/2,H/2,H*0.85);
  vig.addColorStop(0, "rgba(0,0,0,0)");
  vig.addColorStop(1, "rgba(0,0,10,0.72)");
  ctxBl.fillStyle = vig;
  ctxBl.fillRect(0,0,W,H);
}}

// ── Glow ─────────────────────────────────────────────────────────────────────
function drawGlow(cx,cy,r,col,z) {{
  if (!CFG.showGlow) return;
  const {{r:cr,g:cg,b:cb}} = hexRgb(col);
  const glowR = r*(2.2+z*1.4);
  const alpha = 0.22+z*0.18;
  const g1 = ctxB.createRadialGradient(cx,cy,r*0.5, cx,cy,glowR);
  g1.addColorStop(0,   `rgba(${{cr}},${{cg}},${{cb}},${{alpha.toFixed(2)}})`);
  g1.addColorStop(0.4, `rgba(${{cr}},${{cg}},${{cb}},${{(alpha*0.4).toFixed(2)}})`);
  g1.addColorStop(1,   `rgba(${{cr}},${{cg}},${{cb}},0)`);
  ctxB.beginPath(); ctxB.arc(cx,cy,glowR,0,Math.PI*2);
  ctxB.fillStyle = g1; ctxB.fill();
}}

// ── 3D Phong Sphere ───────────────────────────────────────────────────────────
function drawSphere(cx,cy,r,col,z,roll) {{
  const {{r:cr,g:cg,b:cb}} = hexRgb(col);

  // Apply roll tilt as skew transform
  ctxB.save();
  ctxB.translate(cx,cy);
  ctxB.rotate(roll * 0.18);   // subtle skew based on head/eye roll
  ctxB.translate(-cx,-cy);

  // Ambient base
  ctxB.beginPath(); ctxB.arc(cx,cy,r,0,Math.PI*2);
  ctxB.fillStyle=`rgb(${{Math.max(0,cr-100)}},${{Math.max(0,cg-100)}},${{Math.max(0,cb-100)}})`;
  ctxB.fill();

  // Diffuse
  const lx=cx-r*0.55, ly=cy-r*0.55;
  const diff = ctxB.createRadialGradient(lx,ly,r*0.01, cx,cy,r*1.05);
  diff.addColorStop(0,   `rgb(${{Math.min(255,cr+55)}},${{Math.min(255,cg+55)}},${{Math.min(255,cb+55)}})`);
  diff.addColorStop(0.45,`rgb(${{cr}},${{cg}},${{cb}})`);
  diff.addColorStop(0.75,`rgb(${{Math.max(0,cr-60)}},${{Math.max(0,cg-60)}},${{Math.max(0,cb-60)}})`);
  diff.addColorStop(1,   `rgb(${{Math.max(0,cr-110)}},${{Math.max(0,cg-110)}},${{Math.max(0,cb-110)}})`);
  ctxB.beginPath(); ctxB.arc(cx,cy,r,0,Math.PI*2);
  ctxB.fillStyle=diff; ctxB.fill();

  // Rim
  const rim = ctxB.createRadialGradient(cx+r*0.4,cy+r*0.4,r*0.3, cx,cy,r*1.02);
  rim.addColorStop(0,   "rgba(0,0,0,0)");
  rim.addColorStop(0.7, "rgba(0,0,0,0)");
  rim.addColorStop(0.88,`rgba(${{Math.max(0,cr-30)}},${{Math.max(0,cg-10)}},${{Math.min(255,cb+80)}},0.55)`);
  rim.addColorStop(1,   "rgba(0,0,0,0)");
  ctxB.beginPath(); ctxB.arc(cx,cy,r,0,Math.PI*2);
  ctxB.fillStyle=rim; ctxB.fill();

  // Fresnel
  ctxB.beginPath(); ctxB.arc(cx,cy,r,0,Math.PI*2);
  ctxB.strokeStyle="rgba(200,220,255,0.35)";
  ctxB.lineWidth=r*0.045; ctxB.stroke();

  // Clip for highlights
  ctxB.save();
  ctxB.beginPath(); ctxB.arc(cx,cy,r,0,Math.PI*2); ctxB.clip();

  // Primary specular
  const sx1=lx+r*0.06, sy1=ly+r*0.06;
  const sg1=ctxB.createRadialGradient(sx1,sy1,0, sx1,sy1,r*0.42);
  sg1.addColorStop(0,   "rgba(255,255,255,0.98)");
  sg1.addColorStop(0.18,"rgba(255,255,255,0.72)");
  sg1.addColorStop(0.45,"rgba(255,255,255,0.18)");
  sg1.addColorStop(1,   "rgba(255,255,255,0)");
  ctxB.beginPath(); ctxB.arc(sx1,sy1,r*0.42,0,Math.PI*2);
  ctxB.fillStyle=sg1; ctxB.fill();

  // Soft specular
  const sg2=ctxB.createRadialGradient(lx+r*0.1,ly+r*0.1,0, lx,ly,r*0.75);
  sg2.addColorStop(0, "rgba(255,255,255,0.35)");
  sg2.addColorStop(0.5,"rgba(255,255,255,0.08)");
  sg2.addColorStop(1,  "rgba(255,255,255,0)");
  ctxB.beginPath(); ctxB.arc(lx,ly,r*0.75,0,Math.PI*2);
  ctxB.fillStyle=sg2; ctxB.fill();

  // Tack highlight
  const tg=ctxB.createRadialGradient(lx+r*0.02,ly+r*0.02,0, lx+r*0.02,ly+r*0.02,r*0.12);
  tg.addColorStop(0,"rgba(255,255,255,1)");
  tg.addColorStop(0.4,"rgba(255,255,255,0.6)");
  tg.addColorStop(1,"rgba(255,255,255,0)");
  ctxB.beginPath(); ctxB.arc(lx+r*0.02,ly+r*0.02,r*0.12,0,Math.PI*2);
  ctxB.fillStyle=tg; ctxB.fill();

  ctxB.restore(); // clip restore
  ctxB.restore(); // roll restore

  // AO ring
  const aog=ctxB.createRadialGradient(cx,cy+r*0.82,r*0.1, cx,cy+r*0.82,r*0.7);
  aog.addColorStop(0,"rgba(0,0,0,0.28)"); aog.addColorStop(1,"rgba(0,0,0,0)");
  ctxB.beginPath();
  ctxB.ellipse(cx,cy+r*0.82,r*0.7,r*0.22,0,0,Math.PI*2);
  ctxB.fillStyle=aog; ctxB.fill();
}}

// ── Face mesh overlays ────────────────────────────────────────────────────────
function drawMeshOverlay(lms) {{
  if (!CFG.showMesh) return;
  ctxV.beginPath();
  FACE_OVAL.forEach((idx,i)=>{{
    i===0?ctxV.moveTo(lms[idx].x*W,lms[idx].y*H):ctxV.lineTo(lms[idx].x*W,lms[idx].y*H);
  }});
  ctxV.closePath();
  ctxV.strokeStyle="rgba(60,80,180,0.4)"; ctxV.lineWidth=1.2; ctxV.stroke();

  [LEFT_EYE,RIGHT_EYE].forEach(eye=>{{
    ctxV.beginPath();
    eye.forEach((idx,i)=>{{
      i===0?ctxV.moveTo(lms[idx].x*W,lms[idx].y*H):ctxV.lineTo(lms[idx].x*W,lms[idx].y*H);
    }});
    ctxV.closePath();
    ctxV.strokeStyle="rgba(0,200,180,0.5)"; ctxV.lineWidth=1; ctxV.stroke();
  }});
}}

function drawIrisPts(lms) {{
  if (!CFG.showIris) return;
  [...LEFT_IRIS,...RIGHT_IRIS].forEach(idx=>{{
    ctxV.beginPath();
    ctxV.arc(lms[idx].x*W, lms[idx].y*H, 3.5, 0, Math.PI*2);
    ctxV.fillStyle="#00ffaa"; ctxV.fill();
  }});
}}

// ── FPS ───────────────────────────────────────────────────────────────────────
function tickFps() {{
  frameN++;
  const now=performance.now();
  if (now-lastFT>=1000) {{
    fps=frameN; frameN=0; lastFT=now;
    document.getElementById("hFps").textContent=fps;
  }}
}}

// ── Main render callback ──────────────────────────────────────────────────────
function onResults(res) {{
  // Draw mirrored video
  ctxV.save();
  ctxV.translate(W,0); ctxV.scale(-1,1);
  ctxV.drawImage(res.image,0,0,W,H);
  ctxV.restore();

  if (res.multiFaceLandmarks && res.multiFaceLandmarks.length>0) {{
    const lms = res.multiFaceLandmarks[0];

    drawMeshOverlay(lms);
    drawIrisPts(lms);

    // ── EAR blink detection ──────────────────────────────────────────────────
    const earL = calcEAR(lms, L_EAR_PTS);
    const earR = calcEAR(lms, R_EAR_PTS);
    const earAvg = (earL+earR)/2;

    // Update EAR bars
    document.getElementById("earLFill").style.width = Math.min(1,earL/0.3)*100+"%";
    document.getElementById("earRFill").style.width = Math.min(1,earR/0.3)*100+"%";
    // Color red when closed
    const earColor = earAvg < EAR_THRESH ? "#ff3344" : "#00ffaa";
    document.getElementById("earLFill").style.background = earColor;
    document.getElementById("earRFill").style.background = earColor;

    if (earAvg < EAR_THRESH && blinkCooldown<=0) {{
      // BLINK DETECTED
      blinkCount++;
      blinkCooldown = 18;
      // Pulse the ball outward
      blinkScaleV = 0.55 * CFG.blinkBoost + 0.05;
      // Shockwave at ball position
      spawnShock(bx, by, currentColor);
      showBadge("👁️ PISCOU!", "#ff88aa");
      document.getElementById("hBlink").textContent = blinkCount;
    }}
    if (blinkCooldown>0) blinkCooldown--;

    // ── Eye roll / tilt angle ────────────────────────────────────────────────
    // Vector from right eye center to left eye center
    const reC = RIGHT_IRIS.reduce((a,i)=>{{a.x+=lms[i].x;a.y+=lms[i].y;return a;}},{{x:0,y:0}});
    const leC = LEFT_IRIS.reduce((a,i)=>{{a.x+=lms[i].x;a.y+=lms[i].y;return a;}},{{x:0,y:0}});
    reC.x/=4; reC.y/=4; leC.x/=4; leC.y/=4;
    rollAngle = Math.atan2(leC.y - reC.y, leC.x - reC.x);  // radians

    // ── Iris center (mirrored) ────────────────────────────────────────────────
    const irisMid = (idxs)=>{{
      let sx=0,sy=0;
      idxs.forEach(i=>{{sx+=lms[i].x;sy+=lms[i].y;}});
      return [W-sx/idxs.length*W, sy/idxs.length*H];
    }};
    const [lx,ly]=irisMid(LEFT_IRIS);
    const [rx,ry]=irisMid(RIGHT_IRIS);
    const rawX=(lx+rx)/2, rawY=(ly+ry)/2;

    // Amplify
    let nx=Math.max(-1,Math.min(1,((rawX/W)-0.5)*CFG.amplify));
    let ny=Math.max(-1,Math.min(1,((rawY/H)-0.5)*CFG.amplify));

    // ── Gaze direction & color ────────────────────────────────────────────────
    const dir = getGazeDir(nx,ny);
    if (dir !== gazeDir) {{
      gazeDir = dir;
      if (CFG.orientColor) {{
        targetColor = DIR_COLORS[dir] || CFG.ballColor;
        if (dir!=="center") showBadge(
          dir==="left"  ? "👈 ESQUERDA" :
          dir==="right" ? "👉 DIREITA"  :
          dir==="up"    ? "👆 CIMA"     : "👇 BAIXO",
          targetColor
        );
      }}
    }}
    // Lerp color smoothly
    currentColor = lerpColor(currentColor, targetColor, 0.08);
    DIR_COLORS.center = CFG.ballColor;   // keep center color in sync with picker

    // ── Smooth ball position ──────────────────────────────────────────────────
    const tX=(nx+1)/2*W, tY=(ny+1)/2*H;
    const distFromCenter=Math.sqrt(nx*nx+ny*ny);
    const targetZ=Math.max(0,1-distFromCenter*1.6);
    const a=1/CFG.smoothing;
    prevBx=bx; prevBy=by;
    bx+=a*(tX-bx); by+=a*(tY-by); bz+=a*(targetZ-bz);

    document.getElementById("dot").style.background="#00ff88";
    document.getElementById("stTxt").textContent="TRACKING";
    document.getElementById("hX").textContent=Math.round(bx);
    document.getElementById("hY").textContent=Math.round(by);
    document.getElementById("hZ").textContent=bz.toFixed(2);
    document.getElementById("hDir").textContent=gazeDir.toUpperCase();

  }} else {{
    document.getElementById("dot").style.background="#ff3333";
    document.getElementById("stTxt").textContent="Procurando rosto…";
    document.getElementById("hDir").textContent="—";
  }}

  // ── Blink scale physics (spring) ─────────────────────────────────────────
  blinkScale  += blinkScaleV;
  blinkScaleV += (1.0 - blinkScale) * 0.28;   // spring to 1.0
  blinkScaleV *= 0.72;                          // damping
  blinkScale   = Math.max(0.5, blinkScale);

  // ── Pop + blink combined radius ──────────────────────────────────────────
  const popScale  = 1 + bz*(CFG.popEffect/100);
  const dynRadius = CFG.ballRadius * popScale * blinkScale;
  const dynBlur   = CFG.blurAmount*(0.2+bz*0.8);

  // ── Velocity → trail ─────────────────────────────────────────────────────
  const speed = Math.sqrt((bx-prevBx)**2+(by-prevBy)**2);
  if (speed > 1.5) updateTrail(bx, by, dynRadius, currentColor);

  // ── Shadow ───────────────────────────────────────────────────────────────
  drawGroundShadow(bx, by, dynRadius, bz);

  // ── Blur background ───────────────────────────────────────────────────────
  drawBlurredBg(dynBlur);

  // ── Ball layer ────────────────────────────────────────────────────────────
  ctxB.clearRect(0,0,W,H);
  updateShocks();
  drawShocks();
  drawTrail();
  drawGlow(bx, by, dynRadius, currentColor, bz);
  drawSphere(bx, by, dynRadius, currentColor, bz, rollAngle);

  // Badge fade
  if (badgeTimer>0) {{
    badgeTimer--;
    if (badgeTimer===0) document.getElementById("badge").style.opacity="0";
  }}

  tickFps();
}}

// ── MediaPipe init ────────────────────────────────────────────────────────────
const faceMesh = new FaceMesh({{
  locateFile: f=>`https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${{f}}`
}});
faceMesh.setOptions({{
  maxNumFaces:1, refineLandmarks:true,
  minDetectionConfidence:0.5, minTrackingConfidence:0.5,
}});
faceMesh.onResults(onResults);

const camera = new Camera(vid,{{
  onFrame: async()=>{{ await faceMesh.send({{image:vid}}); }},
  width:W, height:H,
}});
camera.start().then(()=>{{
  document.getElementById("loader").style.display="none";
  document.getElementById("wrap").style.display="block";
  document.getElementById("hud").style.display="flex";
}}).catch(err=>{{
  document.getElementById("loader").innerHTML=
    `<span style="color:#ff6677">❌ Câmera: ${{err.message}}</span>`;
}});
</script>
</body>
</html>
"""

components.html(HTML, height=640, scrolling=False)

st.markdown("---")
c1,c2,c3,c4 = st.columns(4)
with c1:
    st.markdown("### 👁️ Piscar")
    st.markdown("Detectado via **EAR** (Eye Aspect Ratio). Quando a razão altura/largura do olho cai abaixo de 0.18, registra piscar, dispara pulso de escala com física de mola e onda de choque.")
with c2:
    st.markdown("### 🧭 Direção")
    st.markdown("A posição normalizada da íris define a direção: **esquerda→vermelho, direita→azul, cima→amarelo, baixo→verde**. Cor interpola suavemente com lerp.")
with c3:
    st.markdown("### 🌀 Roll do Olho")
    st.markdown("O ângulo do vetor entre as duas íris define o **roll**. A bola rotaciona sutilmente acompanhando a inclinação natural da cabeça/olho.")
with c4:
    st.markdown("### 💨 Rastro")
    st.markdown("Partículas de trail só aparecem quando há **velocidade > 1.5px/frame**. Cada partícula tem raio, alpha e cor independentes com decay exponencial.")
