
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Simulacro Streamlit – Tracking Ocular", layout="wide")

st.title("Simulacro Streamlit – tracking ocular como controle principal")
st.caption("Versão Streamlit sem tkinter: cursor controlado pelo olho, foco por permanência do olhar, 1 piscada afasta e 2 piscadas aproximam.")

HTML_APP = r"""
<div id="ocular-gallery-root">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
  :root{
    --bg:#060d1a;
    --bg2:#08101f;
    --panel:rgba(10,16,30,.84);
    --soft:rgba(255,255,255,.05);
    --line:rgba(255,255,255,.08);
    --text:#e8f0ff;
    --muted:#89a0c7;
    --cyan:#5dade2;
    --violet:#a569bd;
    --gold:#f0c040;
    --ok:#2ecc71;
    --warn:#f39c12;
    --danger:#e74c3c;
    font-family:'Space Grotesk',system-ui,sans-serif;
  }
  *{box-sizing:border-box}
  body{background:transparent;margin:0}
  #ocular-gallery-root{
    color:var(--text);
    min-height:1380px;
    border-radius:24px;
    padding:16px;
    overflow:hidden;
    background:
      radial-gradient(ellipse 70% 40% at 20% 0%, rgba(93,173,226,.08) 0%, transparent 55%),
      radial-gradient(ellipse 60% 40% at 80% 100%, rgba(165,105,189,.09) 0%, transparent 55%),
      linear-gradient(180deg, #050b16 0%, #07101d 100%);
    border:1px solid rgba(255,255,255,.05);
  }
  .topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;flex-wrap:wrap;margin-bottom:14px}
  .headline h2{margin:0;font-size:25px;font-weight:800;letter-spacing:-.4px}
  .headline p{margin:6px 0 0;color:var(--muted);font-size:13px;line-height:1.5;max-width:920px}
  .controls{display:flex;gap:8px;flex-wrap:wrap}
  .btn{
    appearance:none;border:none;cursor:pointer;
    padding:10px 14px;border-radius:12px;
    font-size:13px;font-weight:800;color:var(--text);
    background:rgba(255,255,255,.06);
    border:1px solid rgba(255,255,255,.10);
    transition:.18s ease;
  }
  .btn:hover{transform:translateY(-1px);background:rgba(93,173,226,.12);border-color:rgba(93,173,226,.35)}
  .btn.primary{background:rgba(93,173,226,.18);border-color:rgba(93,173,226,.35)}
  .btn.warn{background:rgba(243,156,18,.14);border-color:rgba(243,156,18,.35)}
  .btn.subtle{background:rgba(165,105,189,.14);border-color:rgba(165,105,189,.35)}
  .btn.danger{background:rgba(231,76,60,.14);border-color:rgba(231,76,60,.35)}
  .layout{display:grid;grid-template-columns:minmax(0,1.72fr) 330px;gap:14px;min-height:1120px}
  .scene-panel{
    position:relative;min-height:960px;overflow:hidden;border-radius:22px;
    border:1px solid var(--line);
    background:rgba(255,255,255,.02);
    box-shadow:0 26px 70px rgba(0,0,0,.36);
  }
  #scene-shell{position:absolute;inset:0}
  #room,#heatmap{position:absolute;inset:0;width:100%;height:100%;display:block}
  #heatmap{display:none}
  #gazeCursor{
    position:absolute;left:50%;top:50%;width:28px;height:28px;transform:translate(-50%,-50%);
    border-radius:50%;border:2px solid rgba(255,255,255,.95);
    box-shadow:0 0 0 6px rgba(93,173,226,.14),0 0 24px rgba(93,173,226,.28);
    pointer-events:none;z-index:7;
  }
  #gazeCursor::after{content:"";position:absolute;inset:5px;border-radius:50%;background:rgba(255,255,255,.82)}
  .chip{
    position:absolute;z-index:8;
    display:flex;align-items:center;gap:8px;
    padding:8px 12px;border-radius:999px;
    background:rgba(6,13,26,.84);border:1px solid rgba(255,255,255,.08);
    font-size:12px;color:var(--muted);backdrop-filter:blur(12px);
  }
  .chip strong{color:var(--text)}
  #statusChip{left:14px;top:14px}
  #controlChip{left:174px;top:14px}
  #blinkChip{left:336px;top:14px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--danger);box-shadow:0 0 16px rgba(231,76,60,.4)}
  .dot.on{background:var(--ok);box-shadow:0 0 16px rgba(46,204,113,.4)}
  .meter{
    position:absolute;top:14px;right:14px;z-index:8;width:210px;
    padding:10px 12px;border-radius:14px;
    background:rgba(6,13,26,.84);border:1px solid rgba(255,255,255,.08);
  }
  .meter .label{font-family:'JetBrains Mono',monospace;color:var(--muted);font-size:11px;margin-bottom:6px}
  .bar{height:8px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden}
  .bar>div{height:100%;width:0%;background:linear-gradient(90deg,#5dade2 0%,#a569bd 100%);border-radius:999px;transition:width .06s}
  #permissionNote{
    position:absolute;left:14px;bottom:14px;z-index:8;max-width:70%;
    padding:10px 13px;border-radius:12px;background:rgba(6,13,26,.86);
    border:1px solid rgba(255,255,255,.07);color:var(--muted);font-size:12px;line-height:1.45;
  }
  #blinkToast{
    position:absolute;left:50%;bottom:18px;transform:translateX(-50%);z-index:9;
    padding:8px 16px;border-radius:999px;background:rgba(6,13,26,.90);
    border:1px solid rgba(93,173,226,.22);font-family:'JetBrains Mono',monospace;
    font-size:12px;color:var(--muted);opacity:0;transition:opacity .25s;
  }
  #blinkToast.show{opacity:1}
  #artInfoFloat{
    position:absolute;z-index:9;min-width:220px;max-width:290px;pointer-events:none;
    transform:translate(-50%,-122%);
    opacity:0;transition:opacity .15s ease;
    padding:12px 14px;border-radius:14px;
    background:rgba(6,13,26,.92);border:1px solid rgba(93,173,226,.22);
    box-shadow:0 18px 45px rgba(0,0,0,.35);backdrop-filter:blur(14px);
  }
  #artInfoFloat.show{opacity:1}
  #artInfoFloat .ttl{font-size:13px;font-weight:800;margin-bottom:4px}
  #artInfoFloat .sub{font-size:11px;color:var(--cyan);font-weight:700;margin-bottom:4px}
  #artInfoFloat .txt{font-size:11px;color:var(--muted);line-height:1.4}

  .sidebar{display:flex;flex-direction:column;gap:12px}
  .card{
    background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.07);
    border-radius:16px;
    padding:14px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.03);
  }
  .card h3{margin:0 0 10px;font-size:13px;color:var(--muted);letter-spacing:.5px;text-transform:uppercase}
  .videoWrap{position:relative;width:100%;aspect-ratio:16/10;overflow:hidden;border-radius:12px;border:1px solid rgba(255,255,255,.07);background:#030812}
  #video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1);background:#02060d}
  #camOverlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .stat{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:10px}
  .stat .k{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px}
  .stat .v{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
  .small{margin-top:8px;color:var(--muted);font-size:11.5px;line-height:1.45}
  .manualZoom{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
  .metaLine{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:12px;color:var(--muted)}
  .metaLine strong{color:var(--text)}
  .metaLine:last-child{border-bottom:none}
  #selectedTitle{font-size:17px;font-weight:800;line-height:1.2;margin-bottom:4px}
  #selectedArtist{font-size:12px;color:var(--cyan);font-weight:700;margin-bottom:8px}
  #selectedDesc{font-size:12.5px;color:var(--muted);line-height:1.5}
  #artList{display:grid;gap:8px;max-height:260px;overflow:auto}
  #artList::-webkit-scrollbar{width:4px}
  #artList::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:4px}
  .artRow{
    display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:center;
    padding:10px;border-radius:12px;background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.06);cursor:pointer;transition:.15s ease;
  }
  .artRow:hover{background:rgba(93,173,226,.06);border-color:rgba(93,173,226,.28)}
  .artBullet{width:12px;height:12px;border-radius:50%}
  .artRow .title{font-size:13px;font-weight:700;margin-bottom:2px}
  .artRow .sub{font-size:11px;color:var(--muted)}
  .badge{
    font-size:10px;font-weight:700;color:#bfd6f6;background:rgba(93,173,226,.12);
    border:1px solid rgba(93,173,226,.2);padding:4px 8px;border-radius:999px;white-space:nowrap
  }
  .blinkGuide{display:grid;grid-template-columns:1fr 1fr;gap:6px}
  .blinkCard{
    background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);
    border-radius:10px;padding:8px;text-align:center;
  }
  .blinkCard .icon{font-size:18px;margin-bottom:3px}
  .blinkCard .bl{font-size:11px;font-weight:700;margin-bottom:2px}
  .blinkCard .desc{font-size:10.5px;color:var(--muted)}
  #log{
    min-height:110px;max-height:160px;overflow:auto;border-radius:10px;padding:8px;
    background:rgba(2,6,15,.7);border:1px solid rgba(255,255,255,.06);
    color:var(--muted);font-size:11px;line-height:1.4;font-family:'JetBrains Mono',monospace;white-space:pre-wrap;
  }
  @media (max-width:1080px){
    .layout{grid-template-columns:1fr}
    .scene-panel{min-height:700px}
    #ocular-gallery-root{min-height:1520px}
    .topbar{flex-direction:column}
    #controlChip{left:14px;top:52px}
    #blinkChip{left:168px;top:52px}
    .meter{top:92px;right:14px}
  }
</style>

<div class="topbar">
  <div class="headline">
    <h2>Sala 3D – tracking ocular como controle principal</h2>
    <p>Esta versão usa o <strong>olho como controle principal</strong>: o cursor é movido pelo deslocamento da pupila dentro dos olhos, com foco da obra por permanência do olhar. <strong>1 piscada afasta</strong> e <strong>2 piscadas rápidas aproximam</strong>. A navegação lateral não usa pose da cabeça.</p>
  </div>
  <div class="controls">
    <button class="btn primary" id="startBtn">▶ Iniciar</button>
    <button class="btn warn" id="calibrateBtn">⊕ Calibrar olhos</button>
    <button class="btn subtle" id="invertBtn">↔ Inverter X</button>
    <button class="btn" id="zoomInBtn">＋ Aproximar</button>
    <button class="btn" id="zoomOutBtn">－ Afastar</button>
    <button class="btn" id="exportBtn">↓ PDF</button>
    <button class="btn danger" id="stopBtn">■ Parar</button>
  </div>
</div>

<div class="layout">
  <div class="scene-panel">
    <div id="scene-shell">
      <canvas id="room"></canvas>
      <canvas id="heatmap"></canvas>
      <div id="gazeCursor"></div>
      <div class="chip" id="statusChip"><span id="statusDot" class="dot"></span><span id="statusText">Parado</span></div>
      <div class="chip" id="controlChip">Controle: <strong id="controlText">Olho</strong></div>
      <div class="chip" id="blinkChip">Blink: <strong id="blinkText">Aguardando</strong></div>
      <div class="meter"><div class="label">Dwell / seleção</div><div class="bar"><div id="dwellFill"></div></div></div>
      <div id="permissionNote">Clique em iniciar, permita a câmera e depois clique em calibrar olhando reto. Nesta versão, o cursor lateral é guiado pelo olho; o blink controla o zoom.</div>
      <div id="blinkToast">Blink detectado</div>
      <div id="artInfoFloat"><div class="ttl" id="floatTitle"></div><div class="sub" id="floatSub"></div><div class="txt" id="floatTxt"></div></div>
    </div>
  </div>

  <div class="sidebar">
    <div class="card">
      <h3>Câmera</h3>
      <div class="videoWrap">
        <video id="video" autoplay muted playsinline></video>
        <canvas id="camOverlay"></canvas>
      </div>
      <div class="manualZoom">
        <button class="btn" id="zoomInBtn2">＋ Aproximar</button>
        <button class="btn" id="zoomOutBtn2">－ Afastar</button>
      </div>
      <div class="small" id="cameraHelp">O overlay desenha o contorno dos olhos e a pupila estimada. A pose da cabeça não controla a sala; o deslocamento da pupila controla o cursor.</div>
    </div>

    <div class="card">
      <h3>Estado</h3>
      <div class="stats">
        <div class="stat"><div class="k">Qualidade</div><div class="v" id="qualityValue">0.00</div></div>
        <div class="stat"><div class="k">Zoom</div><div class="v" id="zoomValue">1.0x</div></div>
        <div class="stat"><div class="k">Fixações</div><div class="v" id="fixValue">0</div></div>
        <div class="stat"><div class="k">Obras vistas</div><div class="v" id="seenValue">0</div></div>
      </div>
      <div class="small">
        <div class="metaLine"><span>Modo</span><strong id="modeValue">Ocular</strong></div>
        <div class="metaLine"><span>Piscada</span><strong id="blinkDebug">—</strong></div>
        <div class="metaLine"><span>Obra em foco</span><strong id="hoverValue">Nenhuma</strong></div>
        <div class="metaLine"><span>Calibração</span><strong id="calibValue">Pendente</strong></div>
      </div>
    </div>

    <div class="card">
      <h3>Obra selecionada</h3>
      <div id="selectedTitle">Nenhuma obra selecionada</div>
      <div id="selectedArtist">Olhe para uma obra até o dwell completar.</div>
      <div id="selectedDesc">Quando a obra entra em foco, aparece uma ficha genérica em cima dela e aqui na lateral. O zoom também pode ser manual ou por piscada.</div>
    </div>

    <div class="card">
      <h3>Mapa da sala</h3>
      <div id="artList"></div>
    </div>

    <div class="card">
      <h3>Guia de zoom</h3>
      <div class="blinkGuide">
        <div class="blinkCard"><div class="icon">👁</div><div class="bl">1 piscada</div><div class="desc">Afasta</div></div>
        <div class="blinkCard"><div class="icon">👁👁</div><div class="bl">2 piscadas</div><div class="desc">Aproxima</div></div>
      </div>
      <div class="small">O zoom manual continua ativo. O mapa de calor só vai para o PDF exportado.</div>
    </div>

    <div class="card">
      <h3>Log</h3>
      <div id="log"></div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>

<script>
(function(){
'use strict';

const $ = sel => document.querySelector(sel);
const roomCanvas = $('#room');
const heatCanvas = $('#heatmap');
const video = $('#video');
const camOverlay = $('#camOverlay');
const scenePanel = document.querySelector('.scene-panel');
const roomCtx = roomCanvas.getContext('2d');
const heatCtx = heatCanvas.getContext('2d');
const overlayCtx = camOverlay.getContext('2d');
const analysisCanvas = document.createElement('canvas');
analysisCanvas.width = 220;
analysisCanvas.height = 160;
const analysisCtx = analysisCanvas.getContext('2d', {willReadFrequently:true});

const gazeCursor = $('#gazeCursor');
const statusDot = $('#statusDot');
const statusText = $('#statusText');
const blinkText = $('#blinkText');
const controlText = $('#controlText');
const dwellFill = $('#dwellFill');
const permissionNote = $('#permissionNote');
const blinkToast = $('#blinkToast');
const floatBox = $('#artInfoFloat');
const floatTitle = $('#floatTitle');
const floatSub = $('#floatSub');
const floatTxt = $('#floatTxt');
const qualityValue = $('#qualityValue');
const zoomValue = $('#zoomValue');
const fixValue = $('#fixValue');
const seenValue = $('#seenValue');
const modeValue = $('#modeValue');
const blinkDebug = $('#blinkDebug');
const hoverValue = $('#hoverValue');
const calibValue = $('#calibValue');
const selectedTitle = $('#selectedTitle');
const selectedArtist = $('#selectedArtist');
const selectedDesc = $('#selectedDesc');
const artList = $('#artList');
const logBox = $('#log');

const clamp = (v,a,b) => Math.min(b, Math.max(a, v));
const lerp = (a,b,t) => a + (b-a) * t;
const dist = (a,b) => Math.hypot(a.x-b.x, a.y-b.y);
const avg = arr => arr.reduce((s,v)=>s+v,0) / Math.max(1, arr.length);
function log(msg){
  const line = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  logBox.textContent += (logBox.textContent ? '\n' : '') + line;
  logBox.scrollTop = logBox.scrollHeight;
}
window.addEventListener('error', e => log('ERRO: ' + (e.message || '?')));
window.addEventListener('unhandledrejection', e => log('PROMISE: ' + String(e.reason)));

const state = {
  running:false,
  stream:null,
  faceMesh:null,
  camera:null,
  raf:null,
  startedAt:0,

  gaze:{
    x:0.5, y:0.5,
    targetX:0.5, targetY:0.5,
    rawX:0.5, rawY:0.5,
    quality:0,
    invertX:true,
    history:[]
  },

  eye:{
    baselineReady:false,
    calibSamples:[],
    baseX:0,
    baseY:0,
    gainX:2.3,
    gainY:1.85,
    lastPupilLeft:null,
    lastPupilRight:null,
    lastRaw:{x:0, y:0},
    lostFrames:0
  },

  blink:{
    baseline:0.28,
    baselineReady:false,
    warmup:0,
    phase:'open',
    closeFrames:0,
    openFrames:0,
    minCloseFrames:2,
    minOpenFrames:2,
    closeTs:0,
    pendingSingleTs:0,
    lastEventTs:0,
    lastBlinkTs:0,
    closeRatio:0.70,
    openRatio:0.86,
    minMs:35,
    maxMs:420,
    doubleWindowMs:620,
    lastLabel:'—'
  },

  hover:{
    id:null,
    startTs:0,
    dwellMs:850
  },

  selectedId:null,
  fixations:0,
  seen:new Set(),
  heatPoints:[],
  focusedHistory:[],

  zoom:{
    level:0,
    target:0
  },

  trackingQuality:0,
  metrics:{lastQualityTs:0},
};

const LEFT_EYE_RING = [33,160,158,133,153,144];
const RIGHT_EYE_RING = [362,385,387,263,373,380];
const LEFT_EYE_BOX = [33,133,159,145];
const RIGHT_EYE_BOX = [362,263,386,374];
const LEFT_IRIS = [468,469,470,471,472];
const RIGHT_IRIS = [473,474,475,476,477];

const artworks = [
  {id:'a1', title:'Memórias de Superfície', artist:'Lívia Andrade', year:'2024', theme:'Pintura', desc:'Pintura em camadas com relevo cromático, matéria espessa e memória visual acumulada.', color:'#e74c3c', plane:'back', x:-2.85, y:2.1, z:9.85, w:1.70, h:1.15},
  {id:'a2', title:'Campo Sensível', artist:'Diego Marins', year:'2025', theme:'Generativo', desc:'Peça digital com pulsações geométricas, partículas e luz recortando o espaço expositivo.', color:'#27ae60', plane:'back', x:0.0, y:2.15, z:9.85, w:1.75, h:1.20},
  {id:'a3', title:'Eco de Matéria', artist:'Marina Teles', year:'2026', theme:'Objeto expandido', desc:'Estruturas ópticas e profundidade simulada, evocando lente, microscopia e brilho holográfico.', color:'#f39c12', plane:'back', x:2.85, y:2.1, z:9.85, w:1.70, h:1.18},
  {id:'a4', title:'Horizonte Índigo', artist:'Ciro Menezes', year:'2023', theme:'Geometria', desc:'Superfícies geométricas com vibração cromática e sobreposição ótica nas bordas.', color:'#8e44ad', plane:'left', x:-4.82, y:2.05, z:6.05, w:1.58, h:1.08},
  {id:'a5', title:'Traço Latente', artist:'Rafaela Costa', year:'2022', theme:'Pintura', desc:'Pintura que pede leitura periférica, contraste baixo e foco seletivo do observador.', color:'#2980b9', plane:'right', x:4.82, y:2.02, z:5.75, w:1.58, h:1.08},
  {id:'a6', title:'Arquivo Luminoso', artist:'Bruno Faria', year:'2021', theme:'Instalação', desc:'Camadas translúcidas, emissão suave e sensação de arquivo suspenso no espaço.', color:'#f1c40f', plane:'left', x:-4.82, y:1.25, z:3.25, w:1.25, h:0.94},
  {id:'a7', title:'Fenda de Sinal', artist:'Nina Prado', year:'2024', theme:'Digital', desc:'Imagem em recorte horizontal que combina ruído, oscilação e compressão poética.', color:'#16a085', plane:'right', x:4.82, y:1.24, z:3.15, w:1.25, h:0.94}
];

let projectedArtworks = [];

function buildArtList(){
  artList.innerHTML = '';
  artworks.forEach(art => {
    const row = document.createElement('div');
    row.className = 'artRow';
    row.innerHTML = '<div class="artBullet" style="background:' + art.color + '"></div>'
      + '<div><div class="title">' + art.title + '</div><div class="sub">' + art.artist + ' · ' + art.year + '</div></div>'
      + '<div class="badge">' + art.theme + '</div>';
    row.addEventListener('click', () => selectArtwork(art.id, true));
    artList.appendChild(row);
  });
}
buildArtList();

function setStatus(on, text){
  statusDot.classList.toggle('on', !!on);
  statusText.textContent = text;
}

function flash(msg){
  blinkToast.textContent = msg;
  blinkToast.classList.add('show');
  clearTimeout(flash._t);
  flash._t = setTimeout(() => blinkToast.classList.remove('show'), 1000);
}

function resizeCanvases(){
  const rect = scenePanel.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  [roomCanvas, heatCanvas].forEach(c => {
    c.width = Math.floor(rect.width * dpr);
    c.height = Math.floor(rect.height * dpr);
    c.style.width = rect.width + 'px';
    c.style.height = rect.height + 'px';
  });
  roomCtx.setTransform(dpr,0,0,dpr,0,0);
  heatCtx.setTransform(dpr,0,0,dpr,0,0);

  const vr = video.getBoundingClientRect();
  camOverlay.width = Math.max(1, Math.floor(vr.width * dpr));
  camOverlay.height = Math.max(1, Math.floor(vr.height * dpr));
  camOverlay.style.width = vr.width + 'px';
  camOverlay.style.height = vr.height + 'px';
  overlayCtx.setTransform(dpr,0,0,dpr,0,0);
}
window.addEventListener('resize', resizeCanvases);

function smoothHistory(v){
  state.gaze.history.push(v);
  if(state.gaze.history.length > 8) state.gaze.history.shift();
  return {
    x: avg(state.gaze.history.map(p => p.x)),
    y: avg(state.gaze.history.map(p => p.y))
  };
}

function eyeBox(landmarks, idxs, vw, vh){
  const pts = idxs.map(i => ({x:landmarks[i].x * vw, y:landmarks[i].y * vh}));
  const minX = Math.min(...pts.map(p=>p.x));
  const maxX = Math.max(...pts.map(p=>p.x));
  const minY = Math.min(...pts.map(p=>p.y));
  const maxY = Math.max(...pts.map(p=>p.y));
  const padX = (maxX - minX) * 0.34;
  const padY = (maxY - minY) * 0.58;
  const x = clamp(minX - padX, 0, vw - 1);
  const y = clamp(minY - padY, 0, vh - 1);
  const w = clamp((maxX - minX) + padX * 2, 12, vw - x);
  const h = clamp((maxY - minY) + padY * 2, 10, vh - y);
  return {x, y, w, h};
}

function irisCenter(landmarks, idxs, vw, vh){
  const pts = idxs.filter(i => landmarks[i]).map(i => ({x:landmarks[i].x * vw, y:landmarks[i].y * vh}));
  if(!pts.length) return null;
  return {
    x: avg(pts.map(p=>p.x)),
    y: avg(pts.map(p=>p.y))
  };
}

function darkestPointInROI(imgData, w, h){
  let min = 255, bestX = Math.floor(w/2), bestY = Math.floor(h/2);
  for(let y=2;y<h-2;y+=2){
    for(let x=2;x<w-2;x+=2){
      const idx = (y*w + x) * 4;
      const g = imgData.data[idx] * 0.299 + imgData.data[idx+1] * 0.587 + imgData.data[idx+2] * 0.114;
      if(g < min){
        min = g;
        bestX = x;
        bestY = y;
      }
    }
  }
  return {x:bestX, y:bestY, gray:min};
}

function pupilFromThreshold(box){
  if(box.w < 10 || box.h < 8) return null;
  const sx = Math.floor(box.x), sy = Math.floor(box.y);
  const sw = Math.floor(box.w), sh = Math.floor(box.h);
  if(sw <= 2 || sh <= 2) return null;

  analysisCtx.drawImage(video, 0, 0, analysisCanvas.width, analysisCanvas.height);
  const scaleX = analysisCanvas.width / video.videoWidth;
  const scaleY = analysisCanvas.height / video.videoHeight;
  const rx = Math.floor(box.x * scaleX);
  const ry = Math.floor(box.y * scaleY);
  const rw = Math.max(4, Math.floor(box.w * scaleX));
  const rh = Math.max(4, Math.floor(box.h * scaleY));
  if(rx + rw >= analysisCanvas.width || ry + rh >= analysisCanvas.height) return null;

  const roi = analysisCtx.getImageData(rx, ry, rw, rh);
  const dark = darkestPointInROI(roi, rw, rh);
  const thresholds = [5, 15, 25];
  let best = null;

  thresholds.forEach(off => {
    const t = dark.gray + off;
    let sumX = 0, sumY = 0, count = 0;
    let minX = rw, minY = rh, maxX = 0, maxY = 0;
    for(let y=0;y<rh;y++){
      for(let x=0;x<rw;x++){
        const idx = (y*rw + x) * 4;
        const g = roi.data[idx] * 0.299 + roi.data[idx+1] * 0.587 + roi.data[idx+2] * 0.114;
        if(g <= t){
          sumX += x; sumY += y; count++;
          if(x<minX) minX = x;
          if(y<minY) minY = y;
          if(x>maxX) maxX = x;
          if(y>maxY) maxY = y;
        }
      }
    }
    if(count < 8) return;
    const spreadX = maxX - minX;
    const spreadY = maxY - minY;
    const compact = 1 / (1 + spreadX + spreadY);
    const score = count * compact;
    if(!best || score > best.score){
      best = {
        score,
        x: sumX / count,
        y: sumY / count
      };
    }
  });

  if(!best) return null;
  return {
    x: box.x + best.x / scaleX,
    y: box.y + best.y / scaleY
  };
}

function distance2d(a,b){
  return Math.hypot(a.x-b.x, a.y-b.y);
}

function ear(landmarks, side, vw, vh){
  let p;
  if(side === 'left'){
    p = {
      a:{x:landmarks[33].x*vw, y:landmarks[33].y*vh},
      b:{x:landmarks[160].x*vw, y:landmarks[160].y*vh},
      c:{x:landmarks[158].x*vw, y:landmarks[158].y*vh},
      d:{x:landmarks[133].x*vw, y:landmarks[133].y*vh},
      e:{x:landmarks[153].x*vw, y:landmarks[153].y*vh},
      f:{x:landmarks[144].x*vw, y:landmarks[144].y*vh},
    };
  } else {
    p = {
      a:{x:landmarks[362].x*vw, y:landmarks[362].y*vh},
      b:{x:landmarks[385].x*vw, y:landmarks[385].y*vh},
      c:{x:landmarks[387].x*vw, y:landmarks[387].y*vh},
      d:{x:landmarks[263].x*vw, y:landmarks[263].y*vh},
      e:{x:landmarks[373].x*vw, y:landmarks[373].y*vh},
      f:{x:landmarks[380].x*vw, y:landmarks[380].y*vh},
    };
  }
  const v1 = distance2d(p.b, p.f);
  const v2 = distance2d(p.c, p.e);
  const h = distance2d(p.a, p.d);
  return h > 0.0001 ? (v1 + v2) / (2 * h) : 0.25;
}

function drawEyeOverlay(landmarks, pupilL, pupilR, boxL, boxR){
  const r = video.getBoundingClientRect();
  overlayCtx.clearRect(0,0,r.width,r.height);
  overlayCtx.save();
  overlayCtx.translate(r.width, 0);
  overlayCtx.scale(-1,1);

  function drawPath(idxs, color){
    overlayCtx.beginPath();
    idxs.forEach((i, n) => {
      if(!landmarks[i]) return;
      const x = landmarks[i].x * r.width;
      const y = landmarks[i].y * r.height;
      if(n===0) overlayCtx.moveTo(x,y); else overlayCtx.lineTo(x,y);
    });
    overlayCtx.closePath();
    overlayCtx.strokeStyle = color;
    overlayCtx.lineWidth = 1.8;
    overlayCtx.stroke();
  }

  drawPath(LEFT_EYE_RING, 'rgba(93,173,226,.9)');
  drawPath(RIGHT_EYE_RING, 'rgba(93,173,226,.9)');

  [boxL, boxR].forEach(box => {
    if(!box) return;
    overlayCtx.strokeStyle = 'rgba(240,192,64,.45)';
    overlayCtx.strokeRect(box.x, box.y, box.w, box.h);
  });

  [pupilL, pupilR].forEach(p => {
    if(!p) return;
    overlayCtx.fillStyle = 'rgba(255,255,255,.9)';
    overlayCtx.beginPath();
    overlayCtx.arc(p.x, p.y, 4.2, 0, Math.PI*2);
    overlayCtx.fill();
    overlayCtx.strokeStyle = 'rgba(231,76,60,.85)';
    overlayCtx.lineWidth = 1.5;
    overlayCtx.beginPath();
    overlayCtx.arc(p.x, p.y, 8, 0, Math.PI*2);
    overlayCtx.stroke();
  });

  overlayCtx.restore();
}

function processBlink(avgEar){
  const b = state.blink;
  if(!b.baselineReady){
    if(avgEar > 0.12 && avgEar < 0.60){
      b.baseline = lerp(b.baseline, avgEar, 0.16);
      b.warmup += 1;
      if(b.warmup > 12){
        b.baselineReady = true;
        blinkText.textContent = 'Pronto';
        calibValue.textContent = state.eye.baselineReady ? 'Ok' : 'Olhe reto e calibre';
      }
    }
    return;
  }

  b.baseline = lerp(b.baseline, clamp(avgEar, 0.12, 0.5), avgEar > b.baseline * 0.85 ? 0.04 : 0.0);
  const ratio = avgEar / Math.max(0.0001, b.baseline);
  const now = performance.now();

  if(b.phase === 'open'){
    if(ratio < b.closeRatio){
      b.closeFrames += 1;
      if(b.closeFrames >= b.minCloseFrames){
        b.phase = 'closed';
        b.closeTs = now;
        b.openFrames = 0;
      }
    } else {
      b.closeFrames = 0;
    }
  } else {
    if(ratio > b.openRatio){
      b.openFrames += 1;
      if(b.openFrames >= b.minOpenFrames){
        const dur = now - b.closeTs;
        b.phase = 'open';
        b.closeFrames = 0;
        b.openFrames = 0;
        if(dur >= b.minMs && dur <= b.maxMs){
          registerBlink(now);
        }
      }
    } else {
      b.openFrames = 0;
    }
  }

  if(b.pendingSingleTs && now - b.pendingSingleTs > b.doubleWindowMs){
    b.pendingSingleTs = 0;
    doZoomOut('1 piscada: afasta');
  }
}

function registerBlink(now){
  const b = state.blink;
  if(b.pendingSingleTs && now - b.pendingSingleTs <= b.doubleWindowMs){
    b.pendingSingleTs = 0;
    doZoomIn('2 piscadas: aproxima');
    b.lastLabel = 'duplo';
  } else {
    b.pendingSingleTs = now;
    b.lastLabel = 'simples';
    flash('1 piscada detectada');
  }
  b.lastBlinkTs = now;
  blinkDebug.textContent = b.lastLabel;
}

function calibrateEyes(){
  state.eye.baselineReady = false;
  state.eye.calibSamples = [];
  state.blink.baselineReady = false;
  state.blink.warmup = 0;
  blinkText.textContent = 'Calibrando';
  calibValue.textContent = 'Calibrando';
  permissionNote.textContent = 'Calibrando olhos: olhe reto por 1 segundo com o rosto parado. O cursor será recentrado pelo padrão da pupila dentro dos olhos.';
  log('Calibração ocular reiniciada.');
}

function commitCalibration(){
  if(state.eye.calibSamples.length < 8) return false;
  state.eye.baseX = avg(state.eye.calibSamples.map(s => s.x));
  state.eye.baseY = avg(state.eye.calibSamples.map(s => s.y));
  state.eye.baselineReady = true;
  calibValue.textContent = 'Ok';
  permissionNote.textContent = 'Calibração concluída. O olho controla a lateral e a vertical do cursor; 1 piscada afasta e 2 piscadas aproximam.';
  log('Calibração ocular concluída.');
  return true;
}

function onResults(results){
  if(!state.running) return;
  const r = video.getBoundingClientRect();
  overlayCtx.clearRect(0,0,r.width,r.height);

  const lm = results.multiFaceLandmarks && results.multiFaceLandmarks[0];
  if(!lm){
    state.gaze.quality = lerp(state.gaze.quality, 0, 0.18);
    state.eye.lostFrames += 1;
    hoverValue.textContent = 'Nenhuma';
    blinkText.textContent = 'Sem leitura';
    return;
  }

  const vw = r.width;
  const vh = r.height;

  const boxL = eyeBox(lm, LEFT_EYE_BOX, vw, vh);
  const boxR = eyeBox(lm, RIGHT_EYE_BOX, vw, vh);

  const irisL = irisCenter(lm, LEFT_IRIS, vw, vh);
  const irisR = irisCenter(lm, RIGHT_IRIS, vw, vh);
  const pupilL = pupilFromThreshold(boxL) || irisL;
  const pupilR = pupilFromThreshold(boxR) || irisR;

  drawEyeOverlay(lm, pupilL, pupilR, boxL, boxR);

  if(!pupilL || !pupilR){
    state.gaze.quality = lerp(state.gaze.quality, 0.1, 0.18);
    blinkText.textContent = 'Leitura fraca';
    return;
  }

  const rawLeftX = ((pupilL.x - boxL.x) / Math.max(1, boxL.w)) - 0.5;
  const rawLeftY = ((pupilL.y - boxL.y) / Math.max(1, boxL.h)) - 0.5;
  const rawRightX = ((pupilR.x - boxR.x) / Math.max(1, boxR.w)) - 0.5;
  const rawRightY = ((pupilR.y - boxR.y) / Math.max(1, boxR.h)) - 0.5;

  const rawX = (rawLeftX + rawRightX) * 0.5;
  const rawY = (rawLeftY + rawRightY) * 0.5;

  state.eye.lastRaw = {x:rawX, y:rawY};

  if(!state.eye.baselineReady){
    state.eye.calibSamples.push({x:rawX, y:rawY});
    if(state.eye.calibSamples.length > 18) state.eye.calibSamples.shift();
    commitCalibration();
  }

  const dx = rawX - state.eye.baseX;
  const dy = rawY - state.eye.baseY;
  let targetX = 0.5 + dx * state.eye.gainX * (state.gaze.invertX ? -1 : 1);
  let targetY = 0.5 + dy * state.eye.gainY;

  targetX = clamp(targetX, 0.03, 0.97);
  targetY = clamp(targetY, 0.05, 0.95);

  const smooth = smoothHistory({x:targetX, y:targetY});
  state.gaze.targetX = smooth.x;
  state.gaze.targetY = smooth.y;
  state.gaze.quality = lerp(state.gaze.quality, 0.74, 0.14);

  const eyeWidth = (boxL.w + boxR.w) / 2;
  const binocularAgreement = 1 - clamp(Math.abs(rawLeftX - rawRightX) * 1.8 + Math.abs(rawLeftY - rawRightY) * 1.2, 0, 1);
  const sizeScore = clamp((eyeWidth - 32) / 90, 0, 1);
  state.trackingQuality = clamp(binocularAgreement * 0.55 + sizeScore * 0.45, 0.05, 0.99);
  qualityValue.textContent = state.trackingQuality.toFixed(2);

  const earL = ear(lm, 'left', vw, vh);
  const earR = ear(lm, 'right', vw, vh);
  const avgEar = (earL + earR) * 0.5;
  processBlink(avgEar);
  blinkText.textContent = state.blink.baselineReady ? (state.blink.pendingSingleTs ? 'Aguardando 2ª' : 'Pronto') : 'Calibrando';

  hoverValue.textContent = state.hover.id ? (artworks.find(a => a.id === state.hover.id)?.title || 'Obra') : 'Nenhuma';
}

function startTracking(){
  if(state.running) return;
  if(!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)){
    permissionNote.textContent = 'Este navegador não expõe getUserMedia para câmera.';
    log('getUserMedia indisponível.');
    return;
  }

  navigator.mediaDevices.getUserMedia({video:{facingMode:'user', width:{ideal:1280}, height:{ideal:720}}, audio:false})
    .then(stream => {
      state.stream = stream;
      video.srcObject = stream;
      video.onloadedmetadata = async () => {
        await video.play();
        resizeCanvases();

        state.faceMesh = new window.FaceMesh({
          locateFile: file => 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/' + file
        });
        state.faceMesh.setOptions({
          maxNumFaces:1,
          refineLandmarks:true,
          minDetectionConfidence:0.5,
          minTrackingConfidence:0.5
        });
        state.faceMesh.onResults(onResults);

        const loop = async () => {
          if(!state.running || !state.faceMesh || video.readyState < 2) return;
          try {
            await state.faceMesh.send({image: video});
          } catch (err) {
            log('Falha no FaceMesh: ' + err);
          }
          state.raf = requestAnimationFrame(loop);
        };

        state.running = true;
        state.startedAt = performance.now();
        resetInteractionState();
        setStatus(true, 'Ativo');
        controlText.textContent = 'Olho';
        modeValue.textContent = 'Ocular';
        permissionNote.textContent = 'Tracking ocular ativo. Agora clique em “Calibrar olhos” olhando reto.';
        log('Câmera iniciada.');
        loop();
      };
    })
    .catch(err => {
      permissionNote.textContent = 'Não consegui abrir a câmera: ' + err;
      log('Erro de câmera: ' + err);
    });
}

function stopTracking(){
  state.running = false;
  if(state.raf) cancelAnimationFrame(state.raf);
  state.raf = null;
  if(state.stream){
    state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
  }
  if(state.faceMesh){
    try { state.faceMesh.close(); } catch(e) {}
    state.faceMesh = null;
  }
  video.srcObject = null;
  overlayCtx.clearRect(0,0,camOverlay.width,camOverlay.height);
  setStatus(false, 'Parado');
  permissionNote.textContent = 'Tracking parado.';
  log('Tracking parado.');
}

function resetInteractionState(){
  state.hover.id = null;
  state.hover.startTs = 0;
  state.selectedId = null;
  state.fixations = 0;
  state.seen = new Set();
  state.heatPoints = [];
  state.focusedHistory = [];
  state.eye.baselineReady = false;
  state.eye.calibSamples = [];
  state.blink.baselineReady = false;
  state.blink.warmup = 0;
  state.blink.pendingSingleTs = 0;
  state.gaze.history = [];
  state.gaze.x = 0.5;
  state.gaze.y = 0.5;
  state.gaze.targetX = 0.5;
  state.gaze.targetY = 0.5;
  state.zoom.level = 0;
  state.zoom.target = 0;
  updateSelectedInfo(null);
  fixValue.textContent = '0';
  seenValue.textContent = '0';
  zoomValue.textContent = '1.0x';
  blinkDebug.textContent = '—';
  calibValue.textContent = 'Pendente';
  qualityValue.textContent = '0.00';
  dwellFill.style.width = '0%';
  floatBox.classList.remove('show');
  heatCtx.clearRect(0,0,heatCanvas.width,heatCanvas.height);
}

function updateSelectedInfo(art){
  if(!art){
    selectedTitle.textContent = 'Nenhuma obra selecionada';
    selectedArtist.textContent = 'Olhe para uma obra até o dwell completar.';
    selectedDesc.textContent = 'Quando a obra entra em foco, aparece uma ficha genérica em cima dela e aqui na lateral.';
    return;
  }
  selectedTitle.textContent = art.title;
  selectedArtist.textContent = art.artist + ' · ' + art.year + ' · ' + art.theme;
  selectedDesc.textContent = art.desc;
}

function projectPoint(x,y,z, cameraX, cameraZ, fov, w, h){
  const cx = w * 0.5;
  const cy = h * 0.56;
  const relX = x - cameraX;
  const relY = y - 1.6;
  const relZ = z - cameraZ;
  if(relZ <= 0.1) return null;
  const s = fov / relZ;
  return {
    x: cx + relX * s,
    y: cy - relY * s,
    s, z: relZ
  };
}

function artworkPoly(art, cameraX, cameraZ, fov, w, h){
  let pts = [];
  if(art.plane === 'back'){
    pts = [
      projectPoint(art.x - art.w/2, art.y + art.h/2, art.z, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x + art.w/2, art.y + art.h/2, art.z, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x + art.w/2, art.y - art.h/2, art.z, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x - art.w/2, art.y - art.h/2, art.z, cameraX, cameraZ, fov, w, h)
    ];
  } else if(art.plane === 'left'){
    pts = [
      projectPoint(art.x, art.y + art.h/2, art.z - art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y + art.h/2, art.z + art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y - art.h/2, art.z + art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y - art.h/2, art.z - art.w/2, cameraX, cameraZ, fov, w, h)
    ];
  } else {
    pts = [
      projectPoint(art.x, art.y + art.h/2, art.z + art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y + art.h/2, art.z - art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y - art.h/2, art.z - art.w/2, cameraX, cameraZ, fov, w, h),
      projectPoint(art.x, art.y - art.h/2, art.z + art.w/2, cameraX, cameraZ, fov, w, h)
    ];
  }
  if(pts.some(p => !p)) return null;
  return pts;
}

function drawPoly(ctx, pts, fill, stroke, lineWidth){
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for(let i=1;i<pts.length;i++) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.closePath();
  if(fill){ ctx.fillStyle = fill; ctx.fill(); }
  if(stroke){ ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth || 1; ctx.stroke(); }
}

function pointInPoly(pt, poly){
  let c = false;
  for(let i=0, j=poly.length-1; i<poly.length; j=i++){
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    const intersect = ((yi > pt.y) !== (yj > pt.y)) && (pt.x < (xj-xi)*(pt.y-yi)/(yj-yi + 1e-6) + xi);
    if(intersect) c = !c;
  }
  return c;
}

function drawRoom(){
  const w = roomCanvas.clientWidth;
  const h = roomCanvas.clientHeight;
  roomCtx.clearRect(0,0,w,h);

  const cameraX = lerp(-1.6, 1.6, state.gaze.x);
  const cameraZ = -1.25 - state.zoom.level * 0.9;
  const fov = 620 + state.zoom.level * 120;

  const leftWall = [
    projectPoint(-5.2, 3.7, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 0.1, 0.8, cameraX, cameraZ, fov, w, h)
  ];
  const rightWall = [
    projectPoint(5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 3.7, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 0.1, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h)
  ];
  const backWall = [
    projectPoint(-5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h)
  ];
  const floor = [
    projectPoint(-5.2, 0.1, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 0.1, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 0.1, 10.4, cameraX, cameraZ, fov, w, h)
  ];
  const ceil = [
    projectPoint(-5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 3.7, 10.4, cameraX, cameraZ, fov, w, h),
    projectPoint(5.2, 3.7, 0.8, cameraX, cameraZ, fov, w, h),
    projectPoint(-5.2, 3.7, 0.8, cameraX, cameraZ, fov, w, h)
  ];

  roomCtx.fillStyle = '#06101f';
  roomCtx.fillRect(0,0,w,h);

  if(floor.every(Boolean)) drawPoly(roomCtx, floor, 'rgba(230,236,245,.12)', 'rgba(255,255,255,.05)', 1.1);
  if(ceil.every(Boolean)) drawPoly(roomCtx, ceil, 'rgba(255,255,255,.02)', 'rgba(255,255,255,.03)', 1.0);
  if(leftWall.every(Boolean)) drawPoly(roomCtx, leftWall, 'rgba(77,96,136,.16)', 'rgba(255,255,255,.04)', 1);
  if(rightWall.every(Boolean)) drawPoly(roomCtx, rightWall, 'rgba(65,82,120,.16)', 'rgba(255,255,255,.04)', 1);
  if(backWall.every(Boolean)) drawPoly(roomCtx, backWall, 'rgba(78,92,122,.20)', 'rgba(255,255,255,.04)', 1);

  roomCtx.save();
  roomCtx.globalAlpha = 0.18;
  for(let i=0;i<24;i++){
    const px = ((i * 73) % w);
    const py = ((i * 41) % h);
    roomCtx.fillStyle = i % 2 ? 'rgba(93,173,226,.32)' : 'rgba(165,105,189,.26)';
    roomCtx.beginPath();
    roomCtx.arc(px + (state.gaze.x - 0.5) * 50, py + (state.gaze.y - 0.5) * 28, 1.2 + (i % 3), 0, Math.PI*2);
    roomCtx.fill();
  }
  roomCtx.restore();

  projectedArtworks = [];
  artworks.forEach(art => {
    const poly = artworkPoly(art, cameraX, cameraZ, fov, w, h);
    if(!poly) return;
    const cx = avg(poly.map(p=>p.x));
    const cy = avg(poly.map(p=>p.y));
    const depth = avg(poly.map(p=>p.z));
    projectedArtworks.push({art, poly, center:{x:cx, y:cy}, depth});
  });

  projectedArtworks.sort((a,b) => b.depth - a.depth);
  projectedArtworks.forEach(item => {
    const focused = item.art.id === state.hover.id || item.art.id === state.selectedId;
    const glow = focused ? 26 : 12;
    roomCtx.save();
    roomCtx.shadowBlur = glow;
    roomCtx.shadowColor = focused ? item.art.color : 'rgba(0,0,0,.15)';
    drawPoly(roomCtx, item.poly, item.art.color, focused ? 'rgba(255,255,255,.88)' : 'rgba(255,255,255,.18)', focused ? 2.5 : 1.2);
    roomCtx.restore();

    const inner = item.poly.map((p, i) => {
      const c = item.center;
      return {x: lerp(c.x, p.x, 0.88), y: lerp(c.y, p.y, 0.88)};
    });
    drawPoly(roomCtx, inner, 'rgba(255,255,255,.12)', null, 0);
    roomCtx.fillStyle = 'rgba(255,255,255,.72)';
    roomCtx.font = focused ? '700 13px Space Grotesk' : '600 11px Space Grotesk';
    roomCtx.textAlign = 'center';
    roomCtx.fillText(item.art.title, item.center.x, item.center.y + 4);

    if(focused){
      roomCtx.strokeStyle = 'rgba(240,192,64,.92)';
      roomCtx.lineWidth = 2;
      drawPoly(roomCtx, item.poly, null, roomCtx.strokeStyle, 2);
    }
  });

  drawHeatPoint();
  drawFloatInfo();
}

function drawHeatPoint(){
  const w = heatCanvas.clientWidth;
  const h = heatCanvas.clientHeight;
  const x = state.gaze.x * w;
  const y = state.gaze.y * h;
  state.heatPoints.push({x,y});
  if(state.heatPoints.length > 3200) state.heatPoints.shift();

  const g = heatCtx.createRadialGradient(x, y, 0, x, y, 28);
  g.addColorStop(0, 'rgba(255,96,32,.20)');
  g.addColorStop(1, 'rgba(255,96,32,0)');
  heatCtx.fillStyle = g;
  heatCtx.fillRect(x-28, y-28, 56, 56);
}

function drawFloatInfo(){
  const focused = projectedArtworks.find(p => p.art.id === state.hover.id) || projectedArtworks.find(p => p.art.id === state.selectedId);
  if(!focused){
    floatBox.classList.remove('show');
    return;
  }
  floatTitle.textContent = focused.art.title;
  floatSub.textContent = focused.art.artist + ' · ' + focused.art.year + ' · ' + focused.art.theme;
  floatTxt.textContent = focused.art.desc;
  floatBox.style.left = focused.center.x + 'px';
  floatBox.style.top = focused.center.y + 'px';
  floatBox.classList.add('show');
}

function updateHover(){
  const w = roomCanvas.clientWidth;
  const h = roomCanvas.clientHeight;
  const pt = {x: state.gaze.x * w, y: state.gaze.y * h};

  let best = null;
  projectedArtworks.forEach(item => {
    const inside = pointInPoly(pt, item.poly);
    const d = Math.hypot(pt.x - item.center.x, pt.y - item.center.y);
    const score = (inside ? 0 : 1) * 1000 + d;
    if(!best || score < best.score){
      best = {item, score, inside, d};
    }
  });

  if(!best){
    state.hover.id = null;
    state.hover.startTs = 0;
    dwellFill.style.width = '0%';
    return;
  }

  const threshold = best.inside ? 999 : 92;
  if(best.d > threshold){
    state.hover.id = null;
    state.hover.startTs = 0;
    dwellFill.style.width = '0%';
    return;
  }

  if(state.hover.id !== best.item.art.id){
    state.hover.id = best.item.art.id;
    state.hover.startTs = performance.now();
    state.fixations += 1;
    fixValue.textContent = String(state.fixations);
  }

  const held = performance.now() - state.hover.startTs;
  const pct = clamp(held / state.hover.dwellMs, 0, 1);
  dwellFill.style.width = (pct * 100).toFixed(1) + '%';

  if(pct >= 1 && state.selectedId !== state.hover.id){
    selectArtwork(state.hover.id, true);
    state.hover.startTs = performance.now();
  }
}

function selectArtwork(id, viaGaze){
  state.selectedId = id;
  const art = artworks.find(a => a.id === id);
  if(!art) return;
  updateSelectedInfo(art);
  state.seen.add(id);
  seenValue.textContent = String(state.seen.size);
  if(viaGaze) flash('Obra selecionada');
}

function doZoomIn(label){
  state.zoom.target = clamp(state.zoom.target + 1, 0, 3);
  flash(label || 'Aproximando');
  zoomValue.textContent = (1 + state.zoom.target * 0.35).toFixed(1) + 'x';
}
function doZoomOut(label){
  state.zoom.target = clamp(state.zoom.target - 1, 0, 3);
  flash(label || 'Afastando');
  zoomValue.textContent = (1 + state.zoom.target * 0.35).toFixed(1) + 'x';
}

function animate(){
  state.gaze.x = lerp(state.gaze.x, state.gaze.targetX, 0.13);
  state.gaze.y = lerp(state.gaze.y, state.gaze.targetY, 0.13);
  state.zoom.level = lerp(state.zoom.level, state.zoom.target, 0.10);

  gazeCursor.style.left = (state.gaze.x * 100).toFixed(2) + '%';
  gazeCursor.style.top = (state.gaze.y * 100).toFixed(2) + '%';

  drawRoom();
  updateHover();

  blinkDebug.textContent = state.blink.lastLabel;
  qualityValue.textContent = state.trackingQuality.toFixed(2);
  hoverValue.textContent = state.hover.id ? (artworks.find(a => a.id === state.hover.id)?.title || 'Obra') : 'Nenhuma';

  requestAnimationFrame(animate);
}

async function exportPdf(){
  try{
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF({orientation:'landscape', unit:'pt', format:'a4'});
    const roomImg = roomCanvas.toDataURL('image/png');
    const heatImg = heatCanvas.toDataURL('image/png');

    pdf.setFillColor(6,13,26);
    pdf.rect(0,0,842,595,'F');
    pdf.setTextColor(232,240,255);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(18);
    pdf.text('Relatório da galeria ocular', 28, 32);

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(10);
    pdf.setTextColor(137,160,199);
    pdf.text('Controle principal por olho. 1 piscada afasta. 2 piscadas aproximam.', 28, 50);

    pdf.addImage(roomImg, 'PNG', 28, 70, 500, 340);
    pdf.setFontSize(12);
    pdf.setTextColor(232,240,255);
    pdf.text('Heatmap do relatório', 560, 84);
    pdf.addImage(heatImg, 'PNG', 540, 96, 260, 180);

    pdf.setFontSize(11);
    pdf.setTextColor(232,240,255);
    pdf.text('Resumo', 540, 300);
    pdf.setTextColor(137,160,199);
    pdf.text('Fixações: ' + state.fixations, 540, 322);
    pdf.text('Obras vistas: ' + state.seen.size, 540, 338);
    pdf.text('Qualidade ocular: ' + state.trackingQuality.toFixed(2), 540, 354);
    pdf.text('Zoom final: ' + (1 + state.zoom.target * 0.35).toFixed(1) + 'x', 540, 370);

    let y = 400;
    Array.from(state.seen).slice(0,5).forEach(id => {
      const art = artworks.find(a => a.id === id);
      if(!art) return;
      pdf.setTextColor(232,240,255);
      pdf.text(art.title + ' — ' + art.artist, 540, y);
      pdf.setTextColor(137,160,199);
      const lines = pdf.splitTextToSize(art.desc, 240);
      pdf.text(lines, 540, y + 14);
      y += 42;
    });

    pdf.save('relatorio_galeria_ocular.pdf');
    flash('PDF exportado');
  }catch(err){
    log('Falha ao exportar PDF: ' + err);
  }
}

document.getElementById('startBtn').addEventListener('click', startTracking);
document.getElementById('stopBtn').addEventListener('click', stopTracking);
document.getElementById('calibrateBtn').addEventListener('click', calibrateEyes);
document.getElementById('invertBtn').addEventListener('click', () => {
  state.gaze.invertX = !state.gaze.invertX;
  log('Invert X: ' + (state.gaze.invertX ? 'ligado' : 'desligado'));
});
document.getElementById('zoomInBtn').addEventListener('click', () => doZoomIn('Zoom manual'));
document.getElementById('zoomOutBtn').addEventListener('click', () => doZoomOut('Zoom manual'));
document.getElementById('zoomInBtn2').addEventListener('click', () => doZoomIn('Zoom manual'));
document.getElementById('zoomOutBtn2').addEventListener('click', () => doZoomOut('Zoom manual'));
document.getElementById('exportBtn').addEventListener('click', exportPdf);

resizeCanvases();
resetInteractionState();
setStatus(false, 'Parado');
controlText.textContent = 'Olho';
modeValue.textContent = 'Ocular';
blinkText.textContent = 'Aguardando';
log('Interface pronta.');
animate();
})();
</script>
</div>
"""

components.html(HTML_APP, height=1520, scrolling=True)
