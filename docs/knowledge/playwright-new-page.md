# Python Playwright sync API: `page.context.new_page()` fails after `browser.new_page()`

**Symptom:** `playwright._impl._errors.Error: Please use browser.new_context()`, raised from
`BrowserContext.new_page()`.

**Cause:** `browser.new_page()` (what `platform/dev/e2e/sessions.py`'s `main()` uses for the one
browser tab the script drives) implicitly creates a context and marks it as having an "owner
page"; Playwright's Python implementation (`_impl/_browser_context.py`, `new_page`) then refuses a
second page on that same context, even though the equivalent is allowed in other language
bindings.

**Fix:** open the second tab in its own context instead of the first one's:
`page.context.browser.new_context().new_page()`. A second tab/session does not need to share
cookies or storage with the first here, so a separate context is equivalent for this script's
purpose (closing one tab mid-run while the other keeps going).
