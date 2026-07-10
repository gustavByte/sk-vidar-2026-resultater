import { state, getWeekResults, resultsForPerson } from "./state.js";
import { normalizeSearchText, sortResultsNewestFirst } from "./format.js";

const STANDARD_DISTANCES = ["800 m", "1500 m", "3000 m", "3000 m hinder", "5000 m", "10000 m", "5 km", "10 km", "Halvmaraton", "Maraton"];
const STANDARD_DISTANCE_SET = new Set(STANDARD_DISTANCES);

const cache = new Map();

function memo(key, compute) {
  if (!cache.has(key)) {
    cache.set(key, compute());
  }
  return cache.get(key);
}

export function hasFinitePoints(row) {
  return row.wa_points !== null && row.wa_points !== undefined && Number.isFinite(Number(row.wa_points));
}

function hasFiniteTime(row) {
  return row.result_time_seconds !== null && row.result_time_seconds !== undefined && Number.isFinite(Number(row.result_time_seconds));
}

const TERRAIN_OR_TRAIL_PATTERNS = [
  /\bterreng\w*\b/,
  /\bfjell\w*\b/,
  /\btrail\b/,
  /\bmotbakke\b/,
  /\bultra\w*\b/,
  /\bsky\s?race\b/,
  /\bskyrace\b/,
  /\bskyrunning\b/,
  /\bskogsmaraton\b/,
  /\bbackyard\b/,
  /\b\d+\s*hm\+?\b/,
];

const KNOWN_TERRAIN_EVENTS = [
  /\bzegama\b/,
  /\bmont[-\s]?blanc\b/,
  /\butmb\b/,
  /\bval d aran\b/,
  /\bchianti ultra trail\b/,
  /\bgornergrat\b/,
  /\bzermatt\b/,
  /\blofoten skyrace\b/,
  /\bsynnfjell sky race\b/,
  /\beco\s?trail\b/,
  /\bhornindal rundt\b/,
  /\bnorefjell trail\b/,
  /\bsognefjord trail\b/,
  /\btorshov trail\b/,
  /\btrail des maures\b/,
  /\bsandnes ultratrail\b/,
  /\bromeriksasen pa langs\b/,
  /\bnosen hundreds\b/,
  /\bskyrunning youth world championships\b/,
];

const MAJOR_EVENT_PATTERNS = [
  { pattern: /\b(vm|world championship|world championships|verdensmesterskap)\b/, score: 920 },
  { pattern: /\b(em|european championship|european championships|europamesterskap|european cup)\b/, score: 780 },
  { pattern: /\b(nm|norgesmesterskap|nordisk mesterskap|nordic senior championships)\b/, score: 680 },
  { pattern: /\b(zegama|mont[-\s]?blanc|utmb|val d aran|chianti ultra trail)\b/, score: 1200 },
  { pattern: /\b(skyrunning youth world championships|gornergrat|zermatt|lofoten skyrace|synnfjell sky race)\b/, score: 760 },
  { pattern: /\b(boston marathon|london marathon|bislett games|diamond league|bauhaus galan|paavo nurmi games|track night vienna)\b/, score: 620 },
  { pattern: /\b(mesterskap|championship|cup)\b/, score: 360 },
];

export const TERRAIN_TYPE_LABELS = {
  fjellop: "Fjelløp",
  trail: "Trail",
  skyrace: "Skyrace",
  terreng: "Terreng",
  annet: "Annet",
};

export const TERRAIN_FILTER_TYPES = ["fjellop", "trail", "skyrace", "terreng"];

function highlightText(row) {
  return normalizeSearchText([row.notes_clean, row.event_label, row.distance].filter(Boolean).join(" "));
}

export function terrainTypeTags(row) {
  if (Array.isArray(row.terrain_tags) && row.terrain_tags.length) {
    return [...new Set(row.terrain_tags.filter(Boolean))];
  }
  const text = highlightText(row);
  if (!text) {
    return [];
  }

  const tags = [];
  if (/\bsky\s?race\b|\bskyrace\b|\bskyrunning\b/.test(text)) {
    tags.push("skyrace");
  }
  if (/\bfjell\w*\b|\bzegama\b|\bmont[-\s]?blanc\b|\bgornergrat\b|\bzermatt\b|\bmendi\b|\bnorefjell\b|\b\d+\s*hm\+?\b/.test(text)) {
    tags.push("fjellop");
  }
  if (/\btrail\b|\butmb\b|\bultratrail\b|\beco\s?trail\b/.test(text)) {
    tags.push("trail");
  }
  if (/\bterreng\w*\b|\bskogsmaraton\b|\bbrunkollen rundt\b|\bfurumo terrengl/.test(text)) {
    tags.push("terreng");
  }
  if (!tags.length && (TERRAIN_OR_TRAIL_PATTERNS.some((pattern) => pattern.test(text)) || KNOWN_TERRAIN_EVENTS.some((pattern) => pattern.test(text)))) {
    tags.push("annet");
  }
  return tags;
}

export function terrainTypeOf(row) {
  return terrainTypeTags(row)[0] || "";
}

function numericRank(value) {
  const text = String(value ?? "").trim();
  if (!text || /\b(dnf|dns|dq)\b/i.test(text)) {
    return null;
  }
  const match = text.match(/\d+/);
  if (!match) {
    return null;
  }
  const rank = Number(match[0]);
  return Number.isFinite(rank) && rank > 0 ? rank : null;
}

function placementScore(rank, scores) {
  if (!rank) {
    return 0;
  }
  if (rank === 1) {
    return scores.first;
  }
  if (rank <= 3) {
    return scores.top3;
  }
  if (rank <= 5) {
    return scores.top5;
  }
  if (rank <= 10) {
    return scores.top10;
  }
  if (rank <= 20) {
    return scores.top20;
  }
  if (rank <= 50) {
    return scores.top50;
  }
  return 0;
}

function majorEventScore(text) {
  return MAJOR_EVENT_PATTERNS.reduce((best, entry) => (entry.pattern.test(text) ? Math.max(best, entry.score) : best), 0);
}

function noteHighlightScore(row, text) {
  let score = 0;
  if (row.is_pb || /\b(pb|pers|personlig rekord)\b/.test(text)) {
    score += 120;
  } else if (row.is_sb || /\b(sb|sesongbeste)\b/.test(text)) {
    score += 80;
  }
  if (/\b(rekord|norgesrekord|klubbrekord)\b/.test(text)) {
    score += 120;
  }
  if (/\b(1\. kvinne|1\. mann|vinner|seier)\b/.test(text)) {
    score += 110;
  }
  return score;
}

function compareNewestThenRank(a, b) {
  const dateCompare = String(b.published_date || "").localeCompare(String(a.published_date || ""));
  if (dateCompare !== 0) {
    return dateCompare;
  }
  const placeCompare = (numericRank(a.place) || Number.POSITIVE_INFINITY) - (numericRank(b.place) || Number.POSITIVE_INFINITY);
  if (placeCompare !== 0) {
    return placeCompare;
  }
  return String(a.athlete_name || "").localeCompare(String(b.athlete_name || ""), "nb-NO");
}

export function isTerrainOrTrail(row) {
  const text = highlightText(row);
  if (!text) {
    return false;
  }
  if (terrainTypeTags(row).length) {
    return true;
  }
  const championshipTerrain = /\b(vm|em|nm)\b.*\b(fjell|terreng|trail|motbakke|ultra|skyrace|skyrunning)\b/.test(text);
  const terrainChampionship = /\b(fjell|terreng|trail|motbakke|ultra|skyrace|skyrunning)\b.*\b(vm|em|nm)\b/.test(text);
  return championshipTerrain || terrainChampionship;
}

export function performanceHighlightScore(row) {
  const text = highlightText(row);
  const place = numericRank(row.place);
  const classPlace = numericRank(row.class_place);

  return (
    majorEventScore(text) +
    placementScore(place, { first: 660, top3: 540, top5: 430, top10: 320, top20: 210, top50: 110 }) +
    placementScore(classPlace, { first: 280, top3: 220, top5: 170, top10: 110, top20: 60, top50: 25 }) +
    noteHighlightScore(row, text) +
    (isTerrainOrTrail(row) ? 80 : 0)
  );
}

function comparePerformanceHighlights(a, b) {
  const scoreCompare = performanceHighlightScore(b) - performanceHighlightScore(a);
  if (scoreCompare !== 0) {
    return scoreCompare;
  }
  return compareNewestThenRank(a, b);
}

// Uses the build-time normalization when present (schema v3); falls back to a
// plain standard-distance check for older payloads.
export function rankingDistanceOf(row) {
  if (row.ranking_distance !== undefined && row.ranking_distance !== null) {
    return String(row.ranking_distance);
  }
  const distance = String(row.distance || "").trim();
  return STANDARD_DISTANCE_SET.has(distance) ? distance : "";
}

export function waResults() {
  return memo("waResults", () => state.data.results.filter(hasFinitePoints));
}

export function seasonWaTopResults(limit) {
  const sorted = memo("seasonWaTop", () =>
    [...waResults()].sort((a, b) => Number(b.wa_points) - Number(a.wa_points)),
  );
  return sorted.slice(0, limit);
}

export function seasonWaPerPerson(limit) {
  const entries = memo("seasonWaPerPerson", () => {
    const byPerson = new Map();
    for (const row of waResults()) {
      if (!row.person_id) {
        continue;
      }
      let list = byPerson.get(row.person_id);
      if (!list) {
        list = [];
        byPerson.set(row.person_id, list);
      }
      list.push(row);
    }
    const summaries = [];
    for (const rows of byPerson.values()) {
      rows.sort((a, b) => Number(b.wa_points) - Number(a.wa_points));
      const top3 = rows.slice(0, 3);
      summaries.push({
        best: rows[0],
        waCount: rows.length,
        top3Average: rows.length >= 3 ? top3.reduce((sum, row) => sum + Number(row.wa_points), 0) / 3 : null,
      });
    }
    summaries.sort((a, b) => Number(b.best.wa_points) - Number(a.best.wa_points));
    return summaries;
  });
  return limit ? entries.slice(0, limit) : entries;
}

export function terrainHighlights(limit = 6) {
  const sorted = memo("terrainHighlights", () =>
    state.data.results.filter((row) => isTerrainOrTrail(row) && !hasFinitePoints(row)).sort(comparePerformanceHighlights),
  );
  return limit ? sorted.slice(0, limit) : sorted;
}

function compareTerrainEventGroups(a, b) {
  const weekCompare = Number(b.latestWeek || 0) - Number(a.latestWeek || 0);
  if (weekCompare !== 0) {
    return weekCompare;
  }
  const dateCompare = String(b.latestDate || "").localeCompare(String(a.latestDate || ""));
  if (dateCompare !== 0) {
    return dateCompare;
  }
  const scoreCompare = Number(b.bestScore || 0) - Number(a.bestScore || 0);
  if (scoreCompare !== 0) {
    return scoreCompare;
  }
  const countCompare = Number(b.count || 0) - Number(a.count || 0);
  if (countCompare !== 0) {
    return countCompare;
  }
  return String(a.event_label || "").localeCompare(String(b.event_label || ""), "nb-NO");
}

export function terrainEventGroups({ type = "all", limit = 6 } = {}) {
  const groups = memo("terrainEventGroups", () => {
    const byEvent = new Map();
    for (const row of state.data.results) {
      if (!isTerrainOrTrail(row) || hasFinitePoints(row)) {
        continue;
      }
      const eventLabel = String(row.event_label || "").trim() || "Ukjent løp";
      const eventKey = String(row.event_id || eventLabel);
      let entry = byEvent.get(eventKey);
      if (!entry) {
        entry = {
          event_label: eventLabel,
          rows: [],
          types: new Set(),
          weeks: new Set(),
          count: 0,
          women: 0,
          men: 0,
          best: row,
          bestScore: Number.NEGATIVE_INFINITY,
          latestDate: "",
          latestWeek: 0,
        };
        byEvent.set(eventKey, entry);
      }

      const score = performanceHighlightScore(row);
      entry.rows.push(row);
      entry.count += 1;
      if (row.gender === "K") {
        entry.women += 1;
      } else if (row.gender === "M") {
        entry.men += 1;
      }
      for (const tag of terrainTypeTags(row)) {
        entry.types.add(tag);
      }
      if (row.week_number) {
        entry.weeks.add(Number(row.week_number));
        entry.latestWeek = Math.max(entry.latestWeek, Number(row.week_number));
      }
      if (String(row.published_date || "") > entry.latestDate) {
        entry.latestDate = String(row.published_date || "");
      }
      if (score > entry.bestScore || (score === entry.bestScore && compareNewestThenRank(row, entry.best) < 0)) {
        entry.best = row;
        entry.bestScore = score;
      }
    }

    return [...byEvent.values()]
      .map((entry) => ({
        ...entry,
        types: [...entry.types],
        weeks: [...entry.weeks].sort((a, b) => b - a),
      }))
      .sort(compareTerrainEventGroups);
  });

  const filtered = type && type !== "all" ? groups.filter((entry) => entry.types.includes(type)) : groups;
  return limit ? filtered.slice(0, limit) : filtered;
}

// Full best-per-person rankings per standard distance, same ordering rules as
// the precomputed top-10 payload. Map key: `${distance}|${gender}`.
export function fullRankings() {
  return memo("fullRankings", () => {
    const rankings = new Map();
    const bestPerPerson = new Map();

    for (const row of state.data.results) {
      const distance = rankingDistanceOf(row);
      if (!distance || !hasFiniteTime(row) || !row.person_id) {
        continue;
      }
      if (row.gender !== "K" && row.gender !== "M") {
        continue;
      }
      const key = `${distance}|${row.gender}|${row.person_id}`;
      const existing = bestPerPerson.get(key);
      if (
        !existing ||
        Number(row.result_time_seconds) < Number(existing.result_time_seconds) ||
        (Number(row.result_time_seconds) === Number(existing.result_time_seconds) &&
          String(row.published_date || "") < String(existing.published_date || ""))
      ) {
        bestPerPerson.set(key, row);
      }
    }

    for (const [key, row] of bestPerPerson) {
      const [distance, gender] = key.split("|");
      const groupKey = `${distance}|${gender}`;
      let list = rankings.get(groupKey);
      if (!list) {
        list = [];
        rankings.set(groupKey, list);
      }
      list.push(row);
    }

    for (const list of rankings.values()) {
      list.sort((a, b) => {
        const diff = Number(a.result_time_seconds) - Number(b.result_time_seconds);
        if (diff !== 0) {
          return diff;
        }
        const dateCompare = String(a.published_date || "").localeCompare(String(b.published_date || ""));
        if (dateCompare !== 0) {
          return dateCompare;
        }
        return String(a.athlete_name || "").localeCompare(String(b.athlete_name || ""), "nb-NO");
      });
    }

    return rankings;
  });
}

export function fullRankingList(distance, gender) {
  return fullRankings().get(`${distance}|${gender}`) || [];
}

export function clubRank(personId, distance, gender) {
  if (!personId || !distance || (gender !== "K" && gender !== "M")) {
    return null;
  }
  const list = fullRankingList(distance, gender);
  const index = list.findIndex((row) => row.person_id === personId);
  if (index === -1) {
    return null;
  }
  return { rank: index + 1, total: list.length };
}

export function participationTop(limit) {
  const sorted = memo("participationTop", () => {
    const profiles = [...(state.data.people?.profiles || [])];
    profiles.sort((a, b) => {
      const diff = Number(b.result_count || 0) - Number(a.result_count || 0);
      if (diff !== 0) {
        return diff;
      }
      return normalizeSearchText(a.display_name).localeCompare(normalizeSearchText(b.display_name), "nb-NO");
    });
    return profiles;
  });
  return limit ? sorted.slice(0, limit) : sorted;
}

export function latestPbResults(limit) {
  const sorted = memo("latestPbResults", () => sortResultsNewestFirst(state.data.results.filter((row) => row.is_pb || row.is_sb)));
  return limit ? sorted.slice(0, limit) : sorted;
}

export function biggestEvents(limit) {
  const sorted = memo("biggestEvents", () => {
    const byEvent = new Map();
    for (const row of state.data.results) {
      const label = String(row.event_label || "").trim();
      if (!label) {
        continue;
      }
      let entry = byEvent.get(label);
      if (!entry) {
        entry = {
          event_label: label,
          resultCount: 0,
          athletes: new Set(),
          women: new Set(),
          men: new Set(),
          weeks: new Set(),
        };
        byEvent.set(label, entry);
      }
      entry.resultCount += 1;
      const athleteKey = row.person_id || normalizeSearchText(row.athlete_name || "");
      if (athleteKey) {
        entry.athletes.add(athleteKey);
      }
      if (row.gender === "K") {
        entry.women.add(athleteKey);
      } else if (row.gender === "M") {
        entry.men.add(athleteKey);
      }
      if (row.week_number) {
        entry.weeks.add(Number(row.week_number));
      }
    }
    const entries = [...byEvent.values()].map((entry) => ({
      event_label: entry.event_label,
      count: entry.athletes.size,
      resultCount: entry.resultCount,
      women: entry.women.size,
      men: entry.men.size,
      weeks: [...entry.weeks].sort((a, b) => a - b),
    }));
    entries.sort((a, b) => b.count - a.count || a.event_label.localeCompare(b.event_label, "nb-NO"));
    return entries;
  });
  return limit ? sorted.slice(0, limit) : sorted;
}

export function weekTopPerformances(weekNumber, limit = 3) {
  const week = state.data.weeks.find((entry) => Number(entry.week_number) === Number(weekNumber));
  if (week && Array.isArray(week.top_performances)) {
    return week.top_performances.slice(0, limit);
  }
  return getWeekResults(weekNumber)
    .filter(hasFinitePoints)
    .sort((a, b) => Number(b.wa_points) - Number(a.wa_points))
    .slice(0, limit);
}

const MONTH_LABELS = {
  "01": "Januar",
  "02": "Februar",
  "03": "Mars",
  "04": "April",
  "05": "Mai",
  "06": "Juni",
  "07": "Juli",
  "08": "August",
  "09": "September",
  "10": "Oktober",
  "11": "November",
  "12": "Desember",
};

export function monthsSeries() {
  if (Array.isArray(state.data.months) && state.data.months.length) {
    return state.data.months;
  }
  return memo("monthsFallback", () => {
    const byMonth = new Map();
    for (const row of state.data.results) {
      const month = String(row.published_date || "").slice(0, 7);
      if (!month) {
        continue;
      }
      let entry = byMonth.get(month);
      if (!entry) {
        entry = { month, month_label: MONTH_LABELS[month.slice(5, 7)] || month, result_count: 0, women_count: 0, men_count: 0, athletes: new Set(), events: new Set() };
        byMonth.set(month, entry);
      }
      entry.result_count += 1;
      if (row.gender === "K") {
        entry.women_count += 1;
      } else if (row.gender === "M") {
        entry.men_count += 1;
      }
      if (row.person_id) {
        entry.athletes.add(row.person_id);
      }
      if (row.event_label) {
        entry.events.add(row.event_label);
      }
    }
    return [...byMonth.values()]
      .sort((a, b) => a.month.localeCompare(b.month))
      .map((entry) => ({
        month: entry.month,
        month_label: entry.month_label,
        result_count: entry.result_count,
        women_count: entry.women_count,
        men_count: entry.men_count,
        athlete_count: entry.athletes.size,
        event_count: entry.events.size,
      }));
  });
}

export function weeksAscending() {
  return memo("weeksAscending", () => [...state.data.weeks].sort((a, b) => Number(a.week_number) - Number(b.week_number)));
}

// Distances where the person has at least two timed results, ordered by how
// many results they have on each (most first).
export function progressionDistances(personId) {
  const counts = new Map();
  for (const row of resultsForPerson(personId)) {
    const distance = rankingDistanceOf(row);
    if (!distance || !hasFiniteTime(row)) {
      continue;
    }
    counts.set(distance, (counts.get(distance) || 0) + 1);
  }
  return [...counts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1] || STANDARD_DISTANCES.indexOf(a[0]) - STANDARD_DISTANCES.indexOf(b[0]))
    .map(([distance]) => distance);
}

export function progressionSeries(personId, distance) {
  return resultsForPerson(personId)
    .filter((row) => rankingDistanceOf(row) === distance && hasFiniteTime(row) && row.published_date)
    .sort((a, b) => String(a.published_date).localeCompare(String(b.published_date)));
}
