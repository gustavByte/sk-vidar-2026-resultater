# Workflow for weekly_results_2026

## Filer

- `data/arbeidsfiler/weekly_results_2026.xlsx` er detaljert arbeidsfil
- `data/delt_oversikt/SK Vidar Langdistanse 2026.xlsx` er enkel delt oversikt
- `data/database/` er lokal database og kontrollfiler, ikke offentlig publisering
- `docs/data/results.json` er eneste publiserte datafil for nettsiden
- `scripts/build_shared_weekly_results_2026.py` bygger den delte oversikten pa nytt
- `scripts/build_site_2026.py` bygger publiseringsklar JSON for GitHub Pages
- `Oppdater delt oversikt 2026.bat` er enkel kjorefil fra prosjektroten

## Anbefalt flyt

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx` med nye resultater.
2. Kjor `scripts/build_shared_weekly_results_2026.py` og `scripts/build_site_2026.py`, eller batch-filen.
3. Del filen i `data/delt_oversikt/` med klubben.
4. Publiser bare innholdet i `docs/` til GitHub Pages.

## Hva den delte filen viser

- Uke
- Dato
- Lop
- Navn
- Distanse
- Tid
- Plass
- Kort note

Rafilen beholdes detaljert. Den delte filen er laget for rask lesing.

## Sikkerhetsstandard

- Arbeidsfil, stottefiler og lokal database er private lokale filer.
- Offentlig nettside skal bare bruke `docs/data/results.json`.
- JSON-filen skal bare inneholde felter som frontenden faktisk bruker.
- SQLite-filer skal ikke kopieres til `docs/data/`.
- Hvis et datasett ikke trengs i browseren, skal det ikke publiseres.
