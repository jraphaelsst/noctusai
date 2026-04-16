# Proposal: Extract 'log_action' to Seed Library

**Generated:** 2026-04-16 16:20
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, therapy-platform
**Status:** pending

## Problem

The 'log_action' function is duplicated in two products, which could lead to inconsistencies and maintenance challenges.

## Proposed Solution

Transfer the 'log_action' function to the `seed/backend/lib/logging.py` file. Update the products to import this function from the seed library. Adjust any tests to reflect this change.

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
