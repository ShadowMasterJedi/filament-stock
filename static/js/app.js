import {
  canUseLiveCamera,
  decodeFromFile,
  loadImageFromFile,
} from './scanner.js';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let currentBarcode = null;
let liveStream = null;
let liveScanTimer = null;
let inventoryCache = [];

const toast = (msg) => {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2400);
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Serverfejl');
  return data;
}

function switchView(name) {
  $$('.view').forEach((v) => v.classList.remove('active'));
  $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.view === name));
  $(`#view-${name}`).classList.add('active');
  if (name !== 'scan') stopLiveScan();
  if (name === 'home') refreshDashboard();
  if (name === 'inventory') refreshInventory();
}

$$('.tab').forEach((btn) => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function renderSummary(stats) {
  $('#stats-pill').textContent = `${stats.total_spools} spoler`;
  $('#summary-cards').innerHTML = `
    <div class="stat-card"><div class="value">${stats.total_spools}</div><div class="label">Spoler i alt</div></div>
    <div class="stat-card"><div class="value">${stats.sku_count}</div><div class="label">Produkttyper</div></div>
  `;

  const max = Math.max(...stats.by_material.map((m) => m.spools), 1);
  $('#material-bars').innerHTML = stats.by_material.map((m) => `
    <div class="material-row">
      <div class="head"><span>${m.material}</span><span>${m.spools} spoler · ${m.skus} typer</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${(m.spools / max) * 100}%"></div></div>
    </div>
  `).join('') || '<p class="hint">Ingen filament registreret endnu.</p>';

  $('#recent-scans').innerHTML = stats.recent_scans.map((s) => `
    <div class="recent-item">
      <strong>${s.brand || s.barcode}</strong>
      <span class="inv-meta">${s.material || '–'} ${s.color || ''} · ${s.delta > 0 ? '+' : ''}${s.delta} · ${formatTime(s.created_at)}</span>
    </div>
  `).join('') || '<p class="hint">Ingen scanninger endnu.</p>';
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString('da-DK', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

async function refreshDashboard() {
  const stats = await api('/api/stats');
  renderSummary(stats);
  inventoryCache = (await api('/api/inventory')).items;
  renderPhotoStrip();
}

function renderPhotoStrip() {
  const strip = $('#photo-strip');
  const withPhotos = inventoryCache.filter((i) => i.photo_count > 0).slice(0, 8);
  if (!withPhotos.length) {
    strip.innerHTML = '<p class="hint">Tag billeder under Scan for at se dem her.</p>';
    return;
  }
  strip.innerHTML = withPhotos.map((i) => `
    <div>
      <div class="inv-meta">${i.brand} ${i.color}</div>
      <div class="qty-badge" style="margin-top:0.3rem;width:fit-content">${i.quantity}×</div>
    </div>
  `).join('');
}

function renderInventory(items) {
  const q = $('#search').value.trim().toLowerCase();
  const filtered = items.filter((i) => {
    if (!q) return true;
    const hay = `${i.barcode} ${i.brand} ${i.material} ${i.color} ${i.location}`.toLowerCase();
    return hay.includes(q);
  });

  $('#inventory-list').innerHTML = filtered.map((i) => `
    <article class="inv-card">
      <div class="color-swatch" style="background:${i.color_hex}"></div>
      <div>
        <div class="inv-title">${i.brand || 'Ukendt mærke'} · ${i.material}</div>
        <div class="inv-meta">${i.color || '–'} · ${i.weight_g}g · ${i.location || 'ingen placering'}</div>
        <div class="inv-meta">${i.barcode}</div>
      </div>
      <div class="qty-badge">${i.quantity}</div>
    </article>
  `).join('') || '<p class="hint">Intet matcher søgningen.</p>';
}

async function refreshInventory() {
  inventoryCache = (await api('/api/inventory')).items;
  renderInventory(inventoryCache);
}

$('#search').addEventListener('input', () => renderInventory(inventoryCache));

async function loadMaterials() {
  const { materials } = await api('/api/materials');
  $('#material-select').innerHTML = materials.map((m) => `<option value="${m}">${m}</option>`).join('');
}

function showScanResult(barcode) {
  currentBarcode = barcode;
  $('#scan-result').hidden = false;
  $('#result-barcode').textContent = barcode;
}

async function lookupBarcode(barcode) {
  return api('/api/scan', {
    method: 'POST',
    body: JSON.stringify({ barcode, delta: 0 }),
  });
}

async function handleBarcode(barcode, { uploadPhoto = null, addQty = 0 } = {}) {
  if (!barcode) return;
  showScanResult(barcode);

  const result = await lookupBarcode(barcode);

  if (uploadPhoto) {
    await uploadPhotoFile(uploadPhoto, barcode);
  }

  if (!result.known) {
    $('#known-actions').hidden = true;
    $('#register-form').hidden = false;
    const form = $('#register-form');
    form.barcode.value = barcode;
    form.quantity.value = 1;
    setStatus('Ny stregkode – udfyld og gem');
    return;
  }

  $('#register-form').hidden = true;
  $('#known-actions').hidden = false;
  if (addQty) {
    const { item } = await api('/api/scan', {
      method: 'POST',
      body: JSON.stringify({ barcode, delta: addQty, source: 'photo' }),
    });
    updateKnownUI(item);
    toast(`+${addQty} → nu ${item.quantity} spoler`);
  } else {
    updateKnownUI(result.item);
    toast(`${result.item.brand || barcode}: ${result.item.quantity} spoler`);
  }
}

function updateKnownUI(item) {
  $('#result-item').textContent = `${item.brand} · ${item.material} · ${item.color}`;
  $('#result-qty').textContent = item.quantity;
}

function setStatus(msg) {
  $('#scan-status').textContent = msg;
}

async function adjust(delta) {
  if (!currentBarcode) return;
  const { item } = await api('/api/scan', {
    method: 'POST',
    body: JSON.stringify({ barcode: currentBarcode, delta, source: delta > 0 ? 'manual+' : 'manual-' }),
  });
  updateKnownUI(item);
  toast(`${delta > 0 ? '+' : ''}${delta} → nu ${item.quantity}`);
}

$('#btn-plus').addEventListener('click', () => adjust(1));
$('#btn-minus').addEventListener('click', () => adjust(-1));

$('#register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = Object.fromEntries(fd.entries());
  payload.weight_g = Number(payload.weight_g);
  payload.quantity = Number(payload.quantity);
  const { item } = await api('/api/filament', { method: 'POST', body: JSON.stringify(payload) });
  $('#register-form').hidden = true;
  $('#known-actions').hidden = false;
  updateKnownUI(item);
  toast('Gemt i lager');
});

async function showImagePreview(file) {
  const img = await loadImageFromFile(file);
  const preview = $('#scan-preview');
  preview.innerHTML = '';
  img.className = 'preview-img';
  preview.appendChild(img);
}

async function uploadPhotoFile(file, barcode) {
  const body = new FormData();
  body.append('file', file);
  if (barcode) body.append('barcode', barcode);
  const res = await fetch('/api/photo', { method: 'POST', body });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Kunne ikke uploade billede');
  return data;
}

async function processPhotoFile(file) {
  if (!file) return;
  setStatus('Viser billede og læser stregkode…');
  try {
    await showImagePreview(file);
    const barcode = await decodeFromFile(file);
    setStatus(`Fundet: ${barcode}`);
    await handleBarcode(barcode, { uploadPhoto: file, addQty: 1 });
  } catch (err) {
    setStatus(err.message);
    toast(err.message);
    try {
      await showImagePreview(file);
      await uploadPhotoFile(file);
      toast('Billede gemt – indtast stregkode manuelt nedenfor');
    } catch {
      /* ignore */
    }
  }
}

for (const id of ['photo-camera', 'photo-album']) {
  $(`#${id}`).addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    processPhotoFile(file);
  });
}

$('#btn-manual').addEventListener('click', () => {
  const code = $('#manual-barcode').value.trim();
  if (!code) {
    toast('Indtast en stregkode');
    return;
  }
  handleBarcode(code, { addQty: 0 });
});

$('#manual-barcode').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#btn-manual').click();
});

function stopLiveScan() {
  if (liveScanTimer) {
    clearInterval(liveScanTimer);
    liveScanTimer = null;
  }
  if (liveStream) {
    liveStream.getTracks().forEach((t) => t.stop());
    liveStream = null;
  }
  const video = $('#scan-video');
  video.srcObject = null;
  video.classList.remove('active');
}

async function startLiveScan() {
  if (!canUseLiveCamera()) {
    toast('Live kamera virker ikke over HTTP fra iPhone – brug «Tag billede»');
    return;
  }
  stopLiveScan();
  setStatus('Starter kamera…');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
      audio: false,
    });
    liveStream = stream;
    const video = $('#scan-video');
    video.srcObject = stream;
    video.classList.add('active');
    await video.play();

    if ('BarcodeDetector' in window) {
      const detector = new BarcodeDetector({
        formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e'],
      });
      liveScanTimer = setInterval(async () => {
        if (video.readyState < 2) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length) {
            stopLiveScan();
            const barcode = codes[0].rawValue;
            setStatus(`Scannet: ${barcode}`);
            await handleBarcode(barcode);
            await adjust(1);
          }
        } catch {
          /* continue */
        }
      }, 400);
      setStatus('Peg kameraet mod stregkoden');
      return;
    }
    setStatus('Live-scan ikke understøttet her – brug «Tag billede»');
  } catch {
    setStatus('Kamera blokeret – brug «Tag billede af stregkode»');
    toast('Brug «Tag billede» i stedet');
    stopLiveScan();
  }
}

$('#btn-live-scan').addEventListener('click', startLiveScan);

function setupScanUi() {
  const liveDetails = $('#live-scan-details');
  if (canUseLiveCamera()) {
    liveDetails.hidden = false;
    setStatus('Brug «Tag billede» – det virker bedst fra iPhone over LAN');
  } else {
    liveDetails.hidden = true;
    setStatus('iPhone over LAN: brug «Tag billede» eller indtast stregkode manuelt. Live kamera kræver HTTPS.');
  }
}

async function init() {
  setupScanUi();
  try {
    await api('/api/health');
    await loadMaterials();
    await refreshDashboard();
  } catch (err) {
    $('#subtitle').textContent = 'Kan ikke nå serveren';
    toast(err.message);
  }
}

init();
