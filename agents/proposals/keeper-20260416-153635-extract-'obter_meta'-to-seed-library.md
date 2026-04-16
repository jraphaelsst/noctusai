# Proposal: Extract 'obter_meta' to Seed Library

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** low
**Affected products:** personal-finance, daily-life
**Status:** pending

## Problem

The 'obter_meta' function is duplicated in two products, leading to potential discrepancies and increased maintenance.

## Proposed Solution

1. Extract 'obter_meta' into the 'noctusai_lib' in the seed backend. 2. Modify the products to import and use this function from the seed library. 3. Perform testing to ensure the function behaves as expected in both products.

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
