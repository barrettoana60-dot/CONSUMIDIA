import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sala 3D – Face Tracking Parallax", layout="wide")

st.title("Sala 3D com Face Tracking + Parallax")
st.caption("Tracking facial mais estável, blink recalibrado de forma adaptativa e efeito de parallax com profundidade. 1 piscar aproxima, 2 piscadas rápidas afastam. A piscada agora usa detecção adaptativa e resolução pendente mais confiável.")

HTML_APP = r"""
<div id="eye-room-root">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;800&family=JetBrains+Mono:wght@400;600&display=swap');
  :root{
    --bg:#060d1a;
    --panel:rgba(8,14,28,.9);
    --border:rgba(255,255,255,.07);
    --text:#e8f0ff;
    --muted:#7a90b8;
    --ok:#2ecc71;
    --warn:#f39c12;
    --danger:#e74c3c;
    --cyan:#5dade2;
    --violet:#a569bd;
    --gold:#f0c040;
    font-family:'Space Grotesk',ui-sans-serif,system-ui,sans-serif;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:transparent}
  #eye-room-root{
    width:100%;min-height:1200px;
    color:var(--text);padding:16px;border-radius:20px;overflow:hidden;
    background:
      radial-gradient(ellipse 80% 40% at 20% 0%, rgba(93,173,226,.08) 0%, transparent 55%),
      radial-gradient(ellipse 60% 40% at 80% 100%, rgba(165,105,189,.08) 0%, transparent 55%),
      linear-gradient(180deg,#060d1a 0%,#030810 100%);
    border:1px solid rgba(255,255,255,.05);
  }
  /* ── TOPBAR ── */
  .topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:14px;flex-wrap:wrap}
  .headline h2{font-size:24px;font-weight:800;letter-spacing:-.4px}
  .headline p{margin-top:5px;color:var(--muted);font-size:13px;line-height:1.5;max-width:800px}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .btn{
    border:1px solid rgba(255,255,255,.1);
    background:rgba(255,255,255,.06);
    color:var(--text);padding:9px 14px;border-radius:12px;
    font-weight:700;font-size:13px;cursor:pointer;
    transition:.18s ease;user-select:none;
    font-family:'Space Grotesk',sans-serif;
  }
  .btn:hover{transform:translateY(-1px);border-color:rgba(93,173,226,.5);background:rgba(93,173,226,.12)}
  .btn.primary{background:rgba(93,173,226,.18);border-color:rgba(93,173,226,.4)}
  .btn.warn{background:rgba(243,156,18,.15);border-color:rgba(243,156,18,.4)}
  .btn.subtle{background:rgba(165,105,189,.14);border-color:rgba(165,105,189,.35)}
  .btn.danger{background:rgba(231,76,60,.14);border-color:rgba(231,76,60,.35)}
  /* ── LAYOUT ── */
  .layout{display:grid;grid-template-columns:minmax(0,1.72fr) 330px;gap:14px;min-height:980px}
  /* ── SCENE PANEL ── */
  .scene-panel{
    border:1px solid var(--border);border-radius:18px;overflow:hidden;
    position:relative;min-height:920px;
    box-shadow:0 24px 60px rgba(0,0,0,.35);
  }
  #scene-shell{position:absolute;inset:0}
  #room,#heatmap,#reveal{position:absolute;inset:0;width:100%;height:100%;display:block}
  #heatmap,#reveal{pointer-events:none}
  /* ── GAZE CURSOR ── */
  #gaze-cursor{
    position:absolute;width:26px;height:26px;
    border:2px solid rgba(255,255,255,.92);border-radius:50%;
    box-shadow:0 0 0 6px rgba(93,173,226,.14),0 0 20px rgba(93,173,226,.3);
    transform:translate(-50%,-50%);pointer-events:none;z-index:6;
    left:50%;top:50%;
    transition:width .1s,height .1s,border-color .1s;
  }
  #gaze-cursor::after{content:"";position:absolute;inset:5px;border-radius:50%;background:rgba(255,255,255,.8)}
  /* ── CHIPS ── */
  .chip{
    position:absolute;z-index:7;
    display:inline-flex;align-items:center;gap:7px;
    padding:8px 12px;border-radius:999px;
    background:rgba(6,13,26,.8);
    border:1px solid rgba(255,255,255,.08);
    color:var(--muted);font-size:12px;backdrop-filter:blur(12px);
  }
  .chip strong{color:var(--text)}
  #statusChip{top:14px;left:14px}
  #modeChip{top:14px;left:182px}
  #blinkChip{top:14px;left:316px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--danger);box-shadow:0 0 14px rgba(231,76,60,.4)}
  .dot.on{background:var(--ok);box-shadow:0 0 14px rgba(46,204,113,.4)}
  /* ── DWELL METER ── */
  .meter{
    position:absolute;top:14px;right:14px;z-index:7;
    width:200px;padding:10px 12px;border-radius:14px;
    background:rgba(6,13,26,.8);border:1px solid rgba(255,255,255,.08);
  }
  .meter .label{font-size:11px;color:var(--muted);margin-bottom:6px;font-family:'JetBrains Mono',monospace}
  .bar{width:100%;height:8px;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden}
  .bar>div{width:0%;height:100%;border-radius:999px;background:linear-gradient(90deg,#5dade2 0%,#a569bd 100%);transition:width .05s}
  /* ── BLINK INDICATOR ── */
  #blink-indicator{
    position:absolute;bottom:16px;left:50%;transform:translateX(-50%);z-index:7;
    padding:8px 16px;border-radius:999px;
    background:rgba(6,13,26,.85);border:1px solid rgba(93,173,226,.25);
    font-size:12px;color:var(--muted);
    font-family:'JetBrains Mono',monospace;
    opacity:0;transition:opacity .3s;
  }
  #blink-indicator.show{opacity:1}
  /* ── PERMISSION NOTE ── */
  #permission-note{
    position:absolute;left:14px;bottom:14px;z-index:7;max-width:66%;
    padding:9px 13px;border-radius:12px;
    background:rgba(6,13,26,.85);border:1px solid rgba(255,255,255,.07);
    color:var(--muted);font-size:12px;line-height:1.4;
  }
  /* ── SIDEBAR ── */
  .sidebar{display:flex;flex-direction:column;gap:12px;overflow:hidden}
  .card{
    background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.07);
    border-radius:16px;padding:14px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.03);
  }
  .card h3{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}
  #video{
    width:100%;aspect-ratio:16/10;object-fit:cover;
    border-radius:12px;border:1px solid rgba(255,255,255,.07);
    background:#020609;transform:scaleX(-1);
  }
  /* ── STATS ── */
  .stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .stat{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:10px}
  .stat .k{font-size:11px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.4px}
  .stat .v{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
  .meta-line{
    display:flex;justify-content:space-between;gap:8px;
    border-bottom:1px solid rgba(255,255,255,.05);
    padding:7px 0;color:var(--muted);font-size:12px;
  }
  .meta-line:last-child{border-bottom:none}
  .meta-line strong{color:var(--text);font-size:12px}
  /* ── SELECTED ARTWORK ── */
  #selected-title{font-size:17px;font-weight:800;margin-bottom:4px;line-height:1.2}
  #selected-artist{color:var(--cyan);font-size:12px;font-weight:700;margin-bottom:8px}
  #selected-description{color:var(--muted);line-height:1.5;font-size:12.5px}
  /* ── ARTWORK LIST ── */
  #artwork-list{display:grid;gap:8px;max-height:240px;overflow:auto}
  #artwork-list::-webkit-scrollbar{width:4px}
  #artwork-list::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:4px}
  .art-row{
    display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:center;
    background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);
    border-radius:12px;padding:10px;cursor:pointer;transition:.15s ease;
  }
  .art-row:hover{border-color:rgba(93,173,226,.3);background:rgba(93,173,226,.06)}
  .art-bullet{width:12px;height:12px;border-radius:50%}
  .art-title{font-size:13px;font-weight:700;margin-bottom:2px}
  .art-sub{color:var(--muted);font-size:11px}
  .badge{
    font-size:10px;font-weight:700;color:#bfd6f6;
    background:rgba(93,173,226,.12);border:1px solid rgba(93,173,226,.2);
    padding:4px 8px;border-radius:999px;white-space:nowrap;
  }
  /* ── BLINK GUIDE ── */
  .blink-guide{
    display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px;
  }
  .blink-card{
    background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);
    border-radius:10px;padding:8px;text-align:center;
  }
  .blink-card .icon{font-size:18px;margin-bottom:3px}
  .blink-card .bl{font-size:11px;font-weight:700;margin-bottom:2px}
  .blink-card .desc{font-size:10.5px;color:var(--muted)}
  /* ── LOG ── */
  #logBox{
    min-height:100px;max-height:150px;overflow:auto;border-radius:10px;padding:8px;
    background:rgba(2,6,15,.7);border:1px solid rgba(255,255,255,.06);
    color:var(--muted);font-family:'JetBrains Mono',monospace;
    font-size:11px;line-height:1.4;white-space:pre-wrap;
  }
  #logBox::-webkit-scrollbar{width:3px}
  #logBox::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}
  .small-note{color:var(--muted);font-size:11.5px;line-height:1.4;margin-top:7px}
  @media(max-width:1080px){
    .layout{grid-template-columns:1fr}
    .scene-panel{min-height:640px}
    #eye-room-root{min-height:1400px}
    .topbar{flex-direction:column}
    #modeChip,#blinkChip{top:50px}
    #modeChip{left:14px}
    #blinkChip{left:160px}
    .meter{top:86px;right:14px}
  }
</style>

<!-- TOPBAR -->
<div class="topbar">
  <div class="headline">
    <h2>🎨 Sala 3D – Face Tracking + Parallax</h2>
    <p>Tracking pelo rosto com filtragem mais estável, blink adaptativo, parallax multicamada e zoom por piscadas mais confiável. <strong>1 piscar</strong> → aproxima a obra em foco &nbsp;|&nbsp; <strong>2 piscadas rápidas</strong> → afasta o zoom.</p>
  </div>
  <div class="controls">
    <button class="btn primary" id="startBtn">▶ Iniciar tracking</button>
    <button class="btn warn" id="calibrateBtn">⊕ Calibrar</button>
    <button class="btn subtle" id="invertXBtn">↔ Inverter X</button>
    <button class="btn subtle" id="resetHeatBtn">⬡ Limpar heatmap</button>
    <button class="btn" id="exportPdfBtn">↓ Exportar PDF</button>
    <button class="btn danger" id="stopBtn">■ Parar</button>
  </div>
</div>

<!-- MAIN LAYOUT -->
<div class="layout">
  <!-- SCENE -->
  <div class="scene-panel">
    <div id="scene-shell">
      <canvas id="room"></canvas>
      <canvas id="heatmap"></canvas>
      <canvas id="reveal"></canvas>
      <div id="gaze-cursor"></div>

      <div class="chip" id="statusChip"><span id="statusDot" class="dot"></span><span id="statusText">Aguardando</span></div>
      <div class="chip" id="modeChip">Modo: <strong id="modeText">Cena ativa</strong></div>
      <div class="chip" id="blinkChip">👁 Blink: <strong id="blinkText">Calibrando</strong></div>

      <div class="meter">
        <div class="label">Dwell-click</div>
        <div class="bar"><div id="dwellFill"></div></div>
      </div>

      <div id="blink-indicator">👁 Blink detectado</div>
      <div id="permission-note">Sala carregada. Clique em "Iniciar tracking" para webcam. O eixo lateral foi ajustado para não inverter; se o seu aparelho reagir diferente, use “Inverter X”.</div>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">
    <div class="card">
      <h3>Câmera</h3>
      <video id="video" autoplay playsinline muted></video>
      <div class="small-note">Câmera espelhada para exibição. O tracking pelo rosto compensa o espelhamento automaticamente.</div>
    </div>

    <div class="card">
      <h3>Métricas</h3>
      <div class="stats-grid">
        <div class="stat"><div class="k">Tempo</div><div class="v" id="statTime">00:00</div></div>
        <div class="stat"><div class="k">Fixações</div><div class="v" id="statFixations">0</div></div>
        <div class="stat"><div class="k">Amostras</div><div class="v" id="statPoints">0</div></div>
        <div class="stat"><div class="k">Obras vistas</div><div class="v" id="statArtworks">0</div></div>
      </div>
      <div class="meta-line"><span>Qualidade</span><strong id="qualityText">—</strong></div>
      <div class="meta-line"><span>Hover atual</span><strong id="hoverText">—</strong></div>
      <div class="meta-line"><span>Calibração</span><strong id="calibrationText">Pendente</strong></div>
      <div class="meta-line"><span>Zoom</span><strong id="zoomText">Normal</strong></div>
    </div>

    <div class="card">
      <h3>Obra em foco</h3>
      <div id="selected-title">Nenhuma obra selecionada</div>
      <div id="selected-artist">Vire o rosto e mantenha foco ~1s ou pisque 1× para dar zoom</div>
      <div id="selected-description">Mantenha o foco por 1 segundo (dwell) ou pisque uma vez com a obra em foco. 2 piscadas rápidas afastam o zoom.</div>
    </div>

    <div class="card">
      <h3>Guia de blinks</h3>
      <div class="blink-guide">
        <div class="blink-card">
          <div class="icon">😉</div>
          <div class="bl">1 piscar</div>
          <div class="desc">Zoom na obra em foco</div>
        </div>
        <div class="blink-card">
          <div class="icon">😮</div>
          <div class="bl">2 piscadas rápidas</div>
          <div class="desc">Sai do zoom / afasta</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>Obras da sala</h3>
      <div id="artwork-list"></div>
    </div>

    <div class="card">
      <h3>Log do sistema</h3>
      <div id="logBox">Inicializando…</div>
    </div>
  </div>
</div>

<script>
(function(){
'use strict';

// ─── DOM ───
const roomCanvas   = document.getElementById('room');
const heatmapCanvas= document.getElementById('heatmap');
const revealCanvas = document.getElementById('reveal');
const scenePanel   = document.querySelector('.scene-panel');
const video        = document.getElementById('video');
const ctx          = roomCanvas.getContext('2d');
const heatCtx      = heatmapCanvas.getContext('2d');
const revealCtx    = revealCanvas.getContext('2d');

const gazeCursor    = document.getElementById('gaze-cursor');
const dwellFill     = document.getElementById('dwellFill');
const statusDot     = document.getElementById('statusDot');
const statusText    = document.getElementById('statusText');
const modeText      = document.getElementById('modeText');
const blinkText     = document.getElementById('blinkText');
const blinkIndicator= document.getElementById('blink-indicator');
const permNote      = document.getElementById('permission-note');
const qualityText   = document.getElementById('qualityText');
const hoverText     = document.getElementById('hoverText');
const calibText     = document.getElementById('calibrationText');
const zoomText      = document.getElementById('zoomText');
const statTime      = document.getElementById('statTime');
const statFixations = document.getElementById('statFixations');
const statPoints    = document.getElementById('statPoints');
const statArtworks  = document.getElementById('statArtworks');
const selTitle      = document.getElementById('selected-title');
const selArtist     = document.getElementById('selected-artist');
const selDesc       = document.getElementById('selected-description');
const artworkList   = document.getElementById('artwork-list');
const logBox        = document.getElementById('logBox');
const invertXBtn    = document.getElementById('invertXBtn');

// ─── UTILS ───
const clamp = (v,a,b) => Math.min(b, Math.max(a,v));
const lerp  = (a,b,t) => a + (b-a)*t;
const avgKey= (pts,k) => pts.reduce((s,p)=>s+p[k],0) / Math.max(1,pts.length);

function log(msg){
  const line = '['+new Date().toLocaleTimeString()+'] '+msg;
  logBox.textContent += '\n'+line;
  logBox.scrollTop = logBox.scrollHeight;
}
logBox.textContent = 'Sala inicializada.';
window.addEventListener('error', e => log('ERRO: '+(e.message||'?')));
window.addEventListener('unhandledrejection', e => log('REJECT: '+String(e.reason)));

// ─── STATE ───
const state = {
  running:false,
  usingMouse:true,
  faceMesh:null,
  stream:null,
  rafMedia:null,
  startedAt:null,

  sampleIntervalMs:80,
  lastSampleTs:0,
  hoverStartTs:0,
  dwellMs:1000,

  hoveredId:null,
  selectedId:null,

  fixations:0,
  inFixation:false,
  stableFor:0,
  lastPointPx:null,

  heatPoints:[],
  revealPoints:[],
  selections:[],
  seenIds:new Set(),

  calib:{
    xOff:0,
    yOff:0,
    gainX:1.00,
    gainY:0.94
  },

  blink:{
    closed:false,
    closeTs:0,
    ema:0.27,
    emaFast:0.27,
    baseline:0.27,
    baselineReady:false,
    baselineFrames:0,
    minBaseline:0.16,
    maxBaseline:0.40,
    closeRatio:0.72,
    openRatio:0.88,
    threshClose:0.18,
    threshOpen:0.23,
    minMs:45,
    maxMs:420,
    closedFrames:0,
    openFrames:0,
    minClosedFrames:1,
    minOpenFrames:1,
    lastBlinkTs:0,
    cooldownMs:140,
    cooldownUntil:0,
    doubleWindowMs:420,
    debugLast:'init'
  },

  tracking:{
    invertX:false,
    history:[],
    historyMax:6,
    baselineReady:false,
    baselineFrames:0,
    baseline:{
      centerX:0.5,
      centerY:0.5,
      yaw:0,
      pitch:0,
      size:0.22
    },
    deadzoneX:0.012,
    deadzoneY:0.012,
    centerGainX:1.28,
    centerGainY:0.92,
    yawGainX:0.20,
    pitchGainY:0.14
  },

  parallax:{
    inited:false,
    starsFar:[],
    starsMid:[],
    orbs:[],
    ribbons:[]
  },

  zoom:{
    active:false,
    targetId:null,
    focus:0,
    focusTarget:0
  }
};

// ─── GAZE ───
const gaze = {
  x:.5, y:.5,
  targetX:.5, targetY:.5,
  velX:0, velY:0,
  quality:.8
};

// ─── CAMERA ───
const cam = { x:0, y:1.65, z:-1.4, yaw:0, pitch:0, baseFov:700, fov:700 };

// ─── ARTWORKS ───
const artworks = [
  { id:'a1', title:'Memórias de Superfície', artist:'Lívia Andrade',  year:'2024', wall:'fundo',    color:'#e74c3c', desc:'Pintura em camadas com relevo cromático e estratos de memória afetiva.', plane:'back',  x:-2.8, y:2.1,  z:9.85, w:1.7, h:1.2 },
  { id:'a2', title:'Campo Sensível',         artist:'Diego Marins',   year:'2025', wall:'fundo',    color:'#27ae60', desc:'Trabalho digital generativo com profundidade simulada por partículas.',  plane:'back',  x:0.0,  y:2.2,  z:9.85, w:1.7, h:1.2 },
  { id:'a3', title:'Eco de Matéria',         artist:'Marina Teles',   year:'2026', wall:'fundo',    color:'#f39c12', desc:'Objeto expandido que evoca microscopia e holografia em simultaneidade.',  plane:'back',  x:2.8,  y:2.05, z:9.85, w:1.7, h:1.2 },
  { id:'a4', title:'Horizonte Índigo',       artist:'Ciro Menezes',   year:'2023', wall:'esquerda', color:'#8e44ad', desc:'Composição geométrica com ilusão de profundidade e vibração cromática.',  plane:'left',  x:-4.85,y:2.1,  z:6.1,  w:1.6, h:1.1 },
  { id:'a5', title:'Traço Latente',          artist:'Rafaela Costa',  year:'2022', wall:'direita',  color:'#2980b9', desc:'Pintura que exige leitura periférica e foco seletivo do observador.',     plane:'right', x:4.85, y:2.05, z:5.7,  w:1.6, h:1.1 }
];

let projectedArtworks = [];

// ─── UI HELPERS ───
function setStatus(on,t){ statusDot.classList.toggle('on',!!on); statusText.textContent=t; }
function setMode(t){ modeText.textContent=t; }
function setBlink(t){ blinkText.textContent=t; }

function flashBlinkIndicator(msg){
  blinkIndicator.textContent = msg;
  blinkIndicator.classList.add('show');
  clearTimeout(blinkIndicator._t);
  blinkIndicator._t = setTimeout(()=>blinkIndicator.classList.remove('show'), 1200);
}

// ─── RESIZE ───
function resizeCanvases(){
  const r = scenePanel.getBoundingClientRect();
  const dpr = window.devicePixelRatio||1;
  [roomCanvas,heatmapCanvas,revealCanvas].forEach(c=>{
    c.width  = Math.floor(r.width*dpr);
    c.height = Math.floor(r.height*dpr);
    c.style.width  = r.width+'px';
    c.style.height = r.height+'px';
  });
  ctx.setTransform(dpr,0,0,dpr,0,0);
  heatCtx.setTransform(dpr,0,0,dpr,0,0);
  revealCtx.setTransform(dpr,0,0,dpr,0,0);
}

function wrap(v,max){
  if(v<0) return max + (v % max);
  if(v>max) return v % max;
  return v;
}

function remapDeadzone(v, dz){
  if(Math.abs(v) <= dz) return 0;
  const s = Math.sign(v);
  const m = Math.abs(v) - dz;
  return s * m / (0.5 - dz);
}

function smoothTowards(curr, target, nearA, farA){
  const d = Math.abs(target - curr);
  const a = d > 0.08 ? farA : nearA;
  return lerp(curr, target, a);
}

function pushTrackingHistory(sample){
  state.tracking.history.push(sample);
  if(state.tracking.history.length > state.tracking.historyMax){
    state.tracking.history.shift();
  }
}

function avgHistory(key){
  if(!state.tracking.history.length) return 0;
  return state.tracking.history.reduce((s,p)=>s+p[key],0) / state.tracking.history.length;
}

function resetTrackingState(){
  state.tracking.history = [];
  state.tracking.baselineReady = false;
  state.tracking.baselineFrames = 0;
  state.tracking.baseline = {
    centerX:0.5,
    centerY:0.5,
    yaw:0,
    pitch:0,
    size:0.22
  };

  state.blink.closed = false;
  state.blink.closeTs = 0;
  state.blink.ema = 0.27;
  state.blink.emaFast = 0.27;
  state.blink.baseline = 0.27;
  state.blink.baselineReady = false;
  state.blink.baselineFrames = 0;
  state.blink.closedFrames = 0;
  state.blink.openFrames = 0;
  state.blink.lastBlinkTs = 0;
  state.blink.cooldownUntil = 0;
  state.blink.debugLast = 'reset';

  gaze.targetX = 0.5;
  gaze.targetY = 0.5;
  gaze.x = 0.5;
  gaze.y = 0.5;
}

function initParallax(){
  if(state.parallax.inited) return;
  state.parallax.inited = true;

  const far = [];
  for(let i=0;i<64;i++){
    far.push({
      x:Math.random(),
      y:Math.random(),
      r:0.7 + Math.random()*1.2,
      a:0.05 + Math.random()*0.16,
      speed:0.08 + Math.random()*0.12
    });
  }
  state.parallax.starsFar = far;

  const mid = [];
  for(let i=0;i<42;i++){
    mid.push({
      x:Math.random(),
      y:Math.random(),
      r:1.1 + Math.random()*2.2,
      a:0.06 + Math.random()*0.18,
      speed:0.18 + Math.random()*0.18
    });
  }
  state.parallax.starsMid = mid;

  const orbs = [];
  for(let i=0;i<5;i++){
    orbs.push({
      x:0.12 + Math.random()*0.76,
      y:0.08 + Math.random()*0.68,
      r:80 + Math.random()*170,
      hue:i%2===0 ? '93,173,226' : '165,105,189',
      a:0.04 + Math.random()*0.06,
      depth:0.18 + Math.random()*0.26
    });
  }
  state.parallax.orbs = orbs;

  const ribbons = [];
  for(let i=0;i<4;i++){
    ribbons.push({
      x:Math.random(),
      y:Math.random(),
      w:180 + Math.random()*260,
      h:18 + Math.random()*28,
      a:0.03 + Math.random()*0.04,
      depth:0.22 + Math.random()*0.25,
      rot:(Math.random()*0.7 - 0.35)
    });
  }
  state.parallax.ribbons = ribbons;
}

function drawParallaxBackdrop(r, gx, gy){
  initParallax();

  // distant nebulae
  state.parallax.orbs.forEach(o=>{
    const ox = r.width * o.x  + gx * r.width * o.depth * 0.34;
    const oy = r.height * o.y + gy * r.height * o.depth * 0.24;
    const rad = o.r;
    const g = ctx.createRadialGradient(ox, oy, 0, ox, oy, rad);
    g.addColorStop(0, 'rgba('+o.hue+','+o.a.toFixed(3)+')');
    g.addColorStop(0.5, 'rgba('+o.hue+','+(o.a*0.42).toFixed(3)+')');
    g.addColorStop(1, 'rgba('+o.hue+',0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(ox, oy, rad, 0, Math.PI*2);
    ctx.fill();
  });

  // ribbons / light streaks
  ctx.save();
  state.parallax.ribbons.forEach(rb=>{
    const x = r.width * rb.x + gx * r.width * rb.depth * 0.46;
    const y = r.height * rb.y + gy * r.height * rb.depth * 0.38;
    ctx.translate(x, y);
    ctx.rotate(rb.rot + gx*0.08);
    const grad = ctx.createLinearGradient(-rb.w/2, 0, rb.w/2, 0);
    grad.addColorStop(0, 'rgba(93,173,226,0)');
    grad.addColorStop(0.5, 'rgba(93,173,226,'+rb.a.toFixed(3)+')');
    grad.addColorStop(1, 'rgba(165,105,189,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(-rb.w/2, -rb.h/2, rb.w, rb.h);
    ctx.setTransform(1,0,0,1,0,0);
  });
  ctx.restore();

  // far stars
  state.parallax.starsFar.forEach(s=>{
    const x = wrap(r.width * s.x + gx * r.width * s.speed * 0.22, r.width);
    const y = wrap(r.height * s.y + gy * r.height * s.speed * 0.18, r.height);
    ctx.fillStyle = 'rgba(255,255,255,'+s.a.toFixed(3)+')';
    ctx.beginPath();
    ctx.arc(x, y, s.r, 0, Math.PI*2);
    ctx.fill();
  });

  // mid stars
  state.parallax.starsMid.forEach(s=>{
    const x = wrap(r.width * s.x + gx * r.width * s.speed * 0.34, r.width);
    const y = wrap(r.height * s.y + gy * r.height * s.speed * 0.28, r.height);
    ctx.fillStyle = 'rgba(191,214,246,'+s.a.toFixed(3)+')';
    ctx.beginPath();
    ctx.arc(x, y, s.r, 0, Math.PI*2);
    ctx.fill();
  });
}


// ─── PROJECTION ───
function projectPt(x,y,z){
  const rx=x-cam.x, ry=y-cam.y, rz=z-cam.z;
  const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw);
  const cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
  const x1=rx*cy-rz*sy, z1=rx*sy+rz*cy;
  const y2=ry*cp-z1*sp, z2=ry*sp+z1*cp;
  if(z2<=.1) return null;
  const r=scenePanel.getBoundingClientRect();
  const s=cam.fov/z2;
  return {x:r.width/2+x1*s, y:r.height/2-y2*s, depth:z2, scale:s};
}

function polyPts(art){
  const {x,y,z,w,h,plane}=art;
  if(plane==='back') return [
    projectPt(x-w/2,y-h/2,z), projectPt(x+w/2,y-h/2,z),
    projectPt(x+w/2,y+h/2,z), projectPt(x-w/2,y+h/2,z)
  ];
  if(plane==='left') return [
    projectPt(x,y-h/2,z-w/2), projectPt(x,y-h/2,z+w/2),
    projectPt(x,y+h/2,z+w/2), projectPt(x,y+h/2,z-w/2)
  ];
  return [
    projectPt(x,y-h/2,z+w/2), projectPt(x,y-h/2,z-w/2),
    projectPt(x,y+h/2,z-w/2), projectPt(x,y+h/2,z+w/2)
  ];
}

function drawPoly(pts,fill,stroke,lw){
  if(!pts||pts.some(p=>!p)) return;
  ctx.beginPath();
  ctx.moveTo(pts[0].x,pts[0].y);
  for(let i=1;i<pts.length;i++) ctx.lineTo(pts[i].x,pts[i].y);
  ctx.closePath();
  if(fill){ctx.fillStyle=fill;ctx.fill();}
  if(stroke){ctx.lineWidth=lw||1;ctx.strokeStyle=stroke;ctx.stroke();}
}

function ptInPoly(pt,poly){
  let inside=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++){
    const xi=poly[i].x,yi=poly[i].y,xj=poly[j].x,yj=poly[j].y;
    if(((yi>pt.y)!==(yj>pt.y))&&(pt.x<(xj-xi)*(pt.y-yi)/((yj-yi)||1e-6)+xi))
      inside=!inside;
  }
  return inside;
}

// ─── HEATMAP ───
function addHeat(xN,yN){
  const r=scenePanel.getBoundingClientRect();
  const px=xN*r.width, py=yN*r.height;
  state.heatPoints.push({x:px,y:py,ts:Date.now()});
  if(state.heatPoints.length>6000) state.heatPoints.shift();

  const g=heatCtx.createRadialGradient(px,py,4,px,py,36);
  g.addColorStop(0,'rgba(231,76,60,.17)');
  g.addColorStop(.4,'rgba(243,156,18,.11)');
  g.addColorStop(.75,'rgba(46,204,113,.07)');
  g.addColorStop(1,'rgba(46,204,113,0)');
  heatCtx.fillStyle=g;
  heatCtx.beginPath(); heatCtx.arc(px,py,36,0,Math.PI*2); heatCtx.fill();

  state.revealPoints.push({x:px,y:py,life:1});
  if(state.revealPoints.length>280) state.revealPoints.shift();

  statPoints.textContent=String(state.heatPoints.length);
  qualityText.textContent=Math.round(gaze.quality*100)+'%';

  // fixação
  if(state.lastPointPx){
    const d=Math.hypot(px-state.lastPointPx.x, py-state.lastPointPx.y);
    if(d<28){ state.stableFor+=state.sampleIntervalMs; if(state.stableFor>=250&&!state.inFixation){state.fixations++;state.inFixation=true;statFixations.textContent=String(state.fixations);} }
    else { state.stableFor=0; state.inFixation=false; }
  }
  state.lastPointPx={x:px,y:py};
}

function clearHeatmap(){
  const r=scenePanel.getBoundingClientRect();
  heatCtx.clearRect(0,0,r.width,r.height);
  revealCtx.clearRect(0,0,r.width,r.height);
  state.heatPoints=[]; state.revealPoints=[];
  state.fixations=0; state.inFixation=false;
  state.stableFor=0; state.lastPointPx=null;
  statFixations.textContent='0'; statPoints.textContent='0';
  log('Heatmap limpo.');
}

function drawReveal(){
  const r=scenePanel.getBoundingClientRect();
  revealCtx.clearRect(0,0,r.width,r.height);
  revealCtx.fillStyle='rgba(3,8,18,.5)';
  revealCtx.fillRect(0,0,r.width,r.height);
  revealCtx.globalCompositeOperation='destination-out';
  state.revealPoints.forEach(p=>{
    const rad=110+p.life*80;
    const g=revealCtx.createRadialGradient(p.x,p.y,0,p.x,p.y,rad);
    g.addColorStop(0,'rgba(255,255,255,'+(0.2*p.life)+')');
    g.addColorStop(.45,'rgba(255,255,255,'+(0.12*p.life)+')');
    g.addColorStop(1,'rgba(255,255,255,0)');
    revealCtx.fillStyle=g;
    revealCtx.beginPath(); revealCtx.arc(p.x,p.y,rad,0,Math.PI*2); revealCtx.fill();
    p.life*=.986;
  });
  state.revealPoints=state.revealPoints.filter(p=>p.life>.07);
  revealCtx.globalCompositeOperation='source-over';
}

// ─── CURSOR SMOOTHING ───
function updateCursor(){
  // spring-like smoothing
  gaze.velX = lerp(gaze.velX, gaze.targetX - gaze.x, .22);
  gaze.velY = lerp(gaze.velY, gaze.targetY - gaze.y, .22);
  gaze.x = clamp(gaze.x + gaze.velX*.38, .02, .98);
  gaze.y = clamp(gaze.y + gaze.velY*.38, .02, .98);
  gazeCursor.style.left = (gaze.x*100)+'%';
  gazeCursor.style.top  = (gaze.y*100)+'%';
}

// ─── ARTWORK PANEL ───
function artById(id){ return artworks.find(a=>a.id===id)||null; }

function updateSelPanel(art){
  if(!art){
    selTitle.textContent='Nenhuma obra selecionada';
    selArtist.textContent='Vire o rosto e mantenha foco ~1s ou pisque 1× para dar zoom';
    selDesc.textContent='A ficha aparece aqui após dwell-click ou blink. 2 piscadas rápidas saem do zoom.';
    return;
  }
  selTitle.textContent=art.title;
  selArtist.textContent=art.artist+' · '+art.year+' · parede '+art.wall;
  selDesc.textContent=art.desc;
}

function zoomInToArtwork(art, source, amount){
  if(!art) return;
  state.selectedId = art.id;
  state.zoom.active = true;
  state.zoom.targetId = art.id;
  state.zoom.focusTarget = clamp(Math.max(state.zoom.focusTarget, 0.18) + (amount || 0.32), 0, 1);
  zoomText.textContent = state.zoom.focusTarget > 0.72 ? 'Próximo' : 'Ativo';
  updateSelPanel(art);

  if(!state.seenIds.has(art.id)){
    state.seenIds.add(art.id);
    statArtworks.textContent = String(state.seenIds.size);
  }
  state.selections.push({id:art.id,title:art.title,ts:Date.now(),source:source||'zoom_in'});
  log('Zoom in "'+art.title+'" via '+(source||'zoom_in')+' ('+state.zoom.focusTarget.toFixed(2)+')');
}

function selectArtwork(art,source){
  zoomInToArtwork(art, source || 'select', source === 'dwell' ? 0.22 : 0.28);
}

function zoomOutStep(source){
  if(state.zoom.focusTarget <= 0.02){
    resetZoom();
    return;
  }
  state.zoom.focusTarget = clamp(state.zoom.focusTarget - 0.54, 0, 1);
  if(state.zoom.focusTarget <= 0.06){
    resetZoom();
  } else {
    state.zoom.active = true;
    zoomText.textContent = 'Afastando';
  }
  log('Zoom out via '+(source||'zoom_out')+' ('+state.zoom.focusTarget.toFixed(2)+')');
}

function resetZoom(){
  state.zoom.focusTarget = 0;
  state.zoom.active = false;
  state.zoom.targetId = null;
  state.selectedId = null;
  zoomText.textContent = 'Normal';
  updateSelPanel(null);
}

function blinkTarget(){
  const hovered = artById(state.hoveredId);
  const selected = artById(state.selectedId);
  if(hovered) return hovered;
  if(selected) return selected;

  // fallback: usa a obra mais próxima do cursor atual
  if(projectedArtworks && projectedArtworks.length){
    const r = scenePanel.getBoundingClientRect();
    const gx = gaze.x * r.width;
    const gy = gaze.y * r.height;
    let best = null;
    let bestD = Infinity;
    projectedArtworks.forEach(entry=>{
      const poly = entry.poly;
      const cx = (poly[0].x + poly[1].x + poly[2].x + poly[3].x) / 4;
      const cy = (poly[0].y + poly[1].y + poly[2].y + poly[3].y) / 4;
      const d = Math.hypot(cx - gx, cy - gy);
      if(d < bestD){
        bestD = d;
        best = entry.art;
      }
    });
    if(best && bestD < Math.min(r.width, r.height) * 0.26) return best;
  }
  return null;
}

function onSingleBlink(){
  const target = blinkTarget();
  if(target){
    zoomInToArtwork(target, 'single_blink', target.id === state.hoveredId ? 0.34 : 0.28);
    flashBlinkIndicator('👁 1 piscar → aproxima "'+target.title+'"');
    log('Single blink → aproxima ' + target.title);
  } else {
    flashBlinkIndicator('👁 1 piscar sem obra em foco');
    log('Single blink sem alvo útil');
  }
}

function onDoubleBlink(){
  zoomOutStep('double_blink');
  flashBlinkIndicator('👁👁 2 piscadas → afasta');
  log('Double blink → afasta');
}

function registerBlink(now){
  if(now < state.blink.cooldownUntil){
    state.blink.debugLast = 'cooldown';
    return;
  }

  const delta = state.blink.lastBlinkTs ? (now - state.blink.lastBlinkTs) : Infinity;
  state.blink.cooldownUntil = now + state.blink.cooldownMs;

  if(delta <= state.blink.doubleWindowMs){
    state.blink.debugLast = 'double';
    state.blink.lastBlinkTs = 0;
    setBlink('2x');
    onDoubleBlink();
    return;
  }

  state.blink.debugLast = 'single';
  state.blink.lastBlinkTs = now;
  setBlink('1x');
  onSingleBlink();
}

function eyeOpenness(lm,topIdx,botIdx,lIdx,rIdx){
  const top=lm[topIdx], bot=lm[botIdx], left=lm[lIdx], right=lm[rIdx];
  const vert=Math.hypot(top.x-bot.x, top.y-bot.y);
  const horiz=Math.hypot(left.x-right.x, left.y-right.y);
  return vert/Math.max(horiz,1e-6);
}

function processBlink(landmarks){
  const leftOpen  = eyeOpenness(landmarks,159,145,33,133);
  const rightOpen = eyeOpenness(landmarks,386,374,362,263);
  const now = Date.now();

  const rawAvg = (leftOpen + rightOpen) * 0.5;
  const rawMin = Math.min(leftOpen, rightOpen);
  const rawOpen = rawAvg * 0.58 + rawMin * 0.42;

  state.blink.emaFast = lerp(state.blink.emaFast, rawOpen, 0.58);
  state.blink.ema = lerp(state.blink.ema, rawOpen, 0.18);

  if(!state.blink.closed){
    if(!state.blink.baselineReady){
      state.blink.baselineFrames += 1;
      state.blink.baseline = lerp(state.blink.baseline, state.blink.emaFast, 0.15);
      if(state.blink.baselineFrames >= 10){
        state.blink.baselineReady = true;
      }
    } else if(rawOpen > state.blink.baseline * 0.84){
      state.blink.baseline = lerp(
        state.blink.baseline,
        clamp(rawOpen, state.blink.minBaseline, state.blink.maxBaseline),
        0.028
      );
    }
  }

  const baseline = clamp(state.blink.baseline, state.blink.minBaseline, state.blink.maxBaseline);
  const closeThresh = clamp(Math.min(baseline * state.blink.closeRatio, baseline - 0.035), 0.11, 0.24);
  const openThresh  = clamp(Math.max(baseline * state.blink.openRatio, closeThresh + 0.030), 0.16, 0.34);
  state.blink.threshClose = closeThresh;
  state.blink.threshOpen = openThresh;

  const openness = state.blink.emaFast * 0.72 + state.blink.ema * 0.28;

  if(!state.blink.closed){
    if(openness < closeThresh){
      state.blink.closedFrames += 1;
    } else {
      state.blink.closedFrames = Math.max(0, state.blink.closedFrames - 1);
    }
    state.blink.openFrames = 0;

    if(state.blink.closedFrames >= state.blink.minClosedFrames){
      state.blink.closed = true;
      state.blink.closeTs = now;
      state.blink.closedFrames = 0;
      state.blink.openFrames = 0;
      state.blink.debugLast = 'closed';
      setBlink('Fechado');
      gazeCursor.style.borderColor = 'rgba(243,156,18,.9)';
    }
    return;
  }

  if(openness > openThresh){
    state.blink.openFrames += 1;
  } else {
    state.blink.openFrames = 0;
  }

  if(state.blink.openFrames >= state.blink.minOpenFrames){
    const dur = now - state.blink.closeTs;
    state.blink.closed = false;
    state.blink.closedFrames = 0;
    state.blink.openFrames = 0;
    state.blink.debugLast = 'open';
    setBlink('Aberto');
    gazeCursor.style.borderColor = 'rgba(255,255,255,.92)';

    if(dur >= state.blink.minMs && dur <= state.blink.maxMs){
      registerBlink(now);
    } else {
      state.blink.debugLast = 'ignored_'+dur;
    }
  }
}

// ─── FACE TRACKING / HEAD POSE MAPPING ───
// Nesta versão, o cursor e a navegação da cena passam a seguir o rosto/cabeça,
// não a posição da íris. Isso reduz a inversão lateral que acontecia em alguns
// aparelhos por causa do vídeo espelhado.
// Estratégia:
// - usa nariz + largura da face + alinhamento dos olhos
// - compensa o espelhamento do vídeo invertendo X uma única vez
// - combina translação do rosto com yaw (rotação lateral da cabeça)
// - aplica zona morta e suavização para reduzir tremedeira
function faceBox(lm){
  const ids = [10,152,234,454,93,323,127,356];
  const pts = ids.map(i=>lm[i]).filter(Boolean);
  return {
    minX:Math.min(...pts.map(p=>p.x)),
    maxX:Math.max(...pts.map(p=>p.x)),
    minY:Math.min(...pts.map(p=>p.y)),
    maxY:Math.max(...pts.map(p=>p.y))
  };
}

function faceMetrics(lm){
  const box = faceBox(lm);
  const nose = lm[1];
  const forehead = lm[10];
  const chin = lm[152];
  const leftEyeOuter = lm[33];
  const rightEyeOuter = lm[263];
  const leftCheek = lm[234];
  const rightCheek = lm[454];
  const mouthTop = lm[13];
  const mouthBot = lm[14];

  if(!nose || !forehead || !chin || !leftEyeOuter || !rightEyeOuter || !leftCheek || !rightCheek || !mouthTop || !mouthBot){
    return null;
  }

  const eyeMidX = (leftEyeOuter.x + rightEyeOuter.x) * 0.5;
  const faceWidth = Math.max(0.001, rightCheek.x - leftCheek.x);
  const faceHeight = Math.max(0.001, chin.y - forehead.y);

  // Usa coordenadas cruas da malha facial. Não espelha aqui.
  // Se o aparelho do usuário se comportar diferente, o botão “Inverter X” continua disponível.
  const centerX = clamp(((nose.x * 0.70 + eyeMidX * 0.30) - box.minX) / Math.max(0.001, box.maxX - box.minX), 0, 1);
  const centerY = clamp(((nose.y * 0.66 + ((mouthTop.y + mouthBot.y) * 0.5) * 0.34) - box.minY) / Math.max(0.001, box.maxY - box.minY), 0, 1);

  // yaw segue o sinal cru; o erro anterior vinha de inverter no retorno e de novo no mapeamento.
  const yaw = (nose.x - eyeMidX) / Math.max(0.001, rightEyeOuter.x - leftEyeOuter.x);
  const faceMidY = (forehead.y + chin.y) * 0.5;
  const pitch = (nose.y - faceMidY) / faceHeight;
  const size = faceWidth;

  return {
    centerX,
    centerY,
    yaw,
    pitch,
    size
  };
}

function updateTrackingBaseline(m){
  const b = state.tracking.baseline;
  if(!state.tracking.baselineReady){
    state.tracking.baselineFrames += 1;
    const t = Math.min(1, state.tracking.baselineFrames / 18);
    b.centerX = lerp(b.centerX, m.centerX, 0.20 * t);
    b.centerY = lerp(b.centerY, m.centerY, 0.20 * t);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.16 * t);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.16 * t);
    b.size    = lerp(b.size,    m.size,    0.16 * t);
    if(state.tracking.baselineFrames >= 18){
      state.tracking.baselineReady = true;
      calibText.textContent = 'Auto';
      log('Baseline facial capturada.');
    }
    return;
  }

  const stableCenter = Math.abs(m.centerX - b.centerX) < 0.055 && Math.abs(m.centerY - b.centerY) < 0.055;
  if(stableCenter && !state.blink.closed){
    b.centerX = lerp(b.centerX, m.centerX, 0.010);
    b.centerY = lerp(b.centerY, m.centerY, 0.010);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.010);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.010);
    b.size    = lerp(b.size,    m.size,    0.006);
  }
}

function mapFaceTracking(landmarks){
  const m = faceMetrics(landmarks);
  if(!m) return;

  updateTrackingBaseline(m);

  const xBase = state.tracking.invertX ? (1 - m.centerX) : m.centerX;
  const xRef  = state.tracking.invertX ? (1 - state.tracking.baseline.centerX) : state.tracking.baseline.centerX;

  const sample = {
    x:xBase,
    y:m.centerY,
    yaw:m.yaw,
    pitch:m.pitch,
    size:m.size
  };
  pushTrackingHistory(sample);

  const hx = avgHistory('x');
  const hy = avgHistory('y');
  const hyaw = avgHistory('yaw');
  const hpitch = avgHistory('pitch');
  const hsize = avgHistory('size');

  const dx = hx - xRef;
  const dy = hy - state.tracking.baseline.centerY;
  const dyaw = hyaw - state.tracking.baseline.yaw;
  const dpitch = hpitch - state.tracking.baseline.pitch;

  let combinedX = dx * state.tracking.centerGainX + dyaw * state.tracking.yawGainX;
  let combinedY = dy * state.tracking.centerGainY + dpitch * state.tracking.pitchGainY;

  combinedX = remapDeadzone(combinedX, state.tracking.deadzoneX);
  combinedY = remapDeadzone(combinedY, state.tracking.deadzoneY);

  const targetX = clamp(0.5 + combinedX * 0.92 + state.calib.xOff, 0.02, 0.98);
  const targetY = clamp(0.5 + combinedY * 0.82 + state.calib.yOff, 0.02, 0.98);

  gaze.targetX = smoothTowards(gaze.targetX, targetX, 0.14, 0.22);
  gaze.targetY = smoothTowards(gaze.targetY, targetY, 0.14, 0.22);

  const sym = 1 - Math.abs(dx * 0.72) - Math.abs(dyaw * 0.18) - Math.abs(hsize - state.tracking.baseline.size) * 0.32;
  gaze.quality = clamp(sym, 0.56, 0.99);
}

// ─── DRAW ROOM ───
function drawArtwork(art,highlight){
  const poly=polyPts(art);
  if(!poly||poly.some(p=>!p)) return null;
  const [p0,p1,p2,p3]=poly;

  drawPoly(poly,'rgba(70,55,40,.98)', highlight?'rgba(93,173,226,.9)':'rgba(255,255,255,.1)', highlight?2.5:1);

  const cx=(p0.x+p1.x+p2.x+p3.x)/4;
  const cy=(p0.y+p1.y+p2.y+p3.y)/4;
  const inner=poly.map(p=>({x:lerp(p.x,cx,.08),y:lerp(p.y,cy,.08)}));
  const g=ctx.createLinearGradient(inner[0].x,inner[0].y,inner[2].x,inner[2].y);
  g.addColorStop(0,art.color); g.addColorStop(1,'#0a1525');
  drawPoly(inner,g, highlight?'rgba(255,255,255,.2)':'rgba(255,255,255,.07)', 1);

  ctx.fillStyle='rgba(255,255,255,.93)';
  ctx.font='bold 13px "Space Grotesk",sans-serif';
  ctx.textAlign='center';
  ctx.fillText(art.title,cx,cy-4);
  ctx.fillStyle='rgba(200,215,255,.75)';
  ctx.font='11.5px "Space Grotesk",sans-serif';
  ctx.fillText(art.artist,cx,cy+13);
  return poly;
}

function drawPedestal(x,z,color){
  const base=[projectPt(x-.52,0,z-.52),projectPt(x+.52,0,z-.52),projectPt(x+.52,0,z+.52),projectPt(x-.52,0,z+.52)];
  const top =[projectPt(x-.4,1.05,z-.4),projectPt(x+.4,1.05,z-.4),projectPt(x+.4,1.05,z+.4),projectPt(x-.4,1.05,z+.4)];
  if(base.some(p=>!p)||top.some(p=>!p)) return;
  drawPoly([base[0],base[1],top[1],top[0]],'rgba(210,216,228,.8)','rgba(255,255,255,.1)',1);
  drawPoly([base[1],base[2],top[2],top[1]],'rgba(185,192,206,.82)','rgba(255,255,255,.1)',1);
  drawPoly([base[2],base[3],top[3],top[2]],'rgba(160,170,185,.85)','rgba(255,255,255,.1)',1);
  drawPoly(top,'rgba(232,236,244,.94)','rgba(255,255,255,.12)',1);
  const orb=projectPt(x,1.52,z);
  if(orb){
    const r=orb.scale*.17;
    const g=ctx.createRadialGradient(orb.x-r*.35,orb.y-r*.35,r*.15,orb.x,orb.y,r*1.6);
    g.addColorStop(0,color); g.addColorStop(1,'rgba(10,18,34,.12)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(orb.x,orb.y,r,0,Math.PI*2); ctx.fill();
  }
}

function drawRoom(){
  const r = scenePanel.getBoundingClientRect();
  ctx.clearRect(0,0,r.width,r.height);

  const bg = ctx.createLinearGradient(0,0,0,r.height);
  bg.addColorStop(0,'#060d1a');
  bg.addColorStop(1,'#020709');
  ctx.fillStyle = bg;
  ctx.fillRect(0,0,r.width,r.height);

  const gx = gaze.x - 0.5;
  const gy = gaze.y - 0.5;

  drawParallaxBackdrop(r, gx, gy);

  const zoomArt = artById(state.zoom.targetId);
  state.zoom.focus = lerp(state.zoom.focus, state.zoom.focusTarget, 0.07);

  let fx = 0, fy = 2.0, fz = 8.5;
  if(zoomArt){
    fx = zoomArt.x;
    fy = zoomArt.y;
    fz = zoomArt.z - (zoomArt.plane === 'back' ? 1.95 : 0);
  }

  const f = state.zoom.focus;
  cam.x     = lerp(gx * 0.92,  fx * 0.19, f);
  cam.y     = lerp(1.65 - gy * 0.35, fy - 0.10, f);
  cam.z     = lerp(-1.4, fz - 6.5, f);
  cam.yaw   = lerp(gx * 0.36,  fx * 0.016, f);
  cam.pitch = lerp(-gy * 0.12, -0.022, f);
  cam.fov   = lerp(cam.baseFov, cam.baseFov * 1.56, f);

  const surfDefs = [
    {pts:[[-5,0,0],[5,0,0],[5,0,10],[-5,0,10]],fill:'rgba(18,30,50,.98)',stroke:'rgba(255,255,255,.04)'},
    {pts:[[-5,4,0],[5,4,0],[5,4,10],[-5,4,10]],fill:'rgba(9,16,32,.90)',stroke:'rgba(255,255,255,.04)'},
    {pts:[[-5,0,0],[-5,0,10],[-5,4,10],[-5,4,0]],fill:'rgba(12,20,38,.94)',stroke:'rgba(255,255,255,.05)'},
    {pts:[[5,0,0],[5,0,10],[5,4,10],[5,4,0]],fill:'rgba(11,19,36,.94)',stroke:'rgba(255,255,255,.05)'},
    {pts:[[-5,0,10],[5,0,10],[5,4,10],[-5,4,10]],fill:'rgba(14,23,42,.96)',stroke:'rgba(255,255,255,.05)'}
  ];
  surfDefs.forEach(s => drawPoly(s.pts.map(p=>projectPt(...p)), s.fill, s.stroke, 1));

  // subtle floor grid
  for(let i=-4;i<=4;i++){
    const a = projectPt(i,0.001,0.2), b = projectPt(i,0.001,9.8);
    if(a && b){
      ctx.strokeStyle='rgba(255,255,255,.04)';
      ctx.lineWidth=1;
      ctx.beginPath();
      ctx.moveTo(a.x,a.y);
      ctx.lineTo(b.x,b.y);
      ctx.stroke();
    }
  }
  for(let z=1;z<=10;z++){
    const a = projectPt(-4.8,0.001,z), b = projectPt(4.8,0.001,z);
    if(a && b){
      ctx.strokeStyle='rgba(255,255,255,.04)';
      ctx.lineWidth=1;
      ctx.beginPath();
      ctx.moveTo(a.x,a.y);
      ctx.lineTo(b.x,b.y);
      ctx.stroke();
    }
  }

  // ambient spotlight follows gaze slightly
  const sl = projectPt(gx * 3.2, 3.45, 4.8);
  if(sl){
    const g = ctx.createRadialGradient(sl.x,sl.y,0,sl.x,sl.y,r.width*0.34);
    g.addColorStop(0,'rgba(93,173,226,.18)');
    g.addColorStop(.5,'rgba(93,173,226,.06)');
    g.addColorStop(1,'rgba(93,173,226,0)');
    ctx.fillStyle=g;
    ctx.beginPath();
    ctx.arc(sl.x,sl.y,r.width*0.34,0,Math.PI*2);
    ctx.fill();
  }

  drawPedestal(-1.8,3.0,'rgba(93,173,226,.95)');
  drawPedestal(1.8,3.35,'rgba(165,105,189,.95)');

  projectedArtworks = [];
  artworks.forEach(art=>{
    const hl = state.hoveredId===art.id || state.selectedId===art.id || state.zoom.targetId===art.id;
    const poly = drawArtwork(art, hl);
    if(poly) projectedArtworks.push({art, poly});
  });

  const gPx = {x:gaze.x*r.width, y:gaze.y*r.height};
  ctx.strokeStyle='rgba(255,255,255,.08)';
  ctx.lineWidth=1;
  ctx.beginPath();
  ctx.moveTo(gPx.x,0); ctx.lineTo(gPx.x,r.height);
  ctx.moveTo(0,gPx.y); ctx.lineTo(r.width,gPx.y);
  ctx.stroke();
}

// ─── HOVER / DWELL ───
function updateHoverDwell(now){
  const r=scenePanel.getBoundingClientRect();
  const gPx={x:gaze.x*r.width, y:gaze.y*r.height};
  const hit=projectedArtworks.find(e=>ptInPoly(gPx,e.poly));

  if(!hit){
    if(state.hoveredId){ state.hoveredId=null; state.hoverStartTs=now; }
    dwellFill.style.width='0%';
    hoverText.textContent='—';
    gazeCursor.style.width='26px'; gazeCursor.style.height='26px';
    return;
  }

  hoverText.textContent=hit.art.title;
  if(state.hoveredId!==hit.art.id){
    state.hoveredId=hit.art.id;
    state.hoverStartTs=now;
    gazeCursor.style.width='34px'; gazeCursor.style.height='34px';
  }

  const elapsed=now-state.hoverStartTs;
  const progress=clamp(elapsed/state.dwellMs,0,1);
  dwellFill.style.width=(progress*100).toFixed(1)+'%';
  gazeCursor.style.borderColor=progress>.7?'rgba(46,204,113,.95)':'rgba(93,173,226,.95)';

  if(progress>=1){
    selectArtwork(hit.art,'dwell');
    state.hoverStartTs=now+380; // cooldown
  }
}

// ─── CLOCK ───
function updateClock(){
  if(!state.startedAt){statTime.textContent='00:00';return;}
  const sec=Math.max(0,Math.floor((Date.now()-state.startedAt)/1000));
  statTime.textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');
}
setInterval(updateClock,400);

// ─── SCRIPT LOADER ───
async function loadScript(src){
  return new Promise((res,rej)=>{
    if(document.querySelector('script[data-url="'+src+'"]')){res(true);return;}
    const s=document.createElement('script');
    s.src=src; s.async=true; s.dataset.url=src;
    s.onload=()=>res(true); s.onerror=()=>rej(new Error('Falha: '+src));
    document.head.appendChild(s);
  });
}

async function loadAny(urls){
  for(const u of urls){
    try{ await loadScript(u); log('Lib carregada: '+u); return u; }
    catch(e){ log('Tentativa falhou: '+u); }
  }
  throw new Error('Nenhuma URL disponível');
}

// ─── TRACKING START ───
async function startTracking(){
  log('Iniciando tracking…');
  resetTrackingState();
  state.startedAt=state.startedAt||Date.now();
  state.running=true;
  setStatus(false,'Preparando…');
  permNote.textContent='Tentando webcam + MediaPipe FaceMesh…';

  try{
    if(!navigator.mediaDevices?.getUserMedia)
      throw new Error('getUserMedia não disponível');

    const baseUrl = await loadAny([
      'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js',
      'https://unpkg.com/@mediapipe/face_mesh/face_mesh.js'
    ]);
    const cdnBase = baseUrl.includes('unpkg')
      ? 'https://unpkg.com/@mediapipe/face_mesh/'
      : 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/';

    state.stream = await navigator.mediaDevices.getUserMedia({
      video:{width:{ideal:640},height:{ideal:480},facingMode:'user'}, audio:false
    });
    video.srcObject=state.stream;
    await video.play();
    log('Webcam aberta.');

    state.faceMesh = new window.FaceMesh({
      locateFile: f => cdnBase+f
    });
    state.faceMesh.setOptions({
      maxNumFaces:1, refineLandmarks:true,
      minDetectionConfidence:.5, minTrackingConfidence:.5
    });
    state.faceMesh.onResults(results=>{
      if(!state.running) return;
      if(!results.multiFaceLandmarks?.[0]){
        setStatus(false,'Rosto não encontrado');
        gaze.quality=.4;
        state.blink.closed = false;
        state.blink.closedFrames = 0;
        state.blink.openFrames = 0;
        return;
      }
      mapFaceTracking(results.multiFaceLandmarks[0]);
      processBlink(results.multiFaceLandmarks[0]);
      state.usingMouse=false;
      setMode('Webcam'); setStatus(true,'Tracking facial ativo');
    });

    async function mediaLoop(){
      if(!state.running||!state.faceMesh) return;
      try{ if(video.readyState>=2) await state.faceMesh.send({image:video}); }
      catch(e){ log('Frame error: '+e.message); }
      state.rafMedia=requestAnimationFrame(mediaLoop);
    }
    if(state.rafMedia) cancelAnimationFrame(state.rafMedia);
    state.rafMedia=requestAnimationFrame(mediaLoop);
    state.usingMouse=false;
    setMode('Webcam');
    permNote.textContent='Tracking facial ativo. 1 piscar = aproxima · 2 piscadas rápidas = afasta.';
    log('Tracking facial iniciado.');

  } catch(err){
    state.usingMouse=true;
    setMode('Mouse'); setStatus(true,'Modo mouse');
    const msg=err?.message||String(err);
    permNote.textContent='Webcam indisponível ('+msg+'). Modo mouse ativo para teste.';
    log('Falha webcam: '+msg);
  }
}

function stopTracking(){
  state.running=false;
  if(state.rafMedia){ cancelAnimationFrame(state.rafMedia); state.rafMedia=null; }
  if(state.stream){ state.stream.getTracks().forEach(t=>t.stop()); state.stream=null; }
  video.srcObject=null;
  state.usingMouse=true;
  setMode('Parado'); setStatus(false,'Tracking desligado');
  permNote.textContent='Tracking desligado. Sala continua ativa.';
  dwellFill.style.width='0%';
  resetZoom();
  resetTrackingState();
  log('Tracking parado.');
}

function calibrate(){
  if(state.usingMouse){
    calibText.textContent='Modo mouse';
    log('Calibração não necessária no modo mouse.');
    return;
  }
  state.calib.xOff += (0.5 - gaze.targetX) * 0.22;
  state.calib.yOff += (0.5 - gaze.targetY) * 0.20;
  state.calib.gainX = 1.00;
  state.calib.gainY = 0.94;
  calibText.textContent='Concluída';
  permNote.textContent='Calibração aplicada. Se a direção lateral ainda parecer invertida, use o botão “Inverter X”.';
  log('Calibração aplicada. xOff='+state.calib.xOff.toFixed(3)+' yOff='+state.calib.yOff.toFixed(3));
}

// ─── EXPORT PDF ───
async function exportPdf(){
  log('Exportando PDF…');
  const sceneImg=roomCanvas.toDataURL('image/png',1);
  const heatImg=heatmapCanvas.toDataURL('image/png',1);
  try{
    await loadScript('https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js');
    const jsPDF=window.jspdf?.jsPDF;
    if(!jsPDF) throw new Error('jsPDF não carregou');
    const pdf=new jsPDF('p','mm','a4');
    let y=16;
    pdf.setFillColor(6,13,26); pdf.rect(0,0,210,297,'F');
    pdf.setTextColor(232,240,255); pdf.setFont('helvetica','bold'); pdf.setFontSize(17);
    pdf.text('Relatório Eye Tracking – Sala 3D',12,y); y+=8;
    pdf.setFont('helvetica','normal'); pdf.setFontSize(10); pdf.setTextColor(122,144,184);
    pdf.text('Gerado em: '+new Date().toLocaleString(),12,y); y+=9;
    pdf.setTextColor(232,240,255); pdf.setFontSize(11);
    const lines=[
      'Modo: '+(state.usingMouse?'Mouse':'Webcam'),
      'Amostras: '+state.heatPoints.length,
      'Fixações: '+state.fixations,
      'Obras vistas: '+state.seenIds.size,
      'Qualidade: '+Math.round(gaze.quality*100)+'%',
      'Zoom: '+(state.zoom.focus>.15?'sim':'não')
    ];
    lines.forEach(l=>{ pdf.text(l,12,y); y+=5; });
    y+=4;
    pdf.setFont('helvetica','bold');
    pdf.text('Cena + Heatmap',12,y); y+=3;
    pdf.addImage(sceneImg,'PNG',12,y,88,66,undefined,'FAST');
    pdf.addImage(heatImg,'PNG',108,y,88,66,undefined,'FAST');
    y+=72;
    pdf.setFont('helvetica','bold'); pdf.text('Seleções',12,y); y+=6;
    pdf.setFont('helvetica','normal');
    if(!state.selections.length){ pdf.text('Nenhuma seleção.',12,y); }
    else {
      const grp={};
      state.selections.forEach(s=>{ grp[s.id]=grp[s.id]||{title:s.title,count:0}; grp[s.id].count++; });
      Object.values(grp).forEach(g=>{ pdf.text('• '+g.title+' ('+g.count+'×)',12,y); y+=5; });
    }
    pdf.save('relatorio_sala3d.pdf');
    log('PDF salvo.');
  } catch(e){ log('Erro PDF: '+e.message); permNote.textContent='Erro ao gerar PDF: '+e.message; }
}

// ─── MOUSE FALLBACK ───
scenePanel.addEventListener('mousemove', ev=>{
  if(!state.usingMouse) return;
  const r=scenePanel.getBoundingClientRect();
  gaze.targetX=clamp((ev.clientX-r.left)/r.width,.02,.98);
  gaze.targetY=clamp((ev.clientY-r.top)/r.height,.02,.98);
});

scenePanel.addEventListener('click', ()=>{
  if(!state.usingMouse) return;
  const hov=artById(state.hoveredId);
  if(hov) selectArtwork(hov,'mouse_click');
  else if(state.zoom.focusTarget>0) resetZoom();
});

// ─── BUTTON WIRING ───
document.getElementById('startBtn').addEventListener('click', startTracking);
document.getElementById('stopBtn').addEventListener('click', stopTracking);
document.getElementById('calibrateBtn').addEventListener('click', calibrate);
document.getElementById('resetHeatBtn').addEventListener('click', clearHeatmap);
document.getElementById('exportPdfBtn').addEventListener('click', exportPdf);
invertXBtn.addEventListener('click', ()=>{
  state.tracking.invertX = !state.tracking.invertX;
  permNote.textContent = state.tracking.invertX ? 'Eixo X invertido manualmente.' : 'Eixo X no modo normal.';
  log('Inverter X = '+state.tracking.invertX);
});

// ─── ARTWORK LIST ───
function buildList(){
  artworkList.innerHTML='';
  artworks.forEach(art=>{
    const row=document.createElement('div');
    row.className='art-row';
    row.innerHTML=
      '<div class="art-bullet" style="background:'+art.color+'"></div>'+
      '<div><div class="art-title">'+art.title+'</div><div class="art-sub">'+art.artist+' · '+art.year+'</div></div>'+
      '<div class="badge">'+art.wall+'</div>';
    row.addEventListener('click',()=>selectArtwork(art,'lista'));
    artworkList.appendChild(row);
  });
}

// ─── MAIN LOOP ───
function tick(now){
  requestAnimationFrame(tick);
  if(!state.startedAt) state.startedAt=Date.now();
  updateCursor();
  drawRoom();
  drawReveal();
  if(state.running||state.usingMouse){
    updateHoverDwell(now);
    const t=Date.now();
    if(t-state.lastSampleTs>=state.sampleIntervalMs){
      state.lastSampleTs=t;
      addHeat(gaze.x,gaze.y);
    }
  }
  if(!state.hoveredId){
    gazeCursor.style.width='26px'; gazeCursor.style.height='26px';
    gazeCursor.style.borderColor='rgba(255,255,255,.92)';
  }
}

// ─── INIT ───
resizeCanvases();
initParallax();
buildList();
updateSelPanel(null);
setMode('Face tracking pronto');
setBlink('Pronto');
setStatus(true,'Cena carregada');
window.addEventListener('resize',resizeCanvases);
requestAnimationFrame(tick);
log('Sala pronta. Clique em "Iniciar tracking" para usar webcam com tracking pelo rosto.');

})();
</script>
</div>
"""

components.html(HTML_APP, height=1300, scrolling=True)
