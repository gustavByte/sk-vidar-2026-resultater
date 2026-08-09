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
    apply_match_decisions_to_identity,
    build_identity_reports,
    build_identity_indexes,
    build_people_payload,
    build_person_match_candidates,
    candidate_id_for_people,
    ensure_identity_files_from_seed,
    ensure_new_people_are_appended_without_changing_existing_ids,
    find_identity_graph_errors,
    find_blocking_person_match_candidates,
    load_identity_data,
    match_result_to_person,
    normalize_name,
    normalize_source_system,
    persist_identity_data,
    slugify_person_name,
    validate_public_payload,
    write_canonical_identity_seed,
)
from project_paths import CANONICAL_PERSON_IDENTITY_DIR, WEEKLY_RESULTS_FILE  # noqa: E402
import person_identity as person_identity_module  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8")


def test_identity_csv_bundle_is_unchanged_when_staging_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Old Runner", "profile_slug": "old-runner"}],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000001",
                "alias": "Old Runner",
                "normalized_alias": normalize_name("Old Runner"),
                "source": "test",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )
    before_registry = (tmp_path / "person_registry.csv").read_bytes()
    before_aliases = (tmp_path / "person_aliases.csv").read_bytes()
    identity = load_identity_data(tmp_path)
    identity.registry.loc[0, "display_name"] = "New Runner"
    identity.registry.loc[0, "normalized_name"] = normalize_name("New Runner")
    identity.aliases.loc[0, "alias"] = "New Runner"
    identity.aliases.loc[0, "normalized_alias"] = normalize_name("New Runner")

    real_write_csv = person_identity_module._write_csv
    call_count = 0

    def fail_on_second_staged_write(frame: pd.DataFrame, path: Path, columns: list[str]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("simulated staged write failure")
        real_write_csv(frame, path, columns)

    monkeypatch.setattr(person_identity_module, "_write_csv", fail_on_second_staged_write)

    with pytest.raises(OSError, match="simulated staged write failure"):
        persist_identity_data(identity, tmp_path)

    assert (tmp_path / "person_registry.csv").read_bytes() == before_registry
    assert (tmp_path / "person_aliases.csv").read_bytes() == before_aliases


def test_private_and_canonical_identity_bundles_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_dir = tmp_path / "private"
    seed_dir = tmp_path / "seed"
    person = {"person_id": "skv-p000001", "display_name": "Old Runner", "profile_slug": "old-runner"}
    write_basic_registry(private_dir, [person])
    write_basic_registry(seed_dir, [person])
    before_private_files = {path.name: path.read_bytes() for path in private_dir.iterdir() if path.is_file()}
    before_seed_files = {path.name: path.read_bytes() for path in seed_dir.iterdir() if path.is_file()}
    identity = load_identity_data(private_dir)
    identity.registry.loc[0, "display_name"] = "New Runner"
    identity.registry.loc[0, "normalized_name"] = normalize_name("New Runner")

    real_replace = person_identity_module.os.replace
    failed = False
    seed_registry = (seed_dir / "person_registry.csv").resolve()

    def fail_on_first_canonical_commit(source: object, destination: object) -> None:
        nonlocal failed
        if not failed and Path(destination).resolve() == seed_registry:
            failed = True
            raise OSError("simulated canonical commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(person_identity_module.os, "replace", fail_on_first_canonical_commit)

    with pytest.raises(OSError, match="simulated canonical commit failure"):
        persist_identity_data(identity, private_dir, canonical_seed_dir=seed_dir)

    after_private_files = {path.name: path.read_bytes() for path in private_dir.iterdir() if path.is_file()}
    after_seed_files = {path.name: path.read_bytes() for path in seed_dir.iterdir() if path.is_file()}
    assert after_private_files == before_private_files
    assert after_seed_files == before_seed_files
    assert not list(private_dir.glob(".*.tmp"))
    assert not list(private_dir.glob(".*.bak"))
    assert not list(seed_dir.glob(".*.tmp"))
    assert not list(seed_dir.glob(".*.bak"))


def test_public_output_commit_failure_rolls_back_identity_and_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_dir = tmp_path / "private"
    seed_dir = tmp_path / "seed"
    public_file = tmp_path / "public" / "results.json"
    person = {"person_id": "skv-p000001", "display_name": "Old Runner", "profile_slug": "old-runner"}
    write_basic_registry(private_dir, [person])
    write_basic_registry(seed_dir, [person])
    public_file.parent.mkdir(parents=True)
    public_file.write_text('{"version":"old"}', encoding="utf-8")
    before_private = {path.name: path.read_bytes() for path in private_dir.iterdir() if path.is_file()}
    before_seed = {path.name: path.read_bytes() for path in seed_dir.iterdir() if path.is_file()}
    before_public = public_file.read_bytes()
    identity = load_identity_data(private_dir)
    identity.registry.loc[0, "display_name"] = "New Runner"
    identity.registry.loc[0, "normalized_name"] = normalize_name("New Runner")

    real_replace = person_identity_module.os.replace
    failed = False
    resolved_public_file = public_file.resolve()

    def fail_on_public_commit(source: object, destination: object) -> None:
        nonlocal failed
        if not failed and Path(destination).resolve() == resolved_public_file:
            failed = True
            raise OSError("simulated public output commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(person_identity_module.os, "replace", fail_on_public_commit)

    with pytest.raises(OSError, match="simulated public output commit failure"):
        persist_identity_data(
            identity,
            private_dir,
            canonical_seed_dir=seed_dir,
            additional_file_writes=[
                (public_file, lambda staged_path: staged_path.write_text('{"version":"new"}', encoding="utf-8"))
            ],
        )

    assert {path.name: path.read_bytes() for path in private_dir.iterdir() if path.is_file()} == before_private
    assert {path.name: path.read_bytes() for path in seed_dir.iterdir() if path.is_file()} == before_seed
    assert public_file.read_bytes() == before_public
    assert not list(tmp_path.rglob(".*.tmp"))
    assert not list(tmp_path.rglob(".*.bak"))


def test_failed_backup_restore_is_reported_and_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_file = tmp_path / "first.txt"
    second_file = tmp_path / "second.txt"
    first_file.write_text("old-first", encoding="utf-8")
    second_file.write_text("old-second", encoding="utf-8")
    real_replace = person_identity_module.os.replace

    def fail_commit_then_restore(source: object, destination: object) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == second_file and source_path.suffix == ".tmp":
            raise OSError("simulated second commit failure")
        if destination_path == first_file and source_path.suffix == ".bak":
            raise OSError("simulated backup restore failure")
        real_replace(source, destination)

    monkeypatch.setattr(person_identity_module.os, "replace", fail_commit_then_restore)

    with pytest.raises(RuntimeError, match="rollback incomplete.*Retained backups"):
        person_identity_module._write_files_atomically(
            [
                (first_file, lambda staged_path: staged_path.write_text("new-first", encoding="utf-8")),
                (second_file, lambda staged_path: staged_path.write_text("new-second", encoding="utf-8")),
            ]
        )

    assert first_file.read_text(encoding="utf-8") == "new-first"
    assert second_file.read_text(encoding="utf-8") == "old-second"
    retained_backups = list(tmp_path.glob(".first.txt.*.bak"))
    assert len(retained_backups) == 1
    assert retained_backups[0].read_text(encoding="utf-8") == "old-first"
    assert not list(tmp_path.glob(".second.txt.*.bak"))
    assert not list(tmp_path.glob(".*.tmp"))


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


def test_blank_normalized_aliases_are_normalized_before_conflict_checks(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "Runner One", "profile_slug": "runner-one"},
            {"person_id": "skv-p000002", "display_name": "Runner Two", "profile_slug": "runner-two"},
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000001",
                "alias": "Shared Alias",
                "normalized_alias": "",
                "source": "test",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": "skv-p000002",
                "alias": "Shared Alias",
                "normalized_alias": "",
                "source": "test",
                "active": "true",
                "notes": "",
            },
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )
    identity = load_identity_data(tmp_path)

    match = match_result_to_person({"athlete_name": "Shared Alias"}, identity)
    reports = build_identity_reports(pd.DataFrame(), identity)

    assert match.method == "ambiguous_alias"
    assert len(reports["alias_conflicts"]) == 1
    assert len(reports["name_key_conflicts"]) == 1
    with pytest.raises(ValueError, match="alias_conflicts"):
        persist_identity_data(identity, tmp_path)


def test_stale_normalized_alias_is_recomputed_from_alias_text(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Runner One", "profile_slug": "runner-one"}],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000001",
                "alias": "Correct Alias",
                "normalized_alias": "stale wrong key",
                "source": "test",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )
    identity = load_identity_data(tmp_path)

    assert match_result_to_person({"athlete_name": "Correct Alias"}, identity).person_id == "skv-p000001"
    assert match_result_to_person({"athlete_name": "Stale Wrong Key"}, identity).person_id == ""

    persist_identity_data(identity, tmp_path)
    stored_alias = load_identity_data(tmp_path).aliases.iloc[0]
    assert stored_alias["normalized_alias"] == normalize_name("Correct Alias")


def test_historical_slug_cannot_belong_to_another_active_profile(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "John Smith", "profile_slug": "john-smith"},
            {"person_id": "skv-p000002", "display_name": "John Smith Jr", "profile_slug": "john-smith-jr"},
        ],
    )
    write_basic_slug_history(
        tmp_path,
        [
            {
                "person_id": "skv-p000002",
                "profile_slug": "john-smith",
                "active_from": "2025-01-01",
                "active_to": "2025-12-31",
                "reason": "old profile slug",
            }
        ],
    )
    identity = load_identity_data(tmp_path)
    reports = build_identity_reports(pd.DataFrame(), identity)

    assert len(reports["resolved_slug_owner_conflicts"]) == 1
    with pytest.raises(ValueError, match="resolved_slug_owner_conflicts"):
        persist_identity_data(identity, tmp_path)


def test_external_id_and_name_owner_conflict_fails_closed(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "Runner One", "profile_slug": "runner-one"},
            {"person_id": "skv-p000002", "display_name": "Runner Two", "profile_slug": "runner-two"},
        ],
    )
    write_csv(
        tmp_path / "person_external_ids.csv",
        [{"person_id": "skv-p000001", "source": "slack", "external_id": "U123", "active": "true", "notes": ""}],
        ["person_id", "source", "external_id", "active", "notes"],
    )
    identity = load_identity_data(tmp_path)

    match = match_result_to_person({"athlete_name": "Runner Two", "slack_user_id": "U123"}, identity)

    assert match.person_id == ""
    assert match.method == "conflicting_identity_signals"
    assert match.needs_review


def test_result_source_person_ids_are_scoped_by_provider(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "Runner One", "profile_slug": "runner-one"},
            {"person_id": "skv-p000002", "display_name": "Runner Two", "profile_slug": "runner-two"},
        ],
    )
    write_csv(
        tmp_path / "person_external_ids.csv",
        [
            {
                "person_id": "skv-p000001",
                "source": "result_source:eq-timing",
                "external_id": "123",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": "skv-p000002",
                "source": "result_source:racedays",
                "external_id": "123",
                "active": "true",
                "notes": "",
            },
        ],
        ["person_id", "source", "external_id", "active", "notes"],
    )
    identity = load_identity_data(tmp_path)

    eq_match = match_result_to_person(
        {"athlete_name": "Runner One", "source_system": "EQ Timing", "source_person_id": "123"},
        identity,
    )
    race_match = match_result_to_person(
        {"athlete_name": "Runner Two", "source_system": "RaceDays", "source_person_id": "123"},
        identity,
    )

    assert normalize_source_system("  EQ Timing ") == "eq-timing"
    assert eq_match.person_id == "skv-p000001"
    assert race_match.person_id == "skv-p000002"


def test_new_singleton_external_id_cannot_attach_by_name_when_person_has_another_id(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Kari Runner", "profile_slug": "kari-runner"}],
    )
    external_columns = ["person_id", "source", "external_id", "active", "notes"]
    write_csv(
        tmp_path / "person_external_ids.csv",
        [{"person_id": "skv-p000001", "source": "slack", "external_id": "U1", "active": "true", "notes": ""}],
        external_columns,
    )
    row = {"result_id": "res-1", "athlete_name": "Kari Runner", "slack_user_id": "U2"}

    match = match_result_to_person(row, load_identity_data(tmp_path))
    identity = ensure_new_people_are_appended_without_changing_existing_ids(pd.DataFrame([row]), tmp_path)

    assert match.person_id == ""
    assert match.method == "conflicting_external_id_cardinality"
    assert match.needs_review
    assert set(identity.external_ids["external_id"]) == {"U1"}

    write_csv(
        tmp_path / "person_external_ids.csv",
        [
            {"person_id": "skv-p000001", "source": "slack", "external_id": "U1", "active": "true", "notes": ""},
            {"person_id": "skv-p000001", "source": "slack", "external_id": "U2", "active": "true", "notes": ""},
        ],
        external_columns,
    )
    conflict_report = build_identity_reports(pd.DataFrame(), load_identity_data(tmp_path))[
        "external_source_cardinality_conflicts"
    ]
    assert len(conflict_report) == 1


def test_two_new_same_name_rows_with_different_slack_ids_fail_closed(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )
    rows = pd.DataFrame(
        [
            {"result_id": "res-1", "athlete_name": "New Same Name", "slack_user_id": "U1"},
            {"result_id": "res-2", "athlete_name": "New Same Name", "slack_user_id": "U2"},
        ]
    )

    with pytest.raises(ValueError, match="conflicting external IDs"):
        ensure_new_people_are_appended_without_changing_existing_ids(rows, tmp_path, persist=False)


def test_draft_retry_rejects_a_different_singleton_external_id(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )
    first = pd.DataFrame(
        [{"result_id": "res-1", "athlete_name": "New Same Name", "slack_user_id": "U1"}]
    )
    second = pd.DataFrame(
        [{"result_id": "res-2", "athlete_name": "New Same Name", "slack_user_id": "U2"}]
    )

    ensure_new_people_are_appended_without_changing_existing_ids(first, tmp_path, persist=False)

    with pytest.raises(ValueError, match="conflicting slack IDs"):
        ensure_new_people_are_appended_without_changing_existing_ids(second, tmp_path, persist=False)


def test_draft_person_id_collision_with_unrelated_registry_profile_fails_closed(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )
    new_runner = pd.DataFrame([{"result_id": "res-1", "athlete_name": "New Runner"}])
    staged = ensure_new_people_are_appended_without_changing_existing_ids(
        new_runner,
        tmp_path,
        persist=False,
    )
    reserved_person_id = staged.registry.set_index("display_name").loc["New Runner", "person_id"]

    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"},
            {"person_id": reserved_person_id, "display_name": "Unrelated Runner", "profile_slug": "unrelated-runner"},
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": reserved_person_id,
                "alias": "New Runner",
                "normalized_alias": normalize_name("New Runner"),
                "source": "retired_wrong_alias",
                "active": "false",
                "notes": "must not prove draft ownership",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )

    with pytest.raises(ValueError, match="Draft person_id collision"):
        ensure_new_people_are_appended_without_changing_existing_ids(new_runner, tmp_path, persist=False)


def test_same_name_registry_row_cannot_claim_a_draft_staged_by_another_build(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )
    same_name = pd.DataFrame([{"result_id": "res-1", "athlete_name": "Common Name"}])
    staged = ensure_new_people_are_appended_without_changing_existing_ids(same_name, tmp_path, persist=False)
    reserved_person_id = staged.registry.set_index("display_name").loc["Common Name", "person_id"]

    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"},
            {"person_id": reserved_person_id, "display_name": "Common Name", "profile_slug": "common-name-other"},
        ],
    )
    write_csv(
        tmp_path / "person_external_ids.csv",
        [
            {
                "person_id": reserved_person_id,
                "source": "slack",
                "external_id": "U-UNRELATED",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "source", "external_id", "active", "notes"],
    )

    with pytest.raises(ValueError, match="was not staged by this build"):
        ensure_new_people_are_appended_without_changing_existing_ids(same_name, tmp_path, persist=False)


def test_unscoped_source_person_id_fails_closed_and_creates_no_person(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )
    row = {"result_id": "res-1", "athlete_name": "New Runner", "source_person_id": "123"}

    match = match_result_to_person(row, load_identity_data(tmp_path))
    identity = ensure_new_people_are_appended_without_changing_existing_ids(pd.DataFrame([row]), tmp_path)

    assert match.person_id == ""
    assert match.method == "unscoped_source_person_id"
    assert match.needs_review
    assert identity.registry["person_id"].tolist() == ["skv-p000001"]


def test_provisional_new_person_is_not_persisted_before_publication_gate_passes(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Existing", "profile_slug": "existing"}],
    )

    staged = ensure_new_people_are_appended_without_changing_existing_ids(
        pd.DataFrame([{"result_id": "res-1", "athlete_name": "New Runner"}]),
        tmp_path,
        persist=False,
    )
    stored = load_identity_data(tmp_path)

    assert "New Runner" in set(staged.registry["display_name"])
    assert "New Runner" not in set(stored.registry["display_name"])


def test_provisional_duplicate_can_be_resolved_atomically_on_next_build(tmp_path: Path) -> None:
    primary = "skv-p000001"
    write_basic_registry(
        tmp_path,
        [{"person_id": primary, "display_name": "Alva Witnes Ertresvåg", "profile_slug": "alva-witnes-ertresvag"}],
    )
    results = pd.DataFrame([{"result_id": "res-1", "athlete_name": "Alva Ertresvåg"}])
    first_stage = ensure_new_people_are_appended_without_changing_existing_ids(results, tmp_path, persist=False)
    candidates = build_person_match_candidates(first_stage, results)
    candidate = candidates.iloc[0]
    secondary = candidate["person_id_2"] if candidate["person_id_1"] == primary else candidate["person_id_1"]
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate["candidate_id"],
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "preferred_display_name": "Alva Witnes Ertresvåg",
                "reviewed_at": "2026-08-04T12:00:00+02:00",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    reordered_results = pd.DataFrame(
        [
            {"result_id": "res-0", "athlete_name": "Aaron New Runner"},
            {"result_id": "res-1", "athlete_name": "Alva Ertresvåg"},
        ]
    )
    second_stage = ensure_new_people_are_appended_without_changing_existing_ids(
        reordered_results,
        tmp_path,
        persist=False,
    )
    resolved, decision_result = apply_match_decisions_to_identity(second_stage)
    match = match_result_to_person(reordered_results.iloc[1], resolved)
    blocking = find_blocking_person_match_candidates(build_person_match_candidates(resolved, reordered_results))

    assert decision_result["error_count"] == 0
    assert decision_result["applied_counts"]["merge"] == 1
    assert match.person_id == primary
    assert resolved.registry.set_index("person_id").loc[secondary, "status"] == "merged"
    assert secondary not in set(load_identity_data(tmp_path).registry["person_id"])
    assert blocking.empty

    persist_identity_data(resolved, tmp_path)
    stored = load_identity_data(tmp_path)
    assert stored.registry.set_index("person_id").loc[secondary, "status"] == "merged"
    assert pd.read_csv(tmp_path / "person_drafts.csv").empty


def test_deferred_provisional_person_must_still_exist_on_retry(tmp_path: Path) -> None:
    primary = "skv-p000001"
    write_basic_registry(
        tmp_path,
        [{"person_id": primary, "display_name": "Alva Full", "profile_slug": "alva-full"}],
    )
    provisional_results = pd.DataFrame(
        [{"result_id": "res-1", "athlete_name": "Alva Middle Full"}]
    )
    first_stage = ensure_new_people_are_appended_without_changing_existing_ids(
        provisional_results,
        tmp_path,
        persist=False,
    )
    secondary = first_stage.registry.set_index("display_name").loc["Alva Middle Full", "person_id"]
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "defer",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    retry_stage = ensure_new_people_are_appended_without_changing_existing_ids(
        pd.DataFrame(columns=["result_id", "athlete_name"]),
        tmp_path,
        persist=False,
    )
    _, result = apply_match_decisions_to_identity(retry_stage)

    assert result["error_count"] == 1
    assert "secondary_person_id does not exist" in result["errors"][0]["error"]
    with pytest.raises(ValueError, match="secondary_person_id is missing from registry"):
        persist_identity_data(retry_stage, tmp_path)


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


def test_result_override_does_not_promote_source_name_to_global_alias(tmp_path: Path) -> None:
    henrik_hansen_id = "skv-p900001"
    henrik_victor_id = "skv-p900002"
    write_basic_registry(
        tmp_path,
        [
            {
                "person_id": henrik_hansen_id,
                "display_name": "Henrik Hansen",
                "profile_slug": "henrik-hansen",
            },
            {
                "person_id": henrik_victor_id,
                "display_name": "Henrik Victor Hansen",
                "profile_slug": "henrik-victor-hansen",
            },
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": henrik_hansen_id,
                "alias": "Henrik Hansen",
                "normalized_alias": normalize_name("Henrik Hansen"),
                "source": "test",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": henrik_victor_id,
                "alias": "Henrik Victor Hansen",
                "normalized_alias": normalize_name("Henrik Victor Hansen"),
                "source": "test",
                "active": "true",
                "notes": "",
            },
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )
    write_csv(
        tmp_path / "result_person_overrides.csv",
        [
            {
                "result_id": "res-moseby",
                "person_id": henrik_victor_id,
                "active": "true",
                "reason": "user_confirmed_identity",
                "notes": "",
            }
        ],
        ["result_id", "person_id", "active", "reason", "notes"],
    )
    results = pd.DataFrame(
        [
            {"result_id": "res-moseby", "athlete_name": "Henrik Hansen"},
            {"result_id": "res-drammen", "athlete_name": "Henrik Hansen"},
        ]
    )

    identity = ensure_new_people_are_appended_without_changing_existing_ids(
        results,
        tmp_path,
        persist=False,
    )
    indexes = build_identity_indexes(identity)
    matches = {
        row["result_id"]: match_result_to_person(row, identity, indexes)
        for _, row in results.iterrows()
    }

    assert matches["res-moseby"].person_id == henrik_victor_id
    assert matches["res-moseby"].method == "result_override"
    assert matches["res-drammen"].person_id == henrik_hansen_id
    henrik_aliases = identity.aliases[
        identity.aliases["normalized_alias"].eq(normalize_name("Henrik Hansen"))
    ]
    assert set(henrik_aliases["person_id"]) == {henrik_hansen_id}
    assert build_identity_reports(pd.DataFrame(), identity)["alias_conflicts"].empty


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


def test_empty_private_store_is_seeded_with_stable_merged_identities(tmp_path: Path) -> None:
    seed_dir = tmp_path / "canonical-seed"
    private_dir = tmp_path / "private-store"
    write_basic_registry(
        seed_dir,
        [
            {"person_id": "skv-p000202", "display_name": "Maria Bipop", "profile_slug": "maria-bipop"},
            {
                "person_id": "skv-p000203",
                "display_name": "Maria Bipop Bang Jensen",
                "profile_slug": "maria-bipop-bang-jensen",
                "status": "merged",
                "merged_into_person_id": "skv-p000202",
            },
            {
                "person_id": "skv-p000205",
                "display_name": "Marianne Harnes",
                "profile_slug": "marianne-harnes",
                "status": "merged",
                "merged_into_person_id": "skv-p000206",
            },
            {
                "person_id": "skv-p000206",
                "display_name": "Marianne Harnes Myhrer",
                "profile_slug": "marianne-harnes-myhrer",
            },
        ],
    )
    write_csv(
        seed_dir / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000202",
                "alias": "Maria Bipop",
                "normalized_alias": normalize_name("Maria Bipop"),
                "source": "canonical_seed",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": "skv-p000203",
                "alias": "Maria Bipop Bang Jensen",
                "normalized_alias": normalize_name("Maria Bipop Bang Jensen"),
                "source": "canonical_seed",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": "skv-p000205",
                "alias": "Marianne Harnes",
                "normalized_alias": normalize_name("Marianne Harnes"),
                "source": "canonical_seed",
                "active": "true",
                "notes": "",
            },
            {
                "person_id": "skv-p000206",
                "alias": "Marianne Harnes Myhrer",
                "normalized_alias": normalize_name("Marianne Harnes Myhrer"),
                "source": "canonical_seed",
                "active": "true",
                "notes": "",
            },
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )

    results = pd.DataFrame(
        [
            {"result_id": "res-maria-short", "athlete_name": "Maria Bipop"},
            {"result_id": "res-maria-full", "athlete_name": "Maria Bipop Bang Jensen"},
            {"result_id": "res-marianne-short", "athlete_name": "Marianne Harnes"},
            {"result_id": "res-marianne-full", "athlete_name": "Marianne Harnes Myhrer"},
        ]
    )
    identity = ensure_new_people_are_appended_without_changing_existing_ids(
        results,
        private_dir,
        now=datetime.fromisoformat("2026-08-03T18:00:00+02:00"),
        canonical_seed_dir=seed_dir,
    )
    indexes = build_identity_indexes(identity)

    matches = {
        row["athlete_name"]: match_result_to_person(row, identity, indexes).person_id
        for _, row in results.iterrows()
    }
    assert matches["Maria Bipop"] == matches["Maria Bipop Bang Jensen"] == "skv-p000202"
    assert matches["Marianne Harnes"] == matches["Marianne Harnes Myhrer"] == "skv-p000206"
    assert int((identity.registry["status"].str.casefold() != "merged").sum()) == 2


def test_empty_private_store_fails_closed_without_canonical_seed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="canonical identity seed"):
        ensure_new_people_are_appended_without_changing_existing_ids(
            pd.DataFrame([{"result_id": "res-1", "athlete_name": "Runner"}]),
            tmp_path / "private-store",
            canonical_seed_dir=tmp_path / "missing-seed",
        )


def test_nonempty_stale_private_store_reconciles_canonical_merge(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    seed_dir = tmp_path / "seed"
    rows = [
        {"person_id": "skv-p000001", "display_name": "Alva Witnes Ertresvåg", "profile_slug": "alva-witnes-ertresvag"},
        {"person_id": "skv-p000002", "display_name": "Alva Ertresvåg", "profile_slug": "alva-ertresvag"},
    ]
    write_basic_registry(private_dir, rows)
    write_basic_registry(
        seed_dir,
        [
            rows[0],
            {
                **rows[1],
                "status": "merged",
                "merged_into_person_id": "skv-p000001",
            },
            {"person_id": "skv-p000003", "display_name": "New Seed Runner", "profile_slug": "new-seed-runner"},
        ],
    )
    write_csv(
        seed_dir / "person_aliases.csv",
        [
            {
                "person_id": "skv-p000001",
                "alias": "Alva Ertresvåg",
                "normalized_alias": normalize_name("Alva Ertresvåg"),
                "source": "canonical_merge",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )

    ensure_identity_files_from_seed(private_dir, seed_dir)
    identity = load_identity_data(private_dir)
    registry = identity.registry.set_index("person_id")

    assert registry.loc["skv-p000002", "status"] == "merged"
    assert registry.loc["skv-p000002", "merged_into_person_id"] == "skv-p000001"
    assert "skv-p000003" in registry.index
    assert match_result_to_person({"athlete_name": "Alva Ertresvåg"}, identity).person_id == "skv-p000001"


def test_seed_reconciliation_propagates_profile_alias_and_newer_decision_corrections(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    seed_dir = tmp_path / "seed"
    people = [
        {"person_id": "skv-p000001", "display_name": "Old Name", "profile_slug": "old-name"},
        {"person_id": "skv-p000002", "display_name": "Other Runner", "profile_slug": "other-runner"},
    ]
    write_basic_registry(private_dir, people)
    write_basic_registry(
        seed_dir,
        [
            {"person_id": "skv-p000001", "display_name": "Correct Name", "profile_slug": "correct-name"},
            people[1],
        ],
    )
    alias_columns = ["person_id", "alias", "normalized_alias", "source", "active", "notes"]
    alias_row = {
        "person_id": "skv-p000001",
        "alias": "Old Name",
        "normalized_alias": normalize_name("Old Name"),
        "source": "manual",
        "active": "true",
        "notes": "private note",
    }
    write_csv(private_dir / "person_aliases.csv", [alias_row], alias_columns)
    write_csv(seed_dir / "person_aliases.csv", [{**alias_row, "active": "false", "notes": ""}], alias_columns)

    candidate_id = candidate_id_for_people("skv-p000001", "skv-p000002")
    local_decision = {
        "candidate_id": candidate_id,
        "decision": "defer",
        "primary_person_id": "skv-p000001",
        "secondary_person_id": "skv-p000002",
        "preferred_display_name": "",
        "notes": "private decision note",
        "reviewed_at": "2026-03-01T12:00:00+01:00",
        "applied_at": "",
    }
    seed_decision = {
        **local_decision,
        "decision": "reject",
        "notes": "",
        "reviewed_at": "2026-02-01T12:00:00+01:00",
        "applied_at": "2026-02-01T12:01:00+01:00",
    }
    write_csv(private_dir / "person_match_decisions.csv", [local_decision], MATCH_DECISION_COLUMNS)
    write_csv(seed_dir / "person_match_decisions.csv", [seed_decision], MATCH_DECISION_COLUMNS)
    override_columns = ["result_id", "person_id", "active", "reason", "notes"]
    local_override = {
        "result_id": "res-1",
        "person_id": "skv-p000001",
        "active": "true",
        "reason": "private correction reason",
        "notes": "private override note",
    }
    write_csv(private_dir / "result_person_overrides.csv", [local_override], override_columns)
    write_csv(
        seed_dir / "result_person_overrides.csv",
        [{**local_override, "reason": "", "notes": ""}],
        override_columns,
    )

    ensure_identity_files_from_seed(private_dir, seed_dir)
    identity = load_identity_data(private_dir)

    registry = identity.registry.set_index("person_id")
    assert registry.loc["skv-p000001", "display_name"] == "Correct Name"
    assert registry.loc["skv-p000001", "profile_slug"] == "correct-name"
    assert identity.aliases.iloc[0]["active"] == "false"
    assert identity.aliases.iloc[0]["notes"] == "private note"
    assert identity.match_decisions.iloc[0]["decision"] == "reject"
    assert identity.match_decisions.iloc[0]["notes"] == "private decision note"
    assert identity.result_overrides.iloc[0]["reason"] == "private correction reason"
    assert identity.result_overrides.iloc[0]["notes"] == "private override note"


def test_repository_identity_seed_contains_known_alias_merges() -> None:
    identity = load_identity_data(CANONICAL_PERSON_IDENTITY_DIR)
    indexes = build_identity_indexes(identity)

    assert match_result_to_person({"athlete_name": "Maria Bipop"}, identity, indexes).person_id == "skv-p000202"
    assert match_result_to_person({"athlete_name": "Maria Bipop Bang Jensen"}, identity, indexes).person_id == "skv-p000202"
    assert match_result_to_person({"athlete_name": "Marianne Harnes"}, identity, indexes).person_id == "skv-p000206"
    assert match_result_to_person({"athlete_name": "Marianne Harnes Myhrer"}, identity, indexes).person_id == "skv-p000206"
    assert match_result_to_person({"athlete_name": "Liv Richter Melby"}, identity, indexes).person_id == "skv-p000190"


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
            {"person_id": "skv-p000274", "published_date": "2026-03-01"},
        ]
    )

    candidates = build_person_match_candidates(identity, results)

    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["candidate_id"] == candidate_id_for_people("skv-p000273", "skv-p000274")
    assert candidate["confidence"] == "strong"
    assert candidate["suggested_decision"] == "merge"
    assert candidate["suggested_primary_person_id"] == "skv-p000273"


def test_unreviewed_person_match_candidates_block_publication_until_resolved() -> None:
    rows = [
        {
            "candidate_id": "pmc-new",
            "display_name_1": "Alva Witnes Ertresvåg",
            "display_name_2": "Alva Ertresvåg",
            "decision": "",
        },
        {
            "candidate_id": "pmc-approved-not-applied",
            "display_name_1": "Kari Renslo",
            "display_name_2": "Kari Renslo Instefjord",
            "decision": "merge",
        },
        {
            "candidate_id": "pmc-deferred",
            "display_name_1": "Henrik Hansen",
            "display_name_2": "Henrik Victor Hansen",
            "decision": "defer",
        },
        {
            "candidate_id": "pmc-rejected",
            "display_name_1": "Different Runner",
            "display_name_2": "Different Runnersen",
            "decision": "reject",
        },
    ]

    blocking = find_blocking_person_match_candidates(pd.DataFrame(rows))

    assert blocking["candidate_id"].tolist() == ["pmc-new", "pmc-approved-not-applied"]


def test_repository_identity_seed_recognizes_both_alva_name_variants() -> None:
    identity = load_identity_data(CANONICAL_PERSON_IDENTITY_DIR)
    indexes = build_identity_indexes(identity)

    full_name = match_result_to_person({"athlete_name": "Alva Witnes Ertresvåg"}, identity, indexes)
    short_name = match_result_to_person({"athlete_name": "Alva Ertresvåg"}, identity, indexes)

    assert full_name.person_id == short_name.person_id == "skv-p000011"


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


def test_merge_does_not_reactivate_inactive_secondary_aliases(tmp_path: Path) -> None:
    primary = "skv-p000001"
    secondary = "skv-p000002"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Runner Full", "profile_slug": "runner-full"},
            {"person_id": secondary, "display_name": "Runner", "profile_slug": "runner"},
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": secondary,
                "alias": "Retired Wrong Alias",
                "normalized_alias": normalize_name("Retired Wrong Alias"),
                "source": "manual",
                "active": "false",
                "notes": "must remain inactive",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    result = apply_match_decisions(tmp_path)
    identity = load_identity_data(tmp_path)
    copied = identity.aliases[
        identity.aliases["person_id"].eq(primary)
        & identity.aliases["normalized_alias"].eq(normalize_name("Retired Wrong Alias"))
    ]

    assert result["error_count"] == 0
    assert copied.empty
    assert match_result_to_person({"athlete_name": "Retired Wrong Alias"}, identity).person_id == ""


def test_preferred_display_name_cannot_take_a_third_active_persons_name(tmp_path: Path) -> None:
    primary = "skv-p000001"
    secondary = "skv-p000002"
    third = "skv-p000003"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Runner Full", "profile_slug": "runner-full"},
            {"person_id": secondary, "display_name": "Runner", "profile_slug": "runner"},
            {"person_id": third, "display_name": "Third Runner", "profile_slug": "third-runner"},
        ],
    )
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "preferred_display_name": "Third Runner",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    with pytest.raises(ValueError, match="name_key_conflicts|duplicate_normalized_names"):
        apply_match_decisions(tmp_path)

    stored = load_identity_data(tmp_path).registry.set_index("person_id")
    assert stored.loc[secondary, "status"] == "active"
    assert stored.loc[primary, "display_name"] == "Runner Full"


def test_pending_decision_candidate_id_must_match_exact_person_pair_transactionally(tmp_path: Path) -> None:
    people = [
        {"person_id": "skv-p000001", "display_name": "One", "profile_slug": "one"},
        {"person_id": "skv-p000002", "display_name": "Two", "profile_slug": "two"},
        {"person_id": "skv-p000003", "display_name": "Three", "profile_slug": "three"},
    ]
    write_basic_registry(tmp_path, people)
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people("skv-p000001", "skv-p000002"),
                "decision": "merge",
                "primary_person_id": "skv-p000001",
                "secondary_person_id": "skv-p000003",
                "reviewed_at": "2026-04-28T10:00:00+02:00",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    result = apply_match_decisions(tmp_path, now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"))
    registry = load_identity_data(tmp_path).registry.set_index("person_id")

    assert result["error_count"] == 1
    assert "does not match person pair" in result["errors"][0]["error"]
    assert registry.loc["skv-p000003", "status"] == "active"


def test_applied_decision_candidate_id_must_match_its_recorded_pair(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {"person_id": "skv-p000001", "display_name": "One", "profile_slug": "one"},
            {"person_id": "skv-p000002", "display_name": "Two", "profile_slug": "two"},
            {"person_id": "skv-p000003", "display_name": "Three", "profile_slug": "three"},
        ],
    )
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people("skv-p000001", "skv-p000002"),
                "decision": "reject",
                "primary_person_id": "skv-p000001",
                "secondary_person_id": "skv-p000003",
                "applied_at": "2026-04-28T12:00:00+02:00",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    errors = find_identity_graph_errors(load_identity_data(tmp_path))

    assert any("does not match person pair" in issue for issue in errors["issue"])
    with pytest.raises(ValueError, match="does not match person pair"):
        apply_match_decisions(tmp_path)


def test_duplicate_candidate_decision_rows_fail_before_any_change(tmp_path: Path) -> None:
    primary = "skv-p000001"
    secondary = "skv-p000002"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Runner Full", "profile_slug": "runner-full"},
            {"person_id": secondary, "display_name": "Runner", "profile_slug": "runner"},
        ],
    )
    candidate_id = candidate_id_for_people(primary, secondary)
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id,
                "decision": "reject",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
            },
            {
                "candidate_id": candidate_id,
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
            },
        ],
        MATCH_DECISION_COLUMNS,
    )

    with pytest.raises(ValueError, match="duplicate candidate_id"):
        apply_match_decisions(tmp_path)

    assert load_identity_data(tmp_path).registry.set_index("person_id").loc[secondary, "status"] == "active"


def test_canonical_seed_preserves_applied_decision_and_reapply_is_idempotent(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    seed_dir = tmp_path / "seed"
    primary = "skv-p000001"
    secondary = "skv-p000002"
    write_basic_registry(
        private_dir,
        [
            {"person_id": primary, "display_name": "Runner Full", "profile_slug": "runner-full"},
            {
                "person_id": secondary,
                "display_name": "Runner",
                "profile_slug": "runner",
                "status": "merged",
                "merged_into_person_id": primary,
            },
        ],
    )
    applied_at = "2026-04-28T12:00:00+02:00"
    write_csv(
        private_dir / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "reviewed_at": "2026-04-28T11:00:00+02:00",
                "applied_at": applied_at,
            }
        ],
        MATCH_DECISION_COLUMNS,
    )
    identity = load_identity_data(private_dir)

    write_canonical_identity_seed(identity, seed_dir)
    copied = load_identity_data(seed_dir)

    assert copied.match_decisions.iloc[0]["applied_at"] == applied_at
    result = apply_match_decisions(seed_dir, now=datetime.fromisoformat("2026-04-29T12:00:00+02:00"))
    assert result["applied_counts"]["merge"] == 0


def test_transitive_merge_cluster_preserves_each_recorded_candidate_pair(tmp_path: Path) -> None:
    first = "skv-p000001"
    second = "skv-p000002"
    third = "skv-p000003"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": first, "display_name": "Runner Full", "profile_slug": "runner-full"},
            {"person_id": second, "display_name": "Runner Short", "profile_slug": "runner-short"},
            {"person_id": third, "display_name": "Runner Encoded", "profile_slug": "runner-encoded"},
        ],
    )
    recorded_pairs = [(first, second), (first, third), (second, third)]
    write_csv(
        tmp_path / "person_match_decisions.csv",
        [
            {
                "candidate_id": candidate_id_for_people(primary, secondary),
                "decision": "merge",
                "primary_person_id": primary,
                "secondary_person_id": secondary,
                "preferred_display_name": "Runner Full",
            }
            for primary, secondary in recorded_pairs
        ],
        MATCH_DECISION_COLUMNS,
    )

    result = apply_match_decisions(tmp_path, now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"))
    identity = load_identity_data(tmp_path)
    registry = identity.registry.set_index("person_id")
    stored_pairs = list(
        identity.match_decisions[["primary_person_id", "secondary_person_id"]].itertuples(index=False, name=None)
    )

    assert result["error_count"] == 0
    assert result["applied_counts"]["merge"] == 3
    assert registry.loc[second, "merged_into_person_id"] == first
    assert registry.loc[third, "merged_into_person_id"] == first
    assert stored_pairs == recorded_pairs
    assert identity.match_decisions["applied_at"].ne("").all()
    assert find_identity_graph_errors(identity).empty


def test_alias_only_decision_cannot_create_ambiguous_active_name_owner(tmp_path: Path) -> None:
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

    result = apply_match_decisions(tmp_path, now=datetime.fromisoformat("2026-04-28T12:00:00+02:00"))
    identity = load_identity_data(tmp_path)
    registry = identity.registry.set_index("person_id")
    match = match_result_to_person({"athlete_name": "Kristina M. Stang"}, identity)

    assert result["error_count"] == 1
    assert registry.loc[secondary, "status"] == "active"
    assert match.person_id == secondary
    assert match.method == "registry_name"


def test_alias_only_rejects_secondary_merged_into_another_primary(tmp_path: Path) -> None:
    primary = "skv-p000010"
    secondary = "skv-p000011"
    other_primary = "skv-p000012"
    write_basic_registry(
        tmp_path,
        [
            {"person_id": primary, "display_name": "Primary", "profile_slug": "primary"},
            {
                "person_id": secondary,
                "display_name": "Secondary",
                "profile_slug": "secondary",
                "status": "merged",
                "merged_into_person_id": other_primary,
            },
            {"person_id": other_primary, "display_name": "Other", "profile_slug": "other"},
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
                "reviewed_at": "2026-04-28T10:00:00+02:00",
            }
        ],
        MATCH_DECISION_COLUMNS,
    )

    result = apply_match_decisions(tmp_path)

    assert result["error_count"] == 1
    assert "already resolve" in result["errors"][0]["error"]


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


def test_5000m_is_a_standard_ranking_and_profile_distance(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "distance": "5000 m",
                "gender": "K",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "result_id": "res-5000m",
                "athlete_name": "Runner One",
                "result_time_seconds": 935.7,
                "result_time_normalized": "15:35.70",
                "result_time_raw": "15:35.70",
                "published_date_sort": pd.Timestamp("2026-07-04"),
                "published_date_iso": "2026-07-04",
                "published_date_label": "04.07.2026",
                "week_number": 27,
                "event_label": "Track Test",
                "place": "1",
                "class_place": "1",
            }
        ]
    )
    df["profile_distance"] = df.apply(normalize_ranking_distance, axis=1)

    rankings = build_rankings(df)
    five_thousand = next(group for group in rankings if group["distance"] == "5000 m")
    assert five_thousand["women"][0]["result_id"] == "res-5000m"

    identity = ensure_new_people_are_appended_without_changing_existing_ids(df, tmp_path)
    profile = build_people_payload(df, identity)["profiles"][0]
    assert "5000 m" in profile["distances"]
    assert profile["best_results"][0]["distance"] == "5000 m"


def test_10000m_and_steeple_are_standard_profile_distances(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "distance": "10000 m",
                "gender": "K",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "result_id": "res-10000m",
                "athlete_name": "Runner One",
                "result_time_seconds": 1900.0,
                "result_time_normalized": "31:40",
                "result_time_raw": "31:40",
                "published_date_sort": pd.Timestamp("2026-07-04"),
                "published_date_iso": "2026-07-04",
                "published_date_label": "04.07.2026",
                "week_number": 27,
                "event_label": "Track Test",
                "place": "1",
                "class_place": "1",
            },
            {
                "distance": "3000 m hinder",
                "gender": "K",
                "person_id": "skv-p000001",
                "person_slug": "runner-one",
                "result_id": "res-steeple",
                "athlete_name": "Runner One",
                "result_time_seconds": 560.0,
                "result_time_normalized": "9:20",
                "result_time_raw": "9:20",
                "published_date_sort": pd.Timestamp("2026-07-05"),
                "published_date_iso": "2026-07-05",
                "published_date_label": "05.07.2026",
                "week_number": 27,
                "event_label": "Track Test",
                "place": "1",
                "class_place": "1",
            },
        ]
    )
    df["profile_distance"] = df.apply(normalize_ranking_distance, axis=1)

    rankings = build_rankings(df)
    ten_thousand = next(group for group in rankings if group["distance"] == "10000 m")
    steeple = next(group for group in rankings if group["distance"] == "3000 m hinder")
    assert ten_thousand["women"][0]["result_id"] == "res-10000m"
    assert steeple["women"][0]["result_id"] == "res-steeple"

    identity = ensure_new_people_are_appended_without_changing_existing_ids(df, tmp_path)
    profile = build_people_payload(df, identity)["profiles"][0]
    assert "10000 m" in profile["distances"]
    assert "3000 m hinder" in profile["distances"]


def test_identity_graph_reports_dangling_references_and_merge_cycles(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [
            {
                "person_id": "skv-p000001",
                "display_name": "One",
                "profile_slug": "one",
                "status": "merged",
                "merged_into_person_id": "skv-p000002",
            },
            {
                "person_id": "skv-p000002",
                "display_name": "Two",
                "profile_slug": "two",
                "status": "merged",
                "merged_into_person_id": "skv-p000001",
            },
        ],
    )
    write_csv(
        tmp_path / "person_aliases.csv",
        [
            {
                "person_id": "skv-p009999",
                "alias": "Missing Runner",
                "normalized_alias": "missing runner",
                "source": "test",
                "active": "true",
                "notes": "",
            }
        ],
        ["person_id", "alias", "normalized_alias", "source", "active", "notes"],
    )

    errors = find_identity_graph_errors(load_identity_data(tmp_path))

    assert "merge cycle" in set(errors["issue"])
    assert "person_id is missing from registry" in set(errors["issue"])


def test_missing_identity_match_report_keeps_actionable_method_and_reason(tmp_path: Path) -> None:
    write_basic_registry(
        tmp_path,
        [{"person_id": "skv-p000001", "display_name": "Known Runner", "profile_slug": "known-runner"}],
    )
    identity = load_identity_data(tmp_path)
    df = pd.DataFrame(
        [
            {
                "result_id": "res-1",
                "athlete_name": "Unknown Runner",
                "person_id": "",
                "identity_match_method": "conflicting_identity_signals",
                "identity_match_review": "name->p1; external_id->p2",
            }
        ]
    )

    report = build_identity_reports(df, identity)["results_without_person_id"]

    assert report.iloc[0]["identity_match_method"] == "conflicting_identity_signals"
    assert report.iloc[0]["identity_match_review"] == "name->p1; external_id->p2"


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
                "wa_points": 900.0,
                "is_pb": True,
                "is_sb": False,
                "place": "1",
                "notes_clean": "PB",
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

    assert payload["schema_version"] == 5
    assert payload["results"][0]["is_pb"] is True
    assert payload["results"][0]["ranking_distance"] == "5 km"
    assert payload["weeks"][0]["pb_count"] == 1
    assert payload["weeks"][0]["new_athlete_count"] == 1
    assert payload["weeks"][0]["top_performances"][0]["wa_points"] == 900.0
    assert payload["months"][0]["month_label"] == "April"
    assert payload["people"]["profile_count"] == 1
    assert payload["results"][0]["person_id"] == "skv-p000001"
    validate_public_payload(payload)

    with pytest.raises(ValueError):
        validate_public_payload({"results": [{"slack_user_id": "U123PRIVATE"}]})
    for private_field in (
        "world_athletics_id",
        "wa_person_id",
        "source_person_id",
        "external_person_id",
        "participant_id",
        "deltaker_id",
        "source_system",
    ):
        with pytest.raises(ValueError):
            validate_public_payload({"results": [{private_field: "PRIVATE"}]})


def test_generated_public_json_has_people_and_no_private_fields() -> None:
    payload_path = ROOT / "docs" / "data" / "results.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 5
    assert "people" in payload
    assert all(result.get("person_id") for result in payload["results"])
    known_distances = [
        result["competition_distance_km"]
        for result in payload["results"]
        if result.get("competition_distance_status") == "known"
    ]
    assert len(known_distances) == payload["stats"]["known_distance_result_count"]
    assert payload["stats"]["unknown_distance_result_count"] == 0
    assert all(isinstance(distance, (int, float)) and distance > 0 for distance in known_distances)
    assert sum(known_distances) == pytest.approx(payload["stats"]["competition_distance_km"])
    assert all(
        result.get("competition_distance_km") is None
        for result in payload["results"]
        if result.get("competition_distance_status") == "excluded_aggregate"
    )
    slug_map = payload["people"]["slug_map"]
    assert slug_map["maria-bipop"] == slug_map["maria-bipop-bang-jensen"] == "skv-p000202"
    assert slug_map["marianne-harnes"] == slug_map["marianne-harnes-myhrer"] == "skv-p000206"

    profiles = {profile["person_id"]: profile for profile in payload["people"]["profiles"]}
    assert profiles["skv-p000202"]["result_count"] == 14
    assert profiles["skv-p000206"]["result_count"] == 6
    assert all(result["gender"] == "K" for result in payload["results"] if result["person_id"] == "skv-p000238")
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
