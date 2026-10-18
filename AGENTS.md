# Resultatpublisering – faste brukerpreferanser

- Ta alltid med tilgjengelige offisielle splitter fra store løp på standarddistanser, som Amsterdam maraton. Dette er en fast brukerbeskjed fra 18. oktober 2026.
- Kontroller mellomtidene under innsamlingen og før publisering. Bevar dem gjennom godkjenningskø, batch, offentlig JSON og kildefil; en vellykket resultatimport er ikke ferdig dersom innhentede splitter er droppet.
- Vis normalt første/siste 5 km på 10 km og første/siste halvmaraton på maraton. På halvmaraton brukes offisiell halvveispassering når den finnes, ellers 10 km og resterende 11,0975 km med riktige etiketter. Ikke kall ulikt lange deler positiv/negativ splitt.
- Sluttid og mellomtider må bruke samme tidsgrunnlag. Foretrekk offisielle netto mellomtider ved netto sluttid. Ved omregning fra kumulativ bruttotid trekkes dokumentert startforsinkelse fra; dokumenter beregningen og eventuell sekundavrunding i kildefilen. Ikke summer avrundede segmenttider eller bruk klokkeslett som varighet.
- Mangler en offisiell passering, behold feltet tomt og dokumenter hva som ble undersøkt. Ikke anslå eller interpoler en manglende passering.
- Splitter er metadata til det godkjente sluttresultatet. De skal ikke opprettes som egne resultatlinjer eller endre sluttid, identitet, plassering, WA-poeng eller antall resultater.

Arbeidsflytene finnes i `RESULTATSVEIP_PLAN.md` og ferdighetene `sweep-sk-vidar-results` / `publish-sk-vidar-results`. Det kan ligge upublisert arbeid i hovedmappen; publiser bare oppgavens avgrensede filer fra en ren klone.
