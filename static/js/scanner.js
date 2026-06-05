/** Stregkode-læsning fra billeder og live kamera – offline via lokal ZXing. */

import { withTimeout } from './image_prep.js';

function getZXing() {
  if (!window.ZXing) throw new Error('Stregkode-motor mangler – genindlæs siden helt (luk Safari-fane)');
  return window.ZXing;
}

export function canUseLiveCamera() {
  return !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia);
}

export function getCameraBlockReason() {
  if (!window.isSecureContext) {
    return 'Kamera kræver HTTPS. Åbn https:// adressen (ikke http://) og accepter certifikat-advarslen.';
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'Denne browser understøtter ikke kamera-adgang.';
  }
  return '';
}

export function prepareVideoElement(videoEl) {
  videoEl.hidden = false;
  videoEl.setAttribute('playsinline', 'true');
  videoEl.setAttribute('webkit-playsinline', 'true');
  videoEl.setAttribute('autoplay', 'true');
  videoEl.muted = true;
  videoEl.playsInline = true;
}

function waitForVideoReady(videoEl, timeoutMs = 12000) {
  return new Promise((resolve, reject) => {
    const done = () => {
      if (videoEl.videoWidth > 0 && videoEl.videoHeight > 0) {
        cleanup();
        resolve();
      }
    };
    const fail = (msg) => {
      cleanup();
      reject(new Error(msg));
    };
    const cleanup = () => {
      clearTimeout(timer);
      videoEl.removeEventListener('loadedmetadata', done);
      videoEl.removeEventListener('loadeddata', done);
      videoEl.removeEventListener('playing', done);
      videoEl.removeEventListener('error', onErr);
    };
    const onErr = () => fail('Kameraet kunne ikke vises');
    const timer = setTimeout(() => fail('Kamera timeout – prøv igen'), timeoutMs);

    videoEl.addEventListener('loadedmetadata', done);
    videoEl.addEventListener('loadeddata', done);
    videoEl.addEventListener('playing', done);
    videoEl.addEventListener('error', onErr);
    done();
  });
}

async function requestCameraStream() {
  const attempts = [
    { video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false },
    { video: { facingMode: 'environment' }, audio: false },
    { video: { facingMode: 'user' }, audio: false },
    { video: true, audio: false },
  ];
  let lastErr = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      lastErr = err;
    }
  }
  const name = lastErr?.name || 'Error';
  if (name === 'NotAllowedError') {
    throw new Error('Kamera blokeret – tillad kamera for Safari under Indstillinger → Safari → Kamera');
  }
  if (name === 'NotFoundError') {
    throw new Error('Intet kamera fundet på enheden');
  }
  throw new Error(`Kamera fejlede (${name}) – prøv «Tag billede» i stedet`);
}

async function attachStreamToVideo(videoEl, stream) {
  prepareVideoElement(videoEl);
  videoEl.srcObject = stream;
  try {
    await videoEl.play();
  } catch {
    /* iOS kan alligevel starte efter loadedmetadata */
  }
  await waitForVideoReady(videoEl);
}

function stopStream(videoEl) {
  const stream = videoEl.srcObject;
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
  }
  videoEl.srcObject = null;
  videoEl.hidden = true;
}

async function detectWithBarcodeDetector(source) {
  if (!('BarcodeDetector' in window)) return null;
  try {
    const detector = new BarcodeDetector({
      formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'itf'],
    });
    const codes = await detector.detect(source);
    return codes[0]?.rawValue?.trim() ?? null;
  } catch {
    return null;
  }
}

function decodeCanvasWithZXing(canvas, { invert = false } = {}) {
  const ZXing = getZXing();
  const reader = new ZXing.MultiFormatReader();
  const hints = new Map();
  hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
  if (invert) hints.set(ZXing.DecodeHintType.ALSO_INVERTED, true);
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

async function decodeWithBrowserReader(source) {
  const ZXing = getZXing();
  const reader = new ZXing.BrowserMultiFormatReader();
  let attached = null;
  try {
    let result = null;
    if (source instanceof HTMLImageElement) {
      if (!source.isConnected) {
        attached = source;
        attached.style.position = 'fixed';
        attached.style.left = '-9999px';
        document.body.appendChild(attached);
        await new Promise((res, rej) => {
          if (attached.complete && attached.naturalWidth) return res();
          attached.onload = () => res();
          attached.onerror = () => rej(new Error('Billede kunne ikke indlæses'));
        });
      }
      result = await reader.decodeFromImageElement(source);
    } else if (typeof source === 'string') {
      result = await reader.decodeFromImageUrl(source);
    } else if (source instanceof HTMLCanvasElement) {
      const url = source.toDataURL('image/png');
      result = await reader.decodeFromImageUrl(url);
    }
    reader.reset();
    return result?.getText?.()?.trim() || null;
  } catch {
    reader.reset();
    return null;
  } finally {
    attached?.remove();
  }
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
  canvas.width = Math.max(1, Math.round(sw * cos + sh * sin));
  canvas.height = Math.max(1, Math.round(sw * sin + sh * cos));

  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.rotate(rad);
  ctx.scale(scale, scale);
  ctx.drawImage(img, -w / 2, -h / 2);
  return canvas;
}

export { loadImageFromFile } from './image_prep.js';

function startCanvasScanLoop(videoEl, onDetected) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  let busy = false;

  const timer = setInterval(async () => {
    if (busy || videoEl.readyState < 2 || !videoEl.videoWidth) return;
    busy = true;
    try {
      const w = videoEl.videoWidth;
      const h = videoEl.videoHeight;
      const scale = Math.min(1, 1600 / w);
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

      const native = await detectWithBarcodeDetector(canvas);
      if (native) {
        onDetected(native);
        return;
      }
      const text = decodeCanvasWithZXing(canvas);
      if (text) onDetected(text.trim());
    } catch {
      /* intet fundet i dette frame */
    } finally {
      busy = false;
    }
  }, 250);

  return () => clearInterval(timer);
}

export async function startLiveBarcodeReader(videoEl, onDetected) {
  const reason = getCameraBlockReason();
  if (reason) throw new Error(reason);

  prepareVideoElement(videoEl);
  const stream = await requestCameraStream();
  await attachStreamToVideo(videoEl, stream);

  const stopLoop = startCanvasScanLoop(videoEl, (barcode) => {
    stop();
    onDetected(barcode);
  });

  const stop = () => {
    stopLoop();
    stopStream(videoEl);
  };

  return stop;
}

export async function decodeFromImage(img) {
  const fromNative = await detectWithBarcodeDetector(img);
  if (fromNative) return fromNative;

  const fromBrowser = await decodeWithBrowserReader(img);
  if (fromBrowser) return fromBrowser;

  const scales = [1, 1.5, 2, 0.75, 0.5, 3];
  const rotations = [0, 90, 180, 270];

  for (const scale of scales) {
    for (const rotation of rotations) {
      for (const invert of [false, true]) {
        try {
          const canvas = drawToCanvas(img, { scale, rotation });
          const text = decodeCanvasWithZXing(canvas, { invert });
          if (text) return text.trim();
        } catch {
          /* try next */
        }
      }
    }
  }

  throw new Error(
    'Ingen stregkode fundet. Hold kameraet tæt på, med god belysning, og uden refleksioner.'
  );
}

export async function decodeFromFile(file) {
  const fromFileDetector = await detectWithBarcodeDetector(file);
  if (fromFileDetector) return fromFileDetector;

  const { loadImageFromFile: loadImg } = await import('./image_prep.js');
  const img = await loadImg(file);
  return decodeFromImage(img);
}

export async function decodeFromFileViaServer(file) {
  const body = new FormData();
  body.append('file', file);
  const res = await withTimeout(
    fetch('/api/decode', { method: 'POST', body }),
    25000,
    'Server timeout – prøv «Scan farve-label» eller indtast farve-ID manuelt',
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Server kunne ikke læse stregkoden');
  if (!data.barcode) throw new Error('Ingen stregkode fundet på serveren');
  return data.barcode;
}
