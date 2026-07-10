from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_shared_weekly_results_2026 import filter_publishable_results  # noqa: E402


def test_filter_publishable_results_removes_dns_and_dnf_rows() -> None:
    rows = pd.DataFrame(
        [
            {"athlete_name": "Runner A", "result_time_raw": "DNS", "result_time_normalized": ""},
            {"athlete_name": "Runner B", "result_time_raw": "DNF", "result_time_normalized": ""},
            {"athlete_name": "Runner C", "result_time_raw": "15:00", "result_time_normalized": "15:00"},
            {"athlete_name": "Runner D", "result_time_raw": "", "result_time_normalized": "dnf"},
            {"athlete_name": "Runner E", "result_time_raw": "", "result_time_normalized": "", "position": "DNF"},
            {"athlete_name": "Runner F", "result_time_raw": "", "result_time_normalized": "", "class_place": "DQ"},
            {"athlete_name": "Runner G", "result_time_raw": "", "result_time_normalized": "", "status": "DNS"},
        ]
    )

    published = filter_publishable_results(rows)

    assert published["athlete_name"].tolist() == ["Runner C"]
