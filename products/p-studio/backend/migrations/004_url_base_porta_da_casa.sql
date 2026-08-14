-- ============================================================================
-- 004_url_base_porta_da_casa.sql — P Studio
-- Schema: public (linha do produto no catálogo da plataforma)
--
-- A 002 registrou o produto com `url_base = 'http://localhost:5176'`, que era
-- a porta do Vite no workspace standalone. Depois da absorção o produto roda
-- no modelo de container da casa: UM container, uvicorn servindo API + SPA na
-- MESMA porta (8014). A porta 5176 não existe mais em lugar nenhum.
--
-- Por que forward migration e não editar a 002: a 002 já foi aplicada neste
-- banco. Editar um arquivo já aplicado faz o arquivo mentir sobre o que rodou
-- — quem ler a 002 amanhã veria 8014 e concluiria que nunca houve 5176.
--
-- ⚠️ O que esta migration NÃO é. `url_base` NÃO é a URL pública do produto.
-- Verificado no banco vivo em 2026-08-14: TODOS os 13 produtos do catálogo
-- carregam `http://localhost:<porta>`, incluindo os quatro que estão em
-- produção agora (erp-imobiliario, igig, orbity, social-wiring). O roteamento
-- público é outro mecanismo — `PRODUCT_URL_*` no `.env`, padrão
-- `https://{slug}.noctusai.com`, gerenciado por
-- `noctus.dev.ensure_product_url_roster`. Logo isto é alinhamento de
-- convenção (porta do backend, como todo o resto da frota), não correção de
-- vazamento de localhost para produção.
--
-- Idempotente: o WHERE só casa com o valor antigo, então reaplicar não faz
-- nada e nunca sobrescreve uma edição posterior feita pelo admin.
-- ============================================================================

UPDATE public.products
   SET url_base = 'http://localhost:8014'
 WHERE slug = 'p-studio'
   AND url_base = 'http://localhost:5176';
