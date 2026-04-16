# Proposal: Extract Asset Management Functions to Seed Library

**Agent:** keeper
**Generated:** 2026-04-16 18:14
**Severity:** high
**Effort:** medium
**Affected products:** personal-finance, erp-imobiliario
**Status:** pending

## Problem

Functions like 'obter_ativo', 'criar_ativo', 'atualizar_ativo', and 'excluir_ativo' are duplicated across products, increasing the risk of inconsistencies.

## Proposed Solution

1. Extract these functions from 'personal-finance' and 'erp-imobiliario'. 2. Move them to 'seed/backend/lib/assets.py'. 3. Update imports in both products to use the new library. 4. Run 'python -m agents.keeper --heal --product <name>' to ensure proper integration.

## Trade-offs & Risks

_To be assessed during review._

## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Keeper validates clean (100/100)
- [ ] Documentation updated

## Decision

- [ ] **Accept** — implement this proposal
- [ ] **Reject** — with reason: ___
- [ ] **Defer** — revisit on: ___
