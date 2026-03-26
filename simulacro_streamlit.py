import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sala 3D – Face Tracking", layout="wide")

st.title("Sala 3D com Face Tracking")
st.caption("Tracking pelo rosto corrigido: virar o rosto para um lado move para o mesmo lado na tela. 1 piscar = zoom in, 2 piscadas rápidas = zoom out.")

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
    <h2>🎨 Sala 3D – Face Tracking</h2>
    <p>Tracking pelo rosto corrigido (direção natural). Vire o rosto para a direita e a cena acompanha para a direita. <strong>1 piscar</strong> → zoom na obra em foco &nbsp;|&nbsp; <strong>2 piscadas rápidas (&lt;500ms)</strong> → afasta o zoom.</p>
  </div>
  <div class="controls">
    <button class="btn primary" id="startBtn">▶ Iniciar tracking</button>
    <button class="btn warn" id="calibrateBtn">⊕ Calibrar</button>
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
      <div class="chip" id="blinkChip">👁 Blink: <strong id="blinkText">Pronto</strong></div>

      <div class="meter">
        <div class="label">Dwell-click</div>
        <div class="bar"><div id="dwellFill"></div></div>
      </div>

      <div id="blink-indicator">👁 Blink detectado</div>
      <div id="permission-note">Sala carregada. Clique em "Iniciar tracking" para webcam. Nesta versão, virar o rosto para a direita leva o foco para a direita da tela. Sem câmera, o modo mouse funciona normalmente.</div>
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
  running:false, usingMouse:true,
  faceMesh:null, stream:null, rafMedia:null,
  startedAt:null,
  sampleIntervalMs:80, lastSampleTs:0,
  hoverStartTs:0, dwellMs:1100,
  hoveredId:null, selectedId:null,
  fixations:0, inFixation:false,
  stableFor:0, lastPointPx:null,
  heatPoints:[], revealPoints:[], selections:[],
  seenIds:new Set(),

  // Calibração: depois de calibrar ajusta offsets
  calib:{ xOff:0, yOff:0, gainX:1.12, gainY:1.06 },

  // ── BLINK STATE (single/double) ──
  blink:{
    closed:false, closeTs:0,
    threshold:0.175,   // razão vertical/horizontal abaixo = fechado
    minMs:55,          // mínimo para contar como piscar
    maxMs:420,         // máximo (acima = fechamento longo, ignora)
    lastBlinkTs:0,     // timestamp do blink anterior
    doubleWindowMs:500,// janela para detectar 2º piscar (double blink)
    singleTimer:null,  // timer pendente do single blink
    pendingSingle:false
  },

  zoom:{ active:false, targetId:null, focus:0, focusTarget:0 }
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

function selectArtwork(art,source){
  state.selectedId=art.id;
  state.zoom.active=true;
  state.zoom.targetId=art.id;
  state.zoom.focusTarget=1;
  zoomText.textContent='Zoom';
  updateSelPanel(art);
  if(!state.seenIds.has(art.id)){
    state.seenIds.add(art.id);
    statArtworks.textContent=String(state.seenIds.size);
  }
  state.selections.push({id:art.id,title:art.title,ts:Date.now(),source});
  log('Obra: "'+art.title+'" via '+source);
}

function resetZoom(){
  state.zoom.focusTarget=0;
  state.zoom.active=false;
  state.zoom.targetId=null;
  state.selectedId=null;
  zoomText.textContent='Normal';
  updateSelPanel(null);
}

// ─── BLINK: single vs double ───
// Lógica:
//   - Quando olho abre após blink válido:
//     Se blink anterior foi há < doubleWindowMs → É DOUBLE BLINK → cancela timer single → executa ação double
//     Senão → Agenda timer para ação single (se outro blink vier antes, cancela e dispara double)
function onSingleBlink(){
  const hovered=artById(state.hoveredId);
  if(hovered){
    selectArtwork(hovered,'single_blink');
    flashBlinkIndicator('👁 1 piscar → zoom em "'+hovered.title+'"');
    log('Single blink → zoom: '+hovered.title);
  } else if(state.zoom.focusTarget>0){
    resetZoom();
    flashBlinkIndicator('👁 1 piscar → zoom resetado');
    log('Single blink → zoom resetado (sem obra em foco)');
  }
}

function onDoubleBlink(){
  clearTimeout(state.blink.singleTimer);
  state.blink.pendingSingle=false;
  if(state.zoom.focusTarget>0){
    resetZoom();
    flashBlinkIndicator('😮 2 piscadas → zoom afastado');
    log('Double blink → afasta zoom');
  } else {
    flashBlinkIndicator('😮 2 piscadas (sem zoom ativo)');
    log('Double blink sem zoom ativo');
  }
}

function processBlink(landmarks){
  const eo=eyeOpenness;
  const leftOpen  = eo(landmarks,159,145,33,133);
  const rightOpen = eo(landmarks,386,374,362,263);
  const openness  = (leftOpen+rightOpen)/2;
  const now=Date.now();

  if(openness < state.blink.threshold && !state.blink.closed){
    state.blink.closed=true;
    state.blink.closeTs=now;
    setBlink('Fechado');
    gazeCursor.style.borderColor='rgba(243,156,18,.9)';
  } else if(openness >= state.blink.threshold && state.blink.closed){
    const dur=now-state.blink.closeTs;
    state.blink.closed=false;
    setBlink('Aberto');
    gazeCursor.style.borderColor='rgba(255,255,255,.92)';

    if(dur>=state.blink.minMs && dur<=state.blink.maxMs){
      const timeSinceLast=now-state.blink.lastBlinkTs;

      if(state.blink.pendingSingle && timeSinceLast < state.blink.doubleWindowMs){
        // ── DOUBLE BLINK ──
        onDoubleBlink();
        state.blink.lastBlinkTs=0; // reset para não triggar terceiro
      } else {
        // ── POTENTIAL SINGLE BLINK ──
        // Agendar com delay para confirmar que não vem o 2º piscar
        state.blink.lastBlinkTs=now;
        state.blink.pendingSingle=true;
        clearTimeout(state.blink.singleTimer);
        state.blink.singleTimer=setTimeout(()=>{
          if(state.blink.pendingSingle){
            state.blink.pendingSingle=false;
            onSingleBlink();
          }
        }, state.blink.doubleWindowMs);
      }
    }
  }
}

function eyeOpenness(lm,topIdx,botIdx,lIdx,rIdx){
  const top=lm[topIdx], bot=lm[botIdx], left=lm[lIdx], right=lm[rIdx];
  const vert=Math.hypot(top.x-bot.x, top.y-bot.y);
  const horiz=Math.hypot(left.x-right.x, left.y-right.y);
  return vert/Math.max(horiz,1e-6);
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
  const ids=[10,152,234,454,93,323,127,356];
  const pts=ids.map(i=>lm[i]).filter(Boolean);
  return {
    minX:Math.min(...pts.map(p=>p.x)),
    maxX:Math.max(...pts.map(p=>p.x)),
    minY:Math.min(...pts.map(p=>p.y)),
    maxY:Math.max(...pts.map(p=>p.y))
  };
}

function mapFaceTracking(landmarks){
  const box = faceBox(landmarks);
  const nose = landmarks[1];
  const forehead = landmarks[10];
  const chin = landmarks[152];
  const leftEyeOuter = landmarks[33];
  const rightEyeOuter = landmarks[263];
  const leftTemple = landmarks[234];
  const rightTemple = landmarks[454];

  if(!nose || !forehead || !chin || !leftEyeOuter || !rightEyeOuter || !leftTemple || !rightTemple){
    return;
  }

  const faceW = Math.max(.001, rightTemple.x - leftTemple.x);
  const faceH = Math.max(.001, chin.y - forehead.y);

  // posição do nariz dentro da caixa da face (frame original da câmera)
  const noseXRaw = clamp((nose.x - box.minX) / Math.max(.001, box.maxX - box.minX), 0, 1);
  const noseYRaw = clamp((nose.y - box.minY) / Math.max(.001, box.maxY - box.minY), 0, 1);

  // vídeo está espelhado na interface -> inverter X uma única vez
  const noseXMirrored = 1 - noseXRaw;

  // yaw estimado pela diferença entre nariz e centro dos olhos
  const eyeMidX = (leftEyeOuter.x + rightEyeOuter.x) * 0.5;
  const yawRaw = (nose.x - eyeMidX) / Math.max(.001, rightEyeOuter.x - leftEyeOuter.x);

  // como o vídeo está espelhado, yaw positivo precisa virar negativo na tela
  const yawScreen = -yawRaw;

  // pitch estimado pela posição vertical do nariz dentro da face
  const faceMidY = (forehead.y + chin.y) * 0.5;
  const pitchRaw = (nose.y - faceMidY) / faceH;

  // combina movimento lateral do rosto com rotação da cabeça
  let targetX = 0.5 + (noseXMirrored - 0.5) * state.calib.gainX + yawScreen * 0.55 + state.calib.xOff;
  let targetY = 0.5 + (noseYRaw - 0.5) * state.calib.gainY + pitchRaw * 0.18 + state.calib.yOff;

  // zona morta para reduzir jitter
  const dx = targetX - 0.5;
  const dy = targetY - 0.5;
  if(Math.abs(dx) < 0.018) targetX = 0.5;
  if(Math.abs(dy) < 0.018) targetY = 0.5;

  // suavização um pouco mais forte
  targetX = clamp(targetX, .02, .98);
  targetY = clamp(targetY, .02, .98);
  gaze.targetX = clamp(lerp(gaze.targetX, targetX, .18), .02, .98);
  gaze.targetY = clamp(lerp(gaze.targetY, targetY, .18), .02, .98);

  // qualidade baseada em proporção e simetria mínimas
  const symmetry = 1 - Math.abs((rightEyeOuter.x - eyeMidX) - (eyeMidX - leftEyeOuter.x)) * 8;
  gaze.quality = clamp(symmetry, .5, .99);
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
  const r=scenePanel.getBoundingClientRect();
  ctx.clearRect(0,0,r.width,r.height);

  const bg=ctx.createLinearGradient(0,0,0,r.height);
  bg.addColorStop(0,'#060d1a'); bg.addColorStop(1,'#020709');
  ctx.fillStyle=bg; ctx.fillRect(0,0,r.width,r.height);

  const zoomArt=artById(state.zoom.targetId);
  state.zoom.focus=lerp(state.zoom.focus, state.zoom.focusTarget, .07);

  const gx=gaze.x-.5, gy=gaze.y-.5;
  let fx=0,fy=2.0,fz=8.5;
  if(zoomArt){
    fx=zoomArt.x; fy=zoomArt.y;
    fz=zoomArt.z-(zoomArt.plane==='back'?1.9:0);
  }

  const f=state.zoom.focus;
  cam.x     = lerp(gx*0.85,  fx*.18, f);
  cam.y     = lerp(1.65-gy*.32, fy-.10, f);
  cam.z     = lerp(-1.4, fz-6.45, f);
  cam.yaw   = lerp(gx*.34,  fx*.016, f);
  cam.pitch = lerp(-gy*.11, -.022, f);
  cam.fov   = lerp(cam.baseFov, cam.baseFov*1.52, f);

  const surfDefs=[
    {pts:[[-5,0,0],[5,0,0],[5,0,10],[-5,0,10]],fill:'rgba(18,30,50,.98)',stroke:'rgba(255,255,255,.04)'},
    {pts:[[-5,4,0],[5,4,0],[5,4,10],[-5,4,10]],fill:'rgba(9,16,32,.9)',stroke:'rgba(255,255,255,.04)'},
    {pts:[[-5,0,0],[-5,0,10],[-5,4,10],[-5,4,0]],fill:'rgba(12,20,38,.94)',stroke:'rgba(255,255,255,.05)'},
    {pts:[[5,0,0],[5,0,10],[5,4,10],[5,4,0]],fill:'rgba(11,19,36,.94)',stroke:'rgba(255,255,255,.05)'},
    {pts:[[-5,0,10],[5,0,10],[5,4,10],[-5,4,10]],fill:'rgba(14,23,42,.96)',stroke:'rgba(255,255,255,.05)'}
  ];
  surfDefs.forEach(s=>{
    drawPoly(s.pts.map(p=>projectPt(...p)),s.fill,s.stroke,1);
  });

  // floor grid
  for(let i=-4;i<=4;i++){
    const a=projectPt(i,.001,.2),b=projectPt(i,.001,9.8);
    if(a&&b){ctx.strokeStyle='rgba(255,255,255,.04)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  }
  for(let z=1;z<=10;z++){
    const a=projectPt(-4.8,.001,z),b=projectPt(4.8,.001,z);
    if(a&&b){ctx.strokeStyle='rgba(255,255,255,.04)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  }

  // ambient light
  const sl=projectPt(gx*3,3.5,4.8);
  if(sl){
    const g=ctx.createRadialGradient(sl.x,sl.y,0,sl.x,sl.y,r.width*.34);
    g.addColorStop(0,'rgba(93,173,226,.18)');
    g.addColorStop(.5,'rgba(93,173,226,.06)');
    g.addColorStop(1,'rgba(93,173,226,0)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(sl.x,sl.y,r.width*.34,0,Math.PI*2); ctx.fill();
  }

  drawPedestal(-1.8,3.0,'rgba(93,173,226,.95)');
  drawPedestal(1.8,3.35,'rgba(165,105,189,.95)');

  projectedArtworks=[];
  artworks.forEach(art=>{
    const hl=state.hoveredId===art.id||state.selectedId===art.id||state.zoom.targetId===art.id;
    const poly=drawArtwork(art,hl);
    if(poly) projectedArtworks.push({art,poly});
  });

  // gaze crosshair (sutil)
  const gPx={x:gaze.x*r.width, y:gaze.y*r.height};
  ctx.strokeStyle='rgba(255,255,255,.08)'; ctx.lineWidth=1;
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
    state.hoverStartTs=now+400; // cooldown
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
        setStatus(false,'Rosto não encontrado'); gaze.quality=.4; return;
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
  clearTimeout(state.blink.singleTimer);
  state.blink.pendingSingle=false;
  if(state.rafMedia){ cancelAnimationFrame(state.rafMedia); state.rafMedia=null; }
  if(state.stream){ state.stream.getTracks().forEach(t=>t.stop()); state.stream=null; }
  video.srcObject=null;
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
  state.calib.xOff += (.5-gaze.targetX)*.28;
  state.calib.yOff += (.5-gaze.targetY)*.28;
  state.calib.gainX=1.12; state.calib.gainY=1.06;
  calibText.textContent='Concluída';
  permNote.textContent='Calibração aplicada. Foque no centro da tela e recalibre se necessário.';
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
