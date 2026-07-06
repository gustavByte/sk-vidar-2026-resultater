import { state, getWeekResults, resultsForPerson } from "./state.js";
import { normalizeSearchText, sortResultsNewestFirst } from "./format.js";

const STANDARD_DISTANCES = ["800 m", "1500 m", "3000 m", "5000 m", "5 km", "10 km", "Halvmaraton", "Maraton"];
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
        entry = { event_label: label, count: 0, women: 0, men: 0, weeks: new Set() };
        byEvent.set(label, entry);
      }
      entry.count += 1;
      if (row.gender === "K") {
        entry.women += 1;
      } else if (row.gender === "M") {
        entry.men += 1;
      }
      if (row.week_number) {
        entry.weeks.add(Number(row.week_number));
      }
    }
    const entries = [...byEvent.values()].map((entry) => ({ ...entry, weeks: [...entry.weeks].sort((a, b) => a - b) }));
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
