---
titulo: "Navigation and state"
tipo: sintese
proveniencia:
  origem: "limiar-app agents/mobile-dev/knowledge/04-navigation-state.md (v0.1.0)"
  notas: "Sintetizado em 2026-10-03 a partir da sessão de desenvolvimento do limiar-app."
---
# Navigation and state

## Expo Router
- File-based: `src/app/(tabs)/index.tsx` → `/`; groups in `( )` don't appear in URLs; `[id].tsx` is dynamic.
- **Tabs:** the JS `Tabs` from `expo-router` gives full styling control (custom icon weights, brand
  fonts). `unstable-native-tabs` looks more native but styles less.
- Default tab bar height (49 pt) **clips 12-pt labels**: set
  `tabBarStyle.height = 64 + useSafeAreaInsets().bottom`, `paddingTop: 8`. Don't give the label a
  fixed `lineHeight`.
- `tabBarIcon` receives `color: ColorValue`; Phosphor wants `string` — pass your token by `focused`.
- **Guards for onboarding:** `<Stack.Protected guard={onboarded}>` around app routes and
  `guard={!onboarded}` around the welcome flow; keep help/legal screens outside both so they're always
  reachable. Hide the splash only after persisted state has loaded.
- Route files should export **only** the screen component: move contexts/hooks to `src/state/`.
- Back buttons: `router.canGoBack() ? router.back() : router.replace('/')` (deep links have no history).

## State and persistence
- Start in memory (React context) for a prototype; say so in the UI ("nothing is kept after closing").
- Persist with `@react-native-async-storage/async-storage`: **versioned keys** (`app:v1:prefs`),
  validate shape on read (type guard), and when invalid **log, remove, start fresh** — never silently
  use or silently drop.
- Load once at startup; write-through on change; handle write failure visibly where the user acted.
- Offer "erase everything on this device" (privacy laws, e.g. LGPD) with an in-screen confirmation —
  RN `Alert` does nothing on web.

## Pure logic stays pure
Recommendation/matching code goes in `src/lib/` with no React and no randomness inside (inject a seed;
deterministic shuffle) so it can be unit-tested. When constraints are relaxed to find a result, return
*which* were relaxed and tell the user.
