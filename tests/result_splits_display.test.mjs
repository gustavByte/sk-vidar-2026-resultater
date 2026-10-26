import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resultCardHtml, resultTableRowHtml } from "../docs/js/templates.js";

const payload = JSON.parse(readFileSync(new URL("../docs/data/results.json", import.meta.url), "utf8"));
const findResult = (name, event) => payload.results.find(row => row.athlete_name === name && row.event_label === event);

const theodor = findResult("Theodor Berre Jacobsen", "Valencia halvmaraton 2026");

test("Valencia displays the official 10 km and remaining distance in both layouts", () => {
  for (const render of [resultTableRowHtml, resultCardHtml]) {
    const html = render(theodor);
    assert.match(html, /Første 10 km/);
    assert.match(html, /Siste 11,0975 km/);
    assert.match(html, /30:32/);
    assert.match(html, /36:17/);
    assert.doesNotMatch(html, /Første 5 km|Siste 5 km|split-delta--slow|split-delta--fast/);
  }
});

test("each result retains its own halfway distance in a mixed race table", () => {
  const marathon = payload.results.find(row => row.distance === "Maraton" && row.split_first_label === "Første halvmaraton" && row.split_first_display);
  const tenKm = payload.results.find(row => row.distance === "10 km" && row.split_first_label === "Første 5 km" && row.split_first_display);
  const halfMarathon = payload.results.find(row => row.distance === "Halvmaraton" && row.split_first_label === "Første halvdel" && row.split_first_display);
  for (const row of [marathon, tenKm, halfMarathon]) {
    assert.ok(row);
    for (const render of [resultTableRowHtml, resultCardHtml]) {
      const html = render(row);
      assert.ok(html.includes(row.split_first_label));
      assert.ok(html.includes(row.split_second_label));
      assert.ok(html.includes(row.split_first_display));
      assert.ok(html.includes(row.split_second_display));
    }
  }
  const index = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.ok(!index.includes("5 km / split 1") && !index.includes("Siste del / split 2"));
  assert.ok(index.includes("<th>Første del</th>"));
  assert.ok(index.includes("<th>Andre del</th>"));
});

test("an unresolved official passing does not acquire an estimated halfway split", () => {
  const pal = findResult("Pål Erik Johnsen", "Valencia halvmaraton 2026");
  assert.ok(pal);
  assert.doesNotMatch(resultTableRowHtml(pal), /split-time-value|split-time-label/);
  assert.doesNotMatch(resultCardHtml(pal), /result-card-splits/);
});

test("source labels and split values are escaped in the result table", () => {
  const html = resultTableRowHtml({ ...theodor, split_first_label: '<img src=x onerror="alert(1)">', split_first_display: '<script>bad</script>' });
  assert.doesNotMatch(html, /<img|<script>/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;script&gt;/);
});
