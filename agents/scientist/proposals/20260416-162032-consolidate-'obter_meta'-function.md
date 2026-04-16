# Proposal: Consolidate 'obter_meta' Function

**Generated:** 2026-04-16 16:20
**Severity:** low
**Effort:** low
**Affected products:** daily-life, personal-finance
**Status:** pending

## Problem

The 'obter_meta' function is duplicated in two products, leading to unnecessary code duplication.

## Proposed Solution

Extract 'obter_meta' into the `seed/backend/lib/goals.py` file. Update the affected products to use the function from the seed library. Ensure all tests are consistent with this update.

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
