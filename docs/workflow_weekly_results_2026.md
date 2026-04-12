# Workflow for weekly_results_2026

## Filer

- `data/arbeidsfiler/weekly_results_2026.xlsx` er detaljert arbeidsfil
- `data/delt_oversikt/SK Vidar Langdistanse 2026.xlsx` er enkel delt oversikt
- `scripts/build_shared_weekly_results_2026.py` bygger den delte oversikten pa nytt
- `Oppdater delt oversikt 2026.bat` er enkel kjorefil fra prosjektroten

## Anbefalt flyt

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx` med nye resultater.
2. Kjor `scripts/build_shared_weekly_results_2026.py` eller batch-filen.
3. Del filen i `data/delt_oversikt/` med klubben.

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
