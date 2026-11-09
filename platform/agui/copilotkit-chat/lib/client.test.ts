import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, askTitle, fetchSession, fetchSessions, removeSession, tagSuggestions, updateSession } from "./client.ts";
import type { Fetch } from "./client.ts";
import type { SessionMeta } from "./sessions.ts";

const ID = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f";

function fake(status: number, body: unknown, seen: { url?: string; init?: RequestInit } = {}): Fetch {
  return async (url, init) => {
    seen.url = url;
    seen.init = init;
    return status === 204 ? new Response(null, { status }) : Response.json(body, { status });
  };
}

function meta(id: string, updated_at: string, extra: Partial<SessionMeta> = {}): SessionMeta {
  return {
    id, title: id, tags: [], pinned: false, hidden: false, created_at: updated_at, updated_at, last_run_at: null,
    running: false, ...extra,
  };
}

test("fetchSession: 404 is null, 500 an ApiError with the generic message", async () => {
  assert.equal(await fetchSession(ID, fake(404, { error: "not found" })), null);
  await assert.rejects(fetchSession(ID, fake(500, { error: "internal error" })),
    (e: unknown) => e instanceof ApiError && e.status === 500 && e.message === "Opening the session failed (500): internal error");
});

test("updateSession sends a JSON PATCH and returns the new metadata", async () => {
  const seen: { url?: string; init?: RequestInit } = {};
  const out = await updateSession(ID, { pinned: true }, fake(200, meta(ID, "t", { pinned: true }), seen));
  assert.equal(seen.url, `/api/sessions/${ID}`);
  assert.equal(seen.init?.method, "PATCH");
  assert.equal(seen.init?.body, '{"pinned":true}');
  assert.equal(out.pinned, true);
  await assert.rejects(updateSession(ID, { tags: ["Bad Tag!"] }, fake(400, { error: "invalid tags" })),
    /Saving the change failed \(400\): invalid tags/);
});

test("removeSession: 204 resolves, 404 rejects; fetchSessions returns the list", async () => {
  await removeSession(ID, fake(204, null));
  await assert.rejects(removeSession(ID, fake(404, { error: "not found" })), ApiError);
  assert.deepEqual(await fetchSessions(fake(200, [meta(ID, "t")])), [meta(ID, "t")]);
});

test("askTitle: POST .../title, a JSON Content-Type (the route 415s without one), the metadata back; a non-2xx rejects", async () => {
  const seen: { url?: string; init?: RequestInit } = {};
  const out = await askTitle(ID, fake(200, meta(ID, "t", { title: "Greeting the agent" }), seen));
  assert.equal(seen.url, `/api/sessions/${ID}/title`);
  assert.equal(seen.init?.method, "POST");
  assert.equal((seen.init?.headers as Record<string, string>)["Content-Type"], "application/json");
  assert.equal(seen.init?.body, "{}");
  assert.equal(out.title, "Greeting the agent");
  await assert.rejects(askTitle(ID, fake(404, { error: "no such session" })),
    (e: unknown) => e instanceof ApiError && e.status === 404);
});

test("row menu patches: rename, add and remove a tag", async () => {
  const { renamePatch, withTag, withoutTag } = await import("./client.ts");
  assert.deepEqual(renamePatch("  New name ", "Old"), { title: "New name" });
  assert.equal(renamePatch("   ", "Old"), null);
  assert.equal(renamePatch("Old", "Old"), null);
  assert.deepEqual(withTag(["dns"], " Exfil "), { tags: ["dns", "exfil"] });
  assert.equal(withTag(["dns"], "DNS"), null);
  assert.equal(withTag(["dns"], "  "), null);
  assert.deepEqual(withoutTag(["dns", "exfil"], "dns"), { tags: ["exfil"] });
});

test("tagSuggestions: case-insensitive substring of tags in use, not those already on the session, at most 8", () => {
  const known = ["dns", "exfil", "exfil-try", "canary", "DNS-tunnel"];
  assert.deepEqual(tagSuggestions(known, [], "ex"), ["exfil", "exfil-try"]);
  assert.deepEqual(tagSuggestions(known, ["exfil"], "EX"), ["exfil-try"]);
  assert.deepEqual(tagSuggestions(known, [], "dns"), ["dns", "DNS-tunnel"]);
  assert.deepEqual(tagSuggestions(known, [], "  "), []);
  const many = Array.from({ length: 12 }, (_, i) => `t${i}`);
  assert.equal(tagSuggestions(many, [], "t").length, 8);
});
