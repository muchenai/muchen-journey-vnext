import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const board = await readFile(new URL("./index.html", import.meta.url), "utf8");

test("the worldboard is isolated and non-interactive", () => {
  assert.match(board, /隔离视觉资产/);
  assert.match(board, /不属于任何正式黄金路径/);
  assert.match(board, /均为可撤销的视觉假设/);
  assert.doesNotMatch(board, /<a\b|<button\b|<form\b|href="\/(?:app|join)/);
  assert.match(board, /href="five-map-visual-tokens\.css"/);
});

test("the canonical five maps appear once in the route rail and in order", () => {
  const rail = board.match(/<ol class="journey-rail"[\s\S]*?<\/ol>/)?.[0] ?? "";
  const maps = ["探索营", "新手村", "AI学院", "交付线工会", "BOSS副本"];
  let cursor = -1;
  for (const map of maps) {
    const next = rail.indexOf(`<strong>${map}</strong>`, cursor + 1);
    assert.ok(next > cursor, `${map} must appear in canonical order`);
    cursor = next;
  }
  assert.equal((rail.match(/<li>/g) ?? []).length, 5);
});

test("every map has one visual card and the board supports responsive widths", () => {
  for (const className of ["camp", "village", "academy", "guild", "boss"]) {
    assert.match(board, new RegExp(`class="map-card ${className}"`));
  }
  assert.match(board, /@media \(max-width: 900px\)/);
  assert.match(board, /@media \(max-width: 620px\)/);
  assert.match(board, /width=device-width, initial-scale=1/);
});
