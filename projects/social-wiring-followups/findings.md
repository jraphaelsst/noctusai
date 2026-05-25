# findings — social-wiring-followups

## Slips
- _(none — clean dispatch)_

## Errors
- _(none)_

## Mistakes
- **Dispatched 4 engineers without pinning their fork base.** The harness `isolation:"worktree"` based every agent worktree off `origin/main` (`c72f7b3e`), not `origin/dev` (`9c1b67b1`) — so each engineer inherited a base behind dev by `db482e5c` (Meta-fork retirement) + the `get_publish_service` DI seam. E2 (meta slice) was load-bearing-divergent → it STOPPED (good). E1/E4 produced patches against stale files → `--3way` conflicts at integration. **Fix forward:** engineer briefs must carry `git fetch origin && git rebase origin/dev` as step 0 (or `dispatch_preflight base_ref=origin/main` to detect it). → memory `feedback_harness_worktree_bases_off_main`.

## Lessons
- **Context-collision ≠ logic-conflict.** All 3 `--3way` conflicts (E1 `_meta_api.py` + `__init__.py`, E4 `generation.py`) were *context* collisions: dev inserted code (video-publish fns, `get_publish_service`) in the same regions the stale-base patches touched. Resolution was uniformly "keep both sides" — verified by no-duplicate-def grep + py_compile + the suites, not by eyeballing markers.
- **Verify a salvaged-doc's adopter refs against the live tree before applying.** E3's `di-test-seam.md` draft cited `make_get_settings(settings)` consume + `build_credential_store(client, settings_obj=…)`. On dev the peer actually landed a **product-local** `get_settings()` + `encryption_key=` kwarg — citing the draft verbatim would have shipped doc-drift. Rewrote the section to the real shape + flagged the consume-migration as a follow-up.
- **Self-branching the architect works.** Architect ran as peer-of-its-own-task: integration worktree off `origin/dev`, engineers nested under it, FF-push straight to `dev` — never touched the shared primary `HEAD` while a `core` agent ran concurrently (isolated in `fix/core-e2e-auth-fixture-backend-mock`).

## Interesting findings
- `drive_api/_has_oauth_credential` checking `CALENDAR_PROVIDER` is **correct, not a bug** (E2 confirmed): Google issues ONE OAuth credential covering the Calendar/Drive/YouTube scope bundle, so Drive looks up the shared Google provider key. Preserved in the unified `has_oauth_credential(..., provider=CALENDAR_PROVIDER)`.
- E4's real root cause was narrower than the brief: the leak wasn't `get_admin_client()` but `_resolve_image_gen_adapter → get_image_gen_adapter → resolve_credential → _get_public_client` building its own Supabase client; the DI seam fixes it because the injected `FakeImageGenAdapter` short-circuits the credential resolution.
- Pre-existing: `mcp/noctusai/.venv` has `starlette 1.0.0` (violates seed cap `<0.42.0`); the shared test venv `venv/` is correct at `0.41.3`. Surfaced not auto-fixed (MCP runtime is live + shared with the core agent).
