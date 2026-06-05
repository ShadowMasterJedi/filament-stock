/** OCR af Bambu Lab farve-labels – server først, browser som backup. */

import { withTimeout } from './image_prep.js';

const OCR_TIMEOUT_MS = 45000;

export function extractColorIds(text) {
  const normalized = String(text || '')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
    .replace(/[Oo]/g, '0')
    .replace(/[lI]/g, '1');

  const ids = [];
  const seen = new Set();

  const add = (value) => {
    const code = String(value || '').trim();
    if (!/^[1-9]\d{4}$/.test(code) || seen.has(code)) return;
    seen.add(code);
    ids.push(code);
  };

  for (const match of normalized.matchAll(/\((\d{5})\)/g)) add(match[1]);
  for (const match of normalized.matchAll(/(?:ID|id|SKU|sku|No|Nr)[.: ]*(\d{5})/gi)) add(match[1]);
  for (const match of normalized.matchAll(/\b([1-9]\d{4})\b/g)) add(match[1]);

  return ids;
}

async function ocrViaServer(file, onProgress) {
  onProgress?.('Sender til server-OCR…');
  const body = new FormData();
  body.append('file', file);
  const res = await withTimeout(
    fetch('/api/ocr', { method: 'POST', body }),
    OCR_TIMEOUT_MS,
    'OCR timeout – indtast farve-ID manuelt (fx 10100)',
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Server-OCR fejlede');
  const ids = Array.isArray(data.ids) ? data.ids : extractColorIds(data.text || '');
  if (!ids.length) {
    throw new Error('Ingen farve-ID fundet på label. Tag et tydeligt billede af teksten «(10100)».');
  }
  return { text: data.text || '', ids };
}

async function ocrViaBrowser(file, onProgress) {
  if (!window.Tesseract) {
    throw new Error('OCR-motor mangler – genindlæs siden');
  }

  onProgress?.('Prøver browser-OCR…');
  const { data } = await withTimeout(
    window.Tesseract.recognize(file, 'eng', {
      workerPath: '/lib/tesseract/worker.min.js',
      corePath: '/lib/tesseract/tesseract-core.wasm.js',
      langPath: '/lib/tesseract',
      gzip: true,
      logger: (msg) => {
        if (msg.status === 'recognizing text') {
          onProgress?.(`OCR ${Math.round((msg.progress || 0) * 100)}%`);
        }
      },
    }),
    OCR_TIMEOUT_MS,
    'OCR timeout – indtast farve-ID manuelt (fx 10100)',
  );

  const text = data?.text || '';
  const ids = extractColorIds(text);
  if (!ids.length) {
    throw new Error('Ingen farve-ID fundet på label. Tag et tydeligt billede af teksten «(10100)».');
  }
  return { text, ids };
}

export function preloadOcrWorker() {
  return null;
}

export async function ocrColorIdFromFile(file, onProgress) {
  try {
    return await ocrViaServer(file, onProgress);
  } catch (serverErr) {
    onProgress?.('Server-OCR fejlede – prøver i browser…');
    try {
      return await ocrViaBrowser(file, onProgress);
    } catch {
      throw serverErr;
    }
  }
}
