# Proposal: Extract 'listar_eventos' to Seed Library

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, daily-life
**Status:** pending

## Problem

The 'listar_eventos' function is duplicated in two products, resulting in redundant code and potential maintenance issues.

## Proposed Solution

1. Extract 'listar_eventos' into the 'noctusai_lib' within the seed backend. 2. Refactor the products to import and use this function from the seed library. 3. Test the products to ensure the function operates correctly after refactoring.

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
