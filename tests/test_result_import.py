from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from result_import import adapt_source, result_key  # noqa: E402
from update_results_2026 import workbook_row  # noqa: E402


def test_canonical_csv_is_ready_for_import(tmp_path: Path) -> None:
    source = tmp_path / "resultater.csv"
    source.write_text(
        "dato;løp;distanse;navn;tid;kjønn;notat\n"
        "2026-07-08;Sommerløpet;10 km;Kari Løper;35:12;K;PB\n",
        encoding="utf-8-sig",
    )

    candidates = adapt_source(source)

    assert len(candidates) == 1
    assert candidates[0].status == "ready"
    assert candidates[0].row["published_date"] == "2026-07-08"
    assert candidates[0].row["week_number"] == 28
    assert result_key(candidates[0].row)[3] == "kari løper"


def test_unstructured_text_is_sent_to_review(tmp_path: Path) -> None:
    source = tmp_path / "pasted.txt"
    source.write_text("Kari Løper 35:12 på Sommerløpet", encoding="utf-8")

    candidates = adapt_source(source)

    assert candidates[0].status == "review"
    assert "Mangler kolonner" in candidates[0].issues[0]


def test_internal_note_does_not_enter_public_note(tmp_path: Path) -> None:
    source = tmp_path / "resultater.csv"
    source.write_text(
        "dato;løp;distanse;navn;tid;kjønn;notat\n"
        "2026-07-08;Sommerløpet;10 km;Kari;35:12;K;PB. Sjekk Slack-medlemskap\n",
        encoding="utf-8-sig",
    )

    candidate = adapt_source(source)[0]

    assert candidate.row["notes"] == "PB. Sjekk Slack-medlemskap"
    assert candidate.row["public_note"] == "PB"
    assert "Slack" in candidate.row["internal_note"]


def test_import_preserves_external_identity_fields(tmp_path: Path) -> None:
    source = tmp_path / "resultater.csv"
    source.write_text(
        "dato;løp;distanse;navn;tid;kjønn;slack_user_id;world_athletics_id;source_system;source_person_id\n"
        "2026-07-08;Sommerløpet;10 km;Kari Løper;35:12;K;U123;WA456;EQ Timing;SRC789\n",
        encoding="utf-8-sig",
    )

    candidate = adapt_source(source)[0]
    columns = ["athlete_name", "slack_user_id", "world_athletics_id", "source_system", "source_person_id"]

    assert candidate.row["slack_user_id"] == "U123"
    assert candidate.row["world_athletics_id"] == "WA456"
    assert candidate.row["source_system"] == "EQ Timing"
    assert candidate.row["source_person_id"] == "SRC789"
    assert workbook_row(candidate, columns) == ["Kari Løper", "U123", "WA456", "EQ Timing", "SRC789"]


def test_import_holds_source_person_id_without_source_system_for_review(tmp_path: Path) -> None:
    source = tmp_path / "resultater.csv"
    source.write_text(
        "dato;løp;distanse;navn;tid;kjønn;source_person_id\n"
        "2026-07-08;Sommerløpet;10 km;Kari Løper;35:12;K;123\n",
        encoding="utf-8-sig",
    )

    candidate = adapt_source(source)[0]

    assert candidate.status == "review"
    assert "source_person_id krever source_system" in candidate.issues


def test_import_rejects_event_scoped_participant_id_as_person_identity(tmp_path: Path) -> None:
    source = tmp_path / "resultater.csv"
    source.write_text(
        "dato;løp;distanse;navn;tid;kjønn;source_system;participant_id\n"
        "2026-07-08;Sommerløpet;10 km;Kari Løper;35:12;K;EQ Timing;123\n",
        encoding="utf-8-sig",
    )

    candidate = adapt_source(source)[0]

    assert candidate.status == "review"
    assert any("ikke en stabil person-ID" in issue for issue in candidate.issues)
    assert "source_person_id" not in candidate.row
