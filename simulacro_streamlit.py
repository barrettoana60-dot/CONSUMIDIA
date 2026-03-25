import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sala 3D com tracking ocular", layout="wide")

st.title("Sala 3D com tracking ocular, dwell-click, heatmap e PDF")
st.caption("Versão estável: a sala 3D já aparece sem depender de Three.js. O tracking ocular tenta usar webcam + MediaPipe; se falhar, entra no modo mouse para teste.")

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
      min-height: 1120px;
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
      max-width: 820px;
      line-height: 1.5;
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
    .scene-panel {
      min-height: 880px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 18px 50px rgba(0,0,0,0.25);
    }
    #scene-shell { position: absolute; inset: 0; }
    #room, #heatmap, #reveal {
      position: absolute; inset: 0; width: 100%; height: 100%;
      display: block;
    }
    #heatmap, #reveal { pointer-events: none; }
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
    .mode-badge {
      position: absolute; top: 18px; left: 180px; z-index: 6; padding: 10px 12px; border-radius: 999px;
      background: rgba(9, 16, 30, 0.72); border: 1px solid rgba(255,255,255,0.08);
      color: var(--muted); font-size: 13px;
    }
    .dwell-meter {
      position: absolute; top: 18px; right: 18px; z-index: 6; width: 200px; padding: 12px; border-radius: 16px;
      background: rgba(9, 16, 30, 0.74); border: 1px solid rgba(255,255,255,0.08); backdrop-filter: blur(14px);
    }
    .dwell-meter .label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
    .bar { width: 100%; height: 10px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }
    .bar > div { width: 0%; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7dd3fc 0%, #c084fc 100%); }
    #permission-note {
      position: absolute; left: 18px; bottom: 18px; z-index: 6; padding: 10px 14px; border-radius: 14px;
      background: rgba(10, 18, 35, 0.88); border: 1px solid rgba(255,255,255,0.08);
      color: var(--muted); font-size: 13px; max-width: 620px; line-height: 1.45;
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
      #eye-room-root { min-height: 1440px; }
      .topbar { grid-template-columns: 1fr; }
      .controls { justify-content: flex-start; }
    }
  </style>

  <div class="topbar">
    <div class="headline">
      <h2>Sala 3D guiada pelo olhar</h2>
      <p>Esta versão desenha a sala diretamente em canvas, então o cenário já aparece mesmo se bibliotecas externas falharem. O tracking tenta usar webcam + MediaPipe; se não conseguir, entra no modo mouse para você testar navegação, dwell-click, heatmap e relatório.</p>
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
        <canvas id="room"></canvas>
        <canvas id="heatmap"></canvas>
        <canvas id="reveal"></canvas>
        <div id="gaze-cursor"></div>
        <div class="corner-chip"><span id="statusDot" class="dot"></span><span id="statusText">Aguardando</span></div>
        <div class="mode-badge">Modo: <strong id="modeText">Cena ativa</strong></div>
        <div class="dwell-meter">
          <div class="label">Progresso do clique por permanência</div>
          <div class="bar"><div id="dwellFill"></div></div>
        </div>
        <div id="permission-note">A sala já está visível. Clique em “Iniciar tracking” para tentar webcam; se falhar, o modo mouse permanece ativo para teste.</div>
      </div>
    </div>

    <div class="sidebar">
      <div class="card">
        <h3>Prévia da câmera</h3>
        <video id="video" autoplay playsinline muted></video>
        <div class="small-note" style="margin-top:8px">Se a câmera não abrir, confirme a permissão do navegador e use HTTPS. Mesmo sem câmera, o modo mouse continua funcionando para teste.</div>
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
        <div id="logBox">Inicializando sala…</div>
      </div>
    </div>
  </div>

  <script>
    (function () {
      const roomCanvas = document.getElementById('room');
      const heatmapCanvas = document.getElementById('heatmap');
      const revealCanvas = document.getElementById('reveal');
      const video = document.getElementById('video');
      const scenePanel = document.querySelector('.scene-panel');
      const gazeCursor = document.getElementById('gaze-cursor');
      const dwellFill = document.getElementById('dwellFill');
      const statusDot = document.getElementById('statusDot');
      const statusText = document.getElementById('statusText');
      const modeText = document.getElementById('modeText');
      const permissionNote = document.getElementById('permission-note');
      const qualityText = document.getElementById('qualityText');
      const hoverText = document.getElementById('hoverText');
      const calibrationText = document.getElementById('calibrationText');
      const statTime = document.getElementById('statTime');
      const statFixations = document.getElementById('statFixations');
      const statPoints = document.getElementById('statPoints');
      const statArtworks = document.getElementById('statArtworks');
      const selectedTitle = document.getElementById('selected-title');
      const selectedArtist = document.getElementById('selected-artist');
      const selectedDescription = document.getElementById('selected-description');
      const artworkList = document.getElementById('artwork-list');
      const logBox = document.getElementById('logBox');

      const ctx = roomCanvas.getContext('2d');
      const heatCtx = heatmapCanvas.getContext('2d');
      const revealCtx = revealCanvas.getContext('2d');

      function log(msg) {
        const line = '[' + new Date().toLocaleTimeString() + '] ' + msg;
        console.log(line);
        logBox.textContent += '\n' + line;
        logBox.scrollTop = logBox.scrollHeight;
      }
      logBox.textContent = 'Sala inicializada.';
      window.addEventListener('error', function (e) {
        log('ERRO JS: ' + (e.message || 'desconhecido'));
      });
      window.addEventListener('unhandledrejection', function (e) {
        log('PROMISE REJECTION: ' + String(e.reason));
      });

      const state = {
        running: false,
        usingMouse: true,
        mediaPipeReady: false,
        faceMesh: null,
        stream: null,
        rafMedia: null,
        startedAt: null,
        lastSampleTs: 0,
        sampleIntervalMs: 85,
        dwellMs: 1200,
        hoverStartTs: 0,
        hoveredArtworkId: null,
        selectedArtworkId: null,
        fixations: 0,
        inFixation: false,
        stableFor: 0,
        lastPointPx: null,
        calibration: { xOffset: 0, yOffset: 0, gainX: 1, gainY: 1 },
        revealPoints: [],
        heatPoints: [],
        selections: [],
        seenArtworkIds: new Set(),
      };

      const gaze = {
        x: 0.5, y: 0.5,
        targetX: 0.5, targetY: 0.5,
        rawX: 0.5, rawY: 0.5,
        quality: 0.82
      };

      const artworks = [
        { id: 'obra_01', title: 'Memórias de Superfície', artist: 'Lívia Andrade', year: '2024', wall: 'fundo', color: '#ef4444', description: 'Pintura em camadas com relevo cromático.', plane: 'back', x: -2.8, y: 2.1, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_02', title: 'Campo Sensível', artist: 'Diego Marins', year: '2025', wall: 'fundo', color: '#22c55e', description: 'Trabalho digital com profundidade simulada.', plane: 'back', x: 0.0, y: 2.2, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_03', title: 'Eco de Matéria', artist: 'Marina Teles', year: '2026', wall: 'fundo', color: '#f59e0b', description: 'Objeto expandido que sugere microscopia e holografia.', plane: 'back', x: 2.8, y: 2.05, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_04', title: 'Horizonte Índigo', artist: 'Ciro Menezes', year: '2023', wall: 'esquerda', color: '#8b5cf6', description: 'Composição geométrica com profundidade visual.', plane: 'left', x: -4.85, y: 2.1, z: 6.1, w: 1.6, h: 1.1 },
        { id: 'obra_05', title: 'Traço Latente', artist: 'Rafaela Costa', year: '2022', wall: 'direita', color: '#06b6d4', description: 'Pintura com leitura periférica e foco seletivo.', plane: 'right', x: 4.85, y: 2.05, z: 5.7, w: 1.6, h: 1.1 },
      ];

      let projectedArtworks = [];

      function setStatus(on, text) {
        statusDot.classList.toggle('on', !!on);
        statusText.textContent = text;
      }

      function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
      function lerp(a, b, t) { return a + (b - a) * t; }

      function resizeCanvases() {
        const rect = scenePanel.getBoundingClientRect();
        [roomCanvas, heatmapCanvas, revealCanvas].forEach((canvas) => {
          canvas.width = Math.floor(rect.width * window.devicePixelRatio);
          canvas.height = Math.floor(rect.height * window.devicePixelRatio);
          canvas.style.width = rect.width + 'px';
          canvas.style.height = rect.height + 'px';
        });
        ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        heatCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        revealCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      }

      const camera = { x: 0, y: 1.65, z: -1.4, yaw: 0, pitch: 0, fov: 700 };

      function projectPoint(x, y, z) {
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

        if (z2 <= 0.1) return null;

        const rect = scenePanel.getBoundingClientRect();
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const s = camera.fov / z2;

        return { x: cx + x1 * s, y: cy - y2 * s, depth: z2, scale: s };
      }

      function drawPoly(points, fill, stroke, lineWidth) {
        if (!points || points.some((p) => !p)) return;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
        ctx.closePath();
        if (fill) { ctx.fillStyle = fill; ctx.fill(); }
        if (stroke) { ctx.lineWidth = lineWidth || 1; ctx.strokeStyle = stroke; ctx.stroke(); }
      }

      function pointInPoly(pt, poly) {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const xi = poly[i].x, yi = poly[i].y;
          const xj = poly[j].x, yj = poly[j].y;
          const intersect = ((yi > pt.y) !== (yj > pt.y)) &&
            (pt.x < ((xj - xi) * (pt.y - yi)) / ((yj - yi) || 1e-6) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      }

      function addHeatPoint(xNorm, yNorm) {
        const rect = scenePanel.getBoundingClientRect();
        const px = xNorm * rect.width;
        const py = yNorm * rect.height;
        state.heatPoints.push({ x: px, y: py, ts: Date.now() });
        if (state.heatPoints.length > 5000) state.heatPoints.shift();

        const grad = heatCtx.createRadialGradient(px, py, 4, px, py, 34);
        grad.addColorStop(0, 'rgba(255,64,64,0.18)');
        grad.addColorStop(0.35, 'rgba(255,191,0,0.12)');
        grad.addColorStop(0.7, 'rgba(34,197,94,0.08)');
        grad.addColorStop(1, 'rgba(34,197,94,0)');
        heatCtx.fillStyle = grad;
        heatCtx.beginPath();
        heatCtx.arc(px, py, 34, 0, Math.PI * 2);
        heatCtx.fill();

        state.revealPoints.push({ x: px, y: py, life: 1 });
        if (state.revealPoints.length > 260) state.revealPoints.shift();

        statPoints.textContent = String(state.heatPoints.length);
        qualityText.textContent = Math.round(gaze.quality * 100) + '%';

        if (state.lastPointPx) {
          const dx = px - state.lastPointPx.x;
          const dy = py - state.lastPointPx.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 28) {
            state.stableFor += state.sampleIntervalMs;
            if (state.stableFor >= 260 && !state.inFixation) {
              state.fixations += 1;
              state.inFixation = true;
              statFixations.textContent = String(state.fixations);
            }
          } else {
            state.stableFor = 0;
            state.inFixation = false;
          }
        }
        state.lastPointPx = { x: px, y: py };
      }

      function drawReveal() {
        const rect = scenePanel.getBoundingClientRect();
        revealCtx.clearRect(0, 0, rect.width, rect.height);
        revealCtx.fillStyle = 'rgba(4, 8, 18, 0.48)';
        revealCtx.fillRect(0, 0, rect.width, rect.height);
        revealCtx.globalCompositeOperation = 'destination-out';
        state.revealPoints.forEach((p) => {
          const radius = 100 + p.life * 78;
          const grad = revealCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
          grad.addColorStop(0, 'rgba(255,255,255,' + (0.18 * p.life) + ')');
          grad.addColorStop(0.45, 'rgba(255,255,255,' + (0.11 * p.life) + ')');
          grad.addColorStop(1, 'rgba(255,255,255,0)');
          revealCtx.fillStyle = grad;
          revealCtx.beginPath();
          revealCtx.arc(p.x, p.y, radius, 0, Math.PI * 2);
          revealCtx.fill();
          p.life *= 0.988;
        });
        state.revealPoints = state.revealPoints.filter((p) => p.life > 0.08);
        revealCtx.globalCompositeOperation = 'source-over';
      }

      function updateCursor() {
        gaze.x = lerp(gaze.x, gaze.targetX, 0.14);
        gaze.y = lerp(gaze.y, gaze.targetY, 0.14);
        gazeCursor.style.left = (gaze.x * 100) + '%';
        gazeCursor.style.top = (gaze.y * 100) + '%';
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

      function selectArtwork(art) {
        state.selectedArtworkId = art.id;
        updateSelectedPanel(art);
        if (!state.seenArtworkIds.has(art.id)) {
          state.seenArtworkIds.add(art.id);
          statArtworks.textContent = String(state.seenArtworkIds.size);
        }
        state.selections.push({ id: art.id, title: art.title, ts: Date.now() });
      }

      function buildArtworkList() {
        artworkList.innerHTML = '';
        artworks.forEach((art) => {
          const row = document.createElement('div');
          row.className = 'art-row';
          row.innerHTML =
            '<div class="art-bullet" style="background:' + art.color + '"></div>' +
            '<div><div class="art-title">' + art.title + '</div><div class="art-sub">' + art.artist + ' · ' + art.year + '</div></div>' +
            '<div class="badge">' + art.wall + '</div>';
          row.addEventListener('click', () => selectArtwork(art));
          artworkList.appendChild(row);
        });
      }

      function drawArtwork(art, highlight) {
        let poly = [];
        if (art.plane === 'back') {
          poly = [
            projectPoint(art.x - art.w / 2, art.y - art.h / 2, art.z),
            projectPoint(art.x + art.w / 2, art.y - art.h / 2, art.z),
            projectPoint(art.x + art.w / 2, art.y + art.h / 2, art.z),
            projectPoint(art.x - art.w / 2, art.y + art.h / 2, art.z),
          ];
        } else if (art.plane === 'left') {
          poly = [
            projectPoint(art.x, art.y - art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y - art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z - art.w / 2),
          ];
        } else {
          poly = [
            projectPoint(art.x, art.y - art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y - art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z + art.w / 2),
          ];
        }
        if (poly.some((p) => !p)) return null;

        drawPoly(poly, 'rgba(91,74,54,0.98)', highlight ? 'rgba(125,211,252,0.95)' : 'rgba(255,255,255,0.12)', highlight ? 2 : 1);
        const inner = poly.map((p, idx) => {
          const cx = (poly[0].x + poly[1].x + poly[2].x + poly[3].x) / 4;
          const cy = (poly[0].y + poly[1].y + poly[2].y + poly[3].y) / 4;
          return { x: lerp(p.x, cx, 0.10), y: lerp(p.y, cy, 0.10) };
        });
        const grad = ctx.createLinearGradient(inner[0].x, inner[0].y, inner[2].x, inner[2].y);
        grad.addColorStop(0, art.color);
        grad.addColorStop(1, '#0f172a');
        drawPoly(inner, grad, highlight ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.08)', 1);

        const tx = (inner[0].x + inner[1].x + inner[2].x + inner[3].x) / 4;
        const ty = (inner[0].y + inner[1].y + inner[2].y + inner[3].y) / 4;
        ctx.fillStyle = 'rgba(255,255,255,0.92)';
        ctx.font = 'bold 13px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(art.title, tx, ty - 4);
        ctx.fillStyle = 'rgba(220,230,255,0.78)';
        ctx.font = '12px Inter, sans-serif';
        ctx.fillText(art.artist, tx, ty + 14);

        return poly;
      }

      function drawPedestal(x, z, hue) {
        const base = [
          projectPoint(x - 0.55, 0.0, z - 0.55),
          projectPoint(x + 0.55, 0.0, z - 0.55),
          projectPoint(x + 0.55, 0.0, z + 0.55),
          projectPoint(x - 0.55, 0.0, z + 0.55),
        ];
        const top = [
          projectPoint(x - 0.42, 1.05, z - 0.42),
          projectPoint(x + 0.42, 1.05, z - 0.42),
          projectPoint(x + 0.42, 1.05, z + 0.42),
          projectPoint(x - 0.42, 1.05, z + 0.42),
        ];
        if (base.some((p) => !p) || top.some((p) => !p)) return;
        drawPoly([base[0], base[1], top[1], top[0]], 'rgba(220,225,235,0.82)', 'rgba(255,255,255,0.12)', 1);
        drawPoly([base[1], base[2], top[2], top[1]], 'rgba(192,200,215,0.85)', 'rgba(255,255,255,0.12)', 1);
        drawPoly([base[2], base[3], top[3], top[2]], 'rgba(168,178,190,0.88)', 'rgba(255,255,255,0.12)', 1);
        drawPoly(top, 'rgba(240,243,248,0.95)', 'rgba(255,255,255,0.14)', 1);

        const orb = projectPoint(x, 1.55, z);
        if (orb) {
          const r = orb.scale * 0.18;
          const g = ctx.createRadialGradient(orb.x - r * 0.4, orb.y - r * 0.4, r * 0.2, orb.x, orb.y, r * 1.5);
          g.addColorStop(0, hue);
          g.addColorStop(1, 'rgba(12,20,36,0.15)');
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(orb.x, orb.y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      function drawRoom() {
        const rect = scenePanel.getBoundingClientRect();
        ctx.clearRect(0, 0, rect.width, rect.height);

        const bg = ctx.createLinearGradient(0, 0, 0, rect.height);
        bg.addColorStop(0, '#07111f');
        bg.addColorStop(1, '#030814');
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, rect.width, rect.height);

        camera.yaw = (gaze.x - 0.5) * 0.52;
        camera.pitch = -(gaze.y - 0.5) * 0.18;
        camera.x = (gaze.x - 0.5) * 1.25;
        camera.y = 1.65 - (gaze.y - 0.5) * 0.45;

        const floor = [
          projectPoint(-5, 0, 0),
          projectPoint(5, 0, 0),
          projectPoint(5, 0, 10),
          projectPoint(-5, 0, 10),
        ];
        const ceiling = [
          projectPoint(-5, 4, 0),
          projectPoint(5, 4, 0),
          projectPoint(5, 4, 10),
          projectPoint(-5, 4, 10),
        ];
        const leftWall = [
          projectPoint(-5, 0, 0),
          projectPoint(-5, 0, 10),
          projectPoint(-5, 4, 10),
          projectPoint(-5, 4, 0),
        ];
        const rightWall = [
          projectPoint(5, 0, 0),
          projectPoint(5, 0, 10),
          projectPoint(5, 4, 10),
          projectPoint(5, 4, 0),
        ];
        const backWall = [
          projectPoint(-5, 0, 10),
          projectPoint(5, 0, 10),
          projectPoint(5, 4, 10),
          projectPoint(-5, 4, 10),
        ];

        drawPoly(ceiling, 'rgba(11,18,35,0.9)', 'rgba(255,255,255,0.05)', 1);
        drawPoly(leftWall, 'rgba(15,25,44,0.94)', 'rgba(255,255,255,0.06)', 1);
        drawPoly(rightWall, 'rgba(12,22,39,0.94)', 'rgba(255,255,255,0.06)', 1);
        drawPoly(backWall, 'rgba(17,27,48,0.96)', 'rgba(255,255,255,0.06)', 1);
        drawPoly(floor, 'rgba(22,36,54,0.98)', 'rgba(255,255,255,0.05)', 1);

        for (let i = -4; i <= 4; i += 1) {
          const a = projectPoint(i, 0.001, 0.2);
          const b = projectPoint(i, 0.001, 9.8);
          if (a && b) {
            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
        for (let z = 1; z <= 10; z += 1) {
          const a = projectPoint(-4.8, 0.001, z);
          const b = projectPoint(4.8, 0.001, z);
          if (a && b) {
            ctx.strokeStyle = 'rgba(255,255,255,0.045)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }

        const spotlight = projectPoint((gaze.x - 0.5) * 3.2, 3.5, 4.8);
        if (spotlight) {
          const grd = ctx.createRadialGradient(spotlight.x, spotlight.y, 0, spotlight.x, spotlight.y, rect.width * 0.33);
          grd.addColorStop(0, 'rgba(125,211,252,0.22)');
          grd.addColorStop(0.5, 'rgba(125,211,252,0.06)');
          grd.addColorStop(1, 'rgba(125,211,252,0)');
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(spotlight.x, spotlight.y, rect.width * 0.33, 0, Math.PI * 2);
          ctx.fill();
        }

        drawPedestal(-1.8, 3.0, 'rgba(125,211,252,0.95)');
        drawPedestal(1.8, 3.35, 'rgba(192,132,252,0.95)');

        projectedArtworks = [];
        artworks.forEach((art) => {
          const poly = drawArtwork(art, state.hoveredArtworkId === art.id || state.selectedArtworkId === art.id);
          if (poly) projectedArtworks.push({ art, poly });
        });

        const gazePx = { x: gaze.x * rect.width, y: gaze.y * rect.height };
        ctx.strokeStyle = 'rgba(255,255,255,0.10)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(gazePx.x, 0);
        ctx.lineTo(gazePx.x, rect.height);
        ctx.moveTo(0, gazePx.y);
        ctx.lineTo(rect.width, gazePx.y);
        ctx.stroke();
      }

      function updateHoverAndDwell(now) {
        const rect = scenePanel.getBoundingClientRect();
        const gazePx = { x: gaze.x * rect.width, y: gaze.y * rect.height };
        const hit = projectedArtworks.find((entry) => pointInPoly(gazePx, entry.poly));

        if (!hit) {
          state.hoveredArtworkId = null;
          state.hoverStartTs = now;
          dwellFill.style.width = '0%';
          hoverText.textContent = 'Nenhum';
          return;
        }

        hoverText.textContent = hit.art.title;
        if (state.hoveredArtworkId !== hit.art.id) {
          state.hoveredArtworkId = hit.art.id;
          state.hoverStartTs = now;
        }
        const elapsed = now - state.hoverStartTs;
        const progress = clamp(elapsed / state.dwellMs, 0, 1);
        dwellFill.style.width = (progress * 100).toFixed(1) + '%';

        if (elapsed >= state.dwellMs) {
          selectArtwork(hit.art);
          state.hoverStartTs = now + 260;
        }
      }

      function clearHeatmap() {
        const rect = scenePanel.getBoundingClientRect();
        heatCtx.clearRect(0, 0, rect.width, rect.height);
        revealCtx.clearRect(0, 0, rect.width, rect.height);
        state.heatPoints = [];
        state.revealPoints = [];
        state.fixations = 0;
        state.inFixation = false;
        state.stableFor = 0;
        state.lastPointPx = null;
        statFixations.textContent = '0';
        statPoints.textContent = '0';
        log('Heatmap limpo.');
      }

      function updateClock() {
        if (!state.startedAt) {
          statTime.textContent = '00:00';
          return;
        }
        const sec = Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
        const mm = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss = String(sec % 60).padStart(2, '0');
        statTime.textContent = mm + ':' + ss;
      }
      setInterval(updateClock, 400);

      function avg(points, key) {
        return points.reduce((s, p) => s + p[key], 0) / Math.max(1, points.length);
      }
      function irisCenter(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return { x: avg(pts, 'x'), y: avg(pts, 'y') };
      }
      function eyeBox(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return {
          minX: Math.min.apply(null, pts.map((p) => p.x)),
          maxX: Math.max.apply(null, pts.map((p) => p.x)),
          minY: Math.min.apply(null, pts.map((p) => p.y)),
          maxY: Math.max.apply(null, pts.map((p) => p.y)),
        };
      }

      async function loadScript(src) {
        return new Promise((resolve, reject) => {
          const old = document.querySelector('script[data-src="' + src + '"]');
          if (old) {
            resolve(true);
            return;
          }
          const s = document.createElement('script');
          s.src = src;
          s.async = true;
          s.dataset.src = src;
          s.onload = () => resolve(true);
          s.onerror = () => reject(new Error('Falha ao carregar ' + src));
          document.head.appendChild(s);
        });
      }

      async function startTracking() {
        log('Iniciar tracking clicado.');
        state.startedAt = state.startedAt || Date.now();
        state.running = true;
        setStatus(false, 'Preparando');
        permissionNote.textContent = 'Tentando abrir webcam + tracking ocular…';

        try {
          await loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js');
          state.mediaPipeReady = true;
          log('MediaPipe carregado.');

          state.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
          video.srcObject = state.stream;
          await video.play();
          log('Webcam aberta.');

          state.faceMesh = new window.FaceMesh({
            locateFile: (file) => 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/' + file,
          });
          state.faceMesh.setOptions({
            maxNumFaces: 1,
            refineLandmarks: true,
            minDetectionConfidence: 0.55,
            minTrackingConfidence: 0.55,
          });
          state.faceMesh.onResults((results) => {
            if (!state.running) return;
            if (!results.multiFaceLandmarks || !results.multiFaceLandmarks[0]) {
              setStatus(false, 'Rosto não encontrado');
              gaze.quality = 0.45;
              return;
            }
            const landmarks = results.multiFaceLandmarks[0];
            const leftIris = irisCenter(landmarks, [468, 469, 470, 471, 472]);
            const rightIris = irisCenter(landmarks, [473, 474, 475, 476, 477]);
            const leftEye = eyeBox(landmarks, [33, 133, 159, 145, 160, 144]);
            const rightEye = eyeBox(landmarks, [362, 263, 386, 374, 385, 380]);

            const lrx = clamp((leftIris.x - leftEye.minX) / Math.max(0.001, leftEye.maxX - leftEye.minX), 0, 1);
            const rrx = clamp((rightIris.x - rightEye.minX) / Math.max(0.001, rightEye.maxX - rightEye.minX), 0, 1);
            const lry = clamp((leftIris.y - leftEye.minY) / Math.max(0.001, leftEye.maxY - leftEye.minY), 0, 1);
            const rry = clamp((rightIris.y - rightEye.minY) / Math.max(0.001, rightEye.maxY - rightEye.minY), 0, 1);

            const rawX = ((lrx + rrx) / 2 - 0.5) * state.calibration.gainX + 0.5 + state.calibration.xOffset;
            const rawY = ((lry + rry) / 2 - 0.5) * state.calibration.gainY + 0.5 + state.calibration.yOffset;

            gaze.rawX = clamp(rawX, 0.02, 0.98);
            gaze.rawY = clamp(rawY, 0.02, 0.98);
            gaze.targetX = gaze.rawX;
            gaze.targetY = gaze.rawY;

            const eyeWidthDiff = Math.abs((leftEye.maxX - leftEye.minX) - (rightEye.maxX - rightEye.minX));
            gaze.quality = clamp(1 - eyeWidthDiff * 10, 0.48, 0.98);

            state.usingMouse = false;
            modeText.textContent = 'Webcam';
            setStatus(true, state.calibration.gainX !== 1 || state.calibration.xOffset !== 0 ? 'Tracking ocular ativo' : 'Tracking ocular ativo');
          });

          async function mediaLoop() {
            if (!state.running || !state.faceMesh) return;
            try {
              if (video.readyState >= 2) {
                await state.faceMesh.send({ image: video });
              }
            } catch (err) {
              log('Erro no frame do MediaPipe: ' + err.message);
            }
            state.rafMedia = requestAnimationFrame(mediaLoop);
          }
          if (state.rafMedia) cancelAnimationFrame(state.rafMedia);
          state.rafMedia = requestAnimationFrame(mediaLoop);

          permissionNote.textContent = 'Tracking ocular ativo. Se a precisão estiver ruim, clique em “Calibrar olhar”.';
        } catch (err) {
          state.usingMouse = true;
          modeText.textContent = 'Mouse';
          setStatus(true, 'Modo mouse ativo');
          permissionNote.textContent = 'Não foi possível iniciar webcam/MediaPipe. O modo mouse ficou ativo para teste.';
          log('Falha no tracking ocular: ' + err.message + ' | entrando no modo mouse.');
        }
      }

      function stopTracking() {
        state.running = false;
        if (state.rafMedia) cancelAnimationFrame(state.rafMedia);
        state.rafMedia = null;
        if (state.stream) {
          state.stream.getTracks().forEach((t) => t.stop());
          state.stream = null;
        }
        video.srcObject = null;
        state.usingMouse = true;
        modeText.textContent = 'Cena ativa';
        setStatus(false, 'Tracking desligado');
        permissionNote.textContent = 'Tracking desligado. A sala continua ativa.';
        dwellFill.style.width = '0%';
        log('Tracking parado.');
      }

      function calibrate() {
        if (state.usingMouse) {
          calibrationText.textContent = 'Modo mouse';
          permissionNote.textContent = 'No modo mouse não é necessário calibrar.';
          log('Calibração ignorada no modo mouse.');
          return;
        }
        state.calibration.xOffset += (0.5 - gaze.rawX) * 0.35;
        state.calibration.yOffset += (0.5 - gaze.rawY) * 0.35;
        state.calibration.gainX = 1.18;
        state.calibration.gainY = 1.12;
        calibrationText.textContent = 'Concluída';
        permissionNote.textContent = 'Calibração aplicada.';
        log('Calibração aplicada.');
      }

      async function exportPdf() {
        log('Exportar PDF clicado.');
        const rect = scenePanel.getBoundingClientRect();
        const sceneImg = roomCanvas.toDataURL('image/png', 1.0);
        const heatImg = heatmapCanvas.toDataURL('image/png', 1.0);

        try {
          await loadScript('https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js');
          const jsPDF = window.jspdf && window.jspdf.jsPDF;
          if (!jsPDF) throw new Error('jsPDF não disponível.');

          const pdf = new jsPDF('p', 'mm', 'a4');
          let y = 16;
          pdf.setFillColor(8, 17, 31);
          pdf.rect(0, 0, 210, 297, 'F');
          pdf.setTextColor(238, 244, 255);
          pdf.setFont('helvetica', 'bold');
          pdf.setFontSize(18);
          pdf.text('Relatório de tracking ocular - Sala 3D', 12, y);
          y += 8;
          pdf.setFont('helvetica', 'normal');
          pdf.setFontSize(10);
          pdf.setTextColor(168, 185, 216);
          pdf.text('Gerado em: ' + new Date().toLocaleString(), 12, y);
          y += 9;
          pdf.setTextColor(238, 244, 255);
          pdf.setFontSize(11);
          pdf.text('Modo: ' + (state.usingMouse ? 'Mouse' : 'Webcam'), 12, y);
          y += 5;
          pdf.text('Amostras: ' + state.heatPoints.length, 12, y);
          y += 5;
          pdf.text('Fixações: ' + state.fixations, 12, y);
          y += 5;
          pdf.text('Obras vistas: ' + state.seenArtworkIds.size, 12, y);
          y += 5;
          pdf.text('Qualidade estimada: ' + Math.round(gaze.quality * 100) + '%', 12, y);
          y += 8;

          pdf.setFont('helvetica', 'bold');
          pdf.text('Cena da sala', 12, y);
          y += 3;
          pdf.addImage(sceneImg, 'PNG', 12, y, 88, 66, undefined, 'FAST');
          pdf.addImage(heatImg, 'PNG', 108, y, 88, 66, undefined, 'FAST');
          y += 74;

          pdf.setFont('helvetica', 'bold');
          pdf.text('Seleções registradas', 12, y);
          y += 6;
          pdf.setFont('helvetica', 'normal');
          if (!state.selections.length) {
            pdf.text('Nenhuma seleção registrada.', 12, y);
          } else {
            const grouped = {};
            state.selections.forEach((s) => {
              grouped[s.id] = grouped[s.id] || { title: s.title, count: 0 };
              grouped[s.id].count += 1;
            });
            Object.keys(grouped).forEach((id) => {
              pdf.text('• ' + grouped[id].title + ' (' + grouped[id].count + ')', 12, y);
              y += 5;
            });
          }
          pdf.save('relatorio_tracking_sala3d.pdf');
          log('PDF exportado com jsPDF.');
          return;
        } catch (err) {
          log('jsPDF falhou: ' + err.message + ' | usando impressão do navegador.');
        }

        const win = window.open('', '_blank');
        if (!win) {
          log('Não foi possível abrir a janela de impressão.');
          return;
        }
        win.document.write(
          '<html><head><title>Relatório Sala 3D</title><style>' +
          'body{font-family:Arial,sans-serif;padding:24px;color:#111} h1{margin:0 0 8px} .meta{color:#444;margin-bottom:18px}' +
          'img{max-width:48%;margin-right:2%;border:1px solid #ccc;border-radius:8px} .row{display:flex;gap:12px;margin:18px 0}' +
          '</style></head><body>' +
          '<h1>Relatório de tracking ocular - Sala 3D</h1>' +
          '<div class="meta">Modo: ' + (state.usingMouse ? 'Mouse' : 'Webcam') +
          ' · Amostras: ' + state.heatPoints.length +
          ' · Fixações: ' + state.fixations +
          ' · Obras vistas: ' + state.seenArtworkIds.size +
          ' · Qualidade: ' + Math.round(gaze.quality * 100) + '%</div>' +
          '<div class="row"><img src="' + sceneImg + '"/><img src="' + heatImg + '"/></div>' +
          '<p>Use “Salvar como PDF” na janela de impressão do navegador.</p>' +
          '</body></html>'
        );
        win.document.close();
        win.focus();
        win.print();
        log('Relatório aberto para impressão.');
      }

      scenePanel.addEventListener('mousemove', function (ev) {
        if (!state.usingMouse) return;
        const rect = scenePanel.getBoundingClientRect();
        gaze.targetX = clamp((ev.clientX - rect.left) / rect.width, 0.02, 0.98);
        gaze.targetY = clamp((ev.clientY - rect.top) / rect.height, 0.02, 0.98);
      });
      scenePanel.addEventListener('mouseenter', function () {
        if (state.startedAt === null) state.startedAt = Date.now();
      });

      document.getElementById('startBtn').addEventListener('click', startTracking);
      document.getElementById('stopBtn').addEventListener('click', stopTracking);
      document.getElementById('calibrateBtn').addEventListener('click', calibrate);
      document.getElementById('resetHeatBtn').addEventListener('click', clearHeatmap);
      document.getElementById('exportPdfBtn').addEventListener('click', exportPdf);

      function tick(now) {
        requestAnimationFrame(tick);
        updateCursor();
        drawRoom();
        drawReveal();
        if (state.startedAt === null) state.startedAt = Date.now();

        if (state.running || state.usingMouse) {
          updateHoverAndDwell(now);
          const t = Date.now();
          if (t - state.lastSampleTs >= state.sampleIntervalMs) {
            state.lastSampleTs = t;
            addHeatPoint(gaze.x, gaze.y);
          }
        }
      }

      resizeCanvases();
      buildArtworkList();
      updateSelectedPanel(null);
      modeText.textContent = 'Cena ativa';
      calibrationText.textContent = 'Pendente';
      setStatus(true, 'Cena carregada');
      window.addEventListener('resize', resizeCanvases);
      requestAnimationFrame(tick);
      log('Sala desenhada com sucesso.');
    })();
  </script>
</div>
"""

components.html(HTML_APP, height=1260, scrolling=True)
