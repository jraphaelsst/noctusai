"""The org STAFF list -- who is staff on the org's WhatsApp line (owner decision 2026-10-21, line model 2026-11-04).

"staff will be set in-org. only those registered on the sw are staff and their roles ... by default, if not in the staff
list, it's an incoming lead." Julia's line is ONE number shared by leads and staff notifications; the "One Chat" operator bot
is retired (2026-11-04), so a role no longer grants any bot privilege -- it only names the person in notices and thread authors.

`classificar_remetente` is the ONE function that decides whether a sender is staff. Staff = the ACTIVE rows of this table
(`julia_staff`, migration 298: one row per WhatsApp number, name, optional SW user, role) UNION the phones of the members of the
line-owning org (core `noctus_users.telefone`, read through the seed `resolve_user_phones`). A staff message is stored (chat
`categoria='equipe'`), never reaches an agent, and the org admins get an in-app notice.

Text never confers staff identity: staff is decided by the sender's number only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

T = "julia_staff"
PAPEIS = ("admin", "operador", "corretor", "atendente", "outro")
#: Roles that read as "operator" in the UI (kept for the role label; the One Chat operator bot is retired, 2026-11-04).
PAPEIS_OPERADOR = ("admin", "operador")
NOME_MAX = 120
_DIGITOS = re.compile(r"^[0-9]{10,15}$")
_PAPEL_DO_ORG_ROLE = {"owner": "admin", "admin": "admin"}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── number normalisation ────────────────────────────────────────────────────
def normalizar_telefone(valor: Any) -> Optional[str]:
    """Digits of a phone (`+55 (11) 98888-7777`, `5511988887777@c.us`, ...); None when it is not a 10-15 digit phone (a LID,
    free text, empty)."""
    raw = str(valor or "").strip().lower()
    if not raw or raw.endswith("@lid") or raw.endswith("@g.us"):
        return None
    for suffix in ("@c.us", "@s.whatsapp.net"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    digitos = re.sub(r"[\s()+-]", "", raw)
    return digitos if _DIGITOS.match(digitos) else None


def formas_do_remetente(*identificadores: Any) -> list[str]:
    """Every phone-digits form a sender can be matched by (the chat id and any resolved alias)."""
    out: list[str] = []
    for i in identificadores:
        d = normalizar_telefone(i)
        if d and d not in out:
            out.append(d)
    return out


def e_operador(papel: Optional[str]) -> bool:
    return papel in PAPEIS_OPERADOR


# ── validation ──────────────────────────────────────────────────────────────
def _nome_valido(nome: Optional[str]) -> str:
    n = (nome or "").strip()
    if not 1 <= len(n) <= NOME_MAX:
        raise AppException("nome_invalido", f"O nome deve ter de 1 a {NOME_MAX} caracteres.", status_code=422)
    return n


def _papel_valido(papel: Optional[str]) -> str:
    if papel not in PAPEIS:
        raise AppException("papel_invalido", f"Papel inválido. Use: {', '.join(PAPEIS)}.", status_code=422)
    return str(papel)


def _telefone_valido(valor: Any) -> str:
    d = normalizar_telefone(valor)
    if d is None:
        raise AppException("telefone_invalido", "Informe o WhatsApp com DDI e DDD (de 10 a 15 dígitos).", status_code=422)
    return d


def _usuario_da_org(core: Any, org_id: UUID | str, user_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not user_id:
        return None
    rows = core.table("noctus_users").select("id, nome, org_id, org_role").eq("id", str(user_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("usuario_fora_da_org", "O usuário informado não pertence a esta organização.", status_code=422)
    return rows[0]


# ── reads ───────────────────────────────────────────────────────────────────
def listar(client: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    rows = client.table(T).select("*").eq("org_id", str(org_id)).execute().data or []
    return sorted(rows, key=lambda r: (str(r.get("nome") or "").lower(), str(r.get("telefone") or "")))


def buscar_por_telefone(client: Any, org_id: UUID | str, formas: Iterable[str]) -> Optional[dict[str, Any]]:
    """The ACTIVE staff row any of the phone forms belongs to; None = not staff (=> a lead)."""
    for d in formas:
        rows = client.table(T).select("*").eq("org_id", str(org_id)).eq("telefone", d).eq("ativo", True).limit(1).execute().data or []
        if rows:
            return rows[0]
    return None


def existe_staff_com_telefone(client: Any, org_id: UUID | str) -> bool:
    rows = client.table(T).select("id, telefone").eq("org_id", str(org_id)).eq("ativo", True).execute().data or []
    return any(r.get("telefone") for r in rows)


def _linha(client: Any, org_id: UUID | str, staff_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T).select("*").eq("id", str(staff_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("staff_nao_encontrado", "Registro da equipe não encontrado.", status_code=404)
    return rows[0]


def autor_de_usuario(client: Any, core: Any, org_id: UUID | str, user_id: Optional[str | UUID]) -> Optional[dict[str, Any]]:
    """The author of a human line SW appends to an agents thread: `{user_id, nome, papel}`. The staff list wins (the person's
    registered name and role); a SW user who is not in it is described by their core role (owner/admin -> `admin`, else
    `atendente`) -- they are real org users, but the staff list is what the report calls out as incomplete. None when the user is
    unknown to the org."""
    if not user_id:
        return None
    rows = client.table(T).select("*").eq("org_id", str(org_id)).eq("user_id", str(user_id)).eq("ativo", True).execute().data or []
    if rows:
        melhor = next((r for r in rows if e_operador(r.get("papel"))), rows[0])
        return {"user_id": str(user_id), "nome": melhor["nome"], "papel": melhor["papel"], "na_lista": True}
    usuarios = core.table("noctus_users").select("id, nome, org_role").eq("id", str(user_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    if not usuarios:
        return None
    u = usuarios[0]
    nome = (u.get("nome") or "").strip() or "Atendente"
    return {"user_id": str(user_id), "nome": nome[:NOME_MAX], "papel": _PAPEL_DO_ORG_ROLE.get(str(u.get("org_role")), "atendente"),
            "na_lista": False}


# ── writes ──────────────────────────────────────────────────────────────────
def _numero_bloqueado(client: Any, org_id: UUID | str, telefone: str) -> bool:
    rows = client.table("julia_numeros_bloqueados").select("id").eq("org_id", str(org_id)).eq("numero", telefone).eq("ativo", True).limit(1).execute().data or []
    return bool(rows)


def criar(
    client: Any, core: Any, org_id: UUID | str, ator_user_id: str, *, nome: str, papel: str, telefone: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    nome, papel = _nome_valido(nome), _papel_valido(papel)
    d = _telefone_valido(telefone) if telefone not in (None, "") else None
    if d is None and not user_id:
        raise AppException("identificacao_obrigatoria", "Informe o WhatsApp ou o usuário da equipe.", status_code=422)
    _usuario_da_org(core, org_id, user_id)
    if d:
        if _numero_bloqueado(client, org_id, d):
            raise AppException("numero_bloqueado", "Este número está na lista de bloqueio. Desbloqueie-o antes de cadastrá-lo na equipe.", status_code=409)
        existente = client.table(T).select("id, ativo").eq("org_id", str(org_id)).eq("telefone", d).limit(1).execute().data or []
        if existente and existente[0].get("ativo"):
            raise AppException("telefone_ja_cadastrado", "Este WhatsApp já está na equipe.", status_code=409)
        if existente:  # a deactivated entry for the same number: reactivate it rather than collide with the unique index
            return atualizar(client, core, org_id, existente[0]["id"], {"nome": nome, "papel": papel, "user_id": user_id, "ativo": True})
    linha = {
        "id": str(uuid4()), "org_id": str(org_id), "user_id": str(user_id) if user_id else None, "nome": nome, "papel": papel,
        "telefone": d, "ativo": True, "criado_por": str(ator_user_id),
    }
    res = client.table(T).insert(linha).execute().data or []
    if not res:
        raise RuntimeError("julia: staff row not stored")
    return res[0]


def atualizar(client: Any, core: Any, org_id: UUID | str, staff_id: UUID | str, campos: dict[str, Any]) -> dict[str, Any]:
    atual = _linha(client, org_id, staff_id)
    patch: dict[str, Any] = {}
    if "nome" in campos:
        patch["nome"] = _nome_valido(campos["nome"])
    if "papel" in campos:
        patch["papel"] = _papel_valido(campos["papel"])
    if "ativo" in campos:
        patch["ativo"] = bool(campos["ativo"])
    if "user_id" in campos:
        _usuario_da_org(core, org_id, campos["user_id"])
        patch["user_id"] = str(campos["user_id"]) if campos["user_id"] else None
    if "telefone" in campos and campos["telefone"] != atual.get("telefone"):
        d = _telefone_valido(campos["telefone"]) if campos["telefone"] not in (None, "") else None
        if d:
            outro = client.table(T).select("id").eq("org_id", str(org_id)).eq("telefone", d).neq("id", str(staff_id)).limit(1).execute().data or []
            if outro:
                raise AppException("telefone_ja_cadastrado", "Este WhatsApp já está na equipe.", status_code=409)
            if _numero_bloqueado(client, org_id, d):
                raise AppException("numero_bloqueado", "Este número está na lista de bloqueio.", status_code=409)
        patch["telefone"] = d
    novo = {**atual, **patch}
    if not novo.get("telefone") and not novo.get("user_id"):
        raise AppException("identificacao_obrigatoria", "Informe o WhatsApp ou o usuário da equipe.", status_code=422)
    if not patch:
        return atual
    client.table(T).update({**patch, "updated_at": _agora()}).eq("id", str(staff_id)).eq("org_id", str(org_id)).execute()
    return novo


def remover(client: Any, org_id: UUID | str, staff_id: UUID | str) -> None:
    """A removed person stops being staff at once (their next message is a lead)."""
    _linha(client, org_id, staff_id)  # 404 when it is not this org's
    client.table(T).delete().eq("id", str(staff_id)).eq("org_id", str(org_id)).execute()


@dataclass(frozen=True)
class Remetente:
    """A sender that IS staff. `origem`: `julia_staff` (a registered number) | `membro` (an active member of the line-owning org, by
    the phone in core). `chave` is stable per person (dedupes the admin notice)."""

    origem: str
    nome: str
    papel: str
    chave: str


def telefones_de_membros(core: Any, org_id: UUID | str) -> dict[str, dict[str, str]]:
    """`{phone digits: {id, nome, papel}}` for the members of the org that have a phone in core. Membership is the trusted
    `noctus_users` row (never user_metadata); the phone comes from the seed `resolve_user_phones`."""
    from noctusai_lib.integrations.persistence.table_reads import resolve_user_phones

    membros = core.table("noctus_users").select("id,nome,org_role").eq("org_id", str(org_id)).execute().data or []
    if not membros:
        return {}
    por_id = {str(m["id"]): m for m in membros}
    out: dict[str, dict[str, str]] = {}
    for uid, telefone in resolve_user_phones(core, por_id).items():
        d = normalizar_telefone(telefone)
        if d:
            m = por_id[uid]
            out[d] = {"id": uid, "nome": (m.get("nome") or "").strip()[:NOME_MAX] or "Membro",
                      "papel": _PAPEL_DO_ORG_ROLE.get(str(m.get("org_role")), "atendente")}
    return out


def existe_equipe_com_telefone(client: Any, core: Any, org_id: UUID | str) -> bool:
    """Does the org have ANY staff number at all (a LID costs a WAHA round-trip to resolve: only worth it when this is True)."""
    return existe_staff_com_telefone(client, org_id) or bool(telefones_de_membros(core, org_id))


def classificar_remetente(client: Any, core: Any, org_id: UUID | str, formas: Iterable[str]) -> Optional[Remetente]:
    """Is the sender (any of the phone-digit `formas`, see `formas_do_remetente`) staff of the org that owns the line? None = a lead.
    Staff = an active `julia_staff` row, else an active member of the org whose core phone matches. RAISES on a store failure (the
    caller decides; the webhook logs it and treats the sender as a lead -- it never guesses staff)."""
    formas = [d for d in formas if d]
    if not formas:
        return None
    linha = buscar_por_telefone(client, org_id, formas)
    if linha is not None:
        return Remetente("julia_staff", str(linha.get("nome") or "Equipe"), str(linha.get("papel") or "outro"), f"staff:{linha['id']}")
    membros = telefones_de_membros(core, org_id)
    for d in formas:
        if d in membros:
            m = membros[d]
            return Remetente("membro", m["nome"], m["papel"], f"membro:{m['id']}")
    return None


__all__ = [
    "PAPEIS", "PAPEIS_OPERADOR", "Remetente", "atualizar", "autor_de_usuario", "buscar_por_telefone", "classificar_remetente", "criar",
    "e_operador", "existe_equipe_com_telefone", "existe_staff_com_telefone", "formas_do_remetente", "listar", "normalizar_telefone",
    "remover", "telefones_de_membros",
]
