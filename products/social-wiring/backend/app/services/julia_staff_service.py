"""The org STAFF list -- who is staff on the org's WhatsApp lines (owner decision 2026-10-21).

"staff will be set in-org. only those registered on the sw are staff and their roles ... by default, if not in the staff
list, it's an incoming lead." This module is the ONE place that decides it. It replaces the per-connection
`authorized_numbers` as the thing people EDIT: before this there were three overlapping lists (the connection's
`authorized_numbers`, the Julia teams' members, the org users), none of them a "this number is our colleague" registry.

The list (`julia_staff`, migration 298): one row per WhatsApp number (a person with two numbers has two rows), with the
person's name, their SW user when they have one, and a ROLE:

  admin, operador   -> the One Chat OPERATOR path (they may drive the operator agent from their own number)
  corretor, atendente, outro
                    -> staff, but NOT operators: a message from them on Julia's public line is never a lead and never an
                       operator command; it is stored, logged (ids only) and the org's admins get one notice an hour.

`whatsapp_connections.authorized_numbers` stays as the column the One Chat intake reads (and migration 258's CHECK guards),
but it is now a MIRROR of the staff list: `espelhar_conexoes` writes the active operator numbers into it after every staff
write, preserving only the entries that are not phones (a LID literal, which has no phone to register). Nothing edits that
column by hand any more (the connection PATCH goes through `sincronizar_de_lista`).

Text never confers staff identity: staff is decided by the sender's number only, against this table.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

T = "julia_staff"
T_CONEXOES = "whatsapp_connections"
PAPEIS = ("admin", "operador", "corretor", "atendente", "outro")
#: Roles that may drive the One Chat operator agent from their number.
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


# ── the mirror: authorized_numbers <- active operator numbers ───────────────
def numeros_operadores(client: Any, org_id: UUID | str) -> list[str]:
    rows = client.table(T).select("telefone, papel, ativo").eq("org_id", str(org_id)).eq("ativo", True).execute().data or []
    return sorted({f"+{r['telefone']}" for r in rows if r.get("telefone") and e_operador(r.get("papel"))})


def lista_espelhada(atual: Iterable[Any], operadores: list[str]) -> list[str]:
    """The connection's new `authorized_numbers`: the operator phones plus every entry of the old list that is NOT a phone."""
    preservados = [str(n) for n in atual if str(n).strip() and normalizar_telefone(n) is None]
    return operadores + [p for p in preservados if p not in operadores]


def _conexoes_da_org(client: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    return client.table(T_CONEXOES).select("id, authorized_numbers, agente_leads_ativo").eq("org_id", str(org_id)).execute().data or []


def exigir_que_a_julia_continue_autorizada(client: Any, org_id: UUID | str, operadores: list[str]) -> None:
    """Migration 258's invariant (Julia on => at least one authorized number), checked BEFORE a write so the answer is a clear 409
    instead of a CHECK violation after the staff row already changed."""
    for c in _conexoes_da_org(client, org_id):
        if c.get("agente_leads_ativo") and not lista_espelhada(c.get("authorized_numbers") or [], operadores):
            raise AppException(
                "ultimo_operador",
                "A Julia está ligada em uma linha desta organização e precisa de ao menos um operador (admin ou operador) com WhatsApp.",
                status_code=409,
            )


def espelhar_conexoes(client: Any, org_id: UUID | str) -> dict[str, list[str]]:
    """Write the active operator numbers into every connection's `authorized_numbers` (idempotent). Returns `{connection_id: list}`."""
    operadores = numeros_operadores(client, org_id)
    out: dict[str, list[str]] = {}
    for c in _conexoes_da_org(client, org_id):
        nova = lista_espelhada(c.get("authorized_numbers") or [], operadores)
        out[str(c["id"])] = nova
        if nova != list(c.get("authorized_numbers") or []):
            client.table(T_CONEXOES).update({"authorized_numbers": nova, "updated_at": _agora()}).eq("id", str(c["id"])).eq("org_id", str(org_id)).execute()
    return out


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
    if e_operador(papel):
        espelhar_conexoes(client, org_id)
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
    afeta_operadores = e_operador(atual.get("papel")) or e_operador(novo.get("papel"))
    if afeta_operadores:  # validate the resulting operator set before touching the row
        futuros = [r for r in listar(client, org_id) if str(r["id"]) != str(staff_id)] + [novo]
        ops = sorted({f"+{r['telefone']}" for r in futuros if r.get("ativo") and r.get("telefone") and e_operador(r.get("papel"))})
        exigir_que_a_julia_continue_autorizada(client, org_id, ops)
    client.table(T).update({**patch, "updated_at": _agora()}).eq("id", str(staff_id)).eq("org_id", str(org_id)).execute()
    if afeta_operadores:
        espelhar_conexoes(client, org_id)
    return novo


def remover(client: Any, org_id: UUID | str, staff_id: UUID | str) -> None:
    """A removed person stops being staff at once (their next message is a lead)."""
    atual = _linha(client, org_id, staff_id)
    if e_operador(atual.get("papel")) and atual.get("ativo"):
        restantes = [r for r in listar(client, org_id) if str(r["id"]) != str(staff_id)]
        ops = sorted({f"+{r['telefone']}" for r in restantes if r.get("ativo") and r.get("telefone") and e_operador(r.get("papel"))})
        exigir_que_a_julia_continue_autorizada(client, org_id, ops)
    client.table(T).delete().eq("id", str(staff_id)).eq("org_id", str(org_id)).execute()
    if e_operador(atual.get("papel")):
        espelhar_conexoes(client, org_id)


def sincronizar_de_lista(client: Any, core: Any, org_id: UUID | str, ator_user_id: str, numeros: Iterable[Any]) -> dict[str, list[str]]:
    """The connection PATCH's `authorized_numbers`, redirected into the staff list: every PHONE in `numeros` becomes (or stays) an
    active operator; an active operator-role number that is not in `numeros` is deactivated. Non-phone entries (LID literals) are
    left to the mirror. Returns `{connection_id: authorized_numbers}` after the mirror."""
    pedidos = []
    for n in numeros:
        d = normalizar_telefone(n)
        if d and d not in pedidos:
            pedidos.append(d)
    atuais = {r["telefone"]: r for r in listar(client, org_id) if r.get("telefone")}
    ops_futuros = sorted({f"+{d}" for d in pedidos})
    exigir_que_a_julia_continue_autorizada(client, org_id, ops_futuros)
    for d in pedidos:
        r = atuais.get(d)
        if r is None:
            if _numero_bloqueado(client, org_id, d):
                raise AppException("numero_bloqueado", "Este número está na lista de bloqueio.", status_code=409)
            client.table(T).insert({
                "id": str(uuid4()), "org_id": str(org_id), "nome": f"Operador (final {d[-4:]})", "papel": "operador", "telefone": d,
                "ativo": True, "criado_por": str(ator_user_id),
            }).execute()
        elif not r.get("ativo") or not e_operador(r.get("papel")):
            client.table(T).update({"ativo": True, "papel": r["papel"] if e_operador(r.get("papel")) else "operador", "updated_at": _agora()}).eq("id", str(r["id"])).execute()
    for d, r in atuais.items():
        if d not in pedidos and r.get("ativo") and e_operador(r.get("papel")):
            client.table(T).update({"ativo": False, "updated_at": _agora()}).eq("id", str(r["id"])).execute()
    return espelhar_conexoes(client, org_id)


__all__ = [
    "PAPEIS", "PAPEIS_OPERADOR", "atualizar", "autor_de_usuario", "buscar_por_telefone", "criar", "e_operador", "espelhar_conexoes", "existe_staff_com_telefone",
    "formas_do_remetente", "lista_espelhada", "listar", "normalizar_telefone", "numeros_operadores", "remover", "sincronizar_de_lista",
]
