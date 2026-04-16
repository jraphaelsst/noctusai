# Proposal: Centralize Asset Management Functions

**Generated:** 2026-04-16 17:53
**Severity:** medium
**Effort:** medium
**Affected products:** erp-imobiliario, personal-finance
**Status:** pending

## Problem

Asset management functions ('obter_ativo', 'criar_ativo', 'atualizar_ativo', 'excluir_ativo') are duplicated, leading to unnecessary code repetition and potential inconsistencies.

## Proposed Solution

1. Move these functions to 'seed/backend/lib/assets.py'. 2. Update the affected products to reference the centralized functions. 3. Run tests to confirm that asset management operations work correctly.

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
