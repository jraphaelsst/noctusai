# SPA cache & service workers — never pin a client to a stale bundle

> **Rule.** The SPA **shell** (`index.html`) and any **service-worker script**
> (`sw.js` / `registerSW.js` / `workbox-*.js`) are served **`Cache-Control:
> no-cache`** — they have stable filenames and are the only update paths;
> content-hashed `/assets/*` stay immutably cacheable. **Products do NOT ship a
> precaching service worker** — an always-online app gains ~nothing and a SW
> bypasses HTTP caching, so a stale worker pins clients to an OLD bundle. If a
> product genuinely needs offline, it declares it (`// noc-allow:
> service-worker — <rationale>`); to retire one, ship `selfDestroying: true`.

Born 2026-07-08 (erp-imobiliario / "Marina" incident): one user saw the
pre-rename **"Certificados"** label (current: "Certidões") **and** an
already-fixed form-freeze bug, while the owner on the same prod URL saw the
correct, working build. Root cause was NOT code — it was a **stale
`vite-plugin-pwa` service worker** serving an old precached bundle. Sibling of
[[product-internal-wiring]] on the "correct by construction after deploy" axis.

---

## Why this bites

Two independent caching layers sit between a deploy and the user's screen:

1. **HTTP cache (browser + CDN).** The seed's `serve_spa` already sends the
   shell `no-cache` so a returning visitor re-validates `index.html` and picks
   up the new content-hashed asset filenames. Immutable `/assets/app-<hash>.js`
   stay cacheable (new build ⇒ new filename). This is the `feedback_spa_shell_no_cache`
   fix (2026-06-01).
2. **Service-worker Cache Storage.** A PWA service worker (`vite-plugin-pwa` /
   Workbox) **precaches the shell + JS and serves them from Cache Storage,
   bypassing layer 1 entirely.** Now the shell `no-cache` header cannot reach
   the client — the SW answers navigations from its own precache. A returning
   user runs whatever bundle the SW cached, possibly many deploys old.

The SW is *supposed* to self-update (`registerType: autoUpdate` → skipWaiting +
reload). It fails when the browser/CDN serves a **stale `sw.js`**: the SW update
check fetches the old worker script, never sees the new one, and the client is
pinned **forever**. `sw.js` has a *stable filename* (unlike hashed assets), so
without an explicit `no-cache` a CDN (CloudFlare) happily caches it.

Result: stale labels, "fixed" bugs reappearing, and no amount of normal
refreshing helps (a plain reload does not dislodge an active SW).

---

## The rule, three enforced legs

1. **Shell + SW scripts are `no-cache`** — `serve_spa`'s `_SPAStaticFiles`
   (`seed/framework/backend/noctusai_seed/app.py`) applies `no-cache,
   must-revalidate` to `index.html` (all shell paths + the SPA fallback) **and**
   to `_is_service_worker(path)` (`sw.js` / `service-worker.js` /
   `registerSW.js` / `workbox-*.js`). Hashed `/assets/*` are untouched. Guarded
   by `test_service_worker_scripts_are_no_cache`.
2. **No undeclared precaching SW** — the `check_product_service_worker` keeper
   (severity `high`, `mcp/.../compliance.py`) flags a product whose
   `frontend/vite.config.{ts,js}` references `VitePWA(` / `vite-plugin-pwa`
   unless it is `selfDestroying: true` (retirement) or carries a
   `// noc-allow: service-worker — <rationale>` declaration. Registered in the
   per-product aggregate + `review.py`.
3. **Retire with a self-destroying worker** — to remove a shipped SW you cannot
   just delete the plugin (existing clients keep their installed worker). Ship
   `VitePWA({ selfDestroying: true })` for ≥1 full release cycle: it builds a
   `sw.js` that on the client's next visit `unregister()`s the worker, navigates
   (reloads) all window clients, and deletes every cache — every stuck client
   self-heals with **no manual steps**. Only after telemetry shows no active
   worker remains do you drop the `VitePWA` import entirely.

## Emergency unstick (a single stuck user, before the retirement worker lands)

A normal refresh will not clear an active SW. In Chrome/Edge: **DevTools (F12) →
Application → Service Workers → Unregister**, then **Application → Storage →
Clear site data**, then reload. Confirm first in an **Incognito** window (no SW)
— if it renders correctly there, the diagnosis is the cached SW.

## Related

- [[product-internal-wiring]] — correct-by-construction sibling.
- `feedback_spa_shell_no_cache` (memory) — the layer-1 shell fix this extends.
- `KB § PATTERNS/devops/dev-prod-parity.md` — SW behaviour is a false-green in
  dev/vitest (jsdom has no SW); verify in prod shape (a built PWA + real
  browser + the actually-served `sw.js`).
