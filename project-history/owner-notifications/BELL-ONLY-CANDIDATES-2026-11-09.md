# Owner alerts that still reach only the bell (2026-11-09 sweep)

Source: noc-0's sweep for every place the owner asked to be warned, done while building the owner-notification
catalog (`KB § PATTERNS/backend/owner-notification-catalog.md`).

**The owner explicitly asked for WhatsApp warnings in two places. Both are covered by feat/owner-notification-catalog:**

| Ask | State after this branch |
|---|---|
| Vista sync delists properties ("pause + warn, never delete") | New WhatsApp kinds: `imoveis_delistados`, `imoveis_sync_falhou`, `imoveis_vista_listar_vazio` |
| Julia: an unhappy lead, her own mistake, other drift ("should notify me via whatsapp") | Already sent by WhatsApp to Julia's report destination. Now declared and switchable as `julia_alerta`, `julia_opt_out`, `julia_handoff` and `julia_conclusao` |

**Not asked for by name; these reach only the in-app bell (`write_in_app`).** The owner decides which of them should
become WhatsApp kinds. Promoting one means declaring the kind and routing it through the gated sender.

| # | Event | Product | Where |
|---|---|---|---|
| 1 | Julia budget at 50/80/100% of the cap | agents / SW | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/ai-agent-security-canon.md:206`, `products/agents/projects/julia-v2/GUARDRAILS.md:105` |
| 2 | Julia auto-blocks a contact | SW | `julia_protecao_service.py` (`julia_bloqueio_automatico`) |
| 3 | Julia report: no destination set, failed, document failed, rate-limited | SW | `julia_relatorio_service.py` (`julia_relatorio_*`, `julia_documento_falhou`) |
| 4 | LGPD data-subject request received | SW | `julia_solicitacoes_titular_service.py` (`julia_solicitacao_titular`) |
| 5 | Credit balance crosses the alert threshold | core | `services/credits/wallets.py` (`creditos_alerta`) |
| 6 | New lead from the website funnel | core | `services/website_lead_fanout.py` (`lead_novo`) |
| 7 | Webhook signature disabled; a team notice on the inbound line | SW | `routers/whatsapp_router.py`, `webhook_hmac.py` |
| 8 | Scheduler job failed (deduplicated, at most one per 6h) | every product | seed `domain/scheduler_runs/ledger.py` (`scheduler_job_failed`) |
| 9 | Photo-editing notices, lead import, the scripts feedback scheduler | SW | `edicao_fotos/services/notifier.py`, `leads/services/lead_notice.py`, `card_hub/roteiros_feedback_scheduler.py` |
| 10 | Notifiers in other products (igig `_avisar_agencia`, erp `notificar_equipe`) | igig / erp | `esteira_router.py`, `notificacao_service.py` |
