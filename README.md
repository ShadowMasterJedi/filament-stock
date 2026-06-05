# Filament Stock

Lille webservice til at holde styr på filament-kasser: scan stregkoder, tæl spoler op, tag billeder med iPhone og få overblik over lageret.

## Funktioner

- **Scan stregkode** – live kamera eller tag billede (iPhone-venligt)
- **Bambu Lab farve-ID** – henter produktkatalog fra Bambu Lab EU store, OCR på labels og genkender filamenter
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
pip install -r requirements.txt
chmod +x start.sh gen-cert.sh sync-bambu.sh open-firewall.sh
./sync-bambu.sh    # første gang: henter Bambu Lab SKU-katalog
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
4. Brug **Tag billede** eller **Live kamera** under fold-ud sektionen
5. Appen læser koden, tæller +1 og gemmer billedet

## API (kort)

| Endpoint | Beskrivelse |
|----------|-------------|
| `GET /api/inventory` | Hele lageret |
| `GET /api/stats` | Overblik |
| `POST /api/scan` | Scan/tæl op (`barcode`, `delta`) |
| `POST /api/filament` | Opret/opdater produkt |
| `POST /api/photo` | Upload billede (multipart) |
| `GET /api/bambu/lookup?barcode=` | Slå Bambu Lab produkt op |
| `POST /api/bambu/sync` | Opdater Bambu-katalog fra webshop |

### Bambu Lab farve-ID og stregkoder

Bambu bruger 5-cifrede **farve-ID** på labels (fx `10100` = Jade White PLA Basic) og EAN-stregkoder på kasser (`6975337…`).

Brug **Scan farve-label (OCR)** til at læse farve-ID fra etiketten, eller tag billede af stregkoden.

- Kataloget hentes fra `eu.store.bambulab.com`
- Kendte EAN kan udvides i `data/bambu_barcode_seed.json`
- Ved scan af ukendt stregkode med Bambu-match udfyldes formularen automatisk
- Ved scan med +1 oprettes produktet automatisk i lageret

## Teknologi

- Python 3 + SQLite + zxing-cpp (stregkode-læsning på serveren)
- Vanilla JS mobil-UI
- ZXing + BarcodeDetector til stregkoder
