const MATERIALS = ['PLA', 'PLA+', 'PETG', 'ABS', 'ASA', 'TPU'];
const BRANDS = [
  { id: '', label: 'Alle' },
  { id: 'Bambu Lab', label: 'Bambu' },
  { id: 'SUNLU', label: 'SUNLU' },
];

const state = {
  items: [],
  deals: [],
  maxDiscountBuys: [],
  filtered: [],
  material: '',
  brand: '',
  view: 'overview',
  refreshTimer: null,
};

const SPLASH_MS = 900;

const els = {
  updatedText: document.getElementById('updated-text'),
  statusLine: document.querySelector('.status-line'),
  loadingBar: document.getElementById('loading-bar'),
  refresh: document.getElementById('btn-refresh'),
  badgeRabat: document.getElementById('badge-rabat'),
  heroDeal: document.getElementById('hero-deal'),
  heroContent: document.getElementById('hero-content'),
  compareStrip: document.getElementById('compare-strip'),
  overviewEmpty: document.getElementById('overview-empty'),
  viewOverview: document.getElementById('view-overview'),
  viewMaxRabat: document.getElementById('view-maxrabat'),
  maxrabatList: document.getElementById('maxrabat-list'),
  maxrabatEmpty: document.getElementById('maxrabat-empty'),
  rabatHero: document.getElementById('rabat-hero'),
  rabatHeroContent: document.getElementById('rabat-hero-content'),
  viewList: document.getElementById('view-list'),
  tabs: document.querySelectorAll('.tab'),
  catalogList: document.getElementById('catalog-list'),
  body: document.getElementById('price-body'),
  resultCount: document.getElementById('result-count'),
  q: document.getElementById('filter-q'),
  materialChips: document.getElementById('material-chips'),
  brandChips: document.getElementById('brand-chips'),
  oneKg: document.getElementById('filter-1kg'),
  discountOnly: document.getElementById('filter-discount'),
  inStockOnly: document.getElementById('filter-instock'),
  bestPrice: document.getElementById('filter-best'),
  splash: document.getElementById('splash'),
  helpDialog: document.getElementById('help-dialog'),
  qrDialog: document.getElementById('qr-dialog'),
  qrImg: document.getElementById('qr-img'),
  qrUrl: document.getElementById('qr-url'),
  btnHelp: document.getElementById('btn-help'),
  btnQr: document.getElementById('btn-qr'),
};

function runSplash() {
  if (!els.splash) return;
  window.setTimeout(() => {
    els.splash.classList.add('splash-hide');
    els.splash.addEventListener('transitionend', () => els.splash.remove(), { once: true });
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

function defaultStockUrl() {
  const scheme = window.location.protocol === 'http:' ? 'http' : 'https';
  return `${scheme}://${appHost()}:8090/`;
}

async function resolvePageUrl() {
  try {
    const res = await fetch('/api/info');
    if (!res.ok) throw new Error('info failed');
    const data = await res.json();
    if (data.page_url) return data;
  } catch {
    /* fallback */
  }
  return {
    page_url: pageUrl(),
    scraper_url: defaultScraperUrl(),
    stock_url: defaultStockUrl(),
    qr_hint: 'Kunne ikke finde LAN-IP — åbn siden via PC-ens IP i stedet for localhost',
  };
}

function openHelp() {
  if (!els.helpDialog) return;
  if (typeof els.helpDialog.showModal === 'function') {
    els.helpDialog.showModal();
  }
}

async function openQr() {
  if (!els.qrDialog || !els.qrImg) return;

  const info = await resolvePageUrl();
  const url = info.page_url || pageUrl();
  const hintEl = document.getElementById('qr-hint');

  els.qrImg.src = `/api/qr?size=160&_=${Date.now()}`;
  els.qrImg.alt = `QR-kode til ${url}`;
  if (els.qrUrl) {
    els.qrUrl.textContent = qrDisplayUrl(url);
    els.qrUrl.classList.toggle('qr-warn', isLocalHost(url));
  }
  if (hintEl) {
    hintEl.textContent = isLocalHost(url)
      ? (info.qr_hint || 'Åbn siden via PC-ens LAN-IP — ikke localhost')
      : (info.qr_hint || 'Scan med telefonen på samme WiFi');
  }

  if (typeof els.qrDialog.showModal === 'function') {
    els.qrDialog.showModal();
  }
}

async function bindEcoNav() {
  const link = document.getElementById('link-stock');
  if (!link) return;
  link.href = defaultStockUrl();
  try {
    const info = await resolvePageUrl();
    if (info.stock_url) link.href = info.stock_url;
  } catch {
    link.href = defaultStockUrl();
  }
}

function bindDialogs() {
  document.querySelectorAll('[data-close-dialog]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const dialog = btn.closest('dialog');
      if (dialog) dialog.close();
    });
  });

  [els.helpDialog, els.qrDialog].forEach((dialog) => {
    if (!dialog) return;
    dialog.addEventListener('click', (ev) => {
      if (ev.target === dialog) dialog.close();
    });
  });

  if (els.btnHelp) els.btnHelp.addEventListener('click', openHelp);
  if (els.btnQr) els.btnQr.addEventListener('click', openQr);
}

function fmtEuro(value) {
  if (value == null || Number.isNaN(value)) return '—';
  return `€${Number(value).toFixed(2)}`;
}

function fmtDate(iso) {
  if (!iso) return 'ukendt';
  try {
    return new Date(iso).toLocaleString('da-DK', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function shortBrand(brand) {
  return brand === 'Bambu Lab' ? 'Bambu' : brand === 'SUNLU' ? 'SUNLU' : brand;
}

function brandClass(brand) {
  return brand === 'Bambu Lab' ? 'bambu' : 'sunlu';
}

function effectivePrice(row) {
  return row.sale_price != null ? row.sale_price : row.price;
}

function parseMoq(title) {
  const m = (title || '').match(/\[?\s*MOQ[:\s]*(\d+)\s*Roll/i);
  return m ? Math.max(1, parseInt(m[1], 10)) : 1;
}

function bestVolumeDeal(row) {
  const listUnit = row.price != null ? Number(row.price) : null;
  if (listUnit == null) return null;

  const options = [];
  const saleUnit = row.sale_price != null ? Number(row.sale_price) : listUnit;
  options.push({ moq: 1, unit: saleUnit, source: 'single' });

  const titleMoq = parseMoq(row.product);
  if (titleMoq > 1 && row.sale_price != null) {
    options.push({ moq: titleMoq, unit: Number(row.sale_price), source: 'sunlu_moq' });
  }

  if (row.bulk_unit_price != null && row.bulk_moq) {
    options.push({ moq: Number(row.bulk_moq), unit: Number(row.bulk_unit_price), source: 'bulk' });
  }

  const best = options.reduce((a, b) => (a.unit < b.unit ? a : b));
  return {
    ...best,
    listUnit,
    total: Math.round(best.unit * best.moq * 100) / 100,
    wasTotal: Math.round(listUnit * best.moq * 100) / 100,
    save: Math.round((listUnit - best.unit) * best.moq * 100) / 100,
    discountPct: Math.round((listUnit - best.unit) / listUnit * 1000) / 10,
  };
}

function enrichRow(row) {
  const deal = bestVolumeDeal(row);
  if (deal) {
    const weightG = row.weight_g || 0;
    return {
      ...row,
      moq: deal.moq,
      discount_pct: deal.discountPct,
      bundle_total: deal.total,
      bundle_was_total: deal.wasTotal,
      bundle_save: deal.save,
      max_discount_unit: deal.unit,
      max_discount_source: deal.source,
      max_discount_price_per_kg: weightG
        ? Math.round(deal.unit * 1000 / weightG * 100) / 100
        : row.max_discount_price_per_kg,
    };
  }
  const moq = row.moq != null ? row.moq : parseMoq(row.product);
  const unit = effectivePrice(row);
  const listUnit = row.price != null ? row.price : unit;
  return {
    ...row,
    moq,
    discount_pct: 0,
    bundle_total: unit != null ? Math.round(unit * moq * 100) / 100 : null,
    bundle_was_total: listUnit != null ? Math.round(listUnit * moq * 100) / 100 : null,
    bundle_save: 0,
  };
}

function discountPct(row) {
  if (row.discount_pct != null) return row.discount_pct;
  const deal = bestVolumeDeal(row);
  if (deal && deal.discountPct > 0) return deal.discountPct;
  const price = row.price;
  const sale = row.sale_price;
  if (price == null || sale == null || sale >= price) return 0;
  return Math.round((price - sale) / price * 1000) / 10;
}

function hasDiscount(row) {
  return discountPct(row) >= 10;
}

function bestPricePerKg(row) {
  return row.max_discount_price_per_kg != null ? row.max_discount_price_per_kg : row.price_per_kg;
}

function catalogPricePerKg(row) {
  if (els.bestPrice?.checked) return bestPricePerKg(row);
  return row.price_per_kg;
}

function is1kg(row) {
  return row.weight_g === 1000;
}

function isInStock(row) {
  return row.in_stock !== false;
}

function stockFilterOn() {
  return els.inStockOnly?.checked ?? false;
}

function visibleItems(items = state.items) {
  if (!stockFilterOn()) return items;
  return items.filter(isInStock);
}

function items1kgEur() {
  return visibleItems(state.items).filter((r) => is1kg(r) && r.currency === 'EUR' && r.price_per_kg != null);
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, '&#39;');
}

function shortenProduct(title) {
  return title
    .replace(/^\[MOQ:\s*\d+\s*Rollen?\]\s*/i, '')
    .replace(/^\[MOQ\s*\d+\s*Rolle\]\s*/i, '')
    .trim();
}

function shortenVariant(variant, product) {
  const v = (variant || '').trim();
  if (!v || v === product) return '';
  const parts = v.split('/').map((p) => p.trim());
  if (parts.length >= 2) return parts.slice(1).join(' · ') || parts[0];
  return v;
}

function moqLabel(row) {
  if (row.moq <= 1) return '';
  if (row.max_discount_source === 'bulk') return `min. ${row.moq} stk`;
  return `min. ${row.moq} stk`;
}

function setLoading(on, message) {
  els.loadingBar.hidden = !on;
  els.statusLine?.classList.toggle('loading', on);
  if (on && message && els.updatedText) {
    els.updatedText.textContent = message;
  }
}

/* ——— Navigation ——— */

function setView(view) {
  state.view = view;
  els.tabs.forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  els.viewOverview.classList.toggle('active', view === 'overview');
  els.viewOverview.hidden = view !== 'overview';
  els.viewMaxRabat.classList.toggle('active', view === 'maxrabat');
  els.viewMaxRabat.hidden = view !== 'maxrabat';
  els.viewList.classList.toggle('active', view === 'list');
  els.viewList.hidden = view !== 'list';
}

els.tabs.forEach((tab) => {
  tab.addEventListener('click', () => setView(tab.dataset.view));
});

document.querySelectorAll('[data-goto]').forEach((btn) => {
  btn.addEventListener('click', () => setView(btn.dataset.goto));
});

function openCatalogForMaterial(material) {
  state.material = material;
  buildChips();
  applyFilters();
  setView('list');
}

/* ——— Hero & compare ——— */

function getTopDeal() {
  const buys = stockFilterOn()
    ? state.maxDiscountBuys.filter((b) => isInStock(b.item || b))
    : state.maxDiscountBuys;
  if (buys.length) return buys[0];
  const candidates = visibleItems(state.items)
    .filter((r) => is1kg(r) && hasDiscount(r))
    .sort((a, b) => bestPricePerKg(a) - bestPricePerKg(b));
  return candidates.length ? { item: candidates[0] } : null;
}

function renderHeroBlock(container, row) {
  if (!container || !row) return;
  const ppk = bestPricePerKg(row);
  const moq = row.moq || 1;
  const pct = row.discount_pct || discountPct(row);

  container.innerHTML = `
    <div class="hero-meta">
      <div class="hero-title">${escapeHtml(shortenProduct(row.product))}</div>
      <div class="hero-sub">${escapeHtml(shortenVariant(row.variant, row.product) || row.material)}</div>
      <div class="hero-tags">
        <span class="brand-dot ${brandClass(row.brand)}">${shortBrand(row.brand)}</span>
        ${moq > 1 ? `<span class="moq-chip">${escapeHtml(moqLabel(row))}</span>` : ''}
        ${pct > 0 ? `<span class="disc-chip">-${pct}%</span>` : ''}
      </div>
      <a class="hero-cta" href="${escapeAttr(row.url)}" target="_blank" rel="noopener">Gå til butik →</a>
    </div>
    <div class="hero-price">${fmtEuro(ppk)}<small>/kg</small></div>
  `;
}

function renderHero() {
  const top = getTopDeal();
  if (!top?.item) {
    els.heroDeal.hidden = true;
    return;
  }

  els.heroDeal.hidden = false;
  renderHeroBlock(els.heroContent, top.item);
}

function bestForBrand(matRows, brand) {
  const brandRows = matRows.filter((r) => r.brand === brand);
  if (!brandRows.length) return null;
  const discounted = brandRows.filter((r) => hasDiscount(r));
  const pool = discounted.length ? discounted : brandRows;
  return pool.reduce((best, r) => (bestPricePerKg(r) < bestPricePerKg(best) ? r : best), pool[0]);
}

function renderCompareStrip() {
  const rows = items1kgEur();
  const cards = [];

  for (const mat of MATERIALS) {
    const matRows = rows.filter((r) => r.material === mat);
    if (!matRows.length) continue;

    const bestBambu = bestForBrand(matRows, 'Bambu Lab');
    const bestSunlu = bestForBrand(matRows, 'SUNLU');
    const bambuPrice = bestBambu ? bestPricePerKg(bestBambu) : null;
    const sunluPrice = bestSunlu ? bestPricePerKg(bestSunlu) : null;

    let winner = null;
    let winnerRow = null;
    if (bambuPrice != null && (sunluPrice == null || bambuPrice <= sunluPrice)) {
      winner = 'Bambu';
      winnerRow = bestBambu;
    } else if (sunluPrice != null) {
      winner = 'SUNLU';
      winnerRow = bestSunlu;
    }
    if (!winnerRow) continue;

    const versus = [
      bambuPrice != null ? `Bambu ${fmtEuro(bambuPrice)}` : null,
      sunluPrice != null ? `SUNLU ${fmtEuro(sunluPrice)}` : null,
    ].filter(Boolean).join(' · ');

    cards.push(`
      <button type="button" class="compare-card" data-material="${escapeAttr(mat)}">
        <div class="mat-label">${mat}</div>
        <div class="winner-row">
          <span class="winner">${fmtEuro(bestPricePerKg(winnerRow))}/kg</span>
          <span class="winner-pill ${brandClass(winnerRow.brand)}">${winner}</span>
        </div>
        <div class="versus">${versus}</div>
        ${winnerRow.moq > 1 ? `<div class="moq-hint">${escapeHtml(moqLabel(winnerRow))}</div>` : ''}
      </button>
    `);
  }

  els.compareStrip.innerHTML = cards.length
    ? cards.join('')
    : '<p class="empty-state">Ingen priser at vise endnu.</p>';

  els.compareStrip.querySelectorAll('.compare-card[data-material]').forEach((btn) => {
    btn.addEventListener('click', () => openCatalogForMaterial(btn.dataset.material));
  });

  const hasData = cards.length > 0 || !els.heroDeal.hidden;
  els.overviewEmpty.hidden = hasData;
}

/* ——— Rabatkøb ——— */

function getMaxDiscountBuys() {
  let buys = state.maxDiscountBuys.length ? state.maxDiscountBuys : null;

  if (!buys) {
    const seen = new Set();
    buys = [];
    const candidates = visibleItems(state.items)
      .filter((r) => is1kg(r) && r.currency === 'EUR' && hasDiscount(r))
      .sort((a, b) => bestPricePerKg(a) - bestPricePerKg(b));

    for (const row of candidates) {
      const family = `${row.brand}|${row.material}|${shortenProduct(row.product)}`;
      if (seen.has(family)) continue;
      seen.add(family);
      buys.push({ item: row, material: row.material, moq: row.moq, discount_pct: row.discount_pct });
      if (buys.length >= 16) break;
    }
  } else if (stockFilterOn()) {
    buys = buys.filter((b) => isInStock(b.item || b));
  }

  const q = (els.q?.value || '').trim().toLowerCase();
  if (state.brand || state.material || q) {
    buys = buys.filter((buy) => {
      const row = buy.item || buy;
      if (state.brand && row.brand !== state.brand) return false;
      if (state.material && row.material !== state.material) return false;
      if (q) {
        const hay = `${row.product || ''} ${row.variant || ''} ${row.material || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  return buys;
}

function renderDealTile(buy) {
  const row = buy.item || buy;
  const moq = buy.moq || row.moq || 1;
  const pct = buy.discount_pct || row.discount_pct || 0;
  const ppk = bestPricePerKg(row);
  const name = shortenProduct(row.product);
  const sub = shortenVariant(row.variant, row.product);
  const bundle = row.bundle_total;
  const save = row.bundle_save || 0;

  const bundleLine = moq > 1
    ? `${escapeHtml(moqLabel(row))} · ${fmtEuro(bundle)}`
    : `${fmtEuro(row.max_discount_unit ?? effectivePrice(row))} pr. spole`;

  const saveLine = save > 0 ? ` · spar ${fmtEuro(save)}` : '';

  return `
    <a class="compare-card deal-tile" href="${escapeAttr(row.url)}" target="_blank" rel="noopener">
      <div class="mat-label">${escapeHtml(row.material)} <span class="disc-inline">-${pct}%</span></div>
      <div class="winner-row">
        <span class="winner">${fmtEuro(ppk)}/kg</span>
        <span class="winner-pill ${brandClass(row.brand)}">${shortBrand(row.brand)}</span>
      </div>
      <div class="versus">${escapeHtml(name)}</div>
      ${sub ? `<div class="versus variant-line">${escapeHtml(sub)}</div>` : ''}
      <div class="moq-hint">${bundleLine}${saveLine}</div>
    </a>
  `;
}

function renderMaxRabat() {
  const buys = getMaxDiscountBuys();
  els.badgeRabat.hidden = !buys.length;
  els.badgeRabat.textContent = String(Math.min(buys.length, 99));
  els.maxrabatEmpty.hidden = buys.length > 0;

  const top = buys[0];
  if (top?.item && els.rabatHero && els.rabatHeroContent) {
    els.rabatHero.hidden = false;
    renderHeroBlock(els.rabatHeroContent, top.item);
  } else if (els.rabatHero) {
    els.rabatHero.hidden = true;
  }

  if (!buys.length) {
    els.maxrabatList.innerHTML = '';
    return;
  }

  const grouped = {};
  for (const buy of buys) {
    const mat = buy.material || buy.item?.material || 'Andet';
    grouped[mat] = grouped[mat] || [];
    grouped[mat].push(buy);
  }

  const order = [...MATERIALS, 'Andet'];
  els.maxrabatList.innerHTML = order
    .filter((mat) => grouped[mat]?.length)
    .map((mat) => {
      const tiles = grouped[mat].map((buy) => renderDealTile(buy)).join('');
      return `
        <section class="section-block">
          <div class="section-head">
            <h2>${escapeHtml(mat)}</h2>
            <p class="section-hint">${grouped[mat].length} tilbud · klik for butik</p>
          </div>
          <div class="compare-strip">${tiles}</div>
        </section>
      `;
    })
    .join('');
}

/* ——— Katalog ——— */

function buildChips() {
  const mats = ['', ...MATERIALS.filter((m) => state.items.some((r) => r.material === m))];
  els.materialChips.innerHTML = mats.map((m) => {
    const label = m || 'Alle';
    const active = state.material === m ? ' active' : '';
    return `<button type="button" class="chip${active}" data-material="${escapeAttr(m)}">${escapeHtml(label)}</button>`;
  }).join('');

  els.brandChips.innerHTML = BRANDS.map((b) => {
    const active = state.brand === b.id ? ' active' : '';
    return `<button type="button" class="chip${active}" data-brand="${escapeAttr(b.id)}">${escapeHtml(b.label)}</button>`;
  }).join('');

  els.materialChips.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      state.material = chip.dataset.material;
      buildChips();
      applyFilters();
    });
  });

  els.brandChips.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      state.brand = chip.dataset.brand;
      buildChips();
      applyFilters();
    });
  });
}

function applyFilters() {
  const q = els.q.value.trim().toLowerCase();
  let rows = visibleItems(state.items).slice();

  if (state.brand) rows = rows.filter((r) => r.brand === state.brand);
  if (state.material) rows = rows.filter((r) => r.material === state.material);
  if (els.oneKg.checked) rows = rows.filter((r) => is1kg(r));
  if (els.discountOnly.checked) rows = rows.filter((r) => hasDiscount(r));
  if (q) {
    rows = rows.filter((r) => {
      const hay = `${r.brand} ${r.product} ${r.variant} ${r.material}`.toLowerCase();
      return hay.includes(q);
    });
  }

  rows.sort((a, b) => {
    const ap = catalogPricePerKg(a) ?? 99999;
    const bp = catalogPricePerKg(b) ?? 99999;
    return ap - bp || a.product.localeCompare(b.product);
  });

  state.filtered = rows;
  renderCatalog();
}

function renderProductRow(row) {
  const name = shortenProduct(row.product);
  const sub = shortenVariant(row.variant, row.product);
  const ppk = catalogPricePerKg(row);
  const unit = els.bestPrice.checked && row.max_discount_unit != null
    ? row.max_discount_unit
    : effectivePrice(row);
  const onSale = row.sale_price != null && row.sale_price < row.price;
  const moq = row.moq > 1 ? `<span class="moq-chip">${escapeHtml(moqLabel(row))}</span>` : '';
  const stock = !isInStock(row) ? '<span class="stock-chip">Udsolgt</span>' : '';

  const unitHtml = onSale
    ? `${fmtEuro(row.sale_price)}<span class="price-was">${fmtEuro(row.price)}</span>`
    : fmtEuro(unit);

  return { name, sub, ppk, unitHtml, moq, stock, row };
}

function renderCatalog() {
  const total = state.filtered.length;
  const max = 150;
  const rows = state.filtered.slice(0, max);

  const sortLabel = els.bestPrice.checked ? 'bedste €/kg (inkl. rabat)' : '€/kg';
  els.resultCount.textContent = total
    ? `${Math.min(total, max)} af ${total} vist · sorteret efter ${sortLabel}`
    : 'Ingen match — prøv at fjerne et filter.';

  if (!rows.length) {
    els.catalogList.innerHTML = '<p class="empty-state">Ingen produkter fundet.</p>';
    els.body.innerHTML = '<tr><td colspan="5" class="empty">Ingen produkter fundet.</td></tr>';
    return;
  }

  els.catalogList.innerHTML = rows.map((row) => {
    const p = renderProductRow(row);
    return `
      <article class="catalog-card">
        <div class="product-name">
          <span class="mat-chip">${escapeHtml(row.material)}</span>
          ${escapeHtml(p.name)}
        </div>
        ${p.sub ? `<div class="product-sub">${escapeHtml(p.sub)}</div>` : ''}
        <div class="price-block">
          <div class="ppk">${p.ppk != null ? fmtEuro(p.ppk) : '—'}</div>
          <div class="unit-price">${p.unitHtml}</div>
        </div>
        <div class="card-foot">
          <span class="brand-dot ${brandClass(row.brand)}">${shortBrand(row.brand)} ${p.moq} ${p.stock}</span>
          <a class="row-link" href="${escapeAttr(row.url)}" target="_blank" rel="noopener">Butik →</a>
        </div>
      </article>
    `;
  }).join('');

  els.body.innerHTML = rows.map((row) => {
    const p = renderProductRow(row);
    return `
      <tr>
        <td><span class="brand-dot ${brandClass(row.brand)}">${shortBrand(row.brand)}</span></td>
        <td class="product-cell">
          <div class="name"><span class="tag">${escapeHtml(row.material)}</span>${escapeHtml(p.name)} ${p.stock}</div>
          ${p.sub ? `<div class="sub">${escapeHtml(p.sub)}</div>` : ''}
        </td>
        <td class="num">${p.ppk != null ? fmtEuro(p.ppk) : '—'}</td>
        <td class="num">${p.moq} ${p.unitHtml}</td>
        <td><a class="row-link" href="${escapeAttr(row.url)}" target="_blank" rel="noopener">→</a></td>
      </tr>
    `;
  }).join('');
}

function refreshViews() {
  renderHero();
  renderCompareStrip();
  renderMaxRabat();
  applyFilters();
}

/* ——— Data ——— */

function applyDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const view = params.get('view');
  const material = params.get('material') || '';
  const brand = params.get('brand') || '';
  const q = params.get('q') || '';

  if (material) state.material = material;
  if (brand) state.brand = brand;
  if (q && els.q) els.q.value = q;

  if (view === 'list' || view === 'maxrabat' || view === 'overview') {
    setView(view);
  } else if (material || brand || q) {
    setView('list');
  }

  buildChips();
  refreshViews();
}

async function loadPrices() {
  const res = await fetch('/api/prices');
  const data = await res.json();
  state.items = (data.items || []).map(enrichRow);
  state.deals = data.deals || [];
  state.maxDiscountBuys = data.max_discount_buys || [];

  els.updatedText.textContent = `Opdateret ${fmtDate(data.updated_at)}`;
  setLoading(false);

  buildChips();
  renderHero();
  renderCompareStrip();
  renderMaxRabat();
  applyFilters();

  els.refresh.disabled = !!data.refresh_running;
  if (data.refresh_running) {
    schedulePoll();
  }

  applyDeepLink();
}

function schedulePoll() {
  clearTimeout(state.refreshTimer);
  setLoading(true, 'Henter priser… ca. 1 min');
  state.refreshTimer = setTimeout(async () => {
    try {
      const res = await fetch('/api/prices');
      const data = await res.json();
      state.items = (data.items || []).map(enrichRow);
      state.deals = data.deals || [];
      state.maxDiscountBuys = data.max_discount_buys || [];
      els.updatedText.textContent = `Opdateret ${fmtDate(data.updated_at)}`;
      buildChips();
      renderHero();
      renderCompareStrip();
      renderMaxRabat();
      applyFilters();
      if (data.refresh_running) {
        schedulePoll();
      } else {
        setLoading(false);
        els.refresh.disabled = false;
      }
    } catch (err) {
      setLoading(false);
      els.refresh.disabled = false;
      if (els.updatedText) els.updatedText.textContent = 'Fejl ved opdatering';
    }
  }, 3000);
}

async function triggerRefresh() {
  els.refresh.disabled = true;
  setLoading(true, 'Henter priser… ca. 1 min');
  await fetch('/api/refresh', { method: 'POST' });
  schedulePoll();
}

els.q.addEventListener('input', applyFilters);
els.inStockOnly.addEventListener('change', refreshViews);
els.oneKg.addEventListener('change', applyFilters);
els.discountOnly.addEventListener('change', applyFilters);
els.bestPrice.addEventListener('change', applyFilters);
els.refresh.addEventListener('click', triggerRefresh);

runSplash();
bindDialogs();
bindEcoNav();

setLoading(true, 'Indlæser…');
loadPrices().catch((err) => {
  setLoading(false);
  if (els.updatedText) els.updatedText.textContent = 'Kunne ikke hente data';
  els.overviewEmpty.hidden = false;
  els.overviewEmpty.textContent = `Kunne ikke hente data: ${err.message}`;
  els.catalogList.innerHTML = `<p class="empty-state">${escapeHtml(err.message)}</p>`;
});
