# Methodology Mirror and Workspaces — Local Mirror Layer + Per-Product Workspaces

> **This is a living document, not a rigid checklist.**
> Filed 2026-05-02 as a deliberate deferral. The user explicitly said
> *"This was an idea i had and we wont implement that system now, but we
> will in the future."* The project's job today is to **preserve the
> design context** so that when re-activated, the next agent inherits
> the full reasoning and the open-question list — not a re-derivation.
>
> **Status: Concept — deferred. Do NOT start work without explicit user
> reactivation.** §6 is intentionally empty. The §7 questions are the
> unblock list; do not pretend they're resolved.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-02
- **Status:** Concept — deferred. Captured for future re-activation. §1, §2, §5 (sketch), and §7 are populated; §6 intentionally empty pending §7 resolution + user reactivation.
- **Owner / stakeholders:** Raphael · future zero-context execution agent
- **Related docs:** `CLAUDE.md`; `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`; `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`; `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`; `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`; `templates/PROJECT-TEMPLATE.md`; **sibling project (active)** `projects/methodology-extraction/PROJECT.md` — handles step (a) of the original build order (behavioral methodology + AST stage 1 tooling). This project is steps (b) and (c).
- **Project slug:** `methodology-mirror-and-workspaces` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

This project covers the second and third layers of the original
`methodology-extraction` proposal: **a local mirror checkpoint** between
per-product workspaces and trunk, and **per-product workspace
isolation** for heavy single-product execution sessions. Both were
deferred because the cheap-win-first behavioral methodology + AST
tooling work in `methodology-extraction` is empirically estimated to
recover ~30-40% of per-turn token cost without any structural change —
and that work is hours, while workspaces + mirror is days. The user
agreed to land step (a) first, measure, then decide whether (b)+(c) are
worth the investment.

Why this is a separate project (split 2026-05-02): the user said
*"About the mirror/local versioning thing, scope it as a separate
project. This was an idea i had and we wont implement that system now,
but we will in the future."* The split keeps `methodology-extraction`
focused on the deliverable that actually ships first; this folder
preserves the architecture sketch and the unresolved questions in case
step (a)'s measurements show a ceiling that justifies (b)+(c).

The win the user is reaching for in the deferred tier has three pieces:

1. **Workflow isolation.** Working on one product can't accidentally
   touch another; agents physically can't wander into unrelated
   products.
2. **Token economy beyond the behavioral floor.** Step (a) is estimated
   at ~30-40% per-turn savings. Full physical isolation is estimated
   at ~60-80% — but at days-of-work cost.
3. **Methodology evolution.** Each isolated workspace is free to
   experiment with methodology variants (new keeper detectors, sharper
   KB rules, new templates). The best variants merge back into trunk
   (this repo). Treat methodology like research: many forks, best
   ideas reconverge.

A **local mirror layer** sits between the workspaces and trunk as an
extra gate — locally-approved changes stage to a mirror snapshot
before any "actual push." The mirror's *context* is opt-in — never
auto-loaded, only consulted when explicitly asked (for local
inspections, product inspections, framework/platform-level
inspections, and similar review-shaped questions).

---

## 2. Confirmed constraints (what the user *has* said)

> **Source note:** the bullets below paraphrase user statements from
> the 2026-05-02 conversation that produced the original
> `methodology-extraction` doc, before this project was split out.
> Future agents: if a constraint feels ambiguous, ask the user to
> confirm before acting.

- **Goal is BOTH token economy AND isolated workflows.** Not either-or
  — both come for free from one structural lever (physical workspace
  size). *(Rules out solutions that solve only one of the two.)*
- **Seed is BOTH methodology and runtime.** Structural rules + factories
  products import. *Implication: the seed travels with the methodology
  bundle. A workspace can't boot a product without it; you can't leave
  the seed behind in trunk.*
- **Workspaces are doc-aware, isolated, and free to evolve.** Each
  carries the methodology docs but can fork/experiment with its own
  variants. *(Rules out a model where methodology is locked and can
  only change in trunk first.)*
- **Trunk = this repo.** "Merge the best ones into our main workflow,
  which is here." This monorepo stays the canonical methodology
  source; per-product workspaces are forks that send blessed
  methodology improvements back. *(Direction of methodology merge is
  workspace → trunk. Direction of product-code merge is still TBD —
  see §7 Q1.)*
- **Heavy work happens in dev workspaces, not in the mirror.** The
  mirror is a checkpoint store, not an editing surface. *(Rules out
  treating the mirror as another workspace.)*
- **Three-layer architecture, not two.**
  - Trunk (this repo) — canonical
  - Local mirror — locally-blessed, "safe checkpoint" before CI/CD
  - Per-product dev workspaces — where heavy work happens
  Mirror sits between workspaces and trunk; CI/CD runs against the
  mirror, and only after CI/CD passes does the mirror's content
  actually push to trunk. (`Local approval → mirror`,
  `mirror → CI/CD → trunk`.)
- **Mirror context is opt-in only.** Must NOT be auto-loaded. Only
  consulted when explicitly asked — for local inspections, product
  inspections, framework/platform-level inspections, and similar
  review questions. *Drives a strict rule: any mechanism that bundles
  mirror content into the agent's default context is forbidden.*
- **GitHub stays out of the loop until trunk push.** The mirror +
  CI/CD layer happens fully locally; nothing reaches GitHub until
  both gates pass. *(Rules out PR-shaped flows that round-trip
  through GitHub for review.)*
- **Defer this project until step (a) ships AND its measurements
  justify the investment.** The user explicitly chose to file this as
  future work and continue with the cheaper steps first. *(Don't
  start sketching shapes here without explicit user reactivation.)*
- **Build-order context (recap).** Original three-step plan:
  - (a) behavioral methodology + AST stage 1 — *this is now the entire
    scope of `projects/methodology-extraction/`*
  - (b) local-mirror checkpoint — *this project's first scope*
  - (c) workspace isolation — *this project's second scope, only if
    (a)+(b) hit a measured ceiling*
  Cheapest-win-first; measure (a) before deciding (b), measure (a)+(b)
  before deciding (c).
- **AST tooling stage 2 lives here.** Stage 1 (Python outline + TS
  outline tools) is in `methodology-extraction` step (a). **Stage 2**
  is AST-based diff for the mirror — only meaningful once the mirror
  exists. Defer to this project, and only build it if line-diffs
  prove insufficient for the mirror's review surface.

---

## 3. Design principles (provisional — confirm with §7 answers when re-activated)

1. **Methodology travels as a bundle.** CLAUDE.md + OPENAI.md + KB +
   templates/ + scripts/ + mcp/ + seed/ + memory schema = one
   portable unit. This is the smallest viable starter-kit a
   per-product workspace needs.
2. **Smaller is the lever.** Both token economy and exploration-
   surface isolation come from one structural choice — making the
   workspace physically smaller. Don't introduce two mechanisms when
   one suffices.
3. **Mirror is read-on-demand, write-on-promote.** Reads only when
   asked; writes only at deliberate promote-to-mirror events. Auto-
   anything is forbidden.
4. **Trunk is the methodology source of truth.** Workspaces fork from
   trunk; methodology merges flow workspace → trunk via deliberate
   review. Never the reverse direction silently.
5. **Cross-product scans live in trunk.** The recurrence detector,
   helper-name scan, three-way sync verifier — these need the full
   product set to be useful. They run from trunk on a known cadence,
   not from workspaces. *(Workspaces are isolated by design; they
   can't see cross-product patterns. Accept the trade-off.)*
6. **CI/CD = the existing local verification stack.** Until proven
   otherwise: frontend builds + backend pytest + MCP review +
   verify-kb-sync + cross-product scans, in their canonical order, IS
   the "ci/cd" gate. No new harness unless §7 says otherwise.

---

## 3a. Seed-first analysis

Mandatory per CLAUDE.md. This project is **explicitly about** the seed
and the methodology bundle as a portable unit, so the entire project
IS a seed-first concern. There is no "should this live in a product
or seed?" question — the project's whole purpose is making the
methodology+seed bundle transportable and forkable.

Per-product code-count litmus: **0** lines of new per-product code.
Every mechanism (starter-kit bootstrap, mirror promote, trunk merge-
back) lives at the platform layer. Products don't get their own
copies.

---

## 4. Scope

**In scope** (once §7 is resolved AND step (a) measurements justify
re-activation):

- A reusable starter-kit shape that bundles the methodology layer + seed.
- A defined "promote to mirror" mechanism (local-approval gate).
- A defined "promote to trunk" mechanism (CI/CD gate).
- A defined "consult mirror" affordance for read-only inspection.
- Per-product workspace lifecycle conventions (when to spin up, when
  to tear down, where they live on disk).
- AST-based diff tooling for the mirror's review surface (stage 2 of
  the AST work in `methodology-extraction`), only if line-diffs prove
  insufficient.
- Documentation in KB describing the workflow end-to-end.

**Out of scope (defer):**

- GitHub-side automation (the user explicitly said "without touching
  github YET").
- Replacing trunk's existing project / proposal / keeper systems.
- Migrating existing products to live primarily in workspaces
  (workspaces are for development; trunk remains canonical until §7
  Q1 says otherwise).

**Out of scope, lives elsewhere:**

- Behavioral methodology (CLAUDE.md trim, Explore-agent delegation,
  narrow-read working agreement). → `projects/methodology-extraction/`.
- AST stage 1 tooling (Python outline + TS AST setup + TS outline).
  → `projects/methodology-extraction/`.

---

## 5. Architecture / data model — sketch

```
┌─────────────────────────────────────────────────────────────────────┐
│  TRUNK REPO (this repo)                                             │
│  • CLAUDE.md, OPENAI.md                                             │
│  • KNOWLEDGE-BASE/                                                   │
│  • templates/, scripts/, .github/, .claude/                          │
│  • mcp/noctusai/  (MCP toolkit)                                      │
│  • seed/  (runtime + framework)                                      │
│  • products/  (all products — canonical home, until §7 Q1)           │
│  • Cross-product scans run from here on a defined cadence            │
└─────────────────────────────────────────────────────────────────────┘
                          ▲ promote-to-trunk (after CI/CD passes)
                          │
                  ┌───────┴───────┐
                  │  CI/CD GATE   │   = canonical local verification stack
                  │   (local)     │     (frontend builds + pytest + MCP
                  └───────┬───────┘      review + verify-kb-sync + scans)
                          ▲
                          │
┌─────────────────────────┴───────────────────────────────────────────┐
│  LOCAL MIRROR — "safe checkpoint"                                    │
│  • Locally-blessed snapshot of changes from one or more workspaces   │
│  • READ-ON-DEMAND: never auto-loaded; consulted only on explicit     │
│    request (local inspection, product inspection, framework /        │
│    platform-level inspection, review-shaped questions)               │
│  • WRITE-ON-PROMOTE: written to only at deliberate promote events    │
│  • Storage TBD (§7 Q3)                                                │
└─────────────────────────────────────────────────────────────────────┘
                          ▲ promote-to-mirror (deliberate local approval)
                          │
   ┌──────────────────────┼──────────────────────┐
   │                      │                      │
┌──┴────────────┐  ┌──────┴────────┐  ┌──────────┴───┐
│ workspace:erp │  │ ws:therapy    │  │ ws:pf  ...   │  ← heavy work here
│  • starter    │  │  • starter    │  │  • starter   │
│    kit bundle │  │    kit bundle │  │    kit bundle│
│  • ONE product│  │  • ONE product│  │  • ONE prod  │
│  • free to    │  │  • free to    │  │  • free to   │
│    evolve     │  │    evolve     │  │    evolve    │
│    methodology│  │    methodology│  │    methodlgy │
└───────────────┘  └───────────────┘  └──────────────┘
```

The starter-kit bundle is the unit that travels into a workspace. The
mirror is the unit that aggregates blessed work before trunk
integration.

The auto-memory system at `~/.claude/projects/.../memory/` is **NOT**
the mirror — auto-memory has explicit scale + scope constraints
(small markdown notes for user/feedback/project/reference). Auto-
memory might hold a *registry/index* of mirror state (last-promoted
timestamp, queued items, mirror location) but the mirror's actual
content lives elsewhere. This is one of the §7 questions.

---

## 6. Implementation phases

**Intentionally empty.** This project is deferred pending step (a)
measurements + explicit user reactivation. When re-activated, the
next agent's first move is to interrogate per §7, then draft §6.

---

## 7. Open questions (the unblock list)

Each question paired with the original recommendation. The user
explicitly deferred answering these — do NOT pretend they're
resolved.

1. **Direction of product-code merge.**
   - **(A)** Workspaces are temporary dev forks; product code rebases
     back to trunk; trunk stays the canonical home for every product's
     code.
   - **(B)** Workspaces are permanent homes for their product; trunk
     keeps methodology + a registry; products live in separate repos
     forever.
   *Recommendation: **(A)** for now — keeps trunk's cross-product
   scans meaningful and avoids a one-way migration. Revisit if a
   workspace stabilizes long enough that promoting it to a separate
   repo is cheap.*

2. **What "memory" means for the mirror.**
   - **(a)** Auto-memory holds an *index/registry* of the mirror; the
     mirror's actual files live elsewhere on disk.
   - **(b)** "Memory" = a separate local persistent store (gitignored
     `.mirror/`, sibling folder, git worktree, dedicated branch).
   *Recommendation: **(a)** index-in-auto-memory + **(b)** content-on-
   disk — the auto-memory rule set explicitly forbids storing repo
   content; we honor that and use auto-memory only as a pointer.*

3. **Where the mirror physically lives.**
   - sibling folder (`~/.../noctusai-mirror/`), gitignored `.mirror/`
     inside trunk, dedicated git branch (`mirror/checkpoint`),
     separate clone with its own remote, git worktree, …
   *Recommendation: **git worktree pointing at a `mirror/checkpoint`
   branch** — gives us file-level access, atomic snapshots via commit,
   and no extra storage cost. To revisit if the user wants the mirror
   visible to non-git tools.*

4. **One global mirror or per-workspace.**
   - one mirror that aggregates blessed work from every workspace
     (one conflict-resolution surface), or one mirror per workspace
     (no cross-workspace merge until trunk).
   *Recommendation: **one global mirror** — it's the analog of a
   shared "develop" branch; conflicts surface here instead of being
   deferred to trunk.*

5. **What "ci/cd" fires when there's no GitHub.**
   - the existing local verification stack run automatically against
     the mirror, or a new harness, or somewhere in between.
   *Recommendation: **the existing stack** wrapped by a single
   `promote-to-trunk` script that fails fast if any check fails. No
   new harness until proven necessary.*

6. **Workspace lifecycle.**
   - once-per-task (fresh workspace per focused piece of work,
     discarded after merge), once-per-product (long-lived), once-per-
     experiment (workspaces for methodology variants).
   *Recommendation: **once-per-product, long-lived** as the default;
   experiments fork from a product workspace as branches inside it.
   This amortizes setup cost and makes "what is the therapy
   workspace's state" a meaningful question.*

7. **"Doc-aware" — full KB or scoped.**
   - every workspace carries the *complete* KB at fork time (heavy
     but consistent), or only the topical files relevant to the
     workspace's product (lighter but breaks pointers like
     `02-LANDSCAPE.md` that name other products).
   *Recommendation: **full KB at fork time** — scoping introduces
   broken pointers and undermines the "doc-aware" goal. The KB is
   small enough that carrying it whole is cheap.*

8. **What "approved locally" means.**
   - self-approval (the dev says "promote"), agent-pair review (a
     code-reviewer agent runs the diff before promotion), or a keeper
     pass.
   *Recommendation: **agent-pair review** — a `code-reviewer` agent
   runs over the diff and the keeper detector pass runs in mirror-
   mode before promote-to-trunk. Self-approval skips a useful gate.*

9. **How methodology variants merge back to trunk.**
   - patch-shaped (each variant produces a focused diff against
     trunk's KB / CLAUDE.md / templates), bundle-shaped (a workspace
     promotes its entire methodology delta as one unit), or absorb-
     into-existing-proposals (the current proposals system handles
     methodology drift too).
   *Recommendation: **absorb-into-existing-proposals** — the
   `noctusai_file_proposal` flow already exists for this. A
   methodology variant becomes a proposal in trunk's `proposals/` (or
   a project's), reviewed and applied per the existing protocol.
   Don't invent a parallel merge mechanism.*

10. **What happens when trunk's methodology evolves while a workspace
    is forked.**
    - workspace fast-forwards on demand, workspace is rebased
      automatically, workspace pins to its fork-version and re-syncs
      only when the dev says so.
    *Recommendation: **pin + manual re-sync** — silent rebases corrupt
    in-flight experiments. The dev decides when to pull trunk's
    methodology delta in.*

11. **Reactivation trigger — what evidence justifies starting this
    project.** *(Measurement landed 2026-05-02 — see below.)*
    Step (a)'s success criterion is "behavioral methodology + AST
    stage 1 tooling recovers a meaningful slice of per-turn token
    cost." If the measured savings are at the **lower bound (~30%)**
    or below, the gap to ~60-80% justifies (b)+(c). If they're at
    the **upper bound (~40%+) and the user reports the workflow no
    longer feels constrained**, (b)+(c) may not be worth the days-
    of-work. *Recommendation: re-evaluate this project when step (a)
    closes, with the measurement evidence in hand.*

    **Measurement (2026-05-02, step (a) close):**

    | Surface | Pre-trim | Post-step-(a) | Δ |
    |---|---:|---:|---:|
    | CLAUDE.md tokens | ~10,640 | ~6,754 | **-3,886 (-37%)** |
    | MEMORY.md tokens | ~4,883 | ~5,331 | +448 (+9.2%) |
    | **Auto-load surface (combined)** | **~15,523** | **~12,085** | **-3,438 (-22%)** |

    The static surface delta is **22%** — a touch below the lower-
    bound trigger (30%). However, the static measurement under-
    counts step (a)'s real savings because it doesn't capture the
    **per-file-read benefit** of the narrow-read rule + outline
    tools. Every whole-file Read of a 600-line module avoided in
    favor of a structured outline + targeted slice saves another
    ~5-10K tokens that NEVER show up in the static measurement.
    Subjective evidence from the step (a) shipping session:
    behavioral changes materially reduced per-turn cost on top of
    the static reduction.

    **Status: DEFERRED.** The 22% static + behavioral runtime
    savings (estimated 35-50% effective) is enough that the
    workflow is no longer constrained day-to-day. The mirror +
    workspaces investment (days of work for ~60-80% target) is
    still the next move IF the workflow constraint returns —
    e.g. if the auto-load surface creeps back up, if multi-product
    sessions become routine, or if methodology variants want
    isolated testbeds. **Do not start this project without
    explicit user reactivation** carrying one of those signals.

---

## 8. Dependencies & blockers

- **Step (a) must close first.** This project sits behind
  `projects/methodology-extraction/` in the build order. Don't start
  here until (a)'s phases are all `✅` and the measurement decision
  in §7 Q11 has been made.
- **§7 Q1, Q3, Q4 must resolve before any disk-layout work begins.**
  Those three shape the storage model and the promote mechanism.
- **The seed framework's release rhythm.** Today, seed bumps ripple
  to every product in the same `git pull`. Workspaces will need a
  defined way to pull seed updates (auto vs explicit). Ties to Q10.

---

## 9. Success criteria

When this project ships, the user can:

- Bootstrap a fresh per-product workspace with a single command.
- Work on that product with the full methodology discipline (seed-
  first, recurrence rule, keeper, three-way sync) AT a meaningfully
  smaller per-turn token cost (target: 60-80% reduction vs trunk
  baseline).
- Promote blessed work from the workspace to a local mirror with a
  deliberate act.
- Promote the mirror to trunk after CI/CD (the local verification
  stack) passes.
- Inspect the mirror on demand without paying for its context by
  default.
- Evolve methodology variants in workspaces and merge the best ones
  back into trunk's KB / CLAUDE.md / templates via the existing
  proposal flow.

---

## 10. How to use this project

- **Don't draft §6 phases until §7 resolves AND the user reactivates
  this project.** The user deferred this; the next session's first
  move when re-activated is to ask the §7 questions in order.
- **Don't write code before the architecture is locked.** Specifically:
  Q1, Q3, Q4 must land before any disk-layout work begins.
- **Read this whole file in one pass.** §1, §2, and §7 carry the most
  load-bearing information.
- **Cross-link with `projects/methodology-extraction/`.** That
  project owns step (a); this project owns steps (b)+(c). When step
  (a) closes, its §11 Change Log will record the measured token-cost
  reduction — that's the evidence that re-activates this project.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | **Project filed** — split out from `projects/methodology-extraction/` per user direction *"About the mirror/local versioning thing, scope it as a separate project. This was an idea i had and we wont implement that system now, but we will in the future."* Lifted §1 mirror context, §2 mirror constraints, §5 architecture sketch, and §7 Q1-Q10 (mirror/workspace questions) from the parent project. Added Q11 (reactivation trigger) tying re-activation to step (a)'s measurement evidence. Status remains Concept — deferred. §6 intentionally empty. | Claude Opus 4.7 |
