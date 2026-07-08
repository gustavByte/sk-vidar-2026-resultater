const STATS_SECTIONS = new Set(["hoydepunkter", "topp-10", "wa", "deltakelse", "maneder", "lop"]);

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && String(value) !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function parseQuery(queryString) {
  const params = {};
  for (const [key, value] of new URLSearchParams(queryString || "")) {
    params[key] = value;
  }
  return params;
}

export function hrefWeek(weekNumber, filters = {}) {
  const base = weekNumber === null || weekNumber === undefined ? "#/uke" : `#/uke/${encodeURIComponent(weekNumber)}`;
  return `${base}${buildQuery(filters)}`;
}

export function hrefPerson(slug) {
  return slug ? `#/person/${encodeURIComponent(slug)}` : "#/";
}

export function hrefPeople(params = {}) {
  return `#/personer${buildQuery(params)}`;
}

export function hrefStats(section = "") {
  return section ? `#/statistikk/${encodeURIComponent(section)}` : "#/statistikk";
}

export function hrefSearch(query = "") {
  return `#/sok${buildQuery({ q: query })}`;
}

export function hrefDashboard() {
  return "#/";
}

// Parses a location.hash string to { view, params } without touching the DOM.
export function parseHash(rawHash) {
  const hash = String(rawHash || "");

  if (hash === "#season-top-10") {
    return { view: "stats", params: { section: "topp-10" }, replace: hrefStats("topp-10") };
  }

  if (!hash || hash === "#" || hash === "#/") {
    return { view: "dashboard", params: {} };
  }

  if (!hash.startsWith("#/")) {
    return { view: "dashboard", params: {} };
  }

  const queryIndex = hash.indexOf("?");
  const path = queryIndex === -1 ? hash.slice(2) : hash.slice(2, queryIndex);
  const query = queryIndex === -1 ? "" : hash.slice(queryIndex + 1);
  const segments = path.split("/").filter(Boolean).map((segment) => decodeURIComponent(segment));
  const params = parseQuery(query);

  if (segments.length === 0) {
    return { view: "dashboard", params: {} };
  }

  switch (segments[0]) {
    case "uke": {
      const week = segments.length > 1 ? Number(segments[1]) : null;
      return { view: "week", params: { ...params, week: Number.isFinite(week) ? week : null } };
    }
    case "personer":
      return { view: "people", params };
    case "person":
      return segments.length > 1 ? { view: "person", params: { slug: segments[1] } } : { view: "people", params: {} };
    case "statistikk": {
      const section = segments.length > 1 && STATS_SECTIONS.has(segments[1]) ? segments[1] : "";
      return { view: "stats", params: { section } };
    }
    case "sok":
      return { view: "search", params: { q: params.q || "" } };
    default:
      return { view: "dashboard", params: {} };
  }
}

// Rewrites the current hash without adding a history entry and without
// triggering hashchange (used while typing in filters).
export function replaceHash(href) {
  if (`#${window.location.hash.slice(1)}` === href) {
    return;
  }
  history.replaceState(null, "", href);
}
