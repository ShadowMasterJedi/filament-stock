# Filament Stock

Lille webservice til at holde styr på filament-kasser: scan stregkoder, tæl spoler op, tag billeder med iPhone og få overblik over lageret.

## Funktioner

- **Scan stregkode** – live kamera eller tag billede (iPhone-venligt)
- **Tæl op/ned** – +1 / −1 pr. kasse
- **Registrer ny type** – mærke, materiale, farve, vægt, placering
- **Dashboard** – total spoler, fordelt på materiale
- **Lagerliste** – søgbar oversigt med farvemarkering
- **Billeder** – uploades fra iPhone og knyttes til stregkode
- **SQLite database** – `data/filament.db`
- **LAN-adgang** – brug fra telefon på samme netværk

## Start

```bash
cd ~/Projects/filament-stock
chmod +x start.sh open-firewall.sh
./start.sh
```

Åbn **http://localhost:8090** eller fra iPhone: **http://\<server-ip\>:8090**

Firewall (én gang):

```bash
./open-firewall.sh
```

## Brug fra iPhone

1. Åbn URL i Safari
2. Tryk **Del → Tilføj til hjemmeskærm** (PWA)
3. Gå til **Scan → Tag billede**
4. Peg på stregkoden på filament-kassen
5. Appen læser koden, tæller +1 og gemmer billedet

**Tip:** «Tag billede» virker bedst over HTTP/LAN. Live kamera kræver nyere browser.

## API (kort)

| Endpoint | Beskrivelse |
|----------|-------------|
| `GET /api/inventory` | Hele lageret |
| `GET /api/stats` | Overblik |
| `POST /api/scan` | Scan/tæl op (`barcode`, `delta`) |
| `POST /api/filament` | Opret/opdater produkt |
| `POST /api/photo` | Upload billede (multipart) |

## Teknologi

- Python 3 + SQLite (ingen ekstra pakker)
- Vanilla JS mobil-UI
- ZXing + BarcodeDetector til stregkoder
