import { state, resultsForPerson } from "../state.js";
import {
  displayTime,
  escapeHtml,
  formatCount,
  formatEventLabel,
  formatSecondsAsTime,
  formatWaPoints,
  hasValue,
  sortResultsNewestFirst,
} from "../format.js";
import { hrefPeople, hrefWeek } from "../router.js";
import { resultBadges, waChip } from "../badges.js";
import { clubRank, hasFinitePoints, progressionDistances, progressionSeries, weeksAscending } from "../derive.js?v=20260710-refresh2";
import { chartLegendHtml, lineChartSvg, mountChart, sparklineSvg } from "../charts.js";

let container = null;
let currentPersonId = null;
let selectedDistance = "";

function profileNotFoundHtml(slug) {
  return `
    <article class="profile-shell profile-shell--empty">
      <a class="back-link" href="${hrefPeople()}">Alle personer</a>
      <p class="section-kicker">Personprofil</p>
      <h2>Fant ikke profilen</h2>
      <p class="profile-muted">Ingen publisert profil finnes for ${escapeHtml(slug || "denne lenken")}.</p>
    </article>
  `;
}

function bestResultsHtml(profile) {
  const bestResults = Array.isArray(profile.best_results) ? profile.best_results : [];
  if (!bestResults.length) {
    return `<p class="profile-muted">Ingen standarddistanser med gyldig tid ennå.</p>`;
  }

  return `
    <div class="profile-best-grid">
      ${bestResults
        .map((result) => {
          const rank = clubRank(profile.person_id, result.distance, profile.gender);
          const rankLine = rank ? `<span class="profile-best-rank">Nr. ${rank.rank} av ${rank.total} i klubben</span>` : "";
          const wa = hasFinitePoints(result) ? waChip(result.wa_points, { label: "WA" }) : "";
          return `
            <article class="profile-best-card">
              <span class="profile-best-distance">${escapeHtml(result.distance || "")}</span>
              <strong>${escapeHtml(result.result_time || "")}${wa ? ` ${wa}` : ""}</strong>
              <span>${escapeHtml(formatEventLabel(result.event_label))}</span>
              <span>${escapeHtml(result.published_date_label || "")}</span>
              ${rankLine}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

const PROGRESS_SERIES = [
  { name: "Alle løp", color: "var(--chart-neutral)" },
  { name: "Sesongbeste", color: "var(--green)" },
];

function progressionSectionHtml(personId) {
  const distances = progressionDistances(personId);
  if (!distances.length) {
    return "";
  }
  if (!distances.includes(selectedDistance)) {
    selectedDistance = distances[0];
  }

  const chips = distances
    .map(
      (distance) => `
        <button class="event-chip${distance === selectedDistance ? " is-active" : ""}" type="button" data-distance="${escapeHtml(distance)}" aria-pressed="${distance === selectedDistance ? "true" : "false"}">
          ${escapeHtml(distance)}
        </button>
      `,
    )
    .join("");

  return `
    <section class="profile-section" aria-labelledby="profile-progress-title">
      <div class="section-header profile-section-head">
        <div>
          <p class="section-kicker">Utvikling</p>
          <h3 id="profile-progress-title" class="section-heading">${escapeHtml(selectedDistance)} i 2026</h3>
        </div>
      </div>
      <div class="profile-distance-row" id="progress-distance-chips">${chips}</div>
      <div class="chart" id="progress-chart-mount"></div>
      ${chartLegendHtml(PROGRESS_SERIES)}
      <p class="chart-caption">Sesongbeste-utvikling i 2026. Viser kun resultater fra denne sesongen — ikke personlige rekorder.</p>
    </section>
  `;
}

function mountProgressionChart(personId) {
  const mountEl = container.querySelector("#progress-chart-mount");
  if (!mountEl) {
    return;
  }

  const rows = progressionSeries(personId, selectedDistance);
  const points = rows.map((row) => ({
    x: new Date(`${row.published_date}T12:00:00`).getTime(),
    y: Number(row.result_time_seconds),
    href: hrefWeek(row.week_number),
    title: `${row.published_date_label || row.published_date}: ${displayTime(row)} (${formatEventLabel(row.event_label)})`,
  }));

  let best = Number.POSITIVE_INFINITY;
  const bestPoints = [];
  for (const point of points) {
    if (point.y < best) {
      best = point.y;
    }
    bestPoints.push({ x: point.x, y: best });
  }

  mountChart(mountEl, (width) =>
    lineChartSvg({
      series: [
        { ...PROGRESS_SERIES[0], points },
        { ...PROGRESS_SERIES[1], step: true, showPoints: false, points: bestPoints },
      ],
      width,
      yFormat: formatSecondsAsTime,
      ariaLabel: `Utvikling på ${selectedDistance} i 2026: ${rows.length} resultater, beste tid ${formatSecondsAsTime(best)}.`,
    }),
  );
}

function activitySectionHtml(personId) {
  const weeks = weeksAscending();
  if (!weeks.length) {
    return "";
  }
  const personResults = resultsForPerson(personId);
  const countByWeek = new Map();
  for (const row of personResults) {
    const week = Number(row.week_number);
    countByWeek.set(week, (countByWeek.get(week) || 0) + 1);
  }

  const items = weeks.map((week) => {
    const number = Number(week.week_number);
    const value = countByWeek.get(number) || 0;
    return {
      value,
      label: number % 4 === 0 ? `U${number}` : "",
      href: hrefWeek(number),
      title: `Uke ${number}: ${value} ${value === 1 ? "løp" : "løp"}`,
    };
  });

  const svg = sparklineSvg({
    items,
    height: 52,
    ariaLabel: `Aktivitet per uke i 2026: ${personResults.length} resultater fordelt på ${countByWeek.size} uker.`,
  });

  return `
    <section class="profile-section" aria-labelledby="profile-activity-title">
      <div class="section-header profile-section-head">
        <div>
          <p class="section-kicker">Aktivitet i sesongen</p>
          <h3 id="profile-activity-title" class="section-heading">Løp per uke</h3>
        </div>
      </div>
      <div class="chart chart--sparkline">${svg}</div>
    </section>
  `;
}

function profileResultsHtml(results) {
  if (!results.length) {
    return `<p class="profile-muted">Ingen publiserte resultater.</p>`;
  }

  return `
    <div class="profile-results-list">
      ${results
        .map((row) => {
          const time = displayTime(row);
          const badges = resultBadges(row);
          const wa = hasFinitePoints(row) ? waChip(row.wa_points, { label: "WA" }) : "";
          const place = hasValue(row.place) ? `<span class="result-pill">#${escapeHtml(row.place)}</span>` : "";
          const classPlace = hasValue(row.class_place)
            ? `<span class="result-pill result-pill--muted">Kl ${escapeHtml(row.class_place)}</span>`
            : "";
          const note = hasValue(row.notes_clean) ? `<p class="profile-result-note">${escapeHtml(row.notes_clean)}</p>` : "";

          return `
            <article class="profile-result-row">
              <div class="profile-result-date">
                <span>${escapeHtml(row.published_date_label || "")}</span>
                <small><a class="quiet-link" href="${hrefWeek(row.week_number)}">Uke ${escapeHtml(row.week_number)}</a></small>
              </div>
              <div class="profile-result-main">
                <div class="profile-result-title">
                  <strong>${escapeHtml(formatEventLabel(row.event_label))}</strong>
                  <span class="profile-result-time">${escapeHtml(time)}${badges ? ` ${badges}` : ""}</span>
                </div>
                <div class="profile-result-meta">
                  ${hasValue(row.distance) ? `<span class="result-pill">${escapeHtml(row.distance)}</span>` : ""}
                  ${hasValue(row.class_name) ? `<span class="result-pill">${escapeHtml(row.class_name)}</span>` : ""}
                  ${place}
                  ${classPlace}
                  ${wa}
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

function renderProfileContent(profile) {
  const results = sortResultsNewestFirst(resultsForPerson(profile.person_id));
  const distancePills = (profile.distances || [])
    .map((distance) => `<span class="result-pill">${escapeHtml(distance)}</span>`)
    .join("");
  const latest = profile.latest_result_date ? `Sist registrert ${escapeHtml(profile.latest_result_date)}` : "";

  const waBest = Number.isFinite(Number(profile.wa_points_best)) && profile.wa_points_best !== null
    ? formatWaPoints(Number(profile.wa_points_best))
    : results.filter(hasFinitePoints).reduce((best, row) => Math.max(best, Math.round(Number(row.wa_points))), 0) || "";
  const pbCount = Number(profile.pb_count ?? results.filter((row) => row.is_pb).length) || 0;

  const statCells = [
    `<div><span>Resultater</span><strong>${formatCount(profile.result_count)}</strong></div>`,
    `<div><span>Distanser</span><strong>${formatCount((profile.distances || []).length)}</strong></div>`,
    `<div><span>Beste WA</span><strong>${waBest || "–"}</strong></div>`,
    pbCount > 0 ? `<div><span>Perser</span><strong>${formatCount(pbCount)}</strong></div>` : "",
    `<div><span>Kjønn</span><strong>${escapeHtml(profile.gender || "–")}</strong></div>`,
  ].filter(Boolean);

  container.innerHTML = `
    <article class="profile-shell">
      <div class="profile-head">
        <div>
          <a class="back-link" href="${hrefPeople()}">Alle personer</a>
          <p class="section-kicker">Personprofil</p>
          <h1>${escapeHtml(profile.display_name || "")}</h1>
          <p class="profile-muted">${formatCount(profile.result_count)} resultater${latest ? ` · ${latest}` : ""}</p>
        </div>
        <div class="profile-stat-grid profile-stat-grid--${statCells.length}" aria-label="Profilstatistikk">
          ${statCells.join("")}
        </div>
      </div>

      ${distancePills ? `<div class="profile-distance-row">${distancePills}</div>` : ""}

      <section class="profile-section" aria-labelledby="profile-best-title">
        <div class="section-header profile-section-head">
          <div>
            <p class="section-kicker">Beste noteringer</p>
            <h3 id="profile-best-title" class="section-heading">Per standarddistanse i 2026</h3>
          </div>
        </div>
        ${bestResultsHtml(profile)}
      </section>

      ${progressionSectionHtml(profile.person_id)}
      ${activitySectionHtml(profile.person_id)}

      <section class="profile-section" aria-labelledby="profile-results-title">
        <div class="section-header profile-section-head">
          <div>
            <p class="section-kicker">Alle resultater</p>
            <h3 id="profile-results-title" class="section-heading">Nyeste først</h3>
          </div>
        </div>
        ${profileResultsHtml(results)}
      </section>
    </article>
  `;

  mountProgressionChart(profile.person_id);

  const chipRow = container.querySelector("#progress-distance-chips");
  if (chipRow) {
    chipRow.addEventListener("click", (event) => {
      const chip = event.target.closest(".event-chip");
      if (!chip) {
        return;
      }
      selectedDistance = chip.dataset.distance || "";
      renderProfileContent(profile);
    });
  }
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render(params) {
  const redirectSlug = state.slugRedirects.get(params.slug);
  if (redirectSlug && redirectSlug !== params.slug) {
    window.location.hash = `/person/${redirectSlug}`;
    return;
  }

  const personId = state.personIdBySlug.get(params.slug);
  const profile = personId ? state.peopleById.get(personId) : null;
  if (!profile) {
    container.innerHTML = profileNotFoundHtml(params.slug);
    return;
  }

  if (currentPersonId !== personId) {
    selectedDistance = "";
    currentPersonId = personId;
  }
  renderProfileContent(profile);
}
