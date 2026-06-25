# FilamentScraper

LAN tool that scrapes filament prices from **Bambu Lab EU** and **SUNLU EU**, caches them locally, and shows a mobile-friendly comparison UI.

Part of the [Filament Stock](../README.md) / NxGenLab ecosystem.

**Docs:** [delivery_summary.md](delivery_summary.md) · [User guide](docs/USER_GUIDE.md)

**GitHub:** https://github.com/ShadowMasterJedi/filament-stock/tree/main/filamentscraper

## Features

- **Bambu Lab** — variant prices, sales, 10-roll bulk tiers, in-stock status (`eu.store.bambulab.com`)
- **SUNLU** — Shopify EU store, MOQ deals, in-stock status (`de.store.sunlu.com`)
- **Compare tab** — hero best deal + per-material Bambu vs SUNLU tiles
- **Rabatkøb tab** — volume discount offers in the same tile layout
- **Catalog** — search, filters (1 kg, in stock, discount, best €/kg)
- **Deals engine** — price drops vs history, max-discount buys
- **Cron** — optional 2× daily scrape (06:00 / 18:00)
- **NxGenLab UI** — splash, help, LAN QR code
- **Zero pip deps** — Python 3 standard library only

## Quick start

```bash
cd ~/Projects/filament-stock/filamentscraper
chmod +x start.sh scrape.sh install-cron.sh
./start.sh
```

Open **http://localhost:8095** or **http://\<your-lan-ip\>:8095**.

Use the **QR** button to open the app on your phone (same WiFi).

First start runs a full scrape (Bambu ~1 minute).

### Scheduled scrape

```bash
./install-cron.sh
```

Log: `data/scrape.log`

### Manual scrape

```bash
./scrape.sh
# or
python3 scrape.py
```

Options:

```bash
python3 scrape.py --sunlu-only
python3 scrape.py --bambu-only
python3 scrape.py --bambu-max 5   # debug: limit Bambu pages
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Server status |
| `GET /api/prices` | Cached prices, deals, max-discount buys |
| `GET /api/info` | LAN URL for QR |
| `GET /api/qr` | QR PNG image |
| `POST /api/refresh` | Start background scrape |

## Files

| Path | Role |
|------|------|
| `server.py` | HTTP server + API |
| `scrape.py` | CLI scrape entry |
| `scrapers/` | Bambu, SUNLU, deals |
| `static/` | Web UI |
| `data/` | Cache + logs (gitignored) |

## Notes

- Prices are **EUR** — direct €/kg comparison between stores.
- Respect store rate limits; use **Opdater** sparingly.
- Stock filter requires at least one scrape after upgrading.

## License

MIT — see [LICENSE](LICENSE).
