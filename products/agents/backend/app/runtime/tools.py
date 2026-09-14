"""The academia in-process SDK MCP tools (contract §C / §E.4 / §E.5) — one
per academia tool Julia's allowlist exposes.

``build_academia_tools`` is a PER-TURN factory (not module-level ``@tool``
definitions) because every handler closes over a specific
``TurnContext``/``AcademiaApi``/agent identity/signing key — the same
reason ``build_launch_options`` (claude_runtime.py) is called fresh for
every ``run_turn``.

Handlers run in the CONTROL PLANE (this process), never in the Julia CLI
subprocess — that is the whole point of an in-process SDK MCP server
(contract §E.5 "Tools are in-process SDK MCP tools ... executed by the
control plane, not by the CLI").

**The ``_approval`` seam.** For an ``escrita`` tool, ``can_use_tool``
(``claude_runtime.py``) has already run the gate + broker BEFORE the SDK
ever calls this module's handler, and injects the resulting
``{"approval_id": ..., "approved_by": ...}`` into the handler's own
``args`` via ``PermissionResultAllow(updated_input=...)`` (the SDK
forwards ``updated_input`` verbatim as the tool call's actual arguments —
verified live, ``claude_agent_sdk/_internal/query.py:512-514``). Every
escrita handler below pops ``_approval`` before validating the rest of
``args`` against its own §C field set, mints the assertion for exactly
the method/path/body it is about to send, and marks the approval
consumed only after academia returns without raising.
"""
from __future__ import annotations

import json
from typing import Any, Callable
from uuid import UUID

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

from app.runtime.academia_api import AcademiaApi, AcademiaApiError
from app.runtime.assertion import mint_assertion
from app.runtime.types import TurnContext

__all__ = ["build_academia_tools"]


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _error(exc: AcademiaApiError) -> dict[str, Any]:
    return _ok({"ok": False, "error": {"status": exc.status, "code": exc.code, "detail": exc.detail}})


def _leitura(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    academia_api: AcademiaApi,
    path_fn: Callable[[dict[str, Any]], str],
    params_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda args: {},
) -> SdkMcpTool[Any]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await academia_api.get(path_fn(args), params=params_fn(args))
        except AcademiaApiError as exc:
            return _error(exc)
        return _ok(result)

    return tool(name, description, schema)(handler)


def _escrita(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    academia_api: AcademiaApi,
    agent_id: UUID,
    secret: str,
    aud: str,
    ctx: TurnContext,
    method_fn: Callable[[dict[str, Any]], str],
    path_fn: Callable[[dict[str, Any]], str],
    body_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> SdkMcpTool[Any]:
    # `create_sdk_mcp_server("academia", tools=[...])` prefixes whatever
    # leaf name `tool()` registers here into `mcp__academia__<name>` when
    # exposing it to Claude — `full_name` below is that FULL form, used
    # ONLY for the gate/assertion `tool` claim (must match
    # `app.runtime.gate.ESCRITA` and `ToolUseBlock.name` exactly). Passing
    # the already-prefixed form to `tool()` itself would double-prefix
    # and silently break every gate match.
    full_name = f"mcp__academia__{name}"

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        raw_approval = args.get("_approval")
        rest = {k: v for k, v in args.items() if k != "_approval"}
        if not raw_approval or "approval_id" not in raw_approval:
            # The gate is the only legitimate caller of an escrita handler
            # (contract §E.4/§E.9) — reaching here without an injected
            # approval means can_use_tool was bypassed somehow. No silent
            # fallback: refuse rather than write unapproved.
            return _ok(
                {
                    "ok": False,
                    "error": {
                        "status": 403,
                        "code": "approval_missing",
                        "detail": "Nenhuma aprovação associada a esta chamada.",
                    },
                }
            )

        method = method_fn(rest)
        path = path_fn(rest)
        body = body_fn(rest)
        approval_id = UUID(raw_approval["approval_id"])
        approved_by = UUID(raw_approval["approved_by"])

        assertion = mint_assertion(
            approval_id=approval_id,
            secret=secret,
            agent_id=agent_id,
            org_id=ctx.org_id,
            tool_name=full_name,
            method=method,
            path=path,
            body=body,
            approved_by=approved_by,
            requested_by=ctx.requested_by,
            aud=aud,
        )

        try:
            result = await academia_api.request(method, path, body=body, assertion=assertion)
        except AcademiaApiError as exc:
            return _error(exc)
        return _ok(result)

    return tool(name, description, schema)(handler)


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_S = {"type": "string"}
_S_OPT = {"type": ["string", "null"]}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_TAGS = {"type": "array", "items": {"type": "string"}}


def build_academia_tools(
    *,
    ctx: TurnContext,
    academia_api: AcademiaApi,
    agent_id: UUID,
    secret: str,
    aud: str,
) -> Any:
    """Returns the ``McpSdkServerConfig`` ready for
    ``ClaudeAgentOptions.mcp_servers["academia"]`` — every §E.4 academia
    tool, bound to THIS turn's context/identity/signing key."""

    leitura = [
        _leitura(
            "kb_buscar",
            "Busca entradas do KB da Academia de Reciclagem por texto, categoria, subcategoria ou tag.",
            _obj(
                {
                    "consulta": _S_OPT,
                    "categoria": _S_OPT,
                    "subcategoria": _S_OPT,
                    "tag": _S_OPT,
                    "limite": _I,
                    "offset": _I,
                },
                [],
            ),
            academia_api=academia_api,
            path_fn=lambda a: "/api/kb",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "kb_ler",
            "Lê uma entrada do KB pelo slug.",
            _obj({"slug": _S}, ["slug"]),
            academia_api=academia_api,
            path_fn=lambda a: f"/api/kb/{a['slug']}",
        ),
        _leitura(
            "decisao_listar",
            "Lista decisões do projeto, opcionalmente filtradas por estado.",
            _obj({"estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/decisions",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "pergunta_listar",
            "Lista perguntas em aberto (ou respondidas/todas).",
            _obj({"estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/questions",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "historico_timeline",
            "Lista eventos recentes do histórico do projeto.",
            _obj({"limite": _I}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/timeline",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "roadmap_ler",
            "Lê as fases do roadmap do projeto.",
            _obj({}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/roadmap",
        ),
        _leitura(
            "tarefa_listar",
            "Lista tarefas, opcionalmente filtradas por fase ou estado.",
            _obj({"fase": _S_OPT, "estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/tasks",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "tarefa_preparar_sessao",
            "Retorna o resumo de início de sessão: fase atual, próximas tarefas, bloqueadas e perguntas bloqueantes.",
            _obj({}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/session-prep",
        ),
        _leitura(
            "conteudo_listar",
            "Lista conteúdos de treinamento (roteiro, trilha, quiz, copy...), opcionalmente por tipo.",
            _obj({"tipo": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/content",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "conteudo_ler",
            "Lê um conteúdo de treinamento pelo código.",
            _obj({"codigo": _S}, ["codigo"]),
            academia_api=academia_api,
            path_fn=lambda a: f"/api/content/{a['codigo']}",
        ),
    ]

    def _kb_escrever_method(a: dict[str, Any]) -> str:
        return "PUT" if a.get("slug") else "POST"

    def _kb_escrever_path(a: dict[str, Any]) -> str:
        return f"/api/kb/{a['slug']}" if a.get("slug") else "/api/kb"

    def _kb_escrever_body(a: dict[str, Any]) -> dict[str, Any]:
        body = {"titulo": a["titulo"], "corpo_md": a["corpo_md"], "motivo": a["motivo"]}
        if a.get("categoria") is not None:
            body["categoria"] = a["categoria"]
        if a.get("subcategoria") is not None:
            body["subcategoria"] = a["subcategoria"]
        if not a.get("slug"):
            # POST /api/kb requires categoria (§B.1); PUT never rejects it.
            body.setdefault("categoria", a.get("categoria"))
        return body

    escrita = [
        _escrita(
            "kb_escrever",
            "Cria ou atualiza uma entrada do KB. Sem slug: cria (POST). Com slug: atualiza (PUT).",
            _obj(
                {
                    "slug": _S_OPT,
                    "categoria": _S_OPT,
                    "subcategoria": _S_OPT,
                    "titulo": _S,
                    "corpo_md": _S,
                    "motivo": _S,
                },
                ["titulo", "corpo_md", "motivo"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=_kb_escrever_method,
            path_fn=_kb_escrever_path,
            body_fn=_kb_escrever_body,
        ),
        _escrita(
            "kb_mover",
            "Move (renomeia) uma entrada do KB de um slug para outro.",
            _obj({"origem": _S, "destino": _S, "motivo": _S}, ["origem", "destino", "motivo"]),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "PUT",
            path_fn=lambda a: f"/api/kb/{a['origem']}",
            body_fn=lambda a: {"novo_slug": a["destino"], "motivo": a["motivo"]},
        ),
        _escrita(
            "decisao_registrar",
            "Registra uma nova decisão do projeto, com motivo.",
            _obj(
                {
                    "titulo": _S,
                    "contexto": _S_OPT,
                    "decisao": _S,
                    "motivo": _S,
                    "alternativas_rejeitadas": _S_OPT,
                    "relacionadas": _TAGS,
                },
                ["titulo", "decisao", "motivo"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/decisions",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita(
            "decisao_substituir",
            "Substitui uma decisão anterior por uma nova, mantendo o histórico (append-only).",
            _obj(
                {
                    "substitui": _S,
                    "titulo": _S,
                    "contexto": _S_OPT,
                    "decisao": _S,
                    "motivo": _S,
                    "alternativas_rejeitadas": _S_OPT,
                    "relacionadas": _TAGS,
                },
                ["substitui", "titulo", "decisao", "motivo"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: f"/api/decisions/{a['substitui']}/supersede",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "substitui"
            },
        ),
        _escrita(
            "pergunta_adicionar",
            "Registra uma pergunta em aberto, o motivo de importar e o que ela bloqueia.",
            _obj(
                {
                    "pergunta": _S,
                    "por_que_importa": _S,
                    "bloqueia": _S,
                    "destino_kb": _S_OPT,
                },
                ["pergunta", "por_que_importa", "bloqueia"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/questions",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita(
            "pergunta_responder",
            "Responde uma pergunta em aberto pelo código.",
            _obj({"codigo": _S, "resposta": _S}, ["codigo", "resposta"]),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: f"/api/questions/{a['codigo']}/answer",
            body_fn=lambda a: {"resposta": a["resposta"]},
        ),
        _escrita(
            "historico_append",
            "Registra um evento no histórico do projeto.",
            _obj(
                {"titulo": _S, "descricao": _S, "data": _S_OPT},
                ["titulo", "descricao"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/timeline",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita(
            "roadmap_atualizar",
            "Atualiza uma fase do roadmap (estado, título, objetivo ou critério de conclusão).",
            _obj(
                {
                    "codigo": _S,
                    "estado": _S_OPT,
                    "titulo": _S_OPT,
                    "objetivo": _S_OPT,
                    "concluida_quando": _S_OPT,
                },
                ["codigo"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "PATCH",
            path_fn=lambda a: f"/api/roadmap/{a['codigo']}",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "codigo"
            },
        ),
        _escrita(
            "tarefa_criar",
            "Cria uma nova tarefa dentro de uma fase do roadmap.",
            _obj(
                {
                    "titulo": _S,
                    "fase": _S,
                    "detalhe": _S_OPT,
                    "bloqueada_por": _S_OPT,
                },
                ["titulo", "fase"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/tasks",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita(
            "tarefa_atualizar",
            "Atualiza uma tarefa existente pelo código.",
            _obj(
                {
                    "codigo": _S,
                    "estado": _S_OPT,
                    "detalhe": _S_OPT,
                    "bloqueada_por": _S_OPT,
                },
                ["codigo"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "PATCH",
            path_fn=lambda a: f"/api/tasks/{a['codigo']}",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "codigo"
            },
        ),
        _escrita(
            "conteudo_salvar",
            "Salva um conteúdo de treinamento (roteiro, trilha, quiz, copy...).",
            _obj(
                {
                    "tipo": _S,
                    "titulo": _S,
                    "corpo_md": _S,
                    "referencia": _S_OPT,
                    "fontes": _TAGS,
                },
                ["tipo", "titulo", "corpo_md"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/content",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita(
            "pesquisa_capturar_fonte",
            "Captura uma fonte de pesquisa (URL, trecho citado, resumo) e a vincula a uma entrada do KB.",
            _obj(
                {
                    "url": _S,
                    "titulo": _S,
                    "trecho_citado": _S,
                    "resumo": _S,
                    "kb_slug": _S,
                    "vigencia_confirmada": _B,
                    "exige_da_empresa": _S_OPT,
                },
                ["url", "titulo", "trecho_citado", "resumo", "kb_slug", "vigencia_confirmada"],
            ),
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/sources",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
    ]

    return create_sdk_mcp_server("academia", tools=[*leitura, *escrita])
