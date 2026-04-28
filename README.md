# SK Vidar resultater 2026

Prosjektet er ryddet slik at filer ligger etter funksjon i stedet for alt i rotmappen.

## Struktur

- `data/arbeidsfiler/` inneholder arbeidsfilen `weekly_results_2026.xlsx`
- `data/delt_oversikt/` inneholder ferdig delt fil `SK Vidar Langdistanse 2026.xlsx`
- `data/input_resultater/` inneholder innsamlede tekst-, csv- og Excel-filer for nye resultater
- `data/database/` inneholder lokal SQLite-database, interne kontrollfiler og identitetsrapporter
- `data/stottefiler/` inneholder private/lokale støttefiler
- `data/stottefiler/result_overrides_2026.csv` inneholder manuelle overstyringer for kjønn og klasse
- `data/stottefiler/personer/` inneholder lokalt personregister, aliaser, eksterne ID-er og manuelle personkoblinger
- `scripts/` inneholder Python-skript for oppdatering
- `docs/` inneholder den publiserbare nettsiden og enkel dokumentasjon

## Vanlig bruk

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx`.
2. Kjør `Oppdater delt oversikt 2026.bat` fra prosjektroten.
3. Hent ferdig fil fra `data/delt_oversikt/`.
4. Nettsiden blir oppdatert i `docs/` og databasen i `data/database/`.
5. Hvis et løp mangler kjønn eller klasse, fyll det inn i `data/stottefiler/result_overrides_2026.csv`.
6. Hvis en person er feil koblet, legg alias eller override i `data/stottefiler/personer/` og bygg siden på nytt.
7. For raske navnematcher, kjør `python scripts/review_person_matches_2026.py --generate`, godkjenn i `person_match_decisions.csv`, og kjør `python scripts/review_person_matches_2026.py --apply`.

## Merknad

Hvis en Excel-fil står åpen i et annet program, kan den ikke flyttes eller overskrives før den lukkes.

## Nettside

Nettsiden ligger i `docs/` og er laget for GitHub Pages. Den viser resultater per uke og personprofiler, og leser kun fra `docs/data/results.json`.

Personmodellen er forklart i `docs/person_identity_model.md`.

## Sikker publisering

Prosjektet brukes fra et offentlig GitHub-repo, så lokal arbeidsdata og støttefiler skal behandles som private selv om de ligger i prosjektmappen lokalt.

- Bare publiseringsklare filer skal ligge under `docs/`.
- Nettsiden skal bare lese `docs/data/results.json`.
- `docs/data/` skal ikke inneholde SQLite-filer eller andre interne eksportfiler.
- `data/arbeidsfiler/`, `data/database/` og `data/stottefiler/` er lokale arbeidsområder og skal ikke committes til et offentlig repo.
- Hvis du trenger intern database eller arbeidsfiler lokalt, behold dem lokalt og bygg nettsiden derfra.

Se `PUBLISHING_STANDARD.md` for standarden vi skal følge videre.
