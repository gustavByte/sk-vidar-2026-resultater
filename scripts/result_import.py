from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from result_taxonomy import split_public_internal_note


ALIASES = {
    "published_date": {"published_date", "date", "dato", "resultatdato"},
    "week_number": {"week_number", "uke", "ukenummer"},
    "event_name": {"event_name", "event", "lop", "løp", "arrangement", "stevne"},
    "distance": {"distance", "distanse", "ovelse", "øvelse"},
    "athlete_name": {"athlete_name", "name", "navn", "utover", "utøver"},
    "result_time_raw": {"result_time_raw", "result_time", "time", "tid", "resultat"},
    "gender": {"gender", "kjonn", "kjønn", "sex"},
    "class_name": {"class_name", "class", "klasse", "category", "kategori"},
    "position": {"position", "place", "plass", "totalplass"},
    "class_place": {"class_place", "klasseplass", "plass_klasse"},
    "notes": {"notes", "note", "notat", "kommentar"},
}

REQUIRED = ("published_date", "event_name", "distance", "athlete_name", "result_time_raw")
NON_RESULTS = {"DNS", "DNF", "DQ", "DSQ"}


def normalize_header(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9æøå]+", "_", text).strip("_")
    return text


HEADER_LOOKUP = {alias: canonical for canonical, aliases in ALIASES.items() for alias in aliases}


@dataclass(frozen=True)
class ImportCandidate:
    source_file: str
    source_row: int
    candidate_id: str
    status: str
    issues: tuple[str, ...]
    row: dict[str, object]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_delimited(path: Path) -> pd.DataFrame:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";|\t,").delimiter
    except csv.Error:
        delimiter = ";"
    return pd.read_csv(path, sep=delimiter, dtype=str, encoding="utf-8-sig").fillna("")


def read_source(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix in {".csv", ".txt", ".tsv"}:
        return _read_delimited(path)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, dtype=str, engine="openpyxl").fillna("")
    raise ValueError(f"Ustøttet filtype: {suffix or 'ingen filtype'}")


def canonical_columns(frame: pd.DataFrame) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for column in frame.columns:
        canonical = HEADER_LOOKUP.get(normalize_header(column))
        if canonical and canonical not in mapped:
            mapped[canonical] = str(column)
    return mapped


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _gender(value: object, class_name: object) -> str:
    text = _clean(value).casefold()
    if text.startswith(("k", "w", "f")):
        return "K"
    if text.startswith("m"):
        return "M"
    class_text = _clean(class_name).upper()
    return class_text[:1] if class_text[:1] in {"K", "M"} else ""


def result_key(row: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        _clean(row.get(column)).casefold()
        for column in ("published_date", "event_name", "distance", "athlete_name", "result_time_raw")
    )


def adapt_source(path: Path) -> list[ImportCandidate]:
    try:
        frame = read_source(path)
    except Exception as error:
        candidate_id = hashlib.sha1(f"{path.name}|file".encode("utf-8")).hexdigest()[:16]
        return [ImportCandidate(path.name, 0, candidate_id, "review", (str(error),), {})]

    columns = canonical_columns(frame)
    missing_headers = [column for column in REQUIRED if column not in columns]
    if missing_headers:
        candidate_id = hashlib.sha1(f"{path.name}|headers".encode("utf-8")).hexdigest()[:16]
        issue = f"Mangler kolonner: {', '.join(missing_headers)}"
        return [ImportCandidate(path.name, 0, candidate_id, "review", (issue,), {})]

    candidates: list[ImportCandidate] = []
    for index, source in frame.iterrows():
        row = {canonical: _clean(source.get(original)) for canonical, original in columns.items()}
        raw_date = row.get("published_date", "")
        parsed_date = pd.to_datetime(raw_date, errors="coerce", dayfirst=not bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date)))
        issues: list[str] = []
        if pd.isna(parsed_date):
            issues.append("Ugyldig dato")
        else:
            row["published_date"] = parsed_date.strftime("%Y-%m-%d")
            row["week_number"] = int(parsed_date.isocalendar().week)

        for column in REQUIRED[1:]:
            if not _clean(row.get(column)):
                issues.append(f"Mangler {column}")

        result_status = _clean(row.get("result_time_raw")).upper()
        if result_status in NON_RESULTS:
            issues.append(f"Ikke publiserbart resultat: {result_status}")

        public_note, internal_note = split_public_internal_note(row.get("notes", ""))
        row["notes"] = public_note
        row["internal_note"] = internal_note
        row["gender"] = _gender(row.get("gender"), row.get("class_name"))
        if not row["gender"]:
            issues.append("Mangler sikkert kjønn")

        key_text = "|".join(result_key(row))
        candidate_id = hashlib.sha1(f"{path.name}|{index + 2}|{key_text}".encode("utf-8")).hexdigest()[:16]
        candidates.append(
            ImportCandidate(
                source_file=path.name,
                source_row=index + 2,
                candidate_id=candidate_id,
                status="ready" if not issues else "review",
                issues=tuple(issues),
                row=row,
            )
        )
    return candidates
