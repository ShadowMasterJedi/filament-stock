# Filament Stock – Delivery Summary

**Dato:** 5. juni 2026  
**Projekt:** `/home/per/Projects/filament-stock`  
**GitHub:** https://github.com/ShadowMasterJedi/filament-stock  
**Status:** Funktionel LAN-webapp – klar til daglig brug fra iPhone

---

## Hvad er leveret

Mobil-først **filament-lager** med HTTPS, stregkode-scanning, Bambu Lab-integration og **server-side OCR** af farve-labels. Kør på Linux-server og brug fra iPhone på samme netværk.

### Kernefunktioner

| Funktion | Status |
|----------|--------|
| SQLite-lager (`data/filament.db`) | ✅ |
| Dashboard (spoler, materialer, seneste scans) | ✅ |
| Lagerliste med søgning på farve-ID | ✅ |
| Live kamera-scan (ZXing, HTTPS påkrævet) | ✅ |
| Tag billede af stregkode (server + client decode) | ✅ |
| **Scan farve-label (OCR)** – server RapidOCR | ✅ |
| **Auto-gem fra farve-ID** – ingen manuel stregkode | ✅ |
| Bambu Lab-katalog (EU store + seed EAN) | ✅ |
| +1 / −1 pr. produkt | ✅ |
| Billede-upload fra iPhone | ✅ |
| HTTPS med self-signed cert (`./gen-cert.sh`) | ✅ |
| HEIC/HEIF-billeder (pillow-heif) | ✅ |
| Billedkomprimering før scan (max 1600px) | ✅ |

### Scan-flow

1. **Stregkode** – «Tag billede» eller live kamera → server (`zxing-cpp`) → fallback ZXing i browser
2. **Farve-ID** – «Scan farve-label (OCR)» → server (`rapidocr-onnxruntime`) → fallback Tesseract i browser
3. Ved fund med +1 oprettes produktet **automatisk** i lageret (farve-ID alene er nok – fysisk EAN ikke påkrævet)
4. Bambu-match udfylder mærke, materiale, farve og farve-ID fra katalog

### Vigtige filer

```
filament-stock/
├── server.py              # HTTPS-server + REST API
├── db.py                  # SQLite, Bambu-opslag, auto-registrering
├── decode_image.py        # Server stregkode-decode (zxing-cpp)
├── ocr_label.py           # Server OCR af farve-labels (RapidOCR)
├── bambu_sync.py          # Hent Bambu Lab EU-katalog
├── start.sh               # Starter HTTPS på port 8090
├── gen-cert.sh            # Self-signed TLS-certifikat
├── sync-bambu.sh          # Opdater Bambu-katalog
├── open-firewall.sh       # UFW-regel for LAN
├── data/
│   ├── bambu_barcode_seed.json   # Kendte EAN → farve-ID
│   └── bambu_handles.json        # Produkt-handles til sync
├── static/
│   ├── index.html         # Mobil UI (PWA-venlig)
│   ├── js/
│   │   ├── app.js         # UI-flow, scan, auto-gem
│   │   ├── scanner.js     # Kamera + client stregkode
│   │   ├── label_ocr.js   # OCR (server først, browser backup)
│   │   └── image_prep.js  # Komprimering/timeouts
│   └── lib/
│       ├── zxing.min.js
│       └── tesseract/     # Browser OCR-backup + eng.traineddata.gz
├── delivery_summary.md    # Denne fil
└── README.md
```

### API

| Endpoint | Beskrivelse |
|----------|-------------|
| `GET /api/health` | Server status |
| `GET /api/inventory` | Hele lageret |
| `GET /api/stats` | Dashboard-tal |
| `POST /api/scan` | Scan/tæl (`barcode`/`color_id`, `delta`, `auto_register`) |
| `POST /api/decode` | Stregkode fra billede (multipart) |
| `POST /api/ocr` | Farve-ID fra label-billede (multipart) |
| `POST /api/filament` | Opret/opdater produkt |
| `POST /api/photo` | Upload billede |
| `GET /api/bambu/lookup?barcode=` | Bambu-produktopslag |
| `POST /api/bambu/sync` | Opdater Bambu-katalog |

### Teknologi

- **Backend:** Python 3, SQLite, `zxing-cpp`, `rapidocr-onnxruntime`, Pillow, `pillow-heif`
- **Frontend:** Vanilla JS, ZXing, Tesseract.js (backup), BarcodeDetector API
- **TLS:** Self-signed cert i `certs/` (påkrævet for iPhone-kamera)

### Start

```bash
cd ~/Projects/filament-stock
pip install -r requirements.txt
./sync-bambu.sh          # første gang
./start.sh               # https://<server-ip>:8090
```

På iPhone: åbn **https://** URL, accepter certifikat, tilføj til hjemmeskærm.

---

## Kendte begrænsninger / TODO

| Issue | Prioritet |
|-------|-----------|
| Self-signed cert skal accepteres manuelt på hver ny enhed | Lav |
| Første OCR-kald tager ~5 sek. (model indlæses) | Lav |
| Ikke alle Bambu-varianter har EAN i seed – udvid `bambu_barcode_seed.json` | Medium |
| Browser-OCR (Tesseract WASM) upålidelig på iOS – server-OCR er primær | Info |
| Ingen bruger-login / multi-user | Fremtid |
| Eksport/backup af database | Fremtid |
| Redigering/sletning af produkter i UI | Fremtid |

---

## Session-historik (kort)

1. Oprettet filament-lager med scan, dashboard og SQLite
2. HTTPS + iPhone-kamera (sort skærm løst med TLS)
3. Bambu Lab-katalog og farve-ID i stedet for SKU
4. Server decode + OCR; fix af hæng på store HEIC-billeder
5. Server-side RapidOCR (Tesseract sprogfil var korrupt HTML)
6. Auto-gem fra farve-ID uden krav om manuel stregkode
