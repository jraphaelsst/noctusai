# Upload-route body-override derivation — derive the set, require the value

> Formalized 2026-08-31. `MaxBodySizeMiddleware`'s per-route override map
> (`max_body_path_overrides`) is hand-maintained; a forgotten entry doesn't
> fail a test — it 413s only on a realistically-sized upload, in
> production. Same class as `§ PATTERNS/devops/product-lockfile-and-slug-
> drift.md`, third surface. Self-contained.

## The class

**`MaxBodySizeMiddleware` (`noctusai_lib.api.middleware`) caps every inbound
request body at `settings.max_body_bytes` — 1 MB by default, a deliberate DoS
guard for webhooks.** A route that legitimately receives a browser upload
(document, photo, video, CSV import) needs its OWN, bigger cap, declared as a
per-route entry in `max_body_path_overrides`.

That map is a plain hand-written dict a product author adds to when they
remember to. It had already drifted before this pattern existed: only
`social-wiring` declared ANY entries, and even it was missing three of its
own upload routes (`/api/chat/upload-file`, `/api/leads/import/preview`,
`/api/leads/import/commit`). Four other products with real `UploadFile`
routes — `erp-imobiliario`, `igig`, `adconnect`, `therapy-platform` — had
zero entries at all.

**The failure mode is exactly why nobody noticed.** A forgotten entry doesn't
fail a fixture-sized test (a unit test's upload payload is a few KB). It 413s
only for a realistically-sized file — a phone photo, a multi-thousand-row
CSV, a property-walkthrough video — in production, before the handler that
would have accepted it ever runs. Every test stayed green the whole time.

## The fix — derive the SET, require the VALUE

The byte ceiling itself is a judgment call per route (a 500 MB
property-walkthrough video vs. a 30 MB phone photo needs a human, not a
formula) — so this pattern does **not** auto-assign a number. What it DOES
do is make the *presence* of an entry compliance-by-construction: every route
that needs one is derived from the live route table, and a derived route
with no entry is a boot-time refusal, not a runtime 413 surprise.

| Layer | Mechanism | Where |
|---|---|---|
| Primary, exhaustive | `enforce_upload_route_overrides` walks the FULLY-MOUNTED route table after every router is registered and raises `RuntimeError` at boot if a gap exists | `noctusai_seed.upload_route_overrides`, called from `noctusai_seed.app.create_product_app` |
| Static backstop | `check_upload_route_body_override` (AST, no import/execution) | `mcp/noctusai/tools/noctus/dev/compliance.py`, `--check-upload-route-body-override` |
| Opt-out | `KEEP_DEFAULT_MAX_BODY` sentinel — "someone decided this on purpose" | `noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY` |

### Layer 1 — the boot-time refusal (primary mechanism)

`create_product_app` mounts routers in two steps (standard routers, then
product routers) BEFORE the boot-time check runs — deliberately not inside
`noctusai_lib.api.app_factory.configure_app`, which builds
`MaxBodySizeMiddleware` at step 8, *before any router exists*. Running the
walk there would find nothing to check. `enforce_upload_route_overrides`
therefore runs as step 10a, right after every router (steps 9 + 10) is
mounted, and reads `app.routes` — the real, final route table, not a static
guess about what will be mounted.

For each route:

1. **Does the endpoint declare an `UploadFile` parameter?**
   `_annotation_declares_upload_file` recursively unwraps every shape a
   route in this fleet actually uses:
   - `UploadFile` (bare)
   - `list[UploadFile]` / `typing.List[UploadFile]`
   - `UploadFile | None` (PEP-604) / `typing.Optional[UploadFile]` /
     `typing.Union[UploadFile, None]`
   - `typing.Annotated[UploadFile, fastapi.File(...)]`
   - any nesting of the above (`list[UploadFile] | None`)

   Resolved via `typing.get_type_hints(endpoint, include_extras=True)`, NOT
   raw `__annotations__` / `inspect.signature` — a majority of this fleet's
   router modules use `from __future__ import annotations`, which stores
   every annotation as an unevaluated string; only `get_type_hints` resolves
   those against the endpoint's own `__globals__`.

   🔴 **The PEP-604 origin trap.** `typing.get_origin(UploadFile | None)` is
   `types.UnionType` on Python 3.10–3.13 — a **different object** from
   `typing.Union`, the origin `Optional[X]` / `Union[X, None]` resolves to.
   They only became interchangeable later. Checking `typing.Union` alone
   (the sample in Python's own `get_origin` docs) silently misses every
   PEP-604 annotation on the versions this platform actually runs — this
   module's own first draft made exactly that miss, caught immediately by
   `test_upload_file_or_none_pep604_union` (both the seed-layer and
   keeper-layer test suites carry this test explicitly for that reason).
   Check `origin in (typing.Union, types.UnionType)`.

2. **Convert the route's FastAPI path template into the override map's
   vocabulary.** `noctusai_lib.api.middleware.to_wildcard_pattern` turns
   `/api/clientes/{cliente_id}/documentos` into
   `/api/clientes/*/documentos` — every `{param}` (or `{param:converter}`)
   segment becomes a bare `*`. This is the SAME wildcard vocabulary
   `MaxBodySizeMiddleware` itself matches at request time
   (`_pattern_matches` requires exact segment count, `*` matches exactly one
   segment).

3. **Check coverage.** `path_is_covered_by_overrides` runs the identical
   two-tier lookup `MaxBodySizeMiddleware._limit_for` applies at request
   time: an exact wildcard-pattern match first, else the longest-matching
   plain prefix. `KEEP_DEFAULT_MAX_BODY` counts as covered exactly like a
   real byte ceiling — only the KEY's presence matters here, not the value
   (see Layer 3 below).

A gap raises `RuntimeError` naming every uncovered `(pattern_key, route_path,
endpoint_qualname)`, with the fix instructions inline:

```
TestProduct: 1 route(s) declare an UploadFile parameter but have no entry
in max_body_path_overrides. They would silently inherit the webhook-DoS
default cap (settings.max_body_bytes, 1 MB unless overridden) and reject
any realistically-sized upload with a 413, before the handler that would
have accepted it ever runs:
  - /api/foo/upload   (route=/api/foo/upload, endpoint=upload_foo)
Add each pattern key above to max_body_path_overrides with either a real
byte ceiling, or noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY if this
route should genuinely stay at the default cap.
```

**`configure_app` returns the EFFECTIVE `max_body_path_overrides`.** A
product can declare the map two ways — the `max_body_path_overrides=` kwarg
to `create_product_app`, or `settings.max_body_path_overrides` (the fallback
`configure_app` resolves internally when the kwarg is `None`). Resolving that
fallback a second time, independently, in the boot-time check would risk
validating against a DIFFERENT map than the one the middleware is actually
enforcing if the two resolutions ever drifted. `configure_app` now returns
the map it actually wired into `MaxBodySizeMiddleware`; `create_product_app`
captures that return value and feeds it to
`enforce_upload_route_overrides` — one resolution, two consumers.

### Layer 2 — the static backstop (commit-time signal)

`check_upload_route_body_override` (AST via the stdlib `ast` module, never
regex, `§ PATTERNS/common/ast.md`) mirrors the same detection + matching
logic WITHOUT importing or executing a product's code — the MCP tool layer
stays independent of the seed's runtime package, and a product's own deps
are not guaranteed to be installed where this keeper runs.

For each `products/<slug>/backend/app/**/*.py` (excluding `tests/`,
`migrations/`, `__pycache__/`):

1. Find every `<name> = APIRouter(...)` assignment; extract its `prefix=`
   string literal (or a later same-file `<name>.prefix = "<literal>"`
   post-hoc assignment — the legacy `adconnect` pattern, where the
   constructor didn't set one).
2. Find every `@<router_name>.<method>(...)`-decorated function whose
   parameters include an AST-level `UploadFile` reference (same shapes as
   Layer 1's `_annotation_declares_upload_file`, recognized structurally:
   `ast.Name`/`ast.Attribute` for the bare name, `ast.Subscript` for
   `list[...]`/`Optional[...]`/`Union[...]`/`Annotated[...]`, `ast.BinOp`
   with `ast.BitOr` for `X | None`).
3. Extract that product's declared override keys from `app/main.py` — the
   dict literal passed (directly, or via a `Name` resolved against a
   module-level `<name> = {...}` assignment) as
   `create_product_app(..., max_body_path_overrides=...)`.
4. Report a route whose derived pattern key is not covered.

🔴 **Static-resolution scope — read before trusting a clean run as
exhaustive.** This keeper resolves a route's mounted path from ONLY the
router's own `prefix=` and the route decorator's own path literal. It does
NOT resolve an EXTRA prefix a product might apply at
`app.include_router(router, prefix=...)` time — no product in this fleet
does that for an upload route today, but a future one could, and this keeper
would then derive a shorter-than-real pattern key (a false-negative, not a
false-positive). **The runtime check (Layer 1) has no such gap** — it reads
`app.routes` after every router is mounted, the real final truth. Treat this
keeper as the fast, approximate commit-time signal, and the boot-time
refusal as the source of truth.

Wired into `check_all_products()` (compliance.py), the CLI
(`--check-upload-route-body-override`), and pre-commit — **blocking**, fires
on any staged `products/*/backend/app/**/*.py` (a new/changed route, or an
edit to the overrides map itself). Severity `high`. No auto-fix tool — same
reasoning as Layer 1: the ceiling is a per-route judgment call.

### Layer 3 — the opt-out

A route that genuinely should stay at the default cap (a small,
deliberately-bounded upload) still needs a map entry — a missing entry is
indistinguishable from "nobody has looked at this yet." Map it to
`noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY` instead of a byte count:

```python
from noctusai_lib.api.middleware import KEEP_DEFAULT_MAX_BODY

max_body_path_overrides={
    "/api/videos/upload": 500 * 1024 * 1024,
    "/api/avatar/upload": KEEP_DEFAULT_MAX_BODY,  # deliberately small
}
```

`MaxBodySizeMiddleware.__init__` resolves the sentinel to `self.max_bytes`
(the app-wide default) at construction time — behaviourally identical to
having no entry at all. What differs is that BOTH the runtime refusal
(Layer 1) and the static keeper (Layer 2) only check for the KEY's presence,
never the value, so a sentinel-mapped route reads as "covered" the same way
a real byte ceiling does. Refuse-not-null, always — never a silent fallback
via omission.

## Two-key vocabulary — pattern vs. prefix

`max_body_path_overrides` keys come in two shapes, and `to_wildcard_pattern`
/ `path_is_covered_by_overrides` (and their AST mirrors in the keeper) both
honor the SAME two-tier lookup `MaxBodySizeMiddleware._limit_for` applies:

- **Plain prefix** (no `*`) — `"/api/videos/upload"`. The LONGEST matching
  prefix wins; `/api/videos/upload/from-code` is covered by the same entry
  via prefix, not an exact key.
- **Single-segment wildcard pattern** — `"/api/clientes/*/documentos"`.
  Needed when a dynamic path parameter (a UUID resource id) sits BEFORE the
  segment you actually care about — a plain prefix can't express that
  without either stopping short (too broad — `"/api/clientes"` would also
  raise the cap on every JSON clientes route) or being unwritable (the id is
  dynamic). An exact segment-COUNT + literal match on every non-`*` segment
  means a pattern never accidentally widens to a same-prefix, different-shape
  sibling route (`/api/clientes/*/documentos` does NOT cover
  `/api/clientes/*/financiamento/documentos` — different segment count).

## The general lesson

Same shape as every hand-maintained-list-drift class in this codebase: a map
whose SET should be derivable from the code it governs is safe to
hand-maintain right up until someone forgets an entry, and nothing catches
that until the exact realistic input the map exists to handle. Derive the
set mechanically; keep the judgment call (the actual VALUE) as the one thing
a human still has to decide — and refuse loudly, at the earliest possible
point (boot, not request), when that judgment call hasn't been made yet.

→ `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md` (the sibling
family this pattern joins) · `KB § PATTERNS/common/gate-methodology-sync.md`
(the mechanism-ships-with-the-gate discipline this pattern follows) ·
`noctusai_lib.api.middleware.MaxBodySizeMiddleware` (the enforcement point
this pattern keeps honest).

## Dispatch-brief implication — a brief that forbids `app/main.py` is unsatisfiable for an upload slice

**Evidence: N=2, same day, independently.** On 2026-09-02 two dispatched engineers
(`emissoes-certidoes-be`, `emissoes-matriculas-be`) both stopped and filed a
`surface-to-tech-lead` rather than commit. Both briefs said 🔴 DO NOT EDIT `main.py`;
both slices added an `UploadFile` route. The keeper resolves the override map from
`app/main.py` **and nowhere else**, and it checks for KEY PRESENCE — so it cannot be
satisfied from inside the module, by an exported constant, or by a rationale comment.
There is no allowlist and no per-file opt-out.

The two constraints are therefore jointly unsatisfiable, and every escape is a
catalogued bypass shape: splitting the commit to keep the staged set empty is
staging-shaped gate evasion; dropping `UploadFile` for a raw `Request.body()` read
defeats the guard AND removes the runtime mechanism, so the 1 MB default would
silently 413 in production — the exact defect the gate exists to prevent.

**Both engineers were right to stop.** The gate firing was the methodology working.

**When authoring the brief:** if a slice adds an upload route, the brief MUST
pre-authorize the `_MAX_BODY_PATH_OVERRIDES` entry — name the path, the ceiling, and
the one-line rationale — or hand `app/main.py` to that engineer outright. A file-disjoint
decomposition that routes an upload route away from `main.py` has not removed the
coupling, only hidden it until commit time.

> Provenance: `.claude/dispatches/emissoes-{certidoes,matriculas}-be/surface-*.md`,
> both resolved by `5605c5a6` (Emissões mounted end to end). Absorbed here 2026-09-04
> under drift-fix-on-contact; the surface artifacts were cleared after absorption.
