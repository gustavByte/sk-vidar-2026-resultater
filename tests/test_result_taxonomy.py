from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from result_taxonomy import (  # noqa: E402
    classify_note_for_import,
    competition_distance_km_for_row,
    competition_distance_status_for_row,
    event_type_for_row,
    public_note_has_internal_markers,
    split_public_internal_note,
    terrain_tags_for_row,
    wa_status_for_values,
)


def test_competition_distance_parses_common_units_and_named_distances() -> None:
    assert competition_distance_km_for_row({"distance": "4,7 km"}) == 4.7
    assert competition_distance_km_for_row({"distance": "5000 Meters"}) == 5.0
    assert competition_distance_km_for_row({"distance": "3000 m hinder"}) == 3.0
    assert competition_distance_km_for_row({"distance": "SKY 12.5K"}) == 12.5
    assert competition_distance_km_for_row({"distance": "50K"}) == 50.0
    assert competition_distance_km_for_row({"distance": "PDA 55 km / 3300 hm"}) == 55.0
    assert competition_distance_km_for_row({"distance": "10 miles"}) == 16.09344
    assert competition_distance_km_for_row({"distance": "Halvmaraton"}) == 21.0975
    assert competition_distance_km_for_row({"distance": "Maraton"}) == 42.195
    assert competition_distance_km_for_row({"distance": "42 km"}) == 42.0


def test_competition_distance_uses_event_specific_and_backyard_values() -> None:
    assert competition_distance_km_for_row(
        {"event_label": "Jotunheimen Trail Run 2026", "distance": "Ultra"}
    ) == 73.0
    assert competition_distance_km_for_row(
        {"event_label": "NM terrengløp kort løype stafett 2026", "distance": "6 km stafett"}
    ) == 3.0
    assert competition_distance_km_for_row(
        {"distance": "Backyard", "notes_clean": "8 runder 53.6 km"}
    ) == 53.6
    assert competition_distance_km_for_row(
        {
            "event_label": "Lommedalen Backyard 2026",
            "distance": "Backyard",
            "athlete_name": "Martine Svendsen",
        }
    ) == 80.4
    assert competition_distance_km_for_row(
        {
            "event_label": "The Arctic Run 2026",
            "distance": "Para Arctic Run",
            "athlete_name": "Tone Gravvold",
        }
    ) == 21.0975
    assert competition_distance_km_for_row({"distance": "Festaløpet"}) == 17.5


def test_competition_distance_does_not_guess_ambiguous_categories() -> None:
    assert competition_distance_km_for_row({"distance": "Kombinert"}) is None
    assert competition_distance_km_for_row({"distance": "Backyard", "notes_clean": "9 timer"}) is None
    assert competition_distance_km_for_row({"distance": "Ultra"}) is None
    assert competition_distance_status_for_row({"distance": "Kombinert"}) == "excluded_aggregate"
    assert competition_distance_status_for_row({"distance": "Ultra"}) == "unknown"


def test_terrain_taxonomy_catches_new_mont_blanc_event() -> None:
    row = {"event_name": "Marathon du Mont-Blanc 2026", "distance": "42 km", "notes": "fjelløp"}

    assert "fjellop" in terrain_tags_for_row(row)
    assert event_type_for_row(row) == "terrain"


def test_internal_note_is_removed_from_public_copy() -> None:
    public, internal = classify_note_for_import("Sterk avslutning. Svak navnematch, sjekk Slack før publisering.")

    assert public == "Sterk avslutning"
    assert "Slack" in internal
    assert not public_note_has_internal_markers(public)


def test_legacy_note_is_not_a_publication_fallback() -> None:
    public, internal = split_public_internal_note("Sterk avslutning")

    assert public == ""
    assert internal == "Sterk avslutning"


def test_only_explicit_public_note_crosses_publication_boundary() -> None:
    public, internal = split_public_internal_note(
        "Rånotat som beholdes privat",
        "PB. Relatert utøver må kontrolleres før publisering.",
        "Opprinnelig intern merknad",
    )

    assert public == "PB"
    assert "Relatert utøver" in internal
    assert "Opprinnelig intern merknad" in internal
    assert not public_note_has_internal_markers(public)


def test_wa_status_distinguishes_unsupported_and_missing() -> None:
    assert wa_status_for_values(700, "10 km", "M", "34:00") == "scored"
    assert wa_status_for_values(None, "", "K", "1:20:00") == "not_applicable"
    assert wa_status_for_values(None, "10 km", "M", "34:00") == "missing"
