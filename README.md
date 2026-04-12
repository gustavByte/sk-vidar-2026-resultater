# SK Vidar resultater 2026

Prosjektet er ryddet slik at filer ligger etter funksjon i stedet for alt i rotmappen.

## Struktur

- `data/arbeidsfiler/` inneholder arbeidsfilen `weekly_results_2026.xlsx`
- `data/delt_oversikt/` inneholder ferdig delt fil `SK Vidar Langdistanse 2026.xlsx`
- `data/input_resultater/` inneholder innsamlede tekst-, csv- og Excel-filer for nye resultater
- `data/database/` inneholder SQLite-databasen som brukes av nettsiden
- `data/stottefiler/` inneholder overganger og NM-oppfolging
- `scripts/` inneholder Python-skript for oppdatering
- `docs/` inneholder den publiserbare nettsiden og enkel dokumentasjon

## Vanlig bruk

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx`.
2. Kjor `Oppdater delt oversikt 2026.bat` fra prosjektroten.
3. Hent ferdig fil fra `data/delt_oversikt/`.
4. Nettsiden blir oppdatert i `docs/` og databasen i `data/database/`.

## Merknad

Hvis en Excel-fil star apen i et annet program, kan den ikke flyttes eller overskrives for den lukkes.

## Nettside

Nettsiden ligger i `docs/` og er laget for GitHub Pages. Den viser resultater per uke og leser data fra en JSON-export som bygges fra SQLite-databasen.
