import { state } from "../state.js";
import { displayTime, escapeHtml, formatCount, formatEventLabel, formatWaPoints } from "../format.js";
import { hrefStats, hrefWeek } from "../router.js";
import { genderPill, personLink } from "../templates.js?v=20260802-distance1";
import { waChip } from "../badges.js";
import {
  TERRAIN_FILTER_TYPES,
  TERRAIN_TYPE_LABELS,
  biggestEvents,
  competitionDistanceSummary,
  fullRankingList,
  monthsSeries,
  participationTop,
  seasonWaPerPerson,
  seasonWaTopResults,
  terrainEventGroups,
} from "../derive.js?v=20260802-distance1";
import { barChartSvg, chartLegendHtml, mountChart } from "../charts.js";

const SECTIONS = [
  { id: "", label: "Oversikt" },
  { id: "topp-10", label: "Topp 10 per distanse" },
  { id: "hoydepunkter", label: "Høydepunkter" },
  { id: "wa", label: "WA-poeng" },
  { id: "deltakelse", label: "Deltakelse" },
  { id: "maneder", label: "Måned for måned" },
  { id: "lop", label: "Største løp" },
];

let container = null;
let waGender = "all";
let participationGender = "all";
let distanceGender = "all";
let terrainType = "all";
let currentSection = "";
let rankingDistance = "";
let distanceExpanded = false;
let participationExpanded = false;
const expandedColumns = new Set();
const VALID_TERRAIN_TYPES = new Set(["all", ...TERRAIN_FILTER_TYPES]);
const kilometerFormat = new Intl.NumberFormat("nb-NO", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatKilometers(value, { unit = true } = {}) {
  const formatted = kilometerFormat.format(Number(value) || 0);
  return unit ? `${formatted} km` : formatted;
}

function latestStatsDateLabel() {
  const isoDate = String(state.data.stats?.latest_date || "");
  const match = isoDate.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return "";
  }
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  return new Intl.DateTimeFormat("nb-NO", { day: "numeric", month: "long", year: "numeric" }).format(date);
}

function genderMatchesFilter(gender, filter) {
  if (filter === "women") {
    return gender === "K";
  }
  if (filter === "men") {
    return gender === "M";
  }
  return true;
}

// Standard competition ranking: equal values share a place, and the next
// place equals one plus the number of entries ahead (1, 1, 3 rather than
// 1, 1, 2). The input must already be sorted by the ranked value.
export function rankCompetitionEntries(sortedItems, valueFor) {
  const items = Array.isArray(sortedItems) ? sortedItems : [];
  const scores = items.map((item) => {
    const score = Number(valueFor(item));
    return Number.isFinite(score) ? score : 0;
  });
  const groupSizes = new Map();
  scores.forEach((score) => groupSizes.set(score, (groupSizes.get(score) || 0) + 1));

  let previousScore;
  let rank = 0;
  return items.map((item, index) => {
    const score = scores[index];
    if (index === 0 || score !== previousScore) {
      rank = index + 1;
      previousScore = score;
    }
    return {
      item,
      rank,
      score,
      isTied: groupSizes.get(score) > 1,
    };
  });
}

export function rankingThroughPlace(entries, lastPlace) {
  const place = Number(lastPlace);
  if (!Number.isFinite(place) || place < 1) {
    return [];
  }
  return entries.filter((entry) => entry.rank <= place);
}

function subNavHtml(activeSection) {
  return `
    <div class="stats-subnav" role="navigation" aria-label="Statistikkseksjoner">
      ${SECTIONS.map(
        (section) => `
          <a class="event-chip${section.id === activeSection ? " is-active" : ""}" href="${hrefStats(section.id)}"${section.id === activeSection ? ' aria-current="page"' : ""}>${escapeHtml(section.label)}</a>
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

function highlightBadge(label, modifier = "") {
  const className = modifier ? ` highlight-badge--${modifier}` : "";
  return `<span class="highlight-badge${className}">${escapeHtml(label)}</span>`;
}

function highlightTypeBadge(type, activeType = "all") {
  const label = TERRAIN_TYPE_LABELS[type];
  if (!label) {
    return "";
  }
  if (!TERRAIN_FILTER_TYPES.includes(type)) {
    return highlightBadge(label.toLocaleLowerCase("nb-NO"), "muted");
  }
  const active = activeType === type ? " is-active" : "";
  return `<a class="highlight-badge highlight-badge--terrain${active}" href="${hrefStats("hoydepunkter", { type })}">${escapeHtml(label.toLocaleLowerCase("nb-NO"))}</a>`;
}

function highlightTypeBadgesHtml(types, activeType = "all") {
  return types.map((type) => highlightTypeBadge(type, activeType)).filter(Boolean).join(" ");
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

function terrainFilterChipsHtml(activeType, groups) {
  const counts = new Map(TERRAIN_FILTER_TYPES.map((type) => [type, 0]));
  for (const group of groups) {
    for (const type of group.types) {
      if (counts.has(type)) {
        counts.set(type, counts.get(type) + 1);
      }
    }
  }
  const options = [
    { key: "all", label: "Alle", count: groups.length },
    ...TERRAIN_FILTER_TYPES.map((key) => ({ key, label: TERRAIN_TYPE_LABELS[key], count: counts.get(key) || 0 })),
  ];

  return `
    <div class="terrain-filter-row" role="group" aria-label="Terreng- og fjellkategori">
      ${options
        .map(
          (option) => `
            <a class="event-chip${option.key === activeType ? " is-active" : ""}" href="${hrefStats("hoydepunkter", option.key === "all" ? {} : { type: option.key })}"${option.key === activeType ? ' aria-current="page"' : ""}>
              ${escapeHtml(option.label)} <span>${formatCount(option.count)}</span>
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function terrainWeekLinksHtml(weeks) {
  return weeks.map((week) => `<a class="quiet-link" href="${hrefWeek(week)}">Uke ${escapeHtml(week)}</a>`).join(", ");
}

function terrainEventCardsHtml(groups, emptyText, activeType) {
  if (!groups.length) {
    return `<p class="highlight-empty">${escapeHtml(emptyText)}</p>`;
  }

  return `
    <div class="terrain-event-grid">
      ${groups
        .map((group) => {
          const best = group.best || group.rows[0] || {};
          const place = highlightPlaceText(best);
          const resultText = highlightResultText(best);
          const weekLinks = terrainWeekLinksHtml(group.weeks);
          const typeBadges = highlightTypeBadgesHtml(group.types, activeType);
          return `
            <article class="terrain-event-card">
              <div class="terrain-event-head">
                <div>
                  <h3>${escapeHtml(formatEventLabel(group.event_label))}</h3>
                  ${typeBadges ? `<div class="highlight-badges">${typeBadges}</div>` : ""}
                </div>
                <div class="terrain-event-week">${weekLinks}</div>
              </div>
              <div class="terrain-event-stats">
                <span>${formatCount(group.count)} resultater</span>
                <span>${formatCount(group.women)} K · ${formatCount(group.men)} M</span>
              </div>
              <div class="terrain-event-best">
                <span class="terrain-event-label">Beste</span>
                <div class="terrain-event-best-body">
                  <div class="terrain-event-athlete">${genderPill(best.gender)} ${personLink(best)}</div>
                  <div class="terrain-event-result">
                    ${resultText ? `<strong>${escapeHtml(resultText)}</strong>` : ""}
                    ${place ? `<span>${escapeHtml(place)}</span>` : ""}
                  </div>
                </div>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function highlightsSectionHtml() {
  const activeType = VALID_TERRAIN_TYPES.has(terrainType) ? terrainType : "all";
  const allGroups = terrainEventGroups({ limit: 0 });
  const groups = terrainEventGroups({ type: activeType, limit: activeType === "all" ? 6 : 0 });
  const activeLabel = activeType === "all" ? "" : TERRAIN_TYPE_LABELS[activeType];
  const summary =
    activeType === "all"
      ? `Viser ${formatCount(groups.length)} nyeste/store løp. Klikk en kategori for full oversikt.`
      : `Viser alle ${formatCount(groups.length)} løp i kategorien ${activeLabel.toLocaleLowerCase("nb-NO")}.`;

  return `
    <section class="stats-section highlights-section" id="stats-hoydepunkter" aria-labelledby="highlights-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Utenfor de faste rankingene</p>
          <h2 id="highlights-title" class="section-heading">Høydepunkter</h2>
        </div>
        <p class="section-copy">Kort liste som løfter sterke terreng- og fjellresultater der WA-poeng ikke finnes.</p>
      </div>
      ${terrainFilterChipsHtml(activeType, allGroups)}
      <p class="terrain-overview-summary">${escapeHtml(summary)}</p>
      ${terrainEventCardsHtml(groups, "Ingen terreng- eller fjellresultater uten WA-poeng funnet.", activeType)}
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
  if (!rankings.some((group) => group.distance === rankingDistance)) {
    rankingDistance = rankings[0]?.distance || "";
  }
  const distanceNav = rankings
    .map(
      (group) => `<a class="event-chip${group.distance === rankingDistance ? " is-active" : ""}" href="${hrefStats("topp-10", { distanse: group.distance })}"${group.distance === rankingDistance ? ' aria-current="page"' : ""}>${escapeHtml(group.distance || "")}</a>`,
    )
    .join("");
  const cards = rankings
    .filter((group) => group.distance === rankingDistance)
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
      <div class="stats-distance-nav" aria-label="Velg standarddistanse">${distanceNav}</div>
      <div class="rankings-grid">${cards || `<p class="ranking-empty">Ingen ranking-data tilgjengelig.</p>`}</div>
    </section>
  `;
}

function waSectionHtml() {
  const topResults = seasonWaTopResults(200);
  const filteredResults = topResults.filter((row) => genderMatchesFilter(row.gender, waGender)).slice(0, 15);

  const resultRows = filteredResults
    .map(
      (row, index) => `
        <tr>
          <td class="stats-rank" data-label="Plass">${index + 1}</td>
          <td data-label="Løper">${genderPill(row.gender)} ${personLink(row)}</td>
          <td data-label="Løp">${escapeHtml(formatEventLabel(row.event_label))}</td>
          <td class="muted" data-label="Distanse">${escapeHtml(row.distance || "")}</td>
          <td class="time" data-label="Tid">${escapeHtml(displayTime(row))}</td>
          <td class="wa-cell" data-label="WA">${waChip(row.wa_points)}</td>
        </tr>
      `,
    )
    .join("");

  const perPerson = seasonWaPerPerson(0)
    .filter((entry) => genderMatchesFilter(entry.best.gender, waGender))
    .slice(0, 15);

  const personRows = perPerson
    .map(
      (entry, index) => `
        <tr>
          <td class="stats-rank" data-label="Plass">${index + 1}</td>
          <td data-label="Løper">${genderPill(entry.best.gender)} ${personLink(entry.best)}</td>
          <td data-label="Beste resultat">${escapeHtml(displayTime(entry.best))} <span class="muted">${escapeHtml(entry.best.distance || "")}</span></td>
          <td class="wa-cell" data-label="WA">${waChip(entry.best.wa_points)}</td>
          <td class="muted" data-label="Snitt 3 beste">${entry.top3Average !== null ? formatWaPoints(entry.top3Average) : "—"}</td>
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
              <caption class="visually-hidden">Beste enkeltprestasjoner etter World Athletics-poeng</caption>
              <thead>
                <tr><th scope="col">#</th><th scope="col">Løper</th><th scope="col">Løp</th><th scope="col">Distanse</th><th scope="col">Tid</th><th scope="col">WA</th></tr>
              </thead>
              <tbody>${resultRows || `<tr><td colspan="6" class="muted">Ingen WA-graderte resultater.</td></tr>`}</tbody>
            </table>
          </div>
        </div>
        <div class="stats-block">
          <h3 class="stats-block-heading">Beste per person</h3>
          <div class="stats-table-wrap">
            <table class="stats-table">
              <caption class="visually-hidden">Beste World Athletics-resultat per person</caption>
              <thead>
                <tr><th scope="col">#</th><th scope="col">Løper</th><th scope="col">Beste resultat</th><th scope="col">WA</th><th scope="col">Snitt 3 beste</th></tr>
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
  const filtered = participationTop(0).filter((profile) => genderMatchesFilter(profile.gender, participationGender));
  const ranked = rankCompetitionEntries(filtered, (profile) => profile.result_count);
  const leadingEntries = rankingThroughPlace(ranked, 20);
  const visibleEntries = participationExpanded ? ranked : leadingEntries;

  const rows = visibleEntries
    .map(({ item: profile, rank, isTied }) => {
      const rankLabel = isTied ? `Delt ${rank}. plass` : `${rank}. plass`;
      return `
        <tr class="participation-row${rank === 1 ? " participation-row--leader" : ""}">
          <td class="stats-rank participation-rank" data-label="Plass">
            <span class="participation-rank-inner" aria-hidden="true">
              <span class="participation-rank-number">${rank}</span>
              ${isTied ? '<span class="participation-rank-tie">delt</span>' : ""}
            </span>
            <span class="visually-hidden">${rankLabel}</span>
          </td>
          <th class="participation-athlete" scope="row" data-label="Løper">${genderPill(profile.gender)} ${personLink(profile)}</th>
          <td class="participation-count numeric-cell" data-label="Resultater"><strong class="participation-cell-value">${formatCount(profile.result_count)}</strong></td>
          <td class="participation-distances numeric-cell muted" data-label="Ulike distanser"><span class="participation-cell-value">${formatCount((profile.distances || []).length)}</span></td>
        </tr>
      `;
    })
    .join("");

  const toggleLabel = participationExpanded ? "Vis topp 20-plasseringer" : `Vis alle (${formatCount(ranked.length)})`;
  const toggle = ranked.length > leadingEntries.length
    ? `<button class="ranking-toggle participation-toggle" type="button" data-participation-toggle aria-controls="participation-ranking-body" aria-expanded="${participationExpanded ? "true" : "false"}">${toggleLabel}</button>`
    : "";

  return `
    <section class="stats-section participation-section" id="stats-deltakelse" aria-labelledby="participation-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Deltakelse</p>
          <h2 id="participation-title" class="section-heading">Flest resultater</h2>
        </div>
        <p class="section-copy">Rangert etter antall publiserte resultater i 2026. Ulike distanser vises som kontekst.</p>
      </div>
      ${genderChipsHtml("participation", participationGender)}
      <p class="participation-method" id="participation-ranking-method">
        <span class="participation-method-badge">Delt plass</span>
        <span>Lik totalsum gir samme plass. Neste plass følger antall løpere foran – som 1, 1, 3.</span>
      </p>
      <div class="stats-table-wrap stats-table-wrap--narrow participation-table-wrap">
        <table class="stats-table participation-table" aria-describedby="participation-ranking-method">
          <caption class="visually-hidden">Løpere med flest publiserte resultater i 2026. Like resultatantall gir delt plass.</caption>
          <thead>
            <tr><th scope="col">Plass</th><th scope="col">Løper</th><th scope="col" aria-sort="descending">Resultater</th><th scope="col">Ulike distanser</th></tr>
          </thead>
          <tbody id="participation-ranking-body">${rows}</tbody>
        </table>
      </div>
      ${toggle}
    </section>
  `;
}

function distanceTotalText(profile) {
  const prefix = profile.unknown_result_count ? "Minst " : "";
  return `${prefix}${formatKilometers(profile.total_km)}`;
}

function distancePodiumHtml(leaders) {
  if (!leaders.length) {
    return `<p class="ranking-empty">Ingen resultater med sikkert kjent distanse.</p>`;
  }

  const maxDistance = leaders[0].total_km || 1;
  return `
    <ol class="distance-podium" aria-label="Topp tre på konkurransekilometer">
      ${leaders.slice(0, 3).map((profile, index) => {
        const share = Math.max(4, (profile.total_km / maxDistance) * 100);
        const uncertainty = profile.unknown_result_count
          ? `<span class="distance-uncertain">+ ${formatCount(profile.unknown_result_count)} løp uten kjent distanse</span>`
          : "";
        return `
          <li class="distance-podium-card distance-podium-card--${index + 1}">
            <div class="distance-podium-topline">
              <span class="distance-podium-place">${index + 1}</span>
              <span class="distance-podium-count">${formatCount(profile.result_count)} løp telt</span>
            </div>
            <div class="distance-podium-athlete">${genderPill(profile.gender)} ${personLink(profile)}</div>
            <strong class="distance-podium-total">${escapeHtml(distanceTotalText(profile))}</strong>
            <div class="distance-podium-track" aria-hidden="true"><span style="width: ${share.toFixed(2)}%"></span></div>
            ${uncertainty}
          </li>
        `;
      }).join("")}
    </ol>
  `;
}

function competitionDistanceSectionHtml() {
  const summary = competitionDistanceSummary();
  const leaders = summary.leaders.filter((profile) => genderMatchesFilter(profile.gender, distanceGender));
  const visibleLeaders = distanceExpanded ? leaders : leaders.slice(0, 50);
  const maxDistance = leaders[0]?.total_km || 1;
  const filteredTotalKm = leaders.reduce((sum, profile) => sum + profile.total_km, 0);
  const filteredResultCount = leaders.reduce((sum, profile) => sum + profile.result_count, 0);

  const rows = visibleLeaders
    .map((profile, index) => {
      const barWidth = Math.max(2, (profile.total_km / maxDistance) * 100);
      const longestEvent = formatEventLabel(profile.longest_event_label);
      const uncertainty = profile.unknown_result_count
        ? `<span class="distance-uncertain">Minst – ${formatCount(profile.unknown_result_count)} løp mangler sikker distanse</span>`
        : "";
      return `
        <tr>
          <td class="stats-rank" data-label="Plass">${index + 1}</td>
          <th class="distance-athlete" scope="row" data-label="Løper">${genderPill(profile.gender)} ${personLink(profile)}</th>
          <td class="distance-total-cell" data-label="Konkurranse-km">
            <strong>${escapeHtml(distanceTotalText(profile))}</strong>
            <span class="distance-row-track" aria-hidden="true"><span style="width: ${barWidth.toFixed(2)}%"></span></span>
            ${uncertainty}
          </td>
          <td class="numeric-cell" data-label="Løp telt">${formatCount(profile.result_count)}</td>
          <td class="distance-longest" data-label="Lengste enkeltløp">
            <strong>${escapeHtml(formatKilometers(profile.longest_km))}</strong>
            ${longestEvent ? `<span title="${escapeHtml(longestEvent)}">${escapeHtml(longestEvent)}</span>` : ""}
          </td>
        </tr>
      `;
    })
    .join("");

  const coverage = summary.eligibleResultCount
    ? (summary.includedResultCount / summary.eligibleResultCount) * 100
    : 0;
  const toggle = leaders.length > 50
    ? `<button class="ranking-toggle distance-toggle" type="button" data-distance-toggle aria-expanded="${distanceExpanded ? "true" : "false"}">${
        distanceExpanded ? "Vis topp 50" : `Vis alle (${formatCount(leaders.length)})`
      }</button>`
    : "";

  return `
    <section class="stats-section distance-section" id="stats-kilometer" aria-labelledby="distance-title">
      <div class="section-header">
        <div>
          <p class="section-kicker">Konkurransevolum</p>
          <h2 id="distance-title" class="section-heading">Flest konkurransekilometer</h2>
        </div>
        <p class="section-copy">Summen av den nominelle løpsdistansen i alle publiserte konkurranser så langt i 2026.</p>
      </div>
      ${genderChipsHtml("distance", distanceGender)}
      <div class="distance-summary-grid" aria-label="Oppsummering for valgt kjønnsfilter">
        <div class="distance-summary distance-summary--primary">
          <span>Konkurranse-km i visningen</span>
          <strong>${escapeHtml(formatKilometers(filteredTotalKm))}</strong>
        </div>
        <div class="distance-summary">
          <span>Løpere med kjent distanse</span>
          <strong>${formatCount(leaders.length)}</strong>
        </div>
        <div class="distance-summary">
          <span>Resultater telt i visningen</span>
          <strong>${formatCount(filteredResultCount)}</strong>
        </div>
      </div>
      ${distancePodiumHtml(leaders)}
      <p class="distance-method-note">
        <strong>${formatCount(summary.includedResultCount)} av ${formatCount(summary.eligibleResultCount)}</strong> tellbare resultater har sikkert kjent distanse (${kilometerFormat.format(coverage)} %).
        ${summary.unknownResultCount ? `${formatCount(summary.unknownResultCount)} er foreløpig utelatt.` : ""}
        ${summary.excludedAggregateCount ? `${formatCount(summary.excludedAggregateCount)} sammenlagtplasseringer teller ikke som egne løp.` : ""}
      </p>
      <div class="stats-table-wrap distance-table-wrap">
        <table class="stats-table distance-table">
          <caption class="visually-hidden">Rangering etter samlede konkurransekilometer i 2026</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Løper</th>
              <th scope="col">Konkurranse-km</th>
              <th scope="col">Løp telt</th>
              <th scope="col">Lengste enkeltløp</th>
            </tr>
          </thead>
          <tbody>${rows || `<tr><td colspan="5" class="muted">Ingen resultater med sikkert kjent distanse.</td></tr>`}</tbody>
        </table>
      </div>
      ${toggle}
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
          <td data-label="Måned">${escapeHtml(month.month_label)}</td>
          <td data-label="Resultater">${formatCount(month.result_count)}</td>
          <td data-label="Løpere">${formatCount(month.athlete_count ?? 0)}</td>
          <td data-label="Løp">${formatCount(month.event_count ?? 0)}</td>
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
          <caption class="visually-hidden">Resultatvolum måned for måned i 2026</caption>
          <thead>
            <tr><th scope="col">Måned</th><th scope="col">Resultater</th><th scope="col">Løpere</th><th scope="col">Løp</th></tr>
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
          <td class="stats-rank" data-label="Plass">${index + 1}</td>
          <td data-label="Løp">${escapeHtml(formatEventLabel(entry.event_label))}</td>
          <td data-label="Deltakere">${formatCount(entry.count)}</td>
          <td class="muted" data-label="Kvinner / menn">${formatCount(entry.women)} K · ${formatCount(entry.men)} M</td>
          <td class="muted" data-label="Uke">${weekLinks}</td>
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
          <caption class="visually-hidden">Løp med flest unike SK Vidar-deltakere i 2026</caption>
          <thead>
            <tr><th scope="col">#</th><th scope="col">Løp</th><th scope="col">Deltakere</th><th scope="col">K/M</th><th scope="col">Uke</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

function overviewHtml() {
  const resultCount = state.data.results?.length || 0;
  const peopleCount = state.data.people?.profile_count || state.data.people?.profiles?.length || 0;
  const eventCount = new Set((state.data.results || []).map((row) => row.event_id || row.event_label).filter(Boolean)).size;
  const waCount = (state.data.results || []).filter((row) => row.wa_points !== null && row.wa_points !== undefined).length;
  const items = [
    { section: "topp-10", label: "Standarddistanser", value: `${state.data.rankings?.length || 0} distanser`, copy: "Beste tid per løper, kvinner og menn hver for seg." },
    { section: "hoydepunkter", label: "Høydepunkter", value: `${terrainEventGroups({ limit: 0 }).length} løp`, copy: "Terreng, fjell, trail og skyrace uten WA-poeng." },
    { section: "wa", label: "WA-poeng", value: `${formatCount(waCount)} resultater`, copy: "Sammenlign prestasjoner på tvers av graderbare distanser." },
    { section: "deltakelse", label: "Flest resultater", value: `${formatCount(peopleCount)} løpere`, copy: "Se hvem som har flest publiserte resultater." },
    { section: "maneder", label: "Måned for måned", value: `${formatCount(resultCount)} resultater`, copy: "Følg sesongvolumet gjennom året." },
    { section: "lop", label: "Største løp", value: `${formatCount(eventCount)} løp`, copy: "Arrangementene med flest unike SK Vidar-deltakere." },
  ];
  return `
    <section class="stats-overview" aria-labelledby="stats-overview-title">
      <h2 id="stats-overview-title" class="visually-hidden">Statistikkoversikt</h2>
      ${items.map((item) => `
        <a class="stats-overview-item" href="${hrefStats(item.section)}">
          <span class="stats-overview-label">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <span>${escapeHtml(item.copy)}</span>
        </a>
      `).join("")}
    </section>
  `;
}

function renderContent(activeSection) {
  const sectionRenderers = {
    "topp-10": rankingsSectionHtml,
    hoydepunkter: highlightsSectionHtml,
    wa: waSectionHtml,
    deltakelse: participationSectionHtml,
    kilometer: competitionDistanceSectionHtml,
    maneder: monthsSectionHtml,
    lop: eventsSectionHtml,
  };
  const content = activeSection ? sectionRenderers[activeSection]?.() || overviewHtml() : overviewHtml();
  const dateLabel = latestStatsDateLabel();
  container.innerHTML = `
    <div class="stats-shell">
      <header class="stats-page-header">
        <div>
          <p class="section-kicker">Sesongen 2026</p>
          <h1 class="stats-page-title">Statistikk</h1>
          <p class="stats-page-intro">Prestasjoner, deltakelse og løpsvolum – samlet på ett sted.</p>
        </div>
        ${dateLabel ? `<p class="stats-as-of"><span>Oppdatert til</span><strong>${escapeHtml(dateLabel)}</strong></p>` : ""}
      </header>
      ${subNavHtml(activeSection)}
      ${content}
    </div>
  `;

  if (activeSection === "maneder") {
    mountMonthsChart();
  }

  container.querySelectorAll("[data-gender-group]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.genderGroup === "wa") {
        waGender = button.dataset.gender;
      } else if (button.dataset.genderGroup === "distance") {
        distanceGender = button.dataset.gender;
      } else {
        participationGender = button.dataset.gender;
        participationExpanded = false;
      }
      const genderByGroup = {
        wa: waGender,
        distance: distanceGender,
        participation: participationGender,
      };
      const params = { kjonn: genderByGroup[button.dataset.genderGroup] || "all" };
      window.location.hash = hrefStats(currentSection, params);
    });
  });

  container.querySelector("[data-distance-toggle]")?.addEventListener("click", () => {
    distanceExpanded = !distanceExpanded;
    renderContent(currentSection);
  });

  container.querySelector("[data-participation-toggle]")?.addEventListener("click", () => {
    participationExpanded = !participationExpanded;
    renderContent(currentSection);
  });

  container.querySelectorAll(".ranking-toggle[data-column]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.column;
      if (expandedColumns.has(key)) {
        expandedColumns.delete(key);
      } else {
        expandedColumns.add(key);
      }
      renderContent(currentSection);
    });
  });
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render(params) {
  const section = params.section || "";
  currentSection = section;
  terrainType = VALID_TERRAIN_TYPES.has(params.type) ? params.type : "all";
  rankingDistance = params.distanse || rankingDistance;
  waGender = ["all", "women", "men"].includes(params.kjonn) ? params.kjonn : "all";
  participationGender = ["all", "women", "men"].includes(params.kjonn) ? params.kjonn : "all";
  distanceGender = ["all", "women", "men"].includes(params.kjonn) ? params.kjonn : "all";
  renderContent(section);
  requestAnimationFrame(() => {
    const nav = container.querySelector(".stats-subnav");
    const active = nav?.querySelector('[aria-current="page"]');
    if (nav && active) {
      nav.scrollLeft = Math.max(0, active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2);
    }
  });
}
