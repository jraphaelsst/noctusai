# Remediation markers — greppable in-code deferral for batch evaluation

> **What this is.** A single greppable token an agent leaves **in the code** at a spot that needs later remediation, so the whole backlog can be **swept and evaluated in batches** at a future moment — instead of each deferral living only in a project doc that gets archived. The marker IS the named destination, so a deferral stays **non-silent** (no-silent-errors) while still being deferred.

---

## The token

```
<comment-leader> NOC-REMEDIATE[<class>]: <what + why deferred> — <YYYY-MM-DD>
```

- **`NOC-REMEDIATE`** — fixed, uppercase, namespaced (distinct from the ~1.7k noisy generic `TODO`s). Greppable in every language: `# NOC-REMEDIATE` (Python) · `// NOC-REMEDIATE` (TS/TSX) · `/* NOC-REMEDIATE */`.
- **`[<class>]`** — a short batch-filter tag. **Open/self-extending** taxonomy (a non-fitting instance ⇒ add a class, never force-fit): `perf` · `dry` · `security` · `lgpd` · `test` · `typing` · `seed` · `a11y` · `cleanup` · **`codify`** …
  - **`codify` is a *special* class** — it's the structured token for a **deferred codification** (a Stage-3 rule judged ripe-but-not-yet-built). Besides the advisory `scan_remediation_markers` sweep, it is read every compliance run by the `check_codification_debt` keeper (the always-on gate form of the `/codify` command's *detection* half — `[[methodology-codification-pipeline]]`). Leaving a codification deferral in free prose ("we should codify X someday") instead of a `[codify]` marker is the gap that keeper closes. Put `[codify]` markers in the rule's **durable** KB doc (never `projects/` — archived), with a real date (a placeholder/missing date ⇒ the keeper flags it `high`).
- **`<what + why deferred>`** — one clause; enough for a batch-sweeper with zero context to act.
- **`<date>`** — absolute (ages the backlog).

Examples:
```python
# NOC-REMEDIATE[dry]: 3rd copy of this date-bucket helper; lift to seed when the 4th lands — 2026-05-25
```
```tsx
// NOC-REMEDIATE[perf]: re-renders on every keystroke; memoize in the next perf batch — 2026-05-25
```

---

## The rules (how it reconciles with the rest of the methodology)

- **It is a sanctioned, NON-silent deferral channel.** The marker satisfies *defer-with-a-named-destination* — the destination is "the next `NOC-REMEDIATE` batch sweep." A deferral with a marker is **not** a silent error.
- **NOT a replacement for fix-on-contact.** In-scope ∧ fixable-now ⇒ **fix it** (fix-on-contact). The marker is only for genuinely **batch-able / out-of-current-scope** remediation — an improvement, not a live bug.
- **NEVER an error-suppressor.** Never on an `except` / swallowed failure (`except: pass  # NOC-REMEDIATE` is forbidden — that is the retired `# silent-ok` shape). Every `except` still logs ∨ raises ∨ returns-error-bearing ([[logging-at-except]]). The marker tags deferred *remediation*, never a swallowed error.
- **Pairs with triage.** A marker is the in-code form of a deferred `[R]`/`[F]` or an `[A]` ([[accept-with-rationale]]); recurrence (`N≥3` of one class) ⇒ stop marking, **promote to a real project / seed lift** (the recurrence rule).

---

## Declaration vs. citation (2026-08-31)

A fresh sweep once found 142 raw `NOC-REMEDIATE` hits, ~120 of them "malformed" —
almost all of that was the scanner conflating a genuine **declaration** (a marker
actually left in code, or a KB doc's "Known debt" section) with prose merely
**citing** one — a roadmap bullet, a KB doc pointing back at the code comment, a
test's `assert "...NOC-REMEDIATE[x]..." in some_string`. A citation is not a
marker at all: it must not be counted, dated, or flagged malformed.

The discriminator is structural, decided per file kind:

- **Python (`.py`)** — AST + `tokenize` first. A hit counts only inside a `#`
  COMMENT token or a module/class/function docstring's own line range (via the
  docstring `Expr` node's `lineno`/`end_lineno`). Any other string literal — an
  `assert` target, an f-string, a `.write_text()` test fixture, a
  `logger.warning(...)` format string — is an ordinary string: a citation, even
  when it's colon-shaped. A docstring can ALSO merely cite a marker declared
  elsewhere ("See the ``NOC-REMEDIATE[x]`` marker at the handling site") — being
  in a docstring is necessary but not sufficient; the shape check below still
  applies.
- **Markdown (`.md`)** — no comment concept, so the shape check is the only
  signal, and it is deliberately the STRICT canonical shape only: `[class]:`
  with the colon immediately after the bracket. This is not a blanket `.md`
  skip — a well-formed `[class]: text` declaration in a KB doc (the `codify` /
  `embedding-cache-framework` "Known debt" shape) or a PROJECT.md still counts.
  The reversed-bullet shape below DOES count in code comments but turned out,
  in every verified `.md` instance, to be a citation of the marker actually
  declared in the referenced source file (a roadmap's "Deliberately deferred"
  section citing the code comment that owns the deferral).
- **Other code (`.ts`/`.tsx`/`.sql`/`.yml`)** — a comment-leader heuristic
  (`//`, `--`, `#`, or a JSDoc `*` continuation) stands in for the AST gate; no
  full lexer is wired up for these.

Within a comment/docstring/leader context, one of three shapes marks a real
declaration:
1. **colon-shape** — `[class]: text` (through an optional closing backtick/
   paren).
2. **bare-standalone** — nothing (beyond this line's own comment leader)
   precedes the token; the "what" continues on the following lines (e.g.
   `NOC-REMEDIATE[orbity-finance-fiscal]` opening its own line, explained
   below it).
3. **reversed bullet** (code files only) — `text — NOC-REMEDIATE[class]`, an
   em-dash immediately before the token, nothing after it; a single, complete,
   atomic bullet item (multiple sibling bullets on adjacent lines must never
   be concatenated into one record).

Placeholders are never counted: an angle-bracket class (`[<class>]`, the
original rule) OR a class that is a bare ellipsis (`...` / `…` — the "some
class" notation `validation_signal.py`'s own docstring uses) OR descriptive
text that is itself an angle-bracket/ellipsis placeholder.

**Multi-line markers.** The `— <date>` frequently lands 2-3 lines below the
`[class]:` open (a wrapped sentence, an indented explanation block) — the
single-line-only read was itself a source of false "malformed" reports on
genuinely dated markers. Once a declaration is found, the surrounding block is
read forward (the rest of the docstring's own range for a docstring hit, the
contiguous run of comment lines for a comment hit, a capped non-blank run for
`.md`) and the date is searched across that whole block — restricted to text
strictly AFTER the marker's own `]`, never before it (a preceding bullet's
leading timestamp must never be misread as the marker's own date).

---

## Batch evaluation (the payoff)

Sweep the whole backlog at a chosen moment, optionally by class:

```bash
grep -rn "NOC-REMEDIATE" products/ seed/ mcp/            # everything
grep -rn "NOC-REMEDIATE\[perf\]" products/ seed/ mcp/    # one class
```

A batch session triages the sweep (`[F]`/`[R]`/`[A]`), fixes what's cheap together (shared context ⇒ cheaper than one-at-a-time), and promotes recurrences to projects. **Stage-4 (built 2026-05-25):** `noctus.dev.scan_remediation_markers` (+ `cli.py --scan-remediation-markers`) — the deterministic batch-sweep surface: parses real `[class]` + `— <date>` age, groups by class, flags malformed (missing date) + **FORBIDDEN on-`except`** markers, surfaces any class at **N≥3** (promote to project/seed lift). Advisory query (exit 1 on defects); requires a real `[class]` so it never trips on the prose that *defines* the token (the placeholder-exclusion lesson). The analogue of a keeper `check_*` for *deferred-remediation* shapes ([[methodology-codification-pipeline]]).

The `codify` class gets a second surface — the **`check_codification_debt` keeper** in the compliance gate (built 2026-05-25). It reuses the *same* parser (`markers_of_class` over the shared `_iter_markers` — one parser, two surfaces) but runs *always-on* inside `check_all_products`, so a deferred codification surfaces every gate run, not only when someone remembers to sweep. `[codify]` markers are `warning` (sanctioned, non-blocking); malformed/on-`except` are `high`; backlog ≥3 adds a "run `/codify` sweep" warning. This is the bridge from the advisory scan into the keeper gate — the `/codify` command's *detection* half mechanized.

---

## Composition / codification
- Connects to [[branching]] §6 (self-improvement loop) — an in-flight bump too small/out-of-scope to fix now is left as a `NOC-REMEDIATE` marker, swept into the batch later; the in-code sibling of the `findings.md` capture surface.
- Reconciles with: [[logging-at-except]] (never an error-suppressor) · [[accept-with-rationale]] (the durable-register sibling) · [[project-execution]] (defer-with-destination · the recurrence rule).
- Codification: s1 emerged 2026-05-25 (user: *"agents leave greppable pattern comments on code for remediation, so we might evaluate them in batches in future moments"*) → s2 memory → s3 this doc + CLAUDE.md §1 pointer; s4 = `scan_remediation_markers` (built 2026-05-25 via the `/codify` command — `projects/codification-backlog-drain/`).
- 2026-08-31: declaration-vs-citation rewrite (dispatch `remediation-marker-hygiene`) — the scanner's single-line, path-only discriminator was reporting ~120 of 142 raw hits as "malformed" when the true number of genuinely defective (undated/on-`except`) markers was 0 once citations were excluded and multi-line blocks were read correctly; 50 real markers that WERE genuinely undated got their dates backfilled via `git blame` on the marker's own line. See "Declaration vs. citation" above.
