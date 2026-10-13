# App reverse-engineering — study a third-party SaaS from the owner's own account, read-only, in stages

**The rule.** When the owner wants to understand an external app in order to build our own version, we map it **read-only, from the owner's own logged-in account, in owner-gated stages**, and land the result as a reference folder that a later build contract can cite. Nothing is built, and nothing on the target is changed, until the owner says "go all the way".

**Why.** Born at N=2: CoreStudio (2026-10-05/06 → `products/social-wiring/projects/core-studio/`) and Lais (2026-10-13). Both runs re-derived the same procedure by hand, and both hit the same traps: an output channel too small for bulk data, controls whose side effects were unknown, a second app hiding behind the first, and a tenant-isolation hole. CoreStudio's guessed ids returned **other customers' rows** (`core-studio/specs/mechanisms.md §15`); a procedure that relies on memory to avoid that is not a procedure.

Procedure: skill `noc-reverse-engineer`. Specialist: agent `reverse-engineer`.

## 1 · Stages (each ends with an owner checkpoint)

| Stage | Goal | Output |
|---|---|---|
| **S1 · Map** | Every route, menu, page, tab, field, button, modal, empty state; stack and hosts; every endpoint the frontend can call, with its safety class | `specs/page-map.md`, `ui/ui-notes.md` + screenshots, `analysis/{endpoints,routes,domain-model,mocks,flags-permissions,realtime-and-integrations}.md` |
| **S2 · Data** | Real response shapes from **read-only GETs on the owner's own ids** (allowlist built from S1) | `captures/xhr-<date>/` (redacted) + `specs/xhr-to-fetch.md` status table |
| **S3 · Mechanisms** | How it works behind the pages: entities + relations, state machines, triggers, AI layer (prompts, slots, classifiers), integrations, pricing unit | `specs/mechanisms.md`, `prompts/*-DRAFT.md` |
| **S4 · Synthesis** | Study doc + mapping onto our platform (seed organs, existing products, gaps) + open questions for the owner | `docs/platform-study.md`, `DECISIONS.md` |
| **Build** | Only on the owner's explicit go: contract-first slices | `specs/<module>-contract.md` (skill `noc-contract-first`) |

Interview, never assume (memory `feedback-interview-never-assume-specs`): what the target does is presented as **options**, never as our decision.

## 2 · Safety classes — classify before you click

Every control and endpoint gets one class **before** it is exercised:

| Class | Examples | Allowed |
|---|---|---|
| **READ** | GET list/detail, opening a tab, expanding an accordion, opening a filter drawer, switching list↔kanban view | yes |
| **SIDE-EFFECT-GET** | a GET that re-runs a job, spends credits, marks read, approves (CoreStudio `headlines/reprocess/{id}`, page loads that fire `POST …generate…`) | no — list it under "never call" |
| **WRITE** | Editar/Salvar, toggles, assign, archive, block, send-to-CRM, create | no |
| **SEND** | anything that messages a real person or hands a live conversation between bot and human ("Lais atendendo" switch, composer, broadcast, review request) | never |

Unknown ⇒ treat as WRITE until the code says otherwise (static analysis classifies it). Opening an unread item can flip its read state — prefer already-read items. Leaving a page with a "Leave site?" guard: discard (we never intend to keep an edit).

**Tenant isolation.** Only ids observed in the owner's own UI. Never increment, guess or swap an id, an agency/tenant param or a slug — not even to "check" isolation. If an endpoint *looks* like it trusts a client-side tenant param, record it as **U** and tell the owner; testing it is not ours to do.

## 3 · Techniques (what worked)

1. **Route discovery from the bundle, not the menu.** Grep the shipped JS for `"/<path>"` strings; menus hide gated routes, and buttons often `router.push` instead of `<a href>`.
2. **Per-route chunks via `performance.getEntriesByType('resource')`.** A full navigation resets the buffer — accumulate across visits in `localStorage` under a `__re_*` key, read it back in slices, **remove the key when done**.
3. **Full code coverage from the webpack runtime.** The runtime's `r.u` map lists every async chunk (`id → hash`); fetching those covers modals/wizards never opened.
4. **Static analysis is the safe way to learn writes.** Service classes (`this.post("/web/chats/"+id+"/transfer")`), zod schemas, enum objects and — when shipped — **MSW mock handlers** give request/response shapes without calling a single write. Delegate the bundle sweep to a background agent; it never executes the code (`python3 -I`, scripts outside the download dir).
5. **Embedded legacy apps.** Check every blank-looking page for iframes (`[...document.querySelectorAll('iframe')]`). Lais embeds a Bubble.io app (`legado.<domain>`) per route with `?mode=iframe&agency=<id>&parentOrigin=…`; open that exact URL top-level when the frame doesn't render (third-party cookies). Bubble/no-code backends expose their own data model client-side — a separate S2/S3 lane.
6. **Text over pixels.** `get_page_text`/`read_page` return whole pages; use JS only for small targeted reads. Prefer `find` refs over coordinates — the viewport changes mid-session.
7. **Changelog pages** ("Novidades", "What's new") give dated feature history and the vendor's own explanation of mechanisms — read them early.
8. **FAQ/help accordions** on config pages often state the rule verbatim (Lais' slot-filling: "only asks what the lead hasn't already said; a *qualificatória* question blocks CRM hand-off until answered").

## 4 · Gotchas (cost us time)

- **Browser-tool JS output is capped at ~1 KB**; anything bigger is truncated. Bulk data leaves the browser through `get_page_text`, or a browser download the owner approves.
- **The target's CSP blocks `connect-src` to localhost** — a local receiver does not work. Do not try to get around a site's CSP.
- **zsh does not word-split `$VAR`**: `for f in $LIST` iterates once. Use a file + `while read`, or `bash -c`.
- **Screenshots saved to disk land in a temp dir** — copy them into the study folder in the same step, named `NN-<page>.jpg`.
- **The browser extension can drop mid-batch** — persist notes after every batch, not at the end.
- **Duplicate/odd data in the target is evidence, not noise** (Lais' report repeats the same listing three times; Lais' profile page leaks raw enum keys) — note it.

## 5 · Evidence and sensitivity

- Tag every non-trivial claim **C** (seen; cite file/screenshot/page) · **I** (inferred) · **U** (unknown → open question). Two concepts are the same only by definition **and** real data (memory `feedback-concepts-by-definition-not-name`).
- Study material is **private client material**: lead names, phones, e-mails, chat text and staff lists stay out of committed docs (summarise structure; redact samples). Tokens, CSRF, cookies, `eyJ…` blobs are redacted before anything is committed.
- Folder home: the product that will consume it — `products/<slug>/projects/<target>/` (CoreStudio → social-wiring). Ask the owner when it is not obvious.
