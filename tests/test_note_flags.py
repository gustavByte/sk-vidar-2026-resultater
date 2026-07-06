from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_site_2026 import parse_note_flags  # noqa: E402


def test_pb_token_alone() -> None:
    assert parse_note_flags("PB") == {"is_pb": True, "is_sb": False}


def test_pb_token_with_venue_note() -> None:
    assert parse_note_flags("PB; Stovnerbanen, Oslo; OpenTrack")["is_pb"] is True


def test_pb_token_with_comma_separator() -> None:
    assert parse_note_flags("PB, norsk U23-rekord")["is_pb"] is True


def test_sb_token() -> None:
    assert parse_note_flags("SB") == {"is_pb": False, "is_sb": True}


def test_both_tokens() -> None:
    assert parse_note_flags("PB; SB") == {"is_pb": True, "is_sb": True}


def test_lowercase_token_matches() -> None:
    assert parse_note_flags("pb")["is_pb"] is True


def test_embedded_pb_does_not_match() -> None:
    assert parse_note_flags("Klubb-PB")["is_pb"] is False


def test_unrelated_note() -> None:
    assert parse_note_flags("fartsholder") == {"is_pb": False, "is_sb": False}


def test_empty_and_missing_note() -> None:
    assert parse_note_flags("") == {"is_pb": False, "is_sb": False}
    assert parse_note_flags(None) == {"is_pb": False, "is_sb": False}
    assert parse_note_flags(float("nan")) == {"is_pb": False, "is_sb": False}
