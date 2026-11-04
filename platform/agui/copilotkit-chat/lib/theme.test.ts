import assert from "node:assert/strict";
import { test } from "node:test";
import { effectiveTheme, parseTheme } from "./theme.ts";

test("parseTheme: \"light\" or \"dark\" pass through; anything else is \"system\"", () => {
  assert.equal(parseTheme("light"), "light");
  assert.equal(parseTheme("dark"), "dark");
  assert.equal(parseTheme("system"), "system");
  assert.equal(parseTheme(null), "system");
  assert.equal(parseTheme(""), "system");
  assert.equal(parseTheme("junk"), "system");
});

test("effectiveTheme: an explicit choice wins outright; \"system\" follows systemDark", () => {
  assert.equal(effectiveTheme("light", true), "light");
  assert.equal(effectiveTheme("light", false), "light");
  assert.equal(effectiveTheme("dark", true), "dark");
  assert.equal(effectiveTheme("dark", false), "dark");
  assert.equal(effectiveTheme("system", true), "dark");
  assert.equal(effectiveTheme("system", false), "light");
});
