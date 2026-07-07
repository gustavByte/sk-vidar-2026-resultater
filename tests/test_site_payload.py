from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_site_2026  # noqa: E402
from build_site_2026 import (  # noqa: E402
    build_months,
    build_week_highlights,
    build_weekly_summary,
    normalize_ranking_distance,
    write_json,
)


def _results_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "result_id": "res-1",
                "person_id": "skv-p1",
                "person_slug": "kari",
                "athlete_name": "Kari",
                "gender": "K",
                "week_number": 10,
                "week_label": "Uke 10",
                "published_date_iso": "2026-03-08",
                "published_date_label": "08.03.2026",
                "event_label": "Testløpet",
                "distance": "10 km",
                "result_time_raw": "35:00",
                "result_time_normalized": "35:00",
                "result_time_seconds": 2100.0,
                "wa_points": 1000.0,
                "is_pb": True,
                "is_sb": False,
            },
            {
                "result_id": "res-2",
                "person_id": "skv-p2",
                "person_slug": "ola",
                "athlete_name": "Ola",
                "gender": "M",
                "week_number": 10,
                "week_label": "Uke 10",
                "published_date_iso": "2026-03-08",
                "published_date_label": "08.03.2026",
                "event_label": "Testløpet",
                "distance": "10 km",
                "result_time_raw": "31:00",
                "result_time_normalized": "31:00",
                "result_time_seconds": 1860.0,
                "wa_points": 900.0,
                "is_pb": False,
                "is_sb": True,
            },
            {
                "result_id": "res-3",
                "person_id": "skv-p2",
                "person_slug": "ola",
                "athlete_name": "Ola",
                "gender": "M",
                "week_number": 12,
                "week_label": "Uke 12",
                "published_date_iso": "2026-03-22",
                "published_date_label": "22.03.2026",
                "event_label": "Terrengløpet",
                "distance": "8 km",
                "result_time_raw": "30:00",
                "result_time_normalized": "30:00",
                "result_time_seconds": 1800.0,
                "wa_points": None,
                "is_pb": False,
                "is_sb": False,
            },
            {
                "result_id": "res-4",
                "person_id": "skv-p3",
                "person_slug": "eva",
                "athlete_name": "Eva",
                "gender": "K",
                "week_number": 12,
                "week_label": "Uke 12",
                "published_date_iso": "2026-03-22",
                "published_date_label": "22.03.2026",
                "event_label": "Aprilløpet",
                "distance": "5 km",
                "result_time_raw": "17:00",
                "result_time_normalized": "17:00",
                "result_time_seconds": 1020.0,
                "wa_points": 950.0,
                "is_pb": False,
                "is_sb": False,
            },
        ]
    )


def test_weekly_summary_counts_flags_and_wa() -> None:
    summary = build_weekly_summary(_results_frame())
    week10 = summary[summary["week_number"] == 10].iloc[0]

    assert int(week10["pb_count"]) == 1
    assert int(week10["sb_count"]) == 1
    assert int(week10["wa_result_count"]) == 2

    week12 = summary[summary["week_number"] == 12].iloc[0]
    assert int(week12["wa_result_count"]) == 1


def test_week_highlights_orders_mixed_genders_by_wa_points() -> None:
    highlights = build_week_highlights(_results_frame())

    top = highlights[10]["top_performances"]
    assert [entry["athlete_name"] for entry in top] == ["Kari", "Ola"]
    assert top[0]["wa_points"] == 1000.0
    assert top[0]["gender"] == "K"

    # Uke 12: kun ett WA-gradert resultat; terrengløpet uten poeng utelates.
    assert [entry["athlete_name"] for entry in highlights[12]["top_performances"]] == ["Eva"]


def test_week_highlights_counts_new_athletes_in_first_week_only() -> None:
    highlights = build_week_highlights(_results_frame())

    assert highlights[10]["new_athlete_count"] == 2  # Kari og Ola debuterer
    assert highlights[12]["new_athlete_count"] == 1  # bare Eva er ny


def test_months_bucketing_sums_to_total() -> None:
    months = build_months(_results_frame())

    assert [entry["month"] for entry in months] == ["2026-03"]
    march = months[0]
    assert march["month_label"] == "Mars"
    assert march["result_count"] == 4
    assert march["athlete_count"] == 3
    assert march["women_count"] == 2
    assert march["men_count"] == 2


def test_ranking_distance_for_road_and_trail_42k() -> None:
    road = pd.Series({"distance": "42 km", "result_time_seconds": 9000.0, "event_label": "Oslo Maraton", "notes_clean": ""})
    trail = pd.Series({"distance": "42 km", "result_time_seconds": 9000.0, "event_label": "Lofoten Skyrace", "notes_clean": ""})
    standard = pd.Series({"distance": "10 km", "result_time_seconds": 2100.0, "event_label": "Testløpet", "notes_clean": ""})
    other = pd.Series({"distance": "3 km", "result_time_seconds": 600.0, "event_label": "Gateløp", "notes_clean": ""})
    steeple = pd.Series({"distance": "3000 m hinder", "result_time_seconds": 560.0, "event_label": "Baneløp", "notes_clean": ""})
    track_10000 = pd.Series({"distance": "10000 m", "result_time_seconds": 1900.0, "event_label": "Baneløp", "notes_clean": ""})
    masters_5000 = pd.Series({"distance": "MV 5000 Meters (M35-M55):", "result_time_seconds": 980.0, "event_label": "Nordic Masters", "notes_clean": ""})
    masters_800 = pd.Series({"distance": "WV 800 Meters (W50,W55)", "result_time_seconds": 150.0, "event_label": "Nordic Masters", "notes_clean": ""})

    assert normalize_ranking_distance(road) == "Maraton"
    assert normalize_ranking_distance(trail) == ""
    assert normalize_ranking_distance(standard) == "10 km"
    assert normalize_ranking_distance(other) == ""
    assert normalize_ranking_distance(steeple) == "3000 m hinder"
    assert normalize_ranking_distance(track_10000) == "10000 m"
    assert normalize_ranking_distance(masters_5000) == "5000 m"
    assert normalize_ranking_distance(masters_800) == "800 m"


def test_write_json_is_minified(tmp_path, monkeypatch) -> None:
    target = tmp_path / "results.json"
    monkeypatch.setattr(build_site_2026, "JSON_FILE", target)

    write_json({"stats": {"result_count": 1}, "results": [{"is_pb": True}]})

    text = target.read_text(encoding="utf-8")
    assert "\n" not in text
    assert '"is_pb":true' in text
