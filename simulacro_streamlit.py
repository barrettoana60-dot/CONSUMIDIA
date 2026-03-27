import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Simulacro Streamlit – Eye Tracking sem Tkinter", layout="wide")

st.title("Simulacro Streamlit com Eye Tracking + Blink Zoom + Parallax")
st.caption("Versão compatível com Streamlit: sem tkinter, com câmera no navegador, malha facial/olhos no front-end, seleção por olhar, 1 piscada afasta e 2 piscadas aproximam.")

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
  #heatmap{display:none}
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
    width:100%;height:100%;object-fit:cover;
    border-radius:12px;
    background:#020609;transform:scaleX(-1);
  }
  #meshOverlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
  .manual-zoom{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
  .manual-zoom .btn{width:100%;text-align:center}
  .status-note{margin-top:8px;font-size:11.5px;color:var(--muted);line-height:1.4}

  #focus-info-card{
    position:absolute;z-index:8;min-width:210px;max-width:280px;padding:12px 14px;
    border-radius:14px;background:rgba(6,13,26,.90);border:1px solid rgba(93,173,226,.22);
    backdrop-filter:blur(14px);box-shadow:0 16px 40px rgba(0,0,0,.32);
    pointer-events:none;opacity:0;transform:translate(-50%,-120%);transition:opacity .15s ease, transform .15s ease;
  }
  #focus-info-card.show{opacity:1}
  #focus-info-card .ttl{font-size:13px;font-weight:800;color:var(--text);margin-bottom:4px}
  #focus-info-card .sub{font-size:11px;color:var(--cyan);font-weight:700;margin-bottom:5px}
  #focus-info-card .txt{font-size:11px;color:var(--muted);line-height:1.35}
  .video-wrap{position:relative;width:100%;aspect-ratio:16/10;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,.07);background:#020609}
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
    <h2>Sala 3D – Pose da cabeça + foco por permanência + zoom híbrido</h2>
    <p><strong>Cabeça/rosto</strong> controlam a direção, o <strong>foco entra por permanência do olhar</strong>, e o <strong>zoom principal</strong> vem da distância do rosto e dos botões. O blink continua disponível apenas como reforço opcional quando a câmera estiver boa.</p>
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
      <div id="focus-info-card"><div class="ttl">Obra em foco</div><div class="sub">Aguardando foco</div><div class="txt">Olhe para uma obra para exibir a ficha.</div></div>

      <div class="chip" id="statusChip"><span id="statusDot" class="dot"></span><span id="statusText">Aguardando</span></div>
      <div class="chip" id="modeChip">Modo: <strong id="modeText">Cena ativa</strong></div>
      <div class="chip" id="blinkChip">🔎 Zoom extra: <strong id="blinkText">Pronto</strong></div>

      <div class="meter">
        <div class="label">Dwell-click</div>
        <div class="bar"><div id="dwellFill"></div></div>
      </div>

      <div id="blink-indicator">👁 Blink detectado</div>
      <div id="permission-note">Sala carregada. Clique em "Iniciar tracking". O olhar ocular passa a mirar a obra, a ficha aparece ao focar, 1 piscada afasta e 2 piscadas aproximam. A cabeça continua ajudando quando a câmera oscila.</div>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">
    <div class="card">
      <h3>Câmera</h3>
      <div class="video-wrap">
        <video id="video" autoplay playsinline muted></video>
        <canvas id="meshOverlay"></canvas>
      </div>
      <div class="small-note">Malha facial geral + contorno dos olhos + íris opcional. Nesta versão, o olhar ocular passa a ser o controle principal do cursor; a cabeça entra como fallback e estabilização.</div>
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
      <div class="meta-line"><span>Modo</span><strong id="trackingModeText">Aguardando</strong></div>
      <div class="meta-line"><span>Hover atual</span><strong id="hoverText">—</strong></div>
      <div class="meta-line"><span>Calibração</span><strong id="calibrationText">Pendente</strong></div>
      <div class="meta-line"><span>Zoom</span><strong id="zoomText">Normal</strong></div>
    </div>

    <div class="card">
      <h3>Obra em foco</h3>
      <div id="selected-title">Nenhuma obra em foco</div>
      <div id="selected-artist">Olhe para uma obra para ver a ficha. 1 piscada afasta. 2 piscadas aproximam.</div>
      <div id="selected-description">O sistema usa permanência do olhar para foco e mantém o zoom principal por distância do rosto + botões. Em câmera boa, o blink pode entrar como reforço opcional.</div>
    </div>

    <div class="card">
      <h3>Guia de blinks</h3>
      <div class="blink-guide">
        <div class="blink-card">
          <div class="icon">1×</div>
          <div class="bl">1 piscada</div>
          <div class="desc">Extra opcional: afasta</div>
        </div>
        <div class="blink-card">
          <div class="icon">2×</div>
          <div class="bl">2 piscadas rápidas</div>
          <div class="desc">Aproxima a obra em foco</div>
        </div>
      </div>
    </div>


    <div class="card">
      <h3>Zoom manual / câmera fraca</h3>
      <div class="manual-zoom">
        <button class="btn primary" id="zoomInBtn">+ Aproximar</button>
        <button class="btn warn" id="zoomOutBtn">− Afastar</button>
      </div>
      <div class="status-note" id="weakZoomNote">O zoom principal responde pela distância do rosto e pelos botões. O botão manual agora escolhe automaticamente a obra mais próxima do olhar ou do centro da galeria.</div>
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
const meshOverlay  = document.getElementById('meshOverlay');
const focusInfoCard= document.getElementById('focus-info-card');
const ctx          = roomCanvas.getContext('2d');
const heatCtx      = heatmapCanvas.getContext('2d');
const revealCtx    = revealCanvas.getContext('2d');
const meshCtx      = meshOverlay.getContext('2d');
const analysisCanvas = document.createElement('canvas');
analysisCanvas.width = 160; analysisCanvas.height = 120;
const analysisCtx = analysisCanvas.getContext('2d', {willReadFrequently:true});

const gazeCursor    = document.getElementById('gaze-cursor');
const dwellFill     = document.getElementById('dwellFill');
const statusDot     = document.getElementById('statusDot');
const statusText    = document.getElementById('statusText');
const modeText      = document.getElementById('modeText');
const blinkText     = document.getElementById('blinkText');
const blinkIndicator= document.getElementById('blink-indicator');
const permNote      = document.getElementById('permission-note');
const qualityText   = document.getElementById('qualityText');
const trackingModeText = document.getElementById('trackingModeText');
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
const zoomInBtn     = document.getElementById('zoomInBtn');
const zoomOutBtn    = document.getElementById('zoomOutBtn');
const weakZoomNote  = document.getElementById('weakZoomNote');

// ─── UTILS ───
const clamp = (v,a,b) => Math.min(b, Math.max(a,v));
const lerp  = (a,b,t) => a + (b-a)*t;
const avgKey= (pts,k) => pts.reduce((s,p)=>s+p[k],0) / Math.max(1,pts.length);
const dist2 = (a,b,c,d) => Math.hypot(a-c,b-d);

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
  dwellMs:900,

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
    phase:'open',
    closeTs:0,
    ema:0.27,
    emaFast:0.27,
    baseline:0.27,
    baselineReady:false,
    warmupFrames:0,
    stableFrames:0,
    minBaseline:0.15,
    maxBaseline:0.42,
    closeRatio:0.72,
    openRatio:0.86,
    threshClose:0.18,
    threshOpen:0.24,
    minMs:32,
    maxMs:420,
    closeFrames:0,
    openFrames:0,
    minCloseFrames:2,
    minOpenFrames:2,
    pendingSingleTs:0,
    lastBlinkTs:0,
    lastEventTs:0,
    lastCycleMs:0,
    doubleWindowMs:560,
    debounceMs:88,
    eyeConfidence:0,
    lastLeft:0.27,
    lastRight:0.27,
    ratio:1,
    debugLast:'init'
  },

  tracking:{
    invertX:true,
    mirrorInput:true,
    history:[],
    historyMax:10,
    baselineReady:false,
    baselineFrames:0,
    baseline:{
      centerX:0.5,
      centerY:0.5,
      yaw:0,
      pitch:0,
      size:0.22,
      eyeX:0,
      eyeY:0
    },
    deadzoneX:0.018,
    deadzoneY:0.012,
    centerGainX:0.015,
    centerGainY:0.78,
    yawGainX:2.08,
    pitchGainY:0.34,
    lastSizeRatio:1,
    sizeVelocity:0,
    videoBrightnessScore:0.6,
    videoSharpnessScore:0.55,
    stabilityScore:0.6,
    totalQuality:0.62,
    modeKind:'full',
    weakZoomCooldownUntil:0,
    weakZoomArmed:true,
    lastModeTs:0,
    lastDistanceZoomTs:0,
    distanceNeutralFrames:0,
    frameCounter:0,
    ocularConfidence:0.62,
    irisAvailable:false
  },

  parallax:{
    inited:false,
    starsFar:[],
    starsMid:[],
    orbs:[],
    ribbons:[],
    dustNear:[],
    depthPanels:[],
    artFloaters:[]
  },

  zoom:{
    active:false,
    targetId:null,
    focus:0,
    focusTarget:0,
    dwellLevel:0
  }
};

const modeConfig = {
  full:{label:'Completo', allowBlink:true, usesFaceDistance:true},
  hybrid:{label:'Híbrido', allowBlink:true, usesFaceDistance:true},
  weak:{label:'Câmera fraca', allowBlink:false, usesFaceDistance:true}
};

const FACE_OVAL = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109,10];
const LEFT_EYE = [33,160,158,133,153,144,33];
const RIGHT_EYE = [362,385,387,263,373,380,362];
const LEFT_BROW = [70,63,105,66,107];
const RIGHT_BROW = [336,296,334,293,300];
const NOSE_LINE = [168,6,197,195,5,4,1,19,94,2];
const MOUTH_OUTER = [61,146,91,181,84,17,314,405,321,375,291,308,324,318,402,317,14,87,178,88,95,78,61];
const LEFT_IRIS = [468,469,470,471,472,468];
const RIGHT_IRIS = [473,474,475,476,477,473];

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
function setTrackingMode(kind){
  const cfg = modeConfig[kind] || modeConfig.full;
  state.tracking.modeKind = kind;
  trackingModeText.textContent = cfg.label;
  weakZoomNote.textContent = cfg.allowBlink
    ? 'Zoom principal por distância do rosto + botões. Blink permanece ativo quando a leitura ocular estiver estável.'
    : 'Câmera fraca detectada: blink desligado automaticamente. O zoom continua pela distância do rosto e pelos botões.';
  if(kind === 'weak') {
    permNote.textContent = 'Câmera fraca detectada: o olhar tenta manter o alvo, a cabeça assume a estabilidade, a obra entra por permanência do olhar e o zoom segue pela distância do rosto + botões.';
  } else if(kind === 'hybrid') {
    permNote.textContent = 'Modo híbrido ativo: o olhar ocular controla o cursor, a cabeça estabiliza a direção, foco por permanência do olhar, zoom principal por distância do rosto + botões e blink ativo quando possível.';
  } else {
    permNote.textContent = 'Tracking ativo. O olhar ocular controla o cursor, a obra entra em foco por permanência do olhar, e o zoom principal responde à distância do rosto + botões. Blink fica disponível quando a leitura ocular estiver estável.';
  }
}

function flashBlinkIndicator(msg){
  blinkIndicator.textContent = msg;
  blinkIndicator.classList.add('show');
  clearTimeout(blinkIndicator._t);
  blinkIndicator._t = setTimeout(()=>blinkIndicator.classList.remove('show'), 1200);
}

function resetBlinkState(){
  state.blink.phase = 'open';
  state.blink.closeTs = 0;
  state.blink.closeFrames = 0;
  state.blink.openFrames = 0;
  state.blink.pendingSingleTs = 0;
  state.blink.lastBlinkTs = 0;
  state.blink.lastEventTs = 0;
  state.blink.lastCycleMs = 0;
  state.blink.ema = 0.27;
  state.blink.emaFast = 0.27;
  state.blink.baseline = 0.27;
  state.blink.baselineReady = false;
  state.blink.warmupFrames = 0;
  state.blink.stableFrames = 0;
  state.blink.eyeConfidence = 0;
  state.blink.lastLeft = 0.27;
  state.blink.lastRight = 0.27;
  state.blink.ratio = 1;
  state.blink.debugLast = 'reset';
  setBlink('Pronto');
  gazeCursor.style.borderColor = 'rgba(255,255,255,.92)';
}

function resetTrackingState(){
  state.tracking.history = [];
  state.tracking.baselineReady = false;
  state.tracking.baselineFrames = 0;
  state.tracking.lastSizeRatio = 1;
  state.tracking.sizeVelocity = 0;
  state.tracking.totalQuality = 0.62;
  state.tracking.weakZoomCooldownUntil = 0;
  state.tracking.weakZoomArmed = true;
  state.tracking.lastDistanceZoomTs = 0;
  state.tracking.distanceNeutralFrames = 0;
  state.tracking.baseline = {
    centerX:0.5,
    centerY:0.5,
    yaw:0,
    pitch:0,
    size:0.22,
    eyeX:0,
    eyeY:0
  };
  state.tracking.ocularConfidence = 0.62;
  state.tracking.irisAvailable = false;
  state.zoom.dwellLevel = 0;
  setTrackingMode('full');
}

// ─── RESIZE ───
function syncVideoOverlaySize(){
  const r = video.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  meshOverlay.width = Math.max(1, Math.floor(r.width * dpr));
  meshOverlay.height = Math.max(1, Math.floor(r.height * dpr));
  meshOverlay.style.width = r.width + 'px';
  meshOverlay.style.height = r.height + 'px';
  meshCtx.setTransform(dpr,0,0,dpr,0,0);
}

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
  syncVideoOverlaySize();
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

  const dustNear = [];
  for(let i=0;i<34;i++){
    dustNear.push({
      x:Math.random(),
      y:Math.random(),
      r:1.4 + Math.random()*3.2,
      a:0.04 + Math.random()*0.10,
      depth:0.55 + Math.random()*0.45,
      drift:0.05 + Math.random()*0.12
    });
  }
  state.parallax.dustNear = dustNear;

  state.parallax.depthPanels = [
    {x:-3.65,y:2.05,z:2.2,w:1.25,h:1.95,plane:'left',  tint:'93,173,226', alpha:0.08},
    {x: 3.65,y:2.05,z:2.6,w:1.10,h:1.85,plane:'right', tint:'165,105,189', alpha:0.08},
    {x:-1.05,y:2.35,z:8.35,w:1.10,h:1.55,plane:'back',  tint:'93,173,226', alpha:0.06},
    {x: 1.20,y:2.10,z:7.75,w:1.00,h:1.35,plane:'back',  tint:'240,192,64', alpha:0.06}
  ];

  state.parallax.artFloaters = artworks.map((art, idx)=>(
    {
      artId: art.id,
      phase: idx * 0.9 + Math.random(),
      amp: 0.009 + Math.random()*0.010,
      alpha: 0.05 + Math.random()*0.04
    }
  ));
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



function parallaxOffsetForArt(art){
  const depth = art.plane === 'back' ? 0.42 : 0.54;
  const xShift = (gaze.x - 0.5) * (art.plane === 'back' ? 44 : 34) * depth;
  const yShift = (gaze.y - 0.5) * 20 * depth;
  return {x:xShift, y:yShift, depth};
}

function drawDepthPanels(){
  state.parallax.depthPanels.forEach(panel=>{
    const pts = polyPts(panel);
    if(!pts || pts.some(p=>!p)) return;
    const off = parallaxOffsetForArt(panel);
    const shifted = pts.map(pt=>({x:pt.x + off.x * 0.22, y:pt.y + off.y * 0.12, depth:pt.depth, scale:pt.scale}));
    const cx = shifted.reduce((s,p)=>s+p.x,0) / shifted.length;
    const cy = shifted.reduce((s,p)=>s+p.y,0) / shifted.length;
    const grad = ctx.createRadialGradient(cx - off.x*0.1, cy - off.y*0.1, 0, cx, cy, 160);
    grad.addColorStop(0, 'rgba('+panel.tint+','+(panel.alpha*1.5).toFixed(3)+')');
    grad.addColorStop(0.65, 'rgba('+panel.tint+','+panel.alpha.toFixed(3)+')');
    grad.addColorStop(1, 'rgba('+panel.tint+',0)');
    drawPoly(shifted, grad, 'rgba(255,255,255,0.06)', 1.1);
  });
}

function drawParallaxForeground(r, gx, gy){
  const t = performance.now() * 0.001;
  state.parallax.dustNear.forEach(p=>{
    const x = wrap(r.width * p.x + gx * r.width * p.depth * 0.58 + Math.sin(t*p.drift + p.x*6) * 12, r.width);
    const y = wrap(r.height * p.y + gy * r.height * p.depth * 0.44 + Math.cos(t*p.drift + p.y*7) * 8, r.height);
    const rr = p.r * (1 + Math.abs(gx) * 0.14);
    const g = ctx.createRadialGradient(x, y, 0, x, y, rr*3.2);
    g.addColorStop(0, 'rgba(255,255,255,'+(p.a*1.1).toFixed(3)+')');
    g.addColorStop(0.5, 'rgba(191,214,246,'+(p.a*0.55).toFixed(3)+')');
    g.addColorStop(1, 'rgba(191,214,246,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, rr*3.2, 0, Math.PI*2);
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
    selTitle.textContent='Nenhuma obra em foco';
    selArtist.textContent='Olhe para uma obra para ver a ficha. 1 piscada afasta. 2 piscadas rápidas aproximam.';
    selDesc.textContent='Se a câmera estiver fraca, o sistema desliga o blink sozinho e usa permanência do olhar + distância do rosto + botões.';
    return;
  }
  selTitle.textContent=art.title;
  selArtist.textContent=art.artist+' · '+art.year+' · parede '+art.wall;
  selDesc.textContent=art.desc;
}

function updateFocusInfoCard(){
  const activeId = state.hoveredId || state.selectedId || state.zoom.targetId;
  const activeArt = artById(activeId);
  if(!activeArt || !projectedArtworks.length){
    focusInfoCard.classList.remove('show');
    return;
  }
  const entry = projectedArtworks.find(p=>p.art.id===activeArt.id);
  if(!entry || !entry.center){
    focusInfoCard.classList.remove('show');
    return;
  }
  const r = scenePanel.getBoundingClientRect();
  focusInfoCard.querySelector('.ttl').textContent = activeArt.title;
  focusInfoCard.querySelector('.sub').textContent = activeArt.artist+' · '+activeArt.year;
  focusInfoCard.querySelector('.txt').textContent = activeArt.desc;
  focusInfoCard.style.left = clamp(entry.center.x, 90, r.width-90) + 'px';
  focusInfoCard.style.top = clamp(entry.center.y - 16, 70, r.height-26) + 'px';
  focusInfoCard.classList.add('show');
}

function zoomInToArtwork(art, source, amount){
  if(!art) return;
  state.selectedId = art.id;
  state.zoom.active = true;
  state.zoom.targetId = art.id;
  state.zoom.focusTarget = clamp(Math.max(state.zoom.focusTarget, 0.16) + (amount || 0.26), 0, 1);
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
  if(!art) return;
  state.selectedId = art.id;
  updateSelPanel(art);
  if(source === 'dwell'){
    zoomInToArtwork(art, source || 'select', 0.12);
  } else if(source && source.startsWith('manual')){
    zoomInToArtwork(art, source, 0.24);
  } else {
    state.zoom.targetId = art.id;
  }
}

function zoomOutStep(source){
  if(state.zoom.focusTarget <= 0.02){
    resetZoom();
    return;
  }
  state.zoom.focusTarget = clamp(state.zoom.focusTarget - 0.30, 0, 1);
  if(state.zoom.focusTarget <= 0.05){
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
  state.zoom.dwellLevel = 0;
  zoomText.textContent = 'Normal';
  updateSelPanel(state.hoveredId ? artById(state.hoveredId) : null);
}

function closestProjectedArtwork(px, py, radiusFactor){
  if(!projectedArtworks || !projectedArtworks.length) return null;
  const r = scenePanel.getBoundingClientRect();
  let best = null;
  let bestD = Infinity;
  projectedArtworks.forEach(entry=>{
    const cx = entry.center?.x ?? ((entry.poly[0].x + entry.poly[1].x + entry.poly[2].x + entry.poly[3].x) / 4);
    const cy = entry.center?.y ?? ((entry.poly[0].y + entry.poly[1].y + entry.poly[2].y + entry.poly[3].y) / 4);
    const d = Math.hypot(cx - px, cy - py);
    if(d < bestD){
      bestD = d;
      best = entry.art;
    }
  });
  const radius = Math.min(r.width, r.height) * (radiusFactor ?? 0.42);
  return best && bestD <= radius ? best : null;
}

function resolveZoomTarget(preferCenter){
  const hovered = artById(state.hoveredId);
  const selected = artById(state.selectedId);
  const zoomed = artById(state.zoom.targetId);
  if(hovered) return hovered;
  if(selected) return selected;
  if(zoomed) return zoomed;

  const r = scenePanel.getBoundingClientRect();
  const gx = preferCenter ? r.width * 0.5 : gaze.x * r.width;
  const gy = preferCenter ? r.height * 0.5 : gaze.y * r.height;
  const nearGaze = closestProjectedArtwork(gx, gy, preferCenter ? 0.58 : 0.42);
  if(nearGaze) return nearGaze;
  const nearCenter = closestProjectedArtwork(r.width*0.5, r.height*0.54, 0.70);
  if(nearCenter) return nearCenter;
  return artworks[1] || artworks[0] || null;
}

function blinkTarget(){
  return resolveZoomTarget(false);
}

function manualZoomIn(source){
  const target = resolveZoomTarget(false);
  if(target){
    zoomInToArtwork(target, source || 'manual_zoom_in', target.id === state.hoveredId ? 0.26 : 0.24);
    flashBlinkIndicator('＋ zoom manual → "'+target.title+'"');
  } else {
    state.zoom.focusTarget = clamp(state.zoom.focusTarget + 0.18, 0, 1);
    state.zoom.active = state.zoom.focusTarget > 0.01;
    zoomText.textContent = state.zoom.active ? 'Ativo' : 'Normal';
  }
}

function manualZoomOut(source){
  if(state.zoom.focusTarget > 0.01){
    zoomOutStep(source || 'manual_zoom_out');
    flashBlinkIndicator('－ zoom manual → afasta');
  } else {
    resetZoom();
  }
}

function onSingleBlink(){
  zoomOutStep('single_blink');
  flashBlinkIndicator('👁 1 piscada → afasta');
  log('Single blink → afasta');
}

function onDoubleBlink(){
  const target = blinkTarget();
  if(target){
    zoomInToArtwork(target, 'double_blink', target.id === state.hoveredId ? 0.30 : 0.24);
    flashBlinkIndicator('👁👁 2 piscadas → aproxima "'+target.title+'"');
    log('Double blink → aproxima ' + target.title);
  } else {
    flashBlinkIndicator('👁👁 2 piscadas sem obra em foco');
    log('Double blink sem alvo útil');
  }
}

function flushPendingSingleBlink(now){
  if(!state.blink.pendingSingleTs) return;
  if((now - state.blink.pendingSingleTs) >= state.blink.doubleWindowMs){
    state.blink.pendingSingleTs = 0;
    state.blink.debugLast = 'single_fire';
    setBlink('1x');
    onSingleBlink();
  }
}

function registerBlink(now){
  if((now - state.blink.lastEventTs) < state.blink.debounceMs){
    state.blink.debugLast = 'debounced';
    return;
  }

  if(state.blink.pendingSingleTs && (now - state.blink.pendingSingleTs) <= state.blink.doubleWindowMs){
    state.blink.pendingSingleTs = 0;
    state.blink.lastBlinkTs = now;
    state.blink.lastEventTs = now;
    state.blink.debugLast = 'double';
    setBlink('2x');
    onDoubleBlink();
    return;
  }

  state.blink.pendingSingleTs = now;
  state.blink.lastBlinkTs = now;
  state.blink.lastEventTs = now;
  state.blink.debugLast = 'single_wait';
  setBlink('1?');
}

function eyeContourOpenness(lm, verts, outerIdx, innerIdx){
  const horizontal = dist2(lm[outerIdx].x, lm[outerIdx].y, lm[innerIdx].x, lm[innerIdx].y);
  const verticals = verts.map(pair => dist2(lm[pair[0]].x, lm[pair[0]].y, lm[pair[1]].x, lm[pair[1]].y));
  const avgVert = verticals.reduce((s,v)=>s+v,0) / Math.max(1, verticals.length);
  return avgVert / Math.max(horizontal, 1e-6);
}

function processBlink(landmarks){
  const leftOpen  = eyeContourOpenness(landmarks, [[159,145],[160,144],[158,153]], 33, 133);
  const rightOpen = eyeContourOpenness(landmarks, [[386,374],[385,380],[387,373]], 362, 263);
  const now = Date.now();

  state.blink.lastLeft = lerp(state.blink.lastLeft, leftOpen, 0.36);
  state.blink.lastRight = lerp(state.blink.lastRight, rightOpen, 0.36);

  const rawAvg = (state.blink.lastLeft + state.blink.lastRight) * 0.5;
  const asym = Math.abs(state.blink.lastLeft - state.blink.lastRight);
  const rawOpen = rawAvg * 0.42 + Math.min(state.blink.lastLeft, state.blink.lastRight) * 0.58;

  state.blink.emaFast = lerp(state.blink.emaFast, rawOpen, 0.44);
  state.blink.ema = lerp(state.blink.ema, rawOpen, 0.18);

  if(state.blink.phase === 'open'){
    state.blink.warmupFrames += 1;
    const stableInput = Math.abs(state.blink.emaFast - state.blink.ema) < 0.022 && asym < 0.12;
    if(stableInput) state.blink.stableFrames += 1;
    else state.blink.stableFrames = Math.max(0, state.blink.stableFrames - 1);

    if(!state.blink.baselineReady){
      state.blink.baseline = lerp(state.blink.baseline, clamp(state.blink.ema, state.blink.minBaseline, state.blink.maxBaseline), 0.08);
      if(state.blink.warmupFrames > 10 && state.blink.stableFrames >= 6){
        state.blink.baselineReady = true;
      }
    } else if(state.blink.ema > state.blink.baseline * 0.82 && asym < 0.13){
      state.blink.baseline = lerp(
        state.blink.baseline,
        clamp(state.blink.ema, state.blink.minBaseline, state.blink.maxBaseline),
        0.016
      );
    }
  }

  const baseline = clamp(state.blink.baseline, state.blink.minBaseline, state.blink.maxBaseline);
  const ratio = clamp(state.blink.emaFast / Math.max(0.001, baseline), 0, 1.5);
  const closeThresh = clamp(state.blink.closeRatio, 0.58, 0.82);
  const openThresh  = clamp(state.blink.openRatio, 0.76, 0.94);
  state.blink.ratio = ratio;
  state.blink.threshClose = closeThresh;
  state.blink.threshOpen = openThresh;

  const eyeScore = (
    clamp((baseline - 0.14) / 0.16, 0, 1) * 0.34 +
    clamp((0.11 - asym) / 0.11, 0, 1) * 0.20 +
    clamp((0.03 - Math.abs(state.blink.emaFast - state.blink.ema)) / 0.03, 0, 1) * 0.20 +
    (state.blink.baselineReady ? 0.26 : 0.05)
  );
  state.blink.eyeConfidence = clamp(eyeScore, 0, 1);

  if(ratio < closeThresh){
    state.blink.closeFrames += 1;
    state.blink.openFrames = 0;
  } else if(ratio > openThresh){
    state.blink.openFrames += 1;
    if(state.blink.phase === 'open') state.blink.closeFrames = 0;
  }

  if(state.tracking.modeKind === 'weak'){
    state.blink.debugLast = 'blink_disabled_weak';
    setBlink('Auto off');
    state.blink.phase = 'open';
    state.blink.closeFrames = 0;
    state.blink.openFrames = 0;
    state.blink.pendingSingleTs = 0;
    return;
  }

  const minEyeScore = state.tracking.modeKind === 'hybrid' ? 0.44 : 0.54;
  if(!state.blink.baselineReady || state.blink.eyeConfidence < minEyeScore){
    setBlink(state.tracking.modeKind === 'hybrid' ? 'Opcional' : 'Calibrando');
    return;
  }

  if(state.blink.phase === 'open' && state.blink.closeFrames >= state.blink.minCloseFrames){
    state.blink.phase = 'closed';
    state.blink.closeTs = now;
    state.blink.debugLast = 'closed';
    setBlink('Fechado');
    gazeCursor.style.borderColor = 'rgba(243,156,18,.9)';
  } else if(state.blink.phase === 'closed' && state.blink.openFrames >= state.blink.minOpenFrames){
    const dur = now - state.blink.closeTs;
    state.blink.phase = 'open';
    state.blink.closeFrames = 0;
    state.blink.openFrames = 0;
    state.blink.lastCycleMs = dur;
    state.blink.debugLast = 'open';
    gazeCursor.style.borderColor = 'rgba(255,255,255,.92)';
    if(dur >= state.blink.minMs && dur <= state.blink.maxMs){
      registerBlink(now);
    } else {
      state.blink.debugLast = 'ignored_'+dur;
    }
  }
}

function updateVideoQuality(){
  if(video.readyState < 2) return;
  analysisCtx.drawImage(video, 0, 0, analysisCanvas.width, analysisCanvas.height);
  const data = analysisCtx.getImageData(0,0,analysisCanvas.width,analysisCanvas.height).data;
  let lumSum = 0;
  let sharp = 0;
  let count = 0;
  const w = analysisCanvas.width;
  const h = analysisCanvas.height;
  for(let y=0; y<h-2; y+=2){
    for(let x=0; x<w-2; x+=2){
      const i = (y*w + x) * 4;
      const l = data[i]*0.299 + data[i+1]*0.587 + data[i+2]*0.114;
      const ir = i + 8;
      const ib = i + w*4*2;
      const lr = data[ir]*0.299 + data[ir+1]*0.587 + data[ir+2]*0.114;
      const lb = data[ib]*0.299 + data[ib+1]*0.587 + data[ib+2]*0.114;
      lumSum += l;
      sharp += Math.abs(l-lr) + Math.abs(l-lb);
      count += 1;
    }
  }
  const avgLum = lumSum / Math.max(1, count);
  const avgSharp = sharp / Math.max(1, count);
  state.tracking.videoBrightnessScore = lerp(state.tracking.videoBrightnessScore, clamp((avgLum - 42) / 92, 0, 1), 0.25);
  state.tracking.videoSharpnessScore = lerp(state.tracking.videoSharpnessScore, clamp((avgSharp - 10) / 30, 0, 1), 0.25);
}

function updateTrackingMode(){
  const blinkScore = state.blink.eyeConfidence || 0;
  const gazeScore = state.tracking.ocularConfidence || 0;
  const stability = clamp(1 - (Math.abs(gaze.targetX - gaze.x) + Math.abs(gaze.targetY - gaze.y)) * 1.8, 0, 1);
  state.tracking.stabilityScore = lerp(state.tracking.stabilityScore, stability, 0.22);

  const total = 0.28
    + 0.20 * state.tracking.videoBrightnessScore
    + 0.19 * state.tracking.videoSharpnessScore
    + 0.15 * state.tracking.stabilityScore
    + 0.12 * gazeScore
    + 0.06 * blinkScore
    + (state.tracking.irisAvailable ? 0.04 : 0.0);

  state.tracking.totalQuality = lerp(state.tracking.totalQuality, clamp(total, 0, 1), 0.24);

  let next = 'weak';
  if(state.tracking.totalQuality >= 0.74 && (gazeScore >= 0.52 || blinkScore >= 0.52) && state.tracking.videoSharpnessScore >= 0.22){
    next = 'full';
  } else if(state.tracking.totalQuality >= 0.50){
    next = 'hybrid';
  }

  if(next !== state.tracking.modeKind){
    setTrackingMode(next);
    state.tracking.lastModeTs = Date.now();
    if(next === 'weak'){
      flashBlinkIndicator('📷 câmera fraca → fallback cabeça/distância');
      log('Modo câmera fraca ativado. Cursor fica no olhar quando possível, mas a cabeça e a distância do rosto assumem a estabilidade.');
    } else if(next === 'hybrid'){
      flashBlinkIndicator('🧭 modo híbrido → olhar + cabeça');
      log('Modo híbrido ativado: olhar ocular principal com fallback da cabeça e zoom híbrido.');
    } else {
      flashBlinkIndicator('👁 rastreamento ocular principal ativo');
      log('Modo completo ativo com olhar ocular principal, blink ativo e fallback de cabeça.');
    }
  }

  const label = Math.round(state.tracking.totalQuality * 100)+'% · luz '+Math.round(state.tracking.videoBrightnessScore*100)+' · nitidez '+Math.round(state.tracking.videoSharpnessScore*100)+' · olhar '+Math.round(gazeScore*100)+' · blink '+Math.round(blinkScore*100);
  qualityText.textContent = label;
  setMode('Webcam · '+modeConfig[state.tracking.modeKind].label);
}

function processDistanceZoom(now){
  const ratio = state.tracking.lastSizeRatio || 1;
  const target = blinkTarget();

  const inThresh  = state.tracking.modeKind === 'weak' ? 1.08 : (state.tracking.modeKind === 'hybrid' ? 1.11 : 1.14);
  const outThresh = state.tracking.modeKind === 'weak' ? 0.94 : (state.tracking.modeKind === 'hybrid' ? 0.91 : 0.88);
  const inCooldown = state.tracking.modeKind === 'weak' ? 620 : 760;
  const outCooldown = 620;

  const nearNeutral = ratio > 0.98 && ratio < 1.02;
  state.tracking.distanceNeutralFrames = nearNeutral
    ? Math.min(12, state.tracking.distanceNeutralFrames + 1)
    : Math.max(0, state.tracking.distanceNeutralFrames - 1);

  const allowAction = (now - state.tracking.lastDistanceZoomTs) > Math.min(inCooldown, outCooldown);

  if(ratio > inThresh && allowAction && target){
    zoomInToArtwork(target, 'distancia_rosto', state.tracking.modeKind === 'full' ? 0.16 : 0.18);
    flashBlinkIndicator('↗ rosto aproximou → zoom in');
    state.tracking.lastDistanceZoomTs = now;
    state.tracking.distanceNeutralFrames = 0;
    return;
  }

  if(ratio < outThresh && allowAction && state.zoom.focusTarget > 0.02){
    zoomOutStep('distancia_rosto');
    flashBlinkIndicator('↘ rosto afastou → zoom out');
    state.tracking.lastDistanceZoomTs = now;
    state.tracking.distanceNeutralFrames = 0;
    return;
  }

  if(nearNeutral && state.tracking.distanceNeutralFrames >= 6 && state.tracking.baselineReady && state.zoom.focusTarget < 0.08 && state.blink.phase !== 'closed'){
    state.tracking.baseline.size = lerp(state.tracking.baseline.size, avgHistory('size') || state.tracking.baseline.size, 0.015);
  }
}

function drawMeshOverlay(landmarks){
  syncVideoOverlaySize();
  const w = meshOverlay.clientWidth;
  const h = meshOverlay.clientHeight;
  meshCtx.clearRect(0,0,w,h);
  if(!landmarks || !w || !h) return;
  const toPt = idx => ({x:(1-landmarks[idx].x) * w, y:landmarks[idx].y * h});
  const strokeSeq = (indices, color, width) => {
    meshCtx.beginPath();
    indices.forEach((idx, n)=>{
      if(!landmarks[idx]) return;
      const p = toPt(idx);
      if(n===0) meshCtx.moveTo(p.x,p.y);
      else meshCtx.lineTo(p.x,p.y);
    });
    meshCtx.strokeStyle = color;
    meshCtx.lineWidth = width;
    meshCtx.stroke();
  };
  strokeSeq(FACE_OVAL, 'rgba(93,173,226,.52)', 1.4);
  strokeSeq(LEFT_BROW, 'rgba(255,255,255,.44)', 1.2);
  strokeSeq(RIGHT_BROW, 'rgba(255,255,255,.44)', 1.2);
  strokeSeq(LEFT_EYE, 'rgba(46,204,113,.75)', 1.6);
  strokeSeq(RIGHT_EYE, 'rgba(46,204,113,.75)', 1.6);
  strokeSeq(NOSE_LINE, 'rgba(255,255,255,.32)', 1.1);
  strokeSeq(MOUTH_OUTER, 'rgba(165,105,189,.30)', 1.0);
  if(landmarks[468]) strokeSeq(LEFT_IRIS, 'rgba(240,192,64,.65)', 1.1);
  if(landmarks[473]) strokeSeq(RIGHT_IRIS, 'rgba(240,192,64,.65)', 1.1);
}

function clearMeshOverlay(){
  syncVideoOverlaySize();
  meshCtx.clearRect(0,0,meshOverlay.clientWidth, meshOverlay.clientHeight);
}

// ─── EYE TRACKING / GAZE MAPPING ───
// Adaptado para a galeria web a partir da lógica do código ocular enviado pelo usuário:
// contorno dos olhos + centro da íris quando disponível + calibração dinâmica do baseline.
// No navegador não dá para encaixar diretamente o pipeline OpenCV/Tkinter do arquivo externo,
// então esta versão transpõe a mesma ideia para MediaPipe FaceMesh dentro da galeria.

function lmMapped(lm, idx){
  const p = lm[idx];
  if(!p) return null;
  return { x: state.tracking.mirrorInput ? (1 - p.x) : p.x, y: p.y };
}

function avgMapped(lm, ids){
  let sx = 0, sy = 0, n = 0;
  ids.forEach(idx=>{
    const p = lmMapped(lm, idx);
    if(!p) return;
    sx += p.x; sy += p.y; n += 1;
  });
  return n ? {x:sx/n, y:sy/n} : null;
}

function faceMetrics(lm){
  const nose = lmMapped(lm, 1);
  const forehead = lmMapped(lm, 10);
  const chin = lmMapped(lm, 152);
  const leftEyeOuter = lmMapped(lm, 33);
  const rightEyeOuter = lmMapped(lm, 263);
  const leftCheek = lmMapped(lm, 234);
  const rightCheek = lmMapped(lm, 454);
  const mouthTop = lmMapped(lm, 13);
  const mouthBot = lmMapped(lm, 14);

  if(!nose || !forehead || !chin || !leftEyeOuter || !rightEyeOuter || !leftCheek || !rightCheek || !mouthTop || !mouthBot){
    return null;
  }

  const eyeMidX = (leftEyeOuter.x + rightEyeOuter.x) * 0.5;
  const mouthMidY = (mouthTop.y + mouthBot.y) * 0.5;
  const faceWidth = Math.max(0.001, Math.abs(rightCheek.x - leftCheek.x));
  const faceHeight = Math.max(0.001, chin.y - forehead.y);
  const faceMidY = (forehead.y + chin.y) * 0.5;

  return {
    centerX: clamp(nose.x * 0.58 + eyeMidX * 0.42, 0, 1),
    centerY: clamp(nose.y * 0.64 + mouthMidY * 0.36, 0, 1),
    yaw: (nose.x - eyeMidX) / Math.max(0.001, Math.abs(rightEyeOuter.x - leftEyeOuter.x)),
    pitch: (nose.y - faceMidY) / faceHeight,
    size: faceWidth,
    faceHeight
  };
}

function eyeBoxMetrics(lm, outerIdx, innerIdx, upperIds, lowerIds, irisIds){
  const outer = lmMapped(lm, outerIdx);
  const inner = lmMapped(lm, innerIdx);
  const upper = avgMapped(lm, upperIds);
  const lower = avgMapped(lm, lowerIds);
  const iris = avgMapped(lm, irisIds.slice(0, 5));
  if(!outer || !inner || !upper || !lower) return null;

  const center = {
    x: (outer.x + inner.x) * 0.5,
    y: (upper.y + lower.y) * 0.5
  };
  const width = Math.max(1e-5, Math.hypot(inner.x - outer.x, inner.y - outer.y));
  const height = Math.max(1e-5, Math.abs(lower.y - upper.y));
  const openness = height / width;

  let eyeX = 0;
  let eyeY = 0;
  let irisOk = false;
  let conf = clamp((openness - 0.04) / 0.08, 0, 1) * 0.45;

  if(iris){
    eyeX = clamp((iris.x - center.x) / Math.max(1e-5, width * 0.48), -1.4, 1.4);
    eyeY = clamp((iris.y - center.y) / Math.max(1e-5, height * 1.35), -1.2, 1.2);
    irisOk = true;
    conf = clamp(conf + 0.40 + clamp((0.09 - Math.abs(eyeY)) / 0.09, 0, 1) * 0.15, 0, 1);
  }

  return { outer, inner, upper, lower, center, iris, width, height, openness, eyeX, eyeY, irisOk, conf };
}

function computeEyeGazeMetrics(lm){
  const head = faceMetrics(lm);
  if(!head) return null;

  const left = eyeBoxMetrics(lm, 33, 133, [159,160,158], [145,144,153], LEFT_IRIS);
  const right = eyeBoxMetrics(lm, 362, 263, [386,385,387], [374,380,373], RIGHT_IRIS);
  if(!left || !right) return null;

  const irisAvailable = !!(left.irisOk && right.irisOk);
  const ocularConfidence = irisAvailable
    ? clamp((left.conf + right.conf) * 0.5 - (Math.abs(left.eyeX - right.eyeX) * 0.14), 0, 1)
    : clamp((left.conf + right.conf) * 0.32, 0, 0.46);

  const eyeX = irisAvailable ? ((left.eyeX + right.eyeX) * 0.5) : 0;
  const eyeY = irisAvailable ? ((left.eyeY + right.eyeY) * 0.5) : 0;

  return {
    centerX: head.centerX,
    centerY: head.centerY,
    yaw: head.yaw,
    pitch: head.pitch,
    size: head.size,
    eyeX,
    eyeY,
    irisAvailable,
    ocularConfidence,
    openness:(left.openness + right.openness) * 0.5,
    eyeAsym: Math.abs(left.eyeX - right.eyeX) + Math.abs(left.eyeY - right.eyeY)
  };
}

function updateEyeTrackingBaseline(m){
  const b = state.tracking.baseline;
  state.tracking.ocularConfidence = lerp(state.tracking.ocularConfidence || 0.62, m.ocularConfidence, 0.22);
  state.tracking.irisAvailable = !!m.irisAvailable;

  if(!state.tracking.baselineReady){
    state.tracking.baselineFrames += 1;
    const t = Math.min(1, state.tracking.baselineFrames / 18);
    b.centerX = lerp(b.centerX, m.centerX, 0.20 * t);
    b.centerY = lerp(b.centerY, m.centerY, 0.20 * t);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.20 * t);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.20 * t);
    b.size    = lerp(b.size,    m.size,    0.18 * t);
    b.eyeX    = lerp(b.eyeX || 0, m.eyeX,  0.24 * t);
    b.eyeY    = lerp(b.eyeY || 0, m.eyeY,  0.24 * t);
    if(state.tracking.baselineFrames >= 18){
      state.tracking.baselineReady = true;
      calibText.textContent = 'Auto';
      log('Baseline ocular capturada.');
    }
    return;
  }

  const stable =
    Math.abs(m.centerX - b.centerX) < 0.06 &&
    Math.abs(m.centerY - b.centerY) < 0.06 &&
    Math.abs(m.yaw - b.yaw) < 0.20 &&
    Math.abs(m.eyeX - (b.eyeX || 0)) < 0.32;

  if(stable && state.blink.phase !== 'closed'){
    b.centerX = lerp(b.centerX, m.centerX, 0.010);
    b.centerY = lerp(b.centerY, m.centerY, 0.008);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.011);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.010);
    b.size    = lerp(b.size,    m.size,    0.006);
    if(m.irisAvailable){
      b.eyeX = lerp(b.eyeX || 0, m.eyeX, 0.016);
      b.eyeY = lerp(b.eyeY || 0, m.eyeY, 0.016);
    }
  }
}

function mapEyeTracking(landmarks){
  const m = computeEyeGazeMetrics(landmarks);
  if(!m) return;

  updateEyeTrackingBaseline(m);

  const sample = {
    x:m.centerX,
    y:m.centerY,
    yaw:m.yaw,
    pitch:m.pitch,
    size:m.size,
    eyeX:m.eyeX,
    eyeY:m.eyeY,
    ocularConfidence:m.ocularConfidence
  };
  pushTrackingHistory(sample);

  const hx = avgHistory('x');
  const hy = avgHistory('y');
  const hyaw = avgHistory('yaw');
  const hpitch = avgHistory('pitch');
  const hsize = avgHistory('size');
  const heyeX = avgHistory('eyeX');
  const heyeY = avgHistory('eyeY');
  const hEyeConf = avgHistory('ocularConfidence');

  const dx = hx - state.tracking.baseline.centerX;
  const dy = hy - state.tracking.baseline.centerY;
  const dyaw = hyaw - state.tracking.baseline.yaw;
  const dpitch = hpitch - state.tracking.baseline.pitch;
  const deyeX = heyeX - (state.tracking.baseline.eyeX || 0);
  const deyeY = heyeY - (state.tracking.baseline.eyeY || 0);

  const dirSign = state.tracking.invertX ? -1 : 1;
  const irisWeight = clamp((m.irisAvailable ? 0.34 : 0.08) + hEyeConf * 0.72, 0.18, 0.96);

  const eyeTermX = deyeX * (0.74 + irisWeight * 0.44);
  const headTermX = dyaw * (1.18 - irisWeight * 0.24);
  const centerTermX = dx * 0.035;
  let combinedX = dirSign * (eyeTermX + headTermX + centerTermX);

  const eyeTermY = deyeY * (0.18 + irisWeight * 0.28);
  let combinedY = eyeTermY + dpitch * 0.40 + dy * 0.58;

  combinedX = remapDeadzone(combinedX, Math.max(0.006, state.tracking.deadzoneX * 0.66));
  combinedY = remapDeadzone(combinedY, Math.max(0.008, state.tracking.deadzoneY * 0.82));

  const targetX = clamp(0.5 + combinedX * state.calib.gainX + state.calib.xOff, 0.02, 0.98);
  const targetY = clamp(0.5 + combinedY * 0.88 + state.calib.yOff, 0.02, 0.98);

  gaze.targetX = smoothTowards(gaze.targetX, targetX, 0.075, 0.155);
  gaze.targetY = smoothTowards(gaze.targetY, targetY, 0.080, 0.160);

  const sizeRatio = hsize / Math.max(0.001, state.tracking.baseline.size);
  state.tracking.sizeVelocity = lerp(state.tracking.sizeVelocity, sizeRatio - state.tracking.lastSizeRatio, 0.35);
  state.tracking.lastSizeRatio = lerp(state.tracking.lastSizeRatio, sizeRatio, 0.22);

  const coherence = 1 - clamp(Math.abs(deyeX - dyaw * 0.25) * 0.42 + m.eyeAsym * 0.12, 0, 0.48);
  const q = 0.34 + irisWeight * 0.30 + coherence * 0.18 + state.tracking.videoBrightnessScore * 0.08 + state.tracking.videoSharpnessScore * 0.10;
  gaze.quality = clamp(q, 0.44, 0.99);
}

function registerBlink(now){
  if((now - state.blink.lastEventTs) < state.blink.debounceMs){
    state.blink.debugLast = 'debounced';
    return;
  }

  if(state.blink.pendingSingleTs && (now - state.blink.pendingSingleTs) <= state.blink.doubleWindowMs){
    state.blink.pendingSingleTs = 0;
    state.blink.lastBlinkTs = now;
    state.blink.lastEventTs = now;
    state.blink.debugLast = 'double';
    setBlink('2x');
    onDoubleBlink();
    return;
  }

  state.blink.pendingSingleTs = now;
  state.blink.lastBlinkTs = now;
  state.blink.lastEventTs = now;
  state.blink.debugLast = 'single_wait';
  setBlink('1?');
}

function eyeContourOpenness(lm, verts, outerIdx, innerIdx){
  const horizontal = dist2(lm[outerIdx].x, lm[outerIdx].y, lm[innerIdx].x, lm[innerIdx].y);
  const verticals = verts.map(pair => dist2(lm[pair[0]].x, lm[pair[0]].y, lm[pair[1]].x, lm[pair[1]].y));
  const avgVert = verticals.reduce((s,v)=>s+v,0) / Math.max(1, verticals.length);
  return avgVert / Math.max(horizontal, 1e-6);
}

function processBlink(landmarks){
  const leftOpen  = eyeContourOpenness(landmarks, [[159,145],[160,144],[158,153]], 33, 133);
  const rightOpen = eyeContourOpenness(landmarks, [[386,374],[385,380],[387,373]], 362, 263);
  const now = Date.now();

  state.blink.lastLeft = lerp(state.blink.lastLeft, leftOpen, 0.36);
  state.blink.lastRight = lerp(state.blink.lastRight, rightOpen, 0.36);

  const rawAvg = (state.blink.lastLeft + state.blink.lastRight) * 0.5;
  const asym = Math.abs(state.blink.lastLeft - state.blink.lastRight);
  const rawOpen = rawAvg * 0.42 + Math.min(state.blink.lastLeft, state.blink.lastRight) * 0.58;

  state.blink.emaFast = lerp(state.blink.emaFast, rawOpen, 0.44);
  state.blink.ema = lerp(state.blink.ema, rawOpen, 0.18);

  if(state.blink.phase === 'open'){
    state.blink.warmupFrames += 1;
    const stableInput = Math.abs(state.blink.emaFast - state.blink.ema) < 0.022 && asym < 0.12;
    if(stableInput) state.blink.stableFrames += 1;
    else state.blink.stableFrames = Math.max(0, state.blink.stableFrames - 1);

    if(!state.blink.baselineReady){
      state.blink.baseline = lerp(state.blink.baseline, clamp(state.blink.ema, state.blink.minBaseline, state.blink.maxBaseline), 0.08);
      if(state.blink.warmupFrames > 10 && state.blink.stableFrames >= 6){
        state.blink.baselineReady = true;
      }
    } else if(state.blink.ema > state.blink.baseline * 0.82 && asym < 0.13){
      state.blink.baseline = lerp(
        state.blink.baseline,
        clamp(state.blink.ema, state.blink.minBaseline, state.blink.maxBaseline),
        0.016
      );
    }
  }

  const baseline = clamp(state.blink.baseline, state.blink.minBaseline, state.blink.maxBaseline);
  const ratio = clamp(state.blink.emaFast / Math.max(0.001, baseline), 0, 1.5);
  const closeThresh = clamp(state.blink.closeRatio, 0.58, 0.82);
  const openThresh  = clamp(state.blink.openRatio, 0.76, 0.94);
  state.blink.ratio = ratio;
  state.blink.threshClose = closeThresh;
  state.blink.threshOpen = openThresh;

  const eyeScore = (
    clamp((baseline - 0.14) / 0.16, 0, 1) * 0.34 +
    clamp((0.11 - asym) / 0.11, 0, 1) * 0.20 +
    clamp((0.03 - Math.abs(state.blink.emaFast - state.blink.ema)) / 0.03, 0, 1) * 0.20 +
    (state.blink.baselineReady ? 0.26 : 0.05)
  );
  state.blink.eyeConfidence = clamp(eyeScore, 0, 1);

  if(ratio < closeThresh){
    state.blink.closeFrames += 1;
    state.blink.openFrames = 0;
  } else if(ratio > openThresh){
    state.blink.openFrames += 1;
    if(state.blink.phase === 'open') state.blink.closeFrames = 0;
  }

  if(state.tracking.modeKind === 'weak'){
    state.blink.debugLast = 'blink_disabled_weak';
    setBlink('Auto off');
    state.blink.phase = 'open';
    state.blink.closeFrames = 0;
    state.blink.openFrames = 0;
    state.blink.pendingSingleTs = 0;
    return;
  }

  const minEyeScore = state.tracking.modeKind === 'hybrid' ? 0.44 : 0.54;
  if(!state.blink.baselineReady || state.blink.eyeConfidence < minEyeScore){
    setBlink(state.tracking.modeKind === 'hybrid' ? 'Opcional' : 'Calibrando');
    return;
  }

  if(state.blink.phase === 'open' && state.blink.closeFrames >= state.blink.minCloseFrames){
    state.blink.phase = 'closed';
    state.blink.closeTs = now;
    state.blink.debugLast = 'closed';
    setBlink('Fechado');
    gazeCursor.style.borderColor = 'rgba(243,156,18,.9)';
  } else if(state.blink.phase === 'closed' && state.blink.openFrames >= state.blink.minOpenFrames){
    const dur = now - state.blink.closeTs;
    state.blink.phase = 'open';
    state.blink.closeFrames = 0;
    state.blink.openFrames = 0;
    state.blink.lastCycleMs = dur;
    state.blink.debugLast = 'open';
    gazeCursor.style.borderColor = 'rgba(255,255,255,.92)';
    if(dur >= state.blink.minMs && dur <= state.blink.maxMs){
      registerBlink(now);
    } else {
      state.blink.debugLast = 'ignored_'+dur;
    }
  }
}

function updateVideoQuality(){
  if(video.readyState < 2) return;
  analysisCtx.drawImage(video, 0, 0, analysisCanvas.width, analysisCanvas.height);
  const data = analysisCtx.getImageData(0,0,analysisCanvas.width,analysisCanvas.height).data;
  let lumSum = 0;
  let sharp = 0;
  let count = 0;
  const w = analysisCanvas.width;
  const h = analysisCanvas.height;
  for(let y=0; y<h-2; y+=2){
    for(let x=0; x<w-2; x+=2){
      const i = (y*w + x) * 4;
      const l = data[i]*0.299 + data[i+1]*0.587 + data[i+2]*0.114;
      const ir = i + 8;
      const ib = i + w*4*2;
      const lr = data[ir]*0.299 + data[ir+1]*0.587 + data[ir+2]*0.114;
      const lb = data[ib]*0.299 + data[ib+1]*0.587 + data[ib+2]*0.114;
      lumSum += l;
      sharp += Math.abs(l-lr) + Math.abs(l-lb);
      count += 1;
    }
  }
  const avgLum = lumSum / Math.max(1, count);
  const avgSharp = sharp / Math.max(1, count);
  state.tracking.videoBrightnessScore = lerp(state.tracking.videoBrightnessScore, clamp((avgLum - 42) / 92, 0, 1), 0.25);
  state.tracking.videoSharpnessScore = lerp(state.tracking.videoSharpnessScore, clamp((avgSharp - 10) / 30, 0, 1), 0.25);
}

function updateTrackingMode(){
  const eyeScore = state.blink.eyeConfidence || 0;
  const stability = clamp(1 - (Math.abs(gaze.targetX - gaze.x) + Math.abs(gaze.targetY - gaze.y)) * 1.8, 0, 1);
  state.tracking.stabilityScore = lerp(state.tracking.stabilityScore, stability, 0.22);
  const total = 0.36 + 0.22*state.tracking.videoBrightnessScore + 0.20*state.tracking.videoSharpnessScore + 0.16*state.tracking.stabilityScore + 0.06*eyeScore;
  state.tracking.totalQuality = lerp(state.tracking.totalQuality, clamp(total, 0, 1), 0.24);

  let next = 'weak';
  if(state.tracking.totalQuality >= 0.80 && eyeScore >= 0.56 && state.tracking.videoSharpnessScore >= 0.26){
    next = 'full';
  } else if(state.tracking.totalQuality >= 0.58){
    next = 'hybrid';
  }

  if(next !== state.tracking.modeKind){
    setTrackingMode(next);
    state.tracking.lastModeTs = Date.now();
    if(next === 'weak'){
      flashBlinkIndicator('📷 câmera fraca → zoom por distância do rosto');
      log('Modo câmera fraca ativado. Zoom segue por distância do rosto + botões.');
    } else if(next === 'hybrid'){
      flashBlinkIndicator('🧭 modo híbrido → cabeça + permanência + distância');
      log('Modo híbrido ativado: cabeça principal, foco por permanência e zoom principal por distância do rosto.');
    } else {
      flashBlinkIndicator('🔎 zoom híbrido estável ativo');
      log('Modo completo ativo com zoom principal por distância do rosto e blink como reforço.');
    }
  }

  const label = Math.round(state.tracking.totalQuality * 100)+'% · luz '+Math.round(state.tracking.videoBrightnessScore*100)+' · nitidez '+Math.round(state.tracking.videoSharpnessScore*100)+' · olho '+Math.round(eyeScore*100);
  qualityText.textContent = label;
  setMode('Webcam · '+modeConfig[state.tracking.modeKind].label);
}

function processDistanceZoom(now){
  const ratio = state.tracking.lastSizeRatio || 1;
  const target = blinkTarget();

  const inThresh  = state.tracking.modeKind === 'weak' ? 1.08 : (state.tracking.modeKind === 'hybrid' ? 1.11 : 1.14);
  const outThresh = state.tracking.modeKind === 'weak' ? 0.94 : (state.tracking.modeKind === 'hybrid' ? 0.91 : 0.88);
  const inCooldown = state.tracking.modeKind === 'weak' ? 620 : 760;
  const outCooldown = 620;

  const nearNeutral = ratio > 0.98 && ratio < 1.02;
  state.tracking.distanceNeutralFrames = nearNeutral
    ? Math.min(12, state.tracking.distanceNeutralFrames + 1)
    : Math.max(0, state.tracking.distanceNeutralFrames - 1);

  const allowAction = (now - state.tracking.lastDistanceZoomTs) > Math.min(inCooldown, outCooldown);

  if(ratio > inThresh && allowAction && target){
    zoomInToArtwork(target, 'distancia_rosto', state.tracking.modeKind === 'full' ? 0.16 : 0.18);
    flashBlinkIndicator('↗ rosto aproximou → zoom in');
    state.tracking.lastDistanceZoomTs = now;
    state.tracking.distanceNeutralFrames = 0;
    return;
  }

  if(ratio < outThresh && allowAction && state.zoom.focusTarget > 0.02){
    zoomOutStep('distancia_rosto');
    flashBlinkIndicator('↘ rosto afastou → zoom out');
    state.tracking.lastDistanceZoomTs = now;
    state.tracking.distanceNeutralFrames = 0;
    return;
  }

  if(nearNeutral && state.tracking.distanceNeutralFrames >= 6 && state.tracking.baselineReady && state.zoom.focusTarget < 0.08 && state.blink.phase !== 'closed'){
    state.tracking.baseline.size = lerp(state.tracking.baseline.size, avgHistory('size') || state.tracking.baseline.size, 0.015);
  }
}

function drawMeshOverlay(landmarks){
  syncVideoOverlaySize();
  const w = meshOverlay.clientWidth;
  const h = meshOverlay.clientHeight;
  meshCtx.clearRect(0,0,w,h);
  if(!landmarks || !w || !h) return;
  const toPt = idx => ({x:(1-landmarks[idx].x) * w, y:landmarks[idx].y * h});
  const strokeSeq = (indices, color, width) => {
    meshCtx.beginPath();
    indices.forEach((idx, n)=>{
      if(!landmarks[idx]) return;
      const p = toPt(idx);
      if(n===0) meshCtx.moveTo(p.x,p.y);
      else meshCtx.lineTo(p.x,p.y);
    });
    meshCtx.strokeStyle = color;
    meshCtx.lineWidth = width;
    meshCtx.stroke();
  };
  strokeSeq(FACE_OVAL, 'rgba(93,173,226,.52)', 1.4);
  strokeSeq(LEFT_BROW, 'rgba(255,255,255,.44)', 1.2);
  strokeSeq(RIGHT_BROW, 'rgba(255,255,255,.44)', 1.2);
  strokeSeq(LEFT_EYE, 'rgba(46,204,113,.75)', 1.6);
  strokeSeq(RIGHT_EYE, 'rgba(46,204,113,.75)', 1.6);
  strokeSeq(NOSE_LINE, 'rgba(255,255,255,.32)', 1.1);
  strokeSeq(MOUTH_OUTER, 'rgba(165,105,189,.30)', 1.0);
  if(landmarks[468]) strokeSeq(LEFT_IRIS, 'rgba(240,192,64,.65)', 1.1);
  if(landmarks[473]) strokeSeq(RIGHT_IRIS, 'rgba(240,192,64,.65)', 1.1);
}

function clearMeshOverlay(){
  syncVideoOverlaySize();
  meshCtx.clearRect(0,0,meshOverlay.clientWidth, meshOverlay.clientHeight);
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

  const mapX = x => state.tracking.mirrorInput ? (1 - x) : x;
  const noseX = mapX(nose.x);
  const leftEyeX = mapX(leftEyeOuter.x);
  const rightEyeX = mapX(rightEyeOuter.x);
  const leftCheekX = mapX(leftCheek.x);
  const rightCheekX = mapX(rightCheek.x);

  const eyeMidX = (leftEyeX + rightEyeX) * 0.5;
  const mouthMidY = (mouthTop.y + mouthBot.y) * 0.5;
  const faceWidth = Math.max(0.001, Math.abs(rightCheekX - leftCheekX));
  const faceHeight = Math.max(0.001, chin.y - forehead.y);
  const faceMidY = (forehead.y + chin.y) * 0.5;

  const centerX = clamp(noseX * 0.64 + eyeMidX * 0.36, 0, 1);
  const centerY = clamp(nose.y * 0.68 + mouthMidY * 0.32, 0, 1);
  const yawRaw = (noseX - eyeMidX) / Math.max(0.001, Math.abs(rightEyeX - leftEyeX));
  const pitchRaw = (nose.y - faceMidY) / faceHeight;
  const sizeRaw = faceWidth;

  return {
    centerX,
    centerY,
    yaw:yawRaw,
    pitch:pitchRaw,
    size:sizeRaw,
    faceHeight
  };
}

function updateTrackingBaseline(m){
  const b = state.tracking.baseline;
  if(!state.tracking.baselineReady){
    state.tracking.baselineFrames += 1;
    const t = Math.min(1, state.tracking.baselineFrames / 20);
    b.centerX = lerp(b.centerX, m.centerX, 0.18 * t);
    b.centerY = lerp(b.centerY, m.centerY, 0.18 * t);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.18 * t);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.18 * t);
    b.size    = lerp(b.size,    m.size,    0.18 * t);
    if(state.tracking.baselineFrames >= 20){
      state.tracking.baselineReady = true;
      calibText.textContent = 'Auto';
      log('Baseline facial capturada.');
    }
    return;
  }

  const stableCenter = Math.abs(m.centerX - b.centerX) < 0.05 && Math.abs(m.centerY - b.centerY) < 0.05;
  if(stableCenter && state.blink.phase !== 'closed'){
    b.centerX = lerp(b.centerX, m.centerX, 0.010);
    b.centerY = lerp(b.centerY, m.centerY, 0.008);
    b.yaw     = lerp(b.yaw,     m.yaw,     0.010);
    b.pitch   = lerp(b.pitch,   m.pitch,   0.010);
    b.size    = lerp(b.size,    m.size,    0.006);
  }
}

function mapFaceTracking(landmarks){
  const m = faceMetrics(landmarks);
  if(!m) return;

  updateTrackingBaseline(m);

  const sample = {
    x:m.centerX,
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

  const dx = hx - state.tracking.baseline.centerX;
  const dy = hy - state.tracking.baseline.centerY;
  const dyaw = hyaw - state.tracking.baseline.yaw;
  const dpitch = hpitch - state.tracking.baseline.pitch;

  const dirSign = state.tracking.invertX ? -1 : 1;

  const horizontalYaw = dyaw * state.tracking.yawGainX;
  const horizontalCenter = dx * state.tracking.centerGainX;
  const horizontalMix = horizontalYaw * 0.94 + horizontalCenter * 0.06;
  let combinedX = dirSign * horizontalMix;
  let combinedY = dy * state.tracking.centerGainY + dpitch * state.tracking.pitchGainY;

  combinedX = remapDeadzone(combinedX, state.tracking.deadzoneX);
  combinedY = remapDeadzone(combinedY, state.tracking.deadzoneY);

  const targetX = clamp(0.5 + combinedX * state.calib.gainX + state.calib.xOff, 0.02, 0.98);
  const targetY = clamp(0.5 + combinedY * 0.86 + state.calib.yOff, 0.02, 0.98);

  gaze.targetX = smoothTowards(gaze.targetX, targetX, 0.065, 0.13);
  gaze.targetY = smoothTowards(gaze.targetY, targetY, 0.07, 0.14);

  const sizeRatio = hsize / Math.max(0.001, state.tracking.baseline.size);
  state.tracking.sizeVelocity = lerp(state.tracking.sizeVelocity, sizeRatio - state.tracking.lastSizeRatio, 0.35);
  state.tracking.lastSizeRatio = lerp(state.tracking.lastSizeRatio, sizeRatio, 0.22);

  const sym = 1 - Math.abs(dx * 0.18) - Math.abs(dyaw * 0.22) - Math.abs(hsize - state.tracking.baseline.size) * 0.22;
  gaze.quality = clamp(sym, 0.58, 0.99);
}

// ─── DRAW ROOM ───
function drawArtwork(art,highlight){
  const poly=polyPts(art);
  if(!poly||poly.some(p=>!p)) return null;
  const [p0,p1,p2,p3]=poly;
  const par = parallaxOffsetForArt(art);

  const shadow = poly.map(p=>({x:p.x + par.x*0.18, y:p.y + 10 + par.y*0.18, depth:p.depth, scale:p.scale}));
  drawPoly(shadow,'rgba(0,0,0,.18)', null, 0);

  drawPoly(poly,'rgba(70,55,40,.98)', highlight?'rgba(93,173,226,.92)':'rgba(255,255,255,.10)', highlight?2.6:1.05);

  const cx=(p0.x+p1.x+p2.x+p3.x)/4;
  const cy=(p0.y+p1.y+p2.y+p3.y)/4;
  const inner=poly.map(p=>({x:lerp(p.x,cx,.08),y:lerp(p.y,cy,.08)}));
  const floatCfg = state.parallax.artFloaters.find(f=>f.artId===art.id);
  const drift = floatCfg ? Math.sin(performance.now()*0.0017 + floatCfg.phase) * floatCfg.amp : 0;
  const artShiftX = par.x * 0.18;
  const artShiftY = par.y * 0.14 + drift * 120;
  const innerShifted = inner.map(p=>({x:p.x + artShiftX, y:p.y + artShiftY}));
  const g=ctx.createLinearGradient(innerShifted[0].x,innerShifted[0].y,innerShifted[2].x,innerShifted[2].y);
  g.addColorStop(0,art.color);
  g.addColorStop(0.55,'rgba(255,255,255,.12)');
  g.addColorStop(1,'#0a1525');
  drawPoly(innerShifted,g, highlight?'rgba(255,255,255,.26)':'rgba(255,255,255,.08)', 1.15);

  const glare = ctx.createLinearGradient(cx - 80 + par.x*0.3, cy - 40 + par.y*0.25, cx + 110 + par.x*0.3, cy + 55 + par.y*0.25);
  glare.addColorStop(0,'rgba(255,255,255,0)');
  glare.addColorStop(0.35,'rgba(255,255,255,'+(highlight?0.18:0.10)+')');
  glare.addColorStop(0.65,'rgba(255,255,255,0.03)');
  glare.addColorStop(1,'rgba(255,255,255,0)');
  drawPoly(inner, glare, null, 0);

  const depthStrip = [
    {x:lerp(p0.x,cx,0.10), y:lerp(p0.y,cy,0.10)},
    {x:lerp(p1.x,cx,0.10), y:lerp(p1.y,cy,0.10)},
    {x:lerp(p1.x,cx,0.24) + par.x*0.08, y:lerp(p1.y,cy,0.24) + par.y*0.08},
    {x:lerp(p0.x,cx,0.24) + par.x*0.08, y:lerp(p0.y,cy,0.24) + par.y*0.08}
  ];
  drawPoly(depthStrip, 'rgba(255,255,255,0.05)', null, 0);

  ctx.fillStyle='rgba(255,255,255,.93)';
  ctx.font='bold 13px "Space Grotesk",sans-serif';
  ctx.textAlign='center';
  ctx.fillText(art.title,cx + artShiftX*0.45,cy-4 + artShiftY*0.45);
  ctx.fillStyle='rgba(200,215,255,.75)';
  ctx.font='11.5px "Space Grotesk",sans-serif';
  ctx.fillText(art.artist,cx + artShiftX*0.45,cy+13 + artShiftY*0.45);
  return {poly, center:{x:cx, y:cy}};
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
  drawDepthPanels();

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
    const drawn = drawArtwork(art, hl);
    if(drawn) projectedArtworks.push({art, poly:drawn.poly, center:drawn.center});
  });
  updateFocusInfoCard();
  drawParallaxForeground(r, gx, gy);

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
  let hit=projectedArtworks.find(e=>ptInPoly(gPx,e.poly));

  if(!hit && projectedArtworks.length){
    let best=null;
    let bestD=Infinity;
    projectedArtworks.forEach(entry=>{
      const cx = entry.center?.x ?? ((entry.poly[0].x + entry.poly[1].x + entry.poly[2].x + entry.poly[3].x)/4);
      const cy = entry.center?.y ?? ((entry.poly[0].y + entry.poly[1].y + entry.poly[2].y + entry.poly[3].y)/4);
      const d = Math.hypot(cx - gPx.x, cy - gPx.y);
      if(d < bestD){
        bestD = d;
        best = entry;
      }
    });
    if(best && bestD < Math.min(r.width, r.height) * 0.20){
      hit = best;
    }
  }

  if(!hit){
    if(state.hoveredId){
      state.hoveredId=null;
      state.hoverStartTs=now;
      state.zoom.dwellLevel = 0;
      updateSelPanel(state.selectedId ? artById(state.selectedId) : null);
    }
    dwellFill.style.width='0%';
    hoverText.textContent='—';
    gazeCursor.style.width='26px'; gazeCursor.style.height='26px';
    return;
  }

  hoverText.textContent=hit.art.title;
  updateSelPanel(hit.art);
  if(state.hoveredId!==hit.art.id){
    state.hoveredId=hit.art.id;
    state.hoverStartTs=now;
    state.zoom.dwellLevel = 0;
    gazeCursor.style.width='34px'; gazeCursor.style.height='34px';
  }

  const elapsed=now-state.hoverStartTs;
  const progress=clamp(elapsed/state.dwellMs,0,1);
  dwellFill.style.width=(progress*100).toFixed(1)+'%';
  gazeCursor.style.borderColor=progress>.7?'rgba(46,204,113,.95)':'rgba(93,173,226,.95)';

  if(elapsed >= 800 && state.zoom.dwellLevel < 1){
    state.zoom.dwellLevel = 1;
    selectArtwork(hit.art,'dwell');
    flashBlinkIndicator('🎯 foco travado em "'+hit.art.title+'"');
  }
  if(elapsed >= 1400 && state.zoom.dwellLevel < 2){
    state.zoom.dwellLevel = 2;
    zoomInToArtwork(hit.art,'dwell_progress_1',0.12);
    flashBlinkIndicator('🔎 permanência → aproxima');
  }
  if(elapsed >= 2100 && state.zoom.dwellLevel < 3){
    state.zoom.dwellLevel = 3;
    zoomInToArtwork(hit.art,'dwell_progress_2',0.12);
    flashBlinkIndicator('🔎 permanência longa → aproxima mais');
    state.hoverStartTs = now - 1500;
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
  resetBlinkState();
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
        clearMeshOverlay();
        setStatus(false,'Rosto não encontrado');
        gaze.quality=.4;
        setBlink('Sem rosto');
        return;
      }
      const lm = results.multiFaceLandmarks[0];
      drawMeshOverlay(lm);
      mapEyeTracking(lm);
      processBlink(lm);
      if((state.tracking.frameCounter++ % 4) === 0) updateVideoQuality();
      updateTrackingMode();
      processDistanceZoom(Date.now());
      state.usingMouse=false;
      setStatus(true,'Tracking ocular ativo');
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
    permNote.textContent='Tracking ativo. O olhar ocular agora mira a obra com base no contorno dos olhos e na íris quando disponível; a cabeça segue como fallback de estabilidade. 1 piscada afasta e 2 piscadas aproximam.';
    setTrackingMode('full');
    log('Tracking ocular iniciado com baseline dinâmico dos olhos, blink 1x=afasta / 2x=aproxima e fallback pela cabeça + distância do rosto.');

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
  resetBlinkState();
  resetTrackingState();
  if(state.rafMedia){ cancelAnimationFrame(state.rafMedia); state.rafMedia=null; }
  if(state.stream){ state.stream.getTracks().forEach(t=>t.stop()); state.stream=null; }
  video.srcObject=null;
  clearMeshOverlay();
  state.usingMouse=true;
  setMode('Parado'); setStatus(false,'Tracking desligado');
  permNote.textContent='Tracking desligado. Sala continua ativa.';
  dwellFill.style.width='0%';
  resetZoom();
  log('Tracking parado.');
}

function calibrate(){
  if(state.usingMouse){
    calibText.textContent='Modo mouse';
    log('Calibração não necessária no modo mouse.');
    return;
  }
  state.calib.xOff = clamp((0.5 - gaze.targetX) * 0.62, -0.20, 0.20);
  state.calib.yOff = clamp((0.5 - gaze.targetY) * 0.56, -0.18, 0.18);
  state.calib.gainX = 0.98;
  state.calib.gainY = 0.96;
  state.tracking.history = [];
  state.tracking.baselineReady = false;
  state.tracking.baselineFrames = 0;
  state.tracking.lastDistanceZoomTs = 0;
  state.tracking.distanceNeutralFrames = 0;
  state.tracking.baseline = {
    centerX:0.5,
    centerY:0.5,
    yaw:0,
    pitch:0,
    size:0.22,
    eyeX:0,
    eyeY:0
  };
  state.tracking.ocularConfidence = 0.62;
  state.tracking.irisAvailable = false;
  state.blink.baselineReady = false;
  state.blink.pendingSingleTs = 0;
  state.zoom.dwellLevel = 0;
  calibText.textContent='Ocular';
  permNote.textContent='Calibração ocular aplicada. Olhe reto por alguns instantes para recapturar o centro; se a lateral ainda ficar invertida, use “Inverter X”.';
  log('Calibração ocular centralizada. xOff='+state.calib.xOff.toFixed(3)+' yOff='+state.calib.yOff.toFixed(3)+' invertX='+(state.tracking.invertX ? 'on' : 'off'));
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

function bindPressAction(el, handler){
  let lastTs = 0;
  const wrapped = (ev)=>{
    if(ev){
      ev.preventDefault();
      ev.stopPropagation();
    }
    const now = Date.now();
    if(now - lastTs < 180) return;
    lastTs = now;
    handler();
  };
  el.addEventListener('click', wrapped);
  el.addEventListener('pointerdown', wrapped);
}

bindPressAction(zoomInBtn, ()=> manualZoomIn('manual_zoom_in'));
bindPressAction(zoomOutBtn, ()=> manualZoomOut('manual_zoom_out'));

// ─── BUTTON WIRING ───
document.getElementById('startBtn').addEventListener('click', startTracking);
document.getElementById('stopBtn').addEventListener('click', stopTracking);
document.getElementById('calibrateBtn').addEventListener('click', calibrate);
document.getElementById('resetHeatBtn').addEventListener('click', clearHeatmap);
document.getElementById('exportPdfBtn').addEventListener('click', exportPdf);
invertXBtn.addEventListener('click', ()=>{
  state.tracking.invertX = !state.tracking.invertX;
  permNote.textContent = state.tracking.invertX ? 'Inverter X ligado: o yaw foi invertido manualmente para webcams com direção oposta.' : 'Inverter X desligado: o yaw segue o mesmo espelhamento visível da câmera.';
  resetTrackingState();
  state.tracking.history = [];
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
  flushPendingSingleBlink(Date.now());
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
setTrackingMode('full');
setMode('Eye tracking pronto');
setBlink('Pronto');
setStatus(true,'Cena carregada');
window.addEventListener('resize',resizeCanvases);
video.addEventListener('loadedmetadata', syncVideoOverlaySize);
requestAnimationFrame(tick);
log('Sala pronta. Clique em "Iniciar tracking" para usar o novo rastreamento ocular com foco por olhar, info da obra, 1 piscada afasta, 2 piscadas aproximam e fallback pela cabeça.');

})();
</script>
</div>
"""

components.html(HTML_APP, height=1300, scrolling=True)
