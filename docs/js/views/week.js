import { state, latestWeek, getWeek, getWeekResults } from "../state.js";
import { escapeHtml, formatCount, formatEventLabel, getEventLabel, normalizeSearchText, preferredScrollBehavior } from "../format.js";
import { hrefSearch, hrefWeek, replaceHash } from "../router.js";
import { resultCardHtml, resultTableRowHtml } from "../templates.js";
import { hasFinitePoints } from "../derive.js";

const current = {
  week: null,
  gender: "all",
  distance: "Alle",
  event: "Alle",
  search: "",
  grouping: "",
};

const DISTANCE_ORDER = ["600 m", "800 m", "1500 m", "3000 m", "5000 m", "5 km", "10 km", "Halvmaraton", "Maraton", "42 km", "30 km", "60 km"];

let els = null;
let searchRenderFrame = 0;
let copyStatusTimer = 0;

function grabElements() {
  els = {
    weeksList: document.getElementById("weeks-list"),
    weekSelect: document.getElementById("week-select"),
    selectedWeekTitle: document.getElementById("selected-week-title"),
    selectedWeekMeta: document.getElementById("selected-week-meta"),
    selectedWeekStats: document.getElementById("selected-week-stats"),
    resultsTable: document.getElementById("results-table"),
    resultsCards: document.getElementById("results-cards"),
    emptyState: document.getElementById("empty-state"),
    searchInput: document.getElementById("search-input"),
    distanceFilter: document.getElementById("distance-filter"),
    eventFilter: document.getElementById("event-filter"),
    weekPrev: document.getElementById("week-prev"),
    weekNext: document.getElementById("week-next"),
    copyLink: document.getElementById("copy-link"),
    copyStatus: document.getElementById("copy-status"),
    groupToggle: document.getElementById("group-toggle"),
    globalSearchHint: document.getElementById("global-search-hint"),
    genderButtons: {
      all: document.getElementById("gender-all"),
      women: document.getElementById("gender-women"),
      men: document.getElementById("gender-men"),
    },
  };
}

function genderParamValue() {
  if (current.gender === "women") {
    return "k";
  }
  if (current.gender === "men") {
    return "m";
  }
  return "";
}

function parseGenderParam(value) {
  if (value === "k") {
    return "women";
  }
  if (value === "m") {
    return "men";
  }
  return "all";
}

function filterParams({ includeEvent = true } = {}) {
  return {
    kjonn: genderParamValue(),
    distanse: current.distance !== "Alle" ? current.distance : "",
    lop: includeEvent && current.event !== "Alle" ? current.event : "",
    sok: current.search || "",
    gruppering: current.grouping || "",
  };
}

function syncUrl() {
  replaceHash(hrefWeek(current.week, filterParams()));
}

function scheduleResultsRender() {
  cancelAnimationFrame(searchRenderFrame);
  searchRenderFrame = requestAnimationFrame(() => {
    renderResults();
  });
}

function scrollSelectedWeekIntoView() {
  const selected = els.weeksList?.querySelector(".week-item.is-active");
  if (!selected) {
    return;
  }
  selected.scrollIntoView({ behavior: preferredScrollBehavior(), inline: "center", block: "nearest" });
}

function scrollActiveEventIntoView() {
  const selected = els.eventFilter?.querySelector(".event-chip.is-active");
  if (!selected) {
    return;
  }
  selected.scrollIntoView({ behavior: preferredScrollBehavior(), inline: "center", block: "nearest" });
}

function getWeekEvents(weekNumber, results = getWeekResults(weekNumber)) {
  const counts = new Map();
  results.forEach((row) => {
    const eventName = getEventLabel(row);
    if (eventName) {
      counts.set(eventName, (counts.get(eventName) || 0) + 1);
    }
  });
  return Array.from(counts.entries())
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }
      return a[0].localeCompare(b[0], "nb-NO");
    })
    .map(([eventName]) => eventName);
}

function genderMatches(row) {
  if (current.gender === "women") {
    return row.gender === "K";
  }
  if (current.gender === "men") {
    return row.gender === "M";
  }
  return true;
}

function getFilteredResults() {
  const weekResults = getWeekResults(current.week);
  const query = normalizeSearchText(current.search);

  return weekResults.filter((row) => {
    const eventName = getEventLabel(row);
    const text = normalizeSearchText(
      [
        row.athlete_name,
        eventName,
        row.notes_clean,
        row.notes,
        row.distance,
        row.gender_label,
        row.class_name,
        row.split_first_display,
        row.split_second_display,
        row.split_delta_display,
      ]
        .filter(Boolean)
        .join(" "),
    );

    const matchesSearch = !query || text.includes(query);
    const matchesEvent = current.event === "Alle" || eventName === current.event;
    const matchesDistance = current.distance === "Alle" || String(row.distance ?? "") === current.distance;
    return matchesEvent && matchesSearch && matchesDistance && genderMatches(row);
  });
}

function renderWeeksList() {
  els.weeksList.innerHTML = state.data.weeks
    .map((week) => {
      const active = Number(week.week_number) === Number(current.week);
      const events = week.events.map(formatEventLabel).join(", ");
      const href = hrefWeek(week.week_number, filterParams({ includeEvent: false }));
      return `
        <a class="week-item${active ? " is-active" : ""}" href="${escapeHtml(href)}"${active ? ' aria-current="true"' : ""}>
          <div class="week-top">
            <span class="week-label">${escapeHtml(week.week_label)}</span>
            <span class="week-date">${escapeHtml(week.published_date_label)}</span>
          </div>
          <span class="week-count">${formatCount(week.result_count)} resultater</span>
          <span class="week-balance">${formatCount(week.women_count)} kvinner · ${formatCount(week.men_count)} menn</span>
          <span class="week-events">${escapeHtml(events || "Ingen registrerte løp")}</span>
        </a>
      `;
    })
    .join("");
}

function renderWeekSelect() {
  els.weekSelect.innerHTML = state.data.weeks
    .map((week) => {
      const selected = Number(week.week_number) === Number(current.week);
      const label = `${week.week_label} - ${week.published_date_label} - ${formatCount(week.result_count)} resultater`;
      return `<option value="${escapeHtml(week.week_number)}"${selected ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function renderPrevNext() {
  const numbers = state.data.weeks.map((week) => Number(week.week_number)).sort((a, b) => a - b);
  const index = numbers.indexOf(Number(current.week));
  const prev = index > 0 ? numbers[index - 1] : null;
  const next = index !== -1 && index < numbers.length - 1 ? numbers[index + 1] : null;

  els.weekPrev.hidden = prev === null;
  els.weekNext.hidden = next === null;
  if (prev !== null) {
    els.weekPrev.href = hrefWeek(prev, filterParams({ includeEvent: false }));
    els.weekPrev.textContent = `← Uke ${prev}`;
  }
  if (next !== null) {
    els.weekNext.href = hrefWeek(next, filterParams({ includeEvent: false }));
    els.weekNext.textContent = `Uke ${next} →`;
  }
}

function renderGenderButtons() {
  Object.entries(els.genderButtons).forEach(([key, button]) => {
    const active = current.gender === key;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function renderGroupToggle() {
  const active = current.grouping === "lop";
  els.groupToggle.classList.toggle("is-active", active);
  els.groupToggle.setAttribute("aria-pressed", active ? "true" : "false");
}

function renderEventButtons() {
  const events = ["Alle", ...getWeekEvents(current.week)];
  if (!events.includes(current.event)) {
    current.event = "Alle";
  }

  els.eventFilter.innerHTML = events
    .map((eventName) => {
      const active = current.event === eventName;
      return `
        <button
          class="event-chip${active ? " is-active" : ""}"
          type="button"
          data-event="${escapeHtml(eventName)}"
          aria-pressed="${active ? "true" : "false"}"
        >
          ${escapeHtml(eventName)}
        </button>
      `;
    })
    .join("");
}

function renderGlobalSearchHint() {
  const query = current.search.trim();
  if (!query) {
    els.globalSearchHint.hidden = true;
    return;
  }
  els.globalSearchHint.hidden = false;
  els.globalSearchHint.href = hrefSearch(query);
  els.globalSearchHint.textContent = `Søk i hele sesongen etter «${query}» →`;
}

function groupResults(results) {
  const groups = new Map();
  for (const row of results) {
    const eventName = getEventLabel(row) || "Uten løpsnavn";
    let group = groups.get(eventName);
    if (!group) {
      group = [];
      groups.set(eventName, group);
    }
    group.push(row);
  }
  return Array.from(groups.entries()).sort((a, b) => {
    if (b[1].length !== a[1].length) {
      return b[1].length - a[1].length;
    }
    return a[0].localeCompare(b[0], "nb-NO");
  });
}

function renderResultsTable(results) {
  if (current.grouping === "lop") {
    els.resultsTable.innerHTML = groupResults(results)
      .map(
        ([eventName, rows]) => `
          <tr class="group-row"><th colspan="12" scope="colgroup">${escapeHtml(eventName)} <span>${formatCount(rows.length)} resultater</span></th></tr>
          ${rows.map(resultTableRowHtml).join("")}
        `,
      )
      .join("");
    return;
  }
  els.resultsTable.innerHTML = results.map(resultTableRowHtml).join("");
}

function renderResultsCards(results) {
  if (current.grouping === "lop") {
    els.resultsCards.innerHTML = groupResults(results)
      .map(
        ([eventName, rows]) => `
          <h3 class="card-group-heading">${escapeHtml(eventName)} <span>${formatCount(rows.length)}</span></h3>
          ${rows.map(resultCardHtml).join("")}
        `,
      )
      .join("");
    return;
  }
  els.resultsCards.innerHTML = results.map(resultCardHtml).join("");
}

function renderResults() {
  const week = getWeek(current.week);
  const results = getFilteredResults();

  if (!week) {
    els.selectedWeekTitle.textContent = "Ingen uke valgt";
    els.selectedWeekMeta.textContent = "";
    els.selectedWeekStats.innerHTML = "";
    els.resultsTable.innerHTML = "";
    els.resultsCards.innerHTML = "";
    els.emptyState.hidden = false;
    return;
  }

  els.selectedWeekTitle.textContent = week.week_label;
  els.selectedWeekMeta.textContent = `${week.published_date_label} · ${formatCount(week.result_count)} resultater · ${formatCount(week.athlete_count)} løpere · ${formatCount(week.event_count)} løp`;

  const womenCount = results.filter((row) => row.gender === "K").length;
  const menCount = results.filter((row) => row.gender === "M").length;
  const waCount = results.filter(hasFinitePoints).length;

  els.selectedWeekStats.innerHTML = `
    <div><span class="label">Viser</span><span class="value">${formatCount(results.length)}</span></div>
    <div><span class="label">Kvinner</span><span class="value">${formatCount(womenCount)}</span></div>
    <div><span class="label">Menn</span><span class="value">${formatCount(menCount)}</span></div>
    <div><span class="label">Med WA-poeng</span><span class="value">${formatCount(waCount)}</span></div>
  `;

  renderGlobalSearchHint();

  if (results.length === 0) {
    els.resultsTable.innerHTML = "";
    els.resultsCards.innerHTML = "";
    els.emptyState.hidden = false;
    return;
  }

  els.emptyState.hidden = true;
  renderResultsTable(results);
  renderResultsCards(results);
}

function renderDistanceOptions() {
  const actualDistances = Array.from(new Set(state.data.results.map((row) => String(row.distance ?? "").trim()).filter(Boolean)));
  const orderedDistances = DISTANCE_ORDER.filter((distance) => actualDistances.includes(distance));
  const remainingDistances = actualDistances.filter((distance) => !DISTANCE_ORDER.includes(distance)).sort();
  const options = ["Alle", ...orderedDistances, ...remainingDistances];

  els.distanceFilter.innerHTML = options
    .map((distance) => `<option value="${escapeHtml(distance)}">${escapeHtml(distance)}</option>`)
    .join("");
}

async function copyCurrentLink() {
  const url = window.location.href;
  try {
    await navigator.clipboard.writeText(url);
    els.copyStatus.textContent = "Lenke kopiert!";
  } catch {
    window.prompt("Kopier lenken:", url);
    els.copyStatus.textContent = "";
    return;
  }
  clearTimeout(copyStatusTimer);
  copyStatusTimer = setTimeout(() => {
    els.copyStatus.textContent = "";
  }, 2200);
}

export function init() {
  grabElements();
  renderDistanceOptions();

  els.searchInput.addEventListener("input", (event) => {
    current.search = event.target.value;
    syncUrl();
    scheduleResultsRender();
  });

  els.distanceFilter.addEventListener("change", (event) => {
    current.distance = event.target.value;
    syncUrl();
    renderResults();
  });

  els.weekSelect.addEventListener("change", (event) => {
    window.location.hash = hrefWeek(event.target.value, filterParams({ includeEvent: false }));
  });

  els.eventFilter.addEventListener("click", (event) => {
    const chip = event.target.closest(".event-chip");
    if (!chip) {
      return;
    }
    current.event = chip.dataset.event || "Alle";
    syncUrl();
    renderEventButtons();
    renderResults();
    requestAnimationFrame(scrollActiveEventIntoView);
  });

  Object.entries(els.genderButtons).forEach(([key, button]) => {
    button.addEventListener("click", () => {
      current.gender = key;
      syncUrl();
      renderGenderButtons();
      renderResults();
    });
  });

  els.groupToggle.addEventListener("click", () => {
    current.grouping = current.grouping === "lop" ? "" : "lop";
    syncUrl();
    renderGroupToggle();
    renderResults();
  });

  els.copyLink.addEventListener("click", copyCurrentLink);
}

export function render(params) {
  if (params.week === null || params.week === undefined) {
    window.location.replace(hrefWeek(latestWeek(), {}));
    return;
  }
  if (!getWeek(params.week)) {
    window.location.replace(hrefWeek(latestWeek(), {}));
    return;
  }

  current.week = Number(params.week);
  current.gender = parseGenderParam(params.kjonn || "");
  current.search = params.sok || "";
  current.event = params.lop || "Alle";
  current.grouping = params.gruppering === "lop" ? "lop" : "";

  const requestedDistance = params.distanse || "Alle";
  const hasDistance = Array.from(els.distanceFilter.options).some((option) => option.value === requestedDistance);
  current.distance = hasDistance ? requestedDistance : "Alle";

  if (document.activeElement !== els.searchInput) {
    els.searchInput.value = current.search;
  }
  els.distanceFilter.value = current.distance;

  renderWeeksList();
  renderWeekSelect();
  renderPrevNext();
  renderGenderButtons();
  renderGroupToggle();
  renderEventButtons();
  renderResults();
  requestAnimationFrame(scrollSelectedWeekIntoView);
}
