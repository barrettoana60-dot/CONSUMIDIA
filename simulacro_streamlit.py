import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sala 3D com tracking ocular", layout="wide")

st.title("Sala 3D com tracking ocular, dwell-click, heatmap e PDF")
st.caption("Versão corrigida: os botões ficam ativos dentro do componente, com carregamento dinâmico das bibliotecas e painel de log para depuração.")

HTML_APP = r"""
<div id="eye-room-root">
  <style>
    :root {
      --bg: #07111f;
      --panel: rgba(11, 18, 35, 0.88);
      --panel-2: rgba(20, 30, 52, 0.92);
      --border: rgba(255,255,255,0.08);
      --text: #eef4ff;
      --muted: #a8b9d8;
      --accent: #7dd3fc;
      --accent-2: #c084fc;
      --ok: #34d399;
      --warn: #fbbf24;
      --danger: #fb7185;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: transparent; }
    #eye-room-root {
      width: 100%;
      min-height: 1100px;
      background:
        radial-gradient(circle at top, rgba(81, 120, 255, 0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(194, 120, 255, 0.12), transparent 24%),
        linear-gradient(180deg, #06101c 0%, #040812 100%);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 24px;
      padding: 18px;
      color: var(--text);
      overflow: hidden;
      position: relative;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      margin-bottom: 16px;
    }
    .headline h2 {
      margin: 0;
      font-size: 26px;
      font-weight: 800;
      letter-spacing: 0.2px;
    }
    .headline p {
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 780px;
      line-height: 1.45;
      font-size: 14px;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }
    .btn {
      border: 1px solid rgba(255,255,255,0.1);
      background: linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0.04));
      color: var(--text);
      padding: 10px 14px;
      border-radius: 14px;
      font-weight: 700;
      cursor: pointer;
      transition: 0.2s ease;
      box-shadow: 0 8px 22px rgba(0,0,0,0.18);
      user-select: none;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(125, 211, 252, 0.45); }
    .btn.primary {
      background: linear-gradient(180deg, rgba(125,211,252,0.28), rgba(125,211,252,0.12));
      border-color: rgba(125,211,252,0.35);
    }
    .btn.warn {
      background: linear-gradient(180deg, rgba(251,191,36,0.25), rgba(251,191,36,0.08));
      border-color: rgba(251,191,36,0.35);
    }
    .btn.subtle {
      background: linear-gradient(180deg, rgba(192,132,252,0.18), rgba(192,132,252,0.06));
      border-color: rgba(192,132,252,0.3);
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.72fr) minmax(320px, 0.78fr);
      gap: 16px;
      min-height: 920px;
    }
    .scene-panel, .sidebar {
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
      border: 1px solid var(--border);
      border-radius: 22px;
      overflow: hidden;
      position: relative;
      backdrop-filter: blur(18px);
    }
    .scene-panel { min-height: 880px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 18px 50px rgba(0,0,0,0.25); }
    #scene-shell { position: absolute; inset: 0; background: radial-gradient(circle at center, rgba(255,255,255,0.03), transparent 60%); }
    #scene, #overlay-shell { position: absolute; inset: 0; }
    #heatmap, #reveal {
      position: absolute; inset: 0; width: 100%; height: 100%;
      pointer-events: none; z-index: 2;
    }
    #gaze-cursor {
      position: absolute; width: 28px; height: 28px; border: 2px solid rgba(255,255,255,0.95);
      border-radius: 999px; box-shadow: 0 0 0 8px rgba(125,211,252,0.16), 0 0 24px rgba(125,211,252,0.35);
      transform: translate(-50%, -50%); pointer-events: none; z-index: 5; left: 50%; top: 50%;
    }
    #gaze-cursor::after {
      content: ""; position: absolute; inset: 6px; border-radius: 999px; background: rgba(255,255,255,0.85);
    }
    .corner-chip {
      position: absolute; top: 18px; left: 18px; z-index: 6; display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 12px; border-radius: 999px; background: rgba(9, 16, 30, 0.72);
      border: 1px solid rgba(255,255,255,0.08); font-size: 13px; color: var(--muted);
    }
    .dot { width: 10px; height: 10px; border-radius: 999px; background: var(--danger); box-shadow: 0 0 18px rgba(251,113,133,0.45); }
    .dot.on { background: var(--ok); box-shadow: 0 0 18px rgba(52,211,153,0.45); }
    .dwell-meter {
      position: absolute; top: 18px; right: 18px; z-index: 6; width: 160px; padding: 12px; border-radius: 16px;
      background: rgba(9, 16, 30, 0.74); border: 1px solid rgba(255,255,255,0.08); backdrop-filter: blur(14px);
    }
    .dwell-meter .label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
    .bar { width: 100%; height: 10px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }
    .bar > div { width: 0%; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7dd3fc 0%, #c084fc 100%); }
    #permission-note {
      position: absolute; left: 18px; bottom: 18px; z-index: 6; padding: 10px 14px; border-radius: 14px;
      background: rgba(10, 18, 35, 0.88); border: 1px solid rgba(255,255,255,0.08);
      color: var(--muted); font-size: 13px; max-width: 520px; line-height: 1.45;
    }
    .sidebar { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
    .card {
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; padding: 14px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .card h3 { margin: 0 0 10px; font-size: 15px; letter-spacing: 0.2px; }
    #video {
      width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.08); background: #030712; transform: scaleX(-1);
    }
    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .stat {
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
      border-radius: 16px; padding: 12px;
    }
    .stat .k { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .stat .v { font-size: 22px; font-weight: 800; }
    .meta-line {
      display: flex; justify-content: space-between; gap: 10px;
      border-bottom: 1px dashed rgba(255,255,255,0.08); padding: 8px 0; color: var(--muted); font-size: 13px;
    }
    .meta-line:last-child { border-bottom: none; }
    .meta-line strong { color: var(--text); font-size: 13px; }
    #selected-title { font-size: 20px; margin: 0 0 6px; }
    #selected-artist { color: #7dd3fc; margin-bottom: 10px; font-weight: 700; }
    #selected-description { color: var(--muted); line-height: 1.5; font-size: 13.5px; }
    #artwork-list { display: grid; gap: 10px; max-height: 260px; overflow: auto; }
    .art-row {
      display: grid; grid-template-columns: 14px 1fr auto; gap: 10px; align-items: center;
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
      border-radius: 16px; padding: 12px; cursor: pointer;
    }
    .art-bullet { width: 14px; height: 14px; border-radius: 999px; }
    .art-title { font-weight: 800; margin-bottom: 3px; }
    .art-sub { color: var(--muted); font-size: 12.5px; }
    .badge {
      font-size: 11px; font-weight: 800; color: #dbeafe;
      background: rgba(125,211,252,0.14); border: 1px solid rgba(125,211,252,0.22);
      padding: 6px 9px; border-radius: 999px;
    }
    #logBox {
      min-height: 120px; max-height: 180px; overflow: auto; border-radius: 12px; padding: 10px;
      background: rgba(3, 7, 18, 0.72); border: 1px solid rgba(255,255,255,0.08);
      color: #a8b9d8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.4;
      white-space: pre-wrap;
    }
    .small-note { color: var(--muted); font-size: 12px; line-height: 1.4; }
    @media (max-width: 1080px) {
      .layout { grid-template-columns: 1fr; }
      .scene-panel { min-height: 640px; }
      #eye-room-root { min-height: 1400px; }
      .topbar { grid-template-columns: 1fr; }
      .controls { justify-content: flex-start; }
    }
  </style>

  <div class="topbar">
    <div class="headline">
      <h2>Sala 3D guiada pelo olhar</h2>
      <p>Agora os botões ficam independentes dos imports do Three.js. Se alguma biblioteca falhar, o painel de log mostra o motivo.</p>
    </div>
    <div class="controls">
      <button class="btn primary" id="startBtn">Iniciar tracking</button>
      <button class="btn warn" id="calibrateBtn">Calibrar olhar</button>
      <button class="btn subtle" id="resetHeatBtn">Limpar heatmap</button>
      <button class="btn" id="exportPdfBtn">Exportar PDF</button>
      <button class="btn" id="stopBtn">Parar</button>
    </div>
  </div>

  <div class="layout">
    <div class="scene-panel">
      <div id="scene-shell">
        <div id="scene"></div>
        <canvas id="heatmap"></canvas>
        <canvas id="reveal"></canvas>
        <div id="gaze-cursor"></div>
        <div class="corner-chip"><span id="statusDot" class="dot"></span><span id="statusText">Aguardando</span></div>
        <div class="dwell-meter">
          <div class="label">Progresso do clique por permanência</div>
          <div class="bar"><div id="dwellFill"></div></div>
        </div>
        <div id="permission-note">Clique em “Iniciar tracking”. Se der erro, veja o painel “Log do sistema”.</div>
      </div>
    </div>

    <div class="sidebar">
      <div class="card">
        <h3>Prévia da câmera</h3>
        <video id="video" autoplay playsinline muted></video>
        <div class="small-note" style="margin-top:8px">Se a câmera não abrir, confirme a permissão do navegador e use HTTPS.</div>
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
      </div>

      <div class="card">
        <h3>Obra selecionada</h3>
        <div id="selected-title">Nenhuma obra selecionada</div>
        <div id="selected-artist">Olhe para uma obra por cerca de 1,2 s</div>
        <div id="selected-description">A ficha da obra aparece aqui quando o dwell-click termina.</div>
      </div>

      <div class="card">
        <h3>Obras da sala</h3>
        <div id="artwork-list"></div>
      </div>

      <div class="card">
        <h3>Log do sistema</h3>
        <div id="logBox">Carregando interface…</div>
      </div>
    </div>
  </div>

  <script>
    (function() {
      const logBox = document.getElementById('logBox');
      function log(msg) {
        const line = '[' + new Date().toLocaleTimeString() + '] ' + msg;
        console.log(line);
        logBox.textContent += '\\n' + line;
        logBox.scrollTop = logBox.scrollHeight;
      }
      window.__eyeRoomLog = log;
      window.addEventListener('error', function(e) {
        log('ERRO JS: ' + (e.message || 'desconhecido'));
      });
      window.addEventListener('unhandledrejection', function(e) {
        log('PROMISE REJECTION: ' + (e.reason && e.reason.message ? e.reason.message : String(e.reason)));
      });
      logBox.textContent = 'Interface carregada.';
    })();
  </script>

  <script>
    (function() {
      const log = window.__eyeRoomLog || console.log;

      const sceneHost = document.getElementById('scene');
      const heatmapCanvas = document.getElementById('heatmap');
      const revealCanvas = document.getElementById('reveal');
      const gazeCursor = document.getElementById('gaze-cursor');
      const statusDot = document.getElementById('statusDot');
      const statusText = document.getElementById('statusText');
      const permissionNote = document.getElementById('permission-note');
      const videoElement = document.getElementById('video');
      const dwellFill = document.getElementById('dwellFill');
      const hoverText = document.getElementById('hoverText');
      const qualityText = document.getElementById('qualityText');
      const calibrationText = document.getElementById('calibrationText');
      const selectedTitle = document.getElementById('selected-title');
      const selectedArtist = document.getElementById('selected-artist');
      const selectedDescription = document.getElementById('selected-description');
      const artworkList = document.getElementById('artwork-list');
      const statTime = document.getElementById('statTime');
      const statFixations = document.getElementById('statFixations');
      const statPoints = document.getElementById('statPoints');
      const statArtworks = document.getElementById('statArtworks');

      const heatCtx = heatmapCanvas.getContext('2d');
      const revealCtx = revealCanvas.getContext('2d');

      const roomState = {
        running: false,
        calibrated: false,
        startTs: null,
        hoverStart: 0,
        hoveredArtworkId: null,
        selectedArtwork: null,
        dwellMs: 1200,
        sampleIntervalMs: 85,
        lastSampleTs: 0,
        totalFrames: 0,
        trackedFrames: 0,
        sessionSelections: [],
        revealPoints: [],
        heatPoints: [],
        movementPoints: [],
        fixations: 0,
        inFixation: false,
        stableFor: 0,
        lastPoint: null,
        calibrationMap: { minX: 0.28, maxX: 0.72, minY: 0.30, maxY: 0.70 },
      };

      const gaze = {
        rawX: 0.5, rawY: 0.5, x: 0.5, y: 0.5, smoothX: 0.5, smoothY: 0.5, quality: 0
      };

      const artworks = [
        { id:'obra_01', title:'Memórias de Superfície', artist:'Lívia Andrade', year:'2024', wall:'frente', position:{x:-2.8,y:1.7,z:-4.4}, color:'#ef4444', description:'Pintura em camadas com relevo cromático.' },
        { id:'obra_02', title:'Campo Sensível', artist:'Diego Marins', year:'2025', wall:'frente', position:{x:0.0,y:1.8,z:-4.4}, color:'#22c55e', description:'Trabalho digital com profundidade simulada.' },
        { id:'obra_03', title:'Eco de Matéria', artist:'Marina Teles', year:'2026', wall:'frente', position:{x:2.8,y:1.7,z:-4.4}, color:'#f59e0b', description:'Objeto expandido que sugere microscopia e holografia.' },
        { id:'obra_04', title:'Horizonte Índigo', artist:'Ciro Menezes', year:'2023', wall:'esquerda', position:{x:-4.4,y:1.8,z:-0.6}, color:'#8b5cf6', rotationY: Math.PI / 2, description:'Composição geométrica com profundidade visual.' },
        { id:'obra_05', title:'Traço Latente', artist:'Rafaela Costa', year:'2022', wall:'direita', position:{x:4.4,y:1.75,z:0.8}, color:'#06b6d4', rotationY: -Math.PI / 2, description:'Pintura com leitura periférica e foco seletivo.' },
      ];

      const seenArtworkIds = new Set();
      const artworkObjects = new Map();

      let renderer = null;
      let scene = null;
      let camera = null;
      let raycaster = null;
      let pointer = null;
      let cameraAnchor = null;
      let targetX = 0;
      let targetY = 1.6;
      let faceMesh = null;
      let cameraStream = null;
      let processingLoopId = null;
      let sceneReady = false;

      function setStatus(on, text) {
        statusDot.classList.toggle('on', !!on);
        statusText.textContent = text;
      }

      function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
      function lerp(a, b, t) { return a + (b - a) * t; }
      function avg(points, key) { return points.reduce((s, p) => s + p[key], 0) / Math.max(1, points.length); }

      function irisCenter(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return { x: avg(pts, 'x'), y: avg(pts, 'y') };
      }
      function eyeBox(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return { minX: Math.min(...pts.map((p) => p.x)), maxX: Math.max(...pts.map((p) => p.x)), minY: Math.min(...pts.map((p) => p.y)), maxY: Math.max(...pts.map((p) => p.y)) };
      }
      function rawToScreen(rx, ry) {
        const c = roomState.calibrationMap;
        const nx = clamp((rx - c.minX) / Math.max(0.02, c.maxX - c.minX), 0, 1);
        const ny = clamp((ry - c.minY) / Math.max(0.02, c.maxY - c.minY), 0, 1);
        return { x: clamp(0.04 + nx * 0.92, 0.02, 0.98), y: clamp(0.04 + ny * 0.92, 0.02, 0.98) };
      }

      function updateGazeFromLandmarks(landmarks) {
        const leftIris = irisCenter(landmarks, [468, 469, 470, 471, 472]);
        const rightIris = irisCenter(landmarks, [473, 474, 475, 476, 477]);
        const leftEye = eyeBox(landmarks, [33, 133, 159, 145, 160, 144]);
        const rightEye = eyeBox(landmarks, [362, 263, 386, 374, 385, 380]);

        const lrx = clamp((leftIris.x - leftEye.minX) / Math.max(0.001, leftEye.maxX - leftEye.minX), 0, 1);
        const rrx = clamp((rightIris.x - rightEye.minX) / Math.max(0.001, rightEye.maxX - rightEye.minX), 0, 1);
        const lry = clamp((leftIris.y - leftEye.minY) / Math.max(0.001, leftEye.maxY - leftEye.minY), 0, 1);
        const rry = clamp((rightIris.y - rightEye.minY) / Math.max(0.001, rightEye.maxY - rightEye.minY), 0, 1);

        gaze.rawX = (lrx + rrx) * 0.5;
        gaze.rawY = (lry + rry) * 0.5;
        const mapped = rawToScreen(gaze.rawX, gaze.rawY);
        gaze.x = mapped.x;
        gaze.y = mapped.y;
        gaze.smoothX = lerp(gaze.smoothX, gaze.x, 0.18);
        gaze.smoothY = lerp(gaze.smoothY, gaze.y, 0.18);

        const eyeWidthDiff = Math.abs((leftEye.maxX - leftEye.minX) - (rightEye.maxX - rightEye.minX));
        gaze.quality = clamp(1 - eyeWidthDiff * 10, 0.42, 0.98);
      }

      function moveCursor() {
        gazeCursor.style.left = (gaze.smoothX * 100) + '%';
        gazeCursor.style.top = (gaze.smoothY * 100) + '%';
      }

      function drawReveal() {
        const rect = sceneHost.getBoundingClientRect();
        revealCtx.clearRect(0, 0, rect.width, rect.height);
        revealCtx.fillStyle = 'rgba(4, 8, 18, 0.62)';
        revealCtx.fillRect(0, 0, rect.width, rect.height);
        revealCtx.globalCompositeOperation = 'destination-out';
        roomState.revealPoints.forEach((p) => {
          const radius = 90 + p.life * 70;
          const grad = revealCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
          grad.addColorStop(0, 'rgba(255,255,255,' + (0.16 * p.life) + ')');
          grad.addColorStop(0.4, 'rgba(255,255,255,' + (0.10 * p.life) + ')');
          grad.addColorStop(1, 'rgba(255,255,255,0)');
          revealCtx.fillStyle = grad;
          revealCtx.beginPath();
          revealCtx.arc(p.x, p.y, radius, 0, Math.PI * 2);
          revealCtx.fill();
          p.life *= 0.988;
        });
        roomState.revealPoints = roomState.revealPoints.filter((p) => p.life > 0.08);
        revealCtx.globalCompositeOperation = 'source-over';
      }

      function addHeatPoint(x, y) {
        const rect = sceneHost.getBoundingClientRect();
        const px = x * rect.width;
        const py = y * rect.height;
        roomState.heatPoints.push({ x: px, y: py, ts: Date.now() });
        roomState.movementPoints.push({ x: px, y: py, ts: Date.now() });
        if (roomState.heatPoints.length > 4000) roomState.heatPoints.shift();

        const g = heatCtx.createRadialGradient(px, py, 3, px, py, 32);
        g.addColorStop(0, 'rgba(255, 64, 64, 0.16)');
        g.addColorStop(0.35, 'rgba(255, 191, 0, 0.12)');
        g.addColorStop(0.68, 'rgba(34, 197, 94, 0.08)');
        g.addColorStop(1, 'rgba(34, 197, 94, 0.00)');
        heatCtx.fillStyle = g;
        heatCtx.beginPath();
        heatCtx.arc(px, py, 32, 0, Math.PI * 2);
        heatCtx.fill();

        roomState.revealPoints.push({ x: px, y: py, life: 1 });
        if (roomState.revealPoints.length > 240) roomState.revealPoints.shift();

        roomState.trackedFrames += 1;
        statPoints.textContent = String(roomState.heatPoints.length);
        qualityText.textContent = Math.round(gaze.quality * 100) + '%';

        if (roomState.lastPoint) {
          const dx = px - roomState.lastPoint.x;
          const dy = py - roomState.lastPoint.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 28) {
            roomState.stableFor += roomState.sampleIntervalMs;
            if (roomState.stableFor >= 260 && !roomState.inFixation) {
              roomState.fixations += 1;
              roomState.inFixation = true;
              statFixations.textContent = String(roomState.fixations);
            }
          } else {
            roomState.stableFor = 0;
            roomState.inFixation = false;
          }
        }
        roomState.lastPoint = { x: px, y: py };
      }

      function clearHeatmap() {
        const rect = sceneHost.getBoundingClientRect();
        heatCtx.clearRect(0, 0, rect.width, rect.height);
        revealCtx.clearRect(0, 0, rect.width, rect.height);
        roomState.heatPoints = [];
        roomState.revealPoints = [];
        roomState.movementPoints = [];
        roomState.fixations = 0;
        roomState.inFixation = false;
        roomState.stableFor = 0;
        roomState.lastPoint = null;
        statFixations.textContent = '0';
        statPoints.textContent = '0';
        drawReveal();
        log('Heatmap limpo.');
      }

      function updateSelectedPanel(art) {
        if (!art) {
          selectedTitle.textContent = 'Nenhuma obra selecionada';
          selectedArtist.textContent = 'Olhe para uma obra por cerca de 1,2 s';
          selectedDescription.textContent = 'A ficha da obra aparece aqui quando o dwell-click termina.';
          return;
        }
        selectedTitle.textContent = art.title;
        selectedArtist.textContent = art.artist + ' · ' + art.year + ' · parede ' + art.wall;
        selectedDescription.textContent = art.description;
      }

      function selectArtwork(artId, manual) {
        const art = artworks.find((a) => a.id === artId);
        if (!art) return;
        roomState.selectedArtwork = art;
        updateSelectedPanel(art);
        if (!seenArtworkIds.has(art.id)) {
          seenArtworkIds.add(art.id);
          statArtworks.textContent = String(seenArtworkIds.size);
        }
        roomState.sessionSelections.push({ id: art.id, title: art.title, ts: Date.now(), manual: !!manual });
        const obj = artworkObjects.get(art.id);
        if (obj && obj.children[1] && obj.children[1].material) {
          obj.children[1].material.emissive = new THREE.Color(0x22334a);
          setTimeout(() => {
            try { obj.children[1].material.emissive = new THREE.Color(0x000000); } catch(e){}
          }, 420);
        }
      }

      function buildArtworkList() {
        artworkList.innerHTML = '';
        artworks.forEach((art) => {
          const row = document.createElement('div');
          row.className = 'art-row';
          row.innerHTML = '<div class="art-bullet" style="background:' + art.color + '"></div>' +
                          '<div><div class="art-title">' + art.title + '</div><div class="art-sub">' + art.artist + ' · ' + art.year + '</div></div>' +
                          '<div class="badge">' + art.wall + '</div>';
          row.addEventListener('click', () => selectArtwork(art.id, true));
          artworkList.appendChild(row);
        });
      }

      function resizeCanvases() {
        const rect = sceneHost.getBoundingClientRect();
        const w = Math.max(1, rect.width);
        const h = Math.max(1, rect.height);
        [heatmapCanvas, revealCanvas].forEach((canvas) => {
          canvas.width = Math.floor(w * window.devicePixelRatio);
          canvas.height = Math.floor(h * window.devicePixelRatio);
          canvas.style.width = w + 'px';
          canvas.style.height = h + 'px';
        });
        heatCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        revealCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        if (renderer && camera) {
          renderer.setSize(w, h);
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
        }
        drawReveal();
      }

      function updateSessionClock() {
        if (!roomState.startTs) {
          statTime.textContent = '00:00';
          return;
        }
        const sec = Math.max(0, Math.floor((Date.now() - roomState.startTs) / 1000));
        const mm = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss = String(sec % 60).padStart(2, '0');
        statTime.textContent = mm + ':' + ss;
      }
      setInterval(updateSessionClock, 400);

      function updateHoverAndDwell(now) {
        if (!raycaster || !camera) return;
        pointer.x = gaze.smoothX * 2 - 1;
        pointer.y = -(gaze.smoothY * 2 - 1);
        raycaster.setFromCamera(pointer, camera);
        const objects = Array.from(artworkObjects.values());
        const hits = raycaster.intersectObjects(objects, true);

        artworkObjects.forEach((group) => {
          const frame = group.children[0];
          if (frame && frame.material && frame.material.emissive) frame.material.emissive = new THREE.Color(0x000000);
        });

        let hoveredArt = null;
        for (let i = 0; i < hits.length; i++) {
          let obj = hits[i].object;
          while (obj && !(obj.userData && obj.userData.isArtwork)) obj = obj.parent;
          if (obj && obj.userData && obj.userData.isArtwork) {
            hoveredArt = obj.userData;
            break;
          }
        }

        if (!hoveredArt) {
          roomState.hoveredArtworkId = null;
          roomState.hoverStart = now;
          dwellFill.style.width = '0%';
          hoverText.textContent = 'Nenhum';
          gazeCursor.style.width = '28px';
          gazeCursor.style.height = '28px';
          gazeCursor.style.borderColor = 'rgba(255,255,255,0.95)';
          return;
        }

        hoverText.textContent = hoveredArt.title;
        const hoveredObj = artworkObjects.get(hoveredArt.id);
        if (hoveredObj && hoveredObj.children[0] && hoveredObj.children[0].material) {
          hoveredObj.children[0].material.emissive = new THREE.Color(0x1f3a55);
        }

        if (roomState.hoveredArtworkId !== hoveredArt.id) {
          roomState.hoveredArtworkId = hoveredArt.id;
          roomState.hoverStart = now;
        }
        const elapsed = now - roomState.hoverStart;
        const progress = clamp(elapsed / roomState.dwellMs, 0, 1);
        dwellFill.style.width = (progress * 100).toFixed(1) + '%';
        gazeCursor.style.width = '34px';
        gazeCursor.style.height = '34px';
        gazeCursor.style.borderColor = progress > 0.75 ? 'rgba(52,211,153,0.95)' : 'rgba(125,211,252,0.95)';

        if (elapsed >= roomState.dwellMs) {
          selectArtwork(hoveredArt.id, false);
          roomState.hoverStart = now + 260;
        }
      }

      function loadScriptOnce(src, globalName) {
        return new Promise((resolve, reject) => {
          if (globalName && window[globalName]) {
            resolve(window[globalName]);
            return;
          }
          const existing = document.querySelector('script[data-src="' + src + '"]');
          if (existing) {
            existing.addEventListener('load', () => resolve(globalName ? window[globalName] : true), { once: true });
            existing.addEventListener('error', () => reject(new Error('Falha ao carregar ' + src)), { once: true });
            return;
          }
          const s = document.createElement('script');
          s.src = src;
          s.async = true;
          s.dataset.src = src;
          s.onload = () => resolve(globalName ? window[globalName] : true);
          s.onerror = () => reject(new Error('Falha ao carregar ' + src));
          document.head.appendChild(s);
        });
      }

      async function ensureCoreLibraries() {
        log('Carregando Three.js…');
        await loadScriptOnce('https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.min.js', 'THREE');
        log('Three.js OK.');
      }

      async function ensureTrackingLibraries() {
        log('Carregando MediaPipe Face Mesh…');
        await loadScriptOnce('https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js', 'FaceMesh');
        log('MediaPipe OK.');
      }

      async function ensurePdfLibrary() {
        if (window.jspdf && window.jspdf.jsPDF) return;
        log('Carregando jsPDF…');
        await loadScriptOnce('https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js');
        log('jsPDF OK.');
      }

      function initScene() {
        if (sceneReady) return;
        if (!window.THREE) throw new Error('Three.js não está disponível.');
        log('Inicializando cena 3D…');

        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        sceneHost.innerHTML = '';
        sceneHost.appendChild(renderer.domElement);

        scene = new THREE.Scene();
        scene.fog = new THREE.Fog(0x07111f, 10, 20);
        scene.background = new THREE.Color(0x07111f);

        camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
        camera.position.set(0, 1.7, 8.2);

        raycaster = new THREE.Raycaster();
        pointer = new THREE.Vector2(0, 0);
        cameraAnchor = new THREE.Vector3(0, 1.6, 8.2);

        const ambient = new THREE.AmbientLight(0xbfdcff, 0.7);
        scene.add(ambient);

        const key = new THREE.SpotLight(0xffffff, 2.8, 30, Math.PI / 7, 0.35, 1.6);
        key.position.set(0, 5.5, 4);
        key.castShadow = true;
        key.shadow.mapSize.width = 1024;
        key.shadow.mapSize.height = 1024;
        scene.add(key);
        scene.add(key.target);
        window.__keyLight = key;

        const fill = new THREE.PointLight(0x7dd3fc, 1.1, 18);
        fill.position.set(-3.5, 3.2, 3.2);
        scene.add(fill);

        const fill2 = new THREE.PointLight(0xc084fc, 0.95, 18);
        fill2.position.set(3.5, 3.2, 2.8);
        scene.add(fill2);

        const floorMat = new THREE.MeshStandardMaterial({ color: 0x192434, roughness: 0.94, metalness: 0.04 });
        const floor = new THREE.Mesh(new THREE.PlaneGeometry(12, 12), floorMat);
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        scene.add(floor);

        const wallMat = new THREE.MeshStandardMaterial({ color: 0x101827, roughness: 0.92, metalness: 0.02, side: THREE.DoubleSide });
        const ceilingMat = new THREE.MeshStandardMaterial({ color: 0x0c1424, roughness: 0.96, metalness: 0.01, side: THREE.DoubleSide });

        const backWall = new THREE.Mesh(new THREE.PlaneGeometry(12, 5.2), wallMat);
        backWall.position.set(0, 2.6, -4.8);
        scene.add(backWall);

        const leftWall = new THREE.Mesh(new THREE.PlaneGeometry(9.6, 5.2), wallMat);
        leftWall.position.set(-4.8, 2.6, 0);
        leftWall.rotation.y = Math.PI / 2;
        scene.add(leftWall);

        const rightWall = new THREE.Mesh(new THREE.PlaneGeometry(9.6, 5.2), wallMat);
        rightWall.position.set(4.8, 2.6, 0);
        rightWall.rotation.y = -Math.PI / 2;
        scene.add(rightWall);

        const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(12, 12), ceilingMat);
        ceiling.position.set(0, 5.2, 0);
        ceiling.rotation.x = Math.PI / 2;
        scene.add(ceiling);

        const pedestalGeo = new THREE.CylinderGeometry(0.55, 0.62, 1.05, 32);
        const pedestalMat = new THREE.MeshStandardMaterial({ color: 0xe5e7eb, roughness: 0.55, metalness: 0.2 });
        [[-1.8, 0.52, 1.25], [1.8, 0.52, 1.6]].forEach(([x, y, z], i) => {
          const ped = new THREE.Mesh(pedestalGeo, pedestalMat);
          ped.position.set(x, y, z);
          ped.castShadow = true;
          scene.add(ped);
          const orb = new THREE.Mesh(
            new THREE.IcosahedronGeometry(0.33 + i * 0.06, 1),
            new THREE.MeshStandardMaterial({ color: i === 0 ? 0x7dd3fc : 0xc084fc, roughness: 0.35, metalness: 0.45 })
          );
          orb.position.set(x, 1.45, z);
          orb.castShadow = true;
          scene.add(orb);
        });

        function createArtworkMesh(art) {
          const group = new THREE.Group();
          group.position.set(art.position.x, art.position.y, art.position.z);
          group.rotation.y = art.rotationY || 0;
          group.userData = Object.assign({}, art, { isArtwork: true });

          const frame = new THREE.Mesh(
            new THREE.BoxGeometry(1.8, 1.35, 0.12),
            new THREE.MeshStandardMaterial({ color: 0x5b4a36, roughness: 0.5, metalness: 0.24, emissive: new THREE.Color(0x000000) })
          );
          frame.castShadow = true;
          group.add(frame);

          const artCanvas = document.createElement('canvas');
          artCanvas.width = 800;
          artCanvas.height = 560;
          const ctx = artCanvas.getContext('2d');
          const grad = ctx.createLinearGradient(0, 0, artCanvas.width, artCanvas.height);
          grad.addColorStop(0, art.color);
          grad.addColorStop(1, '#0f172a');
          ctx.fillStyle = grad;
          ctx.fillRect(0, 0, artCanvas.width, artCanvas.height);
          ctx.strokeStyle = 'rgba(255,255,255,0.22)';
          ctx.lineWidth = 4;
          for (let i = 0; i < 14; i++) {
            ctx.beginPath();
            ctx.moveTo(Math.random() * artCanvas.width, 0);
            ctx.lineTo(Math.random() * artCanvas.width, artCanvas.height);
            ctx.stroke();
          }
          const artTexture = new THREE.CanvasTexture(artCanvas);
          const painting = new THREE.Mesh(
            new THREE.PlaneGeometry(1.48, 1.02),
            new THREE.MeshStandardMaterial({ map: artTexture, roughness: 0.72, metalness: 0.06, emissive: new THREE.Color(0x000000) })
          );
          painting.position.z = 0.07;
          group.add(painting);

          scene.add(group);
          artworkObjects.set(art.id, group);
        }

        artworks.forEach(createArtworkMesh);
        resizeCanvases();
        sceneReady = true;
        log('Cena 3D pronta.');
      }

      function animate(now) {
        requestAnimationFrame(animate);
        if (!sceneReady) return;

        const dx = gaze.smoothX - 0.5;
        const dy = gaze.smoothY - 0.5;
        cameraAnchor.x = clamp(cameraAnchor.x + dx * 0.016, -2.9, 2.9);
        cameraAnchor.y = clamp(1.58 - dy * 1.05, 1.1, 2.2);
        camera.position.lerp(cameraAnchor, 0.08);

        targetX = lerp(targetX, dx * 3.4, 0.08);
        targetY = lerp(targetY, 1.55 - dy * 2.1, 0.08);
        camera.lookAt(targetX, targetY, -0.8 + Math.abs(dx) * 0.2);

        if (window.__keyLight) {
          window.__keyLight.position.x = lerp(window.__keyLight.position.x, dx * 3.8, 0.08);
          window.__keyLight.target.position.set(dx * 4.4, 1.5 - dy * 1.9, -1.5);
        }

        artworkObjects.forEach((group, idx) => {
          group.rotation.z = Math.sin(now * 0.0005 + idx) * 0.01;
        });

        if (roomState.running) updateHoverAndDwell(now);
        drawReveal();
        moveCursor();
        renderer.render(scene, camera);
      }

      async function calibrate() {
        if (!roomState.running) {
          log('Calibração ignorada: tracking não iniciado.');
          permissionNote.textContent = 'Inicie o tracking antes de calibrar.';
          return;
        }
        permissionNote.textContent = 'Calibração rápida aplicada.';
        roomState.calibrated = true;
        calibrationText.textContent = 'Concluída';
        roomState.calibrationMap = { minX: 0.26, maxX: 0.74, minY: 0.26, maxY: 0.76 };
        log('Calibração aplicada.');
      }

      function exportPdf() {
        ensurePdfLibrary().then(() => {
          const jsPDF = window.jspdf && window.jspdf.jsPDF;
          if (!jsPDF) throw new Error('jsPDF não disponível.');
          const pdf = new jsPDF('p', 'mm', 'a4');
          const margin = 12;
          let y = 16;

          pdf.setFillColor(8, 17, 31);
          pdf.rect(0, 0, 210, 297, 'F');
          pdf.setTextColor(238, 244, 255);
          pdf.setFont('helvetica', 'bold');
          pdf.setFontSize(18);
          pdf.text('Relatório de tracking ocular - Sala 3D', margin, y);
          y += 8;

          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'normal');
          pdf.setTextColor(168, 185, 216);
          pdf.text('Gerado em: ' + new Date().toLocaleString(), margin, y);
          y += 10;

          pdf.setTextColor(238, 244, 255);
          pdf.setFontSize(12);
          pdf.setFont('helvetica', 'bold');
          pdf.text('Resumo da sessão', margin, y);
          y += 6;
          pdf.setFont('helvetica', 'normal');
          pdf.setFontSize(10.5);

          const sec = roomState.startTs ? Math.floor((Date.now() - roomState.startTs) / 1000) : 0;
          const mm = String(Math.floor(sec / 60)).padStart(2, '0');
          const ss = String(sec % 60).padStart(2, '0');
          [
            'Duração: ' + mm + ':' + ss,
            'Amostras de olhar: ' + roomState.heatPoints.length,
            'Fixações estimadas: ' + roomState.fixations,
            'Obras visualizadas: ' + seenArtworkIds.size,
            'Qualidade estimada: ' + Math.round(gaze.quality * 100) + '%',
            'Calibração: ' + (roomState.calibrated ? 'concluída' : 'não concluída')
          ].forEach((line) => {
            pdf.text('• ' + line, margin, y);
            y += 5.5;
          });

          y += 2;
          pdf.setFont('helvetica', 'bold');
          pdf.text('Obras registradas', margin, y);
          y += 6;
          pdf.setFont('helvetica', 'normal');
          if (!roomState.sessionSelections.length) {
            pdf.text('Nenhuma seleção registrada.', margin, y);
            y += 5.5;
          } else {
            const grouped = {};
            roomState.sessionSelections.forEach((s) => {
              grouped[s.id] = grouped[s.id] || { title: s.title, count: 0 };
              grouped[s.id].count += 1;
            });
            Object.keys(grouped).forEach((id) => {
              pdf.text('• ' + grouped[id].title + ' (' + grouped[id].count + ' seleção(ões))', margin, y);
              y += 5.5;
            });
          }

          if (sceneReady) {
            const roomImg = renderer.domElement.toDataURL('image/png', 1.0);
            const heatImg = heatmapCanvas.toDataURL('image/png', 1.0);
            y += 3;
            pdf.setFont('helvetica', 'bold');
            pdf.text('Captura da sala e mapa de calor', margin, y);
            y += 5;
            pdf.addImage(roomImg, 'PNG', margin, y, 88, 66, undefined, 'FAST');
            pdf.addImage(heatImg, 'PNG', 108, y, 88, 66, undefined, 'FAST');
          }
          pdf.save('relatorio_tracking_sala3d.pdf');
          log('PDF exportado.');
        }).catch((err) => {
          log('Falha ao exportar PDF: ' + err.message);
          permissionNote.textContent = 'Falha ao exportar PDF: ' + err.message;
        });
      }

      async function startTracking() {
        try {
          log('Botão iniciar clicado.');
          permissionNote.textContent = 'Carregando bibliotecas…';
          setStatus(false, 'Preparando');

          await ensureCoreLibraries();
          initScene();
          await ensureTrackingLibraries();

          permissionNote.textContent = 'Solicitando câmera…';
          cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
          videoElement.srcObject = cameraStream;
          await videoElement.play();

          faceMesh = new window.FaceMesh({
            locateFile: (file) => 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/' + file,
          });
          faceMesh.setOptions({
            maxNumFaces: 1,
            refineLandmarks: true,
            minDetectionConfidence: 0.55,
            minTrackingConfidence: 0.55,
          });

          faceMesh.onResults((results) => {
            roomState.totalFrames += 1;
            if (!roomState.running) return;
            if (!results.multiFaceLandmarks || !results.multiFaceLandmarks[0]) {
              setStatus(false, 'Rosto não encontrado');
              return;
            }
            setStatus(true, roomState.calibrated ? 'Tracking ativo' : 'Tracking ativo (sem calibração)');
            const landmarks = results.multiFaceLandmarks[0];
            updateGazeFromLandmarks(landmarks);
            const now = Date.now();
            if (now - roomState.lastSampleTs >= roomState.sampleIntervalMs) {
              roomState.lastSampleTs = now;
              addHeatPoint(gaze.smoothX, gaze.smoothY);
            }
          });

          roomState.running = true;
          roomState.startTs = Date.now();
          permissionNote.textContent = 'Câmera ativa. Use “Calibrar olhar” para melhorar a precisão.';
          calibrationText.textContent = roomState.calibrated ? 'Concluída' : 'Pendente';
          setStatus(true, 'Tracking ativo');
          log('Tracking iniciado.');

          async function loop() {
            if (!roomState.running) return;
            try {
              if (videoElement.readyState >= 2 && faceMesh) {
                await faceMesh.send({ image: videoElement });
              }
            } catch (err) {
              log('Erro no processamento do frame: ' + err.message);
            }
            processingLoopId = requestAnimationFrame(loop);
          }
          if (processingLoopId) cancelAnimationFrame(processingLoopId);
          processingLoopId = requestAnimationFrame(loop);
        } catch (err) {
          log('Falha ao iniciar: ' + err.message);
          permissionNote.textContent = 'Não foi possível iniciar: ' + err.message;
          setStatus(false, 'Falha ao iniciar');
        }
      }

      function stopTracking() {
        roomState.running = false;
        setStatus(false, 'Tracking desligado');
        dwellFill.style.width = '0%';
        if (processingLoopId) cancelAnimationFrame(processingLoopId);
        processingLoopId = null;
        if (videoElement && videoElement.srcObject) {
          videoElement.srcObject.getTracks().forEach((t) => t.stop());
          videoElement.srcObject = null;
        }
        permissionNote.textContent = 'Tracking desligado.';
        log('Tracking parado.');
      }

      document.getElementById('startBtn').addEventListener('click', startTracking);
      document.getElementById('stopBtn').addEventListener('click', stopTracking);
      document.getElementById('calibrateBtn').addEventListener('click', calibrate);
      document.getElementById('resetHeatBtn').addEventListener('click', clearHeatmap);
      document.getElementById('exportPdfBtn').addEventListener('click', exportPdf);

      buildArtworkList();
      updateSelectedPanel(null);
      window.addEventListener('resize', resizeCanvases);
      requestAnimationFrame(animate);
      setStatus(false, 'Aguardando');
      log('Botões conectados.');
    })();
  </script>
</div>
"""

components.html(HTML_APP, height=1250, scrolling=True)
