const distanceOrder = [
  "800 m",
  "1500 m",
  "3000 m",
  "5 km",
  "10 km",
  "Halvmaraton",
  "Maraton",
  "42 km",
  "30 km",
  "60 km",
];

const state = {
  data: null,
  selectedWeek: null,
  search: "",
  distance: "Alle",
};

const numberFormat = new Intl.NumberFormat("nb-NO");

const els = {
  weeksList: document.getElementById("weeks-list"),
  selectedWeekTitle: document.getElementById("selected-week-title"),
  selectedWeekMeta: document.getElementById("selected-week-meta"),
  selectedWeekStats: document.getElementById("selected-week-stats"),
  resultsTable: document.getElementById("results-table"),
  emptyState: document.getElementById("empty-state"),
  searchInput: document.getElementById("search-input"),
  distanceFilter: document.getElementById("distance-filter"),
  statResults: document.getElementById("stat-results"),
  statAthletes: document.getElementById("stat-athletes"),
  statEvents: document.getElementById("stat-events"),
  statWeeks: document.getElementById("stat-weeks"),
  lastUpdated: document.getElementById("last-updated"),
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

function renderStats() {
  const { stats } = state.data;
  els.statResults.textContent = formatCount(stats.result_count);
  els.statAthletes.textContent = formatCount(stats.athlete_count);
  els.statEvents.textContent = formatCount(stats.event_count);
  els.statWeeks.textContent = formatCount(stats.week_count);
  els.lastUpdated.textContent = `Oppdatert ${new Date(state.data.generated_at).toLocaleString("nb-NO", {
    dateStyle: "long",
    timeStyle: "short",
  })}`;
}

function renderDistanceOptions() {
  const actualDistances = Array.from(
    new Set(state.data.results.map((row) => String(row.distance ?? "").trim()).filter(Boolean))
  );
  const orderedDistances = distanceOrder.filter((distance) => actualDistances.includes(distance));
  const remainingDistances = actualDistances.filter((distance) => !distanceOrder.includes(distance)).sort();
  const options = ["Alle", ...orderedDistances, ...remainingDistances];

  els.distanceFilter.innerHTML = options
    .map((distance) => `<option value="${escapeHtml(distance)}">${escapeHtml(distance)}</option>`)
    .join("");
}

function renderWeeks() {
  const maxResults = Math.max(...state.data.weeks.map((week) => week.result_count), 1);
  els.weeksList.innerHTML = state.data.weeks
    .map((week) => {
      const active = Number(week.week_number) === Number(state.selectedWeek);
      const width = Math.max(6, Math.round((week.result_count / maxResults) * 100));
      const events = week.events.join(", ");
      return `
        <button
          class="week-item"
          type="button"
          role="listitem"
          aria-pressed="${active ? "true" : "false"}"
          data-week="${escapeHtml(week.week_number)}"
        >
          <div class="week-top">
            <span class="week-label">${escapeHtml(week.week_label)}</span>
            <span class="week-date">${escapeHtml(week.published_date_label)}</span>
          </div>
          <span class="week-count">${formatCount(week.result_count)} resultater</span>
          <span class="week-events">${escapeHtml(events || "Ingen registrerte løp")}</span>
          <span class="week-bar" aria-hidden="true"><span style="--bar-width:${width}%"></span></span>
        </button>
      `;
    })
    .join("");

  els.weeksList.querySelectorAll(".week-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedWeek = Number(button.dataset.week);
      renderAll();
    });
  });
}

function getFilteredResults() {
  const weekResults = getWeekResults(state.selectedWeek);
  const query = state.search.trim().toLowerCase();

  return weekResults.filter((row) => {
    const text = [
      row.athlete_name,
      row.event_label,
      row.event_name,
      row.notes_clean,
      row.notes,
      row.distance,
      row.slack_name,
      row.split_first_label,
      row.split_second_label,
      row.split_first_display,
      row.split_second_display,
      row.split_delta_display,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    const matchesSearch = !query || text.includes(query);
    const matchesDistance = state.distance === "Alle" || String(row.distance ?? "") === state.distance;
    return matchesSearch && matchesDistance;
  });
}

function splitMarkup(row) {
  if (!row.split_state) {
    return {
      first: "—",
      second: "—",
      delta: "—",
      deltaClass: "split-delta--empty",
    };
  }

  return {
    first: `
      <span class="split-cell">
        <span class="split-distance">${escapeHtml(row.split_first_label || "Split 1")}</span>
        <span class="split-time">${escapeHtml(row.split_first_display || "")}</span>
      </span>
    `,
    second: `
      <span class="split-cell">
        <span class="split-distance">${escapeHtml(row.split_second_label || "Split 2")}</span>
        <span class="split-time">${escapeHtml(row.split_second_display || "")}</span>
      </span>
    `,
    delta: escapeHtml(row.split_delta_display || "00:00"),
    deltaClass:
      row.split_state === "slow" ? "split-delta--slow" : row.split_state === "fast" ? "split-delta--fast" : "split-delta--even",
  };
}

function renderSelectedWeek() {
  const week = getSelectedWeek();
  const results = getFilteredResults();

  if (!week) {
    els.selectedWeekTitle.textContent = "Ingen uke valgt";
    els.selectedWeekMeta.textContent = "";
    els.selectedWeekStats.innerHTML = "";
    els.resultsTable.innerHTML = "";
    els.emptyState.hidden = false;
    return;
  }

  els.selectedWeekTitle.textContent = week.week_label;
  els.selectedWeekMeta.textContent = `${week.published_date_label} · ${formatCount(week.result_count)} resultater · ${formatCount(
    week.athlete_count
  )} løpere · ${formatCount(week.event_count)} løp`;
  els.selectedWeekStats.innerHTML = `
    <div><span class="label">Resultater</span><span class="value">${formatCount(week.result_count)}</span></div>
    <div><span class="label">Løpere</span><span class="value">${formatCount(week.athlete_count)}</span></div>
    <div><span class="label">Løp</span><span class="value">${formatCount(week.event_count)}</span></div>
  `;

  if (results.length === 0) {
    els.resultsTable.innerHTML = "";
    els.emptyState.hidden = false;
    return;
  }

  els.emptyState.hidden = true;
  els.resultsTable.innerHTML = results
    .map((row) => {
      const splits = splitMarkup(row);
      const place = row.place ? `<span class="place">${escapeHtml(row.place)}</span>` : "—";
      const note = row.notes_clean ? `<span class="note">${escapeHtml(row.notes_clean)}</span>` : "—";
      return `
        <tr>
          <td class="athlete">${escapeHtml(row.athlete_name || "")}</td>
          <td class="event">${escapeHtml(row.event_label || row.event_name || "")}</td>
          <td class="distance">${escapeHtml(row.distance || "")}</td>
          <td class="time">${escapeHtml(row.result_time_normalized || row.result_time_raw || "")}</td>
          <td>${splits.first}</td>
          <td>${splits.second}</td>
          <td class="split-delta ${splits.deltaClass}">${splits.delta}</td>
          <td>${place}</td>
          <td>${note}</td>
        </tr>
      `;
    })
    .join("");
}

function renderAll() {
  renderWeeks();
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
