"""Per-turn wiring of the onboarding interviewer: ports in, ``(spec, ctx) -> McpSdkServerConfig`` out.

Everything the tools act on is taken from the SERVER-built turn context: the staff org + conversation id select the
session (``agents.onboarding_sessoes``), the session names the client org, the client agent and the grant. The model
supplies none of those. The apply re-resolves the live grant on every call.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from noctusai_lib.api.auth.session import AuthContext

from app.onboarding.entrevista import Entrevista, Fala
from app.onboarding.servico import aplicar_na_org, valores_armazenados
from app.onboarding.sw_settings import SwSettingsPort

__all__ = ["entrevista_da_conversa", "make_onboarding_tools_factory"]

#: A conversation's messages are read newest-last up to this many: an interview is dozens of turns, not thousands.
MAX_MENSAGENS = 500


class _Leitura:
    """The target org's declared spec keys + stored values, read once per tool call (a fresh :class:`Entrevista` per call)."""

    def __init__(self, ler: Callable[[], Any]) -> None:
        self._ler, self._v = ler, None

    def _get(self):
        if self._v is None:
            self._v = self._ler()
        return self._v

    def declaradas(self) -> dict[str, str]:
        return {d.chave: d.tipo for d in self._get().declaradas}

    def armazenados(self) -> dict[str, str]:
        return valores_armazenados(self._get())


def entrevista_da_conversa(
    *, org_id, conversation_id, requested_by, store, messages, definitions, grants, sw: SwSettingsPort,
    config_fn: Callable[[], Any],
) -> Entrevista | None:
    """The interview of a conversation, or ``None`` when it has no onboarding session."""
    from app.routers.studio_conteudo_router import ler_org_specs

    sessao = store.sessao_da_conversa(org_id, conversation_id)
    if sessao is None:
        return None
    alvo = AuthContext(
        org_id=sessao.alvo_org_id, caller_kind="user", user_id=requested_by, scopes=[], raw_token="onboarding", api_token_id=None,
    )
    config = config_fn()
    leitura = _Leitura(lambda: ler_org_specs(definitions, alvo, sessao.agent_key, config))

    def falas() -> list[Fala]:
        return [Fala(m.texto, m.created_at) for m in messages.list(org_id, conversation_id, limite=MAX_MENSAGENS) if m.role == "user"]

    return Entrevista(
        sessao=sessao, store=store, falas=falas, declaradas=leitura.declaradas, armazenados=leitura.armazenados, config=config,
        actor_id=None,
        aplicar_fn=lambda respostas: aplicar_na_org(
            store=definitions, grants=grants, ctx=alvo, key=sessao.agent_key, product=sessao.product,
            org_id=sessao.alvo_org_id, respostas=respostas, config=config, sw=sw,
            origem_extra={"sessao_onboarding": str(sessao.id)},
        ),
    )


def make_onboarding_tools_factory(
    *, store, messages, definitions, grants, sw_fn: Callable[[Any, Any], SwSettingsPort], config_fn: Callable[[], Any],
):
    """``(spec, ctx) -> McpSdkServerConfig`` for the ``onboarding`` tool group of one studio turn.

    ``sw_fn(org_id, ator)`` builds the social-wiring settings port bound to who is acting, per turn (the turn's org
    and requester, the binding the onboarding router uses); the runtime has no actor when it is built."""

    def _factory(spec: Any, ctx: Any) -> Any:
        from app.onboarding.ferramentas import build_onboarding_tools
        from app.runtime.claude_runtime import pares_do_grupo
        from app.studio.ferramentas_registry import GRUPOS_FERRAMENTAS

        grupo = GRUPOS_FERRAMENTAS["onboarding"]
        sw = sw_fn(ctx.org_id, ctx.requested_by)
        descricoes = {grupo.nome_curto(f): d for f, d in pares_do_grupo(spec, "onboarding")}
        return build_onboarding_tools(
            lambda: entrevista_da_conversa(
                org_id=ctx.org_id, conversation_id=ctx.conversation_id, requested_by=ctx.requested_by, store=store,
                messages=messages, definitions=definitions, grants=grants, sw=sw, config_fn=config_fn),
            descricoes,
        )

    return _factory
