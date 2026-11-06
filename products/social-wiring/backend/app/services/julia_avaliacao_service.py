"""The testing phase on SW's side (owner 2026-11-05): "the testing phase where she only replies to me until she's validated ... only on
agents julia page, not on sw ui". The ONE testing switch is AGENTS' evaluation mode (`modo_avaliacao` + the listed users); SW has no
allowlist. Agents stays the enforcing gate (an outsider gets `restrito_avaliacao` there). SW reads the mode for one reason only:
the owner's own number is an org MEMBER's, so SW's staff filter (`equipe`) would stop it before it ever reached agents' gate.
A member who is on agents' evaluation list WHILE the mode is ON is therefore let through as a lead; every other member stays staff.

ONE switch, on Julia's CORE in the agents app (owner 2026-11-05): agents resolves the core of this company's instance and returns the
core's state on the instance's own token, so SW reads it exactly as before and every company obeys the same switch. The listed users are
NoctusAI evaluators (not members of the company): their phones are resolved from core `noctus_users.telefone` by user id.

Read shape: `GET /api/channels/agents/{key}/controle` -> `modo_avaliacao: bool`, `avaliacao_usuarios: [noctus user id]` (ids, never phones).

Testing mode is a LIVE on/off STATE (owner 2026-11-05), never a latch: it is read from agents on EVERY staff inbound and EVERY
first-contact attempt -- no cache, no "went live once" marker -- so flipping it back ON restricts Julia to the evaluation list at once.
Fail CLOSED: an unreadable controle (no client, agents down, malformed) means NO bypass -- the member stays staff / the first contact is
not sent -- and is logged at ERROR (ids only). Only a staff sender or a first-contact attempt triggers the read, so a lead's message
never costs a call (agents itself gates a lead's reply, `restrito_avaliacao`).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def ler_avaliacao(
    client: Any, org_id: UUID | str, agent_key: str,
) -> Optional[tuple[bool, frozenset[str]]]:
    """`(modo_avaliacao, listed user ids)` from agents' controle, or None when it cannot be read (logged at ERROR).
    Never raises. The two callers fail closed on None in their own way (see below)."""
    if client is None:
        logger.error("julia: agents controle unreadable org=%s (no agents client/token) -- no evaluation bypass", org_id)
        return None
    try:
        controle = await client.controle(agent_key)
    except Exception as exc:  # noqa: BLE001 -- any failure => fail closed, named in the log
        logger.error("julia: agents controle unreadable org=%s (%s) -- no evaluation bypass", org_id, type(exc).__name__)
        return None
    return bool(controle.modo_avaliacao), frozenset(controle.avaliacao_usuarios)


async def usuarios_em_avaliacao(
    client: Any, org_id: UUID | str, agent_key: str,
) -> frozenset[str]:
    """The noctus user ids agents lets through RIGHT NOW: the listed users while evaluation mode is ON, else none (also none when
    the controle is unreadable -- no bypass). Never raises."""
    lido = await ler_avaliacao(client, org_id, agent_key)
    return lido[1] if lido is not None and lido[0] else frozenset()


MOTIVO_RESTRITO = "restrito_avaliacao"
MOTIVO_INDISPONIVEL = "avaliacao_indisponivel"


async def restricao_primeiro_contato(
    client: Any, core: Any, org_id: UUID | str, agent_key: str, telefone: str,
) -> Optional[str]:
    from app.services import julia_staff_service as staff

    return await restricao_para_formas(client, core, org_id, agent_key, staff.formas_do_remetente(telefone))


async def restricao_para_formas(
    client: Any, core: Any, org_id: UUID | str, agent_key: str, formas: list[str],
) -> Optional[str]:
    """May Julia deal with a contact whose phone digits are `formas` -- an inbound message OR a first contact? None = yes.
    Used at SW's intake BEFORE agents is called: a blocked inbound is never forwarded, so agents makes no thread, turn or LLM call. Testing mode (agents' evaluation mode) ON means
    she contacts ONLY the listed numbers -> `restrito_avaliacao` for everyone else; mode OFF means no restriction. FAIL CLOSED: an
    unreadable controle, or listed users whose phones cannot be read, is `avaliacao_indisponivel` (nothing is sent)."""
    lido = await ler_avaliacao(client, org_id, agent_key)
    if lido is None:
        return MOTIVO_INDISPONIVEL
    ligado, ids = lido
    if not ligado:
        return None
    if core is None or not ids:
        if core is None:
            logger.error("julia: evaluation mode ON but no core client to read the listed phones org=%s -- first contact refused", org_id)
            return MOTIVO_INDISPONIVEL
        return MOTIVO_RESTRITO
    try:
        avaliadores = telefones_dos_avaliadores(core, ids)
    except Exception as exc:  # noqa: BLE001 -- fail closed, named in the log
        logger.error("julia: evaluation phones unreadable org=%s (%s) -- contact blocked", org_id, type(exc).__name__)
        return MOTIVO_INDISPONIVEL
    if any(forma in avaliadores for forma in formas):
        return None
    return MOTIVO_RESTRITO


def telefones_dos_avaliadores(core: Any, ids: frozenset[str]) -> frozenset[str]:
    """The phone digits of the listed evaluators, from core `noctus_users.telefone` by user id (they are NoctusAI users, so this is NOT
    scoped to the company's org). Raises on a read failure; the callers fail closed."""
    from noctusai_lib.integrations.persistence.table_reads import resolve_user_phones

    from app.services import julia_staff_service as staff

    return frozenset(d for d in (staff.normalizar_telefone(t) for t in resolve_user_phones(core, ids).values()) if d)


async def numero_em_avaliacao(client: Any, core: Any, org_id: UUID | str, agent_key: str, formas: list[str]) -> bool:
    """Is this sender (phone digits `formas`) an evaluator on agents' list WHILE testing mode is ON? Lets an evaluator past SW's own
    `equipe` filter on any company's line, and ONLY then. Unreadable state / phones => False (no bypass), logged."""
    lido = await ler_avaliacao(client, org_id, agent_key)
    if lido is None or not lido[0] or not lido[1] or core is None:
        return False
    try:
        return any(forma in telefones_dos_avaliadores(core, lido[1]) for forma in formas)
    except Exception as exc:  # noqa: BLE001 -- fail closed
        logger.error("julia: evaluation phones unreadable org=%s (%s) -- no evaluation bypass", org_id, type(exc).__name__)
        return False
