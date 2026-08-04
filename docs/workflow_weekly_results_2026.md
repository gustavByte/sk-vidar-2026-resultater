# Workflow for weekly_results_2026

## Filer

- `data/arbeidsfiler/weekly_results_2026.xlsx` er detaljert arbeidsfil
- `data/delt_oversikt/SK Vidar Langdistanse 2026.xlsx` er enkel delt oversikt
- `data/database/` er lokal database og kontrollfiler, ikke offentlig publisering
- `data/database/identity_reports/` inneholder lokale rapporter for personkoblinger og public-payload-sjekk
- `data/stottefiler/personer/` inneholder lokalt personregister, aliaser, eksterne ID-er og manuelle resultatoverstyringer
- `config/person_identity/` inneholder den versjonerte, saniterte identitetskopien som gjør bygg reproducerbare i nye arbeidsområder
- `docs/data/results.json` er eneste publiserte datafil for nettsiden
- `scripts/build_shared_weekly_results_2026.py` bygger den delte oversikten på nytt
- `scripts/build_site_2026.py` bygger publiseringsklar JSON for GitHub Pages
- `Oppdater delt oversikt 2026.bat` er enkel kjørefil fra prosjektroten

## Anbefalt flyt

1. Oppdater `data/arbeidsfiler/weekly_results_2026.xlsx` med nye resultater.
2. Kjør `scripts/build_shared_weekly_results_2026.py` og `scripts/build_site_2026.py`, eller batch-filen.
3. Hvis et nytt navn ligner en eksisterende profil, stopper bygget før nettsiden oppdateres. Vurder kandidatrapporten og registrer beslutningen før du bygger på nytt.
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
- Leverandør-ID-er må være scoped med `source_system`; `source_person_id=123` fra EQ Timing er en annen nøkkel enn `123` fra RaceDays. En ID uten kildesystem holdes tilbake til kontroll. `participant_id` og `deltaker_id` avvises fordi de normalt bare er stabile innen ett arrangement.
- Bruk `result_person_overrides.csv` for enkeltresultater som ikke bør kobles automatisk.
- Ikke bruk fuzzy-forslag som automatisk fasit. De ligger i `fuzzy_match_candidates.csv` for manuell vurdering.
- Sjekk `external_id_conflicts.csv` hvis samme eksterne ID ser ut til å peke til flere profiler.
- Kandidatkøen oppdateres automatisk ved hvert sidebygg. Uavklarte kandidater stopper publisering, slik at en ny navnevariant ikke rekker å bli en synlig duplikat.
- Fyll `person_match_decisions.csv` med `merge`, `reject` eller `defer`, og bygg på nytt. `person_drafts.csv` reserverer samme foreløpige ID mellom forsøk; reservasjonen blir ikke publisert eller kopiert til `config/`. `defer` lar publisering fortsette mens paret undersøkes, så lenge begge profilene fortsatt finnes; de andre valgene bør begrunnes kort.
- Ved `merge` beholdes den eldste stabile ID-en som standard, mens ønsket fullt navn kan settes i `preferred_display_name`. Aktive kjente skrivemåter kopieres til den beholdte personen som aliaser. Senere resultater med et av navnene kobles dermed direkte til samme `person_id`.
- Sjekk også `resolved_slug_owner_conflicts.csv`: en historisk URL må aldri ha en annen eier enn en aktiv profil med samme slug.
- Commit endringer under `config/person_identity/` sammen med den genererte JSON-filen; de oppdateres automatisk ved bygg og inneholder ikke private eksterne ID-er.

Se `docs/person_identity_model.md` for detaljer.

## Nettsidens datakontrakt (schema v3)

`docs/data/results.json` inneholder i tillegg til resultater/uker/rankings/personer:

- Per resultat: `is_pb`/`is_sb` (token-parsing av notatfeltet), `ranking_distance` (normalisert standarddistanse, tom for terrengløp)
- Per uke: `pb_count`, `sb_count`, `wa_result_count`, `new_athlete_count`, `top_performances` (topp 3 etter WA-poeng, blandet kjønn)
- `months[]`: månedsaggregat med norske etiketter
- Profiler: `wa_points_best`, `pb_count`, `sb_count`; beste-resultater og rankings har `wa_points`

JSON-en skrives minifisert. Frontenden tåler eldre payload (felter mangler → funksjoner degraderer stille), men bygg alltid på nytt etter skjemaendringer.

## Sikkerhetsstandard

- Arbeidsfil, støttefiler og lokal database er private lokale filer.
- Offentlig nettside skal bare bruke `docs/data/results.json`.
- JSON-filen skal bare inneholde felter som frontenden faktisk bruker.
- SQLite-filer skal ikke kopieres til `docs/data/`.
- Hvis et datasett ikke trengs i browseren, skal det ikke publiseres.
