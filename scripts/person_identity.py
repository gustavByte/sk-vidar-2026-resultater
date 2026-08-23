from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from project_paths import (
    CANONICAL_PERSON_IDENTITY_DIR,
    PERSON_ALIASES_FILE,
    PERSON_EXTERNAL_IDS_FILE,
    PERSON_DRAFTS_FILE,
    PERSON_IDENTITY_DIR,
    PERSON_MATCH_DECISIONS_FILE,
    PERSON_REGISTRY_FILE,
    PERSON_SLUG_HISTORY_FILE,
    RESULT_PERSON_OVERRIDES_FILE,
)
from spreadsheet_security import csv_safe_dataframe


PERSON_ID_PREFIX = "skv-p"
SCHEMA_VERSION = 5

REGISTRY_COLUMNS = [
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
ALIAS_COLUMNS = ["person_id", "alias", "normalized_alias", "source", "active", "notes"]
EXTERNAL_ID_COLUMNS = ["person_id", "source", "external_id", "active", "notes"]
SLUG_HISTORY_COLUMNS = ["person_id", "profile_slug", "active_from", "active_to", "reason"]
RESULT_OVERRIDE_COLUMNS = ["result_id", "person_id", "active", "reason", "notes"]
MATCH_DECISION_COLUMNS = [
    "candidate_id",
    "decision",
    "primary_person_id",
    "secondary_person_id",
    "preferred_display_name",
    "notes",
    "reviewed_at",
    "applied_at",
]
DRAFT_COLUMNS = ["person_id", "normalized_name", "external_source", "external_id", "display_name", "created_at"]
MATCH_CANDIDATE_COLUMNS = [
    "candidate_id",
    "confidence",
    "suggested_decision",
    "suggested_primary_person_id",
    "suggested_primary_name",
    "person_id_1",
    "display_name_1",
    "result_count_1",
    "latest_result_date_1",
    "person_id_2",
    "display_name_2",
    "result_count_2",
    "latest_result_date_2",
    "shared_tokens",
    "reason",
    "sequence_similarity",
    "token_overlap",
    "decision",
    "decision_notes",
]
APPLIED_MATCH_DECISIONS = {"merge", "alias_only", "reject"}
OPEN_MATCH_DECISIONS = {"", "defer", "merge", "alias_only"}

STANDARD_PROFILE_DISTANCES = ["800 m", "1500 m", "3000 m", "3000 m hinder", "5000 m", "10000 m", "5 km", "10 km", "Halvmaraton", "Maraton"]
DISTANCE_ORDER = {distance: index for index, distance in enumerate(STANDARD_PROFILE_DISTANCES)}

PRIVATE_PUBLIC_FIELD_NAMES = {
    "slack_user_id",
    "slack_id",
    "world_athletics_id",
    "wa_person_id",
    "world_athletics_person_id",
    "source_person_id",
    "external_person_id",
    "participant_id",
    "deltaker_id",
    "source_system",
    "source_provider",
    "result_provider",
    "kildesystem",
    "slack_name",
    "name_in_message",
    "raw_entry",
    "raw_message",
    "source_ts",
    "source_order",
    "nm sync",
    "beste pr person",
    "notes",
    "external_id",
    "local_path",
    "source_file",
    "person_notes",
    "override_notes",
    "wa kjønn",
    "wa kjonn",
    "wa øvelse",
    "wa ovelse",
    "wa poeng",
}

EXTERNAL_ID_SOURCE_COLUMNS = {
    "slack": ["slack_user_id", "slack_id"],
    "world_athletics": ["world_athletics_id", "wa_person_id", "world_athletics_person_id"],
}
RESULT_SOURCE_ID_COLUMNS = ("source_person_id", "external_person_id")
RESULT_SOURCE_SYSTEM_COLUMNS = ("source_system", "source_provider", "result_provider", "kildesystem")
SINGLETON_EXTERNAL_ID_SOURCES = {"slack", "world_athletics"}

NORWEGIAN_TRANSLATION = str.maketrans(
    {
        "æ": "ae",
        "ø": "o",
        "å": "a",
        "Æ": "Ae",
        "Ø": "O",
        "Å": "A",
        "ð": "d",
        "Ð": "D",
        "þ": "th",
        "Þ": "Th",
    }
)


@dataclass(frozen=True)
class IdentityPaths:
    identity_dir: Path
    registry: Path
    aliases: Path
    external_ids: Path
    slug_history: Path
    result_overrides: Path
    match_decisions: Path
    drafts: Path


@dataclass
class IdentityData:
    registry: pd.DataFrame
    aliases: pd.DataFrame
    external_ids: pd.DataFrame
    slug_history: pd.DataFrame
    result_overrides: pd.DataFrame
    match_decisions: pd.DataFrame
    provisional_person_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PersonMatch:
    person_id: str
    method: str
    reason: str = ""
    needs_review: bool = False


@dataclass
class IdentityIndexes:
    registry_by_normalized_name: dict[str, set[str]]
    aliases_by_normalized_name: dict[str, set[str]]
    external_ids: dict[tuple[str, str], set[str]]
    external_ids_by_person_source: dict[tuple[str, str], set[str]]
    result_overrides: dict[str, set[str]]
    slug_by_person_id: dict[str, str]


def _identity_paths(identity_dir: Path | None = None) -> IdentityPaths:
    base_dir = Path(identity_dir) if identity_dir is not None else PERSON_IDENTITY_DIR
    return IdentityPaths(
        identity_dir=base_dir,
        registry=base_dir / PERSON_REGISTRY_FILE.name,
        aliases=base_dir / PERSON_ALIASES_FILE.name,
        external_ids=base_dir / PERSON_EXTERNAL_IDS_FILE.name,
        slug_history=base_dir / PERSON_SLUG_HISTORY_FILE.name,
        result_overrides=base_dir / RESULT_PERSON_OVERRIDES_FILE.name,
        match_decisions=base_dir / PERSON_MATCH_DECISIONS_FILE.name,
        drafts=base_dir / PERSON_DRAFTS_FILE.name,
    )


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    return False


def _clean_text(value: object) -> str:
    if _is_missing(value):
        return ""
    text = str(value).replace("\u00a0", " ").replace("\ufeff", "").strip()
    return "" if text.lower() == "nan" else text


MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2")


def repair_mojibake(text: str) -> str:
    repaired = text
    for _ in range(3):
        if not any(marker in repaired for marker in MOJIBAKE_MARKERS):
            break
        try:
            candidate = repaired.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def clean_display_text(value: object) -> str:
    return repair_mojibake(_clean_text(value))


def normalize_name(value: object) -> str:
    """Return an exact-match key for a name or alias.

    This intentionally does not do fuzzy matching. It only removes formatting
    differences we want to treat as the same written alias.
    """

    text = repair_mojibake(_clean_text(value))
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text).translate(NORWEGIAN_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold()
    text = re.sub(r"['’`´]", "", text)
    text = re.sub(r"[-‐‑‒–—_/]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify_person_name(value: object, fallback: str = "person") -> str:
    normalized = normalize_name(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or fallback


def _active_value(value: object) -> bool:
    text = _clean_text(value).casefold()
    return text not in {"0", "false", "nei", "no", "n", "inactive", "inaktiv"}


def _active_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    if "active" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["active"].map(_active_value)


def _active_registry_mask(registry: pd.DataFrame) -> pd.Series:
    if registry.empty:
        return pd.Series(dtype=bool)
    status = registry.get("status", pd.Series("", index=registry.index)).fillna("").astype(str).str.casefold()
    return ~status.isin({"inactive", "inaktiv", "deleted", "slettet", "merged"})


def _with_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in columns:
        if column not in working.columns:
            working[column] = ""
    ordered_columns = columns + [column for column in working.columns if column not in columns]
    return working[ordered_columns].fillna("")


def _prepare_aliases(aliases: pd.DataFrame) -> pd.DataFrame:
    """Normalize alias keys so matching and integrity reports see the same facts."""

    working = _with_columns(aliases, ALIAS_COLUMNS)
    for index, row in working.iterrows():
        alias = clean_display_text(row.get("alias"))
        if alias:
            working.at[index, "alias"] = alias
        working.at[index, "normalized_alias"] = normalize_name(alias)
        if not _clean_text(row.get("active")):
            working.at[index, "active"] = "true"
    return working


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, dtype=str).fillna("")
    for column in df.columns:
        df[column] = df[column].map(lambda value: repair_mojibake(value) if isinstance(value, str) else value)
    return _with_columns(df, columns)


def _write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _with_columns(df, columns).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


FileWrite = tuple[Path, Callable[[Path], None]]


def _write_files_atomically(file_writes: list[FileWrite]) -> None:
    """Stage files across directories and roll back if any replacement fails."""

    if not file_writes:
        return
    destinations = [path.resolve() for path, _ in file_writes]
    if len(destinations) != len(set(destinations)):
        raise ValueError("Atomic file bundle contains duplicate destinations")
    transaction_id = uuid.uuid4().hex
    staged: list[tuple[Path, Path, Path | None]] = []
    committed: list[tuple[Path, Path | None]] = []
    temporary_paths: set[Path] = set()
    retained_backup_paths: set[Path] = set()
    try:
        for index, (destination, writer) in enumerate(file_writes):
            parent_dir = destination.parent.resolve()
            parent_dir.mkdir(parents=True, exist_ok=True)
            staged_path = parent_dir / f".{destination.name}.{transaction_id}.{index:02d}.tmp"
            temporary_paths.add(staged_path)
            writer(staged_path)
            backup_path: Path | None = None
            if destination.exists():
                backup_path = parent_dir / f".{destination.name}.{transaction_id}.{index:02d}.bak"
                temporary_paths.add(backup_path)
                shutil.copy2(destination, backup_path)
            staged.append((staged_path, destination, backup_path))

        for staged_path, destination, backup_path in staged:
            os.replace(staged_path, destination)
            committed.append((destination, backup_path))
    except BaseException as commit_error:
        rollback_failures: list[str] = []
        for destination, backup_path in reversed(committed):
            try:
                if backup_path is not None and backup_path.exists():
                    os.replace(backup_path, destination)
                elif destination.exists():
                    destination.unlink()
            except BaseException as rollback_error:
                if backup_path is not None and backup_path.exists():
                    retained_backup_paths.add(backup_path)
                rollback_failures.append(f"{destination}: {rollback_error}")
        if rollback_failures:
            retained = ", ".join(str(path) for path in sorted(retained_backup_paths)) or "none"
            details = "; ".join(rollback_failures)
            raise RuntimeError(
                f"Atomic file commit failed ({commit_error}); rollback incomplete: {details}. "
                f"Retained backups: {retained}"
            ) from commit_error
        raise
    finally:
        for temporary_path in temporary_paths:
            if temporary_path in retained_backup_paths:
                continue
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    # Preserve the original transaction error; a process-level
                    # file lock can be cleaned after that handle is released.
                    pass


def _csv_file_writes(entries: list[tuple[pd.DataFrame, Path, list[str]]]) -> list[FileWrite]:
    file_writes: list[FileWrite] = []
    for frame, destination, columns in entries:
        def write_csv_file(
            staged_path: Path,
            staged_frame: pd.DataFrame = frame,
            staged_columns: list[str] = columns,
        ) -> None:
            _write_csv(staged_frame, staged_path, staged_columns)

        file_writes.append((destination, write_csv_file))
    return file_writes


def _write_csv_bundle_atomically(entries: list[tuple[pd.DataFrame, Path, list[str]]]) -> None:
    _write_files_atomically(_csv_file_writes(entries))


def ensure_identity_files(identity_dir: Path | None = None) -> IdentityPaths:
    return ensure_identity_files_from_seed(identity_dir)


def _copy_canonical_identity_seed(seed_dir: Path, paths: IdentityPaths) -> bool:
    seed_paths = _identity_paths(seed_dir)
    seed_registry = load_person_registry(seed_paths.registry)
    if seed_registry.empty:
        return False

    entries = []
    for source, destination, columns in (
        (seed_paths.registry, paths.registry, REGISTRY_COLUMNS),
        (seed_paths.aliases, paths.aliases, ALIAS_COLUMNS),
        (seed_paths.slug_history, paths.slug_history, SLUG_HISTORY_COLUMNS),
        (seed_paths.result_overrides, paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
        (seed_paths.match_decisions, paths.match_decisions, MATCH_DECISION_COLUMNS),
    ):
        entries.append((_read_csv(source, columns), destination, columns))
    _write_csv_bundle_atomically(entries)
    return True


def _reconcile_registry_from_seed(local_registry: pd.DataFrame, seed_registry: pd.DataFrame) -> pd.DataFrame:
    """Merge portable identity facts into a non-empty private registry.

    The versioned seed is authoritative for portable profile facts. Merges are
    monotonic so an older active seed can never resurrect a locally merged
    profile. Private timestamps and notes remain local.
    """

    local = _with_columns(local_registry, REGISTRY_COLUMNS)
    seed = _with_columns(seed_registry, REGISTRY_COLUMNS)
    if seed.empty:
        return local

    for _, seed_row in seed.iterrows():
        person_id = _clean_text(seed_row.get("person_id"))
        if not person_id:
            continue
        matches = local.index[local["person_id"].eq(person_id)].tolist()
        if not matches:
            local = pd.concat([local, pd.DataFrame([seed_row.to_dict()])], ignore_index=True)
            continue

        index = matches[0]
        local_status = _clean_text(local.at[index, "status"]).casefold()
        seed_status = _clean_text(seed_row.get("status")).casefold()
        local_target = _clean_text(local.at[index, "merged_into_person_id"])
        seed_target = _clean_text(seed_row.get("merged_into_person_id"))
        if local_status == "merged" and seed_status == "merged" and local_target and seed_target and local_target != seed_target:
            raise RuntimeError(f"Conflicting merge targets for {person_id}: {local_target} vs {seed_target}")

        for column in ("display_name", "normalized_name", "profile_slug"):
            seed_value = _clean_text(seed_row.get(column))
            if seed_value:
                local.at[index, column] = seed_value

        if seed_status == "merged" and seed_target:
            local.at[index, "status"] = "merged"
            local.at[index, "merged_into_person_id"] = seed_target
        elif local_status != "merged":
            if seed_status:
                local.at[index, "status"] = seed_status
            local.at[index, "merged_into_person_id"] = ""

    return _with_columns(local, REGISTRY_COLUMNS)


def _append_missing_seed_rows(
    local_df: pd.DataFrame,
    seed_df: pd.DataFrame,
    columns: list[str],
    key_columns: list[str],
) -> pd.DataFrame:
    local = _with_columns(local_df, columns)
    seed = _with_columns(seed_df, columns)
    if seed.empty:
        return local

    existing = {
        tuple(_clean_text(row.get(column)) for column in key_columns)
        for _, row in local.iterrows()
    }
    additions: list[dict[str, object]] = []
    for _, row in seed.iterrows():
        key = tuple(_clean_text(row.get(column)) for column in key_columns)
        if not any(key) or key in existing:
            continue
        additions.append(row.to_dict())
        existing.add(key)
    if additions:
        local = pd.concat([local, pd.DataFrame(additions)], ignore_index=True)
    return _with_columns(local, columns)


def _replace_seed_groups(
    local_df: pd.DataFrame,
    seed_df: pd.DataFrame,
    columns: list[str],
    group_column: str,
    preserve_key_columns: list[str] | None = None,
    preserve_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Replace seed-owned groups while keeping local-only facts and private fields."""

    local = _with_columns(local_df, columns)
    seed = _with_columns(seed_df, columns)
    if seed.empty:
        return local

    seed_groups = {_clean_text(value) for value in seed[group_column] if _clean_text(value)}
    preserved = local[~local[group_column].map(_clean_text).isin(seed_groups)].copy()

    fields_to_preserve = [column for column in (preserve_columns or []) if column in columns]
    if preserve_key_columns and fields_to_preserve:
        local_private_values = {
            tuple(_clean_text(row.get(column)) for column in preserve_key_columns): {
                column: _clean_text(row.get(column)) for column in fields_to_preserve
            }
            for _, row in local.iterrows()
        }
        for index, row in seed.iterrows():
            key = tuple(_clean_text(row.get(column)) for column in preserve_key_columns)
            private_values = local_private_values.get(key, {})
            for column in fields_to_preserve:
                if not _clean_text(seed.at[index, column]) and private_values.get(column):
                    seed.at[index, column] = private_values[column]

    return _with_columns(pd.concat([preserved, seed], ignore_index=True), columns)


def _timestamp_value(value: object) -> float:
    text = _clean_text(value)
    if not text:
        return float("-inf")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _reconcile_match_decisions(local_df: pd.DataFrame, seed_df: pd.DataFrame) -> pd.DataFrame:
    """Reconcile portable decisions without discarding a newer local review."""

    local = _with_columns(local_df, MATCH_DECISION_COLUMNS)
    seed = _with_columns(seed_df, MATCH_DECISION_COLUMNS)
    if seed.empty:
        return local

    portable = ["decision", "primary_person_id", "secondary_person_id", "preferred_display_name"]
    for _, seed_row in seed.iterrows():
        candidate_id = _clean_text(seed_row.get("candidate_id"))
        if not candidate_id:
            continue
        matches = local.index[local["candidate_id"].eq(candidate_id)].tolist()
        if not matches:
            local = pd.concat([local, pd.DataFrame([seed_row.to_dict()])], ignore_index=True)
            continue

        index = matches[-1]
        local_values = tuple(_clean_text(local.at[index, column]) for column in portable)
        seed_values = tuple(_clean_text(seed_row.get(column)) for column in portable)
        local_applied = _clean_text(local.at[index, "applied_at"])
        seed_applied = _clean_text(seed_row.get("applied_at"))

        if local_values == seed_values:
            for column in ("reviewed_at", "applied_at"):
                if not _clean_text(local.at[index, column]) and _clean_text(seed_row.get(column)):
                    local.at[index, column] = seed_row.get(column)
            continue

        if seed_applied:
            if local_applied:
                raise RuntimeError(f"Conflicting applied person-match decision for {candidate_id}")
            private_notes = _clean_text(local.at[index, "notes"])
            for column in portable + ["reviewed_at", "applied_at"]:
                local.at[index, column] = seed_row.get(column)
            if private_notes:
                local.at[index, "notes"] = private_notes
            continue

        local_reviewed_value = _timestamp_value(local.at[index, "reviewed_at"])
        seed_reviewed_value = _timestamp_value(seed_row.get("reviewed_at"))
        if local_applied or local_reviewed_value > seed_reviewed_value:
            continue
        if seed_reviewed_value > local_reviewed_value:
            private_notes = _clean_text(local.at[index, "notes"])
            for column in portable + ["reviewed_at", "applied_at"]:
                local.at[index, column] = seed_row.get(column)
            if private_notes:
                local.at[index, "notes"] = private_notes
            continue

        raise RuntimeError(
            f"Conflicting person-match decision for {candidate_id}; update reviewed_at on the intended row"
        )

    return _with_columns(local, MATCH_DECISION_COLUMNS)


def _reconcile_or_validate_person_drafts(
    drafts: pd.DataFrame,
    identity: IdentityData,
    promoted_person_ids: set[str] | frozenset[str] | None = None,
) -> pd.DataFrame:
    """Remove promoted reservations and reject IDs reused for a different person."""

    working = _with_columns(drafts, DRAFT_COLUMNS)
    if working.empty:
        return working

    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    aliases = _prepare_aliases(identity.aliases)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    persisted_ids = {_clean_text(value) for value in registry["person_id"] if _clean_text(value)}
    overlapping_ids = sorted(
        {_clean_text(value) for value in working["person_id"] if _clean_text(value)} & persisted_ids
    )
    explicitly_promoted_ids = {
        _clean_text(value) for value in (promoted_person_ids or set()) if _clean_text(value)
    }

    for person_id in overlapping_ids:
        if person_id not in explicitly_promoted_ids:
            raise ValueError(
                f"Draft person_id collision for {person_id}: the persisted profile was not staged by this build"
            )
        draft_rows = working[working["person_id"].eq(person_id)]
        registry_row = registry[registry["person_id"].eq(person_id)].iloc[0]
        resolved_person_id = _resolve_person_id(person_id, registry)

        draft_names = {
            _clean_text(value)
            for value in draft_rows["normalized_name"]
            if _clean_text(value)
        }
        draft_names.update(
            normalize_name(value)
            for value in draft_rows["display_name"]
            if normalize_name(value)
        )
        persisted_names = {
            _clean_text(registry_row.get("normalized_name")) or normalize_name(registry_row.get("display_name"))
        }
        for _, alias_row in aliases[_active_mask(aliases)].iterrows():
            if _resolve_person_id(_clean_text(alias_row.get("person_id")), registry) == resolved_person_id:
                normalized_alias = _clean_text(alias_row.get("normalized_alias"))
                if normalized_alias:
                    persisted_names.add(normalized_alias)
        if not draft_names or draft_names.isdisjoint(persisted_names):
            raise ValueError(
                f"Draft person_id collision for {person_id}: reserved names do not match the persisted profile"
            )

        draft_external_keys = {
            (_clean_text(row.get("external_source")).casefold(), _clean_text(row.get("external_id")))
            for _, row in draft_rows.iterrows()
            if _clean_text(row.get("external_source")) and _clean_text(row.get("external_id"))
        }
        persisted_external_keys = {
            (_clean_text(row.get("source")).casefold(), _clean_text(row.get("external_id")))
            for _, row in external_ids[_active_mask(external_ids)].iterrows()
            if _resolve_person_id(_clean_text(row.get("person_id")), registry) == resolved_person_id
        }
        missing_external_keys = draft_external_keys - persisted_external_keys
        if missing_external_keys:
            details = ", ".join(f"{source}:{external_id}" for source, external_id in sorted(missing_external_keys))
            raise ValueError(
                f"Draft person_id collision for {person_id}: reserved external IDs do not match ({details})"
            )

    return working[~working["person_id"].isin(overlapping_ids)].copy()


def _reconcile_private_store_from_seed(seed_dir: Path, paths: IdentityPaths) -> None:
    seed_paths = _identity_paths(seed_dir)
    seed_registry = load_person_registry(seed_paths.registry)
    if seed_registry.empty:
        return

    registry = _reconcile_registry_from_seed(load_person_registry(paths.registry), seed_registry)
    aliases = _replace_seed_groups(
        load_aliases(paths.aliases),
        load_aliases(seed_paths.aliases),
        ALIAS_COLUMNS,
        "normalized_alias",
        ["person_id", "normalized_alias"],
        ["notes"],
    )
    slug_history = _replace_seed_groups(
        load_slug_history(paths.slug_history),
        load_slug_history(seed_paths.slug_history),
        SLUG_HISTORY_COLUMNS,
        "profile_slug",
    )
    result_overrides = _replace_seed_groups(
        load_result_person_overrides(paths.result_overrides),
        load_result_person_overrides(seed_paths.result_overrides),
        RESULT_OVERRIDE_COLUMNS,
        "result_id",
        ["result_id", "person_id"],
        ["reason", "notes"],
    )
    match_decisions = _reconcile_match_decisions(
        load_match_decisions(paths.match_decisions),
        load_match_decisions(seed_paths.match_decisions),
    )

    reconciled_identity = IdentityData(
        registry=registry,
        aliases=aliases,
        external_ids=load_external_ids(paths.external_ids),
        slug_history=slug_history,
        result_overrides=result_overrides,
        match_decisions=match_decisions,
    )
    drafts = _reconcile_or_validate_person_drafts(load_person_drafts(paths.drafts), reconciled_identity)
    validate_identity_graph(
        reconciled_identity,
        allowed_unpersisted_person_ids={
            _clean_text(value) for value in drafts["person_id"] if _clean_text(value)
        },
    )

    _write_csv_bundle_atomically(
        [
            (registry, paths.registry, REGISTRY_COLUMNS),
            (aliases, paths.aliases, ALIAS_COLUMNS),
            (slug_history, paths.slug_history, SLUG_HISTORY_COLUMNS),
            (result_overrides, paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
            (match_decisions, paths.match_decisions, MATCH_DECISION_COLUMNS),
            (drafts, paths.drafts, DRAFT_COLUMNS),
        ]
    )


def ensure_identity_files_from_seed(
    identity_dir: Path | None = None,
    canonical_seed_dir: Path | None = None,
) -> IdentityPaths:
    paths = _identity_paths(identity_dir)
    paths.identity_dir.mkdir(parents=True, exist_ok=True)

    default_store = identity_dir is None
    resolved_seed_dir = (
        Path(canonical_seed_dir)
        if canonical_seed_dir is not None
        else (CANONICAL_PERSON_IDENTITY_DIR if default_store else None)
    )
    existing_registry = load_person_registry(paths.registry)
    if existing_registry.empty and resolved_seed_dir is not None:
        if not _copy_canonical_identity_seed(resolved_seed_dir, paths):
            raise RuntimeError(
                "Person identity store is empty and the canonical identity seed is missing or empty: "
                f"{resolved_seed_dir}"
            )
    elif not existing_registry.empty and resolved_seed_dir is not None:
        _reconcile_private_store_from_seed(resolved_seed_dir, paths)

    for path, columns in (
        (paths.registry, REGISTRY_COLUMNS),
        (paths.aliases, ALIAS_COLUMNS),
        (paths.external_ids, EXTERNAL_ID_COLUMNS),
        (paths.slug_history, SLUG_HISTORY_COLUMNS),
        (paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
        (paths.match_decisions, MATCH_DECISION_COLUMNS),
        (paths.drafts, DRAFT_COLUMNS),
    ):
        if not path.exists():
            _write_csv(pd.DataFrame(columns=columns), path, columns)
    return paths


def _canonical_identity_seed_entries(
    identity: IdentityData,
    canonical_seed_dir: Path | None = None,
) -> tuple[Path, list[tuple[pd.DataFrame, Path, list[str]]]]:
    seed_dir = Path(canonical_seed_dir or CANONICAL_PERSON_IDENTITY_DIR)
    seed_paths = _identity_paths(seed_dir)

    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    registry["created_at"] = ""
    registry["updated_at"] = ""
    registry["notes"] = ""

    aliases = _with_columns(identity.aliases, ALIAS_COLUMNS)
    aliases["notes"] = ""

    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)
    result_overrides = _with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS)
    result_overrides["reason"] = ""
    result_overrides["notes"] = ""
    match_decisions = _with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS)
    match_decisions["notes"] = ""

    entries = [
        (registry, seed_paths.registry, REGISTRY_COLUMNS),
        (aliases, seed_paths.aliases, ALIAS_COLUMNS),
        (slug_history, seed_paths.slug_history, SLUG_HISTORY_COLUMNS),
        (result_overrides, seed_paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
        (match_decisions, seed_paths.match_decisions, MATCH_DECISION_COLUMNS),
    ]
    return seed_dir, entries


def write_canonical_identity_seed(
    identity: IdentityData,
    canonical_seed_dir: Path | None = None,
) -> Path:
    seed_dir, entries = _canonical_identity_seed_entries(identity, canonical_seed_dir)
    _write_csv_bundle_atomically(entries)
    return seed_dir


def persist_identity_data(
    identity: IdentityData,
    identity_dir: Path | None = None,
    canonical_seed_dir: Path | None = None,
    additional_file_writes: list[FileWrite] | None = None,
) -> Path:
    """Persist a validated identity graph and its privacy-safe canonical seed."""

    prepared_identity = IdentityData(
        registry=_with_columns(identity.registry, REGISTRY_COLUMNS),
        aliases=_prepare_aliases(identity.aliases),
        external_ids=_with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS),
        slug_history=_with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS),
        result_overrides=_with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS),
        match_decisions=_with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS),
        provisional_person_ids=frozenset(identity.provisional_person_ids),
    )
    validate_identity_graph(prepared_identity)
    validate_identity_reports(build_identity_reports(pd.DataFrame(), prepared_identity))
    paths = _identity_paths(identity_dir)
    paths.identity_dir.mkdir(parents=True, exist_ok=True)
    drafts = _reconcile_or_validate_person_drafts(
        load_person_drafts(paths.drafts),
        prepared_identity,
        prepared_identity.provisional_person_ids,
    )

    entries = [
        (prepared_identity.registry, paths.registry, REGISTRY_COLUMNS),
        (prepared_identity.aliases, paths.aliases, ALIAS_COLUMNS),
        (prepared_identity.external_ids, paths.external_ids, EXTERNAL_ID_COLUMNS),
        (prepared_identity.slug_history, paths.slug_history, SLUG_HISTORY_COLUMNS),
        (prepared_identity.result_overrides, paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
        (prepared_identity.match_decisions, paths.match_decisions, MATCH_DECISION_COLUMNS),
        (drafts, paths.drafts, DRAFT_COLUMNS),
    ]
    if identity_dir is None or canonical_seed_dir is not None:
        _, seed_entries = _canonical_identity_seed_entries(prepared_identity, canonical_seed_dir)
        entries.extend(seed_entries)
    file_writes = _csv_file_writes(entries)
    file_writes.extend(additional_file_writes or [])
    _write_files_atomically(file_writes)
    return paths.identity_dir


def load_person_registry(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_REGISTRY_FILE, REGISTRY_COLUMNS)


def load_aliases(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_ALIASES_FILE, ALIAS_COLUMNS)


def load_external_ids(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_EXTERNAL_IDS_FILE, EXTERNAL_ID_COLUMNS)


def load_slug_history(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_SLUG_HISTORY_FILE, SLUG_HISTORY_COLUMNS)


def load_result_person_overrides(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or RESULT_PERSON_OVERRIDES_FILE, RESULT_OVERRIDE_COLUMNS)


def load_match_decisions(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_MATCH_DECISIONS_FILE, MATCH_DECISION_COLUMNS)


def load_person_drafts(path: Path | None = None) -> pd.DataFrame:
    return _read_csv(path or PERSON_DRAFTS_FILE, DRAFT_COLUMNS)


def load_identity_data(identity_dir: Path | None = None) -> IdentityData:
    paths = _identity_paths(identity_dir)
    return IdentityData(
        registry=load_person_registry(paths.registry),
        aliases=load_aliases(paths.aliases),
        external_ids=load_external_ids(paths.external_ids),
        slug_history=load_slug_history(paths.slug_history),
        result_overrides=load_result_person_overrides(paths.result_overrides),
        match_decisions=load_match_decisions(paths.match_decisions),
    )


IDENTITY_GRAPH_ERROR_COLUMNS = ["record_type", "record_key", "person_id", "target_person_id", "issue"]


def find_identity_graph_errors(
    identity: IdentityData,
    *,
    allowed_unpersisted_person_ids: set[str] | None = None,
    include_pending_match_decisions: bool = True,
) -> pd.DataFrame:
    """Return broken foreign keys, duplicate IDs, and invalid merge chains."""

    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    registry_ids = [_clean_text(value) for value in registry["person_id"] if _clean_text(value)]
    known_ids = set(registry_ids)
    allowed_pending_ids = {
        _clean_text(value) for value in (allowed_unpersisted_person_ids or set()) if _clean_text(value)
    }
    rows: list[dict[str, str]] = []

    for person_id, count in Counter(registry_ids).items():
        if count > 1:
            rows.append(
                {
                    "record_type": "registry",
                    "record_key": person_id,
                    "person_id": person_id,
                    "target_person_id": "",
                    "issue": f"duplicate person_id ({count} rows)",
                }
            )

    merge_targets: dict[str, str] = {}
    for _, row in registry.iterrows():
        person_id = _clean_text(row.get("person_id"))
        status = _clean_text(row.get("status")).casefold()
        target = _clean_text(row.get("merged_into_person_id"))
        if status != "merged":
            continue
        if not target:
            rows.append(
                {
                    "record_type": "registry",
                    "record_key": person_id,
                    "person_id": person_id,
                    "target_person_id": "",
                    "issue": "merged profile has no target",
                }
            )
            continue
        merge_targets[person_id] = target
        if target not in known_ids:
            rows.append(
                {
                    "record_type": "registry",
                    "record_key": person_id,
                    "person_id": person_id,
                    "target_person_id": target,
                    "issue": "merge target is missing from registry",
                }
            )

    seen_cycles: set[tuple[str, ...]] = set()
    for start in merge_targets:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in merge_targets:
            if current in positions:
                cycle = path[positions[current] :]
                normalized_cycle = tuple(sorted(cycle))
                if normalized_cycle not in seen_cycles:
                    seen_cycles.add(normalized_cycle)
                    rows.append(
                        {
                            "record_type": "registry",
                            "record_key": " -> ".join(cycle + [current]),
                            "person_id": current,
                            "target_person_id": merge_targets.get(current, ""),
                            "issue": "merge cycle",
                        }
                    )
                break
            positions[current] = len(path)
            path.append(current)
            current = merge_targets[current]

    reference_tables = (
        ("alias", _with_columns(identity.aliases, ALIAS_COLUMNS), "alias"),
        ("external_id", _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS), "external_id"),
        ("slug_history", _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS), "profile_slug"),
        ("result_override", _with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS), "result_id"),
    )
    for record_type, frame, key_column in reference_tables:
        for _, row in frame.iterrows():
            person_id = _clean_text(row.get("person_id"))
            record_key = _clean_text(row.get(key_column))
            if not person_id or person_id not in known_ids:
                rows.append(
                    {
                        "record_type": record_type,
                        "record_key": record_key,
                        "person_id": person_id,
                        "target_person_id": "",
                        "issue": "person_id is missing from registry",
                    }
                )

    decisions = _with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS)
    candidate_ids = [_clean_text(value) for value in decisions["candidate_id"] if _clean_text(value)]
    for candidate_id, count in Counter(candidate_ids).items():
        if count > 1:
            rows.append(
                {
                    "record_type": "match_decision",
                    "record_key": candidate_id,
                    "person_id": "",
                    "target_person_id": "",
                    "issue": f"duplicate candidate_id ({count} rows)",
                }
            )
    for _, row in decisions.iterrows():
        candidate_id = _clean_text(row.get("candidate_id"))
        applied_at = _clean_text(row.get("applied_at"))
        decision = _clean_text(row.get("decision")).casefold()
        validate_decision = bool(applied_at) or include_pending_match_decisions
        if not validate_decision:
            continue

        primary_person_id = _clean_text(row.get("primary_person_id"))
        secondary_person_id = _clean_text(row.get("secondary_person_id"))
        if decision and not candidate_id.startswith("pmc-manual-"):
            if not primary_person_id or not secondary_person_id:
                rows.append(
                    {
                        "record_type": "match_decision",
                        "record_key": candidate_id,
                        "person_id": primary_person_id,
                        "target_person_id": secondary_person_id,
                        "issue": "candidate decision requires both person IDs",
                    }
                )
            else:
                expected_candidate_id = candidate_id_for_people(primary_person_id, secondary_person_id)
                if candidate_id != expected_candidate_id:
                    rows.append(
                        {
                            "record_type": "match_decision",
                            "record_key": candidate_id,
                            "person_id": primary_person_id,
                            "target_person_id": secondary_person_id,
                            "issue": f"candidate_id does not match person pair (expected {expected_candidate_id})",
                        }
                    )

        valid_reference_ids = known_ids if applied_at else known_ids | allowed_pending_ids
        for column in ("primary_person_id", "secondary_person_id"):
            person_id = _clean_text(row.get(column))
            if person_id and person_id not in valid_reference_ids:
                rows.append(
                    {
                        "record_type": "match_decision",
                        "record_key": candidate_id,
                        "person_id": person_id,
                        "target_person_id": "",
                        "issue": f"{column} is missing from registry",
                    }
                )

    return pd.DataFrame(rows, columns=IDENTITY_GRAPH_ERROR_COLUMNS)


def validate_identity_graph(
    identity: IdentityData,
    *,
    allowed_unpersisted_person_ids: set[str] | None = None,
    include_pending_match_decisions: bool = True,
) -> None:
    errors = find_identity_graph_errors(
        identity,
        allowed_unpersisted_person_ids=allowed_unpersisted_person_ids,
        include_pending_match_decisions=include_pending_match_decisions,
    )
    if not errors.empty:
        preview = "; ".join(
            f"{row.record_type}:{row.record_key} ({row.issue})"
            for row in errors.head(5).itertuples(index=False)
        )
        raise ValueError(f"Invalid person identity graph: {preview}")


def _row_get(row: Any, key: str) -> object:
    if isinstance(row, pd.Series):
        return row.get(key, "")
    if isinstance(row, dict):
        return row.get(key, "")
    return getattr(row, key, "")


def build_result_id(row: pd.Series | dict[str, object]) -> str:
    date_value = _row_get(row, "published_date_iso") or _row_get(row, "published_date")
    time_value = _row_get(row, "result_time_normalized") or _row_get(row, "result_time_raw")
    parts = [
        _clean_text(date_value),
        _clean_text(_row_get(row, "event_label") or _row_get(row, "event_name")),
        _clean_text(_row_get(row, "distance")),
        normalize_name(_row_get(row, "athlete_name")),
        _clean_text(time_value),
        _clean_text(_row_get(row, "place") or _row_get(row, "position")),
        _clean_text(_row_get(row, "class_name") or _row_get(row, "category")),
        _clean_text(_row_get(row, "class_place")),
    ]
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"res-{digest}"


def assign_result_ids(df: pd.DataFrame) -> pd.Series:
    seen: dict[str, int] = {}
    result_ids: list[str] = []
    for _, row in df.iterrows():
        base_id = build_result_id(row)
        seen[base_id] = seen.get(base_id, 0) + 1
        result_ids.append(base_id if seen[base_id] == 1 else f"{base_id}-{seen[base_id]}")
    return pd.Series(result_ids, index=df.index)


def _resolve_person_id(person_id: str, registry: pd.DataFrame) -> str:
    current = _clean_text(person_id)
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        match = registry[registry["person_id"].eq(current)]
        if match.empty:
            return current
        row = match.iloc[0]
        status = _clean_text(row.get("status")).casefold()
        merged_into = _clean_text(row.get("merged_into_person_id"))
        if status == "merged" and merged_into:
            current = merged_into
            continue
        return current
    return current


def _add_to_index(index: dict[Any, set[str]], key: Any, person_id: str) -> None:
    if not key or not person_id:
        return
    index.setdefault(key, set()).add(person_id)


def build_identity_indexes(identity: IdentityData) -> IdentityIndexes:
    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    aliases = _prepare_aliases(identity.aliases)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    overrides = _with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS)

    registry_by_name: dict[str, set[str]] = {}
    aliases_by_name: dict[str, set[str]] = {}
    external_index: dict[tuple[str, str], set[str]] = {}
    external_ids_by_person_source: dict[tuple[str, str], set[str]] = {}
    override_index: dict[str, set[str]] = {}
    slug_by_person_id: dict[str, str] = {}

    for _, row in registry[_active_registry_mask(registry)].iterrows():
        person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        normalized_name = _clean_text(row.get("normalized_name")) or normalize_name(row.get("display_name"))
        _add_to_index(registry_by_name, normalized_name, person_id)
        slug = _clean_text(row.get("profile_slug"))
        if person_id and slug and person_id not in slug_by_person_id:
            slug_by_person_id[person_id] = slug

    for _, row in aliases[_active_mask(aliases)].iterrows():
        person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        normalized_alias = _clean_text(row.get("normalized_alias")) or normalize_name(row.get("alias"))
        _add_to_index(aliases_by_name, normalized_alias, person_id)

    for _, row in external_ids[_active_mask(external_ids)].iterrows():
        person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        source = _clean_text(row.get("source")).casefold()
        external_id = _clean_text(row.get("external_id"))
        _add_to_index(external_index, (source, external_id), person_id)
        _add_to_index(external_ids_by_person_source, (person_id, source), external_id)

    for _, row in overrides[_active_mask(overrides)].iterrows():
        person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        result_id = _clean_text(row.get("result_id"))
        _add_to_index(override_index, result_id, person_id)

    return IdentityIndexes(
        registry_by_normalized_name=registry_by_name,
        aliases_by_normalized_name=aliases_by_name,
        external_ids=external_index,
        external_ids_by_person_source=external_ids_by_person_source,
        result_overrides=override_index,
        slug_by_person_id=slug_by_person_id,
    )


def _single_person_id(candidates: set[str] | None) -> str:
    if not candidates or len(candidates) != 1:
        return ""
    return next(iter(candidates))


def normalize_source_system(value: object) -> str:
    normalized = normalize_name(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _result_source_ids_for_row(row: pd.Series | dict[str, object]) -> list[str]:
    values: list[str] = []
    for column in RESULT_SOURCE_ID_COLUMNS:
        value = _clean_text(_row_get(row, column))
        if value and value not in values:
            values.append(value)
    return values


def _result_source_system_for_row(row: pd.Series | dict[str, object]) -> str:
    for column in RESULT_SOURCE_SYSTEM_COLUMNS:
        value = normalize_source_system(_row_get(row, column))
        if value:
            return value
    return ""


def _external_keys_for_row(row: pd.Series | dict[str, object]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for source, columns in EXTERNAL_ID_SOURCE_COLUMNS.items():
        for column in columns:
            value = _clean_text(_row_get(row, column))
            if value:
                keys.append((source, value))

    source_system = _result_source_system_for_row(row)
    if source_system:
        for external_id in _result_source_ids_for_row(row):
            keys.append((f"result_source:{source_system}", external_id))
    return keys


def match_result_to_person(
    row: pd.Series | dict[str, object],
    identity: IdentityData,
    indexes: IdentityIndexes | None = None,
) -> PersonMatch:
    lookup = indexes or build_identity_indexes(identity)

    result_id = _clean_text(_row_get(row, "result_id"))
    override_candidates = lookup.result_overrides.get(result_id)
    if override_candidates:
        person_id = _single_person_id(override_candidates)
        if person_id:
            return PersonMatch(person_id=person_id, method="result_override")
        return PersonMatch(person_id="", method="ambiguous_result_override", needs_review=True)

    result_source_ids = _result_source_ids_for_row(row)
    if result_source_ids and not _result_source_system_for_row(row):
        return PersonMatch(
            person_id="",
            method="unscoped_source_person_id",
            reason="source_person_id requires source_system",
            needs_review=True,
        )

    external_keys = list(dict.fromkeys(_external_keys_for_row(row)))
    incoming_ids_by_source: dict[str, set[str]] = defaultdict(set)
    for source, external_id in external_keys:
        incoming_ids_by_source[source].add(external_id)
    for source, external_ids in incoming_ids_by_source.items():
        if source in SINGLETON_EXTERNAL_ID_SOURCES and len(external_ids) > 1:
            return PersonMatch(
                person_id="",
                method="conflicting_singleton_external_ids",
                reason=f"{source} supplied multiple IDs",
                needs_review=True,
            )

    external_matches: list[tuple[tuple[str, str], str]] = []
    for external_key in external_keys:
        external_candidates = lookup.external_ids.get(external_key)
        if not external_candidates:
            continue
        person_id = _single_person_id(external_candidates)
        if not person_id:
            return PersonMatch(
                person_id="",
                method="ambiguous_external_id",
                reason=f"{external_key[0]}:{external_key[1]}",
                needs_review=True,
            )
        external_matches.append((external_key, person_id))

    external_person_ids = {person_id for _, person_id in external_matches}
    if len(external_person_ids) > 1:
        reason = ", ".join(f"{source}:{external_id}->{person_id}" for (source, external_id), person_id in external_matches)
        return PersonMatch(person_id="", method="conflicting_external_ids", reason=reason, needs_review=True)
    external_person_id = next(iter(external_person_ids), "")

    def singleton_id_conflict(person_id: str) -> tuple[str, set[str], str] | None:
        for source, incoming_id in external_keys:
            if source not in SINGLETON_EXTERNAL_ID_SOURCES:
                continue
            known_ids = lookup.external_ids_by_person_source.get((person_id, source), set())
            if known_ids and incoming_id not in known_ids:
                return source, known_ids, incoming_id
        return None

    if external_person_id:
        conflict = singleton_id_conflict(external_person_id)
        if conflict:
            source, known_ids, incoming_id = conflict
            return PersonMatch(
                person_id="",
                method="conflicting_external_id_cardinality",
                reason=f"{source} already has {', '.join(sorted(known_ids))}; incoming {incoming_id}",
                needs_review=True,
            )

    normalized_name = normalize_name(_row_get(row, "athlete_name"))
    if not normalized_name and external_person_id:
        source = external_matches[0][0][0]
        return PersonMatch(person_id=external_person_id, method=f"external_id:{source}")
    if not normalized_name:
        return PersonMatch(person_id="", method="missing_name", needs_review=True)

    alias_candidates = lookup.aliases_by_normalized_name.get(normalized_name)
    alias_person_id = _single_person_id(alias_candidates)
    if alias_candidates and not alias_person_id:
        return PersonMatch(person_id="", method="ambiguous_alias", reason=normalized_name, needs_review=True)

    registry_candidates = lookup.registry_by_normalized_name.get(normalized_name)
    registry_person_id = _single_person_id(registry_candidates)
    if registry_candidates and not registry_person_id:
        return PersonMatch(person_id="", method="ambiguous_registry_name", reason=normalized_name, needs_review=True)

    name_person_ids = {person_id for person_id in (alias_person_id, registry_person_id) if person_id}
    if len(name_person_ids) > 1:
        reason = f"name={normalized_name}; alias={alias_person_id}; registry={registry_person_id}"
        return PersonMatch(person_id="", method="conflicting_name_owners", reason=reason, needs_review=True)
    name_person_id = next(iter(name_person_ids), "")

    if external_person_id and name_person_id and external_person_id != name_person_id:
        reason = f"name={normalized_name}->{name_person_id}; external_id->{external_person_id}"
        return PersonMatch(person_id="", method="conflicting_identity_signals", reason=reason, needs_review=True)
    if name_person_id and not external_person_id:
        conflict = singleton_id_conflict(name_person_id)
        if conflict:
            source, known_ids, incoming_id = conflict
            return PersonMatch(
                person_id="",
                method="conflicting_external_id_cardinality",
                reason=f"{source} already has {', '.join(sorted(known_ids))}; incoming {incoming_id}",
                needs_review=True,
            )
    if external_person_id:
        source = external_matches[0][0][0]
        return PersonMatch(person_id=external_person_id, method=f"external_id:{source}")
    if alias_person_id:
        return PersonMatch(person_id=alias_person_id, method="alias")
    if registry_person_id:
        return PersonMatch(person_id=registry_person_id, method="registry_name")

    return PersonMatch(person_id="", method="new_person")


def _person_number(person_id: str) -> int:
    match = re.search(r"(\d+)$", _clean_text(person_id))
    return int(match.group(1)) if match else 0


def _next_person_id(registry: pd.DataFrame) -> str:
    existing_numbers = [_person_number(person_id) for person_id in registry.get("person_id", [])]
    next_number = max(existing_numbers, default=0) + 1
    return f"{PERSON_ID_PREFIX}{next_number:06d}"


def _allocate_unique_slug(display_name: str, used_slugs: set[str]) -> str:
    base_slug = slugify_person_name(display_name)
    slug = base_slug
    suffix = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    used_slugs.add(slug)
    return slug


def _prepare_registry(registry: pd.DataFrame, now_text: str) -> pd.DataFrame:
    working = _with_columns(registry, REGISTRY_COLUMNS)
    used_slugs = {
        _clean_text(value)
        for value in working.get("profile_slug", [])
        if _clean_text(value)
    }
    for index, row in working.iterrows():
        display_name = clean_display_text(row.get("display_name"))
        if display_name != _clean_text(row.get("display_name")):
            working.at[index, "display_name"] = display_name
        if not _clean_text(row.get("normalized_name")) and display_name:
            working.at[index, "normalized_name"] = normalize_name(display_name)
        if not _clean_text(row.get("status")):
            working.at[index, "status"] = "active"
        if not _clean_text(row.get("profile_slug")) and display_name:
            working.at[index, "profile_slug"] = _allocate_unique_slug(display_name, used_slugs)
        if not _clean_text(row.get("created_at")):
            working.at[index, "created_at"] = now_text
    return working


def _append_alias_if_missing(aliases: pd.DataFrame, person_id: str, alias: str, source: str) -> pd.DataFrame:
    cleaned_alias = clean_display_text(alias)
    normalized_alias = normalize_name(cleaned_alias)
    if not person_id or not normalized_alias:
        return aliases

    working = _prepare_aliases(aliases)
    exists = (
        working["person_id"].eq(person_id)
        & (
            working["normalized_alias"].eq(normalized_alias)
            | working["alias"].map(normalize_name).eq(normalized_alias)
        )
    ).any()
    if exists:
        return working

    return pd.concat(
        [
            working,
            pd.DataFrame(
                [
                    {
                        "person_id": person_id,
                        "alias": cleaned_alias,
                        "normalized_alias": normalized_alias,
                        "source": source,
                        "active": "true",
                        "notes": "",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )


def _append_external_id_if_missing(
    external_ids: pd.DataFrame,
    person_id: str,
    source: str,
    external_id: str,
) -> pd.DataFrame:
    cleaned_external_id = _clean_text(external_id)
    if not person_id or not source or not cleaned_external_id:
        return external_ids

    working = _with_columns(external_ids, EXTERNAL_ID_COLUMNS)
    same_key = working["source"].str.casefold().eq(source.casefold()) & working["external_id"].eq(cleaned_external_id)
    if same_key.any():
        return working

    return pd.concat(
        [
            working,
            pd.DataFrame(
                [
                    {
                        "person_id": person_id,
                        "source": source,
                        "external_id": cleaned_external_id,
                        "active": "true",
                        "notes": "",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )


def candidate_id_for_people(person_id_1: str, person_id_2: str) -> str:
    person_ids = sorted([_clean_text(person_id_1), _clean_text(person_id_2)])
    digest = hashlib.sha1("|".join(person_ids).encode("utf-8")).hexdigest()[:16]
    return f"pmc-{digest}"


def _tokens_for_name(value: object) -> list[str]:
    return normalize_name(value).split()


def _result_stats_by_person(results_df: pd.DataFrame | None) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    if results_df is None or results_df.empty or "person_id" not in results_df.columns:
        return stats

    for person_id, group in results_df[results_df["person_id"].fillna("").ne("")].groupby("person_id"):
        date_column = "published_date_iso" if "published_date_iso" in group.columns else "published_date"
        dates = [_clean_text(value) for value in group.get(date_column, pd.Series(dtype=str)) if _clean_text(value)]
        stats[_clean_text(person_id)] = {
            "result_count": int(len(group)),
            "latest_result_date": max(dates) if dates else "",
        }
    return stats


def _match_decisions_by_candidate(decisions: pd.DataFrame) -> dict[str, dict[str, str]]:
    if decisions.empty:
        return {}
    working = _with_columns(decisions, MATCH_DECISION_COLUMNS)
    latest: dict[str, dict[str, str]] = {}
    for _, row in working.iterrows():
        candidate_id = _clean_text(row.get("candidate_id"))
        if not candidate_id:
            continue
        latest[candidate_id] = {column: _clean_text(row.get(column)) for column in MATCH_DECISION_COLUMNS}
    return latest


def _classify_name_pair(tokens_1: list[str], tokens_2: list[str], name_1: str, name_2: str) -> dict[str, object] | None:
    if not tokens_1 or not tokens_2:
        return None

    token_set_1 = set(tokens_1)
    token_set_2 = set(tokens_2)
    shared = token_set_1 & token_set_2
    token_overlap = len(shared) / min(len(token_set_1), len(token_set_2))
    sequence_similarity = SequenceMatcher(None, normalize_name(name_1), normalize_name(name_2)).ratio()
    same_first = tokens_1[0] == tokens_2[0]
    same_last = tokens_1[-1] == tokens_2[-1]
    same_first_last = same_first and same_last

    middle_1 = tokens_1[1:-1]
    middle_2 = tokens_2[1:-1]
    initial_variant = False
    if same_first_last and middle_1 and middle_2:
        short_middles, long_middles = (middle_1, middle_2) if len(middle_1) <= len(middle_2) else (middle_2, middle_1)
        for short_middle in short_middles:
            if len(short_middle) == 1 and any(long_middle.startswith(short_middle) for long_middle in long_middles):
                initial_variant = True
                break

    if same_first_last and initial_variant:
        return {
            "confidence": "strong",
            "reason": "same first+last; middle initial matches middle name",
            "sequence_similarity": sequence_similarity,
            "token_overlap": token_overlap,
            "shared_tokens": " ".join(sorted(shared)),
        }
    if same_first_last and token_overlap == 1 and abs(len(token_set_1) - len(token_set_2)) <= 3:
        return {
            "confidence": "strong",
            "reason": "same first+last; one name has extra middle token(s)",
            "sequence_similarity": sequence_similarity,
            "token_overlap": token_overlap,
            "shared_tokens": " ".join(sorted(shared)),
        }
    if token_overlap == 1 and len(shared) >= 2 and (same_first or same_last):
        return {
            "confidence": "medium",
            "reason": "shorter name is token subset",
            "sequence_similarity": sequence_similarity,
            "token_overlap": token_overlap,
            "shared_tokens": " ".join(sorted(shared)),
        }
    if same_first_last and sequence_similarity >= 0.72:
        return {
            "confidence": "medium",
            "reason": "same first+last and similar full name",
            "sequence_similarity": sequence_similarity,
            "token_overlap": token_overlap,
            "shared_tokens": " ".join(sorted(shared)),
        }
    if sequence_similarity >= 0.9:
        return {
            "confidence": "review",
            "reason": "very high string similarity",
            "sequence_similarity": sequence_similarity,
            "token_overlap": token_overlap,
            "shared_tokens": " ".join(sorted(shared)),
        }
    return None


def _suggest_primary_person(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    """Keep the oldest stable ID; display-name choice is a separate decision."""

    left_id = _clean_text(left.get("person_id"))
    right_id = _clean_text(right.get("person_id"))
    left_key = (_person_number(left_id), left_id)
    right_key = (_person_number(right_id), right_id)
    return left if left_key <= right_key else right


def build_person_match_candidates(identity: IdentityData, results_df: pd.DataFrame | None = None) -> pd.DataFrame:
    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    decisions = _with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS)
    decision_by_candidate = _match_decisions_by_candidate(decisions)
    result_stats = _result_stats_by_person(results_df)

    active_people: list[dict[str, object]] = []
    for _, row in registry[_active_registry_mask(registry)].iterrows():
        person_id = _clean_text(row.get("person_id"))
        if not person_id or _resolve_person_id(person_id, registry) != person_id:
            continue
        display_name = clean_display_text(row.get("display_name"))
        tokens = _tokens_for_name(display_name)
        if not display_name or not tokens:
            continue
        stats = result_stats.get(person_id, {})
        active_people.append(
            {
                "person_id": person_id,
                "display_name": display_name,
                "tokens": tokens,
                "result_count": int(stats.get("result_count") or 0),
                "latest_result_date": _clean_text(stats.get("latest_result_date")),
            }
        )

    rows: list[dict[str, object]] = []
    for left_index, left in enumerate(active_people):
        for right in active_people[left_index + 1 :]:
            candidate_id = candidate_id_for_people(str(left["person_id"]), str(right["person_id"]))
            decision = decision_by_candidate.get(candidate_id, {})
            decision_value = _clean_text(decision.get("decision")).casefold()
            applied_at = _clean_text(decision.get("applied_at"))
            if decision_value == "reject" or (decision_value in APPLIED_MATCH_DECISIONS and applied_at):
                continue

            classification = _classify_name_pair(
                list(left["tokens"]),
                list(right["tokens"]),
                str(left["display_name"]),
                str(right["display_name"]),
            )
            if classification is None:
                continue

            suggested_primary = _suggest_primary_person(left, right)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "confidence": classification["confidence"],
                    "suggested_decision": "merge",
                    "suggested_primary_person_id": suggested_primary["person_id"],
                    "suggested_primary_name": suggested_primary["display_name"],
                    "person_id_1": left["person_id"],
                    "display_name_1": left["display_name"],
                    "result_count_1": left["result_count"],
                    "latest_result_date_1": left["latest_result_date"],
                    "person_id_2": right["person_id"],
                    "display_name_2": right["display_name"],
                    "result_count_2": right["result_count"],
                    "latest_result_date_2": right["latest_result_date"],
                    "shared_tokens": classification["shared_tokens"],
                    "reason": classification["reason"],
                    "sequence_similarity": round(float(classification["sequence_similarity"]), 3),
                    "token_overlap": round(float(classification["token_overlap"]), 3),
                    "decision": decision_value,
                    "decision_notes": _clean_text(decision.get("notes")),
                }
            )

    if not rows:
        return pd.DataFrame(columns=MATCH_CANDIDATE_COLUMNS)

    confidence_order = {"strong": 0, "medium": 1, "review": 2}
    candidates = pd.DataFrame(rows)
    candidates["_confidence_order"] = candidates["confidence"].map(confidence_order).fillna(99)
    candidates = candidates.sort_values(
        ["_confidence_order", "token_overlap", "sequence_similarity", "display_name_1", "display_name_2"],
        ascending=[True, False, False, True, True],
    )
    return candidates.drop(columns=["_confidence_order"])[MATCH_CANDIDATE_COLUMNS].reset_index(drop=True)


def find_blocking_person_match_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return candidate pairs that still need action before publication.

    Candidate generation already omits applied merges/alias decisions and
    rejected pairs. A deferred pair is intentionally allowed to remain open;
    blank decisions and decisions that have not yet been applied must block so
    a newly created name variant cannot silently become a public duplicate.
    """

    working = _with_columns(candidates, MATCH_CANDIDATE_COLUMNS)
    if working.empty:
        return working

    decisions = working["decision"].map(lambda value: _clean_text(value).casefold())
    non_blocking = decisions.isin({"defer", "reject"})
    return working.loc[~non_blocking].reset_index(drop=True)


def _append_decision_error(errors: list[dict[str, str]], row: pd.Series, message: str) -> None:
    errors.append(
        {
            "candidate_id": _clean_text(row.get("candidate_id")),
            "decision": _clean_text(row.get("decision")),
            "primary_person_id": _clean_text(row.get("primary_person_id")),
            "secondary_person_id": _clean_text(row.get("secondary_person_id")),
            "error": message,
        }
    )


def _copy_aliases_to_primary(aliases: pd.DataFrame, primary_person_id: str, secondary_person_id: str, registry: pd.DataFrame) -> pd.DataFrame:
    working = _prepare_aliases(aliases)
    for person_id in (primary_person_id, secondary_person_id):
        match = registry[registry["person_id"].eq(person_id)]
        if not match.empty:
            working = _append_alias_if_missing(working, primary_person_id, match.iloc[0].get("display_name"), "manual_match_decision")

    secondary_aliases = working[
        working["person_id"].eq(secondary_person_id) & _active_mask(working)
    ].copy()
    for _, alias_row in secondary_aliases.iterrows():
        working = _append_alias_if_missing(working, primary_person_id, alias_row.get("alias"), "manual_match_decision")
    return working


def _copy_external_ids_to_primary(external_ids: pd.DataFrame, primary_person_id: str, secondary_person_id: str) -> pd.DataFrame:
    working = _with_columns(external_ids, EXTERNAL_ID_COLUMNS)
    secondary_external_ids = working[working["person_id"].eq(secondary_person_id)].copy()
    for index, external_row in secondary_external_ids.iterrows():
        source = _clean_text(external_row.get("source"))
        external_id = _clean_text(external_row.get("external_id"))
        same_primary_key = (
            working["person_id"].eq(primary_person_id)
            & working["source"].str.casefold().eq(source.casefold())
            & working["external_id"].eq(external_id)
        )
        if same_primary_key.any():
            working.at[index, "active"] = "false"
            continue
        working.at[index, "person_id"] = primary_person_id
    return working


def _set_preferred_display_name(
    registry: pd.DataFrame,
    aliases: pd.DataFrame,
    person_id: str,
    preferred_display_name: str,
    now_text: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    preferred = clean_display_text(preferred_display_name)
    if not preferred:
        return registry, aliases

    working_registry = _with_columns(registry, REGISTRY_COLUMNS)
    matches = working_registry.index[working_registry["person_id"].eq(person_id)].tolist()
    if not matches:
        return working_registry, aliases

    index = matches[0]
    old_display_name = clean_display_text(working_registry.at[index, "display_name"])
    working_aliases = _append_alias_if_missing(aliases, person_id, old_display_name, "previous_preferred_name")
    working_aliases = _append_alias_if_missing(working_aliases, person_id, preferred, "manual_preferred_name")
    working_registry.at[index, "display_name"] = preferred
    working_registry.at[index, "normalized_name"] = normalize_name(preferred)
    working_registry.at[index, "updated_at"] = now_text
    return working_registry, working_aliases


def apply_match_decisions_to_identity(
    identity: IdentityData,
    now: datetime | None = None,
) -> tuple[IdentityData, dict[str, object]]:
    """Apply pending decisions to an in-memory graph without persisting partial state."""

    validate_identity_graph(identity, include_pending_match_decisions=False)
    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    aliases = _with_columns(identity.aliases, ALIAS_COLUMNS)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)
    decisions = _with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS)
    now_text = (now or datetime.now().astimezone()).isoformat(timespec="seconds")

    applied_counts = {"merge": 0, "alias_only": 0, "reject": 0, "defer": 0}
    errors: list[dict[str, str]] = []

    for index, row in decisions.iterrows():
        decision = _clean_text(row.get("decision")).casefold()
        if not decision:
            continue
        if decision not in {"merge", "alias_only", "reject", "defer"}:
            _append_decision_error(errors, row, "unknown decision")
            continue
        if decision != "defer" and _clean_text(row.get("applied_at")):
            continue

        candidate_id = _clean_text(row.get("candidate_id"))
        raw_primary_person_id = _clean_text(row.get("primary_person_id"))
        raw_secondary_person_id = _clean_text(row.get("secondary_person_id"))
        if not candidate_id.startswith("pmc-manual-"):
            if not raw_primary_person_id or not raw_secondary_person_id:
                _append_decision_error(errors, row, "candidate decisions require both person IDs")
                continue
            expected_candidate_id = candidate_id_for_people(raw_primary_person_id, raw_secondary_person_id)
            if candidate_id != expected_candidate_id:
                _append_decision_error(
                    errors,
                    row,
                    f"candidate_id does not match person pair (expected {expected_candidate_id})",
                )
                continue

        primary_person_id = raw_primary_person_id
        secondary_person_id = raw_secondary_person_id
        if not primary_person_id or not secondary_person_id:
            _append_decision_error(errors, row, "primary_person_id and secondary_person_id are required")
            continue
        if registry[registry["person_id"].eq(primary_person_id)].empty:
            _append_decision_error(errors, row, "primary_person_id does not exist")
            continue
        if registry[registry["person_id"].eq(secondary_person_id)].empty:
            _append_decision_error(errors, row, "secondary_person_id does not exist")
            continue
        if decision == "defer":
            applied_counts["defer"] += 1
            continue
        if decision == "reject":
            decisions.at[index, "applied_at"] = now_text
            applied_counts["reject"] += 1
            continue

        resolved_primary_person_id = _resolve_person_id(primary_person_id, registry)
        resolved_secondary_person_id = _resolve_person_id(secondary_person_id, registry)
        if resolved_primary_person_id not in set(registry["person_id"]):
            _append_decision_error(errors, row, "resolved primary_person_id does not exist")
            continue
        primary_person_id = resolved_primary_person_id

        if decision == "alias_only" and resolved_secondary_person_id != primary_person_id:
            _append_decision_error(
                errors,
                row,
                "alias_only requires the secondary profile to already resolve to the selected primary",
            )
            continue
        if decision == "merge" and resolved_secondary_person_id != secondary_person_id:
            if resolved_secondary_person_id == primary_person_id:
                aliases = _copy_aliases_to_primary(aliases, primary_person_id, secondary_person_id, registry)
                preferred_display_name = _clean_text(row.get("preferred_display_name"))
                if preferred_display_name:
                    registry, aliases = _set_preferred_display_name(
                        registry,
                        aliases,
                        primary_person_id,
                        preferred_display_name,
                        now_text,
                    )
                if candidate_id.startswith("pmc-manual-"):
                    decisions.at[index, "primary_person_id"] = primary_person_id
                decisions.at[index, "applied_at"] = now_text
                applied_counts[decision] += 1
                continue
            _append_decision_error(
                errors,
                row,
                f"secondary profile already resolves to {resolved_secondary_person_id}",
            )
            continue

        aliases = _copy_aliases_to_primary(aliases, primary_person_id, secondary_person_id, registry)
        if decision == "merge":
            external_ids = _copy_external_ids_to_primary(external_ids, primary_person_id, secondary_person_id)
            secondary_mask = registry["person_id"].eq(secondary_person_id)
            registry.loc[secondary_mask, "status"] = "merged"
            registry.loc[secondary_mask, "merged_into_person_id"] = primary_person_id
            registry.loc[secondary_mask, "updated_at"] = now_text

            primary_slug = _clean_text(registry.loc[registry["person_id"].eq(primary_person_id), "profile_slug"].iloc[0])
            secondary_slug = _clean_text(registry.loc[secondary_mask, "profile_slug"].iloc[0])
            if secondary_slug and primary_slug and secondary_slug != primary_slug:
                active_secondary_slug = (
                    slug_history["person_id"].eq(secondary_person_id)
                    & slug_history["profile_slug"].eq(secondary_slug)
                    & slug_history["active_to"].fillna("").eq("")
                )
                slug_history.loc[active_secondary_slug, "active_to"] = now_text
                slug_history = pd.concat(
                    [
                        slug_history,
                        pd.DataFrame(
                            [
                                {
                                    "person_id": secondary_person_id,
                                    "profile_slug": secondary_slug,
                                    "active_from": "",
                                    "active_to": now_text,
                                    "reason": f"merged_into:{primary_person_id}",
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                ).drop_duplicates(subset=["person_id", "profile_slug", "active_to", "reason"], keep="first")

        preferred_display_name = _clean_text(row.get("preferred_display_name"))
        if preferred_display_name:
            registry, aliases = _set_preferred_display_name(
                registry,
                aliases,
                primary_person_id,
                preferred_display_name,
                now_text,
            )

        if candidate_id.startswith("pmc-manual-"):
            decisions.at[index, "primary_person_id"] = primary_person_id
        decisions.at[index, "applied_at"] = now_text
        applied_counts[decision] += 1

    if errors:
        return (
            identity,
            {
                "applied_counts": {key: 0 for key in applied_counts},
                "error_count": len(errors),
                "errors": errors,
            },
        )

    updated_identity = IdentityData(
        registry=registry,
        aliases=aliases,
        external_ids=external_ids,
        slug_history=slug_history,
        result_overrides=identity.result_overrides,
        match_decisions=decisions,
        provisional_person_ids=identity.provisional_person_ids,
    )
    validate_identity_graph(updated_identity)
    validate_identity_reports(build_identity_reports(pd.DataFrame(), updated_identity))
    return (
        updated_identity,
        {
            "applied_counts": applied_counts,
            "error_count": len(errors),
            "errors": errors,
        },
    )


def apply_match_decisions(identity_dir: Path | None = None, now: datetime | None = None) -> dict[str, object]:
    paths = ensure_identity_files(identity_dir)
    identity = load_identity_data(paths.identity_dir)
    updated_identity, result = apply_match_decisions_to_identity(identity, now)
    if not result["error_count"]:
        persist_identity_data(updated_identity, identity_dir)
    return result


def ensure_new_people_are_appended_without_changing_existing_ids(
    results_df: pd.DataFrame,
    identity_dir: Path | None = None,
    now: datetime | None = None,
    canonical_seed_dir: Path | None = None,
    persist: bool = True,
) -> IdentityData:
    paths = ensure_identity_files_from_seed(identity_dir, canonical_seed_dir)
    now_text = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    identity = load_identity_data(paths.identity_dir)

    registry = _prepare_registry(identity.registry, now_text)
    aliases = _prepare_aliases(identity.aliases)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)
    drafts = load_person_drafts(paths.drafts)

    identity = IdentityData(registry, aliases, external_ids, slug_history, identity.result_overrides, identity.match_decisions)
    drafts = _reconcile_or_validate_person_drafts(drafts, identity)
    indexes = build_identity_indexes(identity)

    parent: dict[str, str] = {}
    row_groups: list[dict[str, object]] = []

    def find(node: str) -> str:
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for row_number, (_, row) in enumerate(results_df.iterrows()):
        match = match_result_to_person(row, identity, indexes)
        if match.person_id or match.needs_review:
            continue
        display_name = clean_display_text(row.get("athlete_name"))
        normalized_name = normalize_name(display_name)
        if not normalized_name:
            continue

        row_node = f"row:{row_number}"
        name_node = f"name:{normalized_name}"
        union(row_node, name_node)
        external_keys = _external_keys_for_row(row)
        for source, external_id in external_keys:
            union(row_node, f"external:{source}:{external_id}")
        row_groups.append(
            {
                "node": row_node,
                "display_name": display_name,
                "normalized_name": normalized_name,
                "external_keys": external_keys,
            }
        )

    used_slugs = {
        _clean_text(slug)
        for slug in pd.concat(
            [
                registry.get("profile_slug", pd.Series(dtype=str)),
                slug_history.get("profile_slug", pd.Series(dtype=str)),
            ],
            ignore_index=True,
        )
        if _clean_text(slug)
    }

    components: dict[str, dict[str, object]] = {}
    for row_group in row_groups:
        root = find(str(row_group["node"]))
        component = components.setdefault(
            root,
            {
                "names": Counter(),
                "normalized_names": set(),
                "external_keys": set(),
            },
        )
        component["names"][str(row_group["display_name"])] += 1
        component["normalized_names"].add(str(row_group["normalized_name"]))
        component["external_keys"].update(row_group["external_keys"])

    def component_display_name(component: dict[str, object]) -> str:
        names = component["names"]
        return sorted(names.items(), key=lambda item: (-item[1], item[0]))[0][0]

    new_registry_rows: list[dict[str, str]] = []
    new_slug_rows: list[dict[str, str]] = []
    sorted_components = sorted(components.values(), key=lambda component: normalize_name(component_display_name(component)))
    for component in sorted_components:
        normalized_names = set(component["normalized_names"])
        external_keys = set(component["external_keys"])
        component_ids_by_source: dict[str, set[str]] = defaultdict(set)
        for external_source, external_id in external_keys:
            component_ids_by_source[external_source].add(external_id)
        conflicting_sources = {
            source: ids
            for source, ids in component_ids_by_source.items()
            if source in SINGLETON_EXTERNAL_ID_SOURCES and len(ids) > 1
        }
        if conflicting_sources:
            details = "; ".join(
                f"{source}={','.join(sorted(ids))}" for source, ids in sorted(conflicting_sources.items())
            )
            raise ValueError(
                f"New person candidate {component_display_name(component)} has conflicting external IDs: {details}"
            )
        has_existing_name = any(
            normalized_name in indexes.registry_by_normalized_name
            or normalized_name in indexes.aliases_by_normalized_name
            for normalized_name in normalized_names
        )
        has_existing_external_id = any(external_key in indexes.external_ids for external_key in external_keys)
        if has_existing_name or has_existing_external_id:
            continue
        display_counter = component["names"]
        display_name = component_display_name(component)
        normalized_name = normalize_name(display_name)
        draft_mask = drafts["normalized_name"].isin(normalized_names)
        draft_sources = drafts["external_source"].map(lambda value: _clean_text(value).casefold())
        for external_source, external_id in external_keys:
            draft_mask |= draft_sources.eq(external_source.casefold()) & drafts["external_id"].eq(external_id)
        draft_person_ids = {
            _clean_text(value) for value in drafts.loc[draft_mask, "person_id"] if _clean_text(value)
        }
        if len(draft_person_ids) > 1:
            raise ValueError(
                f"Conflicting draft person reservations for {display_name}: {', '.join(sorted(draft_person_ids))}"
            )
        if draft_person_ids:
            person_id = next(iter(draft_person_ids))
            reserved_drafts = drafts[drafts["person_id"].eq(person_id)]
            for external_source, incoming_id in external_keys:
                if external_source not in SINGLETON_EXTERNAL_ID_SOURCES:
                    continue
                reserved_ids = {
                    _clean_text(row.get("external_id"))
                    for _, row in reserved_drafts.iterrows()
                    if _clean_text(row.get("external_source")).casefold() == external_source
                    and _clean_text(row.get("external_id"))
                }
                if len(reserved_ids) > 1 or (reserved_ids and incoming_id not in reserved_ids):
                    raise ValueError(
                        f"Draft person {person_id} has conflicting {external_source} IDs: "
                        f"reserved {', '.join(sorted(reserved_ids))}; incoming {incoming_id}"
                    )
        else:
            reserved_rows = pd.DataFrame({"person_id": sorted(set(drafts["person_id"]) - {""})})
            person_id = _next_person_id(
                pd.concat([registry, pd.DataFrame(new_registry_rows), reserved_rows], ignore_index=True)
            )

        draft_rows = [
            {
                "person_id": person_id,
                "normalized_name": candidate_name,
                "external_source": "",
                "external_id": "",
                "display_name": display_name,
                "created_at": now_text,
            }
            for candidate_name in sorted(normalized_names)
        ]
        draft_rows.extend(
            {
                "person_id": person_id,
                "normalized_name": "",
                "external_source": external_source,
                "external_id": external_id,
                "display_name": display_name,
                "created_at": now_text,
            }
            for external_source, external_id in sorted(external_keys)
        )
        drafts = pd.concat([drafts, pd.DataFrame(draft_rows)], ignore_index=True).drop_duplicates(
            subset=["person_id", "normalized_name", "external_source", "external_id"],
            keep="first",
        )
        profile_slug = _allocate_unique_slug(display_name, used_slugs)
        new_registry_rows.append(
            {
                "person_id": person_id,
                "display_name": display_name,
                "normalized_name": normalized_name,
                "profile_slug": profile_slug,
                "status": "active",
                "merged_into_person_id": "",
                "created_at": now_text,
                "updated_at": "",
                "notes": "auto-created from result name; review aliases manually when needed",
            }
        )
        new_slug_rows.append(
            {
                "person_id": person_id,
                "profile_slug": profile_slug,
                "active_from": now_text,
                "active_to": "",
                "reason": "initial",
            }
        )
        for alias in sorted(display_counter):
            aliases = _append_alias_if_missing(aliases, person_id, alias, "auto_result_name")

    if new_registry_rows:
        registry = pd.concat([registry, pd.DataFrame(new_registry_rows)], ignore_index=True)
    if new_slug_rows:
        slug_history = pd.concat([slug_history, pd.DataFrame(new_slug_rows)], ignore_index=True)
    _write_csv_bundle_atomically([(drafts, paths.drafts, DRAFT_COLUMNS)])

    identity = IdentityData(registry, aliases, external_ids, slug_history, identity.result_overrides, identity.match_decisions)
    indexes = build_identity_indexes(identity)

    for _, row in results_df.iterrows():
        match = match_result_to_person(row, identity, indexes)
        if not match.person_id:
            continue
        aliases = _append_alias_if_missing(aliases, match.person_id, row.get("athlete_name"), "auto_seen_result_name")
        for source, external_id in _external_keys_for_row(row):
            external_ids = _append_external_id_if_missing(external_ids, match.person_id, source, external_id)

    updated_identity = IdentityData(
        registry=_with_columns(registry, REGISTRY_COLUMNS),
        aliases=_with_columns(aliases, ALIAS_COLUMNS),
        external_ids=_with_columns(external_ids, EXTERNAL_ID_COLUMNS),
        slug_history=_with_columns(slug_history, SLUG_HISTORY_COLUMNS),
        result_overrides=_with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS),
        match_decisions=_with_columns(identity.match_decisions, MATCH_DECISION_COLUMNS),
        provisional_person_ids=frozenset(
            _clean_text(row.get("person_id"))
            for row in new_registry_rows
            if _clean_text(row.get("person_id"))
        ),
    )
    if persist:
        persist_identity_data(updated_identity, identity_dir, canonical_seed_dir)
    return updated_identity


def _display_time(row: pd.Series) -> str:
    return _clean_text(row.get("result_time_normalized")) or _clean_text(row.get("result_time_raw"))


def _has_valid_time(value: object) -> bool:
    if _is_missing(value):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _public_result_summary(row: pd.Series, distance: str | None = None) -> dict[str, object]:
    source_distance = _clean_text(row.get("distance"))
    return {
        "result_id": _clean_text(row.get("result_id")),
        "distance": distance or source_distance,
        "source_distance": source_distance,
        "result_time": _display_time(row),
        "result_time_seconds": row.get("result_time_seconds") if _has_valid_time(row.get("result_time_seconds")) else None,
        "wa_points": row.get("wa_points") if _has_valid_time(row.get("wa_points")) else None,
        "event_label": _clean_text(row.get("event_label")),
        "published_date": _clean_text(row.get("published_date_iso") or row.get("published_date")),
        "published_date_label": _clean_text(row.get("published_date_label")),
        "week_number": int(row.get("week_number")) if not _is_missing(row.get("week_number")) else None,
        "place": _clean_text(row.get("place")),
        "class_place": _clean_text(row.get("class_place")),
    }


def _sort_distances(distances: set[str]) -> list[str]:
    return sorted(distances, key=lambda value: (DISTANCE_ORDER.get(value, 999), value))


def build_people_payload(df: pd.DataFrame, identity: IdentityData) -> dict[str, object]:
    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)
    active_registry = registry[_active_registry_mask(registry)].copy()

    registry_by_id = {
        row["person_id"]: row
        for _, row in active_registry.iterrows()
        if _clean_text(row.get("person_id"))
    }
    current_slug_by_id = {
        person_id: _clean_text(row.get("profile_slug"))
        for person_id, row in registry_by_id.items()
        if _clean_text(row.get("profile_slug"))
    }

    profiles: list[dict[str, object]] = []
    for person_id, person_rows in df[df["person_id"].fillna("").ne("")].groupby("person_id"):
        registry_row = registry_by_id.get(person_id)
        display_name = (
            clean_display_text(registry_row.get("display_name")) if registry_row is not None else ""
        ) or clean_display_text(person_rows["athlete_name"].mode().iloc[0])
        profile_slug = current_slug_by_id.get(person_id) or slugify_person_name(display_name)
        distances = _sort_distances(
            {
                _clean_text(value)
                for value in person_rows.get("distance", pd.Series(dtype=str))
                if _clean_text(value)
            }
        )
        gender_values = sorted(
            {
                _clean_text(value)
                for value in person_rows.get("gender", pd.Series(dtype=str))
                if _clean_text(value)
            }
        )
        gender = gender_values[0] if len(gender_values) == 1 else ""
        gender_label = {"K": "Kvinner", "M": "Menn"}.get(gender, "")

        best_results: list[dict[str, object]] = []
        distance_column = "profile_distance" if "profile_distance" in person_rows.columns else "distance"
        for distance in STANDARD_PROFILE_DISTANCES:
            candidates = person_rows[
                person_rows[distance_column].fillna("").astype(str).eq(distance)
                & person_rows["result_time_seconds"].map(_has_valid_time)
            ].copy()
            if candidates.empty:
                continue
            candidates = candidates.sort_values(
                ["result_time_seconds", "published_date_sort", "event_label"],
                ascending=[True, True, True],
                na_position="last",
            )
            best_results.append(_public_result_summary(candidates.iloc[0], distance=distance))

        published_dates = [
            _clean_text(value)
            for value in person_rows.get("published_date_iso", pd.Series(dtype=str))
            if _clean_text(value)
        ]
        wa_values = pd.to_numeric(person_rows.get("wa_points", pd.Series(dtype=float)), errors="coerce").dropna()
        pb_count = int(person_rows["is_pb"].sum()) if "is_pb" in person_rows.columns else 0
        sb_count = int(person_rows["is_sb"].sum()) if "is_sb" in person_rows.columns else 0
        profiles.append(
            {
                "person_id": person_id,
                "profile_slug": profile_slug,
                "display_name": display_name,
                "gender": gender,
                "gender_label": gender_label,
                "result_count": int(len(person_rows)),
                "distances": distances,
                "best_results": best_results,
                "wa_points_best": float(wa_values.max()) if not wa_values.empty else None,
                "pb_count": pb_count,
                "sb_count": sb_count,
                "first_result_date": min(published_dates) if published_dates else "",
                "latest_result_date": max(published_dates) if published_dates else "",
            }
        )

    slug_map = {profile["profile_slug"]: profile["person_id"] for profile in profiles}
    slug_redirects: dict[str, str] = {}
    for _, row in slug_history.iterrows():
        old_slug = _clean_text(row.get("profile_slug"))
        person_id = _clean_text(row.get("person_id"))
        resolved_person_id = _resolve_person_id(person_id, registry)
        active_to = _clean_text(row.get("active_to"))
        current_slug = current_slug_by_id.get(resolved_person_id, "")
        if old_slug and current_slug:
            slug_map.setdefault(old_slug, resolved_person_id)
        if (active_to or resolved_person_id != person_id) and old_slug and current_slug and old_slug != current_slug:
            slug_redirects[old_slug] = current_slug

    profiles.sort(key=lambda profile: normalize_name(profile["display_name"]))
    return {
        "profile_count": len(profiles),
        "profiles": profiles,
        "slug_map": slug_map,
        "slug_redirects": slug_redirects,
    }


def _safe_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    existing = [column for column in columns if column in df.columns]
    return df[existing].copy() if existing else pd.DataFrame()


def _conflict_report(
    df: pd.DataFrame,
    key_column: str,
    value_column: str = "person_id",
) -> pd.DataFrame:
    if df.empty or key_column not in df.columns or value_column not in df.columns:
        return pd.DataFrame(columns=[key_column, "person_ids", "count"])
    active_df = df[_active_mask(df)].copy() if "active" in df.columns else df.copy()
    rows = []
    for key, group in active_df.groupby(key_column):
        cleaned_key = _clean_text(key)
        person_ids = sorted({_clean_text(value) for value in group[value_column] if _clean_text(value)})
        if cleaned_key and len(person_ids) > 1:
            rows.append({key_column: cleaned_key, "person_ids": ", ".join(person_ids), "count": len(person_ids)})
    return pd.DataFrame(rows, columns=[key_column, "person_ids", "count"])


def _fuzzy_candidates(registry: pd.DataFrame) -> pd.DataFrame:
    active = registry[_active_registry_mask(registry)].copy()
    people = []
    for _, row in active.iterrows():
        normalized = _clean_text(row.get("normalized_name")) or normalize_name(row.get("display_name"))
        if normalized:
            people.append(
                {
                    "person_id": _clean_text(row.get("person_id")),
                    "display_name": clean_display_text(row.get("display_name")),
                    "normalized_name": normalized,
                }
            )

    rows = []
    for left_index, left in enumerate(people):
        for right in people[left_index + 1 :]:
            if left["normalized_name"] == right["normalized_name"]:
                continue
            score = SequenceMatcher(None, left["normalized_name"], right["normalized_name"]).ratio()
            if score >= 0.9:
                rows.append(
                    {
                        "score": round(score, 3),
                        "person_id_1": left["person_id"],
                        "display_name_1": left["display_name"],
                        "person_id_2": right["person_id"],
                        "display_name_2": right["display_name"],
                    }
                )
    return pd.DataFrame(rows).sort_values("score", ascending=False).head(200) if rows else pd.DataFrame(
        columns=["score", "person_id_1", "display_name_1", "person_id_2", "display_name_2"]
    )


def _slug_history_name_mismatches(
    registry: pd.DataFrame,
    aliases: pd.DataFrame,
    slug_history: pd.DataFrame,
) -> pd.DataFrame:
    names_by_person: dict[str, set[str]] = defaultdict(set)
    for _, row in registry.iterrows():
        resolved_person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        normalized_name = normalize_name(row.get("display_name"))
        if resolved_person_id and normalized_name:
            names_by_person[resolved_person_id].add(normalized_name)
    for _, row in aliases[_active_mask(aliases)].iterrows():
        resolved_person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        normalized_alias = _clean_text(row.get("normalized_alias")) or normalize_name(row.get("alias"))
        if resolved_person_id and normalized_alias:
            names_by_person[resolved_person_id].add(normalized_alias)

    rows: list[dict[str, object]] = []
    for _, row in slug_history.iterrows():
        person_id = _clean_text(row.get("person_id"))
        profile_slug = _clean_text(row.get("profile_slug"))
        reason = _clean_text(row.get("reason"))
        if not person_id or not profile_slug or reason.casefold().startswith("manual_slug_assignment"):
            continue
        resolved_person_id = _resolve_person_id(person_id, registry)
        slug_name = normalize_name(profile_slug.replace("-", " "))
        known_names = names_by_person.get(resolved_person_id, set())
        best_score = max(
            (SequenceMatcher(None, slug_name, known_name).ratio() for known_name in known_names),
            default=0.0,
        )
        if best_score >= 0.55:
            continue
        rows.append(
            {
                "person_id": person_id,
                "resolved_person_id": resolved_person_id,
                "profile_slug": profile_slug,
                "reason": reason,
                "best_name_similarity": round(best_score, 3),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["person_id", "resolved_person_id", "profile_slug", "reason", "best_name_similarity"],
    )


def _normalize_public_field_name(value: str) -> str:
    return normalize_name(value).replace(" ", "_")


PRIVATE_PUBLIC_FIELD_KEYS = {_normalize_public_field_name(name) for name in PRIVATE_PUBLIC_FIELD_NAMES}


def find_private_field_leaks(payload: object) -> pd.DataFrame:
    leaks: list[dict[str, str]] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = _normalize_public_field_name(str(key))
                child_path = f"{path}.{key}" if path else str(key)
                if normalized_key in PRIVATE_PUBLIC_FIELD_KEYS:
                    leaks.append(
                        {
                            "path": child_path,
                            "field": str(key),
                            "issue": "private field name",
                            "value_preview": _clean_text(child)[:120],
                        }
                    )
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            if re.search(r"[A-Za-z]:\\|/Users/|\\Users\\", value):
                leaks.append(
                    {
                        "path": path,
                        "field": path.rsplit(".", 1)[-1],
                        "issue": "local filesystem path",
                        "value_preview": value[:120],
                    }
                )

    walk(payload, "")
    return pd.DataFrame(leaks, columns=["path", "field", "issue", "value_preview"])


def validate_public_payload(payload: object) -> pd.DataFrame:
    leaks = find_private_field_leaks(payload)
    if not leaks.empty:
        preview = "; ".join(leaks.head(5)["path"].tolist())
        raise ValueError(f"Public payload contains private fields: {preview}")
    return leaks


def build_identity_reports(
    df: pd.DataFrame,
    identity: IdentityData,
    payload: object | None = None,
) -> dict[str, pd.DataFrame]:
    registry = _with_columns(identity.registry, REGISTRY_COLUMNS)
    aliases = _prepare_aliases(identity.aliases)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)
    identity_graph_errors = find_identity_graph_errors(identity)

    missing_person = df[df.get("person_id", pd.Series("", index=df.index)).fillna("").eq("")]
    duplicate_names = _conflict_report(registry[_active_registry_mask(registry)], "normalized_name")
    alias_report = aliases.copy()
    alias_report["resolved_person_id"] = alias_report["person_id"].map(lambda person_id: _resolve_person_id(_clean_text(person_id), registry))
    alias_conflicts = _conflict_report(alias_report, "normalized_alias", value_column="resolved_person_id")
    active_registry_names = registry[_active_registry_mask(registry)][["person_id", "normalized_name"]].copy()
    active_registry_names = active_registry_names.rename(columns={"person_id": "resolved_person_id", "normalized_name": "name_key"})
    active_alias_names = alias_report[_active_mask(alias_report)][["resolved_person_id", "normalized_alias"]].copy()
    active_alias_names = active_alias_names.rename(columns={"normalized_alias": "name_key"})
    all_name_owners = pd.concat([active_registry_names, active_alias_names], ignore_index=True)
    name_key_conflicts = _conflict_report(all_name_owners, "name_key", value_column="resolved_person_id")
    external_id_report = external_ids.copy()
    external_id_report["resolved_person_id"] = external_id_report["person_id"].map(
        lambda person_id: _resolve_person_id(_clean_text(person_id), registry)
    )
    external_id_report["normalized_source"] = external_id_report["source"].map(
        lambda value: _clean_text(value).casefold()
    )
    external_id_report["external_key"] = (
        external_id_report["normalized_source"]
        + ":"
        + external_id_report["external_id"].map(_clean_text)
    )
    external_id_conflicts = _conflict_report(external_id_report, "external_key", value_column="resolved_person_id")
    external_source_cardinality_rows: list[dict[str, object]] = []
    active_external_ids = external_id_report[_active_mask(external_id_report)].copy()
    for (resolved_person_id, normalized_source), group in active_external_ids.groupby(
        ["resolved_person_id", "normalized_source"]
    ):
        distinct_ids = sorted({_clean_text(value) for value in group["external_id"] if _clean_text(value)})
        if normalized_source in SINGLETON_EXTERNAL_ID_SOURCES and len(distinct_ids) > 1:
            external_source_cardinality_rows.append(
                {
                    "person_id": _clean_text(resolved_person_id),
                    "source": normalized_source,
                    "external_ids": ", ".join(distinct_ids),
                    "count": len(distinct_ids),
                }
            )
    external_source_cardinality_conflicts = pd.DataFrame(
        external_source_cardinality_rows,
        columns=["person_id", "source", "external_ids", "count"],
    )
    slug_collisions = _conflict_report(registry[_active_registry_mask(registry)], "profile_slug")
    slug_owner_rows: list[dict[str, str]] = []
    for _, row in registry[_active_registry_mask(registry)].iterrows():
        person_id = _clean_text(row.get("person_id"))
        slug_key = _clean_text(row.get("profile_slug")).casefold()
        if person_id and slug_key:
            slug_owner_rows.append(
                {
                    "slug_key": slug_key,
                    "resolved_person_id": _resolve_person_id(person_id, registry),
                    "source": "active_registry",
                }
            )
    for _, row in slug_history.iterrows():
        person_id = _clean_text(row.get("person_id"))
        slug_key = _clean_text(row.get("profile_slug")).casefold()
        if person_id and slug_key:
            slug_owner_rows.append(
                {
                    "slug_key": slug_key,
                    "resolved_person_id": _resolve_person_id(person_id, registry),
                    "source": "slug_history",
                }
            )
    resolved_slug_owner_conflicts = _conflict_report(
        pd.DataFrame(slug_owner_rows, columns=["slug_key", "resolved_person_id", "source"]),
        "slug_key",
        value_column="resolved_person_id",
    )
    slug_history_name_mismatches = _slug_history_name_mismatches(registry, aliases, slug_history)
    leaks = find_private_field_leaks(payload) if payload is not None else pd.DataFrame(
        columns=["path", "field", "issue", "value_preview"]
    )

    return {
        "results_without_person_id": _safe_columns(
            missing_person,
            [
                "result_id",
                "published_date_iso",
                "event_label",
                "distance",
                "athlete_name",
                "identity_match_method",
                "identity_match_review",
            ],
        ),
        "person_match_candidates": build_person_match_candidates(identity, df),
        "identity_graph_errors": identity_graph_errors,
        "alias_conflicts": alias_conflicts,
        "name_key_conflicts": name_key_conflicts,
        "external_id_conflicts": external_id_conflicts,
        "external_source_cardinality_conflicts": external_source_cardinality_conflicts,
        "duplicate_normalized_names": duplicate_names,
        "slug_collisions": slug_collisions,
        "resolved_slug_owner_conflicts": resolved_slug_owner_conflicts,
        "slug_history_name_mismatches": slug_history_name_mismatches,
        "fuzzy_match_candidates": _fuzzy_candidates(registry),
        "public_payload_leaks": leaks,
    }


IDENTITY_INTEGRITY_REPORTS = (
    "identity_graph_errors",
    "alias_conflicts",
    "name_key_conflicts",
    "external_id_conflicts",
    "duplicate_normalized_names",
    "slug_collisions",
    "resolved_slug_owner_conflicts",
    "slug_history_name_mismatches",
    "public_payload_leaks",
)


def validate_identity_reports(reports: dict[str, pd.DataFrame]) -> None:
    failures = {
        name: len(reports.get(name, pd.DataFrame()))
        for name in IDENTITY_INTEGRITY_REPORTS
        if not reports.get(name, pd.DataFrame()).empty
    }
    if failures:
        summary = ", ".join(f"{name}={count}" for name, count in failures.items())
        raise ValueError(f"Publisering stoppet av feil i personregisteret: {summary}")


def write_identity_reports(reports: dict[str, pd.DataFrame], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    for name, report_df in reports.items():
        csv_safe_dataframe(report_df).to_csv(
            reports_dir / f"{name}.csv",
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
