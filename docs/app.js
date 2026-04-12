const distanceOrder = ["800 m", "1500 m", "3000 m", "5 km", "10 km", "Halvmaraton", "Maraton", "42 km", "30 km", "60 km"];

const state = {
  data: null,
  selectedWeek: null,
  search: "",
  distance: "Alle",
  eventFilter: "Alle",
  genderFilter: "all",
};

const numberFormat = new Intl.NumberFormat("nb-NO");

const els = {
  weeksList: document.getElementById("weeks-list"),
  selectedWeekTitle: document.getElementById("selected-week-title"),
  selectedWeekMeta: document.getElementById("selected-week-meta"),
  selectedWeekStats: document.getElementById("selected-week-stats"),
  resultsTable: document.getElementById("results-table"),
  resultsCards: document.getElementById("results-cards"),
  emptyState: document.getElementById("empty-state"),
  searchInput: document.getElementById("search-input"),
  distanceFilter: document.getElementById("distance-filter"),
  eventFilter: document.getElementById("event-filter"),
  statResults: document.getElementById("stat-results"),
  statAthletes: document.getElementById("stat-athletes"),
  statWomen: document.getElementById("stat-women"),
  statMen: document.getElementById("stat-men"),
  lastUpdated: document.getElementById("last-updated"),
  genderButtons: {
    all: document.getElementById("gender-all"),
    women: document.getElementById("gender-women"),
    men: document.getElementById("gender-men"),
  },
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return char;
    }
  });
}

function formatCount(value) {
  return numberFormat.format(value ?? 0);
}

function getWeekResults(weekNumber) {
  return state.data.results.filter((row) => Number(row.week_number) === Number(weekNumber));
}

function getSelectedWeek() {
  return state.data.weeks.find((week) => Number(week.week_number) === Number(state.selectedWeek));
}

function getEventLabel(row) {
  return String(row.event_label || row.event_name || "").trim();
}

function getWeekEvents(weekNumber) {
  const events = new Set();
  getWeekResults(weekNumber).forEach((row) => {
    const eventName = getEventLabel(row);
    if (eventName) {
      events.add(eventName);
    }
  });
  return Array.from(events).sort((a, b) => a.localeCompare(b, "nb-NO"));
}

function renderStats() {
  const { stats } = state.data;
  els.statResults.textContent = formatCount(stats.result_count);
  els.statAthletes.textContent = formatCount(stats.athlete_count);
  els.statWomen.textContent = formatCount(stats.women_count);
  els.statMen.textContent = formatCount(stats.men_count);
  els.lastUpdated.textContent = `Oppdatert ${new Date(state.data.generated_at).toLocaleString("nb-NO", {
    dateStyle: "long",
    timeStyle: "short",
  })}`;
}

function renderDistanceOptions() {
  const actualDistances = Array.from(new Set(state.data.results.map((row) => String(row.distance ?? "").trim()).filter(Boolean)));
  const orderedDistances = distanceOrder.filter((distance) => actualDistances.includes(distance));
  const remainingDistances = actualDistances.filter((distance) => !distanceOrder.includes(distance)).sort();
  const options = ["Alle", ...orderedDistances, ...remainingDistances];

  els.distanceFilter.innerHTML = options.map((distance) => `<option value="${escapeHtml(distance)}">${escapeHtml(distance)}</option>`).join("");
}

function renderWeeks() {
  els.weeksList.innerHTML = state.data.weeks
    .map((week) => {
      const active = Number(week.week_number) === Number(state.selectedWeek);
      const events = week.events.join(", ");
      return `
        <button class="week-item" type="button" role="listitem" aria-pressed="${active ? "true" : "false"}" data-week="${escapeHtml(week.week_number)}">
          <div class="week-top">
            <span class="week-label">${escapeHtml(week.week_label)}</span>
            <span class="week-date">${escapeHtml(week.published_date_label)}</span>
          </div>
          <span class="week-count">${formatCount(week.result_count)} resultater</span>
          <span class="week-balance">${formatCount(week.women_count)} kvinner · ${formatCount(week.men_count)} menn</span>
          <span class="week-events">${escapeHtml(events || "Ingen registrerte løp")}</span>
        </button>
      `;
    })
    .join("");

  els.weeksList.querySelectorAll(".week-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedWeek = Number(button.dataset.week);
      state.eventFilter = "Alle";
      renderAll();
    });
  });
}

function genderMatches(row) {
  if (state.genderFilter === "women") {
    return row.gender === "K";
  }
  if (state.genderFilter === "men") {
    return row.gender === "M";
  }
  return true;
}

function getFilteredResults() {
  const weekResults = getWeekResults(state.selectedWeek);
  const query = state.search.trim().toLowerCase();

  return weekResults.filter((row) => {
    const eventName = getEventLabel(row);
    const text = [
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
      .join(" ")
      .toLowerCase();

    const matchesSearch = !query || text.includes(query);
    const matchesEvent = state.eventFilter === "Alle" || eventName === state.eventFilter;
    const matchesDistance = state.distance === "Alle" || String(row.distance ?? "") === state.distance;
    return matchesEvent && matchesSearch && matchesDistance && genderMatches(row);
  });
}

function splitClass(row) {
  if (!row.split_state) {
    return "split-delta--empty";
  }
  if (row.split_state === "slow") {
    return "split-delta--slow";
  }
  if (row.split_state === "fast") {
    return "split-delta--fast";
  }
  return "split-delta--even";
}

function displayValue(value) {
  return value ? escapeHtml(value) : "—";
}

function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function renderResultsTable(results) {
  els.resultsTable.innerHTML = results
    .map((row) => {
      const place = displayValue(row.place);
      const classPlace = displayValue(row.class_place);
      const note = displayValue(row.notes_clean);
      const splitFirst = displayValue(row.split_first_display);
      const splitSecond = displayValue(row.split_second_display);
      const splitDelta = displayValue(row.split_delta_display);

      return `
        <tr>
          <td class="athlete">${escapeHtml(row.athlete_name || "")}</td>
          <td><span class="gender-pill">${displayValue(row.gender)}</span></td>
          <td>${displayValue(row.class_name)}</td>
          <td>${escapeHtml(getEventLabel(row))}</td>
          <td class="muted">${escapeHtml(row.distance || "")}</td>
          <td class="time">${escapeHtml(row.result_time_normalized || row.result_time_raw || "")}</td>
          <td class="split-time">${splitFirst}</td>
          <td class="split-time">${splitSecond}</td>
          <td class="split-delta ${splitClass(row)}">${splitDelta}</td>
          <td>${place}</td>
          <td>${classPlace}</td>
          <td class="muted">${note}</td>
        </tr>
      `;
    })
    .join("");
}

function renderResultsCards(results) {
  els.resultsCards.innerHTML = results
    .map((row) => {
      const metaParts = [
        hasValue(row.distance) ? `<span class="result-pill">${escapeHtml(row.distance)}</span>` : "",
        hasValue(row.class_name) ? `<span class="result-pill">${escapeHtml(row.class_name)}</span>` : "",
        hasValue(row.place) ? `<span class="result-pill">#${escapeHtml(row.place)}</span>` : "",
        hasValue(row.class_place) ? `<span class="result-pill result-pill--muted">Kl ${escapeHtml(row.class_place)}</span>` : "",
      ].filter(Boolean);

      const splitMarkup = row.split_first_display || row.split_second_display || row.split_delta_display
        ? `
          <div class="result-card-splits">
            ${hasValue(row.split_first_display) ? `<span class="result-pill"><strong>${escapeHtml(row.split_first_label || "Split 1")}</strong>${escapeHtml(row.split_first_display)}</span>` : ""}
            ${hasValue(row.split_second_display) ? `<span class="result-pill"><strong>${escapeHtml(row.split_second_label || "Split 2")}</strong>${escapeHtml(row.split_second_display)}</span>` : ""}
            ${hasValue(row.split_delta_display) ? `<span class="result-pill split-delta ${splitClass(row)}"><strong>Splitt</strong>${escapeHtml(row.split_delta_display)}</span>` : ""}
          </div>
        `
        : "";

      const noteMarkup = row.notes_clean ? `<div class="result-card-note">${escapeHtml(row.notes_clean)}</div>` : "";

      return `
        <article class="result-card">
          <div class="result-card-top">
            <div class="result-card-athlete">
              <strong class="result-card-name">${escapeHtml(row.athlete_name || "")}</strong>
              <span class="result-card-meta">${escapeHtml(getEventLabel(row))}</span>
            </div>
            <div class="result-card-side">
              <span class="gender-pill">${displayValue(row.gender)}</span>
              <div class="result-card-time">${escapeHtml(row.result_time_normalized || row.result_time_raw || "")}</div>
            </div>
          </div>
          ${metaParts.length ? `<div class="result-card-inline">${metaParts.join("")}</div>` : ""}
          ${splitMarkup}
          ${noteMarkup}
        </article>
      `;
    })
    .join("");
}

function renderGenderButtons() {
  Object.entries(els.genderButtons).forEach(([key, button]) => {
    button.classList.toggle("is-active", state.genderFilter === key);
  });
}

function renderEventButtons() {
  const events = ["Alle", ...getWeekEvents(state.selectedWeek)];
  if (!events.includes(state.eventFilter)) {
    state.eventFilter = "Alle";
  }

  els.eventFilter.innerHTML = events
    .map(
      (eventName) => `
        <button class="event-chip${state.eventFilter === eventName ? " is-active" : ""}" type="button" data-event="${escapeHtml(eventName)}">
          ${escapeHtml(eventName)}
        </button>
      `,
    )
    .join("");

  els.eventFilter.querySelectorAll(".event-chip").forEach((button) => {
    button.addEventListener("click", () => {
      state.eventFilter = button.dataset.event || "Alle";
      renderEventButtons();
      renderSelectedWeek();
    });
  });
}

function renderSelectedWeek() {
  const week = getSelectedWeek();
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
  const splitCount = results.filter((row) => row.split_state).length;

  els.selectedWeekStats.innerHTML = `
    <div><span class="label">Viser</span><span class="value">${formatCount(results.length)}</span></div>
    <div><span class="label">Kvinner</span><span class="value">${formatCount(womenCount)}</span></div>
    <div><span class="label">Menn</span><span class="value">${formatCount(menCount)}</span></div>
    <div><span class="label">Med splitter</span><span class="value">${formatCount(splitCount)}</span></div>
  `;

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

function renderAll() {
  renderGenderButtons();
  renderWeeks();
  renderEventButtons();
  renderSelectedWeek();
}

function bindFilters() {
  els.searchInput.addEventListener("input", (event) => {
    state.search = event.target.value;
    renderSelectedWeek();
  });

  els.distanceFilter.addEventListener("change", (event) => {
    state.distance = event.target.value;
    renderSelectedWeek();
  });

  els.genderButtons.all.addEventListener("click", () => {
    state.genderFilter = "all";
    renderAll();
  });
  els.genderButtons.women.addEventListener("click", () => {
    state.genderFilter = "women";
    renderAll();
  });
  els.genderButtons.men.addEventListener("click", () => {
    state.genderFilter = "men";
    renderAll();
  });
}

async function main() {
  const response = await fetch("./data/results.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Kunne ikke lese data: ${response.status}`);
  }

  state.data = await response.json();
  state.selectedWeek = Number(state.data.stats.latest_week);

  renderStats();
  renderDistanceOptions();
  bindFilters();
  renderAll();
}

main().catch((error) => {
  console.error(error);
  els.selectedWeekTitle.textContent = "Datafil mangler";
  els.selectedWeekMeta.textContent = "Kjør bygge-skriptet på nytt for å lage JSON og database.";
  els.emptyState.hidden = false;
  els.emptyState.textContent = "Data kunne ikke lastes.";
});
