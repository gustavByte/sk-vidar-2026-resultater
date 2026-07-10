# SK Vidar resultater 2026

Prosjektet er ryddet slik at filer ligger etter funksjon i stedet for alt i rotmappen.

## Struktur

- `data/arbeidsfiler/` inneholder arbeidsfilen `weekly_results_2026.xlsx`
- `data/delt_oversikt/` inneholder ferdig delt fil `SK Vidar Langdistanse 2026.xlsx`
- `data/input_resultater/inbox/` er innboks for nye strukturerte CSV-, TXT- og Excel-filer
- `data/database/` inneholder lokal SQLite-database, interne kontrollfiler og identitetsrapporter
- `data/stottefiler/` inneholder private/lokale støttefiler
- `data/stottefiler/result_overrides_2026.csv` inneholder manuelle overstyringer for kjønn og klasse
- `data/stottefiler/personer/` inneholder lokalt personregister, aliaser, eksterne ID-er og manuelle personkoblinger
- `scripts/` inneholder Python-skript for oppdatering
- `docs/` inneholder den publiserbare nettsiden og enkel dokumentasjon

## Vanlig bruk

1. Legg nye strukturerte resultatfiler i `data/input_resultater/inbox/`. Obligatoriske felt er dato, løp, distanse, navn, tid og sikkert kjønn/klasse.
2. Kjør `Oppdater delt oversikt 2026.bat` fra prosjektroten. Filer med usikre felt holdes tilbake fra hele importen.
3. Kontroller eventuelle avvik i `data/database/import_review_2026.csv`, rett kildefilen og kjør på nytt.
4. Hent ferdig fil fra `data/delt_oversikt/`. Nettsiden bygges i `docs/` og databasen i `data/database/`.
5. Hvis et løp mangler kjønn eller klasse, fyll det inn i `data/stottefiler/result_overrides_2026.csv`.
6. Hvis en person er feil koblet, legg alias eller override i `data/stottefiler/personer/` og bygg siden på nytt.
7. For raske navnematcher, kjør `python scripts/review_person_matches_2026.py --generate`, godkjenn i `person_match_decisions.csv`, og kjør `python scripts/review_person_matches_2026.py --apply`.

Kjør `python scripts/update_results_2026.py --check` for kun å kontrollere innboksen. Kjør med `--build-only` for å bygge eksisterende arbeidsdata uten å lese innboksen.

## Merknad

Hvis en Excel-fil står åpen i et annet program, kan den ikke flyttes eller overskrives før den lukkes.

## Nettside

Nettsiden ligger i `docs/` og er laget for GitHub Pages. Den leser kun fra `docs/data/results.json` (schema v4, minifisert) og har fem hovedvisninger med hash-ruting:

- `#/` — Oversikt: sesongtrend-graf, siste uke med ukens prestasjoner (WA-poeng), siste perser og snarveier
- `#/uke/{nr}` — Ukevisning med delbare filtre i URL-en (`?kjonn=k&distanse=10 km&lop=…&sok=…&gruppering=lop`)
- `#/personer` — Søkbar personkatalog; `#/person/{slug}` — profil med beste noteringer, klubbrangering, utviklingsgraf og aktivitet
- `#/statistikk` — kompakt oversikt med egne undersider for standarddistanser, terreng/fjell uten WA, WA-poeng, deltakelse, måneder og største løp
- `#/sok?q=…` — Globalt søk på tvers av hele sesongen

Koden er delt i ES-moduler under `docs/js/` (`router.js`, `state.js`, `derive.js`, `charts.js`, `views/…`) uten byggeverktøy. `docs/app.js` er inngangspunktet; bump `?v=`-parameteren i `docs/index.html` ved endringer i JS/CSS slik at nettlesere henter ny versjon (undermoduler arver ikke versjonsstempelet, men GitHub Pages cacher dem bare i ~10 minutter).

PB/SB-merker parses fra notatfeltet ved bygging (`is_pb`/`is_sb`); ekte personlige rekorder kan ikke utledes siden datasettet kun dekker 2026. Backlog: normalisering av `class_name` for veteranstatistikk, egne løpssider (`#/lop/{…}`).

Personmodellen er forklart i `docs/person_identity_model.md`.

## Sikker publisering

Prosjektet brukes fra et offentlig GitHub-repo, så lokal arbeidsdata og støttefiler skal behandles som private selv om de ligger i prosjektmappen lokalt.

- Bare publiseringsklare filer skal ligge under `docs/`.
- Nettsiden skal bare lese `docs/data/results.json`.
- `docs/data/` skal ikke inneholde SQLite-filer eller andre interne eksportfiler.
- `data/arbeidsfiler/`, `data/database/` og `data/stottefiler/` er lokale arbeidsområder og skal ikke committes til et offentlig repo.
- Hvis du trenger intern database eller arbeidsfiler lokalt, behold dem lokalt og bygg nettsiden derfra.

Se `PUBLISHING_STANDARD.md` for standarden vi skal følge videre.
