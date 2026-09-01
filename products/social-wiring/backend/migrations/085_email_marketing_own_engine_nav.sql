-- 085_email_marketing_own_engine_nav.sql — register the own-engine Email
-- Marketing pages in status_pagina.
--
-- `app/modules/email_marketing/` is the product's OWN mailing engine
-- (Resend-backed; contacts / contact_lists / templates / campaigns /
-- automations / send_logs / sender_domains, all created in migration 001).
-- It shipped ~62 HTTP routes and NO frontend: the five existing
-- /email-marketing/* PAGES consume `/api/mailchimp/*` instead, so the product
-- has carried two email backends with only the connected one wired. The
-- 2026-09-01 endpoint-to-UI parity sweep found it as the largest unsurfaced
-- module in the product.
--
-- Seven pages now cover it (App.tsx `key: "email-noc"`):
--   email_painel          → /email              analytics/dashboard
--   email_campanhas_noc   → /email/campanhas    campaigns + lifecycle + AI
--   email_contatos_noc    → /email/contatos     contacts + import
--   email_listas_noc      → /email/listas       lists + membership
--   email_templates_noc   → /email/templates    templates + preview + AI
--   email_automacoes_noc  → /email/automacoes   automations + steps + enroll
--   email_dominios_noc    → /email/dominios     sender domains + verify
--
-- The `_noc` suffix is deliberate: `email_campanhas` / `email_listas` /
-- `email_templates` / `email_membros` / `email_config` are ALREADY TAKEN by
-- the Mailchimp-proxy pages, which keep their rows and their routes untouched.
-- `nome_pagina` is UNIQUE, so reusing a name would not add a row — it would
-- silently leave the new page invisible while the ON CONFLICT swallowed it.
--
-- Seeded 'producao': the backend has been live and tested for months, and the
-- UI ships complete (all four states on every list, page-scoped CRUD via the
-- canonical ResourceManager organ) and verified end-to-end against the live
-- API before this migration is applied.
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('email_painel',         'producao'),
    ('email_campanhas_noc',  'producao'),
    ('email_contatos_noc',   'producao'),
    ('email_listas_noc',     'producao'),
    ('email_templates_noc',  'producao'),
    ('email_automacoes_noc', 'producao'),
    ('email_dominios_noc',   'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
