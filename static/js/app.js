import {
  canUseLiveCamera,
  decodeFromFile,
  decodeFromFileViaServer,
  decodeFromImage,
  getCameraBlockReason,
  startLiveBarcodeReader,
} from './scanner.js';
import { prepareScanImage } from './image_prep.js';
import { ocrColorIdFromFile, preloadOcrWorker } from './label_ocr.js';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let currentBarcode = null;
let liveScanStop = null;
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

function colorIdLabel(item) {
  return item.bambu_code || '–';
}

function renderInventory(items) {
  const q = $('#search').value.trim().toLowerCase();
  const filtered = items.filter((i) => {
    if (!q) return true;
    const hay = `${i.bambu_code} ${i.store_sku} ${i.brand} ${i.material} ${i.color} ${i.barcode} ${i.location}`.toLowerCase();
    return hay.includes(q);
  });

  $('#inventory-list').innerHTML = filtered.map((i) => `
    <article class="inv-card">
      <div class="color-swatch" style="background:${i.color_hex}"></div>
      <div>
        <div class="inv-title">${i.brand || 'Ukendt mærke'} · ${i.material}</div>
        <div class="inv-meta">${i.color || '–'} · ${i.weight_g}g · ${i.location || 'ingen placering'}</div>
        <div class="inv-meta">Farve-ID ${colorIdLabel(i)}</div>
      </div>
      <div class="qty-badge">${i.quantity}</div>
    </article>
  `).join('') || '<p class="hint">Intet matcher farve-ID søgningen.</p>';
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

function showScanResult(code, colorId = '') {
  currentBarcode = code;
  $('#scan-result').hidden = false;
  $('#result-barcode').textContent = colorId ? colorId : code;
}

function resetBambuHint() {
  const hint = $('#bambu-hint');
  hint.hidden = true;
  hint.textContent = '';
}

function prefillBambuForm(bambu) {
  const form = $('#register-form');
  form.brand.value = bambu.brand || 'Bambu Lab';
  form.material.value = bambu.material || 'PLA';
  form.color.value = bambu.color || '';
  form.weight_g.value = bambu.weight_g || 1000;
  form.bambu_code.value = bambu.bambu_code || '';
  form.store_sku.value = bambu.store_sku || '';
  const hint = $('#bambu-hint');
  hint.hidden = false;
  hint.textContent = `Bambu Lab: ${bambu.product_line} · ${bambu.color} · Farve-ID ${bambu.bambu_code}${bambu.spool_type ? ` · ${bambu.spool_type}` : ''}`;
}

function storageCodeFor(code, bambu = null) {
  if (bambu) return bambu.barcode || bambu.bambu_code || code;
  return code;
}

async function saveNewFilament(code, { bambu = null, quantity = 1 } = {}) {
  const colorId = bambu?.bambu_code || code;
  const payload = {
    barcode: storageCodeFor(code, bambu),
    bambu_code: colorId,
    store_sku: bambu?.store_sku || '',
    brand: bambu?.brand || 'Bambu Lab',
    material: bambu?.material || 'PLA',
    color: bambu?.color || '',
    weight_g: Number(bambu?.weight_g || 1000),
    quantity,
  };
  const { item } = await api('/api/filament', { method: 'POST', body: JSON.stringify(payload) });
  return item;
}

function showKnownItem(item, { bambu = null, addQty = 0, code = '' } = {}) {
  $('#register-form').hidden = true;
  $('#known-actions').hidden = false;
  updateKnownUI(item);
  if (bambu) {
    toast(`Gemt: ${bambu.product_line} ${bambu.color}`);
  } else if (addQty) {
    toast(`+${addQty} → nu ${item.quantity} spoler`);
  } else {
    toast(`${item.brand || code}: ${item.quantity} spoler`);
  }
}

async function handleBarcode(code, { uploadPhoto = null, addQty = 0, source = null } = {}) {
  if (!code) return;
  resetBambuHint();

  const scanSource = source || (addQty ? 'photo' : 'lookup');
  const result = await api('/api/scan', {
    method: 'POST',
    body: JSON.stringify({
      barcode: code,
      color_id: code,
      sku: code,
      delta: addQty || 0,
      source: scanSource,
      auto_register: true,
    }),
  });

  const displayColorId = result.item?.bambu_code || result.color_id || result.sku || result.bambu?.bambu_code || code;
  let item = result.item || null;
  let storageCode = item?.barcode || storageCodeFor(code, result.bambu);

  if (!result.known && addQty > 0) {
    item = await saveNewFilament(code, { bambu: result.bambu, quantity: addQty });
    storageCode = item.barcode;
    result.known = true;
  }

  showScanResult(storageCode, displayColorId);
  currentBarcode = storageCode;

  if (uploadPhoto && item) {
    await uploadPhotoFile(uploadPhoto, storageCode);
  }

  if (!result.known) {
    $('#known-actions').hidden = true;
    $('#register-form').hidden = false;
    const form = $('#register-form');
    form.barcode.value = storageCodeFor(code, result.bambu);
    form.quantity.value = 1;
    form.bambu_code.value = result.bambu?.bambu_code || code;
    form.store_sku.value = result.bambu?.store_sku || '';
    if (result.bambu) {
      prefillBambuForm(result.bambu);
      setStatus('Bambu Lab produkt fundet – tjek og gem');
      toast(`Bambu: ${result.bambu.product_line} ${result.bambu.color}`);
      return;
    }
    setStatus('Nyt produkt – udfyld og gem');
    return;
  }

  showKnownItem(item, { bambu: result.bambu, addQty, code });
}

function updateKnownUI(item) {
  const colorId = item.bambu_code ? `${item.bambu_code} · ` : '';
  $('#result-item').textContent = `${colorId}${item.brand} · ${item.material} · ${item.color}`;
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

async function showImagePreview(previewImg) {
  stopLiveScan();
  const preview = $('#scan-preview');
  $('#scan-help').hidden = true;
  $('#scan-video').hidden = true;
  preview.querySelectorAll('.preview-img').forEach((el) => el.remove());
  previewImg.className = 'preview-img';
  preview.appendChild(previewImg);
  return previewImg;
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

async function lookupBambuColorId(colorId) {
  return api(`/api/bambu/lookup?barcode=${encodeURIComponent(colorId)}`);
}

async function resolveColorIdFromOcr(file) {
  const { ids } = await ocrColorIdFromFile(file, setStatus);
  if (!ids.length) {
    throw new Error('Ingen farve-ID fundet på label. Tag et tydeligt billede af teksten «(10100)».');
  }

  for (const id of ids) {
    const res = await lookupBambuColorId(id);
    if (res.found) return { id, bambu: res.product };
  }
  return { id: ids[0], bambu: null };
}

async function decodeBarcodeFromPhoto(file, previewImg = null) {
  try {
    return await decodeFromFileViaServer(file);
  } catch (serverErr) {
    setStatus('Prøver lokal stregkode-læsning…');
    try {
      if (previewImg) return await decodeFromImage(previewImg);
      return await decodeFromFile(file);
    } catch {
      throw new Error(
        `${serverErr.message}. Brug «Scan farve-label» eller indtast farve-ID manuelt.`,
      );
    }
  }
}

async function decodeFromPhoto(file, previewImg, { labelOnly = false } = {}) {
  if (!labelOnly) {
    const barcode = await decodeBarcodeFromPhoto(file, previewImg);
    return { type: 'barcode', value: barcode };
  }

  const { id } = await resolveColorIdFromOcr(file);
  return { type: 'color_id', value: id };
}

async function processPhotoFile(file, { labelOnly = false } = {}) {
  if (!file) {
    toast('Ingen fil valgt');
    return;
  }

  let prepared = null;
  let originalFile = file;

  try {
    setStatus('Komprimerer billede…');
    prepared = await prepareScanImage(file);
    await showImagePreview(prepared.previewImg);
    setStatus(labelOnly ? 'Læser farve-label…' : 'Læser stregkode…');

    const result = await decodeFromPhoto(prepared.jpegFile, prepared.previewImg, { labelOnly });
    const label = result.type === 'color_id' ? `Farve-ID ${result.value}` : result.value;
    setStatus(`Fundet: ${label}`);
    await handleBarcode(result.value, {
      uploadPhoto: originalFile,
      addQty: 1,
      source: labelOnly ? 'ocr' : 'photo',
    });
  } catch (err) {
    setStatus(err.message || 'Kunne ikke læse billede');
    toast(err.message || 'Kunne ikke læse billede');
    try {
      if (!prepared) prepared = await prepareScanImage(file);
      await showImagePreview(prepared.previewImg);
      await uploadPhotoFile(originalFile);
      toast('Billede gemt – indtast farve-ID manuelt');
    } catch {
      /* ignore */
    }
  }
}

function bindPhotoInput(id, options = {}) {
  const input = $(`#${id}`);
  if (!input) return;
  input.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    processPhotoFile(file, options);
  });
}

bindPhotoInput('photo-camera');
bindPhotoInput('photo-album');
bindPhotoInput('label-camera', { labelOnly: true });
$('#btn-photo-camera')?.addEventListener('click', () => $('#photo-camera').click());
$('#btn-label-camera')?.addEventListener('click', () => $('#label-camera').click());
$('#btn-photo-album')?.addEventListener('click', () => $('#photo-album').click());

$('#btn-manual').addEventListener('click', () => {
  const colorId = $('#manual-color-id').value.trim();
  if (!colorId) {
    toast('Indtast et farve-ID');
    return;
  }
  handleBarcode(colorId, { addQty: 0 });
});

$('#manual-color-id').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#btn-manual').click();
});

function resetScanPreview() {
  $('#scan-help').hidden = false;
  $('#scan-video').hidden = true;
  $('#btn-stop-live').hidden = true;
  $('#btn-live-scan').hidden = false;
}

function stopLiveScan() {
  if (liveScanStop) {
    liveScanStop();
    liveScanStop = null;
  }
  resetScanPreview();
}

async function startLiveScan() {
  const blockReason = getCameraBlockReason();
  if (blockReason) {
    setStatus(blockReason);
    toast(blockReason);
    return;
  }

  stopLiveScan();
  $('#scan-help').hidden = true;
  $('#btn-live-scan').hidden = true;
  $('#btn-stop-live').hidden = false;
  setStatus('Starter kamera… Tillad adgang hvis iPhone spørger.');

  const video = $('#scan-video');
  try {
    liveScanStop = await startLiveBarcodeReader(video, async (barcode) => {
      stopLiveScan();
      setStatus(`Scannet: ${barcode}`);
      await handleBarcode(barcode);
      await adjust(1);
    });
    setStatus('Peg kameraet mod stregkoden');
  } catch (err) {
    stopLiveScan();
    setStatus(err.message);
    toast(err.message);
  }
}

$('#btn-live-scan').addEventListener('click', startLiveScan);
$('#btn-stop-live').addEventListener('click', stopLiveScan);

function setupScanUi() {
  const liveControls = $('#live-scan-controls');
  const secureWarning = $('#secure-warning');
  const httpsLink = $('#https-link');
  const onHttps = location.protocol === 'https:';

  if (!onHttps) {
    const httpsUrl = `https://${location.host}${location.pathname}`;
    httpsLink.href = httpsUrl;
    httpsLink.textContent = httpsUrl;
    secureWarning.hidden = false;
  } else {
    secureWarning.hidden = true;
  }

  preloadOcrWorker();

  if (canUseLiveCamera()) {
    liveControls.hidden = false;
    setStatus('Tryk «Start live scan» eller brug «Tag billede»');
  } else {
    liveControls.hidden = true;
    setStatus(getCameraBlockReason() || 'Brug «Tag billede» eller indtast stregkode manuelt');
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

window.addEventListener('error', (e) => {
  console.error(e.error || e.message);
  toast(`App-fejl: ${e.message}`);
});
window.addEventListener('unhandledrejection', (e) => {
  console.error(e.reason);
  toast(`Fejl: ${e.reason?.message || e.reason}`);
});

init();
