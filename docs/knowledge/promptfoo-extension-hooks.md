# promptfoo 0.125.1 extension hooks (Python)

Read in `node_modules/promptfoo/dist/src/` (`runExtensionHook`, `runEvalStepAfterBeforeEach`, `processEvalRows`)
and confirmed with a two-test eval (local Python provider and assertion, no model), 2026-11-09. The slice 2 plan
was written against 0.124.1; the pinned 0.125.1 behaves the same.

- `extensions: [file://isolation.py:extension_hook]`: a function not named after a hook is called for **every**
  hook as `fn(hook_name, context)`. A function named `beforeEach` etc. is called only for that hook, as
  `fn(context, {"hookName": ...})`.
- Contexts: `beforeAll` `{suite}`; `beforeEach` `{test}`; `afterEach` `{test, result}`; `afterAll` `{suite,
  results, prompts, evalId, config}`. Returning `None` changes nothing; `beforeEach` may return `{"test": ...}`,
  which replaces the test (a var it adds reaches the provider).
- Order per test: `beforeEach` → provider → assertions → `afterEach`. **Assertions cannot see anything
  `afterEach` adds**: a value an assertion needs must come from the provider's response metadata.
- A `beforeEach` exception aborts the whole eval (exit 1, `Extension hook "beforeEach" failed for …`), before the
  provider is called. An `afterEach` exception is only logged ("afterEach extension hook failed, persisting row
  without hook modifications").
- Each hook call runs the Python file in a fresh process (a new pid each time; a module-level counter stays at 1):
  keep state in files, not module globals.
