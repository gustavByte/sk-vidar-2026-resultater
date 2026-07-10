from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from result_taxonomy import (  # noqa: E402
    event_type_for_row,
    public_note_has_internal_markers,
    split_public_internal_note,
    terrain_tags_for_row,
    wa_status_for_values,
)


def test_terrain_taxonomy_catches_new_mont_blanc_event() -> None:
    row = {"event_name": "Marathon du Mont-Blanc 2026", "distance": "42 km", "notes": "fjelløp"}

    assert "fjellop" in terrain_tags_for_row(row)
    assert event_type_for_row(row) == "terrain"


def test_internal_note_is_removed_from_public_copy() -> None:
    public, internal = split_public_internal_note("Sterk avslutning. Svak navnematch, sjekk Slack før publisering.")

    assert public == "Sterk avslutning"
    assert "Slack" in internal
    assert not public_note_has_internal_markers(public)


def test_wa_status_distinguishes_unsupported_and_missing() -> None:
    assert wa_status_for_values(700, "10 km", "M", "34:00") == "scored"
    assert wa_status_for_values(None, "", "K", "1:20:00") == "not_applicable"
    assert wa_status_for_values(None, "10 km", "M", "34:00") == "missing"
