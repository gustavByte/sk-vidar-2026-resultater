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
    r"relatert\s+(?:treff|ut[oø]ver)",
    r"\bpubliser\w*\b",
    r"(?:sterk|sannsynlig|mulig)\s+kandidat",
    r"nye\s+l[oø]pere",
)

_INTERNAL_NOTE_RE = re.compile("|".join(f"(?:{pattern})" for pattern in PUBLIC_NOTE_BLOCK_PATTERNS), re.IGNORECASE)
_NORMALIZE_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

MARATHON_KM = 42.195
HALF_MARATHON_KM = 21.0975
MILES_TO_KM = 1.609344

# Distances that are named rather than written with a numeric unit in the
# source workbook. Keep this list deliberately small: an unknown distance is
# safer to omit from a cumulative ranking than to guess.
_NAMED_DISTANCE_KM = {
    "halvmaraton": HALF_MARATHON_KM,
    "half marathon": HALF_MARATHON_KM,
    "half-marathon": HALF_MARATHON_KM,
    "halbmarathon men": HALF_MARATHON_KM,
    "maraton": MARATHON_KM,
    "marathon": MARATHON_KM,
    "birken fjellmaraton": 42.0,
    "hoka lofoten skyrace marathon": 42.0,
    "maridalsvannet rundt": 13.0,
    "festaløpet": 17.5,
    "kaptein dreyers minneløp aktiv": 12.0,
}

# A few providers publish only a category name such as "Ultra". These
# event-specific values are documented course lengths and must not be applied
# to similarly named categories at other events.
_EVENT_DISTANCE_KM = {
    ("jotunheimen trail run 2026", "ultra"): 73.0,
    ("jotunheimen trail run 2026", "skyrace"): 16.0,
    ("gornergrat zermatt marathon 2026", "ultra men"): 45.595,
    ("nordmarka skogsmaraton 2026", "ultra"): 63.2925,
    ("nm terrengløp kort løype stafett 2026", "6 km stafett"): 3.0,
    ("flækøyhøe upp 2026", "konkurranseklasse"): 4.0,
    ("fyr til fyr 2026", "fyr til fyr konkurranse"): 43.0,
    ("birkebeinerløpene 2026", "ungdomsbirken løp"): 5.0,
    ("det norske fjellmaraton 2026", "fjellbukk"): 10.0,
    ("saldilten 2026", "konkurranse kort"): 6.63,
    ("skyrunning youth world championships 2026", "vertical"): 4.5,
}

# Result-level overrides are reserved for formats where two athletes in the
# same category can complete different distances (notably backyard races), or
# where the provider omitted the event distance from one specific result.
_ATHLETE_EVENT_DISTANCE_KM = {
    ("lommedalen backyard 2026", "backyard", "martine svendsen"): 80.4,
    ("lommedalen backyard 2026", "backyard", "remi høiseth"): 80.4,
    ("the arctic run 2026", "para arctic run", "tone gravvold"): HALF_MARATHON_KM,
}

_KILOMETER_DISTANCE_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:km|kilometers?|k)\b", re.IGNORECASE)
_MILE_DISTANCE_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*miles?\b", re.IGNORECASE)
_METER_DISTANCE_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:m|meters?)\b", re.IGNORECASE)


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


def _number_from_match(match: re.Match[str]) -> float:
    return float(match.group(1).replace(",", "."))


def _numeric_distance_km(value: object) -> float | None:
    text = clean_text(value)
    if not text:
        return None

    kilometer_match = _KILOMETER_DISTANCE_RE.search(text)
    if kilometer_match:
        distance = _number_from_match(kilometer_match)
    else:
        mile_match = _MILE_DISTANCE_RE.search(text)
        if mile_match:
            distance = _number_from_match(mile_match) * MILES_TO_KM
        else:
            meter_match = _METER_DISTANCE_RE.search(text)
            if not meter_match:
                return None
            distance = _number_from_match(meter_match) / 1000

    if not 0 < distance <= 1000:
        return None
    return round(distance, 6)


def competition_distance_km_for_row(row: object) -> float | None:
    """Return the distance credited to one athlete for a published result.

    The parser accepts explicit metric/imperial units and a conservative set
    of named-distance overrides. Ambiguous categories remain ``None`` and are
    excluded from cumulative distance statistics.
    """

    getter = getattr(row, "get", lambda _key, default="": default)
    distance = clean_text(getter("distance", ""))
    event = clean_text(getter("event_label", "") or getter("event_name", ""))
    normalized_distance = normalize_search_text(distance)
    normalized_event = normalize_search_text(event)
    normalized_athlete = normalize_search_text(getter("athlete_name", ""))

    athlete_override = _ATHLETE_EVENT_DISTANCE_KM.get(
        (normalized_event, normalized_distance, normalized_athlete)
    )
    if athlete_override is not None:
        return athlete_override

    event_override = _EVENT_DISTANCE_KM.get((normalized_event, normalized_distance))
    if event_override is not None:
        return event_override

    named_override = _NAMED_DISTANCE_KM.get(normalized_distance)
    if named_override is not None:
        return named_override

    numeric_distance = _numeric_distance_km(distance)
    if numeric_distance is not None:
        return numeric_distance

    # Backyard results are distance-dependent on completed laps. Only use an
    # explicitly recorded total; elapsed time alone is not enough evidence.
    if "backyard" in normalized_distance:
        notes = getter("notes_clean", "") or getter("public_note", "") or getter("notes", "")
        return _numeric_distance_km(notes)

    return None


def competition_distance_status_for_row(row: object) -> str:
    getter = getattr(row, "get", lambda _key, default="": default)
    normalized_distance = normalize_search_text(getter("distance", ""))
    if normalized_distance == "kombinert":
        return "excluded_aggregate"
    return "known" if competition_distance_km_for_row(row) is not None else "unknown"


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


def _classify_note_parts(source: object, internal_note: object = "") -> tuple[str, str]:
    public_parts: list[str] = []
    explicit_internal = clean_text(internal_note)
    internal_parts: list[str] = [explicit_internal] if explicit_internal else []
    for part in re.split(r"\s*;\s*|(?<=[.!?])\s+", clean_text(source)):
        part = part.strip(" .;,")
        if not part:
            continue
        if _INTERNAL_NOTE_RE.search(part):
            internal_parts.append(part)
        else:
            public_parts.append(part)

    return "; ".join(public_parts), "; ".join(dict.fromkeys(internal_parts))


def classify_note_for_import(notes: object, internal_note: object = "") -> tuple[str, str]:
    """Classify a legacy/source note before it enters the trusted workbook."""

    return _classify_note_parts(notes, internal_note)


def split_public_internal_note(
    notes: object,
    public_note: object = "",
    internal_note: object = "",
) -> tuple[str, str]:
    """Return publishable and internal notes without trusting the legacy field.

    ``notes`` is intentionally never a public fallback. It remains available as
    the preserved raw source, while only ``public_note`` may cross a publication
    boundary. Call ``classify_note_for_import`` during ingestion or migration.
    """

    explicit_public = clean_text(public_note)
    explicit_internal = clean_text(internal_note)
    public, rejected = _classify_note_parts(explicit_public, explicit_internal)

    raw = clean_text(notes)
    if raw and not explicit_public and not explicit_internal:
        rejected = "; ".join(dict.fromkeys(part for part in (rejected, raw) if part))
    return public, rejected


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
