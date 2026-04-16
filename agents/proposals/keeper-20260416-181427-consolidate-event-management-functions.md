# Proposal: Consolidate Event Management Functions

**Agent:** keeper
**Generated:** 2026-04-16 18:14
**Severity:** high
**Effort:** medium
**Affected products:** erp-imobiliario, daily-life
**Status:** pending

## Problem

Functions related to event management like 'criar_evento' and 'listar_eventos' are duplicated, leading to code bloat and maintenance challenges.

## Proposed Solution

1. Extract 'criar_evento' and 'listar_eventos' from both products. 2. Place them in 'seed/backend/lib/events.py'. 3. Update the imports in 'erp-imobiliario' and 'daily-life' to use the new library. 4. Validate changes with 'python -m agents.keeper --heal --product <name>'.

## Trade-offs & Risks

_To be assessed during review._

## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Keeper validates clean (100/100)
- [ ] Documentation updated

## Decision

- [ ] **Accept** — implement this proposal
- [ ] **Reject** — with reason: ___
- [ ] **Defer** — revisit on: ___
