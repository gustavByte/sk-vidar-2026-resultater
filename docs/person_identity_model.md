# Personmodell for SK Vidar-resultater

Denne modellen gjør at samme løper får én stabil profil på nettsiden, selv om visningsnavn, aliaser eller slug endres over tid.

## Prinsipper

- `person_id` er primæridentiteten. Den skal ikke endres når navn eller slug endres.
- `athlete_name` er visningsdata fra resultatet, ikke identitet.
- `profile_slug` brukes til URL-er, men er ikke primærnøkkel.
- Fuzzy matching skal bare lage rapportforslag. Usikre koblinger skal løses med alias, ekstern ID eller manuell override.
- Lokale identitetsfiler ligger under `data/stottefiler/personer/` og skal ikke publiseres eller committes.
- Public frontend skal bare lese `docs/data/results.json`.

## Private støttefiler

Alle filene under ligger lokalt i `data/stottefiler/personer/`.

`person_registry.csv`

Hovedregisteret for personer. Viktige felt:

- `person_id`: stabil ID, for eksempel `skv-p000123`
- `display_name`: foretrukket visningsnavn på profil
- `normalized_name`: normalisert navn brukt til eksakt matching
- `profile_slug`: nåværende slug for `#/person/<slug>`
- `status`: vanligvis `active`, eventuelt `merged` ved sammenslåing
- `merged_into_person_id`: målperson hvis profilen er slått sammen

`person_aliases.csv`

Eksakte navnealiaser som skal peke til en person. Bruk denne når samme person forekommer med ulike navn, for eksempel forkortelse, mellomnavn eller stavevariant.

`person_external_ids.csv`

Lokale koblinger fra eksterne kilder til person, for eksempel Slack-ID eller senere World Athletics-/resultatkilde-ID. Disse ID-ene brukes bare i byggesteg og publiseres ikke.

`person_slug_history.csv`

Historikk for slug-endringer. Gamle slugs kan dermed redirectes til riktig profil i public JSON.

`result_person_overrides.csv`

Manuell kobling for enkeltresultater. Brukes når et resultat ikke trygt kan kobles via alias eller ekstern ID.

`person_match_decisions.csv`

Manuell godkjenningskø for foreslåtte navnematcher. Kjør `python scripts/review_person_matches_2026.py --generate` for å lage `data/database/identity_reports/person_match_candidates.csv`, fyll beslutning i `person_match_decisions.csv`, og kjør `python scripts/review_person_matches_2026.py --apply`.

Header-maler finnes i `docs/person_identity_templates/`.

## Byggeflyt

`scripts/build_site_2026.py` gjør nå dette:

1. Leser arbeidsboken.
2. Genererer `result_id` for hvert resultat.
3. Leser lokale identitetsfiler.
4. Matcher resultat til person via manuell override, ekstern ID, alias eller eksakt registrert navn.
5. Legger nye personer til i det lokale registeret uten å endre eksisterende `person_id`.
6. Skriver public `docs/data/results.json` med `schema_version`, `person_id`, `person_slug` og `people`.
7. Lager lokale kvalitetsrapporter i `data/database/identity_reports/`.

Rapportene dekker manglende `person_id`, aliaser som peker til flere personer, eksterne ID-er som peker til flere personer, dupliserte normaliserte navn, slug-kollisjoner, fuzzy-forslag og mulig lekkasje av private felt i public payload.

`person_match_candidates.csv` er en egen kø for manuell navnematching. Den bruker token-regler som samme første/siste navn, ekstra mellomnavn, initial mot mellomnavn og høy strenglikhet. Den kobler aldri automatisk.

## Korrigere feil kobling

Hvis to resultater er koblet til feil person:

1. Finn `result_id` i `docs/data/results.json` eller i lokal SQLite.
2. Legg en rad i `result_person_overrides.csv` med riktig `person_id`.
3. Kjør `python scripts/build_site_2026.py`.
4. Kontroller `results_without_person_id.csv`, `alias_conflicts.csv` og profilen på nettsiden.

Hvis en navnevariant alltid skal peke til samme person:

1. Legg aliaset i `person_aliases.csv`.
2. Bruk normalisert alias hvis du vil være eksplisitt; ellers fyller koden dette ut ved neste bygg.
3. Kjør byggeskriptet.

## Godkjenne navnematcher

1. Kjør `python scripts/review_person_matches_2026.py --generate`.
2. Åpne `data/database/identity_reports/person_match_candidates.csv`.
3. Kopier `candidate_id`, `primary_person_id` og den andre personen til `data/stottefiler/personer/person_match_decisions.csv`.
4. Sett `decision` til `merge`, `alias_only`, `reject` eller `defer`.
5. Kjør `python scripts/review_person_matches_2026.py --apply`.
6. Kjør `python scripts/build_site_2026.py`.

`merge` slår profilene sammen og beholder `primary_person_id`. `alias_only` legger navnevarianten som alias uten å slå sammen eksisterende profiler. `reject` skjuler forslaget fra fremtidige kandidatrapporter. `defer` lar forslaget bli liggende.

## Slå sammen profiler

Når to profiler viser seg å være samme person:

1. Velg én `person_id` som skal leve videre.
2. Sett den andre profilen til `status=merged`.
3. Fyll `merged_into_person_id` med målpersonens `person_id`.
4. Flytt relevante aliaser og eksterne ID-er til målpersonen, eller la resolveren følge merge-feltet.
5. Legg gammel slug i `person_slug_history.csv` med `active_to` satt, slik at gamle lenker kan redirectes.
6. Kjør byggeskriptet og sjekk rapportene.

## Flere år og flere datakilder

Personregisteret er bevisst ikke knyttet til 2026. Når senere år eller nye kilder legges til, bør de bruke samme `person_id`-register og bare utvide `person_external_ids.csv` med nye kildenøkler. Nye public JSON-er kan da fortsatt publisere minimale profilfelt og aldri lekke lokale eksterne ID-er.
