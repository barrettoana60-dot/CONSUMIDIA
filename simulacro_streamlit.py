
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Simulacro Face Tracking Estável", layout="wide")

st.title("Simulacro — navegação facial estável na sala 3D")
st.caption(
    "Versão refeita para ficar mais estável: rastreamento por rosto/cabeça com filtros, "
    "movimentação fluida, zonas mortas, colisão simples, dwell-click, heatmap, mini mapa, "
    "1 piscada aproxima, 2 piscadas afastam, tracking facial mais estável e fallback por mouse."
)

HTML_APP = r"""
<div id="simulacro-root">
  <style>
    :root{
      --bg:#07111f;
      --panel:rgba(11,18,35,.9);
      --panel-2:rgba(15,25,44,.94);
      --border:rgba(255,255,255,.08);
      --text:#eef4ff;
      --muted:#a8b9d8;
      --ok:#34d399;
      --warn:#fbbf24;
      --danger:#fb7185;
      --cyan:#7dd3fc;
      --violet:#c084fc;
      --soft:rgba(255,255,255,.04);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    }
    *{box-sizing:border-box}
    body{margin:0;background:transparent}
    #simulacro-root{
      width:100%;
      min-height:1360px;
      color:var(--text);
      padding:18px;
      border-radius:24px;
      overflow:hidden;
      background:
        radial-gradient(circle at top, rgba(81,120,255,.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(194,120,255,.12), transparent 24%),
        linear-gradient(180deg, #06101c 0%, #040812 100%);
      border:1px solid rgba(255,255,255,.06);
    }
    .topbar{
      display:grid;
      grid-template-columns:1fr auto;
      gap:16px;
      align-items:center;
      margin-bottom:16px;
    }
    .headline h2{margin:0;font-size:30px;font-weight:800;letter-spacing:.2px}
    .headline p{margin:8px 0 0;color:var(--muted);max-width:980px;line-height:1.5;font-size:14px}
    .controls{
      display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end;
    }
    .btn{
      border:1px solid rgba(255,255,255,.1);
      background:linear-gradient(180deg, rgba(255,255,255,.12), rgba(255,255,255,.04));
      color:var(--text);
      padding:10px 14px;
      border-radius:14px;
      font-weight:700;
      cursor:pointer;
      transition:.18s ease;
      box-shadow:0 8px 22px rgba(0,0,0,.18);
      user-select:none;
    }
    .btn:hover{transform:translateY(-1px);border-color:rgba(125,211,252,.45)}
    .btn.primary{background:linear-gradient(180deg, rgba(125,211,252,.28), rgba(125,211,252,.12));border-color:rgba(125,211,252,.35)}
    .btn.warn{background:linear-gradient(180deg, rgba(251,191,36,.25), rgba(251,191,36,.08));border-color:rgba(251,191,36,.35)}
    .btn.subtle{background:linear-gradient(180deg, rgba(192,132,252,.18), rgba(192,132,252,.06));border-color:rgba(192,132,252,.3)}
    .layout{
      display:grid;
      grid-template-columns:minmax(0,1.66fr) minmax(360px,.84fr);
      gap:16px;
      min-height:1080px;
    }
    .scene-panel,.sidebar{
      background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
      border:1px solid var(--border);
      border-radius:22px;
      overflow:hidden;
      position:relative;
      backdrop-filter:blur(18px);
    }
    .scene-panel{
      min-height:1020px;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 18px 50px rgba(0,0,0,.25);
    }
    #scene-shell{position:absolute;inset:0}
    #room,#heatmap,#reveal{
      position:absolute;inset:0;width:100%;height:100%;display:block;
    }
    #heatmap,#reveal{pointer-events:none}
    #cursor{
      position:absolute;
      width:28px;height:28px;
      border:2px solid rgba(255,255,255,.95);
      border-radius:999px;
      box-shadow:0 0 0 8px rgba(125,211,252,.16),0 0 24px rgba(125,211,252,.35);
      transform:translate(-50%,-50%);
      pointer-events:none;
      z-index:10;
      left:50%;top:50%;
      transition:width .12s ease,height .12s ease,border-color .12s ease;
    }
    #cursor::after{
      content:"";
      position:absolute;inset:6px;border-radius:999px;background:rgba(255,255,255,.9);
    }
    .chip{
      position:absolute;z-index:12;
      display:inline-flex;align-items:center;gap:8px;
      padding:10px 12px;border-radius:999px;
      background:rgba(9,16,30,.76);
      border:1px solid rgba(255,255,255,.08);
      color:var(--muted);font-size:13px;
      backdrop-filter:blur(12px);
      box-shadow:0 6px 18px rgba(0,0,0,.18);
    }
    .chip strong{color:var(--text)}
    .dot{
      width:10px;height:10px;border-radius:999px;background:var(--danger);
      box-shadow:0 0 18px rgba(251,113,133,.45);
    }
    .dot.on{
      background:var(--ok);box-shadow:0 0 18px rgba(52,211,153,.45);
    }
    #statusChip{top:18px;left:18px}
    #modeChip{top:18px;left:190px}
    #blinkChip{top:18px;left:356px}
    #walkChip{top:18px;left:534px}
    .meter{
      position:absolute;top:18px;right:18px;z-index:12;
      width:250px;padding:12px;border-radius:16px;
      background:rgba(9,16,30,.76);border:1px solid rgba(255,255,255,.08);
      box-shadow:0 6px 18px rgba(0,0,0,.18);
    }
    .meter .label{font-size:12px;color:var(--muted);margin-bottom:8px}
    .bar{width:100%;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden}
    .bar>div{width:0%;height:100%;border-radius:999px;background:linear-gradient(90deg,#7dd3fc 0%,#c084fc 100%)}
    #permission-note{
      position:absolute;left:18px;bottom:18px;z-index:12;
      max-width:820px;padding:10px 14px;border-radius:14px;
      background:rgba(10,18,35,.9);border:1px solid rgba(255,255,255,.08);
      color:var(--muted);font-size:13px;line-height:1.45;
      box-shadow:0 6px 18px rgba(0,0,0,.18);
    }
    #minimap{
      position:absolute;right:18px;bottom:18px;z-index:12;
      width:168px;height:168px;border-radius:18px;
      background:rgba(8,14,26,.82);border:1px solid rgba(255,255,255,.08);
      box-shadow:0 6px 18px rgba(0,0,0,.18);
      backdrop-filter:blur(12px);
      padding:8px;
    }
    #minimap canvas{width:100%;height:100%;display:block}
    .sidebar{
      padding:16px;display:flex;flex-direction:column;gap:14px;
    }
    .card{
      background:linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
      border:1px solid rgba(255,255,255,.08);
      border-radius:20px;
      padding:14px;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.04);
    }
    .card h3{margin:0 0 10px;font-size:15px}
    #video{
      width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:16px;
      border:1px solid rgba(255,255,255,.08);background:#030712;transform:scaleX(-1);
    }
    .stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .stat{
      background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
      border-radius:16px;padding:12px;
    }
    .stat .k{font-size:12px;color:var(--muted);margin-bottom:6px}
    .stat .v{font-size:22px;font-weight:800}
    .meta-line{
      display:flex;justify-content:space-between;gap:10px;
      border-bottom:1px dashed rgba(255,255,255,.08);padding:8px 0;
      color:var(--muted);font-size:13px;
    }
    .meta-line:last-child{border-bottom:none}
    .meta-line strong{color:var(--text);font-size:13px}
    #selected-title{font-size:20px;margin:0 0 6px}
    #selected-artist{color:var(--cyan);margin-bottom:10px;font-weight:700}
    #selected-description{color:var(--muted);line-height:1.5;font-size:13.5px}
    #artwork-list{display:grid;gap:10px;max-height:220px;overflow:auto}
    .art-row{
      display:grid;grid-template-columns:14px 1fr auto;gap:10px;align-items:center;
      background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);
      border-radius:16px;padding:12px;cursor:pointer;
    }
    .art-row:hover{border-color:rgba(125,211,252,.28)}
    .art-bullet{width:14px;height:14px;border-radius:999px}
    .art-title{font-weight:800;margin-bottom:3px}
    .art-sub{color:var(--muted);font-size:12.5px}
    .badge{
      font-size:11px;font-weight:800;color:#dbeafe;background:rgba(125,211,252,.14);
      border:1px solid rgba(125,211,252,.22);padding:6px 9px;border-radius:999px;
    }
    #logBox{
      min-height:140px;max-height:200px;overflow:auto;border-radius:12px;padding:10px;
      background:rgba(3,7,18,.72);border:1px solid rgba(255,255,255,.08);
      color:#a8b9d8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
      font-size:12px;line-height:1.4;white-space:pre-wrap;
    }
    .tuning-grid{
      display:grid;grid-template-columns:1fr;gap:10px;
    }
    .slider-wrap label{
      display:flex;justify-content:space-between;gap:10px;
      font-size:12px;color:var(--muted);margin-bottom:6px;
    }
    .slider-wrap input{width:100%}
    .small-note{color:var(--muted);font-size:12px;line-height:1.4}
    @media (max-width:1140px){
      .layout{grid-template-columns:1fr}
      .scene-panel{min-height:760px}
      #simulacro-root{min-height:1700px}
      .topbar{grid-template-columns:1fr}
      .controls{justify-content:flex-start}
      #modeChip{left:18px;top:62px}
      #blinkChip{left:182px;top:62px}
      #walkChip{left:350px;top:62px}
      .meter{top:104px;right:18px}
      #minimap{right:18px;bottom:92px}
    }
  </style>

  <div class="topbar">
    <div class="headline">
      <h2>Sala 3D guiada pelo rosto/cabeça</h2>
      <p>
        Controle estável por pose facial: virar a cabeça gira a câmera de forma sutil, mover o rosto lateralmente desloca com amortecimento, aproximar o rosto da câmera anda para frente e afastar anda para trás. A navegação usa filtro temporal, zonas mortas, amortecimento extra e colisão simples para reduzir tremedeira. Uma piscada aproxima; duas piscadas rápidas afastam.
      </p>
    </div>
    <div class="controls">
      <button class="btn primary" id="startBtn">Iniciar tracking facial</button>
      <button class="btn warn" id="calibrateBtn">Calibrar rosto</button>
      <button class="btn subtle" id="resetHeatBtn">Limpar heatmap</button>
      <button class="btn" id="resetCamBtn">Resetar câmera</button>
      <button class="btn" id="exportPdfBtn">Exportar PDF</button>
      <button class="btn" id="stopBtn">Parar</button>
    </div>
  </div>

  <div class="layout">
    <div class="scene-panel">
      <div id="scene-shell">
        <canvas id="room"></canvas>
        <canvas id="heatmap"></canvas>
        <canvas id="reveal"></canvas>
        <div id="cursor"></div>
        <div class="chip" id="statusChip"><span id="statusDot" class="dot"></span><span id="statusText">Aguardando</span></div>
        <div class="chip" id="modeChip">Modo: <strong id="modeText">Cena ativa</strong></div>
        <div class="chip" id="blinkChip">Blink: <strong id="blinkText">Pronto</strong></div>
        <div class="chip" id="walkChip">Andar: <strong id="walkText">Parado</strong></div>
        <div class="meter">
          <div class="label">Progresso do dwell-click</div>
          <div class="bar"><div id="dwellFill"></div></div>
        </div>
        <div id="permission-note">A sala já está visível. Clique em “Iniciar tracking facial” para tentar webcam. Se a webcam falhar, o modo mouse continua ativo para testar navegação, dwell-click, zoom e relatório.</div>
        <div id="minimap"><canvas id="miniCanvas"></canvas></div>
      </div>
    </div>

    <div class="sidebar">
      <div class="card">
        <h3>Prévia da câmera</h3>
        <video id="video" autoplay playsinline muted></video>
        <div class="small-note" style="margin-top:8px">
          Se a câmera não abrir, confirme a permissão do navegador e use HTTPS. Sem câmera, o modo mouse continua funcionando.
        </div>
      </div>

      <div class="card">
        <h3>Métricas da sessão</h3>
        <div class="stats-grid">
          <div class="stat"><div class="k">Tempo</div><div class="v" id="statTime">00:00</div></div>
          <div class="stat"><div class="k">Fixações</div><div class="v" id="statFixations">0</div></div>
          <div class="stat"><div class="k">Amostras</div><div class="v" id="statPoints">0</div></div>
          <div class="stat"><div class="k">Obras vistas</div><div class="v" id="statArtworks">0</div></div>
        </div>
        <div class="meta-line"><span>Qualidade estimada</span><strong id="qualityText">0%</strong></div>
        <div class="meta-line"><span>Último hover</span><strong id="hoverText">Nenhum</strong></div>
        <div class="meta-line"><span>Calibração</span><strong id="calibrationText">Pendente</strong></div>
        <div class="meta-line"><span>Zoom</span><strong id="zoomText">Normal</strong></div>
        <div class="meta-line"><span>Velocidade</span><strong id="speedText">0.00</strong></div>
      </div>

      <div class="card">
        <h3>Obra selecionada</h3>
        <div id="selected-title">Nenhuma obra selecionada</div>
        <div id="selected-artist">Pare sobre uma obra por ~0,9 s ou faça duas piscadas rápidas</div>
        <div id="selected-description">A ficha da obra aparece aqui quando o dwell-click termina ou quando o zoom é acionado por 1 piscada (aproxima) ou 2 piscadas rápidas (afasta).</div>
      </div>

      <div class="card">
        <h3>Obras da sala</h3>
        <div id="artwork-list"></div>
      </div>

      <div class="card">
        <h3>Ajustes de estabilidade</h3>
        <div class="tuning-grid">
          <div class="slider-wrap">
            <label><span>Suavização do rosto</span><span id="smoothingValue">0.18</span></label>
            <input type="range" id="smoothingRange" min="0.05" max="0.35" step="0.01" value="0.18">
          </div>
          <div class="slider-wrap">
            <label><span>Zona morta horizontal</span><span id="deadXValue">0.05</span></label>
            <input type="range" id="deadXRange" min="0.01" max="0.12" step="0.01" value="0.05">
          </div>
          <div class="slider-wrap">
            <label><span>Zona morta profundidade</span><span id="deadZValue">0.04</span></label>
            <input type="range" id="deadZRange" min="0.01" max="0.12" step="0.01" value="0.04">
          </div>
          <div class="slider-wrap">
            <label><span>Força do andar</span><span id="walkForceValue">1.00</span></label>
            <input type="range" id="walkForceRange" min="0.40" max="2.20" step="0.05" value="1.00">
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Log do sistema</h3>
        <div id="logBox">Inicializando sala…</div>
      </div>
    </div>
  </div>

  <script>
  (function(){
    // ---------- DOM ----------
    const roomCanvas = document.getElementById('room');
    const heatmapCanvas = document.getElementById('heatmap');
    const revealCanvas = document.getElementById('reveal');
    const miniCanvas = document.getElementById('miniCanvas');
    const scenePanel = document.querySelector('.scene-panel');
    const video = document.getElementById('video');

    const ctx = roomCanvas.getContext('2d');
    const heatCtx = heatmapCanvas.getContext('2d');
    const revealCtx = revealCanvas.getContext('2d');
    const miniCtx = miniCanvas.getContext('2d');

    const cursor = document.getElementById('cursor');
    const dwellFill = document.getElementById('dwellFill');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const modeText = document.getElementById('modeText');
    const blinkText = document.getElementById('blinkText');
    const walkText = document.getElementById('walkText');
    const permissionNote = document.getElementById('permission-note');
    const qualityText = document.getElementById('qualityText');
    const hoverText = document.getElementById('hoverText');
    const calibrationText = document.getElementById('calibrationText');
    const zoomText = document.getElementById('zoomText');
    const speedText = document.getElementById('speedText');

    const statTime = document.getElementById('statTime');
    const statFixations = document.getElementById('statFixations');
    const statPoints = document.getElementById('statPoints');
    const statArtworks = document.getElementById('statArtworks');

    const selectedTitle = document.getElementById('selected-title');
    const selectedArtist = document.getElementById('selected-artist');
    const selectedDescription = document.getElementById('selected-description');
    const artworkList = document.getElementById('artwork-list');
    const logBox = document.getElementById('logBox');

    const smoothingRange = document.getElementById('smoothingRange');
    const deadXRange = document.getElementById('deadXRange');
    const deadZRange = document.getElementById('deadZRange');
    const walkForceRange = document.getElementById('walkForceRange');

    const smoothingValue = document.getElementById('smoothingValue');
    const deadXValue = document.getElementById('deadXValue');
    const deadZValue = document.getElementById('deadZValue');
    const walkForceValue = document.getElementById('walkForceValue');

    function log(msg){
      const line = '[' + new Date().toLocaleTimeString() + '] ' + msg;
      console.log(line);
      logBox.textContent += '\\n' + line;
      logBox.scrollTop = logBox.scrollHeight;
    }

    logBox.textContent = 'Sala inicializada.';
    window.addEventListener('error', e => log('ERRO JS: ' + (e.message || 'desconhecido')));
    window.addEventListener('unhandledrejection', e => log('PROMISE REJECTION: ' + String(e.reason)));

    // ---------- Utils ----------
    function clamp(v, a, b){ return Math.min(b, Math.max(a, v)); }
    function lerp(a, b, t){ return a + (b - a) * t; }
    function avg(points, key){ return points.reduce((s, p) => s + p[key], 0) / Math.max(1, points.length); }
    function round2(n){ return (Math.round(n * 100) / 100).toFixed(2); }
    function smoothstep(x){
      const t = clamp(x, 0, 1);
      return t * t * (3 - 2 * t);
    }
    function applyDeadzone(v, dz){
      if(Math.abs(v) <= dz) return 0;
      const sign = Math.sign(v);
      const mag = (Math.abs(v) - dz) / Math.max(1e-6, 1 - dz);
      return sign * mag;
    }
    function distance2(a, b){
      return Math.hypot(a.x - b.x, a.y - b.y);
    }
    function setStatus(on, text){
      statusDot.classList.toggle('on', !!on);
      statusText.textContent = text;
    }
    function setMode(text){ modeText.textContent = text; }
    function setWalk(text){ walkText.textContent = text; }
    function setBlinkCount(n){ blinkText.textContent = String(n); }
    function setBlinkStatus(t){ blinkText.textContent = t; }

    // ---------- Scene data ----------
    const room = { minX:-5.2, maxX:5.2, minZ:-1.0, maxZ:10.4 };
    const artworks = [
      { id:'obra_01', title:'Memórias de Superfície', artist:'Lívia Andrade', year:'2024', wall:'fundo', color:'#ef4444', description:'Pintura em camadas com relevo cromático.', plane:'back', x:-2.8, y:2.1, z:9.85, w:1.7, h:1.2 },
      { id:'obra_02', title:'Campo Sensível', artist:'Diego Marins', year:'2025', wall:'fundo', color:'#22c55e', description:'Trabalho digital com profundidade simulada.', plane:'back', x:0.0, y:2.2, z:9.85, w:1.7, h:1.2 },
      { id:'obra_03', title:'Eco de Matéria', artist:'Marina Teles', year:'2026', wall:'fundo', color:'#f59e0b', description:'Objeto expandido que sugere microscopia e holografia.', plane:'back', x:2.8, y:2.05, z:9.85, w:1.7, h:1.2 },
      { id:'obra_04', title:'Horizonte Índigo', artist:'Ciro Menezes', year:'2023', wall:'esquerda', color:'#8b5cf6', description:'Composição geométrica com profundidade visual.', plane:'left', x:-4.85, y:2.1, z:6.1, w:1.6, h:1.1 },
      { id:'obra_05', title:'Traço Latente', artist:'Rafaela Costa', year:'2022', wall:'direita', color:'#06b6d4', description:'Pintura com leitura periférica e foco seletivo.', plane:'right', x:4.85, y:2.05, z:5.7, w:1.6, h:1.1 },
      { id:'obra_06', title:'Dobra de Luz', artist:'Nina Sá', year:'2021', wall:'esquerda', color:'#f472b6', description:'Experimento cromático com sensação tátil visual.', plane:'left', x:-4.85, y:2.0, z:3.3, w:1.55, h:1.06 },
      { id:'obra_07', title:'Pulso Mineral', artist:'João Mello', year:'2020', wall:'direita', color:'#38bdf8', description:'Série inspirada em textura, erosão e microscopia.', plane:'right', x:4.85, y:2.08, z:2.9, w:1.55, h:1.06 }
    ];

    const gaze = {
      x:0.5, y:0.5,
      targetX:0.5, targetY:0.5,
      quality:0.82
    };

    const camera = {
      x:0, y:1.65, z:-0.2,
      yaw:0, pitch:0,
      vx:0, vz:0, yawVel:0, pitchVel:0,
      baseFov:690,
      fov:690,
      focus:0
    };

    const filters = {
      smoothing:0.08,
      deadX:0.12,
      deadZ:0.14,
      walkForce:0.72,
      yawGain:0.78,
      pitchGain:0.52,
      strafeGain:0.42,
      depthGain:1.08,
      friction:0.965,
      turnFriction:0.955
    };

    const tracking = {
      running:false,
      usingMouse:true,
      startedAt:null,
      faceMesh:null,
      stream:null,
      rafMedia:null,
      lastSampleTs:0,
      sampleIntervalMs:85,
      calibrationReady:false,
      calibration:{
        centerX:0.5,
        centerY:0.5,
        depth:0.34,
        yaw:0,
        pitch:0
      },
      smoothed:{
        centerX:0.5,
        centerY:0.5,
        depth:0.34,
        yaw:0,
        pitch:0
      },
      raw:{
        centerX:0.5,
        centerY:0.5,
        depth:0.34,
        yaw:0,
        pitch:0
      },
      blink:{
        count:0,
        closed:false,
        closeTs:0,
        lastBlinkTs:0,
        threshold:0.175,
        minMs:80,
        maxMs:340,
        doubleWindowMs:420,
        singleWindowMs:240,
        pending:false,
        pendingTs:0,
        pendingTimer:null
      },
      hoverStartTs:0,
      hoveredArtworkId:null,
      selectedArtworkId:null,
      fixations:0,
      inFixation:false,
      stableFor:0,
      lastPointPx:null,
      heatPoints:[],
      revealPoints:[],
      selections:[],
      seenArtworkIds:new Set(),
      zoomStep:0,
      zoomLevels:[0, 0.55, 0.95],
      zoomTarget:0,
      zoomFocusArtworkId:null,
      projectedArtworks:[]
    };

    function syncTuningLabels(){
      smoothingValue.textContent = Number(filters.smoothing).toFixed(2);
      deadXValue.textContent = Number(filters.deadX).toFixed(2);
      deadZValue.textContent = Number(filters.deadZ).toFixed(2);
      walkForceValue.textContent = Number(filters.walkForce).toFixed(2);
    }
    syncTuningLabels();

    smoothingRange.addEventListener('input', () => {
      filters.smoothing = Number(smoothingRange.value);
      syncTuningLabels();
    });
    deadXRange.addEventListener('input', () => {
      filters.deadX = Number(deadXRange.value);
      syncTuningLabels();
    });
    deadZRange.addEventListener('input', () => {
      filters.deadZ = Number(deadZRange.value);
      syncTuningLabels();
    });
    walkForceRange.addEventListener('input', () => {
      filters.walkForce = Number(walkForceRange.value);
      syncTuningLabels();
    });

    // ---------- Layout resize ----------
    function resizeCanvases(){
      const rect = scenePanel.getBoundingClientRect();
      [roomCanvas, heatmapCanvas, revealCanvas].forEach(canvas => {
        canvas.width = Math.floor(rect.width * window.devicePixelRatio);
        canvas.height = Math.floor(rect.height * window.devicePixelRatio);
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
      });
      miniCanvas.width = Math.floor(152 * window.devicePixelRatio);
      miniCanvas.height = Math.floor(152 * window.devicePixelRatio);
      miniCanvas.style.width = '152px';
      miniCanvas.style.height = '152px';

      ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      heatCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      revealCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      miniCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
    }

    // ---------- Geometry ----------
    function projectPoint(x, y, z){
      const relX = x - camera.x;
      const relY = y - camera.y;
      const relZ = z - camera.z;

      const cosy = Math.cos(camera.yaw), siny = Math.sin(camera.yaw);
      const cosp = Math.cos(camera.pitch), sinp = Math.sin(camera.pitch);

      const x1 = relX * cosy - relZ * siny;
      const z1 = relX * siny + relZ * cosy;
      const y1 = relY;

      const y2 = y1 * cosp - z1 * sinp;
      const z2 = y1 * sinp + z1 * cosp;
      if(z2 <= 0.1) return null;

      const rect = scenePanel.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const s = camera.fov / z2;
      return { x: cx + x1 * s, y: cy - y2 * s, depth:z2, scale:s };
    }

    function drawPoly(points, fill, stroke, lineWidth){
      if(!points || points.some(p => !p)) return;
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for(let i=1;i<points.length;i++) ctx.lineTo(points[i].x, points[i].y);
      ctx.closePath();
      if(fill){ ctx.fillStyle = fill; ctx.fill(); }
      if(stroke){ ctx.lineWidth = lineWidth || 1; ctx.strokeStyle = stroke; ctx.stroke(); }
    }

    function pointInPoly(pt, poly){
      let inside = false;
      for(let i=0, j=poly.length - 1; i<poly.length; j=i++){
        const xi = poly[i].x, yi = poly[i].y;
        const xj = poly[j].x, yj = poly[j].y;
        const intersect = ((yi > pt.y) !== (yj > pt.y)) &&
          (pt.x < ((xj - xi) * (pt.y - yi)) / ((yj - yi) || 1e-6) + xi);
        if(intersect) inside = !inside;
      }
      return inside;
    }

    function getArtworkById(id){
      return artworks.find(a => a.id === id) || null;
    }

    // ---------- Scene drawing ----------
    function drawArtwork(art, highlight){
      let poly = [];
      if(art.plane === 'back'){
        poly = [
          projectPoint(art.x - art.w/2, art.y - art.h/2, art.z),
          projectPoint(art.x + art.w/2, art.y - art.h/2, art.z),
          projectPoint(art.x + art.w/2, art.y + art.h/2, art.z),
          projectPoint(art.x - art.w/2, art.y + art.h/2, art.z)
        ];
      } else if(art.plane === 'left'){
        poly = [
          projectPoint(art.x, art.y - art.h/2, art.z - art.w/2),
          projectPoint(art.x, art.y - art.h/2, art.z + art.w/2),
          projectPoint(art.x, art.y + art.h/2, art.z + art.w/2),
          projectPoint(art.x, art.y + art.h/2, art.z - art.w/2)
        ];
      } else {
        poly = [
          projectPoint(art.x, art.y - art.h/2, art.z + art.w/2),
          projectPoint(art.x, art.y - art.h/2, art.z - art.w/2),
          projectPoint(art.x, art.y + art.h/2, art.z - art.w/2),
          projectPoint(art.x, art.y + art.h/2, art.z + art.w/2)
        ];
      }
      if(poly.some(p => !p)) return null;

      drawPoly(poly, 'rgba(91,74,54,.98)', highlight ? 'rgba(125,211,252,.95)' : 'rgba(255,255,255,.12)', highlight ? 2 : 1);

      const cx = (poly[0].x + poly[1].x + poly[2].x + poly[3].x) / 4;
      const cy = (poly[0].y + poly[1].y + poly[2].y + poly[3].y) / 4;
      const inner = poly.map(p => ({ x:lerp(p.x, cx, .1), y:lerp(p.y, cy, .1) }));

      const grad = ctx.createLinearGradient(inner[0].x, inner[0].y, inner[2].x, inner[2].y);
      grad.addColorStop(0, art.color);
      grad.addColorStop(1, '#0f172a');
      drawPoly(inner, grad, highlight ? 'rgba(255,255,255,.22)' : 'rgba(255,255,255,.08)', 1);

      ctx.fillStyle = 'rgba(255,255,255,.92)';
      ctx.font = 'bold 13px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(art.title, cx, cy - 4);
      ctx.fillStyle = 'rgba(220,230,255,.78)';
      ctx.font = '12px Inter, sans-serif';
      ctx.fillText(art.artist, cx, cy + 14);

      return poly;
    }

    function drawPedestal(x, z, hue){
      const base = [
        projectPoint(x - .55, 0, z - .55),
        projectPoint(x + .55, 0, z - .55),
        projectPoint(x + .55, 0, z + .55),
        projectPoint(x - .55, 0, z + .55)
      ];
      const top = [
        projectPoint(x - .42, 1.05, z - .42),
        projectPoint(x + .42, 1.05, z - .42),
        projectPoint(x + .42, 1.05, z + .42),
        projectPoint(x - .42, 1.05, z + .42)
      ];
      if(base.some(p => !p) || top.some(p => !p)) return;

      drawPoly([base[0], base[1], top[1], top[0]], 'rgba(220,225,235,.82)', 'rgba(255,255,255,.12)', 1);
      drawPoly([base[1], base[2], top[2], top[1]], 'rgba(192,200,215,.85)', 'rgba(255,255,255,.12)', 1);
      drawPoly([base[2], base[3], top[3], top[2]], 'rgba(168,178,190,.88)', 'rgba(255,255,255,.12)', 1);
      drawPoly(top, 'rgba(240,243,248,.95)', 'rgba(255,255,255,.14)', 1);

      const orb = projectPoint(x, 1.55, z);
      if(orb){
        const r = orb.scale * .18;
        const g = ctx.createRadialGradient(orb.x - r*.4, orb.y - r*.4, r*.2, orb.x, orb.y, r*1.5);
        g.addColorStop(0, hue);
        g.addColorStop(1, 'rgba(12,20,36,.15)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function drawEnvironmentLight(){
      const rect = scenePanel.getBoundingClientRect();
      const spotlight = projectPoint((gaze.x - .5) * 3.2, 3.5, 4.8);
      if(!spotlight) return;
      const grd = ctx.createRadialGradient(spotlight.x, spotlight.y, 0, spotlight.x, spotlight.y, rect.width * .33);
      grd.addColorStop(0, 'rgba(125,211,252,.22)');
      grd.addColorStop(.5, 'rgba(125,211,252,.06)');
      grd.addColorStop(1, 'rgba(125,211,252,0)');
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.arc(spotlight.x, spotlight.y, rect.width * .33, 0, Math.PI * 2);
      ctx.fill();
    }

    function drawGrid(){
      for(let i=-4;i<=4;i+=1){
        const a = projectPoint(i, .001, .2);
        const b = projectPoint(i, .001, 9.8);
        if(a && b){
          ctx.strokeStyle = 'rgba(255,255,255,.05)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      for(let z=1; z<=10; z+=1){
        const a = projectPoint(-4.8, .001, z);
        const b = projectPoint(4.8, .001, z);
        if(a && b){
          ctx.strokeStyle = 'rgba(255,255,255,.045)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    function drawRoom(){
      const rect = scenePanel.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);

      const bg = ctx.createLinearGradient(0, 0, 0, rect.height);
      bg.addColorStop(0, '#07111f');
      bg.addColorStop(1, '#030814');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, rect.width, rect.height);

      // Background camera response to cursor / tracking for looking
      const lookX = gaze.x - .5;
      const lookY = gaze.y - .5;

      camera.focus = lerp(camera.focus, tracking.zoomTarget, 0.07);
      camera.fov = lerp(camera.baseFov, camera.baseFov * (1 + camera.focus * 0.85), 0.08);

      // Camera pitch is mainly view, movement is handled elsewhere
      camera.pitch = lerp(camera.pitch, -lookY * 0.14, 0.08);

      const floor = [
        projectPoint(-5,0,0), projectPoint(5,0,0), projectPoint(5,0,10), projectPoint(-5,0,10)
      ];
      const ceiling = [
        projectPoint(-5,4,0), projectPoint(5,4,0), projectPoint(5,4,10), projectPoint(-5,4,10)
      ];
      const leftWall = [
        projectPoint(-5,0,0), projectPoint(-5,0,10), projectPoint(-5,4,10), projectPoint(-5,4,0)
      ];
      const rightWall = [
        projectPoint(5,0,0), projectPoint(5,0,10), projectPoint(5,4,10), projectPoint(5,4,0)
      ];
      const backWall = [
        projectPoint(-5,0,10), projectPoint(5,0,10), projectPoint(5,4,10), projectPoint(-5,4,10)
      ];

      drawPoly(ceiling, 'rgba(11,18,35,.9)', 'rgba(255,255,255,.05)', 1);
      drawPoly(leftWall, 'rgba(15,25,44,.94)', 'rgba(255,255,255,.06)', 1);
      drawPoly(rightWall, 'rgba(12,22,39,.94)', 'rgba(255,255,255,.06)', 1);
      drawPoly(backWall, 'rgba(17,27,48,.96)', 'rgba(255,255,255,.06)', 1);
      drawPoly(floor, 'rgba(22,36,54,.98)', 'rgba(255,255,255,.05)', 1);

      drawGrid();
      drawEnvironmentLight();
      drawPedestal(-1.8, 3.0, 'rgba(125,211,252,.95)');
      drawPedestal(1.8, 3.35, 'rgba(192,132,252,.95)');

      tracking.projectedArtworks = [];
      artworks.forEach(art => {
        const highlight = tracking.hoveredArtworkId === art.id || tracking.selectedArtworkId === art.id || tracking.zoomFocusArtworkId === art.id;
        const poly = drawArtwork(art, highlight);
        if(poly) tracking.projectedArtworks.push({ art, poly });
      });

      const gazePx = { x:gaze.x * rect.width, y:gaze.y * rect.height };
      ctx.strokeStyle = 'rgba(255,255,255,.10)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(gazePx.x, 0);
      ctx.lineTo(gazePx.x, rect.height);
      ctx.moveTo(0, gazePx.y);
      ctx.lineTo(rect.width, gazePx.y);
      ctx.stroke();
    }

    function drawMiniMap(){
      const w = 152, h = 152;
      miniCtx.clearRect(0, 0, w, h);
      miniCtx.fillStyle = 'rgba(8,14,26,.92)';
      miniCtx.fillRect(0, 0, w, h);

      const pad = 12;
      const rw = w - pad * 2;
      const rh = h - pad * 2;

      miniCtx.strokeStyle = 'rgba(255,255,255,.12)';
      miniCtx.lineWidth = 1.2;
      miniCtx.strokeRect(pad, pad, rw, rh);

      function mapX(x){ return pad + (x - room.minX) / (room.maxX - room.minX) * rw; }
      function mapZ(z){ return pad + (z - room.minZ) / (room.maxZ - room.minZ) * rh; }

      artworks.forEach(art => {
        miniCtx.fillStyle = art.color;
        miniCtx.beginPath();
        miniCtx.arc(mapX(art.x), mapZ(art.z), 4.2, 0, Math.PI * 2);
        miniCtx.fill();
      });

      const cx = mapX(camera.x);
      const cz = mapZ(camera.z);
      miniCtx.fillStyle = '#dbeafe';
      miniCtx.beginPath();
      miniCtx.arc(cx, cz, 5.2, 0, Math.PI * 2);
      miniCtx.fill();

      const dirLen = 16;
      miniCtx.strokeStyle = '#7dd3fc';
      miniCtx.lineWidth = 2;
      miniCtx.beginPath();
      miniCtx.moveTo(cx, cz);
      miniCtx.lineTo(cx + Math.sin(camera.yaw) * dirLen, cz + Math.cos(camera.yaw) * dirLen);
      miniCtx.stroke();
    }

    // ---------- UI sync ----------
    function updateCursor(){
      cursor.style.left = (gaze.x * 100) + '%';
      cursor.style.top = (gaze.y * 100) + '%';
    }

    function updateSelectedPanel(art){
      if(!art){
        selectedTitle.textContent = 'Nenhuma obra selecionada';
        selectedArtist.textContent = 'Pare sobre uma obra por ~0,9 s ou faça duas piscadas rápidas';
        selectedDescription.textContent = 'A ficha da obra aparece aqui quando o dwell-click termina ou quando o zoom é acionado por 1 piscada (aproxima) ou 2 piscadas rápidas (afasta).';
        return;
      }
      selectedTitle.textContent = art.title;
      selectedArtist.textContent = art.artist + ' · ' + art.year + ' · parede ' + art.wall;
      selectedDescription.textContent = art.description;
    }

    function buildArtworkList(){
      artworkList.innerHTML = '';
      artworks.forEach(art => {
        const row = document.createElement('div');
        row.className = 'art-row';
        row.innerHTML =
          '<div class="art-bullet" style="background:' + art.color + '"></div>' +
          '<div><div class="art-title">' + art.title + '</div><div class="art-sub">' + art.artist + ' · ' + art.year + '</div></div>' +
          '<div class="badge">' + art.wall + '</div>';
        row.addEventListener('click', () => {
          selectArtwork(art, 'lista');
          tracking.zoomTarget = 0.55;
          tracking.zoomFocusArtworkId = art.id;
        });
        artworkList.appendChild(row);
      });
    }

    // ---------- Interaction ----------
    function addHeatPoint(xNorm, yNorm){
      const rect = scenePanel.getBoundingClientRect();
      const px = xNorm * rect.width;
      const py = yNorm * rect.height;

      tracking.heatPoints.push({x:px, y:py, ts:Date.now()});
      if(tracking.heatPoints.length > 6000) tracking.heatPoints.shift();

      const grad = heatCtx.createRadialGradient(px, py, 4, px, py, 34);
      grad.addColorStop(0,'rgba(255,64,64,.18)');
      grad.addColorStop(.35,'rgba(255,191,0,.12)');
      grad.addColorStop(.7,'rgba(34,197,94,.08)');
      grad.addColorStop(1,'rgba(34,197,94,0)');
      heatCtx.fillStyle = grad;
      heatCtx.beginPath();
      heatCtx.arc(px, py, 34, 0, Math.PI * 2);
      heatCtx.fill();

      tracking.revealPoints.push({x:px, y:py, life:1});
      if(tracking.revealPoints.length > 320) tracking.revealPoints.shift();

      statPoints.textContent = String(tracking.heatPoints.length);
      qualityText.textContent = Math.round(gaze.quality * 100) + '%';

      if(tracking.lastPointPx){
        const dist = distance2({x:px,y:py}, tracking.lastPointPx);
        if(dist < 24){
          tracking.stableFor += tracking.sampleIntervalMs;
          if(tracking.stableFor >= 240 && !tracking.inFixation){
            tracking.fixations += 1;
            tracking.inFixation = true;
            statFixations.textContent = String(tracking.fixations);
          }
        } else {
          tracking.stableFor = 0;
          tracking.inFixation = false;
        }
      }
      tracking.lastPointPx = {x:px, y:py};
    }

    function drawReveal(){
      const rect = scenePanel.getBoundingClientRect();
      revealCtx.clearRect(0, 0, rect.width, rect.height);
      revealCtx.fillStyle = 'rgba(4,8,18,.44)';
      revealCtx.fillRect(0, 0, rect.width, rect.height);
      revealCtx.globalCompositeOperation = 'destination-out';

      tracking.revealPoints.forEach(p => {
        const radius = 104 + p.life * 82;
        const grad = revealCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
        grad.addColorStop(0, 'rgba(255,255,255,' + (.18 * p.life) + ')');
        grad.addColorStop(.45, 'rgba(255,255,255,' + (.11 * p.life) + ')');
        grad.addColorStop(1, 'rgba(255,255,255,0)');
        revealCtx.fillStyle = grad;
        revealCtx.beginPath();
        revealCtx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        revealCtx.fill();
        p.life *= .989;
      });

      tracking.revealPoints = tracking.revealPoints.filter(p => p.life > .08);
      revealCtx.globalCompositeOperation = 'source-over';
    }

    function selectArtwork(art, source){
      tracking.selectedArtworkId = art.id;
      updateSelectedPanel(art);
      if(!tracking.seenArtworkIds.has(art.id)){
        tracking.seenArtworkIds.add(art.id);
        statArtworks.textContent = String(tracking.seenArtworkIds.size);
      }
      tracking.selections.push({id:art.id, title:art.title, ts:Date.now(), source:source || 'hover'});
      tracking.zoomFocusArtworkId = art.id;
      log('Obra selecionada: ' + art.title + ' via ' + (source || 'hover'));
    }

    function resetCamera(){
      camera.x = 0;
      camera.z = -0.2;
      camera.y = 1.65;
      camera.yaw = 0;
      camera.pitch = 0;
      camera.vx = 0;
      camera.vz = 0;
      camera.yawVel = 0;
      camera.pitchVel = 0;
      tracking.zoomTarget = 0;
      tracking.zoomFocusArtworkId = null;
      zoomText.textContent = 'Normal';
      permissionNote.textContent = 'Câmera resetada.';
      log('Câmera resetada.');
    }

    function cycleZoom(direction, source){
      const prevStep = tracking.zoomStep;
      if(direction > 0){
        tracking.zoomStep = clamp(tracking.zoomStep + 1, 0, tracking.zoomLevels.length - 1);
      } else {
        tracking.zoomStep = clamp(tracking.zoomStep - 1, 0, tracking.zoomLevels.length - 1);
      }

      const focusId = tracking.hoveredArtworkId || tracking.selectedArtworkId || tracking.zoomFocusArtworkId;
      if(direction > 0 && focusId){
        tracking.zoomFocusArtworkId = focusId;
      }
      if(direction < 0 && tracking.zoomStep === 0){
        tracking.zoomFocusArtworkId = null;
      }

      tracking.zoomTarget = tracking.zoomLevels[tracking.zoomStep];
      zoomText.textContent =
        tracking.zoomStep === 0 ? 'Normal' :
        tracking.zoomStep === 1 ? 'Aproximado' : 'Muito próximo';

      const label = source === 'single_blink' ? '1 piscada: aproximando.' :
                    source === 'double_blink' ? '2 piscadas: afastando.' :
                    (direction > 0 ? 'Aproximando.' : 'Afastando.');
      permissionNote.textContent = label;

      if(prevStep !== tracking.zoomStep){
        log(direction > 0 ? 'Zoom aproximado.' : 'Zoom afastado.');
      }
    }

    function updateHoverAndDwell(now){
      const rect = scenePanel.getBoundingClientRect();
      const gazePx = { x:gaze.x * rect.width, y:gaze.y * rect.height };
      const hit = tracking.projectedArtworks.find(entry => pointInPoly(gazePx, entry.poly));

      if(!hit){
        tracking.hoveredArtworkId = null;
        tracking.hoverStartTs = now;
        dwellFill.style.width = '0%';
        hoverText.textContent = 'Nenhum';
        cursor.style.width = '28px';
        cursor.style.height = '28px';
        cursor.style.borderColor = 'rgba(255,255,255,.95)';
        return;
      }

      hoverText.textContent = hit.art.title;
      if(tracking.hoveredArtworkId !== hit.art.id){
        tracking.hoveredArtworkId = hit.art.id;
        tracking.hoverStartTs = now;
      }

      const elapsed = now - tracking.hoverStartTs;
      const progress = clamp(elapsed / 900, 0, 1);
      dwellFill.style.width = (progress * 100).toFixed(1) + '%';
      cursor.style.width = '34px';
      cursor.style.height = '34px';
      cursor.style.borderColor = progress > .75 ? 'rgba(52,211,153,.95)' : 'rgba(125,211,252,.95)';

      if(progress >= 1){
        selectArtwork(hit.art, 'dwell');
        tracking.zoomFocusArtworkId = hit.art.id;
        tracking.hoverStartTs = now + 280;
      }
    }

    function updateClock(){
      if(!tracking.startedAt){
        statTime.textContent = '00:00';
        return;
      }
      const sec = Math.max(0, Math.floor((Date.now() - tracking.startedAt) / 1000));
      const mm = String(Math.floor(sec / 60)).padStart(2, '0');
      const ss = String(sec % 60).padStart(2, '0');
      statTime.textContent = mm + ':' + ss;
    }
    setInterval(updateClock, 400);

    // ---------- Face math ----------
    function loadScript(src){
      return new Promise((resolve, reject) => {
        const old = document.querySelector('script[data-src="' + src + '"]');
        if(old){ resolve(true); return; }
        const s = document.createElement('script');
        s.src = src;
        s.async = true;
        s.dataset.src = src;
        s.onload = () => resolve(true);
        s.onerror = () => reject(new Error('Falha ao carregar ' + src));
        document.head.appendChild(s);
      });
    }

    async function loadScriptWithFallback(urls){
      let lastErr = null;
      for(const url of urls){
        try{
          await loadScript(url);
          log('Biblioteca carregada: ' + url);
          return url;
        } catch(err){
          lastErr = err;
          log('Tentativa falhou: ' + url);
        }
      }
      throw lastErr || new Error('Nenhuma URL carregou.');
    }

    function irisCenter(landmarks, ids){
      const pts = ids.map(i => landmarks[i]).filter(Boolean);
      return { x:avg(pts,'x'), y:avg(pts,'y') };
    }

    function eyeOpenness(landmarks, topIdx, bottomIdx, leftIdx, rightIdx){
      const top = landmarks[topIdx], bottom = landmarks[bottomIdx], left = landmarks[leftIdx], right = landmarks[rightIdx];
      const vertical = Math.hypot(top.x - bottom.x, top.y - bottom.y);
      const horizontal = Math.hypot(left.x - right.x, left.y - right.y);
      return vertical / Math.max(horizontal, 1e-6);
    }

    function faceMetricsFromLandmarks(landmarks){
      const nose = landmarks[1];
      const chin = landmarks[152];
      const left = landmarks[234];
      const right = landmarks[454];
      const brow = landmarks[10];

      const centerX = (left.x + right.x) / 2;
      const centerY = (brow.y + chin.y) / 2;
      const faceWidth = Math.hypot(left.x - right.x, left.y - right.y);
      const faceHeight = Math.hypot(brow.x - chin.x, brow.y - chin.y);

      // Approx yaw from nose offset relative to face center
      const yaw = clamp((nose.x - centerX) / Math.max(faceWidth * .22, 1e-6), -1, 1);
      // Approx pitch from nose vertical offset
      const pitch = clamp((nose.y - centerY) / Math.max(faceHeight * .18, 1e-6), -1, 1);

      return {
        centerX,
        centerY,
        depth:faceWidth,
        yaw,
        pitch
      };
    }

    function processBlink(landmarks){
      const leftOpen = eyeOpenness(landmarks, 159, 145, 33, 133);
      const rightOpen = eyeOpenness(landmarks, 386, 374, 362, 263);
      const openness = (leftOpen + rightOpen) / 2;
      const now = Date.now();

      if(openness < tracking.blink.threshold && !tracking.blink.closed){
        tracking.blink.closed = true;
        tracking.blink.closeTs = now;
        setBlinkStatus('Fechado');
      } else if(openness >= tracking.blink.threshold && tracking.blink.closed){
        const dur = now - tracking.blink.closeTs;
        tracking.blink.closed = false;
        setBlinkStatus('Aberto');

        if(dur >= tracking.blink.minMs && dur <= tracking.blink.maxMs){
          tracking.blink.count += 1;

          if(tracking.blink.pending && now - tracking.blink.pendingTs <= tracking.blink.doubleWindowMs){
            if(tracking.blink.pendingTimer){
              clearTimeout(tracking.blink.pendingTimer);
              tracking.blink.pendingTimer = null;
            }
            tracking.blink.pending = false;
            tracking.blink.pendingTs = 0;
            tracking.blink.lastBlinkTs = now;
            setBlinkStatus('2 piscadas');
            cycleZoom(-1, 'double_blink');
            return;
          }

          tracking.blink.pending = true;
          tracking.blink.pendingTs = now;
          tracking.blink.lastBlinkTs = now;
          setBlinkStatus('1 piscada…');

          if(tracking.blink.pendingTimer){
            clearTimeout(tracking.blink.pendingTimer);
            tracking.blink.pendingTimer = null;
          }

          tracking.blink.pendingTimer = setTimeout(() => {
            tracking.blink.pending = false;
            tracking.blink.pendingTs = 0;
            tracking.blink.pendingTimer = null;

            const hovered = getArtworkById(tracking.hoveredArtworkId) || getArtworkById(tracking.selectedArtworkId);
            if(hovered){
              selectArtwork(hovered, 'single_blink');
              tracking.zoomFocusArtworkId = hovered.id;
            }
            setBlinkStatus('1 piscada');
            cycleZoom(1, 'single_blink');
            setTimeout(() => {
              if(!tracking.blink.closed && !tracking.blink.pending){
                setBlinkStatus('Pronto');
              }
            }, 260);
          }, tracking.blink.singleWindowMs);
        }
      }
    }

    function smoothTracking(metric){
      const t = filters.smoothing;
      tracking.raw.centerX = metric.centerX;
      tracking.raw.centerY = metric.centerY;
      tracking.raw.depth = metric.depth;
      tracking.raw.yaw = metric.yaw;
      tracking.raw.pitch = metric.pitch;

      tracking.smoothed.centerX = lerp(tracking.smoothed.centerX, metric.centerX, t);
      tracking.smoothed.centerY = lerp(tracking.smoothed.centerY, metric.centerY, t);
      tracking.smoothed.depth = lerp(tracking.smoothed.depth, metric.depth, t);
      tracking.smoothed.yaw = lerp(tracking.smoothed.yaw, metric.yaw, t * .8);
      tracking.smoothed.pitch = lerp(tracking.smoothed.pitch, metric.pitch, t * .8);
    }

    function calibrateFromCurrentFace(){
      tracking.calibration.centerX = tracking.smoothed.centerX;
      tracking.calibration.centerY = tracking.smoothed.centerY;
      tracking.calibration.depth = tracking.smoothed.depth;
      tracking.calibration.yaw = tracking.smoothed.yaw;
      tracking.calibration.pitch = tracking.smoothed.pitch;
      tracking.calibrationReady = true;
      calibrationText.textContent = 'Concluída';
      permissionNote.textContent = 'Calibração facial aplicada.';
      log('Calibração facial aplicada.');
    }

    function applyTrackingToNavigation(dt){
      const cal = tracking.calibrationReady ? tracking.calibration : { centerX:.5, centerY:.5, depth:tracking.smoothed.depth || .34, yaw:0, pitch:0 };

      const dx = applyDeadzone((tracking.smoothed.centerX - cal.centerX) * 2.0, filters.deadX);
      const dy = applyDeadzone((tracking.smoothed.centerY - cal.centerY) * 1.7, 0.07);
      const depthDelta = applyDeadzone((tracking.smoothed.depth - cal.depth) * 4.2, filters.deadZ);
      const yawDelta = applyDeadzone((tracking.smoothed.yaw - cal.yaw), 0.07);
      const pitchDelta = applyDeadzone((tracking.smoothed.pitch - cal.pitch), 0.07);

      // Cursor follows face position gently. Yaw now follows the same intuitive direction as the head.
      gaze.targetX = clamp(0.5 + dx * 0.26 + yawDelta * 0.14, 0.10, 0.90);
      gaze.targetY = clamp(0.5 + dy * 0.22 + pitchDelta * 0.06, 0.14, 0.86);

      const zoomWalkFactor = tracking.zoomTarget > 0.2 ? 0.72 : 1.0;

      // Turn more subtly and naturally.
      const desiredYawVel = ((yawDelta * filters.yawGain) + (dx * 0.05)) * 0.016;
      const desiredPitchVel = (-pitchDelta * filters.pitchGain) * 0.010;

      camera.yawVel = lerp(camera.yawVel, desiredYawVel, 0.08);
      camera.pitchVel = lerp(camera.pitchVel, desiredPitchVel, 0.07);

      // Movement is mainly driven by face lateral position and depth, but much softer.
      const strafe = clamp(dx * filters.strafeGain, -0.65, 0.65);
      const forward = clamp(depthDelta * filters.depthGain, -0.75, 0.75);

      const sinY = Math.sin(camera.yaw);
      const cosY = Math.cos(camera.yaw);

      const desiredVX = (strafe * cosY + forward * sinY) * filters.walkForce * 0.032 * zoomWalkFactor;
      const desiredVZ = (-strafe * sinY + forward * cosY) * filters.walkForce * 0.032 * zoomWalkFactor;

      camera.vx = lerp(camera.vx, desiredVX, 0.07);
      camera.vz = lerp(camera.vz, desiredVZ, 0.07);

      camera.yaw = clamp(camera.yaw + camera.yawVel * dt * 60, -1.15, 1.15);
      camera.pitch = clamp(camera.pitch + camera.pitchVel * dt * 60, -0.24, 0.24);
      camera.x += camera.vx * dt * 60;
      camera.z += camera.vz * dt * 60;

      camera.yawVel *= Math.pow(filters.turnFriction, dt * 60);
      camera.pitchVel *= Math.pow(filters.turnFriction, dt * 60);
      camera.vx *= Math.pow(filters.friction, dt * 60);
      camera.vz *= Math.pow(filters.friction, dt * 60);

      camera.x = clamp(camera.x, room.minX + 0.55, room.maxX - 0.55);
      camera.z = clamp(camera.z, room.minZ + 0.35, room.maxZ - 0.8);

      const obstacles = [
        { x:-1.8, z:3.0, r:0.95 },
        { x:1.8, z:3.35, r:0.95 }
      ];
      obstacles.forEach(o => {
        const dxo = camera.x - o.x;
        const dzo = camera.z - o.z;
        const d = Math.hypot(dxo, dzo);
        if(d < o.r){
          const nx = dxo / Math.max(1e-6, d);
          const nz = dzo / Math.max(1e-6, d);
          camera.x = o.x + nx * o.r;
          camera.z = o.z + nz * o.r;
          camera.vx *= 0.28;
          camera.vz *= 0.28;
        }
      });

      const speed = Math.hypot(camera.vx, camera.vz);
      speedText.textContent = round2(speed);
      if(speed < 0.0025) setWalk('Parado');
      else if(forward > 0.04) setWalk('Frente');
      else if(forward < -0.04) setWalk('Trás');
      else if(strafe > 0.04) setWalk('Direita');
      else if(strafe < -0.04) setWalk('Esquerda');
      else setWalk('Suave');
    }

    // ---------- Camera / mouse fallback ----------
    scenePanel.addEventListener('mousemove', (ev) => {
      if(!tracking.usingMouse) return;
      const rect = scenePanel.getBoundingClientRect();
      gaze.targetX = clamp((ev.clientX - rect.left) / rect.width, .05, .95);
      gaze.targetY = clamp((ev.clientY - rect.top) / rect.height, .08, .92);

      const lookX = gaze.targetX - .5;
      const lookY = gaze.targetY - .5;
      camera.yawVel += lookX * 0.0010;
      camera.pitchVel += -lookY * 0.0006;
    });

    scenePanel.addEventListener('wheel', (ev) => {
      if(!tracking.usingMouse) return;
      ev.preventDefault();
      if(ev.deltaY < 0) cycleZoom(1);
      else cycleZoom(-1);
    }, { passive:false });

    scenePanel.addEventListener('click', () => {
      if(tracking.usingMouse){
        const hovered = getArtworkById(tracking.hoveredArtworkId);
        if(hovered){
          selectArtwork(hovered, 'mouse_click');
          tracking.zoomTarget = 0.55;
          tracking.zoomFocusArtworkId = hovered.id;
        }
      }
    });

    // ---------- Tracking start/stop ----------
    async function startTracking(){
      log('Iniciar tracking facial clicado.');
      tracking.startedAt = tracking.startedAt || Date.now();
      tracking.running = true;
      setStatus(false, 'Preparando');
      permissionNote.textContent = 'Tentando abrir webcam + tracking facial…';

      try{
        if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
          throw new Error('getUserMedia não disponível neste navegador/ambiente.');
        }

        const loadedUrl = await loadScriptWithFallback([
          'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js',
          'https://unpkg.com/@mediapipe/face_mesh/face_mesh.js'
        ]);

        tracking.stream = await navigator.mediaDevices.getUserMedia({
          video:{ width:{ideal:640}, height:{ideal:480}, facingMode:'user' },
          audio:false
        });
        video.srcObject = tracking.stream;
        await video.play();
        log('Webcam aberta.');

        tracking.faceMesh = new window.FaceMesh({
          locateFile:(file) => loadedUrl.indexOf('unpkg.com') !== -1
            ? 'https://unpkg.com/@mediapipe/face_mesh/' + file
            : 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/' + file
        });
        tracking.faceMesh.setOptions({
          maxNumFaces:1,
          refineLandmarks:true,
          minDetectionConfidence:.55,
          minTrackingConfidence:.55
        });

        tracking.faceMesh.onResults((results) => {
          if(!tracking.running) return;

          if(!results.multiFaceLandmarks || !results.multiFaceLandmarks[0]){
            setStatus(false, 'Rosto não encontrado');
            gaze.quality = .45;
            return;
          }

          const landmarks = results.multiFaceLandmarks[0];
          const metric = faceMetricsFromLandmarks(landmarks);
          smoothTracking(metric);
          processBlink(landmarks);

          if(!tracking.calibrationReady){
            tracking.calibration.centerX = tracking.smoothed.centerX;
            tracking.calibration.centerY = tracking.smoothed.centerY;
            tracking.calibration.depth = tracking.smoothed.depth;
            tracking.calibration.yaw = tracking.smoothed.yaw;
            tracking.calibration.pitch = tracking.smoothed.pitch;
          }

          const widthLeft = landmarks[234];
          const widthRight = landmarks[454];
          const eyeWidth = Math.abs(widthRight.x - widthLeft.x);
          gaze.quality = clamp(eyeWidth * 4.2, .52, .98);

          tracking.usingMouse = false;
          setMode('Webcam');
          setStatus(true, 'Tracking facial ativo');
          permissionNote.textContent = 'Tracking facial ativo. Mantenha o rosto estável e use 1 piscada aproxima e 2 piscadas rápidas afastam.';
        });

        async function mediaLoop(){
          if(!tracking.running || !tracking.faceMesh) return;
          try{
            if(video.readyState >= 2){
              await tracking.faceMesh.send({ image: video });
            }
          } catch(err){
            log('Erro no frame do MediaPipe: ' + err.message);
          }
          tracking.rafMedia = requestAnimationFrame(mediaLoop);
        }

        if(tracking.rafMedia) cancelAnimationFrame(tracking.rafMedia);
        tracking.rafMedia = requestAnimationFrame(mediaLoop);
      } catch(err){
        tracking.usingMouse = true;
        setMode('Mouse');
        setStatus(true, 'Modo mouse ativo');
        const reason = err && (err.message || err.name) ? (err.message || err.name) : String(err);
        permissionNote.textContent = 'Tracking facial não iniciou: ' + reason + '. O modo mouse ficou ativo para teste.';
        log('Falha no tracking facial: ' + reason + ' | entrando no modo mouse.');
      }
    }

    function stopTracking(){
      tracking.running = false;
      if(tracking.rafMedia) cancelAnimationFrame(tracking.rafMedia);
      tracking.rafMedia = null;
      if(tracking.stream){
        tracking.stream.getTracks().forEach(t => t.stop());
        tracking.stream = null;
      }
      video.srcObject = null;
      tracking.usingMouse = true;
      setMode('Cena ativa');
      setStatus(false, 'Tracking desligado');
      permissionNote.textContent = 'Tracking desligado. A sala continua ativa.';
      log('Tracking parado.');
    }

    function calibrateTracking(){
      if(tracking.usingMouse){
        calibrationText.textContent = 'Modo mouse';
        permissionNote.textContent = 'No modo mouse não é necessário calibrar.';
        log('Calibração ignorada no modo mouse.');
        return;
      }
      calibrateFromCurrentFace();
    }

    function clearHeatmap(){
      const rect = scenePanel.getBoundingClientRect();
      heatCtx.clearRect(0, 0, rect.width, rect.height);
      revealCtx.clearRect(0, 0, rect.width, rect.height);
      tracking.heatPoints = [];
      tracking.revealPoints = [];
      tracking.fixations = 0;
      tracking.inFixation = false;
      tracking.stableFor = 0;
      tracking.lastPointPx = null;
      statFixations.textContent = '0';
      statPoints.textContent = '0';
      log('Heatmap limpo.');
    }

    async function exportPdf(){
      log('Exportar PDF clicado.');
      const sceneImg = roomCanvas.toDataURL('image/png', 1.0);
      const heatImg = heatmapCanvas.toDataURL('image/png', 1.0);
      const miniImg = miniCanvas.toDataURL('image/png', 1.0);

      try{
        await loadScript('https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js');
        const jsPDF = window.jspdf && window.jspdf.jsPDF;
        if(!jsPDF) throw new Error('jsPDF não disponível.');

        const pdf = new jsPDF('p', 'mm', 'a4');
        let y = 16;
        pdf.setFillColor(8, 17, 31);
        pdf.rect(0, 0, 210, 297, 'F');
        pdf.setTextColor(238, 244, 255);
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(18);
        pdf.text('Relatório de tracking facial - Sala 3D', 12, y);
        y += 8;

        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(10);
        pdf.setTextColor(168, 185, 216);
        pdf.text('Gerado em: ' + new Date().toLocaleString(), 12, y);
        y += 9;

        pdf.setTextColor(238, 244, 255);
        pdf.setFontSize(11);
        pdf.text('Modo: ' + (tracking.usingMouse ? 'Mouse' : 'Webcam'), 12, y); y += 5;
        pdf.text('Amostras: ' + tracking.heatPoints.length, 12, y); y += 5;
        pdf.text('Fixações: ' + tracking.fixations, 12, y); y += 5;
        pdf.text('Obras vistas: ' + tracking.seenArtworkIds.size, 12, y); y += 5;
        pdf.text('Qualidade estimada: ' + Math.round(gaze.quality * 100) + '%', 12, y); y += 5;
        pdf.text('Zoom atual: ' + zoomText.textContent, 12, y); y += 5;
        pdf.text('Posição da câmera: x=' + round2(camera.x) + ' z=' + round2(camera.z), 12, y); y += 8;

        pdf.setFont('helvetica', 'bold');
        pdf.text('Cena e heatmap', 12, y);
        y += 3;
        pdf.addImage(sceneImg, 'PNG', 12, y, 88, 66, undefined, 'FAST');
        pdf.addImage(heatImg, 'PNG', 108, y, 88, 66, undefined, 'FAST');
        y += 72;
        pdf.addImage(miniImg, 'PNG', 12, y, 38, 38, undefined, 'FAST');

        pdf.setFont('helvetica', 'bold');
        pdf.text('Seleções registradas', 58, y + 4);
        pdf.setFont('helvetica', 'normal');
        let yy = y + 10;
        if(!tracking.selections.length){
          pdf.text('Nenhuma seleção registrada.', 58, yy);
        } else {
          const grouped = {};
          tracking.selections.forEach(s => {
            grouped[s.id] = grouped[s.id] || { title:s.title, count:0 };
            grouped[s.id].count += 1;
          });
          Object.keys(grouped).forEach(id => {
            pdf.text('• ' + grouped[id].title + ' (' + grouped[id].count + ')', 58, yy);
            yy += 5;
          });
        }

        pdf.save('relatorio_tracking_facial_sala3d.pdf');
        log('PDF exportado.');
      } catch(err){
        log('Falha ao exportar PDF: ' + err.message);
        permissionNote.textContent = 'Falha ao exportar PDF: ' + err.message;
      }
    }

    // ---------- Animation ----------
    function tick(now){
      requestAnimationFrame(tick);
      const currentTs = Date.now();
      const dt = 1 / 60;

      if(!tracking.startedAt) tracking.startedAt = currentTs;

      // Smooth cursor movement
      gaze.x = lerp(gaze.x, gaze.targetX, 0.16);
      gaze.y = lerp(gaze.y, gaze.targetY, 0.16);
      updateCursor();

      if(!tracking.usingMouse && tracking.running){
        applyTrackingToNavigation(dt);
      } else {
        // mouse-mode damping
        camera.yawVel *= 0.92;
        camera.pitchVel *= 0.88;
        camera.yaw = clamp(camera.yaw + camera.yawVel, -1.3, 1.3);
        camera.pitch = clamp(camera.pitch + camera.pitchVel, -0.35, 0.35);
      }

      drawRoom();
      drawReveal();
      drawMiniMap();

      if(tracking.running || tracking.usingMouse){
        updateHoverAndDwell(now);
        if(currentTs - tracking.lastSampleTs >= tracking.sampleIntervalMs){
          tracking.lastSampleTs = currentTs;
          addHeatPoint(gaze.x, gaze.y);
        }
      }

      if(!tracking.hoveredArtworkId){
        cursor.style.width = '28px';
        cursor.style.height = '28px';
        cursor.style.borderColor = 'rgba(255,255,255,.95)';
      }
    }

    // ---------- Events ----------
    document.getElementById('startBtn').addEventListener('click', startTracking);
    document.getElementById('stopBtn').addEventListener('click', stopTracking);
    document.getElementById('calibrateBtn').addEventListener('click', calibrateTracking);
    document.getElementById('resetHeatBtn').addEventListener('click', clearHeatmap);
    document.getElementById('resetCamBtn').addEventListener('click', resetCamera);
    document.getElementById('exportPdfBtn').addEventListener('click', exportPdf);

    window.addEventListener('resize', resizeCanvases);

    // ---------- Init ----------
    resizeCanvases();
    buildArtworkList();
    updateSelectedPanel(null);
    calibrationText.textContent = 'Pendente';
    zoomText.textContent = 'Normal';
    setMode('Cena ativa');
    setBlinkCount(0);
    setWalk('Parado');
    setStatus(true, 'Cena carregada');
    requestAnimationFrame(tick);
    log('Sala desenhada com sucesso.');
  })();
  </script>
</div>
"""

components.html(HTML_APP, height=1400, scrolling=True)
