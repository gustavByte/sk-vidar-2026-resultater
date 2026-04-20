# Publishing Standard

Denne standarden gjelder for prosjektet sa lenge repoet er offentlig.

## Mal

- `docs/` er offentlig publiseringssone.
- `data/arbeidsfiler/`, `data/database/` og `data/stottefiler/` er lokale/private arbeidsomrader.
- Frontenden skal bare lese publiseringsklare filer som er laget eksplisitt for browseren.

## Regler

1. Publiser bare minimumsdata som faktisk brukes i UI-et.
2. Ikke serialiser hele arbeidsdatasett direkte til offentlige JSON-filer.
3. Ikke publiser SQLite-filer, kontrollrapporter eller interne metadata i `docs/`.
4. Ikke publiser Slack-felter, rå meldingsinnhold, interne ID-er, lokale filstier eller andre hjelpefelter.
5. Hvis et felt ikke trengs i nettsiden, skal det bli igjen i lokal arbeidsfil eller lokal database.

## Riktig flyt

1. Oppdater lokal arbeidsfil.
2. Bygg lokal database og eventuelle interne kontrollfiler.
3. Lag en egen public payload med whitelistede felter.
4. Skriv bare den public payloaden til `docs/data/results.json`.
5. Verifiser at `docs/data/` ikke inneholder andre datafiler enn det nettsiden trenger.

## Sjekkliste for hver publisering

- Inneholder `docs/data/results.json` bare UI-felter?
- Inneholder `docs/` ingen `.sqlite`-filer?
- Ligger ingen lokale filstier i payloaden?
- Ligger ingen Slack-ID-er, råinnhold eller interne hjelpefelter i payloaden?
- Er private arbeidsfiler fortsatt utenfor committen?

## Hvis noe allerede er lekket

- Fjern filen fra aktiv branch sa fort som mulig.
- Regenerer publiserte artefakter med riktig whitelist.
- Vurder separat opprydding i git-historikken hvis dataene ikke skulle vaert offentlige.
