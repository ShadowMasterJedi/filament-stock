# FilamentScraper — Delivery Summary

**Version:** 1.0.0  
**Date:** June 2026  
**Author:** NxGenLab  
**Repository:** [github.com/ShadowMasterJedi/filament-stock](https://github.com/ShadowMasterJedi/filament-stock) (`filamentscraper/` subfolder)  
**Status:** Functional LAN price compare — ready for daily use

---

## 1. Project description

**FilamentScraper** is a small Python LAN tool in the NxGenLab filament lifecycle stack. It scrapes filament prices from **Bambu Lab EU** and **SUNLU EU**, caches results locally, and serves a mobile-friendly web UI for comparing €/kg, volume discounts, and in-stock offers.

Typical use: run on a home server or NUC alongside [Filament Stock](../README.md); open from phone on the same WiFi to check deals before ordering.

Design goals:

- **No pip dependencies** — Python 3 standard library only for scraping and server
- **EUR comparison** — both stores scraped in euro
- **Volume pricing** — SUNLU MOQ (often 3 rolls) and Bambu 10× 1 kg bulk tiers
- **NxGenLab UI** — dark theme, splash screen, help dialog, LAN QR code

---

## 2. Delivered features

### 2.1 Scrapers

| Source | Store | Data |
|--------|-------|------|
| Bambu Lab | `eu.store.bambulab.com` | Variant prices, sale prices, bulk tiers (4/6/10 rolls), `in_stock` from `isSoldOut` |
| SUNLU | `de.store.sunlu.com` | Shopify collection JSON, MOQ from titles, `in_stock` from `available` |

### 2.2 Web UI (Danish)

| Tab | Purpose |
|-----|---------|
| **Sammenlign** | Hero best deal + material comparison tiles (Bambu vs SUNLU €/kg) |
| **Rabatkøb** | Volume discount offers in same tile layout; grouped by material |
| **Katalog** | Search, material/brand chips, filters (1 kg, in stock, discount, best €/kg) |

Other UI:

- Boot splash (~900 ms, NxGenLab branding)
- Help dialog (`?`)
- QR dialog — LAN IP URL for phone access (`QR`)
- Manual refresh + background scrape polling

### 2.3 Scheduling & cache

| Item | Detail |
|------|--------|
| Cron | `install-cron.sh` — scrape at **06:00** and **18:00** |
| Cache | `data/prices_cache.json` |
| History | `data/price_history.json` — price drop detection |
| Log | `data/scrape.log` |

### 2.4 API

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Server status |
| `GET /api/prices` | Cached items, deals, max-discount buys |
| `GET /api/info` | LAN `page_url` for QR (replaces `localhost`) |
| `GET /api/qr` | PNG QR code for current LAN URL |
| `POST /api/refresh` | Trigger background scrape (~1 min) |

---

## 3. File layout

```
filamentscraper/
├── server.py              # HTTP server + API
├── scrape.py              # CLI scrape entry
├── start.sh               # Start server (port 8095)
├── scrape.sh              # Manual scrape wrapper
├── install-cron.sh        # 2× daily cron
├── scrapers/
│   ├── bambu.py           # Bambu EU Next.js/RSC parser
│   ├── sunlu.py           # SUNLU Shopify parser
│   ├── deals.py           # Deals + max-discount logic
│   └── http_util.py       # Shared fetch helpers
├── static/                # Web UI (HTML/CSS/JS)
├── data/                  # Cache + logs (gitignored except .gitkeep)
├── docs/USER_GUIDE.md     # End-user guide (English)
├── README.md
├── delivery_summary.md    # This file
└── LICENSE                # MIT
```

---

## 4. Quick start

```bash
cd ~/Projects/filament-stock/filamentscraper
chmod +x start.sh scrape.sh install-cron.sh
./start.sh
```

Open **http://localhost:8095** or **http://\<lan-ip\>:8095** from your phone (use **QR** in the UI).

First run performs a full scrape (Bambu ~1 minute due to rate limiting).

---

## 5. Known limitations / TODO

| Issue | Priority |
|-------|----------|
| Bambu scrape is slow (~1 min full catalog) | Info |
| Store HTML/API changes may break parsers | Medium |
| No integration with Filament Stock inventory DB yet | Future |
| QR image generation needs server outbound HTTPS (api.qrserver.com) | Low |
| Self-signed / HTTP only — no TLS in this sub-tool | Low |

---

## 6. Ecosystem

Part of the NxGenLab filament lifecycle:

**DryBox** → **Filament Stock** (inventory) → **FilamentScraper** (prices) → print bench (dual feeder, FlowZero)
