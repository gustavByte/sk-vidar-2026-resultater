# Publishing Standard

Denne standarden gjelder for prosjektet så lenge repoet er offentlig.

## Mal

- `docs/` er offentlig publiseringssone.
- `data/arbeidsfiler/`, `data/database/` og `data/stottefiler/` er lokale/private arbeidsområder.
- Frontenden skal bare lese publiseringsklare filer som er laget eksplisitt for browseren.
- Personregister, aliaser, eksterne ID-er, manuelle personkoblinger og kvalitetsrapporter er lokale arbeidsdata.

## Regler

1. Publiser bare minimumsdata som faktisk brukes i UI-et.
2. Ikke serialiser hele arbeidsdatasett direkte til offentlige JSON-filer.
3. Ikke publiser SQLite-filer, kontrollrapporter eller interne metadata i `docs/`.
4. Ikke publiser Slack-felter, rå meldingsinnhold, interne ID-er, lokale filstier, eksterne person-ID-er eller andre hjelpefelter.
5. Hvis et felt ikke trengs i nettsiden, skal det bli igjen i lokal arbeidsfil eller lokal database.
6. Public persondata skal begrenses til `person_id`, `profile_slug`, visningsnavn og aggregater/resultatfelter som UI-et bruker.

## Riktig flyt

1. Oppdater lokal arbeidsfil.
2. Bygg lokal database og eventuelle interne kontrollfiler.
3. Koble resultater til `person_id` via lokale identitetsfiler.
4. Lag en egen public payload med whitelistede felter.
5. Skriv bare den public payloaden til `docs/data/results.json`.
6. Verifiser at `docs/data/` ikke inneholder andre datafiler enn det nettsiden trenger.

## Sjekkliste for hver publisering

- Inneholder `docs/data/results.json` bare UI-felter?
- Har JSON-en `schema_version`, `people` og `person_id` på alle resultater?
- Inneholder `docs/` ingen `.sqlite`-filer?
- Ligger ingen lokale filstier i payloaden?
- Ligger ingen Slack-ID-er, råinnhold, eksterne person-ID-er eller interne hjelpefelter i payloaden?
- Er private arbeidsfiler og identitetsfiler fortsatt utenfor committen?
- Er `data/database/identity_reports/public_payload_leaks.csv` tom?

## Hvis noe allerede er lekket

- Fjern filen fra aktiv branch så fort som mulig.
- Regenerer publiserte artefakter med riktig whitelist.
- Vurder separat opprydding i git-historikken hvis dataene ikke skulle vært offentlige.
