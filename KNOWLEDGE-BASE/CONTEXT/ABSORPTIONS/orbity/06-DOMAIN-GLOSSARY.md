# 06 — Domain Glossary (pt-BR → meaning)

The agency-business vocabulary encoded in Orbity. Read this alongside any other doc.

| Term (pt-BR) | Meaning |
|---|---|
| **Agência** | The tenant — a marketing agency (the paying SaaS customer). Isolated by `agency_id`. |
| **Cliente** | The agency's customer (a business it markets for). A DATA row, **not** a SaaS login. |
| **Lead** | A prospect of a *client*, captured through funnels; lives in the Kanban CRM pipeline. |
| **Gestor de tráfego** | Paid-traffic manager — an agency staff role. |
| **Designer** / **Administrador** | The other agency staff (job) roles. ⚠️ `administrador` is overloaded — also used for platform-master detection. |
| **Funil / Etapa** | CRM funnel / stage. Default pipeline: *Novo → Contato → Qualificado → Proposta → Negociação → Fechado → Perdido* (color-coded, reorderable per agency). |
| **Temperatura** (frio/morno/quente — cold/warm/hot) | Lead quality from qualification scoring (`≥5 hot`, `≥2 warm`, else cold; blocker ⇒ cold). |
| **Ghosting** | A lead going silent. Automation cadences chase it; `stop_on_reply` ends the chase when they answer. |
| **Controle de tráfego** | Per-client ad-ops record: platforms, `daily_budget`, `result` (excellent…terrible), `situation` (improving/worsening), `last_optimization`. |
| **Otimização** | The recurring act of tuning ad campaigns. `OptimizationReminder`/`OptimizationSheet` nudge the gestor on a cadence. |
| **Fechamento mensal** | Monthly closure — the auto-billing + financial-snapshot job (1st of month). |
| **Conexa** | Brazilian fiscal/billing gateway — issues **notas fiscais** (tax invoices), PIX, boletos. |
| **Asaas** | Alternate BR payment gateway (PIX + boleto). |
| **Boleto** | Brazilian bank payment slip. **PIX** = instant BR payment (copy-paste code + QR). |
| **Nota fiscal** | Brazilian tax/fiscal invoice (legally required for sales). |
| **PPR (Participação nos Resultados)** | Profit-sharing bonus program for staff (net-profit pool gated by revenue + NPS → weighted scorecards → final bonus). |
| **NPS** | Client satisfaction score (0–10), feeds the bonus calc. |
| **Boas-vindas / Trial** | Welcome message + 7-day trial. |
| **Pixel / CAPI / Evento** | Meta pixel + Conversions API server-side events (`Lead`, `QualifiedLead`, `ColdLead`, `Purchase`, `Schedule`, `SubmitApplication`). |
| **Snapshot** | Frozen monthly financials (`monthly_snapshots`) or frozen client ad-report (`report_snapshot`). |
| **Painel de Controle** | The master/vendor superadmin console. |
| **Lembretes** | Personal reminders (with recurrence). |
| **Reunião** | Meeting (agenda; Google Calendar two-way sync). |
| **Comissões / Salários** | Commissions / salaries (finance back-office). |
| **DRE** | Demonstração do Resultado do Exercício — income statement (admin financial view). |
| **Orbity leads** | The vendor's OWN sales pipeline of prospective agencies (dogfooding the CRM). |
