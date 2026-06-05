/** OCR af Bambu Lab farve-labels – finder 5-cifret farve-ID (fx 10100). */

import { withTimeout } from './image_prep.js';

const TESS_BASE = '/lib/tesseract';
const OCR_TIMEOUT_MS = 50000;

function getTesseract() {
  if (!window.Tesseract) {
    throw new Error('OCR-motor mangler – genindlæs siden');
  }
  return window.Tesseract;
}

export function extractColorIds(text) {
  const ids = [];
  const seen = new Set();

  const add = (value) => {
    const code = String(value || '').trim();
    if (!/^[1-9]\d{4}$/.test(code) || seen.has(code)) return;
    seen.add(code);
    ids.push(code);
  };

  for (const match of text.matchAll(/\((\d{5})\)/g)) add(match[1]);
  for (const match of text.matchAll(/(?:ID|id|SKU|sku|No|Nr)[.: ]*(\d{5})/gi)) add(match[1]);
  for (const match of text.matchAll(/\b([1-9]\d{4})\b/g)) add(match[1]);

  return ids;
}

export async function ocrColorIdFromFile(file, onProgress) {
  const Tesseract = getTesseract();
  onProgress?.('Starter OCR på label…');

  const { data } = await withTimeout(
    Tesseract.recognize(file, 'eng', {
      workerPath: `${TESS_BASE}/worker.min.js`,
      corePath: `${TESS_BASE}/tesseract-core.wasm.js`,
      langPath: TESS_BASE,
      gzip: true,
      logger: (msg) => {
        if (msg.status === 'loading tesseract core') onProgress?.('Henter OCR-motor…');
        if (msg.status === 'initializing tesseract') onProgress?.('Starter OCR…');
        if (msg.status === 'loading language traineddata') onProgress?.('Henter sprogdata…');
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
  return { text, ids };
}
