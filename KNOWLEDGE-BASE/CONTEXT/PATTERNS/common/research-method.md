# Research method — tiered sources, verified claims, a reliability register that learns

> **Rule.** Any "research X / pesquise / what does the internet say / what do specialists say" ask runs one
> method: decidable sub-questions → source classes per question → the matching house advisors in parallel
> (each with its OWN tier policy) → open the actual source → grade it → cross-check every key claim
> (≥2 independent, ≥1 primary when one exists) → mark verified / contested / unverified with the date read →
> answer with confidence and what would change it. The source-reliability register is read first and
> appended after, so every run leaves the next one better informed. Procedure: skill `noc-research`.

## Why (history mined 2026-11-10)

Research has been done here by hand, well, at least five times (`project-history/assistant-chatbot/research/*.md`,
the four browser-ops specialist reports, the tax advisory, the council research). The good shape recurred,
and so did the same failures:

| Recurring friction | Where it happened | What the method does about it |
|---|---|---|
| A quote taken from a **search-result summary** and then cited as if read | `vendor-facts.md` Q8 (faq.whatsapp.com "search-result summary of the page, not a direct fetch"); `product-roles-research.md` labels a dozen claims `[snippet]` | A snippet or a page summarizer is never a quote. Open the page; otherwise the claim is `unverified` and says so |
| "From memory, not re-verified" facts mixed with verified ones | `vendor-facts.md` legend; Google scope classes UNVERIFIED; "Ganguli 2022 cited from prior knowledge, not re-fetched" (`council-and-product-done.md` §5) | Every claim carries a status and a date read. Memory is a lead, never a source |
| A fast-moving vendor doc silently contradicted an old belief | WAHA "Core = one session" was obsolete since 2026.6.1 (`vendor-facts.md` Q6) | Register rows go `stale` after 180 days; vendor docs are re-read before relying |
| Primary text unreachable (paywall, 404, login) and replaced by a summary without saying so | ISO 25010/42010 paywalled; ADP 6-0 404; ITIL 4 paywalled; SAFe login (`decision-rights-research.md`, `product-roles-research.md`) | `unreachable` is a recorded outcome; the fallback source is named and its tier is lower |
| Weak sources (SEO/vendor pages) filling a gap where no reliable source exists | "No reliable source defines 'product architect'" (`product-roles-research.md`) | Saying "no reliable source found" is a valid, recorded answer; T4 is signal only |
| Specialists researching in parallel without each other's frame, then disagreeing | browser-ops: architect vs security vs agents-security vs legal on container count, login channel, proxies | Route each sub-question to its advisor; the synthesis states each disagreement and which side the evidence favours |

Good shape worth keeping (it recurred because it worked): a source legend at the top (`[read]` / `[snippet]` /
`[paywall]`; `VERIFIED` / `UNVERIFIED`), a "Not verified / weak" section at the end, primary over mirror
(the SEC filing over aboutamazon.com), independent position reports written BEFORE any council, and the
decider's prior written down first (`browser-ops/decider-prior.md`).

## 1 · Sub-questions

Restate the ask as sub-questions that each have a checkable answer ("does Google require verification for
a <100-user personal app?", not "what about Google verification?"). Name the decision the answer feeds.
State the as-of date and jurisdiction or version when they matter (law, tax, vendor API).

## 2 · Source classes and tiers

One general ladder. Domain advisors keep their own labels; the register stores the T-level plus the label.

| Tier | Class | Examples | Use |
|---|---|---|---|
| **T1** | Primary / official | statute text, DOU, the regulator, standards bodies (ISO, W3C, OASIS, NIST, OWASP), vendor docs and terms for the vendor's own product, the framework owner for its own framework, peer-reviewed papers (preprints flagged), primary data/filings | Can carry a claim alone when quoted from the page |
| **T2** | Official secondary / institutional | government guidance on another body's rule, university pages, research programmes (DORA), standard preview pages, official articles | Carries a claim with one cross-check |
| **T3** | Recognized specialist / practitioner / professional publication | SVPG, NN/g, HBR, the Pragmatic Engineer, reputable summaries of paywalled standards (arc42 on ISO 25010) | Needs ≥2 independent sources; name the author |
| **T4** | Community and commercial signal | GitHub issues, Reddit, HN, Stack Overflow, forums, vendor marketing, SEO comparisons, slides of unknown author | **Never** the basis of a claim. Finds leads, failure reports, "what practitioners complain about" |
| — | News | dated reporting | Facts of an event only; tier by outlet; go to the primary it cites |

A search snippet and an AI page summary are **not a tier**: they are a pointer to a page you have not read.
**WebFetch is a summariser too** (it answers a prompt over the page with a small model): its output is
*paraphrase via summariser*. For a verbatim quote, fetch the raw text (`curl`, strip tags) or label it
paraphrase. Never work around a bot check or a permission denial to get the raw text — record it.

**Docs that moved / JS-rendered pages:** try the vendor's `/llms.txt`, a `.md` variant of the page URL, and
the sitemap before declaring `unreachable`. A cross-host 301 (`whatsapp.com/legal/business-solution-terms` →
`facebook.com/legal/…`) is logged under the **final** host.

**GitHub issues (T4 signal):** weight by the commenter's `authorAssociation` (`OWNER`/`MEMBER`/`MAINTAINER`/
`COLLABORATOR` > `CONTRIBUTOR` > `NONE`), sort by comment count to find the canonical thread, and quote the
maintainer's own reply when there is one. A maintainer's statement about their own tool is T1 for that tool;
everyone else's report is a lead.

**Domain tier policies are reused, never forked:**
- legal: `[norma]` · `[órgão oficial]` · `[doutrina/publicação profissional]` · open — `KB § PATTERNS/legal/legal-advisor-canon.md` §1 · §3 (Planalto current wording; DOU; gov.br/anpd).
- tax/accounting: `[norma]` > `[órgão oficial]` > `[publicação técnica/científica]` > `[opinião de especialista, ≥2]` > `[blog/prática, pointer only]`; norm hierarchy CF/EC > LC > Lei > Res. CGSN > IN > Solução de Consulta — `KB § PATTERNS/finance/br-tax-advisor-canon.md` §1.
- security / AI-agent security: standards and vendor advisories first (OWASP, NIST, CVE/EPSS, vendor docs) — `KB § PATTERNS/security/appsec-craft-canon.md` · `KB § PATTERNS/security/ai-agent-security-canon.md`.
- every advisor: the research-first line ("read, cite, mark unverified") — `KB § PATTERNS/common/gate-methodology-sync.md` (Sources & how they map, D13).

Mapping: `[norma]`/`[órgão oficial]` = T1; `[doutrina]`/`[publicação técnica]` = T2–T3; `[opinião de especialista]` = T3; `[blog/prática]` = T4.

## 3 · Who researches what

| Question touches | Route to (parallel when several apply) |
|---|---|
| contracts, LGPD, consumer law, terms of use | `legal-advisor` |
| tax, accounting, Simples, NF-e, finance | `accountant` (tax numbers → skill `noc-tax-params`) |
| app security, CVEs, auth, threat model | `security` |
| LLM agents, prompt injection, MCP/tool abuse | `agents-security` |
| system design, trade-offs, build-vs-buy | `architect` |
| product, market, roles, metrics | `product-manager` · `product-analyst` · `product-architect` |
| UX, accessibility | `product-designer` |
| vendor / platform / API policy (Meta, WhatsApp, Google, WAHA…) | **no advisor owns it** — research inline with the vendor-docs tier; `integrations-engineer` (an executor) reviews if it builds on the answer |
| "what do we already ship" | the house code first (`noctus.graph.*`, `code_search`, the module itself), then the docs |
| an external app's behaviour | skill `noc-reverse-engineer` (not web research) |
| Instagram content | skill `noc-ig-analysis` |

Each brief carries: the sub-questions, the register rows for the domains it will likely hit, the output
shape (claim · status · source URL · tier · date read), and "write your position BEFORE seeing the others"
when the answer feeds a decision (independence; see `KB § PATTERNS/common/council.md` if a council follows).
Nothing in the domain? Research inline, or with the Anthropic `deep-research` skill (§6).

## 4 · Claim status

| Status | Means |
|---|---|
| **verified** | The passage was read on the page (quoted or paraphrased with the URL) AND cross-checked: ≥2 independent sources, ≥1 of them primary when a primary exists. A T1 quote of the rule-owner's own text (a statute, a vendor's own terms) counts as verified alone |
| **contested** | Reliable sources disagree. Keep both, with sources; never reconcile silently (same reason as `feedback_compare_dont_reconcile`) |
| **unverified** | Snippet-only, memory, a single T3/T4 source, or the primary was unreachable. Say so in the answer |
| **house-read `<agent>` `<date>`** | The primary was unreachable to you, but another house agent read it that day (e.g. legal-advisor's read of a JS-rendered Terms page). Cite the agent's report; never upgrade it to `verified` |
| **house-proposal** | A number or threshold the house proposes where no source gives one (e.g. a per-line hourly cap). State the reason; never disguise it as `unverified` (which implies a source might exist) |

- **Independence.** Two pages of the same vendor are not independent; same-model answers are not either. A
  vendor's fact about its own product is `verified` at T1 alone; a register `confirmed` event still needs a
  non-vendor second source. A mirror is a mirror until checked against the original.
- **Self-contradicting T1 page** (Meta's publishing limit given as 100 and 50 per 24h on one page) →
  `contested`, with that page as the evidence, and name the runtime check that settles it
  (`GET /<IG_ID>/content_publishing_limit`).
- **Composite claims** split in two: "what the vendor advises" (verifiable as advice) and "the platform's
  real rule" (often unknowable) — WAHA's 30–60 s gap is verified *as WAHA's advice* and unverified *as
  WhatsApp's threshold*.
- **Empty recovery is a signal.** When `memory_search` / `kb_search` return nothing, grep memory, KB and
  `project-history/` — and every worktree (`git worktree list`) — before concluding nothing is known.

## 5 · The source-reliability register

**Storage decision.** Reused the ledger store (`KB § PATTERNS/common/ledger-store.md`): live events go to
`source-register.ndjson` on the orphan `ledgers` branch through `_ledger_store.append_rows` (listed in
`MOVED_LEDGERS`), so research from any session — including read-only advisors — appends without a commit
on `dev`. The history-mined seed is a committed, reviewed file next to this doc
(`source-register-seed.ndjson`). One small tool reads both and folds them: `noctus.dev.source_register`
(`cli.py --source-register`). A plain markdown table was rejected: every run would need a branch and a
commit to append, and parallel runs would conflict on the same rows.

**Event row** (append-only): `ts · source · outcome · tier? · label? · claim? · evidence? · question? · note? · by?`
- `source` = the host (`arxiv.org`), except a **sub-authority** — a path on a shared host that is its own
  authority — which keeps `host/path`: `gov.br/anpd`, `gov.br/receitafederal`, `whatsapp.com/legal`,
  `facebook.com/legal` (`SUB_AUTHORITIES` in the tool; `web.facebook.com` folds into `facebook.com`). Add a new
  sub-authority to that list in the same change as its first event; any other path reduces to the host.
- `outcome` ∈ `graded` (tier set or changed; needs `tier`) · `confirmed` / `refuted` / `contested` (a claim
  from this source judged by an independent one; needs `claim` + `evidence`) · `unverified` · `unreachable`.

**Folded row** (one per source, recomputed every read): `tier` (latest grade) · `label` · counts per outcome
· `first_seen` / `last_seen` · last 3 notes · last refuted claims · `stale` (> 180 days) · `standing`:

| standing | rule |
|---|---|
| `demote` | ≥2 refuted and refuted ≥ ⅓ of judged claims → regrade one tier down with a note |
| `watch` | ≥1 refuted, or ≥2 contested |
| `hard-to-reach` | ≥2 unreachable, never confirmed → plan a fallback source up front |
| `proven` | ≥3 confirmed, none refuted |
| `new` | otherwise |

**Calling it** (MCP argument → CLI flag; always `2>/dev/null` to drop the toolkit banner):

| MCP | CLI |
|---|---|
| `action=read\|log` | `--source-register-action` |
| `query`, `tier_filter`, `limit` | `--source-register-query`, `--source-register-tier-filter`, `--source-register-limit` |
| `source`, `outcome`, `tier`, `label`, `claim`, `evidence`, `question`, `note`, `by` | `--source-register-<name>` |
| `events=[{…},…]` (batch, all-or-nothing) | `--source-register-events '<json list>'` |
| `confirm=true` | `--source-register-confirm` |

A log result is short on apply (`count`, one line per event, `store_status`); the full rows come back only on
the dry run.

A standing is a signal, not a verdict: the regrade itself is an explicit `graded` event with a note, so the
history of why a source moved is kept.

## 6 · Composition with `deep-research`

The Anthropic `deep-research` skill coordinates subagents into a narrative multi-source report. Use it
**inside step 4** for a broad, open-ended sub-question with no house advisor ("market landscape for X",
"literature on Y"), then grade its sources and claims with §2–§4 and log them in the register — its output
is input, not a verdict. Do not use it for a domain an advisor owns (law, tax, security), for a narrow fact
check (two fetches settle it), or as the whole procedure: it has no register and no house tier policy.

## 7 · Output contract

1. **Short answer first** (2–4 lines) with the overall confidence.
2. **Claims**: claim · status · confidence · source(s) with tier and date read.
3. **Contested points** with both sides.
4. **What would change the answer.**
5. **Register rows touched** (source · outcome · new standing).
6. **Open questions** and who decides (lawyer/OAB, contador/CRC, the owner).

**Word budget set by the caller:** answer (2–4 lines) · one table · key claims with status · register rows ·
change-triggers. Drop prose first, never the statuses.

A report for others becomes an artifact or doc per house rules; the owner's own question is answered in
chat. Answer in the language of the ask.

## 8 · Trial log and metric

Trial `noc-research-v1` (2026-11-09/10), two runs: WhatsApp anti-ban gates for a WAHA line
(`project-history/assistant-chatbot/research/waha-anti-ban.md`) and the Instagram bot shell vs Meta docs
(`…/instagram-shell.md`). Both logged to the register live. The 16 steps the researchers improvised are folded
into v1.1 (this doc + the skill); the three seen in both runs were the CLI flag names, empty recovery caches, and
the missing vendor-policy route.

**Metric (v1.1):** report two numbers per run, separately — **key claims honestly labelled** (every claim has a
status that matches its evidence; the skill's job) and **key claims cross-checked** (≥2 independent sources; bounded
by the domain). A domain with no primary numbers (WhatsApp publishes rules, not thresholds) lowers the second, and
that is a finding about the domain, not a skill defect.

Fix-on-contact the runs produced: the unsourced "general-purpose-bot ban from 2026-01-15" in
`KB § PATTERNS/security/ai-agent-security-canon.md` §6.7 (clause found in Meta Terms for WhatsApp Business Platform
§4.7, date still unverified) and the stale "Send is roadmap S4" docstring in the seed Instagram-Login adapter.

## Sources

- Repo history read 2026-11-10: `project-history/assistant-chatbot/research/{vendor-facts,decision-rights-research,product-roles-research,council-and-product-done}.md`; the browser-ops specialist reports (worktree `ac-browser-ops`, `project-history/assistant-chatbot/browser-ops/`); `.claude/agents/{legal-advisor,accountant,security}.md`.
- Anthropic Engineering, "How we built our multi-agent research system" (2025), https://www.anthropic.com/engineering/multi-agent-research-system — read in the 2026-11-09 council research: breadth-first then narrow, parallel subagents for parallelisable questions, source-quality heuristics (prefer primary over SEO content). T1 for Anthropic's own practice.
- Kim et al., "Correlated Errors in Large Language Models" (ICML 2025), https://arxiv.org/abs/2506.07962 — read 2026-11-09: same-family models share errors, so two answers from the same model are not two independent sources.
- Not re-fetched for this doc (unverified here, cited as house practice): the evidence-grading ladders in legal and tax canons above are the house's own, sourced in those canons.
