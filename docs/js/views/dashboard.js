import { state, latestWeek, getWeek } from "../state.js";
import { displayTime, escapeHtml, formatCount, formatEventLabel } from "../format.js";
import { hrefPeople, hrefSearch, hrefStats, hrefWeek } from "../router.js";
import { performanceItemHtml, personLink } from "../templates.js";
import { resultBadges } from "../badges.js";
import { latestPbResults, seasonWaTopResults, weekTopPerformances, weeksAscending } from "../derive.js";
import { barChartSvg, chartLegendHtml, mountChart } from "../charts.js";

let container = null;

function heroHtml() {
  const { stats } = state.data;
  return `
    <header class="hero dashboard-hero">
      <div>
        <p class="eyebrow">SK Vidar 2026</p>
        <h1>Sesongen 2026</h1>
        <p class="hero-copy">Mellom- og langdistanse: resultater, trender og statistikk for hele sesongen.</p>
      </div>
      <dl class="stats" aria-label="Sammendrag">
        <div>
          <dt>Resultater</dt>
          <dd>${formatCount(stats.result_count)}</dd>
        </div>
        <div>
          <dt>Løpere</dt>
          <dd>${formatCount(stats.athlete_count)}</dd>
        </div>
        <div>
          <dt>Løp</dt>
          <dd>${formatCount(stats.event_count)}</dd>
        </div>
        <div>
          <dt>Uker</dt>
          <dd>${formatCount(stats.week_count)}</dd>
        </div>
      </dl>
    </header>
  `;
}

function mobileSearchHtml() {
  return `
    <form class="dashboard-search mobile-only" id="dashboard-search-form" role="search">
      <input id="dashboard-search-input" type="search" placeholder="Søk i hele sesongen…" aria-label="Søk i hele sesongen" autocomplete="off" />
    </form>
  `;
}

const WEEKLY_SERIES = [
  { name: "Kvinner", color: "var(--chart-women)" },
  { name: "Menn", color: "var(--chart-men)" },
];

function weeklyChartHtml() {
  if (!weeksAscending().length) {
    return "";
  }
  return `
    <section class="dash-card dash-card--wide" aria-labelledby="weekly-chart-title">
      <div class="dash-card-head">
        <div>
          <p class="section-kicker">Sesongtrend</p>
          <h2 id="weekly-chart-title" class="section-heading">Resultater per uke</h2>
        </div>
        <p class="section-copy">Klikk en stolpe for å åpne uken.</p>
      </div>
      <div class="chart" id="weekly-chart-mount"></div>
      ${chartLegendHtml(WEEKLY_SERIES)}
    </section>
  `;
}

function mountWeeklyChart() {
  const weeks = weeksAscending();
  if (!weeks.length) {
    return;
  }
  const items = weeks.map((week) => ({
    label: `U${week.week_number}`,
    values: [week.women_count || 0, week.men_count || 0],
    href: hrefWeek(week.week_number),
    title: `Uke ${week.week_number} · ${week.result_count} resultater (${week.women_count} kvinner, ${week.men_count} menn)`,
  }));
  const maxWeek = weeks.reduce((best, week) => (week.result_count > best.result_count ? week : best), weeks[0]);
  mountChart(container.querySelector("#weekly-chart-mount"), (width) =>
    barChartSvg({
      items,
      series: WEEKLY_SERIES,
      width,
      xTickEvery: 4,
      height: 200,
      ariaLabel: `Stolpediagram over resultater per uke, uke ${weeks[0].week_number} til ${weeks[weeks.length - 1].week_number}. Flest i uke ${maxWeek.week_number} med ${maxWeek.result_count} resultater.`,
      formatValue: formatCount,
    }),
  );
}

function latestWeekCardHtml() {
  const weekNumber = latestWeek();
  const week = getWeek(weekNumber);
  if (!week) {
    return "";
  }

  const chips = [
    Number(week.pb_count) > 0 ? `<span class="result-pill">${formatCount(week.pb_count)} ${Number(week.pb_count) === 1 ? "pers" : "perser"}</span>` : "",
    Number(week.new_athlete_count) > 0 ? `<span class="result-pill">${formatCount(week.new_athlete_count)} debutanter</span>` : "",
  ].filter(Boolean);

  const top = weekTopPerformances(weekNumber, 3);
  const topList = top.length
    ? `<ol class="performance-list">${top.map((row, index) => performanceItemHtml(row, index + 1)).join("")}</ol>`
    : `<p class="empty-state">Ingen WA-graderte løp denne uken.</p>`;

  return `
    <section class="dash-card" aria-labelledby="latest-week-title">
      <div class="dash-card-head">
        <div>
          <p class="section-kicker">Siste uke</p>
          <h2 id="latest-week-title" class="section-heading">${escapeHtml(week.week_label)}</h2>
        </div>
      </div>
      <p class="dash-card-meta">${escapeHtml(week.published_date_label)} · ${formatCount(week.result_count)} resultater · ${formatCount(week.event_count)} løp</p>
      ${chips.length ? `<div class="dash-chip-row">${chips.join("")}</div>` : ""}
      <h3 class="dash-subheading">Ukens prestasjoner</h3>
      ${topList}
      <a class="dash-card-link" href="${hrefWeek(weekNumber)}">Se hele uken →</a>
    </section>
  `;
}

function seasonBestCardHtml() {
  const top = seasonWaTopResults(5);
  const list = top.length
    ? `<ol class="performance-list">${top.map((row, index) => performanceItemHtml(row, index + 1)).join("")}</ol>`
    : `<p class="empty-state">Ingen WA-graderte resultater ennå.</p>`;

  return `
    <section class="dash-card" aria-labelledby="season-best-title">
      <div class="dash-card-head">
        <div>
          <p class="section-kicker">Hele sesongen</p>
          <h2 id="season-best-title" class="section-heading">Sesongens beste prestasjoner</h2>
        </div>
      </div>
      ${list}
      <a class="dash-card-link" href="${hrefStats("wa")}">Alle topplister →</a>
    </section>
  `;
}

function pbFeedCardHtml() {
  const rows = latestPbResults(8);
  const list = rows.length
    ? `<ul class="pb-feed">${rows
        .map(
          (row) => `
            <li class="pb-feed-item">
              <div class="performance-line">
                ${resultBadges(row)}
                <strong class="performance-name">${personLink(row)}</strong>
                <span class="performance-time">${escapeHtml(displayTime(row))}</span>
              </div>
              <div class="performance-meta">
                <span>${escapeHtml(String(row.distance || ""))}</span>
                <span>${escapeHtml(formatEventLabel(row.event_label))}</span>
                <a class="quiet-link" href="${hrefWeek(row.week_number)}">Uke ${escapeHtml(row.week_number)}</a>
              </div>
            </li>
          `,
        )
        .join("")}</ul>`
    : `<p class="empty-state">Ingen registrerte perser ennå.</p>`;

  return `
    <section class="dash-card" aria-labelledby="pb-feed-title">
      <div class="dash-card-head">
        <div>
          <p class="section-kicker">Fra notatene</p>
          <h2 id="pb-feed-title" class="section-heading">Siste perser</h2>
        </div>
      </div>
      ${list}
    </section>
  `;
}

function shortcutsCardHtml() {
  const shortcuts = [
    { href: hrefWeek(latestWeek()), title: "Siste uke", text: "Alle resultater fra siste publisering" },
    { href: hrefStats("topp-10"), title: "Topp 10 per distanse", text: "Sesongens beste tider" },
    { href: hrefPeople(), title: "Alle personer", text: `${formatCount(state.data.people?.profile_count || 0)} løpere med profil` },
    { href: hrefStats(), title: "Statistikk", text: "WA-poeng, deltakelse og måneder" },
  ];
  return `
    <section class="dash-card dash-card--shortcuts" aria-label="Snarveier">
      <div class="dash-card-head">
        <div>
          <p class="section-kicker">Snarveier</p>
          <h2 class="section-heading">Utforsk</h2>
        </div>
      </div>
      <div class="shortcut-grid">
        ${shortcuts
          .map(
            (shortcut) => `
              <a class="shortcut-card" href="${escapeHtml(shortcut.href)}">
                <strong>${escapeHtml(shortcut.title)}</strong>
                <span>${escapeHtml(shortcut.text)}</span>
              </a>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render() {
  container.innerHTML = `
    ${heroHtml()}
    ${mobileSearchHtml()}
    <div class="dashboard-grid">
      ${weeklyChartHtml()}
      ${latestWeekCardHtml()}
      ${seasonBestCardHtml()}
      ${pbFeedCardHtml()}
      ${shortcutsCardHtml()}
    </div>
  `;

  mountWeeklyChart();

  const form = container.querySelector("#dashboard-search-form");
  const input = container.querySelector("#dashboard-search-input");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.location.hash = hrefSearch(input.value);
  });
  input.addEventListener("change", () => {
    if (input.value.trim()) {
      window.location.hash = hrefSearch(input.value);
    }
  });
}
