// Session lists that arrive out of order: only one newer than the last applied is applied.
import { test } from "node:test";
import assert from "node:assert/strict";
import { ListOrder } from "./list-order.ts";
import type { ListResult } from "./reconcile.ts";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

test("ignores an older-started list that arrives after a newer one", async () => {
  const order = new ListOrder();
  const older = deferred<ListResult>();
  const newer = deferred<ListResult>();
  const calls = [older, newer];
  const fetchList = order.wrap(() => calls.shift()!.promise);
  const first = fetchList(); // started first
  const second = fetchList(); // started second
  newer.resolve({ list: [{ id: "N" }] as never, serverOffsetMs: 0 });
  const b = await second;
  assert.equal(order.accept(b.list), true);
  older.resolve({ list: [] as never, serverOffsetMs: 0 });
  const a = await first;
  assert.equal(order.accept(a.list), false);
});

test("applies lists that arrive in the order they started", async () => {
  const order = new ListOrder();
  const a = await order.track(async () => [1], (l) => l);
  assert.equal(order.accept(a), true);
  const b = await order.track(async () => [2], (l) => l);
  assert.equal(order.accept(b), true);
});

test("track and wrap share one order", async () => {
  const order = new ListOrder();
  const slow = deferred<number[]>();
  const viaTrack = order.track(() => slow.promise, (l) => l);
  const viaWrap = await order.wrap(async () => ({ list: [], serverOffsetMs: 0 }))();
  assert.equal(order.accept(viaWrap.list), true);
  slow.resolve([1]);
  assert.equal(order.accept(await viaTrack), false);
});

test("a list it did not stamp is applied", () => {
  assert.equal(new ListOrder().accept([]), true);
});
