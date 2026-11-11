# access-tier -- living findings ledger

> GENERATED next to `findings.ndjson` by `noctus.dev.findings_ledger` (`cli.py --findings-ledger-reconcile access-tier`). Never edit by hand. Read your scope's open rows before you touch it. KB § PATTERNS/common/living-findings-ledgers.md.

**1066 open / in-progress**, 271 fixed, 2 accepted (1339 total).

| scope | open | critical | high | medium | in-progress | fixed |
|---|---:|---:|---:|---:|---:|---:|
| academia-de-reciclagem | 19 | 0 | 0 | 19 | 0 | 13 |
| adconnect | 30 | 0 | 0 | 30 | 0 | 0 |
| agents | 1 | 0 | 0 | 1 | 0 | 26 |
| commerce | 48 | 0 | 0 | 48 | 0 | 13 |
| community | 35 | 0 | 0 | 35 | 0 | 0 |
| core | 93 | 0 | 0 | 93 | 0 | 69 |
| daily-life | 16 | 0 | 0 | 16 | 0 | 0 |
| dev-team | 6 | 0 | 0 | 6 | 0 | 0 |
| erp-imobiliario | 186 | 0 | 1 | 185 | 0 | 15 |
| igig | 58 | 0 | 0 | 58 | 0 | 13 |
| monica | 9 | 0 | 0 | 9 | 0 | 13 |
| orbity | 46 | 0 | 0 | 46 | 0 | 16 |
| p-studio | 20 | 0 | 0 | 20 | 0 | 0 |
| personal-finance | 41 | 0 | 0 | 41 | 0 | 0 |
| pilates | 1 | 0 | 0 | 1 | 0 | 0 |
| seed | 5 | 0 | 0 | 5 | 0 | 25 |
| social-wiring | 276 | 0 | 0 | 276 | 0 | 68 |
| store | 14 | 0 | 0 | 14 | 0 | 0 |
| therapy-platform | 162 | 0 | 0 | 162 | 0 | 0 |

## Open / in-progress (bulk rows are summarised below; every row is in the NDJSON)

| id | scope | target | tier | class | sev | status | found |
|---|---|---|---|---|---|---|---|
| AT-847e83bb | erp-imobiliario | `schema erp served by the data API while erp-imobiliario is ativo=false` | none | inactive-schema-served | high | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-2c294215 | academia-de-reciclagem | `POST /api/public/interessados` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-b291cdb1 | academia-de-reciclagem | `products/academia-de-reciclagem/backend/app/routers/content_router.py (1 routes)` | platform | platform-in-public-schema | medium | open | access-tiers-gate 2026-11-05 |
| AT-15fa319f | academia-de-reciclagem | `products/academia-de-reciclagem/backend/app/routers/timeline_router.py (1 routes)` | platform | platform-in-public-schema | medium | open | access-tiers-gate 2026-11-05 |
| AT-4ea1fe05 | adconnect | `DELETE /admin/reward-rules/{rule_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-154f61bd | adconnect | `GET /admin/dashboard` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-fbf2856c | adconnect | `GET /admin/distributors` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-405c18cd | adconnect | `GET /admin/invoices` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-4a329f80 | adconnect | `GET /admin/reward-rules` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-4b8adc46 | adconnect | `GET /admin/sellout/queue` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-d42d8aad | adconnect | `GET /distributors` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-5bd8eef7 | adconnect | `PATCH /admin/distributors/{distributor_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-f0ace3ce | adconnect | `PATCH /admin/reward-rules/{rule_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-36df15cb | adconnect | `PATCH /rewards/redeem/{redemption_id}/process` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-dd4df5ea | adconnect | `PATCH /sellout/{report_id}/review` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0437f792 | adconnect | `POST /admin/distributors` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c2c5d34d | adconnect | `POST /admin/reward-rules` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ae30bffc | adconnect | `POST /financial/webhook/stripe` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1cadd7c5 | agents | `POST /api/public/ask/{app_slug}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-388fc832 | community | `GET /api/aplicacoes/formulario` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a92585e0 | community | `GET /api/eu` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7b042bb9 | community | `GET /api/planos/publicos` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-07ba762f | community | `POST /api/aplicacoes` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3eea7e36 | community | `POST /api/cadastro` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3ad0324b | community | `POST /api/checkout` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7cdd01ed | community | `POST /api/webhooks/asaas` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-32325372 | community | `POST /api/webhooks/stripe` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-d68465cb | core | `POST /api/auth/login` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-05d35db1 | core | `POST /api/auth/oauth/callback` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ae85e764 | core | `POST /api/auth/refresh` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-d0148f2e | core | `POST /api/auth/signup` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-e59e815d | core | `POST /api/website/events` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-83a0df65 | core | `schema public: browser-role SELECT on 50 of 73` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-30780c95 | erp-imobiliario | `GET /api/banco/conciliacao` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-089385e0 | erp-imobiliario | `GET /api/banco/extratos` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3b8209bb | erp-imobiliario | `GET /api/banco/retorno/{remessa_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-9d08fb76 | erp-imobiliario | `GET /api/dimob/preview` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0ed7998f | erp-imobiliario | `GET /api/dimob/validate` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-e873961c | erp-imobiliario | `GET /api/financeiro` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-5cc23ca8 | erp-imobiliario | `GET /api/financeiro/fluxo-caixa` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-8cb1ef1a | erp-imobiliario | `GET /api/financeiro/resumo` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-9e42c4b9 | erp-imobiliario | `GET /api/financeiro/{lancamento_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-33371a30 | erp-imobiliario | `GET /api/impostos` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-f3306188 | erp-imobiliario | `GET /api/impostos/resumo` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-b36a1e59 | erp-imobiliario | `GET /api/impostos/{imposto_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3cbd16a4 | erp-imobiliario | `GET /api/meta/webhook` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-862c4ac6 | erp-imobiliario | `GET /api/portal-cliente/{token}/chamados` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-242e5aa7 | erp-imobiliario | `GET /api/portal-cliente/{token}/dashboard` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-af3d369b | erp-imobiliario | `GET /api/portal-cliente/{token}/financeiro` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1b27c518 | erp-imobiliario | `GET /api/portal/{portal_token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1f716ef9 | erp-imobiliario | `GET /api/portal/{portal_token}/contratos` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a6a82c9c | erp-imobiliario | `GET /api/portal/{portal_token}/documentos` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-2a5a20f7 | erp-imobiliario | `GET /api/portal/{portal_token}/financeiro` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3a5d2749 | erp-imobiliario | `GET /api/portal/{portal_token}/imoveis` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-beeb4ae7 | erp-imobiliario | `GET /api/site/public/{slug}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3e861fbe | erp-imobiliario | `GET /api/site/public/{slug}/imovel/{imovel_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-71736472 | erp-imobiliario | `POST /api/assinaturas/webhook` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c5e4f1bb | erp-imobiliario | `POST /api/banco/conciliar` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3e220bb2 | erp-imobiliario | `POST /api/banco/gerar-remessa` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-301e3ecf | erp-imobiliario | `POST /api/banco/importar` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-cf71ba19 | erp-imobiliario | `POST /api/dimob/generate` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c8f7190a | erp-imobiliario | `POST /api/metas/digest/{periodo_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-410aa6fc | erp-imobiliario | `POST /api/portal-cliente/{token}/chamados` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-6e5f27e0 | erp-imobiliario | `schema erp: browser-role SELECT on 81 of 83 tables` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-c49d060a | igig | `GET /api/esteira/aprovar/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-5eeb0bd2 | igig | `GET /api/integracoes/email/gmail/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-8a30e145 | igig | `GET /api/webhooks/meta/leadgen` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-e966f014 | igig | `POST /api/comercial/leads/publico` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-91dd4cc4 | igig | `POST /api/esteira/aprovar/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-b809bb56 | orbity | `DELETE /api/clients/{client_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c9f75791 | orbity | `GET /api/clients/{client_id}/offboarding-preview` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-750c4cd6 | orbity | `GET /api/content/approve/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-445ac983 | orbity | `GET /api/reports/public/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-78ccdedd | orbity | `POST /api/billing/webhook/asaas/{org_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-cec6b842 | orbity | `POST /api/capture/{org_id}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-eef49b94 | orbity | `POST /api/clients/{client_id}/archive` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-021a038a | orbity | `POST /api/content/approve/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-dd29ab42 | orbity | `POST /api/financial/charges` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-196bf740 | orbity | `POST /api/financial/charges/{entry_id}/generate` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-9b37a4ca | p-studio | `GET /api/financeiro/status` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-45da28e3 | p-studio | `GET /api/negocios/etapas` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0e0dc110 | p-studio | `GET /api/producoes/etapas` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-b22295b9 | p-studio | `POST /api/integracoes/asaas/webhook` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-360287d2 | p-studio | `schema p_studio: browser-role SELECT on 15` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-3a8de25b | personal-finance | `schema personal-finance: browser-role SELECT on 19 of 20` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-fe44eb6e | pilates | `schema pilates: browser-role SELECT on 7` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-2df307df | seed | `GET /api/team/accept/validate` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-4d4cca79 | seed | `GET {}/{provider}/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-b2345dca | seed | `POST /api/auth/login` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-63775129 | social-wiring | `GET /api/calendar/oauth/callback` | service | unclear | medium | open | keeper 2026-11-10 |
| AT-a9cb4232 | social-wiring | `GET /api/integrations/accounts/gmail/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7134a2a2 | social-wiring | `GET /api/integrations/accounts/google_drive/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-33aa2b06 | social-wiring | `GET /api/integrations/accounts/instagram/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-603c0e74 | social-wiring | `GET /api/integrations/accounts/meta/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a5ea1821 | social-wiring | `GET /api/integrations/accounts/youtube/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1bcc8a18 | social-wiring | `GET /api/youtube/oauth/callback` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-971a905f | social-wiring | `schema imobi_scheduling: browser-role SELECT on 16 tables` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-8f3316f0 | social-wiring | `schema media_scheduling: browser-role SELECT on 14` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |
| AT-d56ff6ea | store | `GET /api/admin/pedidos` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-02ada095 | store | `GET /api/admin/produto/arquivo` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ad18592d | store | `GET /api/admin/settings` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-52c1e369 | store | `GET /api/public/autor/foto` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-8cc01706 | store | `GET /api/public/download/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-15d735d9 | store | `GET /api/public/pedidos/{token}` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-31d55917 | store | `GET /api/public/settings` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a62555e3 | store | `POST /api/admin/autor/foto` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-81639da5 | store | `POST /api/admin/pedidos/{pedido_id}/reenviar` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-5d9d47bb | store | `POST /api/admin/produto/arquivo` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-f213c45d | store | `POST /api/public/checkout` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-67361730 | store | `POST /api/webhooks/asaas` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0464fecb | store | `PUT /api/admin/settings` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-f4f4b20f | therapy-platform | `DELETE /api/admin/financials/commissions/{override_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-974ed5b5 | therapy-platform | `GET /api/admin/appointments` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a4a6ae65 | therapy-platform | `GET /api/admin/blocks` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-572dca81 | therapy-platform | `GET /api/admin/clinics` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-9aea8f48 | therapy-platform | `GET /api/admin/clinics/{clinic_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-90f17a51 | therapy-platform | `GET /api/admin/dashboard` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7f319391 | therapy-platform | `GET /api/admin/financials/` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ede9d2d0 | therapy-platform | `GET /api/admin/financials/commissions` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-64652764 | therapy-platform | `GET /api/admin/financials/payouts` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7d730523 | therapy-platform | `GET /api/admin/financials/summary` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-326203f8 | therapy-platform | `GET /api/admin/financials/transactions` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-f6b16495 | therapy-platform | `GET /api/admin/financials/wallets` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-5f795e67 | therapy-platform | `GET /api/admin/patients` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3a731d60 | therapy-platform | `GET /api/admin/pending` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-023d8c76 | therapy-platform | `GET /api/admin/reports` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-3bba44fe | therapy-platform | `GET /api/admin/reviews/flagged` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c72ce0ad | therapy-platform | `GET /api/admin/support/conversations` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-57cae698 | therapy-platform | `GET /api/admin/therapists` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0f15486f | therapy-platform | `GET /api/admin/therapists/{therapist_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-485caf1b | therapy-platform | `GET /api/invitations/accept/validate` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-37c72f65 | therapy-platform | `GET /api/scheduling/gcal/authorize` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-49e6c42d | therapy-platform | `GET /api/scheduling/gcal/callback` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-191396f1 | therapy-platform | `GET /api/settings/clinic/branding` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-4b94dbf3 | therapy-platform | `GET /api/settings/patient` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-d5fb638e | therapy-platform | `GET /api/settings/platform` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-39153ea7 | therapy-platform | `GET /api/settings/therapist` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-74559b1f | therapy-platform | `PATCH /api/settings/clinic/branding` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-99fd372c | therapy-platform | `PATCH /api/settings/patient` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-8a2092d1 | therapy-platform | `PATCH /api/settings/platform` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-23b287e8 | therapy-platform | `PATCH /api/settings/therapist` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c00f30e4 | therapy-platform | `POST /api/admin/approve/{entity_type}/{entity_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ab0fc6d2 | therapy-platform | `POST /api/admin/assign-patient` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a9a528f4 | therapy-platform | `POST /api/admin/commissions` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-e2db9031 | therapy-platform | `POST /api/admin/financials/commissions` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-a9f75d5c | therapy-platform | `POST /api/admin/financials/payouts/{payout_id}/process` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-93de93b5 | therapy-platform | `POST /api/admin/reject/{entity_type}/{entity_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-47b9760b | therapy-platform | `POST /api/admin/reports/{report_id}/resolve` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-065d8f3f | therapy-platform | `POST /api/admin/reviews/{review_id}/dismiss` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-6ef25b25 | therapy-platform | `POST /api/admin/reviews/{review_id}/hide` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-c5e1de76 | therapy-platform | `POST /api/admin/suspend/{entity_type}/{entity_id}` | org | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1988767d | therapy-platform | `POST /api/auth/forgot-password` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-7f732998 | therapy-platform | `POST /api/auth/google` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-1edad84e | therapy-platform | `POST /api/auth/login` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-ed31e6ce | therapy-platform | `POST /api/auth/register/clinic` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-790059b3 | therapy-platform | `POST /api/auth/register/patient` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-9f82e20a | therapy-platform | `POST /api/auth/register/therapist` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-0b58f0af | therapy-platform | `POST /api/invitations/accept` | none | unclear | medium | open | access-tiers-gate (initial scan) 2026-11-05 |
| AT-d28c061e | therapy-platform | `schema therapy: browser-role SELECT on 55 of 56` | none | browser-grant-schema | medium | open | prod-scan 2026-11-05 (owner/coordinator) 2026-11-05 |

## Bulk (defence in depth: browser grants on tables without `tier:org|public`)

- social-wiring: 267
- erp-imobiliario: 154
- therapy-platform: 114
- core: 87
- igig: 53
- commerce: 48
- personal-finance: 40
- orbity: 36
- community: 27
- academia-de-reciclagem: 16
- adconnect: 16
- daily-life: 16
- p-studio: 15
- monica: 9
- dev-team: 6
- seed: 2
- store: 1

## Accepted (rationale on record)

- AT-85fe7659 agents `audit P1-A: agents definition tables readable by authenticated via PostgREST` -- not-a-finding: prod verified clean 2026-11-05; 036 lockdown + default-privilege revoke
- AT-f7eb97c8 social-wiring `products/social-wiring/backend/app/modules/leads/routers/vista_clientes.py (1 routes)` -- Conditional platform gate: PUT /config is an org-tier route (org admin sets vista_rps / writes false and must see it in docs); only writing importar_identidade=true requires platform admin (LGPD, CONTRACT ad-lead-intake s8). Detector reads the inline require_platform_admin call as route-level platform tier.
