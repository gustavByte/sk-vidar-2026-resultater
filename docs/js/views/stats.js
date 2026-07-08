import { state } from "../state.js";
import { displayTime, escapeHtml, formatCount, formatEventLabel, formatWaPoints } from "../format.js";
import { hrefWeek } from "../router.js";
import { genderPill, personLink } from "../templates.js";
import { waChip } from "../badges.js";
import {
  biggestEvents,
  fullRankingList,
  isTerrainOrTrail,
  monthsSeries,
  participationTop,
  personalHighlights,
  seasonWaPerPerson,
  seasonWaTopResults,
  terrainHighlights,
} from "../derive.js";
import { barChartSvg, chartLegendHtml, mountChart } from "../charts.js";

const SECTIONS = [
  { id: "hoydepunkter", label: "Høydepunkter" },
  { id: "topp-10", label: "Topp 10 per distanse" },
  { id: "wa", label: "WA-poeng" },
  { id: "deltakelse", label: "Deltakelse" },
  { id: "maneder", label: "Måned for måned" },
  { id: "lop", label: "Største løp" },
];

let container = null;
let waGender = "all";
let participationGender = "all";
const expandedColumns = new Set();

function genderMatchesFilter(gender, filter) {
  if (filter === "women") {
    return gender === "K";
  }
  if (filter === "men") {
    return gender === "M";
  }
  return true;
}

function subNavHtml(activeSection) {
  return `
    <div class="stats-subnav" role="navigation" aria-label="Statistikkseksjoner">
      ${SECTIONS.map(
        (section) => `
          <a class="event-chip${section.id === activeSection ? " is-active" : ""}" href="#/statistikk/${section.id}">${escapeHtml(section.label)}</a>
        `,
      ).join("")}
    </div>
  `;
}

function genderChipsHtml(groupName, active) {
  const options = [
    { key: "all", label: "Alle" },
    { key: "women", label: "Kvinner" },
    { key: "men", label: "Menn" },
  ];
  return `
    <div class="segmented segmented--inline" role="group" aria-label="Kjønn">
      ${options
        .map(
          (option) => `
            <button class="segment${option.key === active ? " is-active" : ""}" type="button" data-gender-group="${groupName}" data-gender="${option.key}" aria-pressed="${option.key === active ? "true" : "false"}">
              ${option.label}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function rowText(row) {
  return [row.notes_clean, row.event_label, row.distance].filter(Boolean).join(" ").toLocaleLowerCase("nb-NO");
}

function terrainTypeLabel(row) {
  const text = rowText(row);
  if (text.includes("fjell") || text.includes("zegama") || text.includes("zermatt")) {
    return "fjelløp";
  }
  if (text.includes("skyrace") || text.includes("sky race") || text.includes("skyrunning")) {
    return "skyrace";
  }
  if (text.includes("trail") || text.includes("utmb")) {
    return "trail";
  }
  if (text.includes("ultra")) {
    return "ultra";
  }
  if (text.includes("motbakke")) {
    return "motbakke";
  }
  if (text.includes("terreng")) {
    return "terreng";
  }
  return isTerrainOrTrail(row) ? "terreng" : "";
}

function highlightBadge(label, modifier = "") {
  const className = modifier ? ` highlight-badge--${modifier}` : "";
  return `<span class="highlight-badge${className}">${escapeHtml(label)}</span>`;
}

function highlightBadgesHtml(row) {
  const parts = [];
  const terrainLabel = terrainTypeLabel(row);
  if (terrainLabel) {
    parts.push(highlightBadge(terrainLabel, "terrain"));
  }
  if (row.is_pb) {
    parts.push(highlightBadge("PB", "pb"));
  } else if (row.is_sb) {
    parts.push(highlightBadge("SB", "sb"));
  }
  if (row.wa_points === null || row.wa_points === undefined || !Number.isFinite(Number(row.wa_points))) {
    parts.push(highlightBadge("uten WA", "muted"));
  } else {
    parts.push(waChip(row.wa_points, { label: "WA" }));
  }
  return parts.join(" ");
}

function highlightPlaceText(row) {
  const parts = [];
  if (row.place) {
    parts.push(`Plass ${row.place}`);
  }
  if (row.class_place) {
    parts.push(`Klasse ${row.class_place}`);
  }
  return parts.join(" · ");
}

function highlightResultText(row) {
  const distance = String(row.distance || "").trim();
  const time = displayTime(row);
  return [distance, time].filter(Boolean).join(" · ");
}

function highlightListHtml(rows, emptyText) {
  if (!rows.length) {
    return `<p class="highlight-empty">${escapeHtml(emptyText)}</p>`;
  }

  return `
    <ol class="highlight-list">
      ${rows
        .map((row) => {
          const place = highlightPlaceText(row);
          const week = row.week_number ? `<a class="quiet-link highlight-week" href="${hrefWeek(row.week_number)}">Uke ${escapeHtml(row.week_number)}</a>` : "";
          return `
            <li class="highlight-row">
              <div class="highlight-row-main">
                <div class="highlight-athlete">${genderPill(row.gender)} ${personLink(row)}</div>
                <div class="highlight-event">${escapeHtml(formatEventLabel(row.event_label))}</div>
              </div>
              <div class="highlight-row-meta">
                <span class="highlight-result">${escapeHtml(highlightResultText(row))}</span>
                ${place ? `<span>${escapeHtml(place)}</span>` : ""}
                ${week}
              </div>
              <div class="highlight-badges">${highlightBadgesHtml(row)}</div>
            </li>
          `;
        })
        .join("")}
    </ol>
  `;
}

function highlightsSectionHtml() {
  const terrainRows = terrainHighlights(6);
  const personalRows = personalHighlights(6);

  return `
    <section class="stats-section highlights-section" id="stats-hoydepunkter" aria-labelledby="highlights-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Utenfor de faste rankingene</p>
          <h2 id="highlights-title" class="section-heading">Høydepunkter</h2>
        </div>
        <p class="section-copy">Korte lister som løfter sterke enkeltresultater, også der WA-poeng ikke finnes.</p>
      </div>
      <div class="highlight-columns">
        <section class="highlight-card" aria-label="Terreng og fjell uten WA">
          <h3 class="stats-block-heading">Terreng/fjell uten WA</h3>
          ${highlightListHtml(terrainRows, "Ingen terreng- eller fjellresultater uten WA-poeng funnet.")}
        </section>
        <section class="highlight-card" aria-label="Sterke enkeltprestasjoner">
          <h3 class="stats-block-heading">Sterke enkeltprestasjoner</h3>
          ${highlightListHtml(personalRows, "Ingen høydepunkter funnet ennå.")}
        </section>
      </div>
    </section>
  `;
}

function rankingEntryFromRow(row, rank) {
  return {
    rank,
    athlete_name: row.athlete_name,
    person_slug: row.person_slug,
    result_time: displayTime(row),
    event_label: row.event_label,
    published_date_label: row.published_date_label,
    wa_points: row.wa_points,
  };
}

function rankingColumnHtml(distance, genderKey, title, topEntries) {
  const fullList = fullRankingList(distance, genderKey);
  const columnKey = `${distance}|${genderKey}`;
  const expanded = expandedColumns.has(columnKey);
  const entries = expanded ? fullList.map((row, index) => rankingEntryFromRow(row, index + 1)) : topEntries;

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
      const wa = Number.isFinite(Number(entry.wa_points)) && entry.wa_points !== null ? waChip(entry.wa_points) : "";
      return `
        <li class="ranking-item">
          <span class="ranking-place">${escapeHtml(entry.rank)}</span>
          <div class="ranking-body">
            <div class="ranking-line">
              <strong class="ranking-name">${personLink(entry)}</strong>
              <span class="ranking-time">${escapeHtml(entry.result_time || "")}${wa ? ` ${wa}` : ""}</span>
            </div>
            <div class="ranking-meta">
              <span>${escapeHtml(formatEventLabel(entry.event_label))}</span>
              ${dateMarkup}
            </div>
          </div>
        </li>
      `;
    })
    .join("");

  const toggle =
    fullList.length > 10
      ? `<button class="ranking-toggle" type="button" data-column="${escapeHtml(columnKey)}">${
          expanded ? "Vis topp 10" : `Vis alle (${formatCount(fullList.length)})`
        }</button>`
      : "";

  return `
    <section class="ranking-column" aria-label="${escapeHtml(title)}">
      <div class="ranking-column-head">
        <h4 class="ranking-title">${escapeHtml(title)}</h4>
        <span class="ranking-count">${formatCount(expanded ? fullList.length : entries.length)}</span>
      </div>
      <ol class="ranking-list">
        ${items}
      </ol>
      ${toggle}
    </section>
  `;
}

function rankingsSectionHtml() {
  const rankings = Array.isArray(state.data.rankings) ? state.data.rankings : [];
  const cards = rankings
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
            ${rankingColumnHtml(group.distance, "K", "Kvinner", women)}
            ${rankingColumnHtml(group.distance, "M", "Menn", men)}
          </div>
        </article>
      `;
    })
    .join("");

  return `
    <section class="stats-section rankings-section" id="stats-topp-10" aria-labelledby="rankings-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Sesongoversikt</p>
          <h2 id="rankings-title" class="section-heading">Topp 10 pr. standarddistanse</h2>
        </div>
        <p class="section-copy">Kun beste resultat per utøver vises. Kvinner og menn rangeres hver for seg.</p>
      </div>
      <div class="rankings-grid">${cards || `<p class="ranking-empty">Ingen ranking-data tilgjengelig.</p>`}</div>
    </section>
  `;
}

function waSectionHtml() {
  const topResults = seasonWaTopResults(200);
  const filteredResults = topResults.filter((row) => genderMatchesFilter(row.gender, waGender)).slice(0, 25);

  const resultRows = filteredResults
    .map(
      (row, index) => `
        <tr>
          <td class="stats-rank">${index + 1}</td>
          <td>${genderPill(row.gender)} ${personLink(row)}</td>
          <td>${escapeHtml(formatEventLabel(row.event_label))}</td>
          <td class="muted">${escapeHtml(row.distance || "")}</td>
          <td class="time">${escapeHtml(displayTime(row))}</td>
          <td class="wa-cell">${waChip(row.wa_points)}</td>
        </tr>
      `,
    )
    .join("");

  const perPerson = seasonWaPerPerson(0)
    .filter((entry) => genderMatchesFilter(entry.best.gender, waGender))
    .slice(0, 25);

  const personRows = perPerson
    .map(
      (entry, index) => `
        <tr>
          <td class="stats-rank">${index + 1}</td>
          <td>${genderPill(entry.best.gender)} ${personLink(entry.best)}</td>
          <td>${escapeHtml(displayTime(entry.best))} <span class="muted">${escapeHtml(entry.best.distance || "")}</span></td>
          <td class="wa-cell">${waChip(entry.best.wa_points)}</td>
          <td class="muted">${entry.top3Average !== null ? formatWaPoints(entry.top3Average) : "—"}</td>
        </tr>
      `,
    )
    .join("");

  return `
    <section class="stats-section" id="stats-wa" aria-labelledby="wa-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">På tvers av distanser</p>
          <h2 id="wa-title" class="section-heading">WA-poeng</h2>
        </div>
        <p class="section-copy">WA-poeng gjør prestasjoner på ulike distanser sammenlignbare. Kvinner og menn graderes hver for seg og kan derfor vises i samme liste.</p>
      </div>
      ${genderChipsHtml("wa", waGender)}
      <div class="stats-columns">
        <div class="stats-block">
          <h3 class="stats-block-heading">Beste enkeltprestasjoner</h3>
          <div class="stats-table-wrap">
            <table class="stats-table">
              <thead>
                <tr><th>#</th><th>Løper</th><th>Løp</th><th>Distanse</th><th>Tid</th><th>WA</th></tr>
              </thead>
              <tbody>${resultRows || `<tr><td colspan="6" class="muted">Ingen WA-graderte resultater.</td></tr>`}</tbody>
            </table>
          </div>
        </div>
        <div class="stats-block">
          <h3 class="stats-block-heading">Beste per person</h3>
          <div class="stats-table-wrap">
            <table class="stats-table">
              <thead>
                <tr><th>#</th><th>Løper</th><th>Beste resultat</th><th>WA</th><th>Snitt 3 beste</th></tr>
              </thead>
              <tbody>${personRows || `<tr><td colspan="5" class="muted">Ingen WA-graderte resultater.</td></tr>`}</tbody>
            </table>
          </div>
        </div>
      </div>
      <p class="chart-caption">Terrengløp og stafetter har ikke WA-poeng.</p>
    </section>
  `;
}

function participationSectionHtml() {
  const top = participationTop(0)
    .filter((profile) => genderMatchesFilter(profile.gender, participationGender))
    .slice(0, 20);

  const rows = top
    .map(
      (profile, index) => `
        <tr>
          <td class="stats-rank">${index + 1}</td>
          <td>${genderPill(profile.gender)} ${personLink(profile)}</td>
          <td>${formatCount(profile.result_count)}</td>
          <td class="muted">${formatCount((profile.distances || []).length)}</td>
        </tr>
      `,
    )
    .join("");

  return `
    <section class="stats-section" id="stats-deltakelse" aria-labelledby="participation-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Deltakelse</p>
          <h2 id="participation-title" class="section-heading">Flest løp</h2>
        </div>
        <p class="section-copy">Antall publiserte resultater per løper i 2026.</p>
      </div>
      ${genderChipsHtml("participation", participationGender)}
      <div class="stats-table-wrap stats-table-wrap--narrow">
        <table class="stats-table">
          <thead>
            <tr><th>#</th><th>Løper</th><th>Resultater</th><th>Distanser</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

const MONTH_SERIES = [
  { name: "Kvinner", color: "var(--chart-women)" },
  { name: "Menn", color: "var(--chart-men)" },
];

function mountMonthsChart() {
  const months = monthsSeries();
  if (!months.length) {
    return;
  }
  const items = months.map((month) => ({
    label: month.month_label,
    values: [month.women_count || 0, month.men_count || 0],
    title: `${month.month_label}: ${month.result_count} resultater (${month.women_count} kvinner, ${month.men_count} menn)`,
  }));
  const maxMonth = months.reduce((best, month) => (month.result_count > best.result_count ? month : best), months[0]);
  mountChart(container.querySelector("#months-chart-mount"), (width) =>
    barChartSvg({
      items,
      series: MONTH_SERIES,
      width,
      height: 190,
      ariaLabel: `Stolpediagram over resultater per måned. Flest i ${maxMonth.month_label} med ${maxMonth.result_count} resultater.`,
      formatValue: formatCount,
    }),
  );
}

function monthsSectionHtml() {
  const months = monthsSeries();
  if (!months.length) {
    return "";
  }

  const rows = months
    .map(
      (month) => `
        <tr>
          <td>${escapeHtml(month.month_label)}</td>
          <td>${formatCount(month.result_count)}</td>
          <td>${formatCount(month.athlete_count ?? 0)}</td>
          <td>${formatCount(month.event_count ?? 0)}</td>
        </tr>
      `,
    )
    .join("");

  return `
    <section class="stats-section" id="stats-maneder" aria-labelledby="months-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Volum</p>
          <h2 id="months-title" class="section-heading">Måned for måned</h2>
        </div>
      </div>
      <div class="chart" id="months-chart-mount"></div>
      ${chartLegendHtml(MONTH_SERIES)}
      <div class="stats-table-wrap stats-table-wrap--narrow">
        <table class="stats-table">
          <thead>
            <tr><th>Måned</th><th>Resultater</th><th>Løpere</th><th>Løp</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

function eventsSectionHtml() {
  const events = biggestEvents(15);
  const rows = events
    .map((entry, index) => {
      const weekLinks = entry.weeks
        .map((week) => `<a class="quiet-link" href="${hrefWeek(week)}">Uke ${week}</a>`)
        .join(", ");
      return `
        <tr>
          <td class="stats-rank">${index + 1}</td>
          <td>${escapeHtml(formatEventLabel(entry.event_label))}</td>
          <td>${formatCount(entry.count)}</td>
          <td class="muted">${formatCount(entry.women)} K · ${formatCount(entry.men)} M</td>
          <td class="muted">${weekLinks}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <section class="stats-section" id="stats-lop" aria-labelledby="events-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Løp</p>
          <h2 id="events-title" class="section-heading">Største løp</h2>
        </div>
        <p class="section-copy">Løpene med flest SK Vidar-deltakere i 2026.</p>
      </div>
      <div class="stats-table-wrap">
        <table class="stats-table">
          <thead>
            <tr><th>#</th><th>Løp</th><th>Deltakere</th><th>K/M</th><th>Uke</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderContent(activeSection) {
  container.innerHTML = `
    <div class="stats-shell">
      <div class="section-header">
        <div>
          <p class="section-kicker">Sesongen 2026</p>
          <h2 class="section-heading">Statistikk</h2>
        </div>
      </div>
      ${subNavHtml(activeSection)}
      ${highlightsSectionHtml()}
      ${rankingsSectionHtml()}
      ${waSectionHtml()}
      ${participationSectionHtml()}
      ${monthsSectionHtml()}
      ${eventsSectionHtml()}
    </div>
  `;

  mountMonthsChart();

  container.querySelectorAll("[data-gender-group]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.genderGroup === "wa") {
        waGender = button.dataset.gender;
      } else {
        participationGender = button.dataset.gender;
      }
      renderContent("");
    });
  });

  container.querySelectorAll(".ranking-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.column;
      if (expandedColumns.has(key)) {
        expandedColumns.delete(key);
      } else {
        expandedColumns.add(key);
      }
      renderContent("");
    });
  });
}

function scrollToStatsSection(section, attempt = 0) {
  const target = container.querySelector(`#stats-${CSS.escape(section)}`);
  if (!target) {
    return;
  }

  const navBottom = document.querySelector(".top-nav")?.getBoundingClientRect().bottom || 0;
  const rect = target.getBoundingClientRect();
  const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
  const top = rect.top + window.scrollY - navBottom - 10;
  window.scrollTo({ top: Math.min(Math.max(0, top), maxScroll), behavior: "auto" });

  if (attempt < 4) {
    window.setTimeout(() => {
      const nextRect = target.getBoundingClientRect();
      const nextNavBottom = document.querySelector(".top-nav")?.getBoundingClientRect().bottom || 0;
      const nextMaxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const visibleHeight = Math.min(nextRect.bottom, window.innerHeight) - Math.max(nextRect.top, nextNavBottom);
      const aligned = nextRect.top >= nextNavBottom + 6 && nextRect.top <= nextNavBottom + 90;
      const atPageEnd = window.scrollY >= nextMaxScroll - 2 && visibleHeight > 0;
      if (!aligned && !atPageEnd) {
        scrollToStatsSection(section, attempt + 1);
      }
    }, 80 * (attempt + 1));
  }
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render(params) {
  const section = params.section || "";
  renderContent(section);
  if (section) {
    requestAnimationFrame(() => scrollToStatsSection(section));
  } else {
    window.scrollTo({ top: 0, behavior: "auto" });
  }
}
