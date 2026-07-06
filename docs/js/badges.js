import { escapeHtml, formatWaPoints } from "./format.js";

export function badgePb() {
  return `<span class="badge badge--pb" title="Personlig rekord (fra kildens notater)">PB</span>`;
}

export function badgeSb() {
  return `<span class="badge badge--sb" title="Sesongbeste (fra kildens notater)">SB</span>`;
}

export function badgeWin() {
  return `<span class="badge badge--win" title="Seier">1.</span>`;
}

export function waChip(points, { label = "" } = {}) {
  const value = formatWaPoints(Number(points));
  if (!value) {
    return "";
  }
  const prefix = label ? `<strong>${escapeHtml(label)}</strong>` : "";
  return `<span class="wa-chip" title="World Athletics-poeng">${prefix}${value}</span>`;
}

const WIN_TOKENS = new Set(["1. plass", "1.plass", "1. kvinne", "1. mann"]);

function hasWinToken(note) {
  if (!note) {
    return false;
  }
  return String(note)
    .split(/[;,]/)
    .some((part) => WIN_TOKENS.has(part.trim().toLocaleLowerCase("nb-NO")));
}

export function isWin(row) {
  return String(row.place ?? "").trim() === "1" || hasWinToken(row.notes_clean);
}

// PB takes precedence over SB when a note carries both tokens.
export function resultBadges(row) {
  const parts = [];
  if (isWin(row)) {
    parts.push(badgeWin());
  }
  if (row.is_pb) {
    parts.push(badgePb());
  } else if (row.is_sb) {
    parts.push(badgeSb());
  }
  return parts.join(" ");
}
