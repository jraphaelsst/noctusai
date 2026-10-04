# mobile-dev — learnings log

Append-only. Newest first. Each entry: date · kind · learning · evidence · status.
Kinds: `pitfall` (something broke) · `practice` (something that worked) · `decision` (a choice and why).
Status: `new` (not yet in knowledge/) → `absorbed` (folded into a knowledge file) → `promoted`
(published in a new agent version in the agents product).

| Date | Kind | Learning | Evidence | Status |
|---|---|---|---|---|
| 2026-10-04 | practice | The publish eval gate is a refinement loop: 2/10 failed cases (missed 'check other projects' step; asked for a file instead of giving the fix) became 0.2.2 | Studio eval run f8e41db8 (prod) | absorbed |
| 2026-10-03 | pitfall | `router.replace('/X')` used to "go back for another" stacks a fresh copy of X and loses its params/state; use `router.back()` | limiar-app src/app/atividade/[id].tsx:41 (live review); knowledge: skill review-mobile-screen | absorbed |
| 2026-10-03 | pitfall | Default Expo Router tab bar (49 pt) clips 12-pt labels; use 64 pt + bottom inset | limiar-app 6a89db7; knowledge: playbook/navigation-state | absorbed |
| 2026-10-03 | pitfall | Cormorant Garamond defaults to old-style figures ("192" ≈ "1g2"); force `lining-nums` | limiar-app 6a89db7; knowledge: playbook/ui-typography-icons | absorbed |
| 2026-10-03 | practice | Phosphor per-icon deep imports cut the web bundle 7.1 MB → 1.4 MB | limiar-app 6a89db7; knowledge: playbook/ui-typography-icons | absorbed |
| 2026-10-03 | pitfall | Stray `~/node_modules` (npm 5.1.0) broke create-expo-app and `expo install`, and silently fed old majors to other projects | session 2026-10-03; noc frontends reinstalled; knowledge: playbook/expo-project-setup | absorbed |
| 2026-10-03 | pitfall | Expo Go signed in but CLI not → project won't open; browser login must complete on the computer (localhost callback) | session 2026-10-03; knowledge: playbook/device-testing | absorbed |
| 2026-10-03 | pitfall | Headless Chrome min width ~500 px, plain static server breaks router URLs, fonts need ≥15 s budget | session 2026-10-03; knowledge: playbook/device-testing | absorbed |
| 2026-10-03 | practice | `Stack.Protected` guards for onboarding; help screens outside both guards | limiar-app 319c167; knowledge: playbook/navigation-state | absorbed |
| 2026-10-03 | practice | AsyncStorage: versioned keys + shape validation; invalid data is logged, removed, reset | limiar-app 319c167; knowledge: playbook/navigation-state | absorbed |
| 2026-10-03 | practice | Duration ranges must not repeat the unit ("30–90 min") — found only on device | limiar-app d327081 | new |
| 2026-10-03 | decision | Expo chosen for a React/TS web developer needing iOS+Android+web, offline, push, stores | limiar-app docs/design/decisions.md; knowledge: playbook/web-to-mobile | absorbed |
