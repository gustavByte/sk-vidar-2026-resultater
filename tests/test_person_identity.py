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
    MATCH_DECISION_COLUMNS,
    apply_match_decisions,
    build_identity_indexes,
    build_people_payload,
    build_person_match_candidates,
    candidate_id_for_people,
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


def write_basic_registry(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "person_id",
        "display_name",
        "normalized_name",
        "profile_slug",
        "status",
        "merged_into_person_id",
        "created_at",
        "updated_at",
        "notes",
    ]
    normalized_rows = []
    for row in rows:
        normalized = {column: row.get(column, "") for column in columns}
        normalized["normalized_name"] = normalized["normalized_name"] or normalize_name(normalized["display_name"])
        normalized["status"] = normalized["status"] or "active"
        normalized_rows.append(normalized)
    write_csv(tmp_path / "person_registry.csv", normalized_rows, columns)


def test_existing_mojibake_display_names_are_repaired_for_public_profiles(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {
                "person_id": "skv-p000001",
                "display_name": "\u00c3\u0085dne Andersen",
                "profile_slug": "adne-andersen",
            }
        ],
    )

    results = pd.DataFrame([{"result_id": "res-1", "athlete_name": "\u00c3\u0085dne Andersen"}])
    identity = ensure_new_people_are_appended_without_changing_existing_ids(
        results,
        tmp_path,
        now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"),
    )

    registry = identity.registry.set_index("person_id")
    assert registry.loc["skv-p000001", "display_name"] == "\u00c5dne Andersen"

    public_results = pd.DataFrame(
        [
            {
                "person_id": "skv-p000001",
                "athlete_name": "\u00c3\u0085dne Andersen",
                "distance": "5 km",
                "gender": "M",
                "result_time_seconds": float("inf"),
                "published_date_iso": "2026-04-25",
            }
        ]
    )
    payload = build_people_payload(public_results, identity)

    assert payload["profiles"][0]["display_name"] == "\u00c5dne Andersen"


def write_basic_slug_history(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    write_csv(
        tmp_path / "person_slug_history.csv",
        rows,
        ["person_id", "profile_slug", "active_from", "active_to", "reason"],
    )


def test_person_match_candidates_include_said_middle_name_variant(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000273", "display_name": "Said Abdullahi", "profile_slug": "said-abdullahi"},
            {
                "person_id": "skv-p000274",
                "display_name": "Said Garaashe Abdullahi",
                "profile_slug": "said-garaashe-abdullahi",
            },
        ],
    )
    identity = load_identity_data(tmp_path)
    results = pd.DataFrame(
        [
            {"person_id": "skv-p000273", "published_date": "2026-01-01"},
            {"person_id": "skv-p000274", "published_date": "2026-02-01"},
        ]
    )

    candidates = build_person_match_candidates(identity, results)

    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["candidate_id"] == candidate_id_for_people("skv-p000273", "skv-p000274")
    assert candidate["confidence"] == "strong"
    assert candidate["suggested_decision"] == "merge"


def test_apply_merge_decision_moves_results_to_primary_and_keeps_slug_redirect(tmp_path: Path) -> None:
    primary = "skv-p000273"
    secondary = "skv-p000274"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Said Abdullahi", "profile_slug": "said-abdullahi"},
            {"person_id": secondary, "display_name": "Said Garaashe Abdullahi", "profile_slug": "said-garaashe-abdullahi"},
        ],
    )
    write_basic_slug_history(
        tmp_path,
        [
            {"person_id": primary, "profile_slug": "said-abdullahi", "active_from": "2026-01-01", "active_to": "", "reason": "initial"},
            {
                "person_id": secondary,
                "profile_slug": "said-garaashe-abdullahi",
                "active_from": "2026-01-01",
                "active_to": "",
                "reason": "initial",
            },
        ],
    )
    write_csv(
        tmp_path / "person_external_ids.csv",
        [{"person_id": secondary, "source": "source", "external_id": "abc", "active": "true", "notes": ""}],
        ["person_id", "source", "external_id", "active", "notes"],
    )
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "notes": "same runner",
                "reviewed_at": "2026-04-28T10:00:00+02:00",
                "applied_at": "",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    result = apply_match_decisions(tmp_path, now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"))
    identity = load_identity_data(tmp_path)
    registry = identity.registry.set_index("person_id")
    aliases = identity.aliases[identity.aliases["person_id"].eq(primary)]
    external_ids = identity.external_ids[identity.external_ids["person_id"].eq(primary)]
    indexes = build_identity_indexes(identity)

    assert result["applied_counts"]["merge"] == 1
    assert registry.loc[secondary, "status"] == "merged"
    assert registry.loc[secondary, "merged_into_person_id"] == primary
    assert normalize_name("Said Garaashe Abdullahi") in set(aliases["normalized_alias"])
    assert (external_ids["external_id"] == "abc").any()
    assert match_result_to_person({"athlete_name": "Said Garaashe Abdullahi"}, identity, indexes).person_id == primary

    df = pd.DataFrame(
        [
            {
                "person_id": primary,
                "athlete_name": "Said Abdullahi",
                "distance": "10 km",
                "result_time_seconds": 1800,
                "result_time_normalized": "30:00",
                "event_label": "Test",
                "published_date": "2026-04-28",
                "published_date_label": "28.04.2026",
                "published_date_sort": pd.Timestamp("2026-04-28"),
                "week_number": 18,
                "place": "",
                "class_place": "",
            }
        ]
    )
    people_payload = build_people_payload(df, identity)
    assert people_payload["slug_map"]["said-garaashe-abdullahi"] == primary
    assert people_payload["slug_redirects"]["said-garaashe-abdullahi"] == "said-abdullahi"


def test_alias_only_decision_matches_future_results_without_merging(tmp_path: Path) -> None:
    primary = "skv-p000010"
    secondary = "skv-p000011"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Kristina Marcelius Stang", "profile_slug": "kristina-marcelius-stang"},
            {"person_id": secondary, "display_name": "Kristina M. Stang", "profile_slug": "kristina-m-stang"},
        ],
    )
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "alias_only",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "notes": "future abbreviation",
                "reviewed_at": "2026-04-28T10:00:00+02:00",
                "applied_at": "",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    apply_match_decisions(tmp_path, now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"))
    identity = load_identity_data(tmp_path)
    registry = identity.registry.set_index("person_id")
    match = match_result_to_person({"athlete_name": "Kristina M. Stang"}, identity)

    assert registry.loc[secondary, "status"] == "active"
    assert match.person_id == primary
    assert match.method == "alias"


def test_reject_decision_suppresses_false_positive_candidate(tmp_path: Path) -> None:
    left = "skv-p000132"
    right = "skv-p000280"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": left, "display_name": "Ingrid Skomedal Klovning", "profile_slug": "ingrid-skomedal-klovning"},
            {"person_id": right, "display_name": "Sigurd Skomedal Klovning", "profile_slug": "sigurd-skomedal-klovning"},
        ],
    )
    identity = load_identity_data(tmp_path)
    assert not build_person_match_candidates(identity).empty

    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(left, right),
                "decision": "reject",
                "primary_person_id": left,
                "secondary_person_id": right,
                "notes": "siblings, not same person",
                "reviewed_at": "2026-04-28T10:00:00+02:00",
                "applied_at": "",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )
    identity = load_identity_data(tmp_path)

    assert build_person_match_candidates(identity).empty


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
