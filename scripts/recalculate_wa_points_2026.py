from __future__ import annotations

import sys
from dataclasses import dataclass

import pandas as pd

from project_paths import WA_SCORING_DB_FILE, WA_TOOLKIT_DIR, WEEKLY_RESULTS_FILE


RESULTS_SHEET = "results"
WA_GENDER_COLUMN = "WA Kjønn"
WA_EVENT_COLUMN = "WA Øvelse"
WA_POINTS_COLUMN = "WA Poeng"

MOJIBAKE_WA_COLUMNS = ("WA Kj?nn", "WA ?velse", "WA KjÃ¸nn", "WA Ã˜velse")

DISTANCE_TO_WA_EVENT = {
    "600 m": "600m",
    "800 m": "800m",
    "1500 m": "1500m",
    "3000 m": "3000m",
    "5 km": "5 km",
    "10 km": "10 km",
    "15 km": "15 km",
    "10 mile": "10 Miles",
    "10 miles": "10 Miles",
    "Halvmaraton": "HM",
    "Maraton": "Marathon",
    "30 km": "30 km",
}

WA_EVENT_DISPLAY = {
    "600m": "600m",
    "800m": "800m",
    "1500m": "1500m",
    "3000m": "3000m",
    "5 km": "5 km",
    "10 km": "10 km",
    "15 km": "15 km",
    "10 Miles": "10 Miles",
    "HM": "Halvmaraton",
    "Marathon": "Maraton",
    "30 km": "30 km",
}

ROAD_BISLETT_PREFIX = "bislett distanseserie"


@dataclass(frozen=True)
class WaSummary:
    rows: int
    calculated: int
    unsupported: int
    missing_time: int
    missing_gender: int


def _load_calculator_class():
    if not WA_SCORING_DB_FILE.exists():
        raise FileNotFoundError(f"Missing WA scoring database: {WA_SCORING_DB_FILE}")
    sys.path.insert(0, str(WA_TOOLKIT_DIR))
    from wa_poeng import ScoreCalculator

    return ScoreCalculator


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _normalize_gender(value: object) -> str:
    text = _clean_text(value).upper()
    if text.startswith("K"):
        return "K"
    if text.startswith("M"):
        return "M"
    return ""


def _wa_gender(value: str) -> str:
    if value == "K":
        return "Women"
    if value == "M":
        return "Men"
    return ""


def _wa_event_for_row(row: pd.Series) -> str:
    distance = _clean_text(row.get("distance"))
    event_name = _clean_text(row.get("event_name")).casefold()

    if event_name.startswith(ROAD_BISLETT_PREFIX) and distance == "3000 m":
        return ""

    return DISTANCE_TO_WA_EVENT.get(distance, "")


def _result_time(row: pd.Series) -> str:
    normalized = _clean_text(row.get("result_time_normalized"))
    if normalized:
        return normalized
    return _clean_text(row.get("result_time_raw"))


def _ensure_wa_columns(df: pd.DataFrame) -> pd.DataFrame:
    working = df.copy()
    for column in MOJIBAKE_WA_COLUMNS:
        if column in working.columns and column not in {WA_GENDER_COLUMN, WA_EVENT_COLUMN}:
            working = working.drop(columns=[column])
    for column in (WA_GENDER_COLUMN, WA_EVENT_COLUMN, WA_POINTS_COLUMN):
        if column not in working.columns:
            working[column] = ""
    return working


def recalculate_wa_points() -> tuple[pd.DataFrame, WaSummary]:
    if not WEEKLY_RESULTS_FILE.exists():
        raise FileNotFoundError(f"Missing source workbook: {WEEKLY_RESULTS_FILE}")

    ScoreCalculator = _load_calculator_class()
    working = _ensure_wa_columns(pd.read_excel(WEEKLY_RESULTS_FILE, sheet_name=RESULTS_SHEET, engine="openpyxl"))

    calculated = 0
    unsupported = 0
    missing_time = 0
    missing_gender = 0
    genders: list[str] = []
    events: list[str] = []
    points: list[object] = []

    with ScoreCalculator(WA_SCORING_DB_FILE) as calculator:
        for _, row in working.iterrows():
            gender = _normalize_gender(row.get("gender")) or _normalize_gender(row.get("class_name")) or _normalize_gender(row.get("category"))
            wa_gender = _wa_gender(gender)
            wa_event = _wa_event_for_row(row)
            performance = _result_time(row)

            genders.append(gender)
            events.append(WA_EVENT_DISPLAY.get(wa_event, ""))

            if not wa_gender:
                points.append("")
                missing_gender += 1
                continue
            if not performance:
                points.append("")
                missing_time += 1
                continue
            if not wa_event:
                points.append("")
                unsupported += 1
                continue

            try:
                points.append(calculator.points_for_performance(wa_gender, wa_event, performance)["points"])
                calculated += 1
            except Exception:
                points.append("")
                unsupported += 1

    working[WA_GENDER_COLUMN] = genders
    working[WA_EVENT_COLUMN] = events
    working[WA_POINTS_COLUMN] = points

    summary = WaSummary(
        rows=len(working),
        calculated=calculated,
        unsupported=unsupported,
        missing_time=missing_time,
        missing_gender=missing_gender,
    )
    return working, summary


def write_results_workbook(df: pd.DataFrame) -> None:
    with pd.ExcelWriter(WEEKLY_RESULTS_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name=RESULTS_SHEET, index=False)


def main() -> None:
    df, summary = recalculate_wa_points()
    write_results_workbook(df)
    print(f"Updated WA points in: {WEEKLY_RESULTS_FILE}")
    print(f"Rows: {summary.rows}")
    print(f"Calculated: {summary.calculated}")
    print(f"Unsupported/no official WA event: {summary.unsupported}")
    print(f"Missing time: {summary.missing_time}")
    print(f"Missing gender: {summary.missing_gender}")


if __name__ == "__main__":
    main()
