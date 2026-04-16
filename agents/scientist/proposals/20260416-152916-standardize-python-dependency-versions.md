# Proposal: Standardize Python dependency versions

**Generated:** 2026-04-16 15:29
**Severity:** medium
**Effort:** low
**Affected products:** all
**Status:** pending

## Problem

1 packages have inconsistent versions across products.

## Proposed Solution

Pin all shared dependencies in root requirements.txt. Products inherit.

## Findings

- {"package": "python-dateutil", "type": "version_mismatch", "versions": [{"source": "root", "version": "==2.9.0"}, {"source": "daily-life", "version": ">=2.8.0"}, {"source": "erp-imobiliario", "version": ">=2.9.0"}], "suggestion": "'python-dateutil' has 3 different version specs \u2014 standardize in root requirements.txt", "severity": "warning"}

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
