# quintoandar-agent

An embodiable operator agent for the **QuintoAndar partner portal**
(`https://listings.quintoandar.com.br/`, branded "Marketplace QuintoAndar") as used by
ONE Consultoria Imobiliária. It holds everything learned from mapping the portal on
2026-09-24, so a session (Claude or any other agent) can pick up portal work cold —
answering questions, driving the portal in the browser, or building automations.

## How to embody it

Say something like **"embody the quintoandar agent"** / **"act as quintoandar-agent"**.
The embodying session must then:

1. Read [`AGENT.md`](AGENT.md) fully — identity, ground rules, boot sequence. Non-negotiable.
2. Read the knowledge file(s) the task touches (index below). Don't pre-read everything.
3. Follow [`playbook/browser.md`](playbook/browser.md) before any browser action.

## Index

| File | What it holds |
|---|---|
| [`AGENT.md`](AGENT.md) | Identity, mission, ground rules, boot sequence, how to record new learnings |
| [`knowledge/portal-map.md`](knowledge/portal-map.md) | Every page, route, field, control, state and flow observed + glossary |
| [`knowledge/api.md`](knowledge/api.md) | Observed read endpoints, params, enums, response shapes |
| [`knowledge/open-questions.md`](knowledge/open-questions.md) | Unanswered questions + actions never tested (unknown effects) |
| [`playbook/browser.md`](playbook/browser.md) | Chrome-MCP operating manual: quirks, failures, workarounds |
| [`playbook/snippets/`](playbook/snippets/) | Reusable in-page JS (API logger, route manifest, list scrapers) |
| [`automation/candidates.md`](automation/candidates.md) | Automation ideas, each tied to what is (and isn't) known |
| [`LEARNINGS.md`](LEARNINGS.md) | Append-only log of new facts learned after 2026-09-24 |

## Human-facing reference

The pt-BR operator manual produced from the same mapping session (shareable with the team):
<https://claude.ai/code/artifact/73d21274-fa5a-4a9d-8beb-42f3fe1cc3f3> —
"Portal de Parceiros QuintoAndar — Mapa Funcional". This folder is the agent-side,
self-contained copy; if the two disagree, re-verify in the live portal.

## Status

Lives at repo root "for now" (owner's call, 2026-09-24). Not a noc product, not wired into
`.claude/agents/`. If it grows into code (automations), it should move under the normal
product/seed structure — see `automation/candidates.md`.
