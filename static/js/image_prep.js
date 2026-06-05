/** Komprimer og forbered billeder fra iPhone – undgår hang på store HEIC-filer. */

export function withTimeout(promise, ms, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

function loadViaObjectUrl(file, timeoutMs) {
  return withTimeout(
    new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        if (!img.naturalWidth) {
          reject(new Error('Billedet er tomt'));
          return;
        }
        resolve(img);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('Kunne ikke vise billedet'));
      };
      img.src = url;
    }),
    timeoutMs,
    'Billede timeout – prøv igen eller brug «Vælg fra album»',
  );
}

async function loadViaBitmap(file, timeoutMs) {
  if (!window.createImageBitmap) throw new Error('createImageBitmap ikke tilgængelig');
  const bitmap = await withTimeout(
    createImageBitmap(file, { imageOrientation: 'from-image', resizeWidth: 1600 }),
    timeoutMs,
    'Billede timeout – prøv igen',
  );
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext('2d').drawImage(bitmap, 0, 0);
  bitmap.close?.();
  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  return loadViaObjectUrl(dataUrlToFile(dataUrl), Math.min(timeoutMs, 8000));
}

function dataUrlToFile(dataUrl) {
  const [header, data] = dataUrl.split(',');
  const mime = header.match(/:(.*?);/)[1];
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], 'preview.jpg', { type: mime });
}

export async function loadImageFromFile(file) {
  if (!file) throw new Error('Ingen fil valgt');
  try {
    return await loadViaObjectUrl(file, 10000);
  } catch {
    return loadViaBitmap(file, 12000);
  }
}

export async function prepareScanImage(file, maxDim = 1600) {
  const img = await loadImageFromFile(file);
  const w = img.naturalWidth || img.width;
  const h = img.naturalHeight || img.height;
  const scale = Math.min(1, maxDim / Math.max(w, h));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(w * scale));
  canvas.height = Math.max(1, Math.round(h * scale));
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  const blob = await withTimeout(
    new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.82)),
    8000,
    'Kunne ikke komprimere billedet',
  );

  const jpegFile = new File([blob], 'scan.jpg', { type: 'image/jpeg', lastModified: Date.now() });
  const previewImg = await loadViaObjectUrl(jpegFile, 5000);
  return { jpegFile, previewImg, width: canvas.width, height: canvas.height };
}
