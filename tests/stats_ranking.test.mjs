import assert from "node:assert/strict";
import test from "node:test";

import { rankCompetitionEntries, rankingThroughPlace } from "../docs/js/views/stats.js";

const rankCounts = (counts) => rankCompetitionEntries(counts, (count) => count);

test("equal result counts share a standard competition place", () => {
  const ranked = rankCounts([14, 14, 14, 13, 13, 12]);

  assert.deepEqual(
    ranked.map(({ rank }) => rank),
    [1, 1, 1, 4, 4, 6],
  );
  assert.deepEqual(
    ranked.map(({ isTied }) => isTied),
    [true, true, true, true, true, false],
  );
});

test("ranking is recalculated after applying a gender filter", () => {
  const profiles = [
    { gender: "K", result_count: 14 },
    { gender: "K", result_count: 14 },
    { gender: "M", result_count: 14 },
    { gender: "K", result_count: 13 },
    { gender: "M", result_count: 13 },
    { gender: "M", result_count: 12 },
  ];
  const women = rankCompetitionEntries(
    profiles.filter(({ gender }) => gender === "K"),
    ({ result_count }) => result_count,
  );
  const men = rankCompetitionEntries(
    profiles.filter(({ gender }) => gender === "M"),
    ({ result_count }) => result_count,
  );

  assert.deepEqual(women.map(({ rank }) => rank), [1, 1, 3]);
  assert.deepEqual(men.map(({ rank }) => rank), [1, 2, 3]);
});

test("top-place cutoff keeps the complete tied group", () => {
  const nineteenUniqueScores = Array.from({ length: 19 }, (_, index) => 40 - index);
  const ranked = rankCounts([...nineteenUniqueScores, 10, 10, 10, 9]);
  const visible = rankingThroughPlace(ranked, 20);

  assert.equal(visible.length, 22);
  assert.deepEqual(visible.slice(-3).map(({ rank }) => rank), [20, 20, 20]);
  assert.equal(ranked.at(-1).rank, 23);
});
