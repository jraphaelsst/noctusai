# Proposal: Extract 'atualizar_meta' to Seed Library

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** low
**Affected products:** erp-imobiliario, personal-finance, daily-life
**Status:** pending

## Problem

The 'atualizar_meta' function is duplicated across three products, which can lead to inconsistencies and bugs if not updated uniformly.

## Proposed Solution

1. Move the 'atualizar_meta' function to the 'noctusai_lib' in the seed backend. 2. Refactor the affected products to utilize the centralized function from the seed library. 3. Conduct tests to verify that updates are reflected correctly across all products.

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
