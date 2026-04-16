# Proposal: Standardize 'log_action' Function Across Products

**Generated:** 2026-04-16 17:53
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, therapy-platform
**Status:** pending

## Problem

The 'log_action' function is duplicated in two products, which could lead to inconsistent logging behavior and increased maintenance.

## Proposed Solution

1. Extract 'log_action' to 'seed/backend/lib/logging.py'. 2. Modify both products to use the 'log_action' function from the seed library. 3. Verify logging functionality by running tests in each product.

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
