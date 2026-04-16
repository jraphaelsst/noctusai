# Proposal: Extract 'criar_meta' to Seed Library

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, personal-finance, daily-life
**Status:** pending

## Problem

The 'criar_meta' function is duplicated across three products, leading to code redundancy and increased maintenance effort.

## Proposed Solution

1. Extract the 'criar_meta' function into the 'noctusai_lib' within the seed backend. 2. Update each product to import and use the function from the seed library instead of maintaining separate copies. 3. Test each product to ensure functionality remains consistent.

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
