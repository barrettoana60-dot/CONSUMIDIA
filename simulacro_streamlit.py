import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Simulacro — Cubo 3D com Eye Tracking Real", page_icon="👁️", layout="wide")

with st.sidebar:
    st.header("Controles")
    cube_size = st.slider("Tamanho do cubo", 140, 420, 260)
    points_per_axis = st.slider("Pontos por eixo", 6, 18, 10)
    depth_layers = st.slider("Camadas de profundidade", 6, 18, 10)
    optical_strength = st.slider("Força da ilusão óptica", 0.0, 1.2, 0.45, 0.01)
    follow_strength = st.slider("Força de seguimento do olhar", 0.0, 1.5, 0.85, 0.01)
    quat_strength = st.slider("Força da rotação quaternion", 0.0, 2.0, 0.75, 0.01)
    point_size = st.slider("Tamanho dos microspontos", 1, 8, 3)
    heat_decay = st.slider("Decaimento do calor", 0.900, 0.999, 0.985, 0.001)
    tracking_smoothing = st.slider("Suavização do tracking", 0.01, 0.50, 0.14, 0.01)
    st.markdown("---")
    st.markdown("**Como usar**")
    st.markdown("1. Clique em **Iniciar tracking**")
    st.markdown("2. Permita a câmera")
    st.markdown("3. Faça a calibração olhando para os 5 pontos")
    st.markdown("4. Observe o cubo reagindo ao olhar")
    st.markdown("5. Gere o PDF no botão interno da cena")

html = f"""
<!DOCTYPE html>
<html lang=\"pt-br\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
<title>Simulacro</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0; background: #070b14; color: #dfe9ff;
    font-family: Inter, Segoe UI, Arial, sans-serif;
  }}
  #app {{ padding: 10px; }}
  #topbar {{
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px;
    background: rgba(10,16,30,.9); border: 1px solid rgba(90,150,255,.25);
    padding: 10px; border-radius: 14px;
  }}
  button {{
    background: linear-gradient(135deg,#1d4ed8,#2563eb); color: white; border: 0;
    border-radius: 10px; padding: 10px 14px; cursor: pointer; font-weight: 600;
  }}
  button.secondary {{ background: linear-gradient(135deg,#0f172a,#1e293b); border:1px solid #334155; }}
  button.warn {{ background: linear-gradient(135deg,#7c2d12,#b45309); }}
  #status {{ padding: 8px 12px; border-radius: 10px; background:#0f172a; border:1px solid #334155; }}
  #layout {{ display:grid; grid-template-columns: 1.45fr .9fr; gap: 12px; }}
  #sceneWrap {{
    position: relative; height: 760px; border-radius: 18px; overflow: hidden;
    border: 1px solid rgba(96,165,250,.25); background:
      radial-gradient(circle at 50% 15%, rgba(30,64,175,.22), transparent 25%),
      radial-gradient(circle at 50% 120%, rgba(14,165,233,.12), transparent 40%),
      linear-gradient(180deg,#040812,#08101e 60%, #060b16 100%);
    box-shadow: 0 0 60px rgba(37,99,235,.10), inset 0 0 40px rgba(59,130,246,.08);
  }}
  #threeCanvas, #heatCanvas, #hudCanvas {{ position:absolute; inset:0; width:100%; height:100%; display:block; }}
  #heatCanvas, #hudCanvas {{ pointer-events:none; }}
  #videoPanel {{
    background: rgba(10,16,30,.92); border: 1px solid rgba(96,165,250,.25);
    border-radius: 18px; padding: 10px;
  }}
  #video {{ width:100%; border-radius: 14px; background:#000; aspect-ratio: 4/3; object-fit: cover; }}
  #metrics {{ display:grid; grid-template-columns: repeat(2,1fr); gap:8px; margin-top:10px; }}
  .metric {{ background:#0f172a; border:1px solid #334155; border-radius: 12px; padding: 10px; }}
  .metric b {{ display:block; font-size: 1.1rem; color:#fff; margin-top: 4px; }}
  #log {{
    margin-top: 10px; padding: 10px; min-height: 120px; white-space: pre-wrap; line-height: 1.4;
    background:#09111f; border:1px solid #1f2d44; border-radius:12px; font-size: .92rem;
  }}
  #calib {{
    position:absolute; inset:0; display:none; align-items:center; justify-content:center; z-index:10;
    background: rgba(3,8,18,.45); backdrop-filter: blur(2px);
  }}
  .calib-point {{
    position:absolute; width:22px; height:22px; border-radius:50%; border:2px solid #fff;
    background: rgba(59,130,246,.55); box-shadow: 0 0 18px rgba(96,165,250,.85);
    transform: translate(-50%,-50%);
  }}
  #legend {{ margin-top:8px; font-size:.9rem; color:#b7c9f8; }}
</style>
</head>
<body>
<div id=\"app\">
  <div id=\"topbar\">
    <button id=\"startBtn\">Iniciar tracking</button>
    <button id=\"calibBtn\" class=\"secondary\">Calibrar 5 pontos</button>
    <button id=\"resetHeatBtn\" class=\"secondary\">Resetar calor</button>
    <button id=\"pdfBtn\" class=\"warn\">Baixar PDF</button>
    <div id=\"status\">Aguardando início…</div>
  </div>

  <div id=\"layout\">
    <div id=\"sceneWrap\">
      <canvas id=\"threeCanvas\"></canvas>
      <canvas id=\"heatCanvas\"></canvas>
      <canvas id=\"hudCanvas\"></canvas>
      <div id=\"calib\"></div>
    </div>

    <div id=\"videoPanel\">
      <video id=\"video\" autoplay playsinline muted></video>
      <div id=\"metrics\">
        <div class=\"metric\">Tracking<b id=\"mTracking\">OFF</b></div>
        <div class=\"metric\">Amostras<b id=\"mSamples\">0</b></div>
        <div class=\"metric\">Gaze X/Y<b id=\"mGaze\">0.00 / 0.00</b></div>
        <div class=\"metric\">Depth voxel<b id=\"mDepth\">0</b></div>
        <div class=\"metric\">Ponto pico<b id=\"mPeak\">-</b></div>
        <div class=\"metric\">Calibração<b id=\"mCalib\">Não</b></div>
      </div>
      <div id=\"legend\">
        Tracking no navegador + cubo volumétrico + calor em profundidade + quaternions.
      </div>
      <div id=\"log\">Pronto para iniciar.</div>
    </div>
  </div>
</div>

<script src=\"https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.min.js\"></script>
<script src=\"https://cdn.jsdelivr.net/npm/webgazer@2.0.1/dist/webgazer.min.js\"></script>
<script src=\"https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js\"></script>
<script>
(() => {{
  const CFG = {{
    cubeSize: {cube_size},
    pointsPerAxis: {points_per_axis},
    depthLayers: {depth_layers},
    opticalStrength: {optical_strength},
    followStrength: {follow_strength},
    quatStrength: {quat_strength},
    pointSize: {point_size},
    heatDecay: {heat_decay},
    trackingSmoothing: {tracking_smoothing}
  }};

  const sceneWrap = document.getElementById('sceneWrap');
  const threeCanvas = document.getElementById('threeCanvas');
  const heatCanvas = document.getElementById('heatCanvas');
  const hudCanvas = document.getElementById('hudCanvas');
  const heatCtx = heatCanvas.getContext('2d');
  const hudCtx = hudCanvas.getContext('2d');
  const video = document.getElementById('video');
  const statusEl = document.getElementById('status');
  const logEl = document.getElementById('log');
  const calibEl = document.getElementById('calib');

  const mTracking = document.getElementById('mTracking');
  const mSamples = document.getElementById('mSamples');
  const mGaze = document.getElementById('mGaze');
  const mDepth = document.getElementById('mDepth');
  const mPeak = document.getElementById('mPeak');
  const mCalib = document.getElementById('mCalib');

  let W = sceneWrap.clientWidth;
  let H = sceneWrap.clientHeight;
  threeCanvas.width = heatCanvas.width = hudCanvas.width = W * devicePixelRatio;
  threeCanvas.height = heatCanvas.height = hudCanvas.height = H * devicePixelRatio;
  heatCtx.scale(devicePixelRatio, devicePixelRatio);
  hudCtx.scale(devicePixelRatio, devicePixelRatio);

  const renderer = new THREE.WebGLRenderer({{ canvas: threeCanvas, antialias: true, alpha: true }});
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(W, H, false);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 2000);
  camera.position.set(0, 0, 640);

  const ambient = new THREE.AmbientLight(0x88aaff, 0.9);
  const dir = new THREE.DirectionalLight(0xbfd7ff, 1.15);
  dir.position.set(220, 280, 360);
  scene.add(ambient, dir);

  const cubeGroup = new THREE.Group();
  scene.add(cubeGroup);

  const pts = [];
  const base = [];
  const pointPositions = [];
  const colors = [];
  const heat3D = [];
  const dims = [CFG.pointsPerAxis, CFG.pointsPerAxis, CFG.depthLayers];

  const sx = CFG.cubeSize;
  const sy = CFG.cubeSize;
  const sz = CFG.cubeSize;

  function idx3(x,y,z) {{ return z * dims[0] * dims[1] + y * dims[0] + x; }}

  for (let z = 0; z < dims[2]; z++) {{
    for (let y = 0; y < dims[1]; y++) {{
      for (let x = 0; x < dims[0]; x++) {{
        const px = (x / (dims[0] - 1) - 0.5) * sx;
        const py = (y / (dims[1] - 1) - 0.5) * sy;
        const pz = (z / (dims[2] - 1) - 0.5) * sz;
        base.push([px, py, pz]);
        pointPositions.push(px, py, pz);
        colors.push(0.18, 0.45, 1.00);
        heat3D.push(0);
      }}
    }}
  }}

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(pointPositions, 3));
  geom.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

  const mat = new THREE.PointsMaterial({{
    size: CFG.pointSize,
    vertexColors: true,
    transparent: true,
    opacity: 0.92,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  }});

  const points = new THREE.Points(geom, mat);
  cubeGroup.add(points);

  const box = new THREE.BoxHelper(new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz)), 0x77aaff);
  box.material.transparent = true;
  box.material.opacity = 0.35;
  cubeGroup.add(box);

  let isTracking = false;
  let calibrated = false;
  let calibrationData = [];
  let gazeSmooth = {{ x: 0.5, y: 0.5 }};
  let gazeRaw = {{ x: 0.5, y: 0.5 }};
  let faceFollow = {{ x: 0, y: 0 }};
  let samples = [];

  let heat2D = Array.from({{ length: dims[1] }}, () => Array(dims[0]).fill(0));

  function log(msg) {{
    logEl.textContent = msg + "\n" + logEl.textContent.slice(0, 2500);
  }}

  function setStatus(msg) {{
    statusEl.textContent = msg;
  }}

  function resize() {{
    W = sceneWrap.clientWidth; H = sceneWrap.clientHeight;
    renderer.setSize(W, H, false);
    camera.aspect = W / H; camera.updateProjectionMatrix();
    threeCanvas.width = heatCanvas.width = hudCanvas.width = W * devicePixelRatio;
    threeCanvas.height = heatCanvas.height = hudCanvas.height = H * devicePixelRatio;
    heatCtx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
    hudCtx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  }}
  window.addEventListener('resize', resize);

  function createCalibrationPoints() {{
    calibEl.innerHTML = '';
    const pts = [
      [0.5, 0.5], [0.15, 0.15], [0.85, 0.15], [0.15, 0.85], [0.85, 0.85]
    ];
    pts.forEach((p, i) => {{
      const d = document.createElement('div');
      d.className = 'calib-point';
      d.style.left = (p[0] * 100) + '%';
      d.style.top = (p[1] * 100) + '%';
      d.dataset.x = p[0];
      d.dataset.y = p[1];
      d.dataset.i = i;
      d.addEventListener('click', () => {{
        calibrationData.push({{
          targetX: parseFloat(d.dataset.x),
          targetY: parseFloat(d.dataset.y),
          rawX: gazeRaw.x,
          rawY: gazeRaw.y,
        }});
        d.style.background = 'rgba(16,185,129,.75)';
        d.style.boxShadow = '0 0 20px rgba(16,185,129,.95)';
        log('Ponto de calibração registrado: ' + (i + 1));
        if (calibrationData.length >= 5) {{
          calibrated = true;
          mCalib.textContent = 'Sim';
          calibEl.style.display = 'none';
          setStatus('Calibração concluída');
          log('Calibração concluída com 5 pontos.');
        }}
      }});
      calibEl.appendChild(d);
    }});
  }}

  function applyCalibration(x, y) {{
    if (!calibrated || calibrationData.length < 2) return {{ x, y }};
    const rawXs = calibrationData.map(p => p.rawX);
    const rawYs = calibrationData.map(p => p.rawY);
    const minX = Math.min(...rawXs), maxX = Math.max(...rawXs);
    const minY = Math.min(...rawYs), maxY = Math.max(...rawYs);
    const nx = Math.min(1, Math.max(0, (x - minX) / Math.max(1e-6, (maxX - minX))));
    const ny = Math.min(1, Math.max(0, (y - minY) / Math.max(1e-6, (maxY - minY))));
    return {{ x: nx, y: ny }};
  }}

  function heatColor(v) {{
    const t = Math.max(0, Math.min(1, v));
    const r = Math.min(1, Math.max(0, 1.5 * t));
    const g = Math.min(1, Math.max(0, 1.4 * (1 - Math.abs(t - 0.5) * 2)));
    const b = Math.min(1, Math.max(0, 1.3 * (1 - t)));
    return [r, g, b];
  }}

  function stampHeat3D(nx, ny) {{
    const gx = nx * (dims[0] - 1);
    const gy = (1 - ny) * (dims[1] - 1);
    const gz = Math.round((1 - Math.sqrt((nx - 0.5)**2 + (ny - 0.5)**2) / 0.707) * (dims[2] - 1));

    for (let z = 0; z < dims[2]; z++) {{
      for (let y = 0; y < dims[1]; y++) {{
        for (let x = 0; x < dims[0]; x++) {{
          const d2 = (x - gx) ** 2 + (y - gy) ** 2 + ((z - gz) * 1.25) ** 2;
          const amp = Math.exp(-d2 / 5.0);
          const id = idx3(x, y, z);
          heat3D[id] += amp;
        }}
      }}
    }}
    return gz;
  }}

  function decayHeat() {{
    for (let i = 0; i < heat3D.length; i++) heat3D[i] *= CFG.heatDecay;
  }}

  function updatePointCloud() {{
    const pos = geom.attributes.position.array;
    const col = geom.attributes.color.array;

    const gx = (gazeSmooth.x - 0.5) * 2;
    const gy = -(gazeSmooth.y - 0.5) * 2;

    const qx = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0), gy * CFG.quatStrength * 0.35);
    const qy = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0), gx * CFG.quatStrength * 0.35);
    const qz = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1), faceFollow.x * 0.08);
    const qq = new THREE.Quaternion();
    qq.multiply(qz).multiply(qy).multiply(qx);

    const tmp = new THREE.Vector3();

    let peakVal = -1;
    let peakIdx = 0;

    for (let i = 0; i < base.length; i++) {{
      let [x, y, z] = base[i];
      const rr = Math.sqrt((x/sx)**2 + (y/sy)**2 + (z/sz)**2);
      const optical = (1 - Math.min(1, rr * 1.55)) * CFG.opticalStrength;

      x += gx * optical * 38 * (1 - Math.abs(x) / (sx * 0.6));
      y += gy * optical * 38 * (1 - Math.abs(y) / (sy * 0.6));
      z += (1 - Math.abs(gx) - Math.abs(gy)) * optical * 26;

      tmp.set(x, y, z).applyQuaternion(qq);

      const id3 = i * 3;
      pos[id3 + 0] = tmp.x;
      pos[id3 + 1] = tmp.y;
      pos[id3 + 2] = tmp.z;

      const hv = Math.min(1, heat3D[i] / 10);
      const [r,g,b] = heatColor(hv);
      col[id3 + 0] = 0.18 + r * 0.82;
      col[id3 + 1] = 0.35 + g * 0.65;
      col[id3 + 2] = 0.85 * b + 0.15;

      if (heat3D[i] > peakVal) {{ peakVal = heat3D[i]; peakIdx = i; }}
    }}

    geom.attributes.position.needsUpdate = true;
    geom.attributes.color.needsUpdate = true;

    const pz = Math.floor(peakIdx / (dims[0] * dims[1]));
    const py = Math.floor((peakIdx % (dims[0] * dims[1])) / dims[0]);
    const px = peakIdx % dims[0];
    mPeak.textContent = `${{px+1}},${{py+1}},${{pz+1}}`;
  }}

  function drawHUD() {{
    heatCtx.clearRect(0,0,W,H);
    hudCtx.clearRect(0,0,W,H);

    const gx = gazeSmooth.x * W;
    const gy = gazeSmooth.y * H;

    const grad = heatCtx.createRadialGradient(gx, gy, 0, gx, gy, 90);
    grad.addColorStop(0, 'rgba(255,80,60,0.48)');
    grad.addColorStop(0.35, 'rgba(255,170,60,0.22)');
    grad.addColorStop(1, 'rgba(255,170,60,0)');
    heatCtx.fillStyle = grad;
    heatCtx.beginPath();
    heatCtx.arc(gx, gy, 90, 0, Math.PI*2);
    heatCtx.fill();

    hudCtx.strokeStyle = 'rgba(180,220,255,.85)';
    hudCtx.lineWidth = 1.2;
    hudCtx.beginPath();
    hudCtx.arc(gx, gy, 16, 0, Math.PI*2);
    hudCtx.stroke();
    hudCtx.beginPath();
    hudCtx.moveTo(gx - 26, gy); hudCtx.lineTo(gx + 26, gy);
    hudCtx.moveTo(gx, gy - 26); hudCtx.lineTo(gx, gy + 26);
    hudCtx.stroke();
  }}

  function sampleGaze() {{
    if (!window.webgazer) return;
    const pred = webgazer.getCurrentPrediction();
    if (!pred) return;

    gazeRaw.x = pred.x / window.innerWidth;
    gazeRaw.y = pred.y / window.innerHeight;
    const cal = applyCalibration(gazeRaw.x, gazeRaw.y);

    gazeSmooth.x += (cal.x - gazeSmooth.x) * CFG.trackingSmoothing;
    gazeSmooth.y += (cal.y - gazeSmooth.y) * CFG.trackingSmoothing;

    gazeSmooth.x = Math.max(0, Math.min(1, gazeSmooth.x));
    gazeSmooth.y = Math.max(0, Math.min(1, gazeSmooth.y));

    faceFollow.x += ((gazeSmooth.x - 0.5) * 2 - faceFollow.x) * 0.12;
    faceFollow.y += ((gazeSmooth.y - 0.5) * 2 - faceFollow.y) * 0.12;

    const depthLayer = stampHeat3D(gazeSmooth.x, gazeSmooth.y);

    samples.push({{
      t: performance.now(),
      gazeX: gazeSmooth.x,
      gazeY: gazeSmooth.y,
      depthLayer,
    }});
    if (samples.length > 12000) samples.shift();

    mSamples.textContent = String(samples.length);
    mGaze.textContent = `${{(gazeSmooth.x*2-1).toFixed(2)}} / ${{(-(gazeSmooth.y*2-1)).toFixed(2)}}`;
    mDepth.textContent = String(depthLayer + 1);
  }}

  function animate() {{
    requestAnimationFrame(animate);
    if (isTracking) {{
      decayHeat();
      sampleGaze();
    }}

    cubeGroup.rotation.y += (((gazeSmooth.x - 0.5) * 2) * 0.10 * CFG.followStrength - cubeGroup.rotation.y) * 0.08;
    cubeGroup.rotation.x += ((-(gazeSmooth.y - 0.5) * 2) * 0.10 * CFG.followStrength - cubeGroup.rotation.x) * 0.08;

    camera.position.x += (((gazeSmooth.x - 0.5) * 2) * 85 - camera.position.x) * 0.07;
    camera.position.y += ((-(gazeSmooth.y - 0.5) * 2) * 70 - camera.position.y) * 0.07;
    camera.lookAt(0,0,0);

    updatePointCloud();
    drawHUD();
    renderer.render(scene, camera);
  }}

  async function startTracking() {{
    try {{
      const stream = await navigator.mediaDevices.getUserMedia({{ video: true, audio: false }});
      video.srcObject = stream;

      await webgazer
        .setRegression('ridge')
        .setTracker('TFFacemesh')
        .showVideoPreview(false)
        .showPredictionPoints(false)
        .showFaceOverlay(false)
        .begin();

      isTracking = true;
      mTracking.textContent = 'ON';
      setStatus('Tracking ativo no navegador');
      log('Tracking iniciado com WebGazer.');
    }} catch (err) {{
      setStatus('Erro ao iniciar câmera/tracking');
      log('Erro: ' + err.message);
    }}
  }}

  function resetHeat() {{
    for (let i = 0; i < heat3D.length; i++) heat3D[i] = 0;
    samples = [];
    mSamples.textContent = '0';
    mPeak.textContent = '-';
    log('Mapa de calor resetado.');
  }}

  async function generatePDF() {{
    const {{ jsPDF }} = window.jspdf;
    const pdf = new jsPDF({{ orientation: 'portrait', unit: 'pt', format: 'a4' }});

    const sceneImg = threeCanvas.toDataURL('image/png');
    const heatImg = heatCanvas.toDataURL('image/png');
    const hudImg = hudCanvas.toDataURL('image/png');

    const merge = document.createElement('canvas');
    merge.width = W; merge.height = H;
    const mctx = merge.getContext('2d');

    await new Promise(res => {{
      const i1 = new Image(); const i2 = new Image(); const i3 = new Image();
      let done = 0; const check = () => {{ done++; if (done === 3) res(); }};
      i1.onload = () => {{ mctx.drawImage(i1,0,0,W,H); check(); }};
      i2.onload = () => {{ mctx.drawImage(i2,0,0,W,H); check(); }};
      i3.onload = () => {{ mctx.drawImage(i3,0,0,W,H); check(); }};
      i1.src = sceneImg; i2.src = heatImg; i3.src = hudImg;
    }});

    const merged = merge.toDataURL('image/png');
    const videoShot = document.createElement('canvas');
    videoShot.width = video.videoWidth || 640;
    videoShot.height = video.videoHeight || 480;
    const vs = videoShot.getContext('2d');
    vs.drawImage(video, 0, 0, videoShot.width, videoShot.height);
    const videoImg = videoShot.toDataURL('image/png');

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(18);
    pdf.text('Simulacro — Relatório de tracking ocular 3D', 40, 42);
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'normal');
    pdf.text('Tracking no navegador + cubo volumétrico de microspontos + heatmap em profundidade.', 40, 60);

    pdf.setFont('helvetica', 'bold');
    pdf.text('Métricas', 40, 88);
    pdf.setFont('helvetica', 'normal');
    pdf.text('Amostras: ' + samples.length, 40, 106);
    pdf.text('Tracking: ' + (isTracking ? 'ativo' : 'inativo'), 40, 122);
    pdf.text('Calibrado: ' + (calibrated ? 'sim' : 'não'), 40, 138);
    pdf.text('Pico voxel: ' + mPeak.textContent, 40, 154);
    pdf.text('Gaze atual: ' + mGaze.textContent, 40, 170);

    pdf.addImage(merged, 'PNG', 40, 190, 515, 320);
    pdf.addPage();
    pdf.text('Captura da câmera', 40, 42);
    pdf.addImage(videoImg, 'PNG', 40, 60, 360, 270);

    pdf.text('Interpretação automática', 40, 360);
    const interp =
      'O cubo 3D responde ao olhar do observador com rotação quaternion, deslocamento de perspectiva e deformação óptica dos microspontos. O mapa de calor é acumulado no volume interno do cubo, distribuindo incidência entre largura, altura e profundidade conforme a posição estimada do olhar.';
    pdf.setFontSize(10);
    const lines = pdf.splitTextToSize(interp, 500);
    pdf.text(lines, 40, 380);

    pdf.save('relatorio_simulacro_tracking_3d.pdf');
    log('PDF gerado com sucesso.');
  }}

  document.getElementById('startBtn').addEventListener('click', startTracking);
  document.getElementById('calibBtn').addEventListener('click', () => {{
    calibrationData = [];
    calibrated = false;
    mCalib.textContent = 'Em andamento';
    calibEl.style.display = 'flex';
    createCalibrationPoints();
    setStatus('Calibração ativa');
    log('Calibração iniciada. Clique nos 5 pontos olhando para cada um.');
  }});
  document.getElementById('resetHeatBtn').addEventListener('click', resetHeat);
  document.getElementById('pdfBtn').addEventListener('click', generatePDF);

  animate();
}})();
</script>
</body>
</html>
"""

st.title("👁️ Simulacro — Cubo volumétrico com tracking do observador")
st.caption("Esta versão faz o tracking no navegador e faz o cubo responder ao olhar com pontos 3D em profundidade.")

components.html(html, height=820, scrolling=False)

st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### O que muda aqui")
    st.markdown("- tracking no navegador  \\n- cubo 3D volumétrico de pontos  \\n- calor dentro do volume  \\n- quaternions na rotação  \\n- ilusão óptica dos microspontos")
with col2:
    st.markdown("### Como funciona")
    st.markdown("- WebGazer estima o ponto de olhar em tempo real  \\n- o olhar é calibrado em 5 pontos  \\n- o gaze é convertido em voxel dentro do cubo  \\n- os pontos seguem o observador")
with col3:
    st.markdown("### Observação")
    st.markdown("É um **protótipo inicial real da lógica correta**. O próximo passo seria trocar a regressão do olhar por um modelo próprio e sincronizar os dados no backend.")
