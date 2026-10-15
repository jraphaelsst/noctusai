"""Org-level Favorecidos registry (migration 251) + the card-side SELECTION.

A favorecido (who a parcela's money is owed to) is registered ONCE per org here;
a card only SELECTS it (`selecionar_para_card`), which links an
`atendimento_favorecidos` row to the registry entry. The card reader
(`negociacao_estruturada_service._sobrepor_registro`) then reads the registry's
CURRENT values — reference, not snapshot; a generated contract version already
persists its rendered text.

🔴 LGPD — FINANCIAL PII + PERSONAL DATA
----------------------------------------
CPF/CNPJ, bank account, PIX key of a named person.
- RLS org-scoped (migration 251); every query here is `org_id`-filtered too.
- NOTHING in this module logs a payee value — only ids and counts.
- LIST responses are MASKED (`cpf_cnpj_mascarado`, `pix_mascarado`, conta last
  two digits). The FULL record is served only to a WRITE role (every org role
  except `viewer`, resolved from the TRUSTED `noctus_users` row — never the
  spoofable JWT metadata); a read-only caller gets the masked record.
- Writes are role-gated (403) and stamped `created_por` / `updated_por`.
  There is no per-read audit table for this registry: SW's only access-log seam
  (`*_documento_acessos`) is document-specific, so inventing a parallel one was
  deferred — NOC-REMEDIATE[favorecidos-read-audit]: audit full-record reads
  through the seed audit sink — 2026-10-13.
- DELETE is soft (`ativo=false`): cards already referencing the entry keep it.

Validation (a WRONG value is refused, a missing one is never invented):
CPF/CNPJ check digits are verified (never computed); conta OR pix is required;
banco + agência are required when there is a conta.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session import resolve_org_role_for
from noctusai_lib.integrations.documents import cnpj, cpf
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import negociacao_estruturada_service as estruturada
from app.modules.card_hub.banco_texto import (
    banco_saneado,
    banco_tem_dados_de_conta,
    com_banco_separado,
)
from app.services import identificadores as idf
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = estruturada.TABLE_REGISTRO_FAVORECIDOS
TABLE_CARD = estruturada.TABLE_FAVORECIDOS
TABLE_INTERMEDIARIOS = estruturada.TABLE_INTERMEDIARIOS

TIPOS_PESSOA = ("PF", "PJ")
TIPOS_CONTA = ("corrente", "poupanca", "pagamento")
TIPOS_PIX = ("cpf", "cnpj", "email", "telefone", "aleatoria")

#: Roles that may NOT write the registry nor read a full record. Everything
#: else in `ORG_ROLES` (owner/admin/manager/member/corretor/juridico/dev/test)
#: is a write role; an unresolvable role (None) fails closed.
READ_ONLY_ROLES = frozenset({"viewer"})

CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "nome", "tipo_pessoa", "cpf_cnpj", "banco", "agencia", "conta",
    "tipo_conta", "pix_tipo", "pix", "corretor_id",
)


# ─── role gate ────────────────────────────────────────────────────────────


def tem_papel_de_escrita(core_client: Any, auth: Any, request: Any = None) -> bool:
    """B3: the role is the caller's IN the request's selected org (`auth` = the `(user, token, org_id)`
    tuple), never the home-org role."""
    role = resolve_org_role_for(core_client, auth, request)
    return role is not None and role not in READ_ONLY_ROLES


def exigir_escrita(core_client: Any, auth: Any, request: Any = None) -> None:
    if not tem_papel_de_escrita(core_client, auth, request):
        raise ForbiddenError("Seu perfil não pode alterar o cadastro de favorecidos.")


# ─── masking ──────────────────────────────────────────────────────────────


def _alnum(valor: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(valor or "")).upper()


def mascarar_documento(valor: Any) -> Optional[str]:
    """`***.456.789-**` (CPF) / `**.***.789/0001-**` (CNPJ); `None` for a blank
    or a value that is neither (never echoed back)."""
    d = _alnum(valor)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"**.***.{d[5:8]}/{d[8:12]}-**"
    return None


def mascarar_conta(valor: Any) -> Optional[str]:
    d = _alnum(valor)
    if not d:
        return None
    return "*" * max(len(d) - 2, 0) + d[-2:]


def mascarar_pix(valor: Any, pix_tipo: Optional[str]) -> Optional[str]:
    texto = str(valor or "").strip()
    if not texto:
        return None
    if pix_tipo in ("cpf", "cnpj"):
        return mascarar_documento(texto) or _ocultar_meio(texto)
    if pix_tipo == "email" and "@" in texto:
        local, _, dominio = texto.partition("@")
        return f"{local[:1]}***@{dominio}"
    return _ocultar_meio(texto)


def _ocultar_meio(texto: str) -> str:
    if len(texto) <= 4:
        return "*" * len(texto)
    return texto[:2] + "*" * (len(texto) - 4) + texto[-2:]


# ─── output shapes ────────────────────────────────────────────────────────


def _saida_lista(row: dict) -> dict:
    """The LIST item — masked, never a full document/account/key."""
    return {
        "id": row["id"],
        "nome": row["nome"],
        "tipo_pessoa": row.get("tipo_pessoa"),
        "cpf_cnpj_mascarado": mascarar_documento(row.get("cpf_cnpj")),
        "banco": banco_saneado(row.get("banco")),
        "banco_requer_revisao": banco_tem_dados_de_conta(row.get("banco")),
        "pix_tipo": row.get("pix_tipo"),
        "pix_mascarado": mascarar_pix(row.get("pix"), row.get("pix_tipo")),
        "ativo": bool(row.get("ativo", True)),
    }


def _saida_completa(row: dict) -> dict:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "tipo_pessoa": row.get("tipo_pessoa"),
        "cpf_cnpj": row.get("cpf_cnpj"),
        "banco": row.get("banco"),
        "agencia": row.get("agencia"),
        "conta": row.get("conta"),
        "tipo_conta": row.get("tipo_conta"),
        "pix_tipo": row.get("pix_tipo"),
        "pix": row.get("pix"),
        "corretor_id": row.get("corretor_id"),
        "ativo": bool(row.get("ativo", True)),
        "mascarado": False,
        "created_at": row.get("created_at"),
        "created_por": row.get("created_por"),
        "updated_at": row.get("updated_at"),
        "updated_por": row.get("updated_por"),
    }


def _saida_detalhe_mascarada(row: dict) -> dict:
    """The detail shape for a read-only caller: same keys, sensitive values
    masked (the account number keeps its last two digits)."""
    return {
        **_saida_completa(row),
        "cpf_cnpj": mascarar_documento(row.get("cpf_cnpj")),
        "conta": mascarar_conta(row.get("conta")),
        "agencia": None,
        "banco": banco_saneado(row.get("banco")),
        "banco_requer_revisao": banco_tem_dados_de_conta(row.get("banco")),
        "pix": mascarar_pix(row.get("pix"), row.get("pix_tipo")),
        "cpf_cnpj_mascarado": mascarar_documento(row.get("cpf_cnpj")),
        "pix_mascarado": mascarar_pix(row.get("pix"), row.get("pix_tipo")),
        "mascarado": True,
    }


# ─── validation ───────────────────────────────────────────────────────────


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _validar_documento(bruto: Optional[str]) -> Optional[tuple[str, str]]:
    """`(canonical form, 'PF'|'PJ')` or a named 400. Check digits are VERIFIED,
    never computed."""
    if not bruto:
        return None
    s = cnpj.normalize(bruto)
    if len(s) == 11 and s.isdigit():
        if not cpf.is_valid(s):
            raise ValidationError_(
                "CPF inválido: os dígitos verificadores não conferem", field="cpf_cnpj"
            )
        return idf.canonico_cpf_cnpj(s) or s, "PF"
    if len(s) == 14:
        if not cnpj.is_valid(s):
            raise ValidationError_(
                "CNPJ inválido: os dígitos verificadores não conferem", field="cpf_cnpj"
            )
        return idf.canonico_cpf_cnpj(s) or s, "PJ"
    raise ValidationError_(
        "cpf_cnpj deve ser um CPF (11 dígitos) ou um CNPJ (14 caracteres)",
        field="cpf_cnpj",
    )


def _normalizar(valores: dict, *, atual: Optional[dict] = None) -> dict:
    """The row to write: `valores` over `atual`, validated as a WHOLE (a PATCH
    that clears the conta must still leave a pix, etc.)."""
    mesclado = {c: (atual or {}).get(c) for c in CAMPOS_EDITAVEIS}
    for c in CAMPOS_EDITAVEIS:
        if c in valores:
            mesclado[c] = valores[c]
    for c in ("nome", "cpf_cnpj", "banco", "agencia", "conta", "pix"):
        mesclado[c] = _texto(mesclado.get(c))

    if not mesclado["nome"]:
        raise ValidationError_("nome é obrigatório", field="nome")

    doc = _validar_documento(mesclado["cpf_cnpj"])
    if doc:
        mesclado["cpf_cnpj"], tipo_doc = doc
        if mesclado.get("tipo_pessoa") and mesclado["tipo_pessoa"] != tipo_doc:
            raise ValidationError_(
                f"tipo_pessoa {mesclado['tipo_pessoa']} não confere com o documento "
                f"informado ({'CPF' if tipo_doc == 'PF' else 'CNPJ'})",
                field="tipo_pessoa",
            )
        mesclado["tipo_pessoa"] = tipo_doc
    if mesclado.get("tipo_pessoa") not in TIPOS_PESSOA:
        raise ValidationError_("tipo_pessoa deve ser PF ou PJ", field="tipo_pessoa")

    for campo, validos in (("tipo_conta", TIPOS_CONTA), ("pix_tipo", TIPOS_PIX)):
        if mesclado.get(campo) is not None and mesclado[campo] not in validos:
            raise ValidationError_(
                f"{campo} deve ser um de: {', '.join(validos)}", field=campo
            )

    mesclado = com_banco_separado(mesclado)
    if banco_tem_dados_de_conta(mesclado["banco"]):
        raise ValidationError_(
            "O campo Banco deve conter apenas o nome do banco; "
            "informe a agência e a conta nos campos Agência e Conta",
            field="banco",
        )
    if not mesclado["conta"] and not mesclado["pix"]:
        raise ValidationError_("informe a conta bancária ou a chave PIX", field="conta")
    if mesclado["conta"] and not (mesclado["banco"] and mesclado["agencia"]):
        raise ValidationError_(
            "banco e agência são obrigatórios quando há conta", field="banco"
        )
    if mesclado["pix"] and not mesclado.get("pix_tipo"):
        raise ValidationError_("informe o tipo da chave PIX", field="pix_tipo")
    if not mesclado["pix"]:
        mesclado["pix_tipo"] = None
    if mesclado.get("corretor_id") is not None:
        mesclado["corretor_id"] = str(mesclado["corretor_id"])
    return mesclado


# ─── reads ────────────────────────────────────────────────────────────────


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _linhas(client: Any, org_id: UUID) -> list[dict]:
    return table_reads.paged_rows(client, TABLE, org_id)


def _exigir(client: Any, org_id: UUID, favorecido_id: UUID) -> dict:
    rows = (
        _t(client, TABLE).select("*")
        .eq("org_id", str(org_id)).eq("id", str(favorecido_id)).execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE, str(favorecido_id))
    return rows[0]


def listar(
    client: Any, org_id: UUID, *, q: Optional[str] = None, ativo: Optional[bool] = None
) -> dict:
    rows = _linhas(client, org_id)
    if ativo is not None:
        rows = [r for r in rows if bool(r.get("ativo", True)) is ativo]
    termo = _texto(q)
    if termo:
        t = termo.lower()
        digitos = _alnum(termo)
        rows = [
            r for r in rows
            if t in str(r.get("nome") or "").lower()
            or (len(digitos) >= 3 and digitos in _alnum(r.get("cpf_cnpj")))
        ]
    rows.sort(key=lambda r: str(r.get("nome") or "").lower())
    return {"items": [_saida_lista(r) for r in rows]}


def obter(client: Any, org_id: UUID, favorecido_id: UUID, *, completo: bool) -> dict:
    row = _exigir(client, org_id, favorecido_id)
    return _saida_completa(row) if completo else _saida_detalhe_mascarada(row)


# ─── writes ───────────────────────────────────────────────────────────────


def _exigir_documento_livre(
    client: Any, org_id: UUID, cpf_cnpj: Optional[str], *, exceto: Optional[str] = None
) -> None:
    chave = _alnum(cpf_cnpj)
    if not chave:
        return
    for r in _linhas(client, org_id):
        if (
            r.get("ativo", True)
            and str(r["id"]) != exceto
            and _alnum(r.get("cpf_cnpj")) == chave
        ):
            raise ConflictError(
                "já existe um favorecido ativo com este CPF/CNPJ", resource=TABLE
            )


def criar(
    client: Any, org_id: UUID, *, valores: dict, usuario_id: Optional[UUID]
) -> dict:
    novo = _normalizar(valores)
    _exigir_documento_livre(client, org_id, novo["cpf_cnpj"])
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        **{c: novo[c] for c in CAMPOS_EDITAVEIS},
        "ativo": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE).insert(row).execute()
    logger.info("favorecido created id=%s org=%s", row["id"], org_id)
    return _saida_completa(row)


def atualizar(
    client: Any, org_id: UUID, favorecido_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atual = _exigir(client, org_id, favorecido_id)
    novo = _normalizar(valores, atual=atual)
    if atual.get("ativo", True) or valores.get("ativo"):
        _exigir_documento_livre(
            client, org_id, novo["cpf_cnpj"], exceto=str(favorecido_id)
        )
    patch = {c: novo[c] for c in CAMPOS_EDITAVEIS}
    if "ativo" in valores and valores["ativo"] is not None:
        patch["ativo"] = bool(valores["ativo"])
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    patch["updated_por"] = str(usuario_id) if usuario_id else None
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(favorecido_id)
    ).execute()
    logger.info("favorecido updated id=%s org=%s", favorecido_id, org_id)
    return _saida_completa({**atual, **patch})


def desativar(
    client: Any, org_id: UUID, favorecido_id: UUID, *, usuario_id: Optional[UUID]
) -> None:
    """Soft delete — cards that already reference the entry keep reading it."""
    _exigir(client, org_id, favorecido_id)
    _t(client, TABLE).update({
        "ativo": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_por": str(usuario_id) if usuario_id else None,
    }).eq("org_id", str(org_id)).eq("id", str(favorecido_id)).execute()
    logger.info("favorecido deactivated id=%s org=%s", favorecido_id, org_id)


# ─── card side: SELECT from the registry ──────────────────────────────────


def selecionar_para_card(
    client: Any, org_id: UUID, atendimento_id: UUID, *, favorecido_id: UUID,
    intermediario_id: Optional[UUID], usuario_id: Optional[UUID],
) -> dict:
    """Link a registry entry to the card (idempotent: one card row per entry per
    atendimento) and, when `intermediario_id` is given, to that intermediário.
    The card row's own columns are filled from the registry as the fallback copy
    (`_sobrepor_registro` makes the registry win at read time). An INACTIVE
    entry cannot be newly selected (409). Returns the LINKED card row
    (`atendimento_favorecidos`, the id parcelas/intermediários reference)."""
    if not (
        _t(client, "atendimentos").select("id")
        .eq("org_id", str(org_id)).eq("id", str(atendimento_id)).execute()
    ).data:
        raise NotFoundError("atendimentos", str(atendimento_id))
    reg = _exigir(client, org_id, favorecido_id)

    existentes = (
        _t(client, TABLE_CARD).select("*")
        .eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id))
        .eq("favorecido_id", str(favorecido_id)).execute()
    ).data or []
    if existentes:
        card_id = existentes[0]["id"]
    else:
        if not reg.get("ativo", True):
            raise ConflictError("este favorecido está inativo no cadastro", resource=TABLE)
        card_id = str(uuid4())
        _t(client, TABLE_CARD).insert({
            "id": card_id,
            "org_id": str(org_id),
            "atendimento_id": str(atendimento_id),
            "favorecido_id": str(favorecido_id),
            **{c: reg.get(c) for c in estruturada._CAMPOS_DO_REGISTRO},
            "origem": "manual",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_por": str(usuario_id) if usuario_id else None,
        }).execute()

    if intermediario_id is not None:
        achados = (
            _t(client, TABLE_INTERMEDIARIOS).select("id")
            .eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id))
            .eq("id", str(intermediario_id)).execute()
        ).data or []
        if not achados:
            raise NotFoundError(TABLE_INTERMEDIARIOS, str(intermediario_id))
        _t(client, TABLE_INTERMEDIARIOS).update({
            "favorecido_id": str(card_id),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_por": str(usuario_id) if usuario_id else None,
        }).eq("org_id", str(org_id)).eq("id", str(intermediario_id)).execute()

    logger.info(
        "favorecido selected registry=%s atendimento=%s org=%s",
        favorecido_id, atendimento_id, org_id,
    )
    linha = (
        _t(client, TABLE_CARD).select("*")
        .eq("org_id", str(org_id)).eq("id", str(card_id)).execute()
    ).data[0]
    return estruturada._favorecido_out(estruturada._sobrepor_registro(client, org_id, [linha])[0])
