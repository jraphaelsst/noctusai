# Doc Symbology — Lossless Compression Glossary

> Symbols pack more meaning per token. Used carefully, they preserve richness while cutting token cost on auto-loaded surfaces (CLAUDE.md, MASTER-PROMPTs, KB patterns).
>
> **Contract:** every symbol below has a single fixed meaning. Swap prose → symbol ONLY when the swap is lossless. **Lossless** = a reader who knows this glossary recovers the same semantic the prose conveyed.

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

---

## 2. Where to use

- **MASTER-PROMPT.md** "Rules" / "Patterns" / "Methodology evolution" sections — high-density rule lists benefit most.
- **CLAUDE.md §1 universal rules** — tight bullets already; symbols compress further.
- **KB pattern docs §-headings + cross-references** — symbols make scan-reading faster.
- **PROJECT.md §6 phase headers + §11 change log** — `✅` / `⏳` / `❌` over prose.
- **Memory entry bodies** — `⇒` / `↔` / `∧` / `∨` cut connective tissue without losing logic.

## 3. Where NOT to use

- **Error messages** facing the user or returned by tools — keep human-readable.
- **First-paragraph context** in a new doc — the reader hasn't loaded the glossary yet; introduce concept in prose then use symbols.
- **Quoted user instructions** — preserve verbatim.
- **Code comments explaining a specific bug fix** — comments need to survive a fresh reader; symbols add cognitive load.
- **Commit messages** — short prose is already token-efficient; symbols there look like noise.

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
