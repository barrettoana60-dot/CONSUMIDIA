from pathlib import Path
import zipfile

app_code = r'''import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sala 3D com eye tracking e blink zoom", layout="wide")

st.title("Sala 3D com tracking ocular avançado")
st.caption(
    "Versão completa com navegação pelo olhar, heatmap, dwell-click, calibração em 5 pontos e zoom por piscada."
)
st.info(
    "Fluxo sugerido: 1) Abra o app. 2) Clique em “Iniciar tracking”. 3) Clique em “Calibração 5 pontos”. "
    "4) Olhe para cada alvo. 5) Pare o olhar sobre uma obra para selecionar. 6) Pisque olhando para a obra para entrar ou sair do zoom."
)

HTML_APP = r"""
<div id="eye-room-root">
  <style>
    :root {
      --bg0: #040a14;
      --bg1: #07111f;
      --bg2: #0d1a31;
      --card: rgba(12, 20, 37, 0.84);
      --card2: rgba(17, 28, 51, 0.9);
      --border: rgba(255,255,255,0.08);
      --text: #eef4ff;
      --muted: #a8b9d8;
      --cyan: #7dd3fc;
      --purple: #c084fc;
      --green: #34d399;
      --yellow: #fbbf24;
      --pink: #fb7185;
      --glass: rgba(255,255,255,0.05);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: transparent; }

    #eye-room-root {
      width: 100%;
      min-height: 1280px;
      padding: 18px;
      border-radius: 26px;
      overflow: hidden;
      color: var(--text);
      border: 1px solid rgba(255,255,255,0.06);
      background:
        radial-gradient(circle at 20% 0%, rgba(125,211,252,0.11), transparent 28%),
        radial-gradient(circle at 100% 100%, rgba(192,132,252,0.11), transparent 30%),
        linear-gradient(180deg, #07101d 0%, #040812 100%);
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
      font-size: 28px;
      font-weight: 900;
      letter-spacing: 0.2px;
    }
    .headline p {
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 860px;
      line-height: 1.55;
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
      color: var(--text);
      padding: 10px 14px;
      border-radius: 14px;
      font-weight: 800;
      cursor: pointer;
      transition: 0.2s ease;
      user-select: none;
      background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04));
      box-shadow: 0 8px 22px rgba(0,0,0,0.18);
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(125,211,252,0.4); }
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
      grid-template-columns: minmax(0, 1.75fr) minmax(330px, 0.78fr);
      gap: 16px;
      min-height: 980px;
    }
    .scene-panel, .sidebar {
      border-radius: 24px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
      backdrop-filter: blur(18px);
      position: relative;
      overflow: hidden;
    }
    .scene-panel {
      min-height: 920px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 18px 50px rgba(0,0,0,0.26);
    }
    .scene-shell {
      position: absolute;
      inset: 0;
      overflow: hidden;
    }
    #room, #heatmap, #reveal, #hud {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      display: block;
    }
    #heatmap, #reveal, #hud { pointer-events: none; }
    #gaze-cursor {
      position: absolute;
      width: 28px;
      height: 28px;
      border: 2px solid rgba(255,255,255,0.95);
      border-radius: 999px;
      transform: translate(-50%, -50%);
      left: 50%;
      top: 50%;
      z-index: 8;
      pointer-events: none;
      box-shadow: 0 0 0 8px rgba(125,211,252,0.15), 0 0 24px rgba(125,211,252,0.28);
      transition: width 0.12s ease, height 0.12s ease, border-color 0.12s ease;
    }
    #gaze-cursor::after {
      content: "";
      position: absolute;
      inset: 6px;
      border-radius: 999px;
      background: rgba(255,255,255,0.85);
    }
    .chip {
      position: absolute;
      z-index: 9;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 12px;
      border-radius: 999px;
      background: rgba(9, 16, 30, 0.74);
      border: 1px solid rgba(255,255,255,0.08);
      font-size: 13px;
      color: var(--muted);
      box-shadow: 0 10px 22px rgba(0,0,0,0.18);
    }
    .status-chip { top: 18px; left: 18px; }
    .mode-chip { top: 18px; left: 170px; }
    .zoom-chip { top: 18px; left: 310px; }
    .blink-chip { top: 18px; left: 472px; }
    .quality-chip { top: 18px; left: 635px; }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--pink);
      box-shadow: 0 0 16px rgba(251,113,133,0.42);
    }
    .dot.on {
      background: var(--green);
      box-shadow: 0 0 16px rgba(52,211,153,0.42);
    }
    .right-overlay {
      position: absolute;
      top: 18px;
      right: 18px;
      z-index: 9;
      display: grid;
      gap: 10px;
      width: 228px;
    }
    .meter-card {
      padding: 12px;
      border-radius: 18px;
      background: rgba(9, 16, 30, 0.74);
      border: 1px solid rgba(255,255,255,0.08);
      backdrop-filter: blur(12px);
    }
    .meter-card .label {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .bar {
      width: 100%;
      height: 10px;
      background: rgba(255,255,255,0.08);
      border-radius: 999px;
      overflow: hidden;
    }
    .bar > div {
      width: 0%;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #7dd3fc 0%, #c084fc 100%);
    }
    .bottom-note {
      position: absolute;
      left: 18px;
      bottom: 18px;
      z-index: 9;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(9, 16, 30, 0.84);
      border: 1px solid rgba(255,255,255,0.08);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      max-width: 720px;
    }
    #calibration-target {
      position: absolute;
      width: 48px;
      height: 48px;
      border-radius: 999px;
      border: 3px solid rgba(255,255,255,0.94);
      transform: translate(-50%, -50%);
      z-index: 10;
      display: none;
      box-shadow: 0 0 0 10px rgba(251,191,36,0.16), 0 0 24px rgba(251,191,36,0.34);
      pointer-events: none;
    }
    #calibration-target::before {
      content: "";
      position: absolute;
      inset: 11px;
      border-radius: 999px;
      background: rgba(251,191,36,0.96);
      box-shadow: 0 0 18px rgba(251,191,36,0.5);
    }
    #calibration-label {
      position: absolute;
      z-index: 10;
      display: none;
      transform: translate(-50%, calc(-50% - 48px));
      color: #fff7dd;
      font-weight: 800;
      font-size: 13px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(40, 28, 6, 0.82);
      border: 1px solid rgba(251,191,36,0.34);
      pointer-events: none;
    }
    .sidebar {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .card {
      border-radius: 22px;
      padding: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .card h3 {
      margin: 0 0 10px;
      font-size: 15px;
      letter-spacing: 0.2px;
    }
    #video {
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.08);
      background: #020712;
      transform: scaleX(-1);
    }
    .stats-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .stat {
      border-radius: 18px;
      padding: 12px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
    }
    .stat .k {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .stat .v {
      font-size: 22px;
      font-weight: 900;
    }
    .meta-line {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 0;
      color: var(--muted);
      font-size: 13px;
      border-bottom: 1px dashed rgba(255,255,255,0.08);
    }
    .meta-line:last-child { border-bottom: none; }
    .meta-line strong { color: var(--text); font-size: 13px; }
    #selected-title {
      margin: 0 0 6px;
      font-size: 20px;
    }
    #selected-artist {
      margin-bottom: 10px;
      color: var(--cyan);
      font-weight: 800;
    }
    #selected-description {
      color: var(--muted);
      line-height: 1.55;
      font-size: 13.5px;
    }
    #artwork-list {
      display: grid;
      gap: 10px;
      max-height: 280px;
      overflow: auto;
    }
    .art-row {
      display: grid;
      grid-template-columns: 14px 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border-radius: 16px;
      cursor: pointer;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
    }
    .art-row.active {
      border-color: rgba(125,211,252,0.28);
      background: rgba(125,211,252,0.08);
    }
    .art-bullet {
      width: 14px;
      height: 14px;
      border-radius: 999px;
    }
    .art-title {
      font-weight: 800;
      margin-bottom: 3px;
    }
    .art-sub {
      color: var(--muted);
      font-size: 12.5px;
    }
    .badge {
      font-size: 11px;
      font-weight: 900;
      color: #dbeafe;
      background: rgba(125,211,252,0.14);
      border: 1px solid rgba(125,211,252,0.22);
      padding: 6px 8px;
      border-radius: 999px;
    }
    #logBox {
      min-height: 130px;
      max-height: 200px;
      overflow: auto;
      border-radius: 14px;
      padding: 10px;
      background: rgba(3, 7, 18, 0.76);
      border: 1px solid rgba(255,255,255,0.08);
      color: #b3c2df;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .small-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    @media (max-width: 1320px) {
      .quality-chip { display: none; }
      .zoom-chip { left: 310px; }
      .blink-chip { left: 472px; }
    }
    @media (max-width: 1180px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .scene-panel {
        min-height: 720px;
      }
      #eye-room-root {
        min-height: 1560px;
      }
      .topbar {
        grid-template-columns: 1fr;
      }
      .controls {
        justify-content: flex-start;
      }
    }
    @media (max-width: 880px) {
      .mode-chip, .zoom-chip, .blink-chip, .quality-chip {
        display: none;
      }
    }
  </style>

  <div class="topbar">
    <div class="headline">
      <h2>Sala 3D guiada pelo olhar</h2>
      <p>
        Melhorias desta versão: filtro ocular mais estável, calibração em 5 pontos,
        detecção de piscada com Eye Aspect Ratio, zoom ao piscar sobre uma obra,
        navegação pelo cenário mais suave, dwell-click para abrir a ficha e relatório com heatmap.
      </p>
    </div>
    <div class="controls">
      <button class="btn primary" id="startBtn">Iniciar tracking</button>
      <button class="btn warn" id="calibrateBtn">Calibração 5 pontos</button>
      <button class="btn subtle" id="resetHeatBtn">Limpar heatmap</button>
      <button class="btn" id="resetViewBtn">Resetar visão</button>
      <button class="btn" id="exportPdfBtn">Exportar PDF</button>
      <button class="btn" id="stopBtn">Parar</button>
    </div>
  </div>

  <div class="layout">
    <div class="scene-panel" id="scenePanel">
      <div class="scene-shell">
        <canvas id="room"></canvas>
        <canvas id="heatmap"></canvas>
        <canvas id="reveal"></canvas>
        <canvas id="hud"></canvas>

        <div id="gaze-cursor"></div>
        <div class="chip status-chip"><span id="statusDot" class="dot"></span><span id="statusText">Cena ativa</span></div>
        <div class="chip mode-chip">Modo: <strong id="modeText">Mouse</strong></div>
        <div class="chip zoom-chip">Zoom: <strong id="zoomText">Livre</strong></div>
        <div class="chip blink-chip">Piscadas: <strong id="blinkText">0</strong></div>
        <div class="chip quality-chip">Qualidade: <strong id="qualityHeaderText">0%</strong></div>

        <div class="right-overlay">
          <div class="meter-card">
            <div class="label">Progresso do clique por permanência</div>
            <div class="bar"><div id="dwellFill"></div></div>
          </div>
          <div class="meter-card">
            <div class="label">Intensidade do zoom</div>
            <div class="bar"><div id="zoomFill"></div></div>
          </div>
          <div class="meter-card">
            <div class="label">Piscada atual</div>
            <div class="bar"><div id="blinkFill"></div></div>
          </div>
        </div>

        <div id="calibration-target"></div>
        <div id="calibration-label"></div>

        <div class="bottom-note" id="permissionNote">
          A sala já está ativa em modo mouse. Para usar o olhar, clique em “Iniciar tracking”.
          Depois rode a calibração. Para dar zoom, olhe para uma obra e pisque.
        </div>
      </div>
    </div>

    <div class="sidebar">
      <div class="card">
        <h3>Prévia da câmera</h3>
        <video id="video" autoplay playsinline muted></video>
        <div class="small-note" style="margin-top:8px">
          Se a webcam falhar, o app continua em modo mouse para teste. O tracking ocular usa MediaPipe no navegador.
        </div>
      </div>

      <div class="card">
        <h3>Métricas da sessão</h3>
        <div class="stats-grid">
          <div class="stat"><div class="k">Tempo</div><div class="v" id="statTime">00:00</div></div>
          <div class="stat"><div class="k">Fixações</div><div class="v" id="statFixations">0</div></div>
          <div class="stat"><div class="k">Amostras</div><div class="v" id="statPoints">0</div></div>
          <div class="stat"><div class="k">Obras vistas</div><div class="v" id="statArtworks">0</div></div>
          <div class="stat"><div class="k">Piscadas</div><div class="v" id="statBlinks">0</div></div>
          <div class="stat"><div class="k">Zooms</div><div class="v" id="statZooms">0</div></div>
        </div>
        <div class="meta-line"><span>Qualidade estimada</span><strong id="qualityText">0%</strong></div>
        <div class="meta-line"><span>Último hover</span><strong id="hoverText">Nenhum</strong></div>
        <div class="meta-line"><span>Calibração</span><strong id="calibrationText">Pendente</strong></div>
        <div class="meta-line"><span>Obra em foco</span><strong id="focusText">Nenhuma</strong></div>
      </div>

      <div class="card">
        <h3>Obra selecionada</h3>
        <div id="selected-title">Nenhuma obra selecionada</div>
        <div id="selected-artist">Pare o olhar sobre uma obra por ~1,1 s</div>
        <div id="selected-description">Depois, pisque olhando para a obra para entrar ou sair do zoom.</div>
      </div>

      <div class="card">
        <h3>Obras da sala</h3>
        <div id="artwork-list"></div>
      </div>

      <div class="card">
        <h3>Log do sistema</h3>
        <div id="logBox">Inicializando sala...</div>
      </div>
    </div>
  </div>

  <script>
    (function () {
      const roomCanvas = document.getElementById('room');
      const heatmapCanvas = document.getElementById('heatmap');
      const revealCanvas = document.getElementById('reveal');
      const hudCanvas = document.getElementById('hud');
      const scenePanel = document.getElementById('scenePanel');
      const video = document.getElementById('video');

      const ctx = roomCanvas.getContext('2d');
      const heatCtx = heatmapCanvas.getContext('2d');
      const revealCtx = revealCanvas.getContext('2d');
      const hudCtx = hudCanvas.getContext('2d');

      const gazeCursor = document.getElementById('gaze-cursor');
      const statusDot = document.getElementById('statusDot');
      const statusText = document.getElementById('statusText');
      const modeText = document.getElementById('modeText');
      const zoomText = document.getElementById('zoomText');
      const blinkText = document.getElementById('blinkText');
      const qualityHeaderText = document.getElementById('qualityHeaderText');
      const permissionNote = document.getElementById('permissionNote');

      const dwellFill = document.getElementById('dwellFill');
      const zoomFill = document.getElementById('zoomFill');
      const blinkFill = document.getElementById('blinkFill');

      const statTime = document.getElementById('statTime');
      const statFixations = document.getElementById('statFixations');
      const statPoints = document.getElementById('statPoints');
      const statArtworks = document.getElementById('statArtworks');
      const statBlinks = document.getElementById('statBlinks');
      const statZooms = document.getElementById('statZooms');

      const qualityText = document.getElementById('qualityText');
      const hoverText = document.getElementById('hoverText');
      const calibrationText = document.getElementById('calibrationText');
      const focusText = document.getElementById('focusText');

      const selectedTitle = document.getElementById('selected-title');
      const selectedArtist = document.getElementById('selected-artist');
      const selectedDescription = document.getElementById('selected-description');

      const artworkList = document.getElementById('artwork-list');
      const logBox = document.getElementById('logBox');

      const calibrationTarget = document.getElementById('calibration-target');
      const calibrationLabel = document.getElementById('calibration-label');

      function log(message) {
        const line = '[' + new Date().toLocaleTimeString() + '] ' + message;
        console.log(line);
        logBox.textContent += '\n' + line;
        logBox.scrollTop = logBox.scrollHeight;
      }
      logBox.textContent = 'Sala carregada.';
      window.addEventListener('error', (e) => log('ERRO JS: ' + (e.message || 'desconhecido')));
      window.addEventListener('unhandledrejection', (e) => log('PROMISE: ' + String(e.reason)));

      function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
      function lerp(a, b, t) { return a + (b - a) * t; }
      function dist2d(ax, ay, bx, by) { return Math.hypot(ax - bx, ay - by); }
      function avg(points, key) {
        return points.reduce((sum, p) => sum + p[key], 0) / Math.max(1, points.length);
      }
      function setStatus(isOn, text) {
        statusDot.classList.toggle('on', !!isOn);
        statusText.textContent = text;
      }

      const artworks = [
        { id: 'obra_01', title: 'Memórias de Superfície', artist: 'Lívia Andrade', year: '2024', wall: 'fundo', color: '#ef4444', description: 'Pintura em camadas com relevo cromático e leitura visual por aproximação.', plane: 'back', x: -2.8, y: 2.12, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_02', title: 'Campo Sensível', artist: 'Diego Marins', year: '2025', wall: 'fundo', color: '#22c55e', description: 'Trabalho digital de profundidade simulada que reage bem ao foco ocular.', plane: 'back', x: 0.0, y: 2.18, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_03', title: 'Eco de Matéria', artist: 'Marina Teles', year: '2026', wall: 'fundo', color: '#f59e0b', description: 'Objeto expandido com atmosfera quase microscópica e aura de holografia.', plane: 'back', x: 2.8, y: 2.08, z: 9.85, w: 1.7, h: 1.2 },
        { id: 'obra_04', title: 'Horizonte Índigo', artist: 'Ciro Menezes', year: '2023', wall: 'esquerda', color: '#8b5cf6', description: 'Composição geométrica com percepção lateral e leitura periférica.', plane: 'left', x: -4.85, y: 2.10, z: 6.1, w: 1.6, h: 1.1 },
        { id: 'obra_05', title: 'Traço Latente', artist: 'Rafaela Costa', year: '2022', wall: 'direita', color: '#06b6d4', description: 'Pintura cuja leitura muda conforme o observador muda a inclinação do olhar.', plane: 'right', x: 4.85, y: 2.06, z: 5.7, w: 1.6, h: 1.1 }
      ];

      const state = {
        running: false,
        usingMouse: true,
        startTs: null,
        faceMesh: null,
        stream: null,
        rafMedia: null,
        sampleIntervalMs: 75,
        lastSampleTs: 0,
        dwellMs: 1100,
        hoveredArtworkId: null,
        hoverStartTs: 0,
        selectedArtworkId: null,
        focusedArtworkId: null,
        focusTransition: 0,
        fixations: 0,
        stableFor: 0,
        inFixation: false,
        lastPointPx: null,
        heatPoints: [],
        revealPoints: [],
        seenArtworkIds: new Set(),
        selections: [],
        zoomCount: 0,
        blinkCount: 0,
        blinkClosed: false,
        blinkStartedAt: 0,
        blinkProgress: 0,
        calibration: {
          mode: 'default',
          sequenceActive: false,
          currentIndex: 0,
          points: [
            { x: 0.50, y: 0.50, label: 'Centro' },
            { x: 0.14, y: 0.50, label: 'Esquerda' },
            { x: 0.86, y: 0.50, label: 'Direita' },
            { x: 0.50, y: 0.16, label: 'Topo' },
            { x: 0.50, y: 0.84, label: 'Base' }
          ],
          stepSamples: [],
          results: [],
          currentStartTs: 0,
          gatherDelayMs: 400,
          gatherDurationMs: 850,
          map: { xMin: 0.32, xMax: 0.68, yMin: 0.32, yMax: 0.68, marginX: 0.05, marginY: 0.06 }
        }
      };

      const gaze = {
        rawX: 0.5,
        rawY: 0.5,
        targetX: 0.5,
        targetY: 0.5,
        x: 0.5,
        y: 0.5,
        velocity: 0,
        quality: 0.0
      };

      const blink = {
        ear: 0.28,
        threshold: 0.205,
        cooldownUntil: 0
      };

      const camera = {
        x: 0,
        y: 1.63,
        z: -1.6,
        yaw: 0,
        pitch: 0,
        focal: 710
      };
      const cameraTargets = {
        x: 0,
        y: 1.63,
        z: -1.6,
        yaw: 0,
        pitch: 0,
        focal: 710
      };

      let projectedArtworks = [];

      function updateCursor() {
        const dx = gaze.targetX - gaze.x;
        const dy = gaze.targetY - gaze.y;
        const distance = Math.hypot(dx, dy);
        gaze.velocity = lerp(gaze.velocity, distance, 0.22);

        const alpha = clamp(0.08 + gaze.velocity * 0.55, 0.09, 0.28);
        gaze.x = lerp(gaze.x, gaze.targetX, alpha);
        gaze.y = lerp(gaze.y, gaze.targetY, alpha);

        gazeCursor.style.left = (gaze.x * 100) + '%';
        gazeCursor.style.top = (gaze.y * 100) + '%';
      }

      function resizeCanvases() {
        const rect = scenePanel.getBoundingClientRect();
        [roomCanvas, heatmapCanvas, revealCanvas, hudCanvas].forEach((canvas) => {
          canvas.width = Math.floor(rect.width * window.devicePixelRatio);
          canvas.height = Math.floor(rect.height * window.devicePixelRatio);
          canvas.style.width = rect.width + 'px';
          canvas.style.height = rect.height + 'px';
        });
        ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        heatCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        revealCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
        hudCtx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      }

      function updateSessionClock() {
        if (!state.startTs) {
          statTime.textContent = '00:00';
          return;
        }
        const sec = Math.max(0, Math.floor((Date.now() - state.startTs) / 1000));
        const mm = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss = String(sec % 60).padStart(2, '0');
        statTime.textContent = mm + ':' + ss;
      }
      setInterval(updateSessionClock, 400);

      function buildArtworkList() {
        artworkList.innerHTML = '';
        artworks.forEach((art) => {
          const row = document.createElement('div');
          row.className = 'art-row';
          row.dataset.id = art.id;
          row.innerHTML =
            '<div class="art-bullet" style="background:' + art.color + '"></div>' +
            '<div><div class="art-title">' + art.title + '</div><div class="art-sub">' + art.artist + ' · ' + art.year + '</div></div>' +
            '<div class="badge">' + art.wall + '</div>';
          row.addEventListener('click', () => {
            selectArtwork(art);
            focusArtwork(art.id);
          });
          artworkList.appendChild(row);
        });
      }

      function refreshArtworkListState() {
        Array.from(artworkList.children).forEach((row) => {
          row.classList.toggle('active', row.dataset.id === state.selectedArtworkId || row.dataset.id === state.focusedArtworkId);
        });
      }

      function updateSelectedPanel(art) {
        if (!art) {
          selectedTitle.textContent = 'Nenhuma obra selecionada';
          selectedArtist.textContent = 'Pare o olhar sobre uma obra por ~1,1 s';
          selectedDescription.textContent = 'Depois, pisque olhando para a obra para entrar ou sair do zoom.';
          return;
        }
        selectedTitle.textContent = art.title;
        selectedArtist.textContent = art.artist + ' · ' + art.year + ' · parede ' + art.wall;
        selectedDescription.textContent = art.description;
      }

      function findArtworkById(id) {
        return artworks.find((a) => a.id === id) || null;
      }

      function selectArtwork(art) {
        state.selectedArtworkId = art.id;
        if (!state.seenArtworkIds.has(art.id)) {
          state.seenArtworkIds.add(art.id);
          statArtworks.textContent = String(state.seenArtworkIds.size);
        }
        state.selections.push({ id: art.id, title: art.title, ts: Date.now() });
        updateSelectedPanel(art);
        refreshArtworkListState();
      }

      function focusArtwork(id) {
        state.focusedArtworkId = id;
        focusText.textContent = findArtworkById(id)?.title || 'Nenhuma';
        zoomText.textContent = id ? 'Focado' : 'Livre';
        if (id) {
          state.zoomCount += 1;
          statZooms.textContent = String(state.zoomCount);
        }
        refreshArtworkListState();
      }

      function clearFocus() {
        state.focusedArtworkId = null;
        focusText.textContent = 'Nenhuma';
        zoomText.textContent = 'Livre';
        refreshArtworkListState();
      }

      function toggleFocusByBlink() {
        if (state.hoveredArtworkId) {
          if (state.focusedArtworkId === state.hoveredArtworkId) {
            clearFocus();
            permissionNote.textContent = 'Zoom removido. Continue navegando com o olhar.';
            log('Blink: saiu do zoom.');
          } else {
            const art = findArtworkById(state.hoveredArtworkId);
            if (art) {
              selectArtwork(art);
              focusArtwork(art.id);
              permissionNote.textContent = 'Zoom ativado em “' + art.title + '”. Pisque novamente olhando para a obra para sair.';
              log('Blink: zoom ativado em ' + art.title + '.');
            }
          }
        } else if (state.focusedArtworkId) {
          clearFocus();
          permissionNote.textContent = 'Zoom removido.';
          log('Blink sem hover: zoom removido.');
        }
      }

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

        if (z2 <= 0.12) return null;

        const rect = scenePanel.getBoundingClientRect();
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const scale = camera.focal / z2;

        return { x: cx + x1 * scale, y: cy - y2 * scale, z: z2, scale };
      }

      function drawPolygon(points, fill, stroke, lineWidth) {
        if (!points || points.some((p) => !p)) return;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
        ctx.closePath();
        if (fill) {
          ctx.fillStyle = fill;
          ctx.fill();
        }
        if (stroke) {
          ctx.strokeStyle = stroke;
          ctx.lineWidth = lineWidth || 1;
          ctx.stroke();
        }
      }

      function pointInPolygon(point, poly) {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const xi = poly[i].x, yi = poly[i].y;
          const xj = poly[j].x, yj = poly[j].y;
          const intersect =
            ((yi > point.y) !== (yj > point.y)) &&
            (point.x < ((xj - xi) * (point.y - yi)) / ((yj - yi) || 1e-6) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      }

      function drawPedestal(x, z, hue) {
        const base = [
          projectPoint(x - 0.56, 0.0, z - 0.56),
          projectPoint(x + 0.56, 0.0, z - 0.56),
          projectPoint(x + 0.56, 0.0, z + 0.56),
          projectPoint(x - 0.56, 0.0, z + 0.56)
        ];
        const top = [
          projectPoint(x - 0.42, 1.05, z - 0.42),
          projectPoint(x + 0.42, 1.05, z - 0.42),
          projectPoint(x + 0.42, 1.05, z + 0.42),
          projectPoint(x - 0.42, 1.05, z + 0.42)
        ];
        if (base.some((p) => !p) || top.some((p) => !p)) return;

        drawPolygon([base[0], base[1], top[1], top[0]], 'rgba(228,234,242,0.86)', 'rgba(255,255,255,0.12)', 1);
        drawPolygon([base[1], base[2], top[2], top[1]], 'rgba(198,206,218,0.88)', 'rgba(255,255,255,0.12)', 1);
        drawPolygon([base[2], base[3], top[3], top[2]], 'rgba(170,178,191,0.9)', 'rgba(255,255,255,0.12)', 1);
        drawPolygon(top, 'rgba(245,247,250,0.96)', 'rgba(255,255,255,0.14)', 1);

        const orb = projectPoint(x, 1.56, z);
        if (orb) {
          const r = orb.scale * 0.19;
          const g = ctx.createRadialGradient(orb.x - r * 0.35, orb.y - r * 0.35, r * 0.2, orb.x, orb.y, r * 1.5);
          g.addColorStop(0, hue);
          g.addColorStop(1, 'rgba(12,20,36,0.10)');
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(orb.x, orb.y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      function drawArtwork(art, highlight, selected) {
        let poly = [];
        if (art.plane === 'back') {
          poly = [
            projectPoint(art.x - art.w / 2, art.y - art.h / 2, art.z),
            projectPoint(art.x + art.w / 2, art.y - art.h / 2, art.z),
            projectPoint(art.x + art.w / 2, art.y + art.h / 2, art.z),
            projectPoint(art.x - art.w / 2, art.y + art.h / 2, art.z)
          ];
        } else if (art.plane === 'left') {
          poly = [
            projectPoint(art.x, art.y - art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y - art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z - art.w / 2)
          ];
        } else {
          poly = [
            projectPoint(art.x, art.y - art.h / 2, art.z + art.w / 2),
            projectPoint(art.x, art.y - art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z - art.w / 2),
            projectPoint(art.x, art.y + art.h / 2, art.z + art.w / 2)
          ];
        }
        if (poly.some((p) => !p)) return null;

        const frameStroke = highlight ? 'rgba(125,211,252,0.96)' : selected ? 'rgba(192,132,252,0.88)' : 'rgba(255,255,255,0.12)';
        const frameLine = highlight ? 2.6 : selected ? 2 : 1;
        drawPolygon(poly, 'rgba(91,74,54,0.98)', frameStroke, frameLine);

        const center = {
          x: (poly[0].x + poly[1].x + poly[2].x + poly[3].x) / 4,
          y: (poly[0].y + poly[1].y + poly[2].y + poly[3].y) / 4
        };
        const inner = poly.map((p) => ({ x: lerp(p.x, center.x, 0.1), y: lerp(p.y, center.y, 0.1) }));
        const grad = ctx.createLinearGradient(inner[0].x, inner[0].y, inner[2].x, inner[2].y);
        grad.addColorStop(0, art.color);
        grad.addColorStop(1, '#0f172a');
        drawPolygon(inner, grad, highlight ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.08)', 1);

        const glowAlpha = highlight ? 0.22 : selected ? 0.15 : 0.08;
        ctx.fillStyle = 'rgba(255,255,255,' + glowAlpha.toFixed(3) + ')';
        ctx.beginPath();
        ctx.arc(center.x, center.y, 8, 0, Math.PI * 2);
        ctx.fill();

        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(255,255,255,0.94)';
        ctx.font = 'bold 13px Inter, sans-serif';
        ctx.fillText(art.title, center.x, center.y - 4);
        ctx.fillStyle = 'rgba(215,224,244,0.78)';
        ctx.font = '12px Inter, sans-serif';
        ctx.fillText(art.artist, center.x, center.y + 14);

        return poly;
      }

      function drawRoom() {
        const rect = scenePanel.getBoundingClientRect();
        ctx.clearRect(0, 0, rect.width, rect.height);
        hudCtx.clearRect(0, 0, rect.width, rect.height);

        const bg = ctx.createLinearGradient(0, 0, 0, rect.height);
        bg.addColorStop(0, '#07111f');
        bg.addColorStop(1, '#030814');
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, rect.width, rect.height);

        const gazeDx = gaze.x - 0.5;
        const gazeDy = gaze.y - 0.5;

        if (state.focusedArtworkId) {
          const art = findArtworkById(state.focusedArtworkId);
          if (art) {
            state.focusTransition = lerp(state.focusTransition, 1, 0.08);

            if (art.plane === 'back') {
              cameraTargets.x = art.x * 0.28;
              cameraTargets.y = 1.60 - (art.y - 2.0) * 0.18;
              cameraTargets.z = 1.2;
              cameraTargets.yaw = clamp(art.x * 0.038, -0.23, 0.23);
              cameraTargets.pitch = clamp(-(art.y - 2.0) * 0.18, -0.12, 0.12);
              cameraTargets.focal = 980;
            } else if (art.plane === 'left') {
              cameraTargets.x = -1.45;
              cameraTargets.y = 1.60;
              cameraTargets.z = 0.8;
              cameraTargets.yaw = -0.42;
              cameraTargets.pitch = 0.00;
              cameraTargets.focal = 1020;
            } else {
              cameraTargets.x = 1.45;
              cameraTargets.y = 1.60;
              cameraTargets.z = 0.8;
              cameraTargets.yaw = 0.42;
              cameraTargets.pitch = 0.00;
              cameraTargets.focal = 1020;
            }

            cameraTargets.yaw += gazeDx * 0.10;
            cameraTargets.pitch += -gazeDy * 0.08;
          }
        } else {
          state.focusTransition = lerp(state.focusTransition, 0, 0.08);
          cameraTargets.x = gazeDx * 1.35;
          cameraTargets.y = 1.62 - gazeDy * 0.42;
          cameraTargets.z = -1.6 + Math.abs(gazeDx) * 0.08;
          cameraTargets.yaw = gazeDx * 0.55;
          cameraTargets.pitch = -gazeDy * 0.18;
          cameraTargets.focal = 710 + Math.abs(gazeDx) * 40;
        }

        camera.x = lerp(camera.x, cameraTargets.x, 0.08);
        camera.y = lerp(camera.y, cameraTargets.y, 0.08);
        camera.z = lerp(camera.z, cameraTargets.z, 0.08);
        camera.yaw = lerp(camera.yaw, cameraTargets.yaw, 0.08);
        camera.pitch = lerp(camera.pitch, cameraTargets.pitch, 0.08);
        camera.focal = lerp(camera.focal, cameraTargets.focal, 0.08);

        const floor = [
          projectPoint(-5, 0, 0),
          projectPoint(5, 0, 0),
          projectPoint(5, 0, 10),
          projectPoint(-5, 0, 10)
        ];
        const ceiling = [
          projectPoint(-5, 4, 0),
          projectPoint(5, 4, 0),
          projectPoint(5, 4, 10),
          projectPoint(-5, 4, 10)
        ];
        const leftWall = [
          projectPoint(-5, 0, 0),
          projectPoint(-5, 0, 10),
          projectPoint(-5, 4, 10),
          projectPoint(-5, 4, 0)
        ];
        const rightWall = [
          projectPoint(5, 0, 0),
          projectPoint(5, 0, 10),
          projectPoint(5, 4, 10),
          projectPoint(5, 4, 0)
        ];
        const backWall = [
          projectPoint(-5, 0, 10),
          projectPoint(5, 0, 10),
          projectPoint(5, 4, 10),
          projectPoint(-5, 4, 10)
        ];

        drawPolygon(ceiling, 'rgba(11,18,35,0.92)', 'rgba(255,255,255,0.05)', 1);
        drawPolygon(leftWall, 'rgba(15,25,44,0.95)', 'rgba(255,255,255,0.06)', 1);
        drawPolygon(rightWall, 'rgba(12,22,39,0.95)', 'rgba(255,255,255,0.06)', 1);
        drawPolygon(backWall, 'rgba(16,27,48,0.96)', 'rgba(255,255,255,0.06)', 1);
        drawPolygon(floor, 'rgba(22,36,54,0.99)', 'rgba(255,255,255,0.05)', 1);

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

        const spotlight = projectPoint((gaze.x - 0.5) * 3.0, 3.4, 4.8);
        if (spotlight) {
          const grd = ctx.createRadialGradient(spotlight.x, spotlight.y, 0, spotlight.x, spotlight.y, rect.width * 0.34);
          grd.addColorStop(0, 'rgba(125,211,252,0.24)');
          grd.addColorStop(0.5, 'rgba(125,211,252,0.06)');
          grd.addColorStop(1, 'rgba(125,211,252,0)');
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(spotlight.x, spotlight.y, rect.width * 0.34, 0, Math.PI * 2);
          ctx.fill();
        }

        drawPedestal(-1.8, 3.0, 'rgba(125,211,252,0.96)');
        drawPedestal(1.8, 3.35, 'rgba(192,132,252,0.96)');

        projectedArtworks = [];
        artworks.forEach((art) => {
          const poly = drawArtwork(
            art,
            state.hoveredArtworkId === art.id,
            state.selectedArtworkId === art.id || state.focusedArtworkId === art.id
          );
          if (poly) projectedArtworks.push({ art, poly });
        });

        const gazePx = { x: gaze.x * rect.width, y: gaze.y * rect.height };
        hudCtx.strokeStyle = 'rgba(255,255,255,0.09)';
        hudCtx.lineWidth = 1;
        hudCtx.beginPath();
        hudCtx.moveTo(gazePx.x, 0);
        hudCtx.lineTo(gazePx.x, rect.height);
        hudCtx.moveTo(0, gazePx.y);
        hudCtx.lineTo(rect.width, gazePx.y);
        hudCtx.stroke();

        const ringRadius = 22 + state.focusTransition * 10;
        hudCtx.strokeStyle = state.focusedArtworkId ? 'rgba(52,211,153,0.64)' : 'rgba(125,211,252,0.45)';
        hudCtx.lineWidth = 2;
        hudCtx.beginPath();
        hudCtx.arc(gazePx.x, gazePx.y, ringRadius, 0, Math.PI * 2);
        hudCtx.stroke();
      }

      function drawReveal() {
        const rect = scenePanel.getBoundingClientRect();
        revealCtx.clearRect(0, 0, rect.width, rect.height);
        revealCtx.fillStyle = 'rgba(4, 8, 18, 0.44)';
        revealCtx.fillRect(0, 0, rect.width, rect.height);
        revealCtx.globalCompositeOperation = 'destination-out';
        state.revealPoints.forEach((p) => {
          const radius = 100 + p.life * 88;
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

      function addHeatPoint(xNorm, yNorm) {
        const rect = scenePanel.getBoundingClientRect();
        const px = xNorm * rect.width;
        const py = yNorm * rect.height;
        state.heatPoints.push({ x: px, y: py, ts: Date.now() });
        if (state.heatPoints.length > 5500) state.heatPoints.shift();

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
        if (state.revealPoints.length > 300) state.revealPoints.shift();

        statPoints.textContent = String(state.heatPoints.length);
        const qPct = Math.round(gaze.quality * 100);
        qualityText.textContent = qPct + '%';
        qualityHeaderText.textContent = qPct + '%';

        if (state.lastPointPx) {
          const d = Math.hypot(px - state.lastPointPx.x, py - state.lastPointPx.y);
          if (d < 26) {
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

      function eyeCenter(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return { x: avg(pts, 'x'), y: avg(pts, 'y') };
      }

      function eyeBox(landmarks, ids) {
        const pts = ids.map((i) => landmarks[i]).filter(Boolean);
        return {
          minX: Math.min(...pts.map((p) => p.x)),
          maxX: Math.max(...pts.map((p) => p.x)),
          minY: Math.min(...pts.map((p) => p.y)),
          maxY: Math.max(...pts.map((p) => p.y))
        };
      }

      function pointDistance(a, b) {
        return Math.hypot(a.x - b.x, a.y - b.y);
      }

      function calcEAR(landmarks, idx) {
        const p1 = landmarks[idx[0]];
        const p2 = landmarks[idx[1]];
        const p3 = landmarks[idx[2]];
        const p4 = landmarks[idx[3]];
        const p5 = landmarks[idx[4]];
        const p6 = landmarks[idx[5]];
        const vertical = pointDistance(p2, p6) + pointDistance(p3, p5);
        const horizontal = pointDistance(p1, p4);
        return vertical / Math.max(0.0001, 2 * horizontal);
      }

      function mapRawToScreen(rawX, rawY) {
        const m = state.calibration.map;
        const nx = clamp((rawX - m.xMin) / Math.max(0.01, m.xMax - m.xMin), 0, 1);
        const ny = clamp((rawY - m.yMin) / Math.max(0.01, m.yMax - m.yMin), 0, 1);
        return {
          x: clamp(m.marginX + nx * (1 - 2 * m.marginX), 0.02, 0.98),
          y: clamp(m.marginY + ny * (1 - 2 * m.marginY), 0.02, 0.98)
        };
      }

      function updateBlink(ear) {
        blink.ear = ear;
        const now = Date.now();
        const closedRatio = clamp((blink.threshold - ear) / 0.07, 0, 1);
        blinkFill.style.width = (closedRatio * 100).toFixed(1) + '%';

        if (ear < blink.threshold) {
          if (!state.blinkClosed) {
            state.blinkClosed = true;
            state.blinkStartedAt = now;
          }
        } else {
          if (state.blinkClosed) {
            const duration = now - state.blinkStartedAt;
            state.blinkClosed = false;
            if (duration >= 65 && duration <= 380 && now > blink.cooldownUntil) {
              state.blinkCount += 1;
              blink.cooldownUntil = now + 420;
              blinkText.textContent = String(state.blinkCount);
              statBlinks.textContent = String(state.blinkCount);
              toggleFocusByBlink();
            }
          }
        }
      }

      function updateHoverAndDwell(now) {
        const rect = scenePanel.getBoundingClientRect();
        const gazePx = { x: gaze.x * rect.width, y: gaze.y * rect.height };
        const hit = projectedArtworks.find((entry) => pointInPolygon(gazePx, entry.poly));

        if (!hit) {
          state.hoveredArtworkId = null;
          state.hoverStartTs = now;
          dwellFill.style.width = '0%';
          hoverText.textContent = '
