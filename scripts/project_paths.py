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

WEEKLY_RESULTS_FILE = ARBEIDSFILER_DIR / "weekly_results_2026.xlsx"
SHARED_OVERVIEW_FILE = DELT_OVERSIKT_DIR / "SK Vidar Langdistanse 2026.xlsx"
