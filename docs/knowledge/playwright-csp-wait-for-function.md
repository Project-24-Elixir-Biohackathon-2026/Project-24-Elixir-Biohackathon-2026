# Playwright `wait_for_function` under a strict CSP

**Symptom.** Python Playwright's `page.wait_for_function("…")` on the report service's pages (canary hits,
`script-src 'self'`, no `'unsafe-eval'`) fails with `EvalError: … 'unsafe-eval' is not an allowed source of script`.
A string predicate is compiled with `new Function` in the page, and the CSP refuses it.

**Fix.** Poll from Python instead of in the page: read a locator until it changes, e.g.

```python
deadline = time.time() + 10
while page.locator("#hits details.hit").count() < before + 1 and time.time() < deadline:
    time.sleep(0.05)
```

`locator.wait_for()` and `expect(locator)` also work: they don't evaluate code that the page's CSP checks.

**Related, for screenshots of these pages.** A hand-written `<id>.status.json` needs the watcher's ISO timestamps
(`canary_watch._iso`); epoch floats make the header read "running" without "watched N s ago". Headless Chromium
denies notifications, so the button reads "Notifications blocked".
