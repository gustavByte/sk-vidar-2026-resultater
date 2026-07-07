from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from recalculate_wa_points_2026 import _wa_event_for_row  # noqa: E402


def event_for(distance: str, event_name: str = "Baneløp") -> str:
    return _wa_event_for_row(pd.Series({"distance": distance, "event_name": event_name}))


def test_track_standard_distances_map_to_wa_events() -> None:
    assert event_for("5000 m") == "5000m"
    assert event_for("10000 m") == "10000m"
    assert event_for("3000 m hinder") == "3000m SC"


def test_masters_meter_labels_map_to_standard_track_events() -> None:
    assert event_for("WV 800 Meters (W50,W55)", "Nordic Masters") == "800m"
    assert event_for("MV 1500 Meters (M35-M50)", "Nordic Masters") == "1500m"
    assert event_for("MV 5000 Meters (M35-M55):", "Nordic Masters") == "5000m"
    assert event_for("MV 10000 Meters (M35-M60, M70-M80)", "Nordic Masters") == "10000m"


def test_bislett_distanseserie_road_3k_stays_unmapped() -> None:
    assert event_for("3000 m", "Bislett distanseserie 4- 3K") == ""

