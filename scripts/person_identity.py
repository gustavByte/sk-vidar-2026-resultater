from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

from project_paths import (
    PERSON_ALIASES_FILE,
    PERSON_EXTERNAL_IDS_FILE,
    PERSON_IDENTITY_DIR,
    PERSON_REGISTRY_FILE,
    PERSON_SLUG_HISTORY_FILE,
    RESULT_PERSON_OVERRIDES_FILE,
)


PERSON_ID_PREFIX = "skv-p"
SCHEMA_VERSION = 2

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

STANDARD_PROFILE_DISTANCES = ["800 m", "1500 m", "3000 m", "5 km", "10 km", "Halvmaraton", "Maraton"]
DISTANCE_ORDER = {distance: index for index, distance in enumerate(STANDARD_PROFILE_DISTANCES)}

PRIVATE_PUBLIC_FIELD_NAMES = {
    "slack_user_id",
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
    "slack": ["slack_user_id"],
    "world_athletics": ["world_athletics_id", "wa_person_id"],
    "result_source": ["source_person_id", "external_person_id"],
}

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


@dataclass
class IdentityData:
    registry: pd.DataFrame
    aliases: pd.DataFrame
    external_ids: pd.DataFrame
    slug_history: pd.DataFrame
    result_overrides: pd.DataFrame


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


def repair_mojibake(text: str) -> str:
    repaired = text
    for _ in range(2):
        if not any(marker in repaired for marker in ("Ã", "Â", "â")):
            break
        try:
            candidate = repaired.encode("latin1").decode("utf-8")
        except Exception:
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


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
    return ~status.isin({"inactive", "inaktiv", "deleted", "slettet"})


def _with_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in columns:
        if column not in working.columns:
            working[column] = ""
    ordered_columns = columns + [column for column in working.columns if column not in columns]
    return working[ordered_columns].fillna("")


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return _with_columns(pd.read_csv(path, dtype=str).fillna(""), columns)


def _write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _with_columns(df, columns).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def ensure_identity_files(identity_dir: Path | None = None) -> IdentityPaths:
    paths = _identity_paths(identity_dir)
    paths.identity_dir.mkdir(parents=True, exist_ok=True)
    for path, columns in (
        (paths.registry, REGISTRY_COLUMNS),
        (paths.aliases, ALIAS_COLUMNS),
        (paths.external_ids, EXTERNAL_ID_COLUMNS),
        (paths.slug_history, SLUG_HISTORY_COLUMNS),
        (paths.result_overrides, RESULT_OVERRIDE_COLUMNS),
    ):
        if not path.exists():
            _write_csv(pd.DataFrame(columns=columns), path, columns)
    return paths


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


def load_identity_data(identity_dir: Path | None = None) -> IdentityData:
    paths = _identity_paths(identity_dir)
    return IdentityData(
        registry=load_person_registry(paths.registry),
        aliases=load_aliases(paths.aliases),
        external_ids=load_external_ids(paths.external_ids),
        slug_history=load_slug_history(paths.slug_history),
        result_overrides=load_result_person_overrides(paths.result_overrides),
    )


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
    aliases = _with_columns(identity.aliases, ALIAS_COLUMNS)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    overrides = _with_columns(identity.result_overrides, RESULT_OVERRIDE_COLUMNS)

    registry_by_name: dict[str, set[str]] = {}
    aliases_by_name: dict[str, set[str]] = {}
    external_index: dict[tuple[str, str], set[str]] = {}
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

    for _, row in overrides[_active_mask(overrides)].iterrows():
        person_id = _resolve_person_id(_clean_text(row.get("person_id")), registry)
        result_id = _clean_text(row.get("result_id"))
        _add_to_index(override_index, result_id, person_id)

    return IdentityIndexes(
        registry_by_normalized_name=registry_by_name,
        aliases_by_normalized_name=aliases_by_name,
        external_ids=external_index,
        result_overrides=override_index,
        slug_by_person_id=slug_by_person_id,
    )


def _single_person_id(candidates: set[str] | None) -> str:
    if not candidates or len(candidates) != 1:
        return ""
    return next(iter(candidates))


def _external_keys_for_row(row: pd.Series | dict[str, object]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for source, columns in EXTERNAL_ID_SOURCE_COLUMNS.items():
        for column in columns:
            value = _clean_text(_row_get(row, column))
            if value:
                keys.append((source, value))
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

    for external_key in _external_keys_for_row(row):
        external_candidates = lookup.external_ids.get(external_key)
        if not external_candidates:
            continue
        person_id = _single_person_id(external_candidates)
        if person_id:
            return PersonMatch(person_id=person_id, method=f"external_id:{external_key[0]}")
        return PersonMatch(
            person_id="",
            method="ambiguous_external_id",
            reason=f"{external_key[0]}:{external_key[1]}",
            needs_review=True,
        )

    normalized_name = normalize_name(_row_get(row, "athlete_name"))
    if not normalized_name:
        return PersonMatch(person_id="", method="missing_name", needs_review=True)

    alias_candidates = lookup.aliases_by_normalized_name.get(normalized_name)
    if alias_candidates:
        person_id = _single_person_id(alias_candidates)
        if person_id:
            return PersonMatch(person_id=person_id, method="alias")
        return PersonMatch(person_id="", method="ambiguous_alias", reason=normalized_name, needs_review=True)

    registry_candidates = lookup.registry_by_normalized_name.get(normalized_name)
    if registry_candidates:
        person_id = _single_person_id(registry_candidates)
        if person_id:
            return PersonMatch(person_id=person_id, method="registry_name")
        return PersonMatch(person_id="", method="ambiguous_registry_name", reason=normalized_name, needs_review=True)

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
        display_name = _clean_text(row.get("display_name"))
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
    cleaned_alias = _clean_text(alias)
    normalized_alias = normalize_name(cleaned_alias)
    if not person_id or not normalized_alias:
        return aliases

    working = _with_columns(aliases, ALIAS_COLUMNS)
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


def ensure_new_people_are_appended_without_changing_existing_ids(
    results_df: pd.DataFrame,
    identity_dir: Path | None = None,
    now: datetime | None = None,
) -> IdentityData:
    paths = ensure_identity_files(identity_dir)
    now_text = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    identity = load_identity_data(paths.identity_dir)

    registry = _prepare_registry(identity.registry, now_text)
    aliases = _with_columns(identity.aliases, ALIAS_COLUMNS)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)
    slug_history = _with_columns(identity.slug_history, SLUG_HISTORY_COLUMNS)

    identity = IdentityData(registry, aliases, external_ids, slug_history, identity.result_overrides)
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
        display_name = _clean_text(row.get("athlete_name"))
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
        person_id = _next_person_id(pd.concat([registry, pd.DataFrame(new_registry_rows)], ignore_index=True))
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

    identity = IdentityData(registry, aliases, external_ids, slug_history, identity.result_overrides)
    indexes = build_identity_indexes(identity)

    for _, row in results_df.iterrows():
        match = match_result_to_person(row, identity, indexes)
        if not match.person_id:
            continue
        aliases = _append_alias_if_missing(aliases, match.person_id, row.get("athlete_name"), "auto_seen_result_name")
        for source, external_id in _external_keys_for_row(row):
            external_ids = _append_external_id_if_missing(external_ids, match.person_id, source, external_id)

    _write_csv(registry, paths.registry, REGISTRY_COLUMNS)
    _write_csv(aliases, paths.aliases, ALIAS_COLUMNS)
    _write_csv(external_ids, paths.external_ids, EXTERNAL_ID_COLUMNS)
    _write_csv(slug_history, paths.slug_history, SLUG_HISTORY_COLUMNS)
    _write_csv(identity.result_overrides, paths.result_overrides, RESULT_OVERRIDE_COLUMNS)
    return load_identity_data(paths.identity_dir)


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
            _clean_text(registry_row.get("display_name")) if registry_row is not None else ""
        ) or _clean_text(person_rows["athlete_name"].mode().iloc[0])
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
                "first_result_date": min(published_dates) if published_dates else "",
                "latest_result_date": max(published_dates) if published_dates else "",
            }
        )

    slug_map = {profile["profile_slug"]: profile["person_id"] for profile in profiles}
    slug_redirects: dict[str, str] = {}
    for _, row in slug_history.iterrows():
        old_slug = _clean_text(row.get("profile_slug"))
        person_id = _clean_text(row.get("person_id"))
        active_to = _clean_text(row.get("active_to"))
        current_slug = current_slug_by_id.get(person_id, "")
        if old_slug and current_slug:
            slug_map.setdefault(old_slug, person_id)
        if active_to and old_slug and current_slug and old_slug != current_slug:
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
                    "display_name": _clean_text(row.get("display_name")),
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
    aliases = _with_columns(identity.aliases, ALIAS_COLUMNS)
    external_ids = _with_columns(identity.external_ids, EXTERNAL_ID_COLUMNS)

    missing_person = df[df.get("person_id", pd.Series("", index=df.index)).fillna("").eq("")]
    duplicate_names = _conflict_report(registry[_active_registry_mask(registry)], "normalized_name")
    alias_conflicts = _conflict_report(aliases, "normalized_alias")
    external_id_report = external_ids.copy()
    external_id_report["external_key"] = (
        external_id_report["source"].fillna("").astype(str).str.casefold()
        + ":"
        + external_id_report["external_id"].fillna("").astype(str)
    )
    external_id_conflicts = _conflict_report(external_id_report, "external_key")
    slug_collisions = _conflict_report(registry[_active_registry_mask(registry)], "profile_slug")
    leaks = find_private_field_leaks(payload) if payload is not None else pd.DataFrame(
        columns=["path", "field", "issue", "value_preview"]
    )

    return {
        "results_without_person_id": _safe_columns(
            missing_person,
            ["result_id", "published_date_iso", "event_label", "distance", "athlete_name", "identity_match_method"],
        ),
        "alias_conflicts": alias_conflicts,
        "external_id_conflicts": external_id_conflicts,
        "duplicate_normalized_names": duplicate_names,
        "slug_collisions": slug_collisions,
        "fuzzy_match_candidates": _fuzzy_candidates(registry),
        "public_payload_leaks": leaks,
    }


def write_identity_reports(reports: dict[str, pd.DataFrame], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    for name, report_df in reports.items():
        report_df.to_csv(reports_dir / f"{name}.csv", index=False, encoding="utf-8", lineterminator="\n")
