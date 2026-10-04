---
titulo: "Running on a real device and verifying"
tipo: guia
proveniencia:
  fonte: "limiar-app agents/mobile-dev/knowledge/05-device-testing.md (v0.1.0)"
  data: "2026-10-03"
---
# Running on a real device and verifying

## Expo Go on a phone (fastest loop; no Xcode needed)
1. Phone and computer on the same Wi-Fi.
2. `npx expo start --lan` (port 8081). Check reachability from the LAN IP:
   `curl http://<lan-ip>:8081/status` → `packager-status:running`.
3. Non-interactive/background runs print **no QR**. Generate one for `exp://<lan-ip>:8081`
   (`qrcode` Python lib) or type the URL in Expo Go → "Enter URL manually".
4. First bundle takes 30–60 s; afterwards saves hot-reload.

### "You're signed in to Expo Go as X, but not signed in to Expo CLI"
Expo Go and the CLI must match. Either sign the computer in or sign Expo Go out.
- `npx expo login --browser` prints an OAuth URL whose redirect is `http://localhost:<port>/auth/callback`
  — it must be opened **on the computer**, and the user must click the confirm/authorize button.
  Logging in on expo.dev alone does nothing for the CLI. Check with `npx expo whoami`.
- Restart the dev server after logging in.

The floating gear in Expo Go is Expo's dev menu (reload, perf), not the app.

## Web as a fast visual check (not a substitute for the phone)
- `npx expo export --platform web --output-dir <tmp>`; serve with **clean URLs**
  (`/sofa` → `sofa.html`, dynamic `/atividade/x` → `atividade/[id].html`). Plain `http.server` makes the
  router show "Unmatched Route".
- Headless Chrome won't lay out narrower than ~500 px: wrap the page in a 390×844 `<iframe>`.
- Give `--virtual-time-budget` ≥ 15000 ms or web fonts may not have loaded (labels render in a
  fallback serif).
- What web can't tell you: native font rendering, safe areas, haptics, permission prompts, performance.

## Verification ladder (report which rungs you actually ran)
`tsc --noEmit` → `expo export --platform web` → screenshots → **device** → unit tests (pure logic) →
store build. "It type-checks" is not "it works".
