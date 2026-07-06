export const numberFormat = new Intl.NumberFormat("nb-NO");

export const eventLabelReplacements = {
  "Fornebul?pet 2026": "Fornebuløpet 2026",
};

export function escapeHtml(value) {
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

export function formatCount(value) {
  return numberFormat.format(value ?? 0);
}

export function preferredScrollBehavior() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/æ/g, "ae")
    .replace(/ø/g, "o")
    .replace(/å/g, "a")
    .replace(/Æ/g, "ae")
    .replace(/Ø/g, "o")
    .replace(/Å/g, "a")
    .toLocaleLowerCase("nb-NO")
    .trim();
}

export function formatEventLabel(value) {
  const eventName = String(value || "").trim();
  return eventLabelReplacements[eventName] || eventName;
}

export function getEventLabel(row) {
  return formatEventLabel(row.event_label || row.event_name);
}

export function displayValue(value) {
  return value ? escapeHtml(value) : "—";
}

export function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

export function displayTime(row) {
  return row.result_time_normalized || row.result_time_raw || "";
}

export function formatSecondsAsTime(seconds) {
  if (!Number.isFinite(seconds)) {
    return "";
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function formatWaPoints(points) {
  if (!Number.isFinite(points)) {
    return "";
  }
  return String(Math.round(points));
}

export function sortResultsNewestFirst(results) {
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
