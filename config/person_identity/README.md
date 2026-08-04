# Canonical person identity seed

Disse CSV-filene er en sanitert, versjonert kopi av identitetsgrafen som brukes til å bygge nettsiden reproducerbart i et nytt arbeidsområde.

Byggeskriptet vedlikeholder filene automatisk. Kopien omfatter stabile person-ID-er, offentlige navnealiaser, sammenslåinger, slug-historikk, eventuelle resultatoverstyringer og saniterte matchbeslutninger. Private eksterne ID-er, `person_drafts.csv` og manuelle vurderingsnotater skal aldri legges her.

Den versjonerte kopien er autoritativ for offentlige identitetsfelt i et eksisterende lokalt arbeidsområde. Nye lokale endringer skrives tilbake hit først etter at alle publiseringskontroller har passert; matchbeslutninger som brukes via review-skriptet synkroniseres med en gang.
