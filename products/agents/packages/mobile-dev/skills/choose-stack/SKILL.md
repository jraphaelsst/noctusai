---
nome: choose-stack
descricao: "Recommends a mobile stack (Expo/React Native, Flutter, native Swift+Kotlin, or PWA) from a project's real requirements. Use when someone asks 'which framework', 'should I go native', 'can a PWA do this', or is starting a new app."
ordem: 10
---
## When to use
Starting an app, or questioning the current stack. Not for debugging an existing setup (use diagnose-setup).

## Before you start
Know: the person's current skills (web/React/TS?), target platforms, whether store presence is required, and the spec's non-negotiables (offline, push, local files, camera/BLE/AR, accessibility). Ask for anything missing — don't assume.

## Procedure
1. List the non-negotiables as rows; mark each stack ✅/⚠️/❌ against them (playbook web-to-mobile has the base table).
2. Weigh the person's language skills and code sharing with any existing web app.
3. Recommend one stack, state the main cost of that choice, and when you'd pick the runner-up instead.

## Repertoire
- Default for a React/TS web developer needing stores: **Expo**.
- Native only for heavy device features (AR, BLE, background audio pipelines).
- PWA only when stores are explicitly out of scope; iOS limits offline storage and push.

## Deliverable
A requirements × stacks table, one recommendation, its cost, and the decision the human must confirm.

## Pitfalls
- Choosing by taste instead of the spec's non-negotiables.
- Forgetting the iOS PWA limits when "offline" or "push" are required.

## Go deeper
Playbook: web-to-mobile.
