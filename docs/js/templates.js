import { displayTime, displayValue, escapeHtml, formatEventLabel, getEventLabel, hasValue } from "./format.js";
import { hrefPerson, hrefWeek } from "./router.js";
import { resultBadges, waChip } from "./badges.js";

export function personLink(row, className = "person-link") {
  const name = escapeHtml(row.athlete_name || row.display_name || "");
  const slug = row.person_slug || row.profile_slug || "";
  if (!slug) {
    return name;
  }
  return `<a class="${className}" href="${hrefPerson(slug)}">${name}</a>`;
}

export function genderPill(gender) {
  return `<span class="gender-pill">${displayValue(gender)}</span>`;
}

export function splitClass(row) {
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

export function resultTableRowHtml(row) {
  const place = displayValue(row.place);
  const classPlace = displayValue(row.class_place);
  const note = displayValue(row.notes_clean);
  const splitFirst = displayValue(row.split_first_display);
  const splitSecond = displayValue(row.split_second_display);
  const splitDelta = displayValue(row.split_delta_display);
  const badges = resultBadges(row);
  const wa = Number.isFinite(Number(row.wa_points)) && row.wa_points !== null ? waChip(row.wa_points) : `<span class="muted">—</span>`;

  return `
    <tr>
      <td class="athlete">${genderPill(row.gender)} ${personLink(row)}</td>
      <td>${displayValue(row.class_name)}</td>
      <td>${escapeHtml(getEventLabel(row))}</td>
      <td class="muted">${escapeHtml(row.distance || "")}</td>
      <td class="time">${escapeHtml(displayTime(row))}${badges ? ` ${badges}` : ""}</td>
      <td class="wa-cell">${wa}</td>
      <td class="split-time">${splitFirst}</td>
      <td class="split-time">${splitSecond}</td>
      <td class="split-delta ${splitClass(row)}">${splitDelta}</td>
      <td>${place}</td>
      <td>${classPlace}</td>
      <td class="muted">${note}</td>
    </tr>
  `;
}

export function resultCardHtml(row) {
  const time = displayTime(row);
  const eventLabel = getEventLabel(row);
  const badges = resultBadges(row);
  const metaParts = [
    hasValue(row.distance) ? `<span class="result-pill">${escapeHtml(row.distance)}</span>` : "",
    hasValue(row.class_name) ? `<span class="result-pill">${escapeHtml(row.class_name)}</span>` : "",
    hasValue(row.place) ? `<span class="result-pill">Plass ${escapeHtml(row.place)}</span>` : "",
    hasValue(row.class_place) ? `<span class="result-pill result-pill--muted">Klasse ${escapeHtml(row.class_place)}</span>` : "",
    Number.isFinite(Number(row.wa_points)) && row.wa_points !== null ? waChip(row.wa_points, { label: "WA" }) : "",
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
          ${genderPill(row.gender)}
          <strong class="result-card-name">${personLink(row)}${badges ? ` ${badges}` : ""}</strong>
          <div class="result-card-time">${escapeHtml(time)}</div>
        </div>
      </div>
      <div class="result-card-meta">${escapeHtml(eventLabel)}</div>
      ${metaParts.length ? `<div class="result-card-inline">${metaParts.join("")}</div>` : ""}
      ${splitParts.length ? `<div class="result-card-splits">${splitParts.join("")}</div>` : ""}
      ${row.notes_clean ? `<div class="result-card-note">${escapeHtml(row.notes_clean)}</div>` : ""}
    </article>
  `;
}

// Compact ranked line used for WA top lists on the dashboard and stats page.
export function performanceItemHtml(row, rank) {
  const distance = hasValue(row.distance) ? row.distance : row.ranking_distance;
  return `
    <li class="performance-item">
      <span class="ranking-place">${rank}</span>
      <div class="performance-body">
        <div class="performance-line">
          ${genderPill(row.gender)}
          <strong class="performance-name">${personLink(row)}</strong>
          <span class="performance-time">${escapeHtml(row.result_time || displayTime(row))}</span>
          ${waChip(row.wa_points)}
        </div>
        <div class="performance-meta">
          <span>${escapeHtml(String(distance || ""))}</span>
          <span>${escapeHtml(formatEventLabel(row.event_label))}</span>
          ${row.week_number ? `<a class="quiet-link" href="${hrefWeek(row.week_number)}">Uke ${escapeHtml(row.week_number)}</a>` : ""}
        </div>
      </div>
    </li>
  `;
}
