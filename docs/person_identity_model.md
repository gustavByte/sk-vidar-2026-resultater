# Personmodell for SK Vidar-resultater

Denne modellen gjør at samme løper får én stabil profil på nettsiden, selv om visningsnavn, aliaser eller slug endres over tid.

## Prinsipper

- `person_id` er primæridentiteten. Den skal ikke endres når navn eller slug endres.
- `athlete_name` er visningsdata fra resultatet, ikke identitet.
- `profile_slug` brukes til URL-er, men er ikke primærnøkkel.
- Fuzzy matching skal bare lage rapportforslag. Usikre koblinger skal løses med alias, ekstern ID eller manuell override.
- Lokale identitetsfiler ligger under `data/stottefiler/personer/` og skal ikke publiseres eller committes.
- `config/person_identity/` er en versjonert, sanitert identitetskopi med stabile ID-er, offentlige navnealiaser, slug-historikk og beslutninger uten private notater. Den inneholder aldri eksterne ID-er.
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

Lokale koblinger fra eksterne kilder til person, for eksempel Slack-ID eller World Athletics-/resultatkilde-ID. Slack- og World Athletics-ID-er har egne globale navnerom. En leverandørspesifikk `source_person_id` må ha `source_system`; den lagres som for eksempel `result_source:eq-timing` + `123`. En uscopet leverandør-ID stopper i kontroll og brukes aldri til automatisk kobling. Eventlokale `participant_id`/`deltaker_id` avvises fordi samme verdi kan gjenbrukes i neste løp. ID-ene brukes bare i byggesteg og publiseres ikke.

`person_slug_history.csv`

Historikk for slug-endringer. Gamle slugs kan dermed redirectes til riktig profil i public JSON.

`result_person_overrides.csv`

Manuell kobling for enkeltresultater. Brukes når et resultat ikke trygt kan kobles via alias eller ekstern ID.

`person_match_decisions.csv`

Manuell godkjenningskø for foreslåtte navnematcher. Kjør `python scripts/review_person_matches_2026.py --generate` for å lage `data/database/identity_reports/person_match_candidates.csv`, fyll beslutning i `person_match_decisions.csv`, og bygg på nytt. Bygget anvender beslutningen i minnet før publisering, også når en kandidatprofil ennå ikke er lagret. Ved sammenslåing kan `preferred_display_name` settes slik at den eldste stabile `person_id`-en beholdes samtidig som det beste fulle navnet vises. `--apply` finnes fortsatt for vedlikehold av profiler som allerede ligger i registeret.

`person_drafts.csv`

Privat, lokal reservasjon av foreløpige person-ID-er. Den gjør at en uavklart kandidat får samme ID når en blokkert bygging kjøres på nytt, selv om andre nye navn kommer til i mellomtiden. En reservasjon promoteres bare når navn og eventuelle eksterne ID-er fortsatt stemmer; ID-kollisjon eller motstridende Slack-/World Athletics-ID stopper byggingen. Filen tas aldri med i den versjonerte identitetskopien.

Header-maler finnes i `docs/person_identity_templates/`.

## Versjonert identitetskopi

Et nytt arbeidsområde mangler de ignorerte støttefilene. Byggeskriptet fyller da den lokale identitetsmappen fra `config/person_identity/` før matching. Hvis både det lokale registeret og den versjonerte kopien er tomme, stopper bygget i stedet for å opprette en ny profil for hver navnevariant.

Etter et vellykket bygg skrives en sanitert kopi av register, aliaser, slug-historikk, resultatoverstyringer og matchbeslutninger tilbake til `config/person_identity/`. Beslutningsnotater og eksterne kilde-ID-er forblir lokale. Dermed husker også nye arbeidsområder hvilke navnepar som allerede er avvist eller utsatt.

## Byggeflyt

`scripts/build_site_2026.py` gjør nå dette:

1. Leser arbeidsboken.
2. Genererer `result_id` for hvert resultat.
3. Leser lokale identitetsfiler, eller fyller dem fra den versjonerte identitetskopien i et nytt arbeidsområde.
4. Matcher resultat til person via manuell override, ekstern ID, alias eller eksakt registrert navn.
5. Reserverer en stabil foreløpig ID lokalt og lager eventuelle nye personer i minnet uten å endre eksisterende `person_id`.
6. Lager kvalitetsrapporter og stopper hvis en navnekandidat er uavklart, en identitetsreferanse mangler, merge-grafen er ugyldig eller andre datakrav feiler.
7. Stager privat register, sanitert identitetskopi, SQLite, mangelliste og public JSON, og committer eller ruller tilbake hele filsettet samlet.
8. Den ferdige `docs/data/results.json` inneholder `schema_version`, `person_id`, `person_slug` og `people`.

Rapportene dekker manglende `person_id` med matchmetode og årsak, hengende identitetsreferanser, merge-sykluser, aliaser som peker til flere personer, eksterne ID-er som peker til flere personer, dupliserte normaliserte navn, slug-kollisjoner og historiske slugs med feil eier, fuzzy-forslag og mulig lekkasje av private felt i public payload. Flere aktive Slack-/World Athletics-ID-er på samme person rapporteres separat for kontroll, men kan være legitim konto-historikk.

`person_match_candidates.csv` er en egen kø for manuell navnematching. Den bruker token-regler som samme første/siste navn, ekstra mellomnavn, initial mot mellomnavn og høy strenglikhet. Den kobler aldri automatisk. Køen er en publiseringsport: et uavklart par må få `merge`, `reject` eller `defer` før ny offentlig JSON kan skrives.

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
4. Sett `decision` til `merge`, `reject` eller `defer`, begrunn valget i `notes`, og oppdater `reviewed_at` med et ISO-tidspunkt.
5. Kjør `python scripts/build_site_2026.py`; beslutningen brukes i samme kontrollerte transaksjon og lagres først etter at alle datakontroller har passert. Privat og sanitert register, SQLite og public JSON committes samlet eller rulles tilbake samlet. Ved en sjelden feil i selve gjenopprettingen beholdes backupfilen og feilmeldingen oppgir recovery-stien.

`merge` slår profilene sammen og beholder `primary_person_id`. Kandidatrapporten foreslår den eldste/laveste stabile ID-en som primær; et bedre fullt navn settes separat i `preferred_display_name`. Bare aktive aliaser kopieres fra sekundærprofilen. `reject` skjuler forslaget fra fremtidige kandidatrapporter. `defer` lar forslaget bli liggende, men begge reserverte profiler må fortsatt finnes. Det interne valget `alias_only` er bare idempotent vedlikehold for en sekundærprofil som allerede resolver til den valgte primærprofilen; det skal ikke brukes for to aktive kandidatprofiler.

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
