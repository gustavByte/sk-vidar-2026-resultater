# Workflow for weekly_results_2026

## Filer

- `data/arbeidsfiler/weekly_results_2026.xlsx` er detaljert arbeidsfil
- `data/delt_oversikt/SK Vidar Langdistanse 2026.xlsx` er enkel delt oversikt
- `data/database/` er lokal database og kontrollfiler, ikke offentlig publisering
- `data/database/identity_reports/` inneholder lokale rapporter for personkoblinger og public-payload-sjekk
- `data/stottefiler/personer/` inneholder lokalt personregister, aliaser, eksterne ID-er og manuelle resultatoverstyringer
- `docs/data/results.json` er eneste publiserte datafil for nettsiden
- `scripts/build_shared_weekly_results_2026.py` bygger den delte oversikten på nytt
- `scripts/build_site_2026.py` bygger publiseringsklar JSON for GitHub Pages
- `Oppdater delt oversikt 2026.bat` er enkel kjørefil fra prosjektroten

## Anbefalt flyt

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx` med nye resultater.
2. Kjør `scripts/build_shared_weekly_results_2026.py` og `scripts/build_site_2026.py`, eller batch-filen.
3. Sjekk identitetsrapportene hvis nye personer, aliaser eller fuzzy-forslag dukker opp.
4. Del filen i `data/delt_oversikt/` med klubben.
5. Publiser bare innholdet i `docs/` til GitHub Pages.

## Hva den delte filen viser

- Uke
- Dato
- Løp
- Navn
- Distanse
- Tid
- Plass
- Kort note

Råfilen beholdes detaljert. Den delte filen er laget for rask lesing.

## Personkoblinger

Nettsiden publiserer `person_id` og `person_slug` for hvert resultat. Selve identitetsarbeidet skjer lokalt:

- Legg sikre navnevarianter i `person_aliases.csv`.
- Legg sikre kilde-ID-er i `person_external_ids.csv`.
- Bruk `result_person_overrides.csv` for enkeltresultater som ikke bør kobles automatisk.
- Ikke bruk fuzzy-forslag som automatisk fasit. De ligger i `fuzzy_match_candidates.csv` for manuell vurdering.
- Sjekk `external_id_conflicts.csv` hvis samme eksterne ID ser ut til å peke til flere profiler.
- Kjør `scripts/review_person_matches_2026.py --generate` for å lage en effektiv lokal kø med navnematcher som trenger manuell godkjenning.
- Fyll `person_match_decisions.csv` og kjør `scripts/review_person_matches_2026.py --apply` før du bygger siden hvis profiler skal slås sammen.

Se `docs/person_identity_model.md` for detaljer.

## Sikkerhetsstandard

- Arbeidsfil, støttefiler og lokal database er private lokale filer.
- Offentlig nettside skal bare bruke `docs/data/results.json`.
- JSON-filen skal bare inneholde felter som frontenden faktisk bruker.
- SQLite-filer skal ikke kopieres til `docs/data/`.
- Hvis et datasett ikke trengs i browseren, skal det ikke publiseres.
