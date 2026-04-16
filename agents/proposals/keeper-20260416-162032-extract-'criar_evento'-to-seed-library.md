# Proposal: Extract 'criar_evento' to Seed Library

**Generated:** 2026-04-16 16:20
**Severity:** medium
**Effort:** low
**Affected products:** daily-life, erp-imobiliario
**Status:** pending

## Problem

The 'criar_evento' function is duplicated across two products, increasing maintenance overhead.

## Proposed Solution

Move 'criar_evento' to the `seed/backend/lib/events.py` file. Refactor the products to use this centralized function from the seed library. Update all relevant tests.

## Trade-offs & Risks

_To be assessed during review._

## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Guardian score remains 100/100
- [ ] Documentation updated

## Decision

- [ ] **Accept** — implement this proposal
- [ ] **Reject** — with reason: ___
- [ ] **Defer** — revisit on: ___
