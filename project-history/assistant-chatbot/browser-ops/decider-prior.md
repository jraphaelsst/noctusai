# Decider's prior (written before any specialist/council input) — 2026-11-10
1. Feasible: one image (Chromium + CDP; noVNC only for owner login/2FA), driven by Playwright over CDP behind an internal "browser-ops" service API (task queue: named recipes like drive.list, sheet.read/write, ig.profile_check). Recipes are deterministic scripts; an LLM (Claude) drives only unknown flows, never free-browsing with the logged-in session.
2. Isolation: one container (or at least one browser profile/volume) PER ACCOUNT; Google and Instagram never share a container. Same image for all.
3. Google: browser ops are mostly unnecessary — the owner's own OAuth client in the NoctusAI project works for the owner without verification (<100 users); add Sheets/Docs scopes to the existing trio and use the API now. Browser container only for UI-only Google operations.
4. Instagram: browser container is the only quick path without App Review; read-only checks first, low rate, own accounts only; ToS/ban risk accepted by owner explicitly; multi-account = one profile volume each, sequential.
5. Security: session cookies on the VPS = account takeover if breached → encrypted volume, no public port, noVNC only over the tunnel with auth; page content treated as untrusted input to any LLM.
6. Capacity: Chromium ~0.5-1 GB RAM per live browser → start/stop per job, not always-on.
