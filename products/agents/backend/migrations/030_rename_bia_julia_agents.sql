-- 030_rename_bia_julia_agents.sql -- owner order 2026-10-19.
--
--   * The Academia assistant, keyed `julia` since migration 006, is renamed to `bia` ("Bia").
--   * The real-estate SDR studio agent, keyed `lead-imob` since Lais A2, takes the key `julia`
--     (its display name is already "Julia").
--
-- ORDER MATTERS: the Academia row frees the key `julia` BEFORE the SDR row claims it
-- (agents.agents is UNIQUE (org_id, key)). Every other agent table (personas, versions, sections,
-- conversations, messages, approvals, knowledge, evals, audit log, tokens' principal_agent_id,
-- session transcripts, editorial items ...) references the agent by `agent_id` (UUID), so renaming
-- the key is one UPDATE; nothing else carries the key. The key-bearing leftovers are:
--   - agents.status_pagina.nome_pagina 'julia'  (the `/julia` nav page -> `/bia`);
--   - agents.app_integration_config.key 'julia_agent_id' (the academia principal id credential);
--   - agents.api_tokens.label text that names the old keys (cosmetic, kept readable).
--
-- Re-run safe: the Academia row is identified by what it is (key 'julia' + runtime 'claude_sdk' +
-- definition_mode 'legacy'), so after the rename a second run finds nothing to move and the SDR row
-- (runtime 'llm', definition_mode 'studio') is never mistaken for it. Every UPDATE is guarded by
-- NOT EXISTS on the target key, so it can never trip the unique constraint.
-- Forward-only. One multi-statement batch: the migration runner executes the file as a single
-- implicit transaction, so the two key moves land together or not at all.

SET search_path = agents, public;


-- 1. Academia agent: julia -> bia (frees the key `julia`).
UPDATE agents.agents a
   SET key  = 'bia',
       nome = CASE WHEN a.nome = 'Julia' THEN 'Bia' ELSE a.nome END
 WHERE a.key = 'julia'
   AND a.runtime = 'claude_sdk'
   AND a.definition_mode = 'legacy'
   AND NOT EXISTS (
        SELECT 1 FROM agents.agents b WHERE b.org_id = a.org_id AND b.key = 'bia'
   );

-- 2. SDR studio agent: lead-imob -> julia (only after step 1 freed the key).
UPDATE agents.agents a
   SET key = 'julia'
 WHERE a.key = 'lead-imob'
   AND NOT EXISTS (
        SELECT 1 FROM agents.agents b WHERE b.org_id = a.org_id AND b.key = 'julia'
   );

-- 3. Nav page visibility: the `julia` page row becomes `bia` (status preserved).
UPDATE agents.status_pagina s
   SET nome_pagina = 'bia'
 WHERE s.nome_pagina = 'julia'
   AND NOT EXISTS (SELECT 1 FROM agents.status_pagina t WHERE t.nome_pagina = 'bia');
INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('bia', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

-- 4. Credential store: the academia principal-id credential is now `bia_agent_id`.
UPDATE agents.app_integration_config c
   SET key = 'bia_agent_id'
 WHERE c.key = 'julia_agent_id'
   AND NOT EXISTS (SELECT 1 FROM agents.app_integration_config d WHERE d.key = 'bia_agent_id');

-- 5. Token labels that name the old keys (display only).
UPDATE agents.api_tokens
   SET label = replace(label, 'agents → academia (Julia)', 'agents → academia (Bia)')
 WHERE label LIKE '%agents → academia (Julia)%';
UPDATE agents.api_tokens
   SET label = replace(label, ' · lead-imob:', ' · julia:')
 WHERE label LIKE 'canal % · lead-imob:%';

