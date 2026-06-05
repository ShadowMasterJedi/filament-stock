# Filament Stock

Lille webservice til at holde styr på filament-kasser: scan stregkoder eller farve-labels, tæl spoler op, tag billeder med iPhone og få overblik over lageret.

Se **[delivery_summary.md](delivery_summary.md)** for fuld leveranceoversigt og TODO.

## Funktioner

- **Scan stregkode** – live kamera eller tag billede (iPhone-venligt, kræver HTTPS)
- **Scan farve-label (OCR)** – læser Bambu Lab farve-ID (fx `10100`) via server-OCR
- **Auto-gem** – farve-ID alene er nok; produktet oprettes automatisk ved scan (+1)
- **Bambu Lab-katalog** – henter produktdata fra EU store, kendte EAN i seed-fil
- **Tæl op/ned** – +1 / −1 pr. kasse
- **Dashboard** – total spoler, fordelt på materiale
- **Lagerliste** – søgbar oversigt med farvemarkering
- **Billeder** – uploades fra iPhone og knyttes til produkt
- **SQLite database** – `data/filament.db`
- **LAN-adgang** – brug fra telefon på samme netværk

## Start

```bash
cd ~/Projects/filament-stock
pip install -r requirements.txt
chmod +x start.sh gen-cert.sh sync-bambu.sh open-firewall.sh
./sync-bambu.sh    # første gang: henter Bambu Lab-katalog
./start.sh
```

Ved første opstart forsøger serveren også at hente Bambu-kataloget automatisk, hvis det er tomt.

Serveren starter med **HTTPS** og et self-signed certifikat (oprettes automatisk første gang).

Åbn **https://localhost:8090** eller fra iPhone: **https://\<server-ip\>:8090**

Firewall (én gang):

```bash
./open-firewall.sh
```

### Self-signed certifikat på iPhone

Safari viser «Forbindelsen er ikke privat» første gang – det er normalt:

1. Tryk **Vis detaljer** (eller **Avanceret**)
2. Tryk **Besøg websitet** / **Fortsæt til …**
3. Giv kamera-tilladelse når du trykker **Start live scan**

**Sort kamera?** Tjek dette:

- URL skal starte med **https://** (ikke http://)
- Slet gammel genvej på hjemmeskærm og tilføj igen fra **https**-adressen
- Safari → Indstillinger → **Kamera** = «Spørg» eller «Tillad»
- Genindlæs siden (luk Safari-fane helt og åbn igen)

Genopret certifikat (fx efter IP-skift):

```bash
rm -rf certs/
./gen-cert.sh
```

HTTP uden TLS (kun til test):

```bash
python3 server.py 8090 --http
```

## Brug fra iPhone

1. Åbn **https://** URL i Safari og accepter certifikat-advarslen
2. Tryk **Del → Tilføj til hjemmeskærm** (PWA)
3. Gå til **Scan**
4. **Stregkode:** «Tag billede» eller «Start live scan»
5. **Farve-ID:** «Scan farve-label (OCR)» – peg på teksten `(10100)` på etiketten
6. Produktet gemmes automatisk (+1 spole); juster med +1/−1 bagefter

Du kan også indtaste farve-ID manuelt (fx `10100`) uden at scanne.

## API

| Endpoint | Beskrivelse |
|----------|-------------|
| `GET /api/health` | Server status |
| `GET /api/inventory` | Hele lageret |
| `GET /api/stats` | Dashboard-tal |
| `POST /api/scan` | Scan/tæl (`barcode`/`color_id`, `delta`, `auto_register`) |
| `POST /api/decode` | Stregkode fra billede (multipart `file`) |
| `POST /api/ocr` | Farve-ID fra label-billede (multipart `file`) |
| `POST /api/filament` | Opret/opdater produkt |
| `POST /api/photo` | Upload billede (multipart) |
| `GET /api/bambu/lookup?barcode=` | Slå Bambu Lab produkt op |
| `POST /api/bambu/sync` | Opdater Bambu-katalog fra webshop |

### Bambu Lab farve-ID og stregkoder

Bambu bruger 5-cifrede **farve-ID** på labels (fx `10100` = Jade White PLA Basic) og EAN-stregkoder på kasser (`6975337…`).

- **OCR** kører primært på serveren (RapidOCR) – hurtigere og mere stabilt end browser på iPhone
- Kataloget hentes fra `eu.store.bambulab.com`
- Kendte EAN kan udvides i `data/bambu_barcode_seed.json`
- Ved scan med +1 oprettes produktet automatisk – **farve-ID alene er nok**, fysisk stregkode ikke påkrævet

## Teknologi

- Python 3 + SQLite
- `zxing-cpp` – server stregkode-decode
- `rapidocr-onnxruntime` – server OCR af farve-labels
- `pillow-heif` – HEIC-billeder fra iPhone
- Vanilla JS mobil-UI
- ZXing + BarcodeDetector (client stregkode)
- Tesseract.js (client OCR-backup)
