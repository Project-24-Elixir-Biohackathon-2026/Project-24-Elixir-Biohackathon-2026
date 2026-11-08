import assert from "node:assert/strict";
import { test } from "node:test";
import { focusLost, menuIndex, popoverPosition, refocusIfLost } from "./menu.ts";

const view = { width: 1280, height: 800 };
const size = { width: 180, height: 200 };
const anchor = (top: number, left: number) => ({ top, bottom: top + 28, left, right: left + 28 });

test("popoverPosition: under the anchor, left edges aligned", () => {
  assert.deepEqual(popoverPosition(anchor(100, 200), size, view), { top: 132, left: 200, above: false });
});

test("popoverPosition: flips above when it would leave the viewport at the bottom", () => {
  assert.deepEqual(popoverPosition(anchor(700, 200), size, view), { top: 496, left: 200, above: true });
});

test("popoverPosition: no room either side keeps it under, clamped into the viewport", () => {
  const tall = { width: 180, height: 790 };
  assert.deepEqual(popoverPosition(anchor(300, 200), tall, view), { top: 8, left: 200, above: false });
});

test("popoverPosition: pushed left to stay inside the right edge, never past the left one", () => {
  assert.equal(popoverPosition(anchor(100, 1200), size, view).left, 1280 - 8 - 180);
  assert.equal(popoverPosition(anchor(100, 2), size, view).left, 8);
});

test("menuIndex: arrows wrap, Home and End jump, other keys are not the menu's", () => {
  assert.equal(menuIndex("ArrowDown", -1, 5), 0);
  assert.equal(menuIndex("ArrowDown", 4, 5), 0);
  assert.equal(menuIndex("ArrowDown", 1, 5), 2);
  assert.equal(menuIndex("ArrowUp", -1, 5), 4);
  assert.equal(menuIndex("ArrowUp", 0, 5), 4);
  assert.equal(menuIndex("ArrowUp", 3, 5), 2);
  assert.equal(menuIndex("Home", 3, 5), 0);
  assert.equal(menuIndex("End", 0, 5), 4);
  assert.equal(menuIndex("Enter", 0, 5), null);
  assert.equal(menuIndex("ArrowDown", -1, 0), null);
});

test("focusLost: only a press that left focus on the page itself, or nowhere", () => {
  const body = { name: "body" };
  const root = { name: "html" };
  const page = { body, documentElement: root };
  assert.equal(focusLost(body, page), true);
  assert.equal(focusLost(root, page), true);
  assert.equal(focusLost(null, page), true);
  assert.equal(focusLost({ name: "textarea" }, page), false);
  assert.equal(focusLost({ name: "another row's button" }, page), false);
});

test("refocusIfLost: waits for the press's own focus change, then refocuses the ⋯ only if focus was lost", () => {
  const body = { name: "body" };
  const page = { body, documentElement: { name: "html" }, activeElement: body as object | null };
  const focused: unknown[] = [];
  const trigger = { focus: (o?: unknown) => focused.push(o) };
  let later: (() => void) | undefined;
  const schedule = (f: () => void) => { later = f; };

  refocusIfLost(page, () => trigger, schedule);
  assert.equal(focused.length, 0, "nothing before the press has moved focus");
  later!();
  assert.deepEqual(focused, [{ preventScroll: true }]);

  // The press landed on something focusable: focus stays where it put it.
  focused.length = 0;
  page.activeElement = { name: "textarea" };
  refocusIfLost(page, () => trigger, schedule);
  later!();
  assert.equal(focused.length, 0);

  // The ⋯ is gone by then (its row left the list): nothing to do.
  page.activeElement = body;
  refocusIfLost(page, () => undefined, schedule);
  assert.doesNotThrow(() => later!());
});
