from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_site_2026 import (  # noqa: E402
    build_missing_report,
    build_payload,
    build_rankings,
    build_weekly_summary,
    load_results,
    normalize_ranking_distance,
)
from person_identity import (  # noqa: E402
    build_identity_indexes,
    build_people_payload,
    ensure_new_people_are_appended_without_changing_existing_ids,
    load_identity_data,
    match_result_to_person,
    normalize_name,
    slugify_person_name,
    validate_public_payload,
)
from project_paths import WEEKLY_RESULTS_FILE  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8")


def test_normalize_name_handles_spacing_punctuation_and_diacritics() -> None:
    assert normalize_name("  Ådne  Andersen-Andersen ") == "adne andersen andersen"
    assert normalize_name("Kasper Sørlie-Reininger") == "kasper sorlie reininger"
    assert normalize_name("Madelène Holum") == "madelene holum"


def test_slugify_person_name_is_url_safe() -> None:
    assert slugify_person_name("Ådne Andersen") == "adne-andersen"
    assert slugify_person_name("Kasper Sørlie-Reininger") == "kasper-sorlie-reininger"


def test_new_people_are_appended_without_changing_existing_ids_and_slug_collisions(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "person_registry.csv",
        [
            {
                "person_id": "skv-p000042",
                "display_name": "Existing Person",
                "normalized_name": "existing person",
                "profile_slug": "runner",
                "status": "active",
                "merged_into_person_id": "",
                "created_at": "2026-01-01T00:00:00+01:00",
                "updated_at": "",
                "notes": "",
            }
        ],
        [
            "person_id",
            "display_name",
            "normalized_name",
            "profile_slug",
            "status",
            "merged_into_person_id",
            "created_at",
            "updated_at",
            "notes",
        ],
    )

    results = pd.DataFrame([{"result_id": "res-1", "athlete_name": "Runner"}])
    identity = ensure_new_people_are_appended_without_changing_existing_ids(
        results,
        tmp_path,
        now=datetime.fromisoformat("2026-04-27T12:00:00+02:00"),
    )

    registry = identity.registry.set_index("display_name")
    assert registry.loc["Existing Person", "person_id"] == "skv-p000042"
    assert registry.loc["Runner", "person_id"] == "skv-p000043"
    assert registry.loc["Runner", "profile_slug"] == "runner-2"


def test_match_result_to_person_uses_exact_alias(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "person_registry.csv",
        [
            {
                "person_id": "skv-p000005",
                "display_name": "Kasper Sørlie-Reininger",
                "normalized_name": normalize_name("Kasper Sørlie-Reininger"),
                "profile_slug": "kasper-sorlie-reininger",
                "status": "active",
                "merged_into_person_id": "",
                "created_at": "",
                "updated_at": "",
                "notes": "",
            }
        ],
        [
            "person_id",
            "display_name",
            "normalized_name",
            "profile_slug",
            "status",
            "merged_into_person_id",
            "created_at",
            "updated_at",
            "notes",
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000005",
                "alias": "Kasper S-R",
                "normalized_alias": normalize_name("Kasper S-R"),
                "source": "manual",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )

    identity = load_identity_data(tmp_path)
    match = match_result_to_person({"result_id": "res-1", "athlete_name": "Kasper S-R"}, identity)
    assert match.person_id == "skv-p000005"
    assert match.method == "alias"


def test_rankings_deduplicate_best_result_per_person_id() -> None:
    ranking_df = pd.DataFrame(
        [
            {
                "distance": "5 km",
                "gender": "M",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "result_id": "res-fast",
                "athlete_name": "Runner One",
                "result_time_seconds": 950,
                "result_time_normalized": "15:50",
                "result_time_raw": "15:50",
                "published_date_sort": pd.Timestamp("2026-02-01"),
                "published_date_iso": "2026-02-01",
                "published_date_label": "01.02.2026",
                "event_label": "Testløp",
            },
            {
                "distance": "5 km",
                "gender": "M",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "result_id": "res-slow",
                "athlete_name": "Runner 1",
                "result_time_seconds": 970,
                "result_time_normalized": "16:10",
                "result_time_raw": "16:10",
                "published_date_sort": pd.Timestamp("2026-03-01"),
                "published_date_iso": "2026-03-01",
                "published_date_label": "01.03.2026",
                "event_label": "Testløp 2",
            },
            {
                "distance": "5 km",
                "gender": "M",
                "person_id": "skv-p000002",
                "person_slug": "runner-two",
                "result_id": "res-other",
                "athlete_name": "Runner Two",
                "result_time_seconds": 960,
                "result_time_normalized": "16:00",
                "result_time_raw": "16:00",
                "published_date_sort": pd.Timestamp("2026-02-15"),
                "published_date_iso": "2026-02-15",
                "published_date_label": "15.02.2026",
                "event_label": "Testløp",
            },
        ]
    )

    rankings = build_rankings(ranking_df)
    five_k = next(group for group in rankings if group["distance"] == "5 km")
    men = five_k["men"]
    assert [entry["person_id"] for entry in men] == ["skv-p000001", "skv-p000002"]
    assert men[0]["result_id"] == "res-fast"


def test_public_payload_contract_and_private_field_validation(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "result_id": "res-1",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "published_date_iso": "2026-04-27",
                "published_date_label": "27.04.2026",
                "published_date_sort": pd.Timestamp("2026-04-27"),
                "week_number": 17,
                "week_label": "Uke 17",
                "athlete_name": "Runner One",
                "gender": "M",
                "gender_label": "Menn",
                "class_name": "M senior",
                "class_place": "1",
                "event_label": "Testløp",
                "event_name": "Testløp",
                "distance": "5 km",
                "profile_distance": "5 km",
                "result_time_raw": "15:50",
                "result_time_normalized": "15:50",
                "result_time_seconds": 950,
                "place": "1",
                "notes_clean": "",
                "split_first_label": "",
                "split_first_display": "",
                "split_second_label": "",
                "split_second_display": "",
                "split_delta_display": "",
                "split_state": "",
            }
        ]
    )
    identity = ensure_new_people_are_appended_without_changing_existing_ids(df, tmp_path)
    people_payload = build_people_payload(df, identity)
    payload = build_payload(df, build_weekly_summary(df), build_missing_report(df), build_rankings(df), people_payload)

    assert payload["schema_version"] == 2
    assert payload["people"]["profile_count"] == 1
    assert payload["results"][0]["person_id"] == "skv-p000001"
    validate_public_payload(payload)

    with pytest.raises(ValueError):
        validate_public_payload({"results": [{"slack_user_id": "U123PRIVATE"}]})


def test_generated_public_json_has_people_and_no_private_fields() -> None:
    payload_path = ROOT / "docs" / "data" / "results.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert "people" in payload
    assert all(result.get("person_id") for result in payload["results"])
    validate_public_payload(payload)


def test_build_site_flow_works_with_source_workbook_sample(tmp_path: Path) -> None:
    if not WEEKLY_RESULTS_FILE.exists():
        pytest.skip("Local source workbook is not available")

    df = load_results().head(30).copy()
    identity = ensure_new_people_are_appended_without_changing_existing_ids(df, tmp_path)
    indexes = build_identity_indexes(identity)

    person_ids = []
    person_slugs = []
    for _, row in df.iterrows():
        match = match_result_to_person(row, identity, indexes)
        person_ids.append(match.person_id)
        person_slugs.append(indexes.slug_by_person_id.get(match.person_id, ""))

    df["person_id"] = person_ids
    df["person_slug"] = person_slugs
    df["profile_distance"] = df.apply(normalize_ranking_distance, axis=1)

    payload = build_payload(
        df,
        build_weekly_summary(df),
        build_missing_report(df),
        build_rankings(df),
        build_people_payload(df, identity),
    )

    assert payload["stats"]["result_count"] == len(df)
    assert all(result["person_id"] for result in payload["results"])
    validate_public_payload(payload)
