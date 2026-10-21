-- backfill_corretor_do_lead_como_membro.sql
--
-- DATA-ONLY. A lead created with a corretor (`leads.corretor_id`) never made
-- that broker a member of the card (`cliente_membros`), so Negociacao ->
-- Divisao da comissao showed "Nenhum membro no cartao" for the agents slice
-- (live finding, deal 857). Code now writes the membership on create
-- (`clientes_service.ensure_corretor_membro`) and in the clientes sweep; this
-- backfills the cards that already exist.
--
-- Scope: OPEN cards (not archived, not closed) whose cliente has NO member at
-- all. Cards an operator already staffed are untouched. One member per
-- cliente (earliest lead's corretor, deterministic). Idempotent:
-- ON CONFLICT on the (cliente_id, lead_corretor_id) PK + the NOT EXISTS guard.

INSERT INTO social_wiring.cliente_membros (cliente_id, lead_corretor_id, org_id)
SELECT DISTINCT ON (a.cliente_id)
       a.cliente_id, l.corretor_id, a.org_id
  FROM social_wiring.atendimentos a
  JOIN social_wiring.leads l ON l.id = a.lead_id
 WHERE l.corretor_id IS NOT NULL
   AND a.cliente_id IS NOT NULL
   AND COALESCE(a.arquivado, false) = false
   AND a.closed_at IS NULL
   AND NOT EXISTS (
         SELECT 1 FROM social_wiring.cliente_membros m
          WHERE m.cliente_id = a.cliente_id
       )
 ORDER BY a.cliente_id, l.created_at, l.id
ON CONFLICT (cliente_id, lead_corretor_id) DO NOTHING;
