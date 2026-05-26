# Doc Symbology — Lossless Compression Glossary

> Symbols pack more meaning per token. Used carefully, they preserve richness while cutting token cost on auto-loaded surfaces (CLAUDE.md, MASTER-PROMPTs, KB patterns).
>
> **Contract:** every symbol below has a single fixed meaning. Swap prose → symbol ONLY when the swap is lossless. **Lossless** = a reader who knows this glossary recovers the same semantic the prose conveyed.
>
> **Provenance — caveman skill alignment (retrieved 2026-05-18).** The token-density layer is informed by the open-source **caveman** Claude Code skill (`github.com/JuliusBrussee/caveman`, `skills/caveman/SKILL.md` + `README.md`; coverage: `skillsllm.com/blog/caveman-token-compression-claude-code`, `dev.to/onsen/caveman-claude-...`, `decrypt.co/363440/...`, `pcworld.com/article/3115406/...`). **Validated for symbol/AI-communication**: tiktoken-verified ~61-75% output-token reduction across 4 standard task types (web-search 68%, code-edit 50%, Q&A 72%) with full technical accuracy preserved. caveman is a *voice-compression* scheme (drop articles/filler/hedging/pleasantries; fragments OK; code/errors/symbols exact), **not** a glyph glossary — its only symbolic primitives are the `ultra`-level causal arrow + a prose-word abbreviation set. We **adopt its prose-discipline rules** (§8) and its **abbreviation set** (§1, code-name-exempt), **align our intensity model** to its lite/full/ultra ladder (§3a), and **explicitly reject its `X → Y` causal-arrow mapping** — our `→` is locked to routes/pointer and `⇒` to implies (lossless-swap contract; re-mapping would break every existing caller). Divergence recorded in §1 + §4.

---

## 1. Core symbol inventory

### Logic & set theory
| Symbol | Meaning | Example |
|---|---|---|
| `∧` | AND | "test green ∧ keeper clean ∧ build passes" |
| `∨` | OR | "PF ∨ ERP ∨ therapy" |
| `¬` | NOT / forbidden | "¬ `git add .`" |
| `⇒` | implies / leads to | "N≥3 ⇒ MUST formalize" |
| `↔` | bidirectional / equivalence | "KB ↔ CLAUDE.md ↔ memory" |
| `∈` | in / belongs to | "<product> ∈ {ERP, YT, imobi}" |
| `⊂` | subset of | "Stage 4 ⊂ codifiable rules" |
| `≡` | equivalent to | "N=3 ≡ MUST formalize" |
| `≠` | not equal | "Stage 3 ≠ Stage 4" |
| `≈` | approximately | "≈70% token saving" |
| `⊄` | not a subset of | "product shape ⊄ seed contract" |
| `⊥` | incompatible with / orthogonal to | "absorbed shape ⊥ seed default"; "Harness overlay ⊥ worktree divergence" |
| `≫` | much greater than | "rebuild-all-fleet time ≫ rebuild-modified" |

### Counts & comparisons
| Symbol | Meaning | Example |
|---|---|---|
| `N≥3`, `N=2`, `N=1` | recurrence count | "N≥3 ⇒ formalize" |
| `≥`, `≤` | gte / lte | "≥80% disk usage" |
| `Δ` | delta / change | "Δ tests = +29 / -0" |
| `Σ` | sum / total | "Σ keeper detectors = 32" |
| `±` | plus-or-minus | "±5 LoC tolerance" |

### Status (project / phase / task)
| Symbol | Meaning |
|---|---|
| `✅` | done / shipped |
| `⏳` | in-progress / pending |
| `❌` | failed / blocked |
| `🔒` | blocked on dependency |
| `📋` | filed (not yet started) |
| `🗑` | deleted / archived |
| `⭐` | recommended / preferred |
| `⚠️` | warning / caution |
| `🟢` `🟡` `🔴` | severity (green/yellow/red) |

### Code & pipeline
| Symbol | Meaning | Example |
|---|---|---|
| `→` | leads to / routes to / pointer | "rule → KB § PATTERNS/X.md" |
| `s1`/`s2`/`s3`/`s4` | codification pipeline stages | "s3 → s4 promotion" |
| `§` | section reference | "see §6" |
| `D-N` | days back | "D-2 archive cutoff" |
| `@` | annotation / decorator | "@limiter.limit(...)" |

### Methodology actions (3-way triage)
| Symbol | Meaning |
|---|---|
| `[F]` | Formalize (extend framework/seed) |
| `[R]` | Refactor (align with contract) |
| `[A]` | Accept-with-rationale (catalog) |

Each divergence lands on ONE of `[F]`/`[R]`/`[A]` — silent moving forbidden.

### Prose-word abbreviations (adopted from caveman `ultra`; code-name-exempt)
Short forms safe in dense prose because they are unambiguous in this codebase's domain. **HARD EXEMPTION: never abbreviate a code symbol / function / API / file / config-key name** — these compress *English wrapper words only*, never identifiers.

| Long | Short | | Long | Short |
|---|---|---|---|---|
| database | `DB` | | request | `req` |
| authentication / authorization | `auth` | | response | `res` |
| configuration | `config` | | function | `fn` |
| implementation / implement | `impl` | | repository | `repo` |

Provenance: caveman `ultra`-level abbreviation set. Extend this table (never inline-invent) — same glossary-stability contract as §4.

### Divergence register (kept ≠ caveman)
| Glyph | Our locked meaning | caveman use | Resolution |
|---|---|---|---|
| `→` | routes to / pointer | causal `X → Y` (cause→effect) | **KEEP ours** — `⇒` already carries implies/causality; re-mapping `→` breaks every existing routing caller (lossless-swap contract). When caveman docs say `→`, read it as our `⇒`. |

---

## 2. Where to use

- **MASTER-PROMPT.md** "Rules" / "Patterns" / "Methodology evolution" sections — high-density rule lists benefit most.
- **CLAUDE.md §1 universal rules** — tight bullets already; symbols compress further.
- **KB pattern docs §-headings + cross-references** — symbols make scan-reading faster.
- **PROJECT.md + `proposals/*.md` — the WHOLE file, AI scaffolding** (2026-05-18 scope extension). These are AI-authored-and-consumed, ephemeral, high-churn, often regenerated — the *ideal* symbol-compression profile (high token throughput, no durable-human-readership contract). Apply throughout: §3a/§5/§6 phase headers/§7/§11 change log etc. **The §3 NOT-list still governs *within* the file**: §2 quoted-user-verbatim stays prose, §1 zero-context-reader framing stays prose, Open-Questions / human-decision text stays readable. **From-now-on only** — do NOT retrofit existing projects/proposals; the `check_doc_symbology_drift` enforcement scope stays **docs-only** (`_SYMBOLOGY_DOC_GLOBS` unchanged), so projects/proposals are an *authoring-discipline* extension, never scan-flagged → no retrofit pressure on existing files.
- **Memory entry bodies** — `⇒` / `↔` / `∧` / `∨` cut connective tissue without losing logic.
- **`findings.md`** (2026-05-18) — AI appends slips/lessons in-the-moment, AI re-consumes at retro; 5-category durable knowledge artifact. Same from-now-on/no-retrofit/not-scan-enforced treatment as PROJECT.md.
- **`.claude/dispatcher.md`** (2026-05-18) — the unified two-session architect↔operator queue (`## Pending`/`## Completed`/`## Outbox`). Purest AI-to-AI surface (ephemeral, gitignored, never human-read); committed shape = `templates/dispatcher.md`.
- **`live-patterns-log.md`** (2026-05-18) — master-tree per-batch cross-pollination log; AI-written during parallel batches, AI-consumed.
- **Engineer dispatch briefs + `.claude/agents/*.md`** (2026-05-18) — AI→AI instruction text (briefs are tool-call params: the brief *author* applies symbol-first) + agent-definition docs (referenced into every dispatch — high-leverage). Same NOT-list caveats (first-paragraph framing prose).

**The discriminator (generalizes the list — we extend it over time).** Symbol-first applies to **AI-intended files**: machine-authored-and-consumed, no durable-human-readership contract (docs / AI scaffolding). It does NOT apply to human-read surfaces (commit messages, PR bodies, error messages) or quoted-verbatim content. New AI-intended file classes are added to this §2 list as identified — the scope is deliberately extensible.

## 3. Where NOT to use

- **Error messages** facing the user or returned by tools — keep human-readable.
- **First-paragraph context** in a new doc — the reader hasn't loaded the glossary yet; introduce concept in prose then use symbols.
- **Quoted user instructions** — preserve verbatim.
- **Code comments explaining a specific bug fix** — comments need to survive a fresh reader; symbols add cognitive load.
- **Commit messages** — short prose is already token-efficient; symbols there look like noise.

## 3a. ROI calibration (bimodal yield)

**Lossless symbology yields are bimodal** — calibrated 2026-05-11 from SYM wave:

| Surface type | Typical yield | Recommendation |
|---|---|---|
| Bullet/rule-list (CLAUDE.md §1, MASTER-PROMPTs Rules, dispatch briefs) | 8-15% | **Apply by default** |
| Status + cross-ref headers (PROJECT.md §6+§11) | 5-10% | **Apply by default** |
| Glossary tables + decision matrices | 3-8% | Apply where lossless |
| Narrative pattern docs (KB § PATTERNS bodies, examples) | 0-3% | **Prose-acceptable; symbol swap only on obvious wins** |
| Code-fence-dense docs (containerization / fake-real-adapter) | <1% | Skip — code blocks dominate |

The methodology values clarity over compression. When a swap would force prose-rewrite to hit a target, **the prose stays**.

### 3a.1 Intensity ladder (aligned to caveman lite/full/ultra)

caveman's validated 3-rung ladder maps onto our surfaces. **Our `lossless-swap` contract gates every rung — we never trade accuracy for a reduction target.**

| Rung | caveman def | Our use | Typical surface |
|---|---|---|---|
| **lite** | no filler/hedging; keep articles + full sentences (~30%) | default for narrative KB bodies, guides, first-time-reader docs | `KB § PATTERNS/*` prose, `GUIDES/*` |
| **full** | drop articles; fragments OK; short synonyms (~65%) | default for rule-lists + dispatch briefs + status headers | CLAUDE.md §1, MASTER-PROMPT Rules, briefs |
| **ultra** | abbreviate prose words; strip conjunctions; symbolic logic (~75-80%) | reserved for the densest reference tables / decision matrices already glossary-anchored | doc-symbology §7 reference patterns, decision matrices |

We **do not adopt** caveman's `wenyan-*` (classical-Chinese) rungs — out of scope for an English+symbol codebase; explicit rejection (no silent omission).

## 4. Anti-patterns

- **Stacking** symbols without breathing room: `A ⇒ B ∧ ¬C ∨ D` becomes unparseable. Default to ≤2 symbols per clause.
- **Inventing new symbols** without adding them here. Glossary stability matters — drift kills the lossless contract.
- **Using `→` to mean both "routes to" and "leads to"** when the meanings differ. Pick one. (Convention: `→` = routes/pointer; `⇒` = logical implies.)
- **Symbol-loading a doc that no agent reads frequently** — refactor cost > savings. ROI threshold: doc must appear in ≥3 engineer briefs OR be auto-loaded.

## 5. The lossless-swap test

Before swapping prose → symbol, apply the test:

> *Would a reader who has this glossary open recover the exact same semantic the prose conveyed?*

If yes: swap. If "almost yes": keep prose. The methodology values clarity over compression.

## 6. Versioning

Glossary additions go in this doc. Memory entry `feedback_doc_symbology.md` tracks the rule. CLAUDE.md §2 has the pointer. Doc-code coherence rule applies — when a symbol's meaning changes, update every doc that uses it in the same commit.

## 6a. Prose-discipline layer (adopted from caveman, lossless-gated)

The glyph glossary (§1) compresses *logic/status*; this layer compresses the *English wrapper* around it. Adopted from the caveman skill's validated voice-compression ruleset — applied **only where the lossless-swap test passes**, never to the §3-NOT surfaces.

- **Drop:** articles (a/an/the), filler (just, really, basically, actually, simply), pleasantries (sure, certainly, of course, happy to), hedging — when removal changes no meaning.
- **Fragments OK.** `[thing] [action] [reason]. [next step].` is a valid sentence shape in rule-lists/briefs.
- **Short synonym over long phrase:** "big" not "extensive", "fix" not "implement a solution for" — when the short form is unambiguous in-domain.
- **Abbreviate prose words** per §1 abbreviation table (`ultra` rung) — code/identifier names stay exact.
- **Auto-clarity exceptions (caveman-validated, mirrors our §3 NOT-list):** keep full prose for security warnings, irreversible-action confirmations, multi-step sequences where misread is costly, technical-ambiguity risk. These are the *voice-layer* twin of the §3 symbol-NOT list — same surfaces, same rationale.
- **Code / errors / quoted-user / commits stay exact** — identical carve-out to §3; the prose layer never rewrites them.

ROI: §3a's bimodal-yield table governs the *glyph* layer; the prose layer adds caveman's ~30/65/75% rungs (§3a.1) on top, lossless-gated.

---

## 7. Reference patterns

### Codification pipeline (replaces 12-line prose with 1 line)
```
s1 emerges → s2 memory → s3 KB+CLAUDE.md → s4 keeper check_*
Promote when: deterministic predicate ∧ N≥3 ∧ remediation defined.
```

### Three-way triage at divergence
```
Every divergence ⇒ [F] ∨ [R] ∨ [A].  Silent ¬allowed.
```

### Doc-code coherence
```
Tool Δ ⇒ doc Δ same commit.  "later" ¬allowed.
Discovery: grep -rn "<tool>" KB/ CLAUDE/ products/*/README.md
```

### Recurrence rule
```
N=2 ⇒ triage. N≥3 ⇒ MUST formalize. Silent shipping the 4th ¬allowed.
```

### Status legend per project
```
✅ shipped | ⏳ in-progress | 🔒 blocked | 📋 filed | 🗑 archived
```
