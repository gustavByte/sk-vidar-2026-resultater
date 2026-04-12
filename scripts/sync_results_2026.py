from __future__ import annotations

import math

import pandas as pd

from project_paths import DRAMMEN_RESULTS_FILE, OVERRIDES_FILE, WEEKLY_RESULTS_FILE


DRAMMEN_DATE = "2026-04-11"
DRAMMEN_EVENT = "Drammen10K"
DRAMMEN_DISTANCE = "10 km"
RESULTS_SHEET = "results"
MANAGED_COLUMNS = [
    "gender",
    "class_name",
    "class_place",
    "split_first_raw",
    "split_second_raw",
    "split_delta_raw",
]

TEXT_FIXES = {
    "Fredrikstadl?pet": "Fredrikstadløpet",
    "J?rgen Korum": "Jørgen Korum",
    "Liz-Helen L?chen": "Liz-Helen Løchen",
    "Alva Witnes Ertresv?g": "Alva Witnes Ertresvåg",
    "Bj?rnar Slettv?g": "Bjørnar Slettvåg",
    "M ?pen": "M åpen",
}


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _fix_text(value: object) -> str:
    text = _clean_text(value)
    for bad, good in TEXT_FIXES.items():
        text = text.replace(bad, good)
    return text


def _normalize_time(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = text.replace("(sluttid)", "").strip()
    if text.startswith("00:"):
        return text[3:]
    if text.startswith("0:") and text.count(":") == 2:
        return text[2:]
    return text


def _normalize_gender(value: object) -> str:
    text = _clean_text(value).upper()
    if text.startswith("K"):
        return "K"
    if text.startswith("M"):
        return "M"
    return ""


def _result_key(published_date: object, event_name: object, distance: object, athlete_name: object) -> tuple[str, str, str, str]:
    return (
        _clean_text(published_date),
        _fix_text(event_name),
        _fix_text(distance),
        _fix_text(athlete_name),
    )


def load_overrides() -> dict[tuple[str, str, str, str], dict[str, str]]:
    if not OVERRIDES_FILE.exists():
        return {}

    overrides_df = pd.read_csv(OVERRIDES_FILE, dtype=str).fillna("")
    overrides = {}
    for _, row in overrides_df.iterrows():
        key = _result_key(row["published_date"], row["event_name"], row["distance"], row["athlete_name"])
        overrides[key] = {
            "gender": _normalize_gender(row.get("gender", "")),
            "class_name": _clean_text(row.get("class_name", "")),
            "class_place": _clean_text(row.get("class_place", "")),
        }
    return overrides


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    working = df.copy()
    for column in MANAGED_COLUMNS:
        if column not in working.columns:
            working[column] = ""
    return working


def read_workbook_results() -> pd.DataFrame:
    df = pd.read_excel(WEEKLY_RESULTS_FILE, sheet_name=RESULTS_SHEET, engine="openpyxl")
    return ensure_columns(df)


def read_drammen_results() -> pd.DataFrame:
    if not DRAMMEN_RESULTS_FILE.exists():
        raise FileNotFoundError(f"Missing Drammen source workbook: {DRAMMEN_RESULTS_FILE}")

    df = pd.read_excel(DRAMMEN_RESULTS_FILE, sheet_name="SK Vidar", header=2, engine="openpyxl")
    df = df[df["Navn"].notna()].copy()
    return df


def build_drammen_rows(base_df: pd.DataFrame, overrides: dict[tuple[str, str, str, str], dict[str, str]]) -> pd.DataFrame:
    source = read_drammen_results()
    rows: list[dict[str, object]] = []

    for _, row in source.iterrows():
        athlete_name = _clean_text(row.get("Navn"))
        class_name = _clean_text(row.get("Klasse"))
        gender = _normalize_gender(class_name)
        override = overrides.get(_result_key(DRAMMEN_DATE, DRAMMEN_EVENT, DRAMMEN_DISTANCE, athlete_name), {})

        if override.get("gender"):
            gender = override["gender"]
        if override.get("class_name"):
            class_name = override["class_name"]
        if not class_name and gender:
            class_name = f"{gender} åpen"

        result_row = {column: None for column in base_df.columns}
        result_row.update(
            {
                "published_date": DRAMMEN_DATE,
                "week_number": 15,
                "event_name": DRAMMEN_EVENT,
                "distance": DRAMMEN_DISTANCE,
                "category": class_name or None,
                "athlete_name": athlete_name,
                "slack_user_id": None,
                "slack_name": None,
                "name_in_message": None,
                "result_time_raw": _normalize_time(row.get("Tid") or row.get("Nettotid")),
                "result_time_normalized": _normalize_time(row.get("Tid") or row.get("Nettotid")),
                "secondary_time_raw": _normalize_time(row.get("5 km tid")),
                "secondary_time_normalized": _normalize_time(row.get("5 km tid")),
                "position": _clean_text(row.get("Plass")) or None,
                "notes": None,
                "raw_entry": _clean_text(row.get("Deltakerkilde")) or _clean_text(row.get("Resultatkilde")) or "Drammen reimport 2026",
                "source_ts": "drammen-reimport-2026",
                "source_order": pd.to_numeric(row.get("Plass"), errors="coerce"),
                "WA Kjønn": gender or None,
                "WA Øvelse": DRAMMEN_DISTANCE,
                "WA Poeng": None,
                "NM sync": "Drammen reimport 2026",
                "Beste pr person": None,
                "gender": gender or None,
                "class_name": class_name or None,
                "class_place": override.get("class_place") or _clean_text(row.get("Plass klasse detalj")) or None,
                "split_first_raw": _normalize_time(row.get("5 km tid")),
                "split_second_raw": _normalize_time(row.get("Siste 5 km")),
                "split_delta_raw": _clean_text(row.get("Splitt")) or None,
            }
        )
        rows.append(result_row)

    imported_df = pd.DataFrame(rows, columns=base_df.columns)
    imported_df["source_order"] = pd.to_numeric(imported_df["source_order"], errors="coerce")
    return imported_df


def apply_defaults(df: pd.DataFrame, overrides: dict[tuple[str, str, str, str], dict[str, str]]) -> pd.DataFrame:
    working = ensure_columns(df)

    working["published_date"] = pd.to_datetime(working["published_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in ["event_name", "athlete_name", "category", "class_name", "raw_entry", "slack_name", "name_in_message"]:
        if column in working.columns:
            working[column] = working[column].fillna("").map(_fix_text)
    if "notes" in working.columns:
        working["notes"] = working["notes"].fillna("")

        anders_mask = (
            working["athlete_name"].eq("Anders Nordby")
            & working["event_name"].eq("Milano Marathon")
        )
        fredrikstad_5k_mask = (
            working["event_name"].eq("Fredrikstadløpet")
            & working["distance"].eq("5 km")
        )
        working.loc[anders_mask | fredrikstad_5k_mask, "notes"] = ""

    derived_class_name = working["class_name"].fillna("")
    derived_class_name = derived_class_name.mask(derived_class_name.eq(""), working["category"].fillna(""))
    working["class_name"] = derived_class_name

    derived_gender = working["gender"].fillna("")
    derived_gender = derived_gender.mask(derived_gender.eq(""), working["WA Kjønn"].fillna("").map(_normalize_gender))
    derived_gender = derived_gender.mask(
        derived_gender.eq(""),
        working["class_name"].fillna("").astype(str).str.extract(r"^([KM])", expand=False).fillna(""),
    )
    working["gender"] = derived_gender

    for index, row in working.iterrows():
        key = _result_key(row.get("published_date"), row.get("event_name"), row.get("distance"), row.get("athlete_name"))
        override = overrides.get(key)
        if not override:
            continue
        if override.get("gender"):
            working.at[index, "gender"] = override["gender"]
        if override.get("class_name"):
            working.at[index, "class_name"] = override["class_name"]
        if override.get("class_place"):
            working.at[index, "class_place"] = override["class_place"]

    working["gender"] = working["gender"].fillna("").map(_normalize_gender)
    working["class_name"] = working["class_name"].fillna("")
    working["class_name"] = working["class_name"].mask(
        working["class_name"].eq("") & working["gender"].ne(""),
        working["gender"] + " åpen",
    )
    working["category"] = working["category"].fillna("")
    working["category"] = working["category"].mask(working["category"].eq(""), working["class_name"])
    working["WA Kjønn"] = working["WA Kjønn"].fillna("")
    working["WA Kjønn"] = working["WA Kjønn"].mask(working["WA Kjønn"].eq(""), working["gender"])
    return working


def sync_results_workbook() -> pd.DataFrame:
    overrides = load_overrides()
    base_df = read_workbook_results()
    drammen_rows = build_drammen_rows(base_df, overrides)

    published_dates = pd.to_datetime(base_df["published_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    event_series = base_df["event_name"].fillna("").astype(str)
    keep_mask = ~(
        published_dates.eq(DRAMMEN_DATE)
        & event_series.str.contains("Drammen10K", case=False, na=False)
        & base_df["distance"].astype(str).eq(DRAMMEN_DISTANCE)
    )
    working = pd.concat([base_df[keep_mask].copy(), drammen_rows], ignore_index=True)
    working = apply_defaults(working, overrides)

    with pd.ExcelWriter(WEEKLY_RESULTS_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        working.to_excel(writer, sheet_name=RESULTS_SHEET, index=False)

    return working


def main() -> None:
    working = sync_results_workbook()
    drammen_count = (
        working["published_date"].astype(str).eq(DRAMMEN_DATE)
        & working["event_name"].astype(str).eq(DRAMMEN_EVENT)
        & working["distance"].astype(str).eq(DRAMMEN_DISTANCE)
    ).sum()
    print(f"Synced results workbook: {WEEKLY_RESULTS_FILE}")
    print(f"Drammen rows: {int(drammen_count)}")


if __name__ == "__main__":
    main()
