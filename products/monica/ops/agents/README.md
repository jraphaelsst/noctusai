# `monica-leads` -- the agent definition behind the Contexto page

The page **Contexto** edits the *org specs* of an agent definition (`agents.agent_version_specs` declares the
fields; `agents.agent_org_specs` holds Mônica's values). The agent itself is explicitly LATER: it has no prompt
behaviour beyond what Studio requires, it is **not activated on any channel**. Reference:
`KB § INTEGRATIONS/agents-org-specs.md`.

Files here (data only, nothing is applied by the repo):

| File | What |
|---|---|
| `monica-leads.specs.json` | the 11 declared specs (pt-BR label + help, `texto` / `texto_longo`, none required) = the body of `PUT /api/studio/agents/monica-leads/draft/specs` (`noctus.agents.content kind=spec`) |
| `prefill-contexto.sql` | prefills ONLY `quem_sou` and `instagram` for her org; `ON CONFLICT DO NOTHING` |

## Go-live steps (tech-lead; the first needs the Studio content token)

1. Create the definition (dry-run first): `noctus.agents.content action=criar_agente agent=monica-leads
   base_url=<agents prod> payload_path=<json outside git: {"nome": "Monica -- agente de leads",
   "owner_product": "monica", "instanciavel": false}>`.
2. Declare the specs: `action=set kind=spec agent=monica-leads payload_path=<copy of monica-leads.specs.json>`
   (dry-run diff, then `confirm=True`).
3. Publish a version (Studio; the draft needs a version for `GET /api/studio/agents/monica-leads/specs` to return
   the form -- the specs endpoint reads the ACTIVE version).
4. Make sure Mônica's org has an INSTANCE row of the key (`agents.agents`, `definition_scope='instancia'`), then apply
   `prefill-contexto.sql`.

**Open decision (surfaced, not assumed):** `instanciavel=true` would give EVERY org an instance of this agent
once published; `false` keeps it Mônica-only but then her instance row is created by hand/Studio. Until step 3-4
the Contexto page shows a clear "ainda não foi liberado" / "ainda não está disponível" message (the proxy answers
404 or an empty form) -- it never shows made-up fields.
