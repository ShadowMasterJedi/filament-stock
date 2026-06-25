# Filament Stock – Delivery Summary

**Dato:** 25. juni 2026  
**Projekt:** `/home/per/Projects/filament-stock`  
**GitHub:** https://github.com/ShadowMasterJedi/filament-stock  
**Status:** Funktionel LAN-webapp med FilamentScraper-integration — klar til daglig brug fra iPhone

---

## Hvad er leveret

Mobil-først **filament-lager** med HTTPS, stregkode-scanning, Bambu Lab-integration, **server-side OCR**, **Frontline-dashboard**, **prisintegration** mod FilamentScraper og valgfri **Moonraker** auto-bogføring.

### Kernefunktioner

| Funktion | Status |
|----------|--------|
| SQLite-lager (`data/filament.db`) | ✅ |
| **Frontline-dashboard** (kapital, KPI, handlingsliste, materiale) | ✅ |
| **Pill-nav** Home · Scan · Lager · Setup med ikoner | ✅ |
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

### FilamentScraper-integration

| Funktion | Status |
|----------|--------|
| **Bundet kapital** – Bambu SKU + SUNLU fuzzy match | ✅ |
| **Lav beholdning** (≤1 spole) med Rabatkøb/katalog-links | ✅ |
| **Prisalarmer** på egne farver (rabat, prisfald) | ✅ |
| Eco-nav Lager ↔ Priser med LAN-links | ✅ |
| Delt NxGenLab UI-tema (`shared/ui/nxgenlab.css`) | ✅ |
| Splash, hjælp, QR på begge apps | ✅ |

### Moonraker (Setup)

| Funktion | Status |
|----------|--------|
| Poll `print_stats` via REST | ✅ |
| Auto −1 på aktiv spole ved `complete` | ✅ |
| Konfiguration i `data/config.json` | ✅ |
| UI under Setup-fanen | ✅ |

Se [filamentscraper/delivery_summary.md](filamentscraper/delivery_summary.md).

### Scan-flow

1. **Stregkode** – «Tag billede» eller live kamera → server (`zxing-cpp`) → fallback ZXing i browser
2. **Farve-ID** – «Scan farve-label (OCR)» → server (`rapidocr-onnxruntime`) → fallback Tesseract i browser
3. Ved fund med +1 oprettes produktet **automatisk** i lageret (farve-ID alene er nok)
4. Bambu-match udfylder mærke, materiale, farve og farve-ID fra katalog

### Vigtige filer

```
filament-stock/
├── server.py              # HTTPS-server + REST API
├── db.py                  # SQLite, Bambu-opslag, price_watch_state
├── inventory_value.py     # Bundet kapital, lav beholdning, prisalarmer
├── price_match.py         # Bambu SKU + SUNLU fuzzy pris-match
├── moonraker.py           # Auto −1 ved print færdig
├── app_urls.py            # LAN URLs (Stock HTTPS, Scraper HTTP)
├── decode_image.py        # Server stregkode-decode (zxing-cpp)
├── ocr_label.py           # Server OCR af farve-labels (RapidOCR)
├── bambu_sync.py          # Hent Bambu Lab EU-katalog
├── start.sh               # Starter HTTPS på port 8090
├── shared/ui/nxgenlab.css # Delt NxGenLab design-tokens + komponenter
├── static/
│   ├── index.html         # Frontline UI + pill-nav
│   ├── css/nxgenlab.css   # Kopi af shared tema (statisk serving)
│   └── js/app.js          # Dashboard, scan, moonraker
├── filamentscraper/       # Bambu + SUNLU prissammenligning (port 8095)
├── delivery_summary.md    # Denne fil
└── README.md
```

### API (udvidelser)

| Endpoint | Beskrivelse |
|----------|-------------|
| `GET /api/info` | LAN URL + scraper_url |
| `GET /api/qr` | QR PNG |
| `GET /api/inventory/value` | Bundet kapital |
| `GET /api/inventory/low-stock` | Lav beholdning + scraper-links |
| `GET /api/inventory/price-alerts` | Prisalarmer på egne farver |
| `GET /api/moonraker/status` | Moonraker/printer-status |
| `GET/POST /api/moonraker/config` | Moonraker-indstillinger |

### Teknologi

- **Backend:** Python 3, SQLite, `zxing-cpp`, `rapidocr-onnxruntime`, Pillow, `pillow-heif`
- **Frontend:** Vanilla JS, Frontline dashboard, pill-navigation, ZXing, Tesseract.js (backup)
- **Integration:** FilamentScraper cache/API, Moonraker REST
- **TLS:** Self-signed cert i `certs/` (påkrævet for iPhone-kamera)

### Start

```bash
cd ~/Projects/filament-stock
pip install -r requirements.txt
./sync-bambu.sh          # første gang
./start.sh               # https://<server-ip>:8090

cd filamentscraper && ./start.sh   # http://<server-ip>:8095
```

På iPhone: åbn **https://** URL, accepter certifikat, tilføj til hjemmeskærm.

---

## Kendte begrænsninger / TODO

| Issue | Prioritet |
|-------|-----------|
| Self-signed cert skal accepteres manuelt på hver ny enhed | Lav |
| Prisalarmer kræver 2. scrape for prisfald-baseline | Lav |
| SUNLU fuzzy match er bedst med farvenavn i lageret | Medium |
| Moonraker kræver manuelt valg af aktiv spole | Medium |
| Ikke alle Bambu-varianter har EAN i seed | Medium |
| Ingen bruger-login / multi-user | Fremtid |
| Eksport/backup af database | Fremtid |
| Redigering/sletning af produkter i UI | Fremtid |

---

## Session-historik (kort)

1. Oprettet filament-lager med scan, dashboard og SQLite
2. HTTPS + iPhone-kamera; Bambu Lab-katalog og farve-ID
3. Server decode + OCR; auto-gem fra farve-ID
4. FilamentScraper (Bambu + SUNLU priser, rabatkøb, katalog)
5. UI-harmonisering NxGenLab-tema; Lager ↔ Priser navigation
6. Bundet kapital, lav beholdning, prisalarmer, SUNLU-match
7. Moonraker auto −1; Frontline-dashboard; pill-nav med ikoner
