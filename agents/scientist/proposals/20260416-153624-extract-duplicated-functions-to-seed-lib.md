# Proposal: Extract duplicated functions to seed lib

**Generated:** 2026-04-16 15:36
**Severity:** medium
**Effort:** medium
**Affected products:** erp-imobiliario, therapy-platform, personal-finance, mailing, daily-life
**Status:** pending

## Problem

16 functions appear in multiple products with similar signatures.

## Proposed Solution

Review each function and extract to noctusai_lib if it's truly shared logic.

## Findings

- {"function": "criar_meta", "products": ["erp-imobiliario", "personal-finance", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/goals.py", "line": 88, "body_lines": 27}, {"product": "erp-imobiliario", "file": "backend/app/routers/metas.py", "line": 357, "body_lines": 17}, {"product": "personal-finance", "file": "backend/app/routers/metas.py", "line": 49, "body_lines": 9}], "suggestion": "'criar_meta' appears in 3 products \u2014 candidate for seed lib extraction"}
- {"function": "atualizar_meta", "products": ["erp-imobiliario", "personal-finance", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/goals.py", "line": 137, "body_lines": 25}, {"product": "erp-imobiliario", "file": "backend/app/routers/metas.py", "line": 376, "body_lines": 13}, {"product": "personal-finance", "file": "backend/app/routers/metas.py", "line": 60, "body_lines": 12}], "suggestion": "'atualizar_meta' appears in 3 products \u2014 candidate for seed lib extraction"}
- {"function": "obter_meta", "products": ["personal-finance", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/goals.py", "line": 117, "body_lines": 18}, {"product": "personal-finance", "file": "backend/app/routers/metas.py", "line": 27, "body_lines": 9}], "suggestion": "'obter_meta' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "registrar_checkin", "products": ["erp-imobiliario", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/goals.py", "line": 181, "body_lines": 16}, {"product": "erp-imobiliario", "file": "backend/app/routers/campo.py", "line": 113, "body_lines": 17}], "suggestion": "'registrar_checkin' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "listar_eventos", "products": ["erp-imobiliario", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/schedule.py", "line": 60, "body_lines": 6}, {"product": "erp-imobiliario", "file": "backend/app/routers/agenda.py", "line": 96, "body_lines": 8}], "suggestion": "'listar_eventos' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "criar_evento", "products": ["erp-imobiliario", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/schedule.py", "line": 90, "body_lines": 29}, {"product": "erp-imobiliario", "file": "backend/app/routers/agenda.py", "line": 150, "body_lines": 29}], "suggestion": "'criar_evento' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "obter_evento", "products": ["erp-imobiliario", "daily-life"], "locations": [{"product": "daily-life", "file": "backend/app/routers/schedule.py", "line": 121, "body_lines": 12}, {"product": "erp-imobiliario", "file": "backend/app/routers/agenda.py", "line": 215, "body_lines": 11}], "suggestion": "'obter_evento' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "log_action", "products": ["erp-imobiliario", "therapy-platform"], "locations": [{"product": "erp-imobiliario", "file": "backend/app/dependencies.py", "line": 43, "body_lines": 14}, {"product": "therapy-platform", "file": "backend/app/dependencies.py", "line": 92, "body_lines": 6}], "suggestion": "'log_action' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "obter_ativo", "products": ["erp-imobiliario", "personal-finance"], "locations": [{"product": "erp-imobiliario", "file": "backend/app/routers/ativos.py", "line": 203, "body_lines": 9}, {"product": "personal-finance", "file": "backend/app/routers/ativos.py", "line": 36, "body_lines": 9}], "suggestion": "'obter_ativo' appears in 2 products \u2014 candidate for seed lib extraction"}
- {"function": "criar_ativo", "products": ["erp-imobiliario", "personal-finance"], "locations": [{"product": "erp-imobiliario", "file": "backend/app/routers/ativos.py", "line": 214, "body_lines": 49}, {"product": "personal-finance", "file": "backend/app/routers/ativos.py", "line": 47, "body_lines": 9}], "suggestion": "'criar_ativo' appears in 2 products \u2014 candidate for seed lib extraction"}

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
