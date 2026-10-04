---
nome: diagnose-setup
descricao: "Diagnoses Expo/React Native setup, install, bundling and device problems: create-expo-app or expo install failing, npm errors, type-check failures from the template, Expo Go not opening the project, login mismatch, LAN/QR issues, fonts not loading, web export oddities."
ordem: 20
---
## When to use
Something in the toolchain fails or behaves unexpectedly. Not for design/UX review (use review-mobile-screen).

## Before you start
Get the exact command, the exact error text, OS, `node -v`, `npm -v`, and how the command was run (interactive or background). Never diagnose from a paraphrase.

## Procedure
1. Reproduce from the error text; match it against the known signatures in Repertoire.
2. Check the machine before the project: stray `~/node_modules`/`~/package.json`, which `npm` the tool actually resolved (npm debug log first lines), Xcode developer dir.
   If a parent-folder `node_modules` is the cause, ALWAYS add: before moving it, check whether other projects silently resolve dependencies from it (for each project, `require.resolve(dep, {paths:[projectDir]})` must not land there) — moving it can break them, and they may already be running the wrong versions.
3. Check the project: lockfile present, `npx expo install --check`, `expo-env.d.ts` present for `tsc`.
4. Propose the smallest fix, and how to verify it fixed the cause (not just the symptom).

## Repertoire
- `Could not parse JSON returned from "npm pack … --dry-run"` / `cb.apply is not a function` → an old npm in a parent `node_modules` (often the home folder). Move it aside; reinstall affected projects with `npm ci`; scan that no project resolves deps from it.
- `tsc` fails on `*.module.css` / `global.css` imports in a fresh template → create `expo-env.d.ts` (`/// <reference types="expo/types" />`).
- Expo Go: "signed in to Expo Go as X but not to Expo CLI" → `npx expo login --browser`, open the URL **on the computer**, click confirm; check `npx expo whoami`; restart the dev server. Or sign Expo Go out.
- Background `expo start` prints no QR → generate one for `exp://<lan-ip>:8081`, or "Enter URL manually"; verify `curl <lan-ip>:8081/status`.
- Web check shows "Unmatched Route" → the static server lacks clean URLs.

## Deliverable
Cause (verified or suspected — say which), the fix, the verification command, and a LEARNING line if new.

## Pitfalls
- Fixing the project when the machine is the cause.
- Reporting "fixed" after the error disappears without confirming the root cause.

## Go deeper
Playbook: expo-project-setup, device-testing.
