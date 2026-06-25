# FilamentScraper — User Guide

Compare Bambu Lab and SUNLU filament prices on your local network. All prices are in **EUR** from the EU stores.

---

## Start the app

On your server or PC:

```bash
cd ~/Projects/filament-stock/filamentscraper
./start.sh
```

Open in a browser:

- On the same machine: **http://localhost:8095**
- On your phone: use the **QR** button in the header (same WiFi as the server)

The QR code uses your PC’s LAN address — not `localhost`.

---

## Tabs

### Sammenlign (Compare)

- **Hero card** — best current deal (lowest €/kg with discounts applied)
- **Material tiles** — quick Bambu vs SUNLU comparison per material (PLA, PETG, …)
- Tap a material tile to open the catalog filtered to that material

### Rabatkøb (Volume deals)

- Same tile layout as the home screen
- Shows offers where buying **multiple rolls** gives a better unit price:
  - **SUNLU** — often MOQ 3 rolls (marked in product title)
  - **Bambu Lab** — bulk discount at **10× 1 kg** spools
- Tap a tile to open the product in the store

### Katalog (Catalog)

Full searchable list with filters:

| Filter | Effect |
|--------|--------|
| **Kun på lager** | Hide out-of-stock variants |
| **Kun 1 kg** | Only 1 kg spools |
| **Kun rabat** | Only items on sale or with volume discount |
| **Vis bedste €/kg** | Show lowest unit price including volume tiers |

Use material and brand chips to narrow results.

---

## Update prices

- **↻ Opdater** — fetches fresh prices from both stores (~1 minute)
- **Automatic** — if you ran `install-cron.sh`, prices update at 06:00 and 18:00

Respect store rate limits; avoid hammering **Opdater**.

---

## Help and splash

- **?** — short guide to each tab
- **Splash screen** — shows briefly on each page load (NxGenLab branding)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| QR opens wrong URL on phone | Hard-refresh the page; server must be restarted after updates |
| `ERR_CONNECTION_FAILED` after scanning QR | Phone must be on the **same WiFi**; URL must show `192.168.x.x`, not `localhost` |
| Empty or old prices | Press **Opdater** or run `./scrape.sh` |
| “Kun på lager” shows everything | Run **Opdater** once so stock flags are in the cache |

---

## Data sources

- Bambu Lab: [eu.store.bambulab.com](https://eu.store.bambulab.com)
- SUNLU EU: [de.store.sunlu.com](https://de.store.sunlu.com)

This tool is for personal price comparison only. Always confirm price and availability on the store before ordering.
