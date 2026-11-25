# click-path-audit — evaluation scenarios

Desk-checked on 2026-11-25 by skill-scout, not model-run: each scenario is answered by the workflow step or pattern named. A model-run eval is owed before an agent with no human in the loop calls it.

| # | Scenario | Expected finding | Result |
|---|---|---|---|
| 1 | "Novo e-mail" button calls `setComposeMode(true)` then `selectThread(null)`; `selectThread` resets `composeMode` | Step 2 map flags `selectThread` as a dangerous reset; step 4 sequential undo; fix = reorder or stop `selectThread` owning `composeMode` | covered |
| 2 | A filter chip sets `loading=false` in the `.then` of request A while request B sets `loading=true`; spinner flickers off early | Async race; final state depends on resolve order; fix = key loading by request id | covered |
| 3 | A "Salvar" handler validates the form and returns; nothing is sent to the API | Missing transition (label promises Save) | covered |
| 4 | A page returns 500 because a select names a wrong column | Out of scope; route to `noc-wiring-audit` | covered (refuses) |
