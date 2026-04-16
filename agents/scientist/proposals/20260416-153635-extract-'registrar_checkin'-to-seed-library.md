# Proposal: Extract 'registrar_checkin' to Seed Library

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, daily-life
**Status:** pending

## Problem

The 'registrar_checkin' function appears in two products, causing unnecessary duplication of logic.

## Proposed Solution

1. Centralize 'registrar_checkin' in the 'noctusai_lib' of the seed backend. 2. Update the products to use the function from the seed library. 3. Validate through testing that the functionality is consistent across products.

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
