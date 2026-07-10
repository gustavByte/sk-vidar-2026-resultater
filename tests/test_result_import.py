from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from result_import import adapt_source, result_key  # noqa: E402


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

    assert candidate.row["notes"] == "PB"
    assert "Slack" in candidate.row["internal_note"]
