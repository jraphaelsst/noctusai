"""Structure ↔ constructor parity manifest (keeper ``check_structure_constructor_parity``).

When an entity's STRUCTURE changes (a field on its record), every function that CONSTRUCTS it must change in the same
commit, or creation silently drops the field: unit tests stay green (each surface defaults it) while the real path
breaks. This manifest names the record and every surface the field must reach. A field that legitimately does not
reach a surface is listed in that surface's ``exempt`` WITH the reason; the keeper reads this file by AST (never
imports it) and fails a record field that is neither carried nor exempted.

Adding a new field ⇒ carry it on every surface below, or exempt it with a reason. Adding a new constructor of the
entity ⇒ add it here as a surface. Pattern: ``KB § PATTERNS/backend/structure-constructor-parity.md``.

Surface ``kind``:
  ``fields``            the annotated fields of a class (dataclass / pydantic model) — the record itself uses it;
  ``params``            the parameter names of a function or method;
  ``call_kwargs:<Fn>``  the keyword names passed to ``<Fn>(...)`` inside the target function;
  ``dict_keys:<var>``   the keys of the dict literal assigned to ``<var>`` inside the target function;
  ``tuple``             the strings of a module-level tuple (``*OTHER`` entries from the same module expand).
Targets are ``<repo-relative path>::<Qualified.name>``.
"""
from __future__ import annotations

_S = "products/agents/backend/app/stores/studio_definitions.py"

#: Reasons reused across surfaces.
_DB = "set by the database (default / now())"
_NUNCA = "never chosen at creation: a created agent is always definition_mode='studio'"
_INATIVO = "a created agent is always inactive; activation is its publish"
_LIMIAR = "DB default 0.8; changed later through update_agent"
_MODO = "derived from definition_scope by _validate_scope"
_SUPERFICIE = "validated against the row's kind, so ensure_definicao applies it right after create via update_definicao"
_PLATAFORMA = "this path always creates a platform definition (definition_scope='plataforma')"
_INSTANCIA = "only an org INSTANCE carries it (_instanciar)"
_EXEMPLAR = "platform-ADMIN toggle only (PUT /plataforma/agentes/{key}/exemplar), never at create"
_ORG = "the caller's org (the platform org), from the session/token"

STRUCTURE_PARITY = {
    "agent": {
        "record": f"{_S}::StudioAgentRecord",
        "surfaces": [
            {
                "name": "Supabase row → record (every read)",
                "target": f"{_S}::SupabaseStudioDefinitionStore._agent",
                "kind": "call_kwargs:StudioAgentRecord",
                "exempt": {},
            },
            {
                "name": "Fake store create builds the record",
                "target": f"{_S}::FakeStudioDefinitionStore.create_studio_agent",
                "kind": "call_kwargs:StudioAgentRecord",
                "exempt": {"superficie_claude": _SUPERFICIE},
            },
            {
                "name": "Supabase create_studio_agent signature",
                "target": f"{_S}::SupabaseStudioDefinitionStore.create_studio_agent",
                "kind": "params",
                "exempt": {
                    "id": _DB, "created_at": _DB, "updated_at": _DB, "definition_mode": _NUNCA, "ativo": _INATIVO,
                    "publicacao_limiar": _LIMIAR, "conteudo_modo": _MODO, "superficie_claude": _SUPERFICIE,
                },
            },
            {
                "name": "Supabase insert payload",
                "target": f"{_S}::SupabaseStudioDefinitionStore.create_studio_agent",
                "kind": "dict_keys:payload",
                "exempt": {
                    "id": _DB, "created_at": _DB, "updated_at": _DB, "publicacao_limiar": _LIMIAR,
                    "superficie_claude": _SUPERFICIE,
                },
            },
            {
                "name": "ensure_definicao (the one platform-definition constructor)",
                "target": "products/agents/backend/app/studio/plataforma.py::ensure_definicao",
                "kind": "params",
                "exempt": {
                    "id": _DB, "created_at": _DB, "updated_at": _DB, "definition_mode": _NUNCA, "ativo": _INATIVO,
                    "publicacao_limiar": _LIMIAR, "conteudo_modo": _MODO, "definition_scope": _PLATAFORMA,
                    "definition_agent_id": _INSTANCIA,
                },
            },
            {
                "name": "POST /plataforma/agents request body",
                "target": "products/agents/backend/app/schemas/studio_plataforma.py::PlataformaAgentCreateRequest",
                "kind": "fields",
                "exempt": {
                    "id": _DB, "org_id": _ORG, "created_at": _DB, "updated_at": _DB, "definition_mode": _NUNCA,
                    "ativo": _INATIVO, "publicacao_limiar": _LIMIAR, "conteudo_modo": _MODO,
                    "definition_scope": _PLATAFORMA, "definition_agent_id": _INSTANCIA, "exemplar": _EXEMPLAR,
                },
            },
            {
                "name": "POST /plataforma/agents forwards the body to ensure_definicao",
                "target": "products/agents/backend/app/routers/studio_conteudo_router.py::create_platform_definition",
                "kind": "call_kwargs:ensure_definicao",
                "exempt": {
                    "id": _DB, "org_id": "passed positionally (ctx.org_id)", "key": "passed positionally (payload.key)",
                    "created_at": _DB, "updated_at": _DB, "definition_mode": _NUNCA, "ativo": _INATIVO,
                    "publicacao_limiar": _LIMIAR, "conteudo_modo": _MODO, "definition_scope": _PLATAFORMA,
                    "definition_agent_id": _INSTANCIA, "exemplar": _EXEMPLAR,
                },
            },
            {
                "name": "definition response model",
                "target": "products/agents/backend/app/schemas/studio_plataforma.py::PlataformaAgentOut",
                "kind": "fields",
                "exempt": {
                    "created_at": "not part of the definition view", "updated_at": "not part of the definition view",
                    "definition_mode": "always 'studio' for a definition", "ativo": _INATIVO,
                    "publicacao_limiar": "read from the agent shell (GET /agents/{key})", "definition_agent_id": _INSTANCIA,
                },
            },
            {
                "name": "_definicao_out fills the response",
                "target": "products/agents/backend/app/routers/studio_conteudo_router.py::_definicao_out",
                "kind": "call_kwargs:PlataformaAgentOut",
                "exempt": {
                    "created_at": "not part of the definition view", "updated_at": "not part of the definition view",
                    "definition_mode": "always 'studio' for a definition", "ativo": _INATIVO,
                    "publicacao_limiar": "read from the agent shell (GET /agents/{key})", "definition_agent_id": _INSTANCIA,
                },
            },
            {
                "name": "MCP noctus.agents.content action=criar_agente payload keys",
                "target": "mcp/noctusai/tools/noctus/agents/content.py::_CRIAR_CAMPOS",
                "kind": "tuple",
                "exempt": {
                    "id": _DB, "key": "the agent= argument", "org_id": _ORG, "created_at": _DB, "updated_at": _DB,
                    "definition_mode": _NUNCA, "ativo": _INATIVO, "publicacao_limiar": _LIMIAR, "conteudo_modo": _MODO,
                    "definition_scope": _PLATAFORMA, "definition_agent_id": _INSTANCIA, "exemplar": _EXEMPLAR,
                },
            },
        ],
    },
}
