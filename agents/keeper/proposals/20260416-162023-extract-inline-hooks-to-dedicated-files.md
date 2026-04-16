# Proposal: Extract inline hooks to dedicated files

**Generated:** 2026-04-16 16:20
**Severity:** low
**Effort:** low
**Affected products:** erp-imobiliario, therapy-platform
**Status:** pending

## Problem

6 pages have TanStack Query hooks inlined instead of in dedicated hook files.

## Proposed Solution

Extract useQuery/useMutation calls from page components into hooks/ directory files.

## Findings

- {"product": "erp-imobiliario", "file": "frontend/src/pages/Dimob.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}
- {"product": "erp-imobiliario", "file": "frontend/src/pages/Equipe.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}
- {"product": "erp-imobiliario", "file": "frontend/src/pages/Negociacoes.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}
- {"product": "erp-imobiliario", "file": "frontend/src/pages/WhatsAppInbox.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}
- {"product": "therapy-platform", "file": "frontend/src/pages/admin/Financials.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}
- {"product": "therapy-platform", "file": "frontend/src/pages/patient/Reviews.tsx", "issue": "TanStack Query hooks inlined in page \u2014 should be in dedicated hook file", "severity": "warning"}

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
