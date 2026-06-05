/** Stregkode-læsning fra billeder – offline via lokal ZXing. */

function getZXing() {
  if (!window.ZXing) throw new Error('Stregkode-motor mangler – genindlæs siden (Ctrl+F5)');
  return window.ZXing;
}

export function canUseLiveCamera() {
  const host = location.hostname;
  const local = host === 'localhost' || host === '127.0.0.1';
  return (location.protocol === 'https:' || local)
    && !!navigator.mediaDevices?.getUserMedia;
}

export function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Kunne ikke vise billedet – prøv et andet format (JPEG/PNG)'));
    };
    img.src = url;
  });
}

function drawToCanvas(img, { scale = 1, rotation = 0 } = {}) {
  const canvas = document.createElement('canvas');
  const w = img.naturalWidth || img.width;
  const h = img.naturalHeight || img.height;
  if (!w || !h) throw new Error('Billedet har ingen størrelse');

  const rad = (rotation * Math.PI) / 180;
  const sin = Math.abs(Math.sin(rad));
  const cos = Math.abs(Math.cos(rad));
  const sw = Math.round(w * scale);
  const sh = Math.round(h * scale);
  canvas.width = Math.round(sw * cos + sh * sin);
  canvas.height = Math.round(sw * sin + sh * cos);

  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.rotate(rad);
  ctx.scale(scale, scale);
  ctx.drawImage(img, -w / 2, -h / 2);
  return canvas;
}

function decodeCanvasWithZXing(canvas) {
  const ZXing = getZXing();
  const reader = new ZXing.MultiFormatReader();
  const hints = new Map();
  hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
  hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
    ZXing.BarcodeFormat.EAN_13,
    ZXing.BarcodeFormat.EAN_8,
    ZXing.BarcodeFormat.CODE_128,
    ZXing.BarcodeFormat.CODE_39,
    ZXing.BarcodeFormat.UPC_A,
    ZXing.BarcodeFormat.UPC_E,
    ZXing.BarcodeFormat.ITF,
  ]);
  reader.setHints(hints);

  const luminance = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
  const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminance));
  return reader.decode(bitmap).getText();
}

async function detectWithBarcodeDetector(source) {
  if (!('BarcodeDetector' in window)) return null;
  try {
    const detector = new BarcodeDetector({
      formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'itf'],
    });
    const codes = await detector.detect(source);
    return codes[0]?.rawValue ?? null;
  } catch {
    return null;
  }
}

export async function decodeFromImage(img) {
  const fromNative = await detectWithBarcodeDetector(img);
  if (fromNative) return fromNative;

  const scales = [1, 1.5, 0.75, 2, 0.5];
  const rotations = [0, 90, 180, 270];

  for (const scale of scales) {
    for (const rotation of rotations) {
      try {
        const canvas = drawToCanvas(img, { scale, rotation });
        const text = decodeCanvasWithZXing(canvas);
        if (text) return text.trim();
      } catch {
        /* try next */
      }
    }
  }

  throw new Error(
    'Ingen stregkode fundet. Tag billedet tættere på, med god belysning, og uden glare.'
  );
}

export async function decodeFromFile(file) {
  const img = await loadImageFromFile(file);
  return decodeFromImage(img);
}
