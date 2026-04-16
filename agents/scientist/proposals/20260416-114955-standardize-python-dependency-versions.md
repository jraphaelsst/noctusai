# Proposal: Standardize Python dependency versions

**Generated:** 2026-04-16 11:49
**Severity:** medium
**Effort:** low
**Affected products:** all
**Status:** pending

## Problem

4 packages have inconsistent versions across products.

## Proposed Solution

Pin all shared dependencies in root requirements.txt. Products inherit.

## Findings

- {"package": "httpx", "type": "version_mismatch", "versions": [{"source": "root", "version": ">=0.27.0"}, {"source": "daily-life", "version": ">=0.27.0"}, {"source": "erp-imobiliario", "version": "==0.27.0"}, {"source": "mailing", "version": ">=0.27.0"}, {"source": "personal-finance", "version": ">=0.27.0"}, {"source": "seed", "version": ">=0.27.0"}, {"source": "therapy-platform", "version": ">=0.27.0"}], "suggestion": "'httpx' has 2 different version specs \u2014 standardize in root requirements.txt", "severity": "warning"}
- {"package": "python-dateutil", "type": "version_mismatch", "versions": [{"source": "root", "version": "==2.9.0"}, {"source": "daily-life", "version": ">=2.8.0"}, {"source": "erp-imobiliario", "version": "==2.9.0"}], "suggestion": "'python-dateutil' has 2 different version specs \u2014 standardize in root requirements.txt", "severity": "warning"}
- {"package": "python-multipart", "type": "version_mismatch", "versions": [{"source": "root", "version": ">=0.0.9"}, {"source": "erp-imobiliario", "version": "==0.0.9"}, {"source": "mailing", "version": ">=0.0.9"}, {"source": "therapy-platform", "version": ">=0.0.9"}], "suggestion": "'python-multipart' has 2 different version specs \u2014 standardize in root requirements.txt", "severity": "warning"}
- {"package": "slowapi", "type": "version_mismatch", "versions": [{"source": "root", "version": ">=0.1.9"}, {"source": "daily-life", "version": ">=0.1.9"}, {"source": "erp-imobiliario", "version": "==0.1.9"}, {"source": "mailing", "version": ">=0.1.9"}, {"source": "personal-finance", "version": ">=0.1.9"}, {"source": "seed", "version": ">=0.1.9"}, {"source": "therapy-platform", "version": ">=0.1.9"}], "suggestion": "'slowapi' has 2 different version specs \u2014 standardize in root requirements.txt", "severity": "warning"}

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
