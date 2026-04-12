from __future__ import annotations

import json
import math
import shutil
import sqlite3
from datetime import datetime

import pandas as pd

from build_shared_weekly_results_2026 import (
    EVENT_NAME_OVERRIDES,
    clean_note,
    extract_place,
    parse_time_for_sort,
)
from project_paths import ROOT_DIR, WEEKLY_RESULTS_FILE


DATA_DB_DIR = ROOT_DIR / "data" / "database"
PUBLIC_DATA_DIR = ROOT_DIR / "docs" / "data"
DB_FILE = DATA_DB_DIR / "sk_vidar_2026.sqlite"
PUBLIC_DB_FILE = PUBLIC_DATA_DIR / "sk_vidar_2026.sqlite"
JSON_FILE = PUBLIC_DATA_DIR / "results.json"

DISTANCE_ORDER = {
    "800 m": 1,
    "1500 m": 2,
    "3000 m": 3,
    "5 km": 4,
    "10 km": 5,
    "Halvmaraton": 6,
    "Maraton": 7,
    "42 km": 7,
    "30 km": 8,
    "60 km": 9,
}

SPLIT_LABELS = {
    "3000 m": ("1500 m", "1500 m"),
    "5 km": ("2.5 km", "2.5 km"),
    "10 km": ("5 km", "5 km"),
    "Halvmaraton": ("10 km", "11.1 km"),
    "Maraton": ("21.1 km", "21.1 km"),
}


def _serialize_value(value: object) -> object:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    return value


def format_duration(seconds: float | int | None) -> str:
    if seconds is None or pd.isna(seconds):
        return ""

    total = float(seconds)
    sign = "-" if total < 0 else ""
    total = abs(total)
    minutes = int(total // 60)
    remainder = total - minutes * 60

    if abs(remainder - round(remainder)) < 0.005:
        return f"{sign}{minutes}:{int(round(remainder)):02d}"
    return f"{sign}{minutes}:{remainder:05.2f}"


def format_delta(seconds: float | int | None) -> str:
    if seconds is None or pd.isna(seconds):
        return ""

    total = float(seconds)
    if abs(total) < 0.005:
        return "00:00"

    sign = "+" if total > 0 else "-"
    return f"{sign}{format_duration(abs(total))}"


def split_labels(distance: str) -> tuple[str, str]:
    return SPLIT_LABELS.get(distance, ("Split 1", "Split 2"))


def load_results() -> pd.DataFrame:
    if not WEEKLY_RESULTS_FILE.exists():
        raise FileNotFoundError(f"Missing source workbook: {WEEKLY_RESULTS_FILE}")

    df = pd.read_excel(WEEKLY_RESULTS_FILE, sheet_name="results", engine="openpyxl")
    working = df.copy()

    working["published_date"] = pd.to_datetime(working["published_date"], errors="coerce")
    working["published_date_iso"] = working["published_date"].dt.strftime("%Y-%m-%d")
    working["published_date_label"] = working["published_date"].dt.strftime("%d.%m.%Y")
    working["week_number"] = pd.to_numeric(working["week_number"], errors="coerce")
    working["week_label"] = working["week_number"].apply(lambda value: f"Uke {int(value)}" if pd.notna(value) else "")
    working["event_label"] = working["event_name"].fillna("").astype(str).str.strip().replace(EVENT_NAME_OVERRIDES)
    working["notes_clean"] = working["notes"].apply(clean_note)
    working["place"] = [extract_place(position, note) for position, note in zip(working["position"], working["notes"])]
    working["result_time_source"] = working["result_time_normalized"].fillna(working["result_time_raw"])
    working["secondary_time_source"] = working["secondary_time_normalized"].fillna(working["secondary_time_raw"])
    working["result_time_seconds"] = working["result_time_source"].apply(parse_time_for_sort)
    working["secondary_time_seconds"] = working["secondary_time_source"].apply(parse_time_for_sort)
    working["distance_sort"] = working["distance"].fillna("").map(DISTANCE_ORDER).fillna(99)
    working["event_sort"] = working["event_label"]
    working["week_sort"] = working["week_number"]
    working["published_date_sort"] = working["published_date"]
    working["display_order"] = range(1, len(working) + 1)

    split_first_seconds = []
    split_second_seconds = []
    split_delta_seconds = []
    split_first_labels = []
    split_second_labels = []
    split_states = []

    for _, row in working.iterrows():
        result_seconds = row["result_time_seconds"]
        secondary_seconds = row["secondary_time_seconds"]
        distance = str(row.get("distance") or "").strip()

        if (
            pd.isna(result_seconds)
            or pd.isna(secondary_seconds)
            or secondary_seconds >= result_seconds
            or result_seconds <= 0
        ):
            split_first_seconds.append(None)
            split_second_seconds.append(None)
            split_delta_seconds.append(None)
            split_first_labels.append("")
            split_second_labels.append("")
            split_states.append("")
            continue

        first = float(secondary_seconds)
        second = float(result_seconds) - first
        delta = second - first
        first_label, second_label = split_labels(distance)
        split_first_seconds.append(first)
        split_second_seconds.append(second)
        split_delta_seconds.append(delta)
        split_first_labels.append(first_label)
        split_second_labels.append(second_label)
        if abs(delta) < 0.005:
            split_states.append("even")
        elif delta > 0:
            split_states.append("slow")
        else:
            split_states.append("fast")

    working["split_first_seconds"] = split_first_seconds
    working["split_second_seconds"] = split_second_seconds
    working["split_delta_seconds"] = split_delta_seconds
    working["split_first_label"] = split_first_labels
    working["split_second_label"] = split_second_labels
    working["split_state"] = split_states
    working["split_first_display"] = working["split_first_seconds"].apply(format_duration)
    working["split_second_display"] = working["split_second_seconds"].apply(format_duration)
    working["split_delta_display"] = working["split_delta_seconds"].apply(format_delta)
    working["has_split"] = working["split_state"].astype(bool)

    working = working.sort_values(
        ["week_sort", "published_date_sort", "event_sort", "distance_sort", "result_time_seconds", "athlete_name"],
        ascending=[False, False, True, True, True, True],
        na_position="last",
    ).reset_index(drop=True)

    return working


def build_weekly_summary(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["week_number", "week_label"], dropna=False)
        .agg(
            result_count=("athlete_name", "count"),
            athlete_count=("athlete_name", "nunique"),
            event_count=("event_label", "nunique"),
            published_date_iso=("published_date_iso", "max"),
            published_date_label=("published_date_label", "max"),
            events=(
                "event_label",
                lambda values: sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip()}),
            ),
        )
        .reset_index()
    )

    return grouped.sort_values(
        ["week_number", "published_date_iso"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)


def row_to_dict(row: pd.Series) -> dict[str, object]:
    data = {key: _serialize_value(value) for key, value in row.to_dict().items()}
    data["week_number"] = int(data["week_number"]) if data["week_number"] is not None else None
    data["result_time_seconds"] = _serialize_value(row["result_time_seconds"])
    data["secondary_time_seconds"] = _serialize_value(row["secondary_time_seconds"])
    data["distance_sort"] = _serialize_value(row["distance_sort"])
    data["week_sort"] = _serialize_value(row["week_sort"])
    data["published_date_sort"] = _serialize_value(row["published_date_sort"])
    data["split_first_seconds"] = _serialize_value(row["split_first_seconds"])
    data["split_second_seconds"] = _serialize_value(row["split_second_seconds"])
    data["split_delta_seconds"] = _serialize_value(row["split_delta_seconds"])
    return data


def build_payload(df: pd.DataFrame, summary_df: pd.DataFrame) -> dict[str, object]:
    results = [row_to_dict(row) for _, row in df.iterrows()]
    weeks = []
    for _, row in summary_df.iterrows():
        weeks.append(
            {
                "week_number": int(row["week_number"]) if pd.notna(row["week_number"]) else None,
                "week_label": row["week_label"],
                "published_date": row["published_date_iso"],
                "published_date_label": row["published_date_label"],
                "result_count": int(row["result_count"]),
                "athlete_count": int(row["athlete_count"]),
                "event_count": int(row["event_count"]),
                "events": row["events"],
            }
        )

    stats = {
        "result_count": int(len(df)),
        "athlete_count": int(df["athlete_name"].nunique()),
        "event_count": int(df["event_name"].nunique()),
        "week_count": int(df["week_number"].nunique()),
        "latest_week": int(df["week_number"].max()),
        "latest_date": df["published_date_iso"].max(),
    }

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file": str(WEEKLY_RESULTS_FILE),
        "stats": stats,
        "weeks": weeks,
        "results": results,
    }


def write_database(df: pd.DataFrame, summary_df: pd.DataFrame, payload: dict[str, object]) -> None:
    DATA_DB_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

    metadata = pd.DataFrame(
        [
            {"key": "generated_at", "value": payload["generated_at"]},
            {"key": "source_file", "value": payload["source_file"]},
            {"key": "result_count", "value": payload["stats"]["result_count"]},
            {"key": "athlete_count", "value": payload["stats"]["athlete_count"]},
            {"key": "event_count", "value": payload["stats"]["event_count"]},
            {"key": "week_count", "value": payload["stats"]["week_count"]},
            {"key": "latest_week", "value": payload["stats"]["latest_week"]},
            {"key": "latest_date", "value": payload["stats"]["latest_date"]},
        ]
    )

    db_results = df[
        [
            "published_date_iso",
            "published_date_label",
            "week_number",
            "week_label",
            "event_name",
            "event_label",
            "distance",
            "category",
            "athlete_name",
            "slack_user_id",
            "slack_name",
            "name_in_message",
            "result_time_raw",
            "result_time_normalized",
            "secondary_time_raw",
            "secondary_time_normalized",
            "position",
            "notes",
            "notes_clean",
            "place",
            "raw_entry",
            "source_ts",
            "source_order",
            "WA Kjønn",
            "WA Øvelse",
            "WA Poeng",
            "NM sync",
            "Beste pr person",
            "result_time_source",
            "secondary_time_source",
            "result_time_seconds",
            "secondary_time_seconds",
            "split_first_seconds",
            "split_second_seconds",
            "split_delta_seconds",
            "split_first_label",
            "split_second_label",
            "split_state",
        ]
    ].copy()

    db_results = db_results.rename(
        columns={
            "published_date_iso": "published_date",
            "published_date_label": "published_date_label",
            "week_number": "week_number",
            "week_label": "week_label",
            "event_name": "event_name",
            "event_label": "event_label",
            "distance": "distance",
            "category": "category",
            "athlete_name": "athlete_name",
            "slack_user_id": "slack_user_id",
            "slack_name": "slack_name",
            "name_in_message": "name_in_message",
            "result_time_raw": "result_time_raw",
            "result_time_normalized": "result_time_normalized",
            "secondary_time_raw": "secondary_time_raw",
            "secondary_time_normalized": "secondary_time_normalized",
            "position": "position",
            "notes": "notes",
            "notes_clean": "notes_clean",
            "place": "place",
            "raw_entry": "raw_entry",
            "source_ts": "source_ts",
            "source_order": "source_order",
            "WA Kjønn": "wa_kjonn",
            "WA Øvelse": "wa_ovelse",
            "WA Poeng": "wa_poeng",
            "NM sync": "nm_sync",
            "Beste pr person": "beste_pr_person",
            "result_time_source": "result_time_source",
            "secondary_time_source": "secondary_time_source",
            "result_time_seconds": "result_time_seconds",
            "secondary_time_seconds": "secondary_time_seconds",
            "split_first_seconds": "split_first_seconds",
            "split_second_seconds": "split_second_seconds",
            "split_delta_seconds": "split_delta_seconds",
            "split_first_label": "split_first_label",
            "split_second_label": "split_second_label",
            "split_state": "split_state",
        }
    )

    summary_db = summary_df.copy()
    summary_db["events"] = summary_db["events"].apply(lambda values: ", ".join(values))

    with sqlite3.connect(DB_FILE) as connection:
        metadata.to_sql("metadata", connection, if_exists="replace", index=False)
        db_results.to_sql("results", connection, if_exists="replace", index=False)
        summary_db.to_sql("weekly_summary", connection, if_exists="replace", index=False)

    shutil.copy2(DB_FILE, PUBLIC_DB_FILE)


def write_json(payload: dict[str, object]) -> None:
    JSON_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    df = load_results()
    summary_df = build_weekly_summary(df)
    payload = build_payload(df, summary_df)
    write_database(df, summary_df, payload)
    write_json(payload)

    print(f"Created SQLite database: {DB_FILE}")
    print(f"Created public copy: {PUBLIC_DB_FILE}")
    print(f"Created JSON export: {JSON_FILE}")
    print(f"Rows: {payload['stats']['result_count']}")
    print(f"Weeks: {payload['stats']['week_count']}")


if __name__ == "__main__":
    main()
