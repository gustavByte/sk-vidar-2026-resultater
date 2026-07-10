from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Iterable


TERRAIN_TAG_ORDER = ("fjellop", "trail", "skyrace", "terreng", "ultra", "motbakke")
PUBLIC_NOTE_BLOCK_PATTERNS = (
    r"\bslack\b",
    r"svak\s+navnematch",
    r"alias\s+kontrollert",
    r"\bskjermbilde\b",
    r"\bscreenshot\b",
    r"\bskv-p\d+\b",
    r"\binternt?\b",
    r"manuell\s+(?:registrering|oppdatering)",
    r"aktiv(?:t)?\s+medlem",
    r"fellestrening",
    r"mulig\s+sk\s+vidar",
    r"sk\s+vidar-relatert",
    r"nye\s+l[oø]pere",
)

_INTERNAL_NOTE_RE = re.compile("|".join(f"(?:{pattern})" for pattern in PUBLIC_NOTE_BLOCK_PATTERNS), re.IGNORECASE)
_NORMALIZE_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def normalize_search_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value).casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text).strip()


def _row_text(row: object) -> str:
    getter = getattr(row, "get", lambda _key, default="": default)
    values = [
        getter("event_label", ""),
        getter("event_name", ""),
        getter("distance", ""),
        getter("public_note", ""),
        getter("notes_clean", ""),
        getter("notes", ""),
    ]
    return normalize_search_text(" ".join(clean_text(value) for value in values if clean_text(value)))


def terrain_tags_for_row(row: object) -> list[str]:
    text = _row_text(row)
    tags: set[str] = set()

    if re.search(r"\b(?:sky\s?race|skyrace|skyrunning)\b", text):
        tags.add("skyrace")
    if re.search(r"\b(?:fjell\w*|zegama|mont[-\s]?blanc|gornergrat|zermatt|mendi|norefjell)\b|\b\d+\s*hm\+?\b", text):
        tags.add("fjellop")
    if re.search(r"\b(?:trail|utmb|ultratrail|eco\s?trail)\b", text):
        tags.add("trail")
    if re.search(r"\b(?:terreng\w*|skogsmaraton|brunkollen\s+rundt|furumo\s+terrengl)\b", text):
        tags.add("terreng")
    if re.search(r"\b(?:ultra\w*|backyard|hundreds)\b", text):
        tags.add("ultra")
    if re.search(r"\b(?:motbakke|opp(?:lo|lop|løp)|vertical)\b", text):
        tags.add("motbakke")

    known_terrain = re.search(
        r"\b(?:hornindal\s+rundt|romeriksasen\s+pa\s+langs|nosen\s+hundreds|sandsjobacka|bessegglopet)\b",
        text,
    )
    if known_terrain and not tags:
        tags.add("terreng")

    return [tag for tag in TERRAIN_TAG_ORDER if tag in tags]


def event_type_for_row(row: object) -> str:
    if terrain_tags_for_row(row):
        return "terrain"

    getter = getattr(row, "get", lambda _key, default="": default)
    distance = normalize_search_text(getter("distance", ""))
    event = normalize_search_text(getter("event_label", "") or getter("event_name", ""))
    if event.startswith("bislett distanseserie") and distance == "3000 m":
        return "road"
    if re.search(r"\b(?:600|800|1500|3000|5000|10000|10\s*000)\s*(?:m|meter|meters)\b", distance):
        return "track"
    if re.search(r"\b(?:km|halvmaraton|maraton|marathon|miles?)\b", distance):
        return "road"
    return "other"


def event_id_for_label(value: object) -> str:
    normalized = normalize_search_text(value)
    stable = _NORMALIZE_NON_ALNUM_RE.sub("-", normalized).strip("-") or "ukjent-lop"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"evt-{stable[:48]}-{digest}"


def split_public_internal_note(
    notes: object,
    public_note: object = "",
    internal_note: object = "",
) -> tuple[str, str]:
    explicit_public = clean_text(public_note)
    explicit_internal = clean_text(internal_note)
    source = explicit_public or clean_text(notes)

    public_parts: list[str] = []
    internal_parts: list[str] = [explicit_internal] if explicit_internal else []
    for part in re.split(r"\s*;\s*|(?<=[.!?])\s+", source):
        part = part.strip(" .;,")
        if not part:
            continue
        if _INTERNAL_NOTE_RE.search(part):
            internal_parts.append(part)
        else:
            public_parts.append(part)

    return "; ".join(public_parts), "; ".join(dict.fromkeys(internal_parts))


def public_note_has_internal_markers(value: object) -> bool:
    return bool(_INTERNAL_NOTE_RE.search(clean_text(value)))


def wa_status_for_values(wa_points: object, wa_event: object, gender: object, result_time: object) -> str:
    try:
        if wa_points is not None and not (isinstance(wa_points, float) and math.isnan(wa_points)):
            float(wa_points)
            return "scored"
    except (TypeError, ValueError):
        pass

    if clean_text(wa_event) and clean_text(gender) in {"K", "M"} and clean_text(result_time):
        return "missing"
    return "not_applicable"


def tags_as_text(tags: Iterable[str]) -> str:
    return ",".join(dict.fromkeys(clean_text(tag) for tag in tags if clean_text(tag)))
