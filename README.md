# SK Vidar resultater 2026

Prosjektet er ryddet slik at filer ligger etter funksjon i stedet for alt i rotmappen.

## Struktur

- `data/arbeidsfiler/` inneholder arbeidsfilen `weekly_results_2026.xlsx`
- `data/delt_oversikt/` inneholder ferdig delt fil `SK Vidar Langdistanse 2026.xlsx`
- `data/input_resultater/` inneholder innsamlede tekst-, csv- og Excel-filer for nye resultater
- `data/database/` inneholder lokal SQLite-database og interne kontrollfiler
- `data/stottefiler/` inneholder overganger og NM-oppfolging
- `data/stottefiler/result_overrides_2026.csv` inneholder manuelle overstyringer for kjønn og klasse
- `scripts/` inneholder Python-skript for oppdatering
- `docs/` inneholder den publiserbare nettsiden og enkel dokumentasjon

## Vanlig bruk

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx`.
2. Kjor `Oppdater delt oversikt 2026.bat` fra prosjektroten.
3. Hent ferdig fil fra `data/delt_oversikt/`.
4. Nettsiden blir oppdatert i `docs/` og databasen i `data/database/`.
5. Hvis et lop mangler kjønn eller klasse, fyll det inn i `data/stottefiler/result_overrides_2026.csv`.

## Merknad

Hvis en Excel-fil star apen i et annet program, kan den ikke flyttes eller overskrives for den lukkes.

## Nettside

Nettsiden ligger i `docs/` og er laget for GitHub Pages. Den viser resultater per uke og leser kun fra `docs/data/results.json`.

## Sikker publisering

Prosjektet brukes fra et offentlig GitHub-repo, sa lokal arbeidsdata og stottefiler skal behandles som private selv om de ligger i prosjektmappen lokalt.

- Bare publiseringsklare filer skal ligge under `docs/`.
- Nettsiden skal bare lese `docs/data/results.json`.
- `docs/data/` skal ikke inneholde SQLite-filer eller andre interne eksportfiler.
- `data/arbeidsfiler/`, `data/database/` og `data/stottefiler/` er lokale arbeidsomrader og skal ikke committes til et offentlig repo.
- Hvis du trenger intern database eller arbeidsfiler lokalt, behold dem lokalt og bygg nettsiden derfra.

Se `PUBLISHING_STANDARD.md` for standarden vi skal folge videre.
