import assert from "node:assert/strict";
import { test } from "node:test";
import { isSessionId } from "./session-id.ts";
import { searchWith, sessionFromSearch } from "./session-url.ts";

const ID = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f";

test("isSessionId accepts only canonical lower-case UUID v4", () => {
  assert.equal(isSessionId(ID), true);
  for (const bad of [ID.toUpperCase(), "../x", "a/b", "", null, 42, ID.replace("-4c3d-", "-1c3d-"), `${ID}x`]) {
    assert.equal(isSessionId(bad), false, String(bad));
  }
});

test("sessionFromSearch: a valid id, else null (malformed, missing, repeated junk)", () => {
  assert.equal(sessionFromSearch(`?session=${ID}`), ID);
  assert.equal(sessionFromSearch(`?x=1&session=${ID}`), ID);
  assert.equal(sessionFromSearch("?session=../../etc/passwd"), null);
  assert.equal(sessionFromSearch(`?session=${ID.toUpperCase()}`), null);
  assert.equal(sessionFromSearch(""), null);
});

test("searchWith sets or drops the parameter and keeps the others", () => {
  assert.equal(searchWith("", ID), `?session=${ID}`);
  assert.equal(searchWith("?session=bad&x=1", null), "?x=1");
  assert.equal(searchWith("?session=bad", null), "");
  assert.equal(searchWith(`?x=1&session=${ID}`, ID), `?x=1&session=${ID}`);
});
