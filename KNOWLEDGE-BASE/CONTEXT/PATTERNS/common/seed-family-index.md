# Seed architecture — family index (§1 consolidation)

> **Family-line pattern:** CLAUDE.md §1 carries ONE line for this family. The member rules live here **verbatim**: a lossless MOVE, not a summary. Each member keeps its own depth doc; this index is the router hop between the §1 family line and those docs.
>
> Consolidated 2026-11-08. Declaring Event-Oriented Architecture needed a §1 line, and §1 stood at the 55-rule cap. → `KB § PATTERNS/common/methodology-gc.md`

All five rules answer one question: **does this change go through the seed, completely and canonically?**
- The first sets the approach.
- The second checks that the seed really ships what you plan to consume.
- The third says what "ships" means for IO.
- The fourth says what a seed default must be.
- The fifth refuses the half-shipped commit.

A change that follows one and not the others still forks a product.

## Members (verbatim from §1)

- **Seed first. Always.** The seed IS the approach; a customization not through a named seam is a structural fork. → `KB § 03-SEED-ARCHITECTURE.md` · skill `noc-new-product`
- **Verify the seed ships it.** A planned "consume" silently becomes a "seed-build" if only the Protocol/Fake ships. → `KB § 03-SEED-ARCHITECTURE.md`
- **Seed IO modules ship Fake+Real+factory.** Half-shipped seed IO generates consumer-side forks. → `KB § PATTERNS/backend/seed-fake-real-adapter.md`
- **Seed defaults = canonical answer, not consumer-#1 coincidence.** A coincidence default silently misroutes consumers #2..N. → `KB § PATTERNS/architect/seed-canonical-defaults.md`
- **No incomplete commits.** One real side + one placeholder side lies about maturity; "scaffolded" ≠ "complete." → `KB § 03-SEED-ARCHITECTURE.md`

## Why a family line

A session about to build or consume a seed capability needs all five at once: discovery (seed first), existence (it ships), shape (Fake+Real+factory), defaults (canonical), and completeness (no half-commit). One router hop gives back four lines of always-on budget. The procedure is skill `noc-verify-seed`; the forcing function is the router keeper's rule-COUNT ceiling. → `KB § PATTERNS/common/claude-md-router-discipline.md`
