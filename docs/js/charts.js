import { escapeHtml } from "./format.js";

// All chart helpers return SVG markup as strings, sized via viewBox so the
// CSS can scale them to the container width. No animation, no dependencies.

function niceCeil(value) {
  if (!Number.isFinite(value) || value <= 0) {
    return 1;
  }
  const power = 10 ** Math.floor(Math.log10(value));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (factor * power >= value) {
      return factor * power;
    }
  }
  return 10 * power;
}

const TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];

function timeTicks(min, max) {
  const range = Math.max(max - min, 1);
  let step = TIME_STEPS[TIME_STEPS.length - 1];
  for (const candidate of TIME_STEPS) {
    if (range / candidate <= 4) {
      step = candidate;
      break;
    }
  }
  const ticks = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + 1e-9; tick += step) {
    ticks.push(tick);
  }
  return ticks;
}

export function chartLegendHtml(series) {
  const items = series
    .map(
      (entry) => `
        <span class="chart-legend-item">
          <span class="chart-legend-swatch" style="background:${entry.color}"></span>${escapeHtml(entry.name)}
        </span>
      `,
    )
    .join("");
  return `<div class="chart-legend">${items}</div>`;
}

// Mounts a chart into an element sized to the element's current width, so SVG
// text renders at ~1:1 scale on both mobile and desktop.
export function mountChart(el, build) {
  if (!el) {
    return;
  }
  const width = Math.max(Math.round(el.clientWidth || 0), 320);
  el.innerHTML = build(width);
}

export function barChartSvg({ items, series, width = 800, xTickEvery = 1, height = 190, ariaLabel = "", formatValue = String }) {
  if (!items.length) {
    return "";
  }

  const pad = { top: 10, right: 6, bottom: 22, left: 38 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const maxTotal = Math.max(...items.map((item) => item.values.reduce((sum, value) => sum + (value || 0), 0)), 1);
  const yMax = niceCeil(maxTotal);
  const scale = innerHeight / yMax;
  const slot = innerWidth / items.length;
  const barWidth = Math.min(slot * 0.72, 34);
  const baseline = pad.top + innerHeight;

  const gridlines = [0, yMax / 2, yMax]
    .map((tick) => {
      const y = baseline - tick * scale;
      const label = tick === 0 ? "0" : formatValue(Math.round(tick));
      return `
        <line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="chart-grid-line" />
        <text x="${pad.left - 6}" y="${y + 3}" text-anchor="end">${escapeHtml(label)}</text>
      `;
    })
    .join("");

  const bars = items
    .map((item, index) => {
      const x = pad.left + slot * index + (slot - barWidth) / 2;
      let cursorY = baseline;
      const segments = item.values
        .map((value, seriesIndex) => {
          const segmentHeight = Math.max((value || 0) * scale, 0);
          cursorY -= segmentHeight;
          if (segmentHeight <= 0) {
            return "";
          }
          return `<rect x="${x.toFixed(1)}" y="${cursorY.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${segmentHeight.toFixed(1)}" fill="${series[seriesIndex]?.color || "currentColor"}" />`;
        })
        .join("");
      const title = item.title ? `<title>${escapeHtml(item.title)}</title>` : "";
      const showLabel = index % xTickEvery === 0 || index === items.length - 1;
      const label = showLabel
        ? `<text x="${(pad.left + slot * index + slot / 2).toFixed(1)}" y="${height - 7}" text-anchor="middle">${escapeHtml(item.label)}</text>`
        : "";
      const group = `<g>${title}${segments}</g>`;
      const linked = item.href ? `<a href="${escapeHtml(item.href)}" aria-label="${escapeHtml(item.title || item.label)}">${group}</a>` : group;
      return `${linked}${label}`;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}" xmlns="http://www.w3.org/2000/svg">
      ${gridlines}
      ${bars}
    </svg>
  `;
}

function buildLinePath(coords, step) {
  if (!coords.length) {
    return "";
  }
  const [first, ...rest] = coords;
  let path = `M ${first.x.toFixed(1)} ${first.y.toFixed(1)}`;
  for (const point of rest) {
    if (step) {
      path += ` H ${point.x.toFixed(1)} V ${point.y.toFixed(1)}`;
    } else {
      path += ` L ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    }
  }
  return path;
}

// Time-series line chart. Y values are seconds; the smallest value renders at
// the top so a faster time is visually higher.
export function lineChartSvg({ series, width = 800, height = 220, yFormat = String, xFormat, ariaLabel = "" }) {
  const allPoints = series.flatMap((entry) => entry.points);
  if (!allPoints.length) {
    return "";
  }

  const pad = { top: 12, right: 14, bottom: 24, left: 52 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;

  let xMin = Math.min(...allPoints.map((point) => point.x));
  let xMax = Math.max(...allPoints.map((point) => point.x));
  if (xMin === xMax) {
    xMin -= 86400000;
    xMax += 86400000;
  }

  let yMin = Math.min(...allPoints.map((point) => point.y));
  let yMax = Math.max(...allPoints.map((point) => point.y));
  const spread = yMax - yMin;
  const padding = spread > 0 ? spread * 0.08 : Math.max(yMin * 0.05, 1);
  yMin -= padding;
  yMax += padding;

  const xPos = (value) => pad.left + ((value - xMin) / (xMax - xMin)) * innerWidth;
  const yPos = (value) => pad.top + ((value - yMin) / (yMax - yMin)) * innerHeight;

  const gridlines = timeTicks(yMin, yMax)
    .map(
      (tick) => `
        <line x1="${pad.left}" y1="${yPos(tick).toFixed(1)}" x2="${width - pad.right}" y2="${yPos(tick).toFixed(1)}" class="chart-grid-line" />
        <text x="${pad.left - 6}" y="${(yPos(tick) + 3).toFixed(1)}" text-anchor="end">${escapeHtml(yFormat(tick))}</text>
      `,
    )
    .join("");

  const formatX = xFormat || ((value) => new Date(value).toLocaleDateString("nb-NO", { day: "2-digit", month: "2-digit" }));
  const xLabels = [
    `<text x="${pad.left}" y="${height - 7}" text-anchor="start">${escapeHtml(formatX(xMin))}</text>`,
    `<text x="${width - pad.right}" y="${height - 7}" text-anchor="end">${escapeHtml(formatX(xMax))}</text>`,
  ].join("");

  const layers = series
    .map((entry) => {
      const coords = entry.points.map((point) => ({ ...point, x: xPos(point.x), y: yPos(point.y) }));
      const path = buildLinePath(coords, entry.step);
      const line = path
        ? `<path d="${path}" fill="none" stroke="${entry.color}" stroke-width="${entry.step ? 1.6 : 2}" ${entry.step ? 'stroke-dasharray="1 0"' : ""} stroke-linejoin="round" stroke-linecap="round" />`
        : "";
      const dots = entry.showPoints === false
        ? ""
        : coords
            .map((point) => {
              const title = point.title ? `<title>${escapeHtml(point.title)}</title>` : "";
              const circle = `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.6" fill="${entry.color}">${title}</circle>`;
              return point.href ? `<a href="${escapeHtml(point.href)}" aria-label="${escapeHtml(point.title || "")}">${circle}</a>` : circle;
            })
            .join("");
      return `${line}${dots}`;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}" xmlns="http://www.w3.org/2000/svg">
      ${gridlines}
      ${xLabels}
      ${layers}
    </svg>
  `;
}

// Compact activity strip: one slim bar per slot (e.g. week), zero values shown
// as a faint stub so gaps stay visible.
export function sparklineSvg({ items, height = 42, color = "var(--accent)", ariaLabel = "" }) {
  if (!items.length) {
    return "";
  }

  const slot = 16;
  const width = items.length * slot;
  const pad = { top: 4, bottom: 14 };
  const innerHeight = height - pad.top - pad.bottom;
  const maxValue = Math.max(...items.map((item) => item.value || 0), 1);

  const bars = items
    .map((item, index) => {
      const x = index * slot + 3;
      const value = item.value || 0;
      const barHeight = value > 0 ? Math.max((value / maxValue) * innerHeight, 4) : 2;
      const y = pad.top + innerHeight - barHeight;
      const fill = value > 0 ? color : "var(--chart-grid)";
      const title = item.title ? `<title>${escapeHtml(item.title)}</title>` : "";
      const rect = `<rect x="${x}" y="${y.toFixed(1)}" width="${slot - 6}" height="${barHeight.toFixed(1)}" rx="2" fill="${fill}">${title}</rect>`;
      const label = item.label
        ? `<text x="${x + (slot - 6) / 2}" y="${height - 3}" text-anchor="middle">${escapeHtml(item.label)}</text>`
        : "";
      const linked = item.href ? `<a href="${escapeHtml(item.href)}" aria-label="${escapeHtml(item.title || "")}">${rect}</a>` : rect;
      return `${linked}${label}`;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}" xmlns="http://www.w3.org/2000/svg" class="sparkline">
      ${bars}
    </svg>
  `;
}
