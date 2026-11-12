"""Shared PostgREST-error → typed-store-error mapping for the Agent Studio
stores (``studio_definitions`` / ``studio_knowledge`` / ``studio_evals``).

Why one module: supabase-py RAISES ``postgrest.exceptions.APIError`` on a
constraint violation (``code`` = the SQLSTATE, ``message`` = the server
text) — it never returns empty ``data``. A Real store that tests
``if not resp.data`` after a duplicate insert therefore 500s in prod while
its Fake (which raises a typed error) keeps the router tests green. Every
studio write goes through :func:`exec_query` / :func:`exec_rpc` so the SAME
translation applies everywhere, and the routes map the typed errors, never a
driver exception.

Translation (first match wins):

* The 012/013 functions and triggers ``RAISE EXCEPTION '<code>'`` with the
  machine code AS the message — mapped by :data:`_P0001_CODES`.
* ``23505`` unique violation → :class:`StudioConflict` ``unique_code``.
* ``23503`` FK violation → :class:`StudioConflict` ``fk_code``.
* ``23514`` CHECK violation → :class:`ValueError` (the size caps / allowlists
  — a 422 at the router, never a 500).
* Anything else propagates unchanged (a real failure is never masked).

The text a PERSON reads is never the exception's own message: a DB-mapped
conflict would carry the raw Postgres text (constraint and index names, e.g.
``duplicate key value violates unique constraint "skill_files_caminho_key"``)
and a store-raised one carries English internal prose. Routers render
:func:`mensagem_conflito` — the pt-BR text per ``code`` from
:data:`MENSAGENS_CONFLITO`, with a generic pt-BR fallback — so neither leaks.
"""
from __future__ import annotations

from typing import Any, Callable

from app.stores.errors import Conflict, NotFound

__all__ = [
    "StudioConflict",
    "VersionImmutable",
    "MENSAGENS_CONFLITO",
    "map_db_error",
    "erro_de_item",
    "mensagem_conflito",
    "exec_query",
    "exec_rpc",
]


class StudioConflict(Conflict):
    """A write refused for a machine-readable reason — ``code`` is the §D
    409 code the router returns verbatim (``key_taken`` / ``draft_exists`` /
    ``skill_exists`` / ``client_exists`` / ``chave_conflict`` /
    ``caminho_conflict`` / ``draft_referenced`` / ``draft_changed`` /
    ``eval_required`` / ``client_entries_cap`` / ``slug_taken`` /
    ``slug_in_other_collection`` / ``case_in_use`` /
    ``run_not_cancellable``)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class VersionImmutable(StudioConflict):
    """The target version (or a child of it) is not a ``rascunho``."""

    def __init__(self, message: str = "") -> None:
        super().__init__("version_immutable", message or "version_immutable")


#: The pt-BR text a person reads for each 409 ``code``. Keyed by the CODE (the contract), never by the exception's
#: message (internal: DB text or English prose). A code missing here falls back to
#: :data:`MENSAGEM_CONFLITO_GENERICA` — still pt-BR, still free of internals.
MENSAGENS_CONFLITO: dict[str, str] = {
    "version_immutable": "A versão publicada é imutável.",
    "loop_ativo_existente": "Este agente já tem um loop de avaliação ativo nesta suíte. Encerre-o antes de abrir outro.",
    "rodada_em_andamento": "Já há uma rodada deste loop em andamento.",
    "loop_encerrado": "O loop de avaliação foi encerrado. Inicie um novo loop.",
    "execucao_em_andamento": "Você já tem uma avaliação em andamento. Aguarde terminar ou cancele-a antes de iniciar outra.",
    "loop_ativo_do_usuario": "Você já tem um loop de avaliação ativo. Finalize-o ou pare-o (\"Parar loop\") antes de iniciar outra avaliação.",
    "compiled_prompt_immutable": "O prompt compilado já gravado não pode ser alterado.",
    "audit_log_append_only": "O histórico de auditoria não pode ser alterado.",
    "draft_exists": "Este agente já tem um rascunho em edição.",
    "draft_changed": "O rascunho mudou desde que foi aberto. Recarregue a página e tente de novo.",
    "conflito_de_versao": "O rascunho mudou desde que foi aberto. Recarregue a página e tente de novo.",
    "draft_referenced": "Este rascunho já é usado por um prompt compilado e não pode ser removido.",
    "eval_required": "A avaliação do prompt atual ainda não passou; só uma pessoa pode publicar com justificativa.",
    "mecanismo_required": "A suíte de mecanismo ainda não foi aprovada para o prompt atual.",
    "chave_conflict": "Há chaves repetidas no que foi enviado.",
    "chave_taken": "Já existe um item com essa chave.",
    "caminho_conflict": "Há arquivos com o mesmo caminho na skill.",
    "skill_exists": "Já existe uma skill com esse nome.",
    "client_exists": "Já existe um cliente com esse identificador.",
    "client_entries_cap": "O cliente atingiu o limite de registros.",
    "key_taken": "Já existe um agente com essa chave.",
    "slug_taken": "Já existe um item com esse identificador.",
    "kind_immutable": "O tipo do agente não pode ser alterado depois de criado.",
    "definition_not_platform": "A definição precisa ser da plataforma.",
    "definition_invalid": "A definição não corresponde ao agente da plataforma com essa chave.",
    "definition_not_granted": "Esta organização não tem acesso a essa definição de agente.",
    "scope_immutable": "O escopo da definição não pode ser alterado.",
    "learning_content_immutable": "O conteúdo de um aprendizado já registrado não pode ser alterado.",
    "gerador_ja_existe": "Já existe outra definição marcada como gerador de agentes.",
    "geracao_em_andamento": "Já há uma geração com IA em andamento para este agente. Aguarde ela terminar.",
    "run_not_cancellable": "Esta execução não pode mais ser cancelada.",
    "case_in_use": "Este caso já tem resultados; desative-o em vez de excluir.",
    "grant_exists": "Esse acesso já foi concedido.",
    "channel_exists": "Esse canal já está cadastrado.",
    "inbound_exists": "Essa entrada já está cadastrada.",
    "lead_ref_exists": "Essa referência de lead já está cadastrada.",
    "participante_exists": "Essa pessoa já participa da conversa.",
    "participante_estado_mudou": "A participação mudou enquanto você editava. Recarregue e tente de novo.",
    "estado_concorrente": "Outra rodada de avaliação atualizou este caso ao mesmo tempo. Recarregue para ver o estado atual.",
    "pai_invalido": "O modelo de origem escolhido não é válido para este agente (precisa ser um modelo da mesma organização, sem ciclo).",
    "pai_nao_publicado": "O modelo de origem deste agente ainda não tem versão publicada. Publique o modelo primeiro.",
    "pai_desatualizado": "O modelo de origem mudou desde a avaliação. Publique o modelo e avalie este agente de novo.",
    "outro_agente_ativo": "Outro agente já está ativo neste canal.",
    "editorial_unlinked": "O documento está fora do fluxo editorial desta coleção; coloque a coleção sob revisão de novo.",
    "editorial_archived": "O documento está arquivado e não aceita nova versão.",
    "editorial_actor_required": "Colocar uma coleção sob revisão exige um usuário autenticado.",
    "cannot_ungovern": "Uma coleção sob revisão editorial não volta a ser livre.",
    "editorial_governed": "O documento está sob revisão editorial: altere-o pelo fluxo editorial (nova versão, revisão, publicação).",
    "editorial_in_review": "O documento está em revisão: devolva-o a rascunho ou aguarde a revisão antes de enviar nova versão.",
    "slug_in_other_collection": "Já existe um documento com esse identificador em outra coleção.",
    "publicado": "O agente tem versão publicada e não pode ser excluído.",
    "tem_instancias": "O agente tem instâncias em organizações e não pode ser excluído.",
    "tem_conversas": "O agente tem conversas e não pode ser excluído.",
    "tem_canal": "O agente está ligado a um canal e não pode ser excluído.",
    "ativo": "Desligue o agente antes de excluí-lo.",
    "origem_invalida": "A origem não é um agente de código desta organização.",
    "destino_invalido": "O destino não é um agente do Studio desta organização.",
    "mesmo_agente": "Origem e destino são o mesmo agente.",
    "historico_pendente": "O agente ainda tem conversas — transfira o histórico antes de arquivar.",
}

MENSAGEM_CONFLITO_GENERICA = "A operação conflita com o estado atual. Recarregue a página e tente de novo."


def mensagem_conflito(exc: StudioConflict) -> str:
    """The pt-BR text for a 409 — by ``exc.code``; never ``str(exc)`` (DB text / internal prose)."""
    return MENSAGENS_CONFLITO.get(exc.code, MENSAGEM_CONFLITO_GENERICA)


def erro_de_item(exc: Exception) -> str:
    """The per-item error text of a batch reply: a conflict reads its pt-BR catalog text; a ``ValueError`` (a size
    cap / allowlist / field rule, already written for the caller) keeps its own message."""
    return mensagem_conflito(exc) if isinstance(exc, StudioConflict) else str(exc)


def _conflict(code: str) -> Callable[[str], Exception]:
    return lambda msg: StudioConflict(code, msg)


#: Machine codes raised by the 012/013 functions/triggers.
_P0001_CODES: dict[str, Callable[[str], Exception]] = {
    "version_immutable": VersionImmutable,
    "compiled_prompt_immutable": _conflict("compiled_prompt_immutable"),
    "audit_log_append_only": _conflict("audit_log_append_only"),
    "draft_exists": _conflict("draft_exists"),
    "draft_changed": _conflict("draft_changed"),
    "conflito_de_versao": _conflict("conflito_de_versao"),
    "eval_required": _conflict("eval_required"),
    "mecanismo_required": _conflict("mecanismo_required"),
    "chave_conflict": _conflict("chave_conflict"),
    "skill_exists": _conflict("skill_exists"),
    "client_entries_cap": _conflict("client_entries_cap"),
    "kind_immutable": _conflict("kind_immutable"),
    # 087 guard_eval_um_por_usuario (the race backstop of the one-run-per-user rule)
    "execucao_em_andamento": _conflict("execucao_em_andamento"),
    "loop_ativo_do_usuario": _conflict("loop_ativo_do_usuario"),
    # 031 guard_agent_definition_scope
    "definition_not_platform": _conflict("definition_not_platform"),
    "definition_invalid": _conflict("definition_invalid"),
    "scope_immutable": _conflict("scope_immutable"),
    "learning_content_immutable": _conflict("learning_content_immutable"),
    # 048 agents.excluir_agente guards (the SQL text is distinct; the 409 code is the bare one).
    "excluir_agente_publicado": _conflict("publicado"),
    "excluir_agente_tem_instancias": _conflict("tem_instancias"),
    "excluir_agente_tem_conversas": _conflict("tem_conversas"),
    "excluir_agente_tem_canal": _conflict("tem_canal"),
    "excluir_agente_ativo": _conflict("ativo"),
    "version_not_found": NotFound,
    "agent_not_found": NotFound,
    "participante_not_found": NotFound,
    "participante_estado_mudou": _conflict("participante_estado_mudou"),
    # 073 agent layers
    "pai_invalido": _conflict("pai_invalido"),
    "pai_nao_publicado": _conflict("pai_nao_publicado"),
    "pai_desatualizado": _conflict("pai_desatualizado"),
    "eval_case_not_found": NotFound,
    "no_eval_cases": ValueError,
    "too_many_cases": ValueError,
    "query_too_long": ValueError,
    "invalid_payload": ValueError,
    "client_required": ValueError,
    # 053 Renata cutover (agents.transferir_historico_agente / agents.arquivar_agente_legado)
    "transferir_origem_invalida": _conflict("origem_invalida"),
    "transferir_destino_invalido": _conflict("destino_invalido"),
    "transferir_mesmo_agente": _conflict("mesmo_agente"),
    "arquivar_historico_pendente": _conflict("historico_pendente"),
}


def _error_text(exc: Exception) -> tuple[str | None, str]:
    code = getattr(exc, "code", None)
    msg = getattr(exc, "message", None) or str(exc)
    return code, msg


def map_db_error(
    exc: Exception, *, unique_code: str | None = None, fk_code: str | None = None,
) -> Exception:
    """The typed error for ``exc`` — or ``exc`` itself when it is not one
    of the recognised shapes (the caller re-raises it unchanged)."""
    code, msg = _error_text(exc)
    text = msg.strip()
    factory = _P0001_CODES.get(text)
    if factory is None:
        for machine_code, candidate in _P0001_CODES.items():
            if machine_code in text:
                factory = candidate
                break
    if factory is not None:
        return factory(text)
    # The DB text (constraint/index names) stays on the chained cause for the logs; the conflict carries the code.
    if code == "23505" and unique_code is not None:
        return StudioConflict(unique_code)
    if code == "23503" and fk_code is not None:
        return StudioConflict(fk_code)
    if code == "23514":
        return ValueError(msg)
    return exc


def exec_query(query: Any, *, unique_code: str | None = None, fk_code: str | None = None):
    """``query.execute()`` with :func:`map_db_error` applied."""
    try:
        return query.execute()
    except Exception as exc:
        mapped = map_db_error(exc, unique_code=unique_code, fk_code=fk_code)
        if mapped is exc:
            raise
        raise mapped from exc


def exec_rpc(
    client: Any, schema: str, fn: str, params: dict[str, Any], *,
    unique_code: str | None = None, fk_code: str | None = None,
):
    """``client.schema(schema).rpc(fn, params).execute()`` with
    :func:`map_db_error` applied (one RPC = one Postgres transaction)."""
    return exec_query(client.schema(schema).rpc(fn, params), unique_code=unique_code, fk_code=fk_code)
