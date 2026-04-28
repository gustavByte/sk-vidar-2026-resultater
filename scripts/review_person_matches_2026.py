from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from person_identity import (
    MATCH_CANDIDATE_COLUMNS,
    apply_match_decisions,
    build_person_match_candidates,
    ensure_identity_files,
    load_identity_data,
)
from project_paths import IDENTITY_REPORT_DIR, PERSON_IDENTITY_DIR, ROOT_DIR


PUBLIC_RESULTS_FILE = ROOT_DIR / "docs" / "data" / "results.json"
PERSON_MATCH_CANDIDATES_FILE = IDENTITY_REPORT_DIR / "person_match_candidates.csv"


def load_public_results() -> pd.DataFrame:
    if not PUBLIC_RESULTS_FILE.exists():
        return pd.DataFrame()
    payload = json.loads(PUBLIC_RESULTS_FILE.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("results", []))


def generate_candidates() -> pd.DataFrame:
    ensure_identity_files(PERSON_IDENTITY_DIR)
    identity = load_identity_data(PERSON_IDENTITY_DIR)
    results_df = load_public_results()
    candidates = build_person_match_candidates(identity, results_df)
    IDENTITY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if candidates.empty:
        candidates = pd.DataFrame(columns=MATCH_CANDIDATE_COLUMNS)
    candidates.to_csv(PERSON_MATCH_CANDIDATES_FILE, index=False, encoding="utf-8", lineterminator="\n")
    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and apply manual person match decisions.")
    parser.add_argument("--generate", action="store_true", help="Write the local person match candidate CSV.")
    parser.add_argument("--apply", action="store_true", help="Apply approved decisions from person_match_decisions.csv.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.generate and not args.apply:
        args.generate = True

    if args.apply:
        result = apply_match_decisions(PERSON_IDENTITY_DIR)
        counts = result["applied_counts"]
        print(
            "Applied decisions: "
            f"merge={counts['merge']}, alias_only={counts['alias_only']}, "
            f"reject={counts['reject']}, defer={counts['defer']}"
        )
        if result["error_count"]:
            print(f"Decision errors: {result['error_count']}")
            for error in result["errors"]:
                print(
                    f"- {error['candidate_id']}: {error['error']} "
                    f"({error['primary_person_id']} -> {error['secondary_person_id']})"
                )

    if args.generate:
        candidates = generate_candidates()
        print(f"Created candidate report: {PERSON_MATCH_CANDIDATES_FILE}")
        print(f"Candidates: {len(candidates)}")


if __name__ == "__main__":
    main()
