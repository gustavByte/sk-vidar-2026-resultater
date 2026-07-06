export const state = {
  data: null,
  peopleById: new Map(),
  personIdBySlug: new Map(),
  slugRedirects: new Map(),
  resultsByPerson: new Map(),
};

function buildIndexes() {
  const people = state.data.people || {};
  const profiles = Array.isArray(people.profiles) ? people.profiles : [];
  state.peopleById = new Map(profiles.map((profile) => [profile.person_id, profile]));
  state.personIdBySlug = new Map(Object.entries(people.slug_map || {}));
  state.slugRedirects = new Map(Object.entries(people.slug_redirects || {}));

  state.resultsByPerson = new Map();
  for (const row of state.data.results) {
    if (!row.person_id) {
      continue;
    }
    let list = state.resultsByPerson.get(row.person_id);
    if (!list) {
      list = [];
      state.resultsByPerson.set(row.person_id, list);
    }
    list.push(row);
  }
}

export async function loadData() {
  const response = await fetch("./data/results.json", { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Kunne ikke lese data: ${response.status}`);
  }
  state.data = await response.json();
  buildIndexes();
}

export function latestWeek() {
  return Number(state.data.stats.latest_week);
}

export function getWeek(weekNumber) {
  return state.data.weeks.find((week) => Number(week.week_number) === Number(weekNumber));
}

export function getWeekResults(weekNumber) {
  return state.data.results.filter((row) => Number(row.week_number) === Number(weekNumber));
}

export function resultsForPerson(personId) {
  return state.resultsByPerson.get(personId) || [];
}
