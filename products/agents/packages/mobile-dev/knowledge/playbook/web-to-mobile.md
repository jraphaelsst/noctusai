---
titulo: "Web → mobile: the mental model"
tipo: sintese
proveniencia:
  origem: "limiar-app agents/mobile-dev/knowledge/01-web-to-mobile.md (v0.1.0)"
  notas: "Sintetizado em 2026-10-03 a partir da sessão de desenvolvimento do limiar-app."
---
# Web → mobile: the mental model

## What carries over from web
- Components, props, state, hooks (React Native **is** React).
- Data fetching, REST/JSON, auth tokens. The backend usually doesn't change: the app is a second client.
- Routing → **screens** (stack / tabs / modals). Expo Router is file-based like Next.js.
- TypeScript, ESLint, npm.

## What is genuinely different
| Topic | Web | Mobile |
|---|---|---|
| Delivery | deploy → instant | binary → store review (hours–days); Expo OTA updates JS-only changes |
| Rendering | DOM + CSS | native views: `<View>`, `<Text>`; flexbox only, no cascade, no `div` |
| Text | any element holds text | text MUST be inside `<Text>` |
| Styles | CSS files, cascade | `StyleSheet` objects per component; no inheritance except within nested `<Text>` |
| Fonts | `@font-face`, weight synthesis | every weight is its own family name; no synthesis |
| Platforms | browsers | iOS + Android (+ web via react-native-web) — conventions differ |
| Device APIs | limited | camera, push, biometrics, files, location — each behind a permission prompt |
| Lifecycle | tab open/closed | app suspended/killed/resumed any time; persist what matters |
| Network | assume online | expect offline; local storage matters more |
| Safe areas | rare | notch, home indicator, status bar on every screen |
| Accounts/cost | domain + hosting | Apple Developer $99/yr (iOS builds need a Mac), Google Play $25 once |

## Choosing a stack (decision framework)
| | Expo / React Native | Flutter | Native (Swift + Kotlin) | PWA |
|---|---|---|---|---|
| Language for a web dev | TS/React — none to learn | Dart | two new ones | none |
| Codebases | 1 (iOS+Android+web) | 1 | 2 | 1 |
| Store presence | yes | yes | yes | no |
| Offline / push / local files on iOS | solid | solid | best | weak (iOS restricts PWAs) |
| Share code with a React web app | high | low | none | total |

**Default for a React web developer: Expo.** Choose native only for heavy device features (AR, BLE,
background audio pipelines); choose PWA only when stores are explicitly out of scope.
Decide from the spec's *non-negotiables* (offline? push? stores?), not from taste.

## A shared backend is "the link"
Web app and mobile app are two front doors to one backend (auth, DB, file storage). Build the backend
once; screens differ, data doesn't. Phase a product so the first prototype can run with local data
and no backend at all.
