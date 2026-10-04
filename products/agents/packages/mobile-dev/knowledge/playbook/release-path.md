---
titulo: "Path to the stores — status: NOT YET EXERCISED"
tipo: guia
proveniencia:
  fonte: "limiar-app agents/mobile-dev/knowledge/07-release-path.md (v0.1.0)"
  data: "2026-10-03"
---
# Path to the stores — status: NOT YET EXERCISED

Everything below is the documented Expo path, not yet done on a real project here. Treat as a plan;
replace with verified steps (and a LEARNINGS entry) the first time each one is actually run.

1. Accounts: Apple Developer Program ($99/yr), Google Play Console ($25 once), Expo account.
2. Identity in `app.json`: `ios.bundleIdentifier`, `android.package` (reverse-DNS, permanent once
   published), app name, icon (1024² PNG, no transparency for iOS), adaptive icon, splash.
3. `npx eas-cli build:configure` → `eas.json` profiles (development, preview, production).
4. Development build when Expo Go isn't enough (custom native modules): `eas build --profile development`.
5. Internal testing: TestFlight (iOS), internal testing track (Android).
6. `eas submit` to the stores; fill store listings, privacy questionnaires (data collected, tracking),
   age rating, screenshots per device size.
7. Review: expect questions on health/wellbeing claims, account deletion, privacy policy URL.
8. Updates: `eas update` for JS-only changes (OTA); native changes need a new build + review.
