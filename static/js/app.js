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

const SPLASH_MS = 900;

let currentBarcode = null;
let liveScanStop = null;
let inventoryCache = [];
let valueCache = null;
let lowStockCache = null;
let priceAlertsCache = null;

const toast = (msg) => {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2400);
};

function runSplash() {
  const splash = $('#splash');
  if (!splash) return;
  window.setTimeout(() => {
    splash.classList.add('splash-hide');
    splash.addEventListener('transitionend', () => splash.remove(), { once: true });
  }, SPLASH_MS);
}

function pageUrl() {
  return window.location.href.split('#')[0];
}

function qrDisplayUrl(url) {
  return url.replace(/^https?:\/\//, '');
}

function isLocalHost(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  } catch {
    return false;
  }
}

function appHost() {
  const host = window.location.hostname;
  return host === '127.0.0.1' ? 'localhost' : host;
}

function defaultScraperUrl() {
  return `http://${appHost()}:8095/`;
}

function scraperRabatUrl() {
  return `${defaultScraperUrl()}?view=maxrabat`;
}

function defaultStockUrl() {
  const scheme = window.location.protocol === 'http:' ? 'http' : 'https';
  return `${scheme}://${appHost()}:8090/`;
}

async function resolvePageUrl() {
  try {
    const res = await fetch('/api/info');
    if (!res.ok) throw new Error('info failed');
    return await res.json();
  } catch {
    return {
      page_url: pageUrl(),
      scraper_url: defaultScraperUrl(),
      stock_url: defaultStockUrl(),
      qr_hint: 'Kunne ikke finde LAN-IP — åbn siden via PC-ens IP i stedet for localhost',
    };
  }
}

function openHelp() {
  const dialog = $('#help-dialog');
  if (dialog?.showModal) dialog.showModal();
}

async function openQr() {
  const dialog = $('#qr-dialog');
  const img = $('#qr-img');
  if (!dialog || !img) return;

  const info = await resolvePageUrl();
  const url = info.page_url || pageUrl();
  const hintEl = $('#qr-hint');

  img.src = `/api/qr?size=160&_=${Date.now()}`;
  img.alt = `QR-kode til ${url}`;
  const urlEl = $('#qr-url');
  if (urlEl) {
    urlEl.textContent = qrDisplayUrl(url);
    urlEl.classList.toggle('qr-warn', isLocalHost(url));
  }
  if (hintEl) {
    hintEl.textContent = isLocalHost(url)
      ? (info.qr_hint || 'Åbn siden via PC-ens LAN-IP — ikke localhost')
      : (info.qr_hint || 'Scan med telefonen på samme WiFi');
  }

  if (dialog.showModal) dialog.showModal();
}

function bindDialogs() {
  $$('[data-close-dialog]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const dialog = btn.closest('dialog');
      if (dialog) dialog.close();
    });
  });

  ['#help-dialog', '#qr-dialog'].forEach((sel) => {
    const dialog = $(sel);
    if (!dialog) return;
    dialog.addEventListener('click', (ev) => {
      if (ev.target === dialog) dialog.close();
    });
  });

  $('#btn-help')?.addEventListener('click', openHelp);
  $('#btn-qr')?.addEventListener('click', openQr);
  $('#btn-settings-help')?.addEventListener('click', openHelp);
  $('#btn-settings-qr')?.addEventListener('click', openQr);
}

async function bindEcoNav() {
  const link = $('#link-prices');
  if (!link) return;
  link.href = defaultScraperUrl();
  try {
    const info = await resolvePageUrl();
    if (info.scraper_url) link.href = info.scraper_url;
  } catch {
    link.href = defaultScraperUrl();
  }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Serverfejl');
  return data;
}

const VIEW_TITLES = {
  home: 'Frontline',
  scan: 'Scan',
  inventory: 'Lager',
  settings: 'Setup',
};

function switchView(name) {
  $$('.view').forEach((v) => v.classList.remove('active'));
  $$('.tab-pill').forEach((t) => t.classList.toggle('active', t.dataset.view === name));
  const viewEl = $(`#view-${name}`);
  if (viewEl) viewEl.classList.add('active');
  const titleEl = $('#page-title');
  if (titleEl && VIEW_TITLES[name]) titleEl.textContent = VIEW_TITLES[name];
  if (name !== 'scan') stopLiveScan();
  if (name === 'home') refreshDashboard();
  if (name === 'inventory') refreshInventory();
  if (name === 'settings') refreshMoonrakerUi();
}

$$('.tab-pill').forEach((btn) => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function formatEuro(amount) {
  if (amount == null || Number.isNaN(amount)) return '—';
  return `€${Number(amount).toFixed(2)}`;
}

function valueForItem(barcode) {
  if (!valueCache?.items) return null;
  return valueCache.items.find((row) => row.barcode === barcode) || null;
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString('da-DK', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

function bindDashboardNav() {
  $$('[data-goto-view]').forEach((btn) => {
    if (btn.dataset.gotoBound) return;
    btn.dataset.gotoBound = '1';
    btn.addEventListener('click', () => switchView(btn.dataset.gotoView));
  });
}

function renderDashboard(stats, value, lowStock, priceAlerts, moonraker) {
  const lowCount = lowStock?.count || 0;
  const alertCount = priceAlerts?.count || 0;
  const pricesOk = !!value?.prices_available;
  const capital = pricesOk ? formatEuro(value.total_eur) : '—';
  const capitalHint = pricesOk
    ? `${value.matched_spools}/${value.total_spools} spoler prissat · Bambu + SUNLU`
    : 'Start FilamentScraper for priser';

  $('#stats-pill').textContent = pricesOk
    ? `${stats.total_spools} spoler · ${formatEuro(value.total_eur)}`
    : `${stats.total_spools} spoler`;

  const subtitle = $('#subtitle');
  if (subtitle) {
    subtitle.textContent = lowCount || alertCount
      ? `${lowCount} lav beholdning · ${alertCount} prisalarmer`
      : 'Dit filament-lager — overblik på ét sted';
  }

  const pricesLink = $('#link-prices')?.href || defaultScraperUrl();
  const heroValue = $('#dash-hero-value');
  const heroSub = $('#dash-hero-sub');
  if (heroValue) heroValue.textContent = capital;
  if (heroSub) heroSub.textContent = capitalHint;

  const rabatLink = $('#dash-rabat-link');
  const pricesDashLink = $('#dash-prices-link');
  if (rabatLink) rabatLink.href = scraperRabatUrl();
  if (pricesDashLink) pricesDashLink.href = pricesLink;

  $('#dash-kpis').innerHTML = `
    <article class="dash-kpi">
      <span class="dash-kpi-value">${stats.total_spools}</span>
      <span class="dash-kpi-label">Spoler</span>
    </article>
    <article class="dash-kpi">
      <span class="dash-kpi-value">${stats.sku_count}</span>
      <span class="dash-kpi-label">Typer</span>
    </article>
    <article class="dash-kpi ${lowCount ? 'warn' : ''}">
      <span class="dash-kpi-value">${lowCount}</span>
      <span class="dash-kpi-label">Lav</span>
    </article>
    <article class="dash-kpi ${alertCount ? 'good' : ''}">
      <span class="dash-kpi-value">${alertCount}</span>
      <span class="dash-kpi-label">Alarmer</span>
    </article>
  `;

  bindDashboardNav();

  renderActionQueue(lowStock, priceAlerts);
  renderMaterialBars(stats, value);
  renderDashFooter(stats, value, moonraker);
}

function renderActionQueue(lowStock, priceAlerts) {
  const panel = $('#dash-frontline-panel');
  const container = $('#dash-action-queue');
  if (!container) return;

  const seen = new Set();
  const queue = [];

  for (const item of lowStock?.items || []) {
    seen.add(item.barcode);
    queue.push({
      kind: item.quantity <= 0 ? 'empty' : 'low',
      sort: item.quantity,
      title: [item.brand || 'Ukendt', item.material].filter(Boolean).join(' · '),
      sub: [item.color || '–', item.bambu_code ? `ID ${item.bambu_code}` : ''].filter(Boolean).join(' · '),
      hint: item.deal_hint || (item.quantity <= 0 ? 'Tom — bestil nu' : '≤1 spole tilbage'),
      badge: item.quantity <= 0 ? 'Tom' : `${item.quantity} stk`,
      rabat: item.scraper_rabat_url,
      prices: item.scraper_url,
      shop: item.product_url,
    });
  }

  for (const item of priceAlerts?.items || []) {
    if (seen.has(item.barcode)) continue;
    queue.push({
      kind: 'alert',
      sort: -1,
      title: [item.brand || 'Ukendt', item.material, item.color].filter(Boolean).join(' · '),
      sub: item.unit_eur != null ? `Nu €${item.unit_eur.toFixed(2)}/spole` : '',
      hint: (item.reasons || []).join(' · '),
      badge: 'Rabat',
      rabat: item.scraper_rabat_url,
      prices: item.scraper_url,
      shop: item.product_url,
    });
  }

  queue.sort((a, b) => a.sort - b.sort);

  if (!queue.length) {
    container.innerHTML = '<p class="dash-empty">Alt ser godt ud — ingen lav beholdning eller prisalarmer.</p>';
    if (panel) panel.hidden = false;
    return;
  }

  if (panel) panel.hidden = false;
  container.innerHTML = queue.map((row) => {
    const kindClass = row.kind === 'empty' ? 'kind-empty' : row.kind === 'low' ? 'kind-low' : 'kind-alert';
    const shop = row.shop
      ? `<a class="dash-queue-link ghost" href="${row.shop}" target="_blank" rel="noopener">Butik</a>`
      : '';
    return `
      <article class="dash-queue-card ${kindClass}">
        <div class="dash-queue-main">
          <span class="dash-queue-badge">${row.badge}</span>
          <div class="dash-queue-title">${row.title}</div>
          <div class="dash-queue-sub">${row.sub}</div>
          <p class="dash-queue-hint">${row.hint}</p>
        </div>
        <div class="dash-queue-actions">
          <a class="dash-queue-link rabat" href="${row.rabat}" target="_blank" rel="noopener">Rabatkøb</a>
          <a class="dash-queue-link" href="${row.prices}" target="_blank" rel="noopener">Priser</a>
          ${shop}
        </div>
      </article>
    `;
  }).join('');
}

function renderMaterialBars(stats, value) {
  const valueByMaterial = {};
  if (value?.by_material) {
    for (const row of value.by_material) {
      valueByMaterial[row.material] = row;
    }
  }
  const mats = stats.by_material || [];
  const max = Math.max(...mats.map((m) => m.spools), 1);
  $('#material-bars').innerHTML = mats.map((m) => {
    const val = valueByMaterial[m.material];
    const valueHint = val?.value_eur ? formatEuro(val.value_eur) : '';
    return `
      <div class="material-row dash-mat-row">
        <div class="head"><span class="dash-mat-name">${m.material}</span><span>${m.spools} · ${valueHint || `${m.skus} typer`}</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${(m.spools / max) * 100}%"></div></div>
      </div>
    `;
  }).join('') || '<p class="hint">Ingen filament registreret endnu.</p>';
}

function renderDashFooter(stats, value, moonraker) {
  const lines = [];
  const recent = stats.recent_scans?.[0];
  if (recent) {
    lines.push(`Seneste: ${recent.brand || recent.barcode} ${recent.delta > 0 ? '+' : ''}${recent.delta} · ${formatTime(recent.created_at)}`);
  }
  if (value?.prices_updated_at) {
    lines.push(`Priser: ${formatTime(value.prices_updated_at)}`);
  }
  if (moonraker?.enabled) {
    if (moonraker.last_error) {
      lines.push(`Moonraker: offline`);
    } else {
      const state = moonraker.print_state || 'ukendt';
      const active = moonraker.active_item
        ? `${moonraker.active_item.material} ${moonraker.active_item.color}`.trim()
        : 'ingen aktiv spole';
      lines.push(`Printer: ${state} · ${active}`);
    }
  }

  const footer = $('#dash-footer');
  if (!footer) return;
  footer.innerHTML = lines.length
    ? lines.map((line) => `<span class="dash-foot-item">${line}</span>`).join('')
    : '<span class="dash-foot-item">Scan en spole for at komme i gang</span>';
}

async function refreshDashboard() {
  const [stats, inv, value, lowStock, priceAlerts, moonraker] = await Promise.all([
    api('/api/stats'),
    api('/api/inventory'),
    api('/api/inventory/value').catch(() => null),
    api('/api/inventory/low-stock').catch(() => null),
    api('/api/inventory/price-alerts').catch(() => null),
    api('/api/moonraker/status').catch(() => null),
  ]);
  valueCache = value;
  lowStockCache = lowStock;
  priceAlertsCache = priceAlerts;
  inventoryCache = inv.items;
  renderDashboard(stats, value, lowStock, priceAlerts, moonraker);
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

  $('#inventory-list').innerHTML = filtered.map((i) => {
    const val = valueForItem(i.barcode);
    const valueLine = val?.matched
      ? `<div class="inv-meta inv-value">${formatEuro(val.value_eur)} · ${formatEuro(val.unit_eur)}/spole</div>`
      : (valueCache?.prices_available ? '<div class="inv-meta inv-unknown">Ingen markedspris</div>' : '');
    return `
    <article class="inv-card">
      <div class="color-swatch" style="background:${i.color_hex}"></div>
      <div>
        <div class="inv-title">${i.brand || 'Ukendt mærke'} · ${i.material}</div>
        <div class="inv-meta">${i.color || '–'} · ${i.weight_g}g · ${i.location || 'ingen placering'}</div>
        <div class="inv-meta">Farve-ID ${colorIdLabel(i)}</div>
        ${valueLine}
      </div>
      <div class="qty-badge">${i.quantity}</div>
    </article>
  `;
  }).join('') || '<p class="hint">Intet matcher farve-ID søgningen.</p>';
}

async function refreshInventory() {
  const [inv, value] = await Promise.all([
    api('/api/inventory'),
    api('/api/inventory/value').catch(() => null),
  ]);
  inventoryCache = inv.items;
  valueCache = value;
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

function moonrakerFilamentLabel(item) {
  return [item.brand, item.material, item.color, `(${item.quantity}×)`].filter(Boolean).join(' · ');
}

async function refreshMoonrakerUi() {
  const select = $('#moonraker-filament');
  if (!select) return;

  if (!inventoryCache.length) {
    try {
      const inv = await api('/api/inventory');
      inventoryCache = inv.items;
    } catch {
      /* ignore */
    }
  }

  const [status, config] = await Promise.all([
    api('/api/moonraker/status').catch(() => null),
    api('/api/moonraker/config').catch(() => null),
  ]);

  const moon = config?.moonraker || {};
  const enabledEl = $('#moonraker-enabled');
  const urlEl = $('#moonraker-url');
  if (enabledEl) enabledEl.checked = !!(status?.enabled ?? moon.enabled);
  if (urlEl) urlEl.value = moon.url || status?.url || 'http://127.0.0.1:7125';

  const active = status?.active_barcode || moon.active_barcode || '';
  const options = ['<option value="">— vælg spole —</option>'];
  for (const item of inventoryCache) {
    if ((item.quantity || 0) <= 0) continue;
    const label = moonrakerFilamentLabel(item);
    const selected = item.barcode === active ? ' selected' : '';
    options.push(`<option value="${item.barcode}"${selected}>${label}</option>`);
  }
  select.innerHTML = options.join('');

  const statusEl = $('#moonraker-status');
  if (!statusEl) return;
  if (!status) {
    statusEl.textContent = 'Moonraker-status ikke tilgængelig';
    return;
  }
  if (!status.enabled) {
    statusEl.textContent = 'Auto −1 er slået fra';
    return;
  }
  if (status.last_error) {
    statusEl.textContent = `Kan ikke nå Moonraker: ${status.last_error}`;
    return;
  }
  const parts = [];
  if (status.print_state) parts.push(`Printer: ${status.print_state}`);
  if (status.active_item) {
    parts.push(`Aktiv: ${moonrakerFilamentLabel(status.active_item)}`);
  } else {
    parts.push('Vælg aktiv spole');
  }
  if (status.last_decrement_at) {
    parts.push(`Sidst −1: ${formatTime(status.last_decrement_at)}`);
  }
  statusEl.textContent = parts.join(' · ');
}

async function saveMoonrakerConfig() {
  const payload = {
    moonraker: {
      enabled: $('#moonraker-enabled')?.checked || false,
      url: ($('#moonraker-url')?.value || '').trim() || 'http://127.0.0.1:7125',
      active_barcode: $('#moonraker-filament')?.value || '',
      auto_decrement: true,
    },
  };
  await api('/api/moonraker/config', { method: 'POST', body: JSON.stringify(payload) });
  toast('Moonraker gemt');
  await refreshMoonrakerUi();
}

async function init() {
  runSplash();
  bindDialogs();
  bindEcoNav();
  bindDashboardNav();
  setupScanUi();
  $('#btn-moonraker-save')?.addEventListener('click', () => {
    saveMoonrakerConfig().catch((err) => toast(err.message));
  });
  try {
    await api('/api/health');
    await loadMaterials();
    await refreshDashboard();
  } catch (err) {
    $('#subtitle').textContent = 'Kan ikke nå serveren — genstart ./start.sh';
    renderDashboard(
      { total_spools: 0, sku_count: 0, by_material: [], recent_scans: [] },
      null,
      null,
      null,
      null,
    );
    const heroSub = $('#dash-hero-sub');
    if (heroSub) heroSub.textContent = err.message || 'Server offline';
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
