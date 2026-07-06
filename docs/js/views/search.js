import { state } from "../state.js";
import { escapeHtml, formatCount, getEventLabel, normalizeSearchText } from "../format.js";
import { hrefSearch, hrefWeek, replaceHash } from "../router.js";
import { genderPill, personLink, resultCardHtml } from "../templates.js";

const PERSON_LIMIT = 25;
const RESULT_LIMIT = 100;

let container = null;
let inputEl = null;
let resultsEl = null;
let renderFrame = 0;

function mount() {
  if (inputEl) {
    return;
  }
  container.innerHTML = `
    <section class="search-shell" aria-label="Globalt søk">
      <div class="section-header">
        <div>
          <p class="section-kicker">Hele sesongen</p>
          <h2 class="section-heading">Søk</h2>
        </div>
        <p class="section-copy">Finn løpere og resultater på tvers av alle uker.</p>
      </div>
      <label class="field search-field">
        <span>Søk etter løper, løp eller notat</span>
        <input id="global-search-input" type="search" placeholder="F.eks. et navn eller «Sentrumsløpet»" autocomplete="off" />
      </label>
      <div id="global-search-results" class="search-results" aria-live="polite"></div>
    </section>
  `;
  inputEl = container.querySelector("#global-search-input");
  resultsEl = container.querySelector("#global-search-results");

  inputEl.addEventListener("input", (event) => {
    const query = event.target.value;
    replaceHash(hrefSearch(query));
    cancelAnimationFrame(renderFrame);
    renderFrame = requestAnimationFrame(() => renderResults(query));
  });
}

function matchPeople(query) {
  const profiles = state.data.people?.profiles || [];
  return profiles.filter((profile) => normalizeSearchText(profile.display_name).includes(query));
}

function matchResults(query) {
  return state.data.results.filter((row) => {
    const text = normalizeSearchText(
      [
        row.athlete_name,
        getEventLabel(row),
        row.notes_clean,
        row.distance,
        row.gender_label,
        row.class_name,
      ]
        .filter(Boolean)
        .join(" "),
    );
    return text.includes(query);
  });
}

function personRowHtml(profile) {
  const latest = profile.latest_result_date ? ` · Sist: ${escapeHtml(profile.latest_result_date)}` : "";
  return `
    <li class="search-person-row">
      ${genderPill(profile.gender)}
      <strong>${personLink(profile)}</strong>
      <span class="muted">${formatCount(profile.result_count)} resultater${latest}</span>
    </li>
  `;
}

function renderResults(rawQuery) {
  const query = normalizeSearchText(rawQuery);
  if (!query) {
    resultsEl.innerHTML = `<p class="empty-state">Skriv i feltet over for å søke i hele sesongen.</p>`;
    return;
  }

  const people = matchPeople(query);
  const results = matchResults(query);

  const peopleHtml = people.length
    ? `<ul class="search-person-list">${people.slice(0, PERSON_LIMIT).map(personRowHtml).join("")}</ul>${
        people.length > PERSON_LIMIT ? `<p class="muted search-cap-note">Viser ${PERSON_LIMIT} av ${formatCount(people.length)} personer.</p>` : ""
      }`
    : `<p class="empty-state">Ingen personer matcher.</p>`;

  const groups = new Map();
  for (const row of results.slice(0, RESULT_LIMIT)) {
    const key = Number(row.week_number);
    let group = groups.get(key);
    if (!group) {
      group = { week_number: key, published_date_label: row.published_date_label, rows: [] };
      groups.set(key, group);
    }
    group.rows.push(row);
  }
  const orderedGroups = [...groups.values()].sort((a, b) => b.week_number - a.week_number);

  const resultsHtml = results.length
    ? `${orderedGroups
        .map(
          (group) => `
            <h4 class="search-week-heading"><a class="quiet-link" href="${hrefWeek(group.week_number)}">Uke ${group.week_number} · ${escapeHtml(group.published_date_label || "")}</a></h4>
            <div class="search-result-cards">${group.rows.map(resultCardHtml).join("")}</div>
          `,
        )
        .join("")}${
        results.length > RESULT_LIMIT
          ? `<p class="muted search-cap-note">Viser ${RESULT_LIMIT} av ${formatCount(results.length)} treff — avgrens søket.</p>`
          : ""
      }`
    : "";

  if (!people.length && !results.length) {
    resultsEl.innerHTML = `<p class="empty-state">Ingen treff for «${escapeHtml(rawQuery.trim())}».</p>`;
    return;
  }

  resultsEl.innerHTML = `
    <section class="search-section">
      <h3 class="search-section-heading">Personer <span>${formatCount(people.length)}</span></h3>
      ${peopleHtml}
    </section>
    <section class="search-section">
      <h3 class="search-section-heading">Resultater <span>${formatCount(results.length)}</span></h3>
      ${results.length ? resultsHtml : `<p class="empty-state">Ingen resultater matcher.</p>`}
    </section>
  `;
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render(params) {
  mount();
  const query = params.q || "";
  if (document.activeElement !== inputEl) {
    inputEl.value = query;
  }
  renderResults(query);
  if (!query) {
    inputEl.focus();
  }
}
