import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT, MAX, MIN, STEP, VIEWPORT_MARGIN, clampWidth, maxFor, parseWidth, stepWidth } from "./sidebar-width.ts";

test("clampWidth keeps a value inside [MIN, MAX], clamps outside it", () => {
  assert.equal(clampWidth(MIN), MIN);
  assert.equal(clampWidth(MAX), MAX);
  assert.equal(clampWidth(320), 320);
  assert.equal(clampWidth(MIN - 50), MIN);
  assert.equal(clampWidth(MAX + 50), MAX);
});

test("parseWidth: a valid stored width, clamped; DEFAULT for null, junk or NaN", () => {
  assert.equal(parseWidth("320"), 320);
  assert.equal(parseWidth(String(MAX + 100)), MAX);
  assert.equal(parseWidth(String(MIN - 100)), MIN);
  assert.equal(parseWidth(null), DEFAULT);
  assert.equal(parseWidth(""), DEFAULT);
  assert.equal(parseWidth("not a number"), DEFAULT);
  assert.equal(parseWidth("NaN"), DEFAULT);
});

test("stepWidth moves by STEP and clamps at the bounds", () => {
  assert.equal(stepWidth(260, 1), 260 + STEP);
  assert.equal(stepWidth(260, -1), 260 - STEP);
  assert.equal(stepWidth(MAX, 1), MAX);
  assert.equal(stepWidth(MIN, -1), MIN);
});

test("maxFor: the viewport's width minus the margin, never above MAX, never below 0", () => {
  assert.equal(maxFor(375), 375 - VIEWPORT_MARGIN); // a phone: well under MAX
  assert.equal(maxFor(1200), MAX); // a desktop: the margin would allow more than MAX
  assert.equal(maxFor(MAX + VIEWPORT_MARGIN), MAX); // exactly at the MAX boundary
  assert.equal(maxFor(VIEWPORT_MARGIN), 0); // viewport no wider than the margin itself
  assert.equal(maxFor(10), 0); // narrower still: never negative
});
