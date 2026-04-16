# Proposal: Extract 'criar_meta' Function to Seed Library

**Generated:** 2026-04-16 17:53
**Severity:** medium
**Effort:** low
**Affected products:** daily-life, erp-imobiliario, personal-finance
**Status:** pending

## Problem

The 'criar_meta' function is duplicated across three products, leading to maintenance challenges and potential inconsistencies.

## Proposed Solution

1. Move the 'criar_meta' function from each product to the seed library under 'seed/backend/lib/goals.py'. 2. Update each product to import 'criar_meta' from the seed library. 3. Run `python -m agents --heal` on each affected product to ensure integration is successful.

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
