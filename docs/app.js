const distanceOrder = ["800 m", "1500 m", "3000 m", "5 km", "10 km", "Halvmaraton", "Maraton", "42 km", "30 km", "60 km"];

const state = {
  data: null,
  selectedWeek: null,
  search: "",
  distance: "Alle",
  eventFilter: "Alle",
  genderFilter: "all",
  route: { type: "week" },
  peopleById: new Map(),
  personIdBySlug: new Map(),
  slugRedirects: new Map(),
};

const numberFormat = new Intl.NumberFormat("nb-NO");
let searchRenderFrame = 0;

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
  weekSelect: document.getElementById("week-select"),
  eventFilter: document.getElementById("event-filter"),
  rankingsGrid: document.getElementById("rankings-grid"),
  weekView: document.getElementById("week-view"),
  profileView: document.getElementById("profile-view"),
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

function preferredScrollBehavior() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("nb-NO")
    .trim();
}

function scrollSelectedWeekIntoView() {
  const selected = els.weeksList?.querySelector('.week-item[aria-pressed="true"]');
  if (!selected) {
    return;
  }

  selected.scrollIntoView({
    behavior: preferredScrollBehavior(),
    inline: "center",
    block: "nearest",
  });
}

function scrollActiveEventIntoView() {
  const selected = els.eventFilter?.querySelector(".event-chip.is-active");
  if (!selected) {
    return;
  }

  selected.scrollIntoView({
    behavior: preferredScrollBehavior(),
    inline: "center",
    block: "nearest",
  });
}

function scheduleSelectedWeekRender() {
  cancelAnimationFrame(searchRenderFrame);
  searchRenderFrame = requestAnimationFrame(() => {
    renderSelectedWeek();
  });
}

function profileHref(slug) {
  return slug ? `#/person/${encodeURIComponent(slug)}` : "#/";
}

function personLink(row, className = "person-link") {
  const name = escapeHtml(row.athlete_name || "");
  if (!row.person_slug) {
    return name;
  }
  return `<a class="${className}" href="${profileHref(row.person_slug)}">${name}</a>`;
}

function buildPeopleIndex() {
  const people = state.data.people || {};
  const profiles = Array.isArray(people.profiles) ? people.profiles : [];
  state.peopleById = new Map(profiles.map((profile) => [profile.person_id, profile]));
  state.personIdBySlug = new Map(Object.entries(people.slug_map || {}));
  state.slugRedirects = new Map(Object.entries(people.slug_redirects || {}));
}

function parseRoute() {
  const hash = window.location.hash || "";
  if (hash.startsWith("#/person/")) {
    return {
      type: "person",
      slug: decodeURIComponent(hash.slice("#/person/".length)),
    };
  }
  return { type: "week" };
}

function setView(route) {
  state.route = route;
  const isProfile = route.type === "person";
  els.weekView.hidden = isProfile;
  els.profileView.hidden = !isProfile;
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
  const counts = new Map();
  getWeekResults(weekNumber).forEach((row) => {
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

function renderWeekSelect() {
  if (!els.weekSelect) {
    return;
  }

  els.weekSelect.innerHTML = state.data.weeks
    .map((week) => {
      const selected = Number(week.week_number) === Number(state.selectedWeek);
      const label = `${week.week_label} - ${week.published_date_label} - ${formatCount(week.result_count)} resultater`;
      return `<option value="${escapeHtml(week.week_number)}"${selected ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function setSelectedWeek(weekNumber, { resetEvent = true } = {}) {
  const nextWeek = Number(weekNumber);
  if (!Number.isFinite(nextWeek)) {
    return;
  }

  state.selectedWeek = nextWeek;

  if (resetEvent) {
    state.eventFilter = "Alle";
  }

  renderWeeks();
  renderWeekSelect();
  renderEventButtons();
  renderSelectedWeek();
  requestAnimationFrame(scrollSelectedWeekIntoView);
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
      setSelectedWeek(button.dataset.week);
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
  const query = normalizeSearchText(state.search);

  return weekResults.filter((row) => {
    const eventName = getEventLabel(row);
    const text = normalizeSearchText([
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
      .join(" "));

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
          <td class="athlete">${personLink(row)}</td>
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
      const time = row.result_time_normalized || row.result_time_raw || "";
      const eventLabel = getEventLabel(row);
      const metaParts = [
        hasValue(row.distance) ? `<span class="result-pill">${escapeHtml(row.distance)}</span>` : "",
        hasValue(row.class_name) ? `<span class="result-pill">${escapeHtml(row.class_name)}</span>` : "",
        hasValue(row.place) ? `<span class="result-pill">Plass ${escapeHtml(row.place)}</span>` : "",
        hasValue(row.class_place) ? `<span class="result-pill result-pill--muted">Klasse ${escapeHtml(row.class_place)}</span>` : "",
      ].filter(Boolean);

      const splitParts = [
        hasValue(row.split_first_display)
          ? `<span class="result-pill"><strong>${escapeHtml(row.split_first_label || "Split 1")}</strong>${escapeHtml(row.split_first_display)}</span>`
          : "",
        hasValue(row.split_second_display)
          ? `<span class="result-pill"><strong>${escapeHtml(row.split_second_label || "Split 2")}</strong>${escapeHtml(row.split_second_display)}</span>`
          : "",
        hasValue(row.split_delta_display)
          ? `<span class="result-pill split-delta ${splitClass(row)}"><strong>Splitt</strong>${escapeHtml(row.split_delta_display)}</span>`
          : "",
      ].filter(Boolean);

      return `
        <article class="result-card">
          <div class="result-card-top">
            <div class="result-card-athlete">
              <span class="gender-pill">${displayValue(row.gender)}</span>
              <strong class="result-card-name">${personLink(row)}</strong>
              <div class="result-card-time">${escapeHtml(time)}</div>
            </div>
          </div>
          <div class="result-card-meta">${escapeHtml(eventLabel)}</div>
          ${metaParts.length ? `<div class="result-card-inline">${metaParts.join("")}</div>` : ""}
          ${splitParts.length ? `<div class="result-card-splits">${splitParts.join("")}</div>` : ""}
          ${row.notes_clean ? `<div class="result-card-note">${escapeHtml(row.notes_clean)}</div>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderGenderButtons() {
  Object.entries(els.genderButtons).forEach(([key, button]) => {
    const active = state.genderFilter === key;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function renderEventButtons() {
  const events = ["Alle", ...getWeekEvents(state.selectedWeek)];
  if (!events.includes(state.eventFilter)) {
    state.eventFilter = "Alle";
  }

  els.eventFilter.innerHTML = events
    .map((eventName) => {
      const active = state.eventFilter === eventName;
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

  els.eventFilter.querySelectorAll(".event-chip").forEach((button) => {
    button.addEventListener("click", () => {
      state.eventFilter = button.dataset.event || "Alle";
      renderEventButtons();
      renderSelectedWeek();
      requestAnimationFrame(scrollActiveEventIntoView);
    });
  });
}

function renderRankingColumn(title, entries) {
  if (!entries.length) {
    return `
      <section class="ranking-column" aria-label="${escapeHtml(title)}">
        <div class="ranking-column-head">
          <h4 class="ranking-title">${escapeHtml(title)}</h4>
          <span class="ranking-count">0</span>
        </div>
        <p class="ranking-empty">Ingen gyldige tider registrert ennå.</p>
      </section>
    `;
  }

  const items = entries
    .map((entry) => {
      const dateMarkup = entry.published_date_label ? `<span>${escapeHtml(entry.published_date_label)}</span>` : "";
      return `
        <li class="ranking-item">
          <span class="ranking-place">${escapeHtml(entry.rank)}</span>
          <div class="ranking-body">
            <div class="ranking-line">
              <strong class="ranking-name">${personLink(entry)}</strong>
              <span class="ranking-time">${escapeHtml(entry.result_time || "")}</span>
            </div>
            <div class="ranking-meta">
              <span>${escapeHtml(entry.event_label || "")}</span>
              ${dateMarkup}
            </div>
          </div>
        </li>
      `;
    })
    .join("");

  return `
    <section class="ranking-column" aria-label="${escapeHtml(title)}">
      <div class="ranking-column-head">
        <h4 class="ranking-title">${escapeHtml(title)}</h4>
        <span class="ranking-count">${formatCount(entries.length)}</span>
      </div>
      <ol class="ranking-list">
        ${items}
      </ol>
    </section>
  `;
}

function renderRankings() {
  const rankings = Array.isArray(state.data.rankings) ? state.data.rankings : [];
  if (!rankings.length) {
    els.rankingsGrid.innerHTML = `<p class="ranking-empty">Ingen ranking-data tilgjengelig.</p>`;
    return;
  }

  els.rankingsGrid.innerHTML = rankings
    .map((group) => {
      const women = Array.isArray(group.women) ? group.women : [];
      const men = Array.isArray(group.men) ? group.men : [];

      return `
        <article class="ranking-card">
          <div class="ranking-card-head">
            <div>
              <p class="ranking-kicker">Standarddistanse</p>
              <h3>${escapeHtml(group.distance || "")}</h3>
            </div>
            <div class="ranking-summary">${formatCount(women.length)} kvinner · ${formatCount(men.length)} menn</div>
          </div>
          <div class="ranking-columns">
            ${renderRankingColumn("Kvinner", women)}
            ${renderRankingColumn("Menn", men)}
          </div>
        </article>
      `;
    })
    .join("");
}

function sortResultsNewestFirst(results) {
  return [...results].sort((a, b) => {
    const dateCompare = String(b.published_date || "").localeCompare(String(a.published_date || ""));
    if (dateCompare !== 0) {
      return dateCompare;
    }
    const weekCompare = Number(b.week_number || 0) - Number(a.week_number || 0);
    if (weekCompare !== 0) {
      return weekCompare;
    }
    return Number(a.result_time_seconds || Number.POSITIVE_INFINITY) - Number(b.result_time_seconds || Number.POSITIVE_INFINITY);
  });
}

function renderProfileNotFound(slug) {
  els.profileView.innerHTML = `
    <article class="profile-shell profile-shell--empty">
      <a class="back-link" href="#/">Til ukeoversikt</a>
      <p class="section-kicker">Personprofil</p>
      <h2>Fant ikke profilen</h2>
      <p class="profile-muted">Ingen publisert profil finnes for ${escapeHtml(slug || "denne lenken")}.</p>
    </article>
  `;
}

function renderBestResults(profile) {
  const bestResults = Array.isArray(profile.best_results) ? profile.best_results : [];
  if (!bestResults.length) {
    return `<p class="profile-muted">Ingen standarddistanser med gyldig tid ennå.</p>`;
  }

  return `
    <div class="profile-best-grid">
      ${bestResults
        .map(
          (result) => `
            <article class="profile-best-card">
              <span class="profile-best-distance">${escapeHtml(result.distance || "")}</span>
              <strong>${escapeHtml(result.result_time || "")}</strong>
              <span>${escapeHtml(result.event_label || "")}</span>
              <span>${escapeHtml(result.published_date_label || "")}</span>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderProfileResults(results) {
  if (!results.length) {
    return `<p class="profile-muted">Ingen publiserte resultater.</p>`;
  }

  return `
    <div class="profile-results-list">
      ${results
        .map((row) => {
          const time = row.result_time_normalized || row.result_time_raw || "";
          const place = hasValue(row.place) ? `<span class="result-pill">#${escapeHtml(row.place)}</span>` : "";
          const classPlace = hasValue(row.class_place)
            ? `<span class="result-pill result-pill--muted">Kl ${escapeHtml(row.class_place)}</span>`
            : "";
          const note = hasValue(row.notes_clean) ? `<p class="profile-result-note">${escapeHtml(row.notes_clean)}</p>` : "";

          return `
            <article class="profile-result-row">
              <div class="profile-result-date">
                <span>${escapeHtml(row.published_date_label || "")}</span>
                <small>Uke ${escapeHtml(row.week_number || "")}</small>
              </div>
              <div class="profile-result-main">
                <div class="profile-result-title">
                  <strong>${escapeHtml(row.event_label || "")}</strong>
                  <span class="profile-result-time">${escapeHtml(time)}</span>
                </div>
                <div class="profile-result-meta">
                  ${hasValue(row.distance) ? `<span class="result-pill">${escapeHtml(row.distance)}</span>` : ""}
                  ${hasValue(row.class_name) ? `<span class="result-pill">${escapeHtml(row.class_name)}</span>` : ""}
                  ${place}
                  ${classPlace}
                </div>
                ${note}
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderProfile(route) {
  const redirectSlug = state.slugRedirects.get(route.slug);
  if (redirectSlug && redirectSlug !== route.slug) {
    window.location.hash = `/person/${redirectSlug}`;
    return;
  }

  const personId = state.personIdBySlug.get(route.slug);
  const profile = personId ? state.peopleById.get(personId) : null;
  if (!profile) {
    renderProfileNotFound(route.slug);
    return;
  }

  const results = sortResultsNewestFirst(state.data.results.filter((row) => row.person_id === personId));
  const distancePills = (profile.distances || [])
    .map((distance) => `<span class="result-pill">${escapeHtml(distance)}</span>`)
    .join("");
  const latest = profile.latest_result_date ? `Sist registrert ${escapeHtml(profile.latest_result_date)}` : "";

  els.profileView.innerHTML = `
    <article class="profile-shell">
      <div class="profile-head">
        <div>
          <a class="back-link" href="#/">Til ukeoversikt</a>
          <p class="section-kicker">Personprofil</p>
          <h2>${escapeHtml(profile.display_name || "")}</h2>
          <p class="profile-muted">${formatCount(profile.result_count)} resultater${latest ? ` · ${latest}` : ""}</p>
        </div>
        <div class="profile-stat-grid" aria-label="Profilstatistikk">
          <div><span>Resultater</span><strong>${formatCount(profile.result_count)}</strong></div>
          <div><span>Distanser</span><strong>${formatCount((profile.distances || []).length)}</strong></div>
          <div><span>Kjønn</span><strong>${escapeHtml(profile.gender || "–")}</strong></div>
        </div>
      </div>

      ${distancePills ? `<div class="profile-distance-row">${distancePills}</div>` : ""}

      <section class="profile-section" aria-labelledby="profile-best-title">
        <div class="section-header profile-section-head">
          <div>
            <p class="section-kicker">Beste noteringer</p>
            <h3 id="profile-best-title" class="section-heading">Per standarddistanse</h3>
          </div>
        </div>
        ${renderBestResults(profile)}
      </section>

      <section class="profile-section" aria-labelledby="profile-results-title">
        <div class="section-header profile-section-head">
          <div>
            <p class="section-kicker">Alle resultater</p>
            <h3 id="profile-results-title" class="section-heading">Nyeste først</h3>
          </div>
        </div>
        ${renderProfileResults(results)}
      </section>
    </article>
  `;
}

function renderRoute() {
  const route = parseRoute();
  setView(route);
  if (route.type === "person") {
    renderProfile(route);
  }
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
  renderWeekSelect();
  renderEventButtons();
  renderSelectedWeek();
  requestAnimationFrame(scrollSelectedWeekIntoView);
}

function bindFilters() {
  els.searchInput.addEventListener("input", (event) => {
    state.search = event.target.value;
    scheduleSelectedWeekRender();
  });

  els.distanceFilter.addEventListener("change", (event) => {
    state.distance = event.target.value;
    renderSelectedWeek();
  });

  if (els.weekSelect) {
    els.weekSelect.addEventListener("change", (event) => {
      setSelectedWeek(event.target.value);
    });
  }

  els.genderButtons.all.addEventListener("click", () => {
    state.genderFilter = "all";
    renderGenderButtons();
    renderSelectedWeek();
  });
  els.genderButtons.women.addEventListener("click", () => {
    state.genderFilter = "women";
    renderGenderButtons();
    renderSelectedWeek();
  });
  els.genderButtons.men.addEventListener("click", () => {
    state.genderFilter = "men";
    renderGenderButtons();
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
  buildPeopleIndex();

  renderStats();
  renderDistanceOptions();
  renderRankings();
  bindFilters();
  renderAll();
  window.addEventListener("hashchange", renderRoute);
  renderRoute();
}

main().catch((error) => {
  console.error(error);
  els.selectedWeekTitle.textContent = "Datafil mangler";
  els.selectedWeekMeta.textContent = "Kjør bygge-skriptet på nytt for å lage JSON og database.";
  els.emptyState.hidden = false;
  els.emptyState.textContent = "Data kunne ikke lastes.";
});
