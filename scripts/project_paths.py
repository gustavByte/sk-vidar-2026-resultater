from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"

ARBEIDSFILER_DIR = DATA_DIR / "arbeidsfiler"
DELT_OVERSIKT_DIR = DATA_DIR / "delt_oversikt"
INPUT_RESULTATER_DIR = DATA_DIR / "input_resultater"
STOTTEFILER_DIR = DATA_DIR / "stottefiler"
OVERGANGER_DIR = STOTTEFILER_DIR / "overganger"
NM_UTOVERE_DIR = STOTTEFILER_DIR / "nm_utovere_oppfolging"
OVERRIDES_FILE = STOTTEFILER_DIR / "result_overrides_2026.csv"
MISSING_REPORT_FILE = DATA_DIR / "database" / "missing_gender_class_2026.csv"
IDENTITY_REPORT_DIR = DATA_DIR / "database" / "identity_reports"
PERSON_IDENTITY_DIR = STOTTEFILER_DIR / "personer"
PERSON_REGISTRY_FILE = PERSON_IDENTITY_DIR / "person_registry.csv"
PERSON_ALIASES_FILE = PERSON_IDENTITY_DIR / "person_aliases.csv"
PERSON_EXTERNAL_IDS_FILE = PERSON_IDENTITY_DIR / "person_external_ids.csv"
PERSON_SLUG_HISTORY_FILE = PERSON_IDENTITY_DIR / "person_slug_history.csv"
RESULT_PERSON_OVERRIDES_FILE = PERSON_IDENTITY_DIR / "result_person_overrides.csv"
PERSON_MATCH_DECISIONS_FILE = PERSON_IDENTITY_DIR / "person_match_decisions.csv"

WEEKLY_RESULTS_FILE = ARBEIDSFILER_DIR / "weekly_results_2026.xlsx"
SHARED_OVERVIEW_FILE = DELT_OVERSIKT_DIR / "SK Vidar Langdistanse 2026.xlsx"
DRAMMEN_RESULTS_FILE = (
    ROOT_DIR.parent.parent / "Div beregininger" / "API resulater" / "Drammen 10k" / "drammen_10k_2026_resultater.xlsx"
)
