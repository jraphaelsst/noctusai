# Proposal: Consolidate Event Management Functions

**Generated:** 2026-04-16 17:53
**Severity:** medium
**Effort:** medium
**Affected products:** daily-life, erp-imobiliario
**Status:** pending

## Problem

Functions related to event management ('listar_eventos', 'criar_evento', 'obter_evento') are duplicated across products, increasing the risk of bugs and inconsistencies.

## Proposed Solution

1. Extract these functions to 'seed/backend/lib/events.py'. 2. Refactor the affected products to use the new centralized functions. 3. Ensure all event-related functionalities are tested post-refactor.

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
