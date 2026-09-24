"""`empresas` — the row itself, its group-level D1 write policy, and the
manual/card-hub link (P0c contract §A.1/§C6/§D1-D2).

GROUP-LEVEL PROVENANCE, NOT PER-FIELD (contract §H12, accepted)
------------------------------------------------------------------
Unlike `clientes`/`imovel_dados`, every machine-read `empresas` column
(`razao_social`, `nome_fantasia`, `natureza_juridica`, `data_abertura`,
`situacao_cadastral`, `data_situacao_cadastral`, `motivo_situacao`, `uf`)
shares ONE `dados_*` provenance quintet. A Cartão CNPJ reads the whole
cadastral block off a single document in a single pass — the group IS the
unit of trust here. A DISAGREEING field still opens its OWN `empresa_campo_
conflitos` row (per field, never per group) through the shared writer
(`app.services.campo_conflitos`, contract §H6).

🔴 SCOPE CUT (owner decision, 2026-09-24, twice-confirmed): the company's
registered ADDRESS — including `uf` — is deliberately NOT modeled at all:
no columns, no write path, nothing on the API response. Every state
certidão this product issues is SP regardless of the empresa's location, so
an address would be reference-only with no process it feeds; the Receita
also masks it on a BAIXADA Cartão (5/5 real samples); and Crednet's own
"Participação Societária UF" column turned out not to even BE the
empresa's registered UF (it is printed beside the participation, not the
company record), closing off the one other candidate source. The raw
Crednet value still travels — inside `cliente_documentos.extracao_crednet`
JSONB, exactly as printed — just never promoted to a semantic `empresas`
column.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.services import campo_conflitos, table_reads

TABLE = "empresas"

#: Cadastral fields — fill-empty / conflict-on-disagree, per the group
#: provenance rule. No `uf` / address fields — see the module docstring's
#: scope-cut note (`empresas` has neither column).
CAMPOS_CADASTRAIS: tuple[str, ...] = (
    "razao_social", "nome_fantasia", "natureza_juridica", "data_abertura",
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao",
)

PROVENIENCIA_COLUNAS: tuple[str, ...] = (
    "dados_origem", "dados_documento_id", "dados_em",
    "dados_confirmado_por", "dados_confirmado_em",
)


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ""


def _serializar(valor: Any) -> Any:
    """A `date`/`datetime` off `CartaoCnpjFields` (`data_abertura`,
    `data_situacao_cadastral`) -> its ISO string, JSON-safe for both a
    PATCH onto `empresas` and a `valor_proposto` on `empresa_campo_
    conflitos` — never a bare `date` object, which the REAL PostgREST
    client (httpx's stdlib JSON encoder) cannot serialise (the mock's own
    `MockSupabaseClient` write-shape assertion catches this too). Anything
    else (a `str`, `None`) passes through unchanged."""
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def _mesmo_valor(atual: Any, proposto: Any) -> bool:
    if _vazio(atual) or _vazio(proposto):
        return _vazio(atual) and _vazio(proposto)
    if isinstance(atual, str) and isinstance(proposto, str):
        return atual.strip().casefold() == proposto.strip().casefold()
    return atual == proposto


def get_empresa(client: Any, org_id: UUID, empresa_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def ensure_empresa(client: Any, org_id: UUID, empresa_id: UUID) -> dict:
    empresa = get_empresa(client, org_id, empresa_id)
    if empresa is None:
        raise NotFoundError(TABLE, str(empresa_id))
    return empresa


def criar_ou_vincular_manual(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    cnpj: str,
    razao_social: Optional[str] = None,
    participacao_pct: Optional[float] = None,
    confirmado_por: Optional[Any] = None,
) -> dict:
    """`POST /api/clientes/{cliente_id}/empresas` (contract §D2) — a manual
    link. Upserts the empresa by `(org_id, cnpj)` (fill-empty `razao_social`
    only, never overwriting a machine-provenanced one), then upserts a
    `origem='manual'` participação for this cliente, fill-empty on `pct`.
    """
    from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

    cnpj_norm = normalize_cnpj(cnpj)
    existentes = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cnpj", cnpj_norm)
        .limit(1)
        .execute()
    ).data or []
    now = _now()
    if existentes:
        empresa = existentes[0]
        if not empresa.get("razao_social") and razao_social:
            _t(client, TABLE).update({"razao_social": razao_social}).eq(
                "id", empresa["id"]
            ).execute()
            empresa = {**empresa, "razao_social": razao_social}
    else:
        empresa = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cnpj": cnpj_norm,
            "razao_social": razao_social,
            "dados_origem": "manual",
            "dados_documento_id": None,
            "dados_em": now,
            "dados_confirmado_por": str(confirmado_por) if confirmado_por else None,
            "dados_confirmado_em": now if confirmado_por else None,
            "created_at": now,
        }
        _t(client, TABLE).insert(empresa).execute()

    participacoes_table = "cliente_empresa_participacoes"
    existentes_part = (
        _t(client, participacoes_table)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("empresa_id", str(empresa["id"]))
        .limit(1)
        .execute()
    ).data or []
    if existentes_part:
        parte = existentes_part[0]
        if parte.get("participacao_pct") is None and participacao_pct is not None:
            _t(client, participacoes_table).update(
                {"participacao_pct": participacao_pct}
            ).eq("id", parte["id"]).execute()
    else:
        _t(client, participacoes_table).insert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "cliente_id": str(cliente_id),
                "empresa_id": str(empresa["id"]),
                "participacao_pct": participacao_pct,
                "desde": None,
                "fonte_documento_id": None,
                "origem": "manual",
                "confirmado_por": str(confirmado_por) if confirmado_por else None,
                "confirmado_em": now if confirmado_por else None,
                "created_at": now,
            }
        ).execute()
    return empresa


#: `aplicar_cartao`'s outcomes.
CNPJ_DIVERGENTE = "cnpj_divergente"
APLICADO = "aplicado"
SEM_MUDANCA = "sem_mudanca"


def aplicar_cartao(
    client: Any,
    org_id: UUID,
    empresa_id: UUID,
    leitura: Any,
    *,
    documento_id: UUID,
    notify_one=None,
) -> dict:
    """The Cartão CNPJ's D1 apply, group-level (contract §C6). Never raises
    for a disagreement — that is a conflict, a normal outcome.

    `leitura` is a `CartaoCnpjFields`-shaped object (duck-typed — this
    module never imports the seed's dataclass; see `crednet_service`'s own
    note on the same pattern).

    Returns `{"status": ..., "aviso": Optional[str], "conflitos": [...]}`.
    """
    empresa = ensure_empresa(client, org_id, empresa_id)

    from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

    if leitura.cnpj and normalize_cnpj(leitura.cnpj) != empresa["cnpj"]:
        return {"status": CNPJ_DIVERGENTE, "aviso": "cnpj_divergente", "conflitos": []}

    patch: dict[str, Any] = {}
    conflitos: list[dict] = []
    for campo in CAMPOS_CADASTRAIS:
        proposto = _serializar(getattr(leitura, campo, None))
        if _vazio(proposto):
            continue
        atual = empresa.get(campo)
        if _vazio(atual):
            patch[campo] = proposto
            continue
        if _mesmo_valor(atual, proposto):
            continue
        confianca = (getattr(leitura, "confiancas", None) or {}).get(campo)
        novo = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, org_id, empresa_id, campo,
            valor_anterior=atual,
            origem_anterior=empresa.get("dados_origem"),
            valor_proposto=proposto,
            origem_proposto="cartao_cnpj",
            confianca_proposta=getattr(confianca, "value", confianca),
            fonte_tabela="empresa_documentos",
            fonte_id=documento_id,
        )
        if novo is not None:
            conflitos.append(novo)

    if patch:
        now = _now()
        patch["dados_origem"] = "cartao_cnpj"
        patch["dados_documento_id"] = str(documento_id)
        patch["dados_em"] = now
        patch["dados_confirmado_por"] = None
        patch["dados_confirmado_em"] = None
        patch["updated_at"] = now
        _t(client, TABLE).update(patch).eq("id", str(empresa_id)).execute()

    return {
        "status": APLICADO if patch else SEM_MUDANCA,
        "aviso": None,
        "conflitos": conflitos,
    }


def confirmar_dados(
    client: Any, org_id: UUID, empresa_id: UUID, *, confirmado_por: Any
) -> dict:
    """`POST /api/empresas/{id}/documentos/{doc_id}/extracao/confirmar`
    (contract §D4) — a human vouches for the currently machine-pending
    group. No-op (not re-stamped) when already confirmed or when there is
    nothing machine-sourced to confirm (`dados_origem` NULL or 'manual')."""
    empresa = ensure_empresa(client, org_id, empresa_id)
    if not empresa.get("dados_origem") or empresa.get("dados_origem") == "manual":
        return empresa
    if empresa.get("dados_confirmado_em"):
        return empresa
    now = _now()
    patch = {
        "dados_confirmado_por": str(confirmado_por) if confirmado_por else None,
        "dados_confirmado_em": now,
        "updated_at": now,
    }
    _t(client, TABLE).update(patch).eq("id", str(empresa_id)).execute()
    return {**empresa, **patch}


#: `atualizar_manual`'s PATCH surface (contract-adjacent, slice D). `cnpj` is
#: NOT part of the group provenance quintet (it is the empresa's identity,
#: never machine-"read" the way the cadastral block is) — a typed correction
#: always applies immediately, gated only by mod-11 validity + uniqueness.
CAMPOS_PATCH_EDITAVEIS: tuple[str, ...] = (
    "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
    "data_situacao_cadastral",
)


def _registrar_edicao_manual_confirmada(
    client: Any,
    org_id: UUID,
    empresa_id: UUID,
    campo: str,
    *,
    valor_anterior: Any,
    origem_anterior: Optional[str],
    valor_proposto: Any,
    decidido_por: Optional[Any],
) -> None:
    """An admin's edit of a document-sourced cadastral field — applied
    immediately by the caller (already written to `empresas` in the SAME
    PATCH), logged here PRE-DECIDED (`status='aceito'`, `decidido_por` the
    admin themselves) so `valor_anterior` survives as history/rollback.
    Mirrors `clientes_service._registrar_edicao_manual_confirmada` — same
    posture, a different owner table (`empresa_campo_conflitos` via
    `campo_conflitos.EMPRESA`), written directly rather than through
    `campo_conflitos.registrar_conflito` because that helper only ever
    opens a `pendente` row (see its own docstring's "open" contract) — an
    admin's edit is pre-decided, not pending."""
    from datetime import datetime, timezone

    table = campo_conflitos.EMPRESA
    # Close out any stale pendente row on the SAME (empresa, campo) — the
    # admin's own edit is what happened instead (mirrors
    # `clientes_service._superseder_conflitos_pendentes`).
    pendentes = (
        _t(client, table.table)
        .select("id")
        .eq("org_id", str(org_id))
        .eq(table.owner_col, str(empresa_id))
        .eq("campo", campo)
        .eq("status", "pendente")
        .execute()
    ).data or []
    now = datetime.now(timezone.utc).isoformat()
    for row in pendentes:
        _t(client, table.table).update(
            {
                "status": "rejeitado",
                "decidido_por": str(decidido_por) if decidido_por else None,
                "decidido_em": now,
            }
        ).eq("id", row["id"]).execute()

    _t(client, table.table).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            table.owner_col: str(empresa_id),
            "campo": campo,
            "valor_anterior": valor_anterior,
            "origem_anterior": origem_anterior,
            "valor_proposto": valor_proposto,
            "origem_proposto": "manual",
            "confianca_proposta": None,
            "fonte_tabela": None,
            "fonte_id": None,
            "status": "aceito",
            "notificado_em": None,
            "decidido_por": str(decidido_por) if decidido_por else None,
            "decidido_em": now,
            "created_at": now,
        }
    ).execute()


def atualizar_manual(
    client: Any,
    org_id: UUID,
    empresa_id: UUID,
    *,
    acting_user_id: Optional[Any] = None,
    is_admin: bool = False,
    **updates: Any,
) -> dict:
    """`PATCH /api/empresas/{id}` (slice D) — razão social, nome fantasia,
    CNPJ, situação cadastral, data da situação.

    Honors the SAME conflict/provenance discipline `clientes_service.
    update_cliente` gives its own document-sourced fields, adapted to
    `empresas`' GROUP-level provenance (this module's docstring):
    `razao_social`/`nome_fantasia`/`situacao_cadastral`/`data_situacao_
    cadastral` are gated as ONE unit — is `dados_origem` machine-sourced
    (not NULL, not 'manual')? An admin's edit applies immediately (logged
    pre-decided, for history/rollback); anyone else's is held back and
    queued per-field in `empresa_campo_conflitos` for admin adjudication.
    `cnpj` is never gated (see `CAMPOS_PATCH_EDITAVEIS`'s own note) —
    validated for mod-11 validity and org-uniqueness instead.

    Returns the updated empresa row (or the unchanged one, when every
    touched field was deferred) plus `pendente_confirmacao` — the item
    keys THIS call deferred, empty when nothing was."""
    payload = {k: v for k, v in updates.items() if k in CAMPOS_PATCH_EDITAVEIS}
    empresa = ensure_empresa(client, org_id, empresa_id)
    if not payload:
        return {**empresa, "pendente_confirmacao": []}

    # 🔴 Snapshotted BEFORE any `.update()` call, not re-read off `empresa`
    # afterwards: the mock client's in-memory store mutates a row's dict IN
    # PLACE (`noctusai_lib.testing.mocks`'s own `update()` — "mutates
    # matching rows in place via dict.update"), and `ensure_empresa` above
    # hands back that SAME row object — a real PostgREST client always
    # returns a fresh dict per call, so this aliasing is mock-only, but
    # reading `empresa` post-write would silently see the NEW values on
    # the mock and the OLD values in prod, a divergence no test running
    # only against the mock could ever catch.
    dados_origem_antes = empresa.get("dados_origem")
    valores_antes = {campo: empresa.get(campo) for campo in CAMPOS_CADASTRAIS}

    if "cnpj" in payload:
        from noctusai_lib.integrations.documents.cnpj import (
            is_valid as cnpj_is_valid,
            normalize as normalize_cnpj,
        )

        cnpj_bruto = payload["cnpj"]
        novo_cnpj = normalize_cnpj(cnpj_bruto)
        if not cnpj_is_valid(novo_cnpj):
            raise ValidationError_(f"CNPJ inválido: {cnpj_bruto!r}", field="cnpj")
        if novo_cnpj != empresa["cnpj"]:
            existentes = (
                _t(client, TABLE)
                .select("id")
                .eq("org_id", str(org_id))
                .eq("cnpj", novo_cnpj)
                .neq("id", str(empresa_id))
                .limit(1)
                .execute()
            ).data or []
            if existentes:
                raise ValidationError_(
                    "Já existe uma empresa cadastrada com este CNPJ nesta organização.",
                    field="cnpj",
                )
        payload["cnpj"] = novo_cnpj

    campos_grupo_tocados = [c for c in CAMPOS_CADASTRAIS if c in payload]
    pendentes: list[str] = []
    if campos_grupo_tocados:
        eh_documento = bool(dados_origem_antes) and dados_origem_antes != "manual"
        if eh_documento and not is_admin:
            for campo in campos_grupo_tocados:
                campo_conflitos.registrar_conflito(
                    client, campo_conflitos.EMPRESA, org_id, empresa_id, campo,
                    valor_anterior=valores_antes[campo],
                    origem_anterior=dados_origem_antes,
                    valor_proposto=_serializar(payload[campo]),
                    origem_proposto="manual",
                )
                pendentes.append(campo)
            for campo in campos_grupo_tocados:
                del payload[campo]

    if not payload:
        return {**empresa, "pendente_confirmacao": pendentes}

    now = _now()
    grupo_aplicado_agora = [c for c in campos_grupo_tocados if c not in pendentes]
    if grupo_aplicado_agora:
        # Every cadastral field that made it into `payload` is being written
        # NOW as a human typed value — the group's provenance becomes
        # 'manual', same stamping `criar_ou_vincular_manual`'s own insert
        # path gives a brand-new empresa.
        payload["dados_origem"] = "manual"
        payload["dados_documento_id"] = None
        payload["dados_em"] = now
    payload["updated_at"] = now

    resp = (
        _t(client, TABLE)
        .update(payload)
        .eq("id", str(empresa_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise NotFoundError(TABLE, str(empresa_id))
    resultado = rows[0]

    if grupo_aplicado_agora and dados_origem_antes not in (None, "manual"):
        # This was gated and the caller IS an admin — log the pre-decided
        # audit row per touched field (see `_registrar_edicao_manual_
        # confirmada`'s own docstring).
        for campo in grupo_aplicado_agora:
            _registrar_edicao_manual_confirmada(
                client, org_id, empresa_id, campo,
                valor_anterior=valores_antes[campo],
                origem_anterior=dados_origem_antes,
                valor_proposto=resultado.get(campo),
                decidido_por=acting_user_id,
            )

    return {**resultado, "pendente_confirmacao": pendentes}


def remover_participacao(
    client: Any, org_id: UUID, cliente_id: UUID, empresa_id: UUID
) -> dict:
    """The DELETE surface (slice D) — removes THIS cliente's link
    (`cliente_empresa_participacoes`) to `empresa_id`; the `empresas` row
    itself (and everything that CASCADEs off it — `empresa_documentos`,
    `empresa_campo_conflitos`, migration 167) is deleted too, but ONLY when
    no other cliente still participates in it.

    Returns `{"participacao_removida": bool, "empresa_removida": bool,
    "documentos": [{"id","storage_path"}, ...]}` — `documentos` is collected
    BEFORE any delete runs (mirrors `clientes_service.excluir_cliente`'s own
    ordering note: `empresa_documentos` CASCADEs off `empresas`, so its rows
    — and their `storage_path`s — would already be gone by the time a
    caller tried to read them AFTER the empresa delete). Storage is
    deliberately NOT touched here — this module is DB I/O only; the ROUTE
    deletes each path from the bucket, same split `excluir_cliente_route`
    already takes."""
    ensure_empresa(client, org_id, empresa_id)

    participacoes_table = "cliente_empresa_participacoes"
    existentes = (
        _t(client, participacoes_table)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("empresa_id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    if not existentes:
        raise NotFoundError(participacoes_table, f"{cliente_id}/{empresa_id}")

    _t(client, participacoes_table).delete().eq("id", existentes[0]["id"]).execute()

    restantes = (
        _t(client, participacoes_table)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("empresa_id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    if restantes:
        return {
            "participacao_removida": True,
            "empresa_removida": False,
            "documentos": [],
        }

    documentos = (
        _t(client, "empresa_documentos")
        .select("id, storage_path")
        .eq("org_id", str(org_id))
        .eq("empresa_id", str(empresa_id))
        .execute()
    ).data or []

    _t(client, TABLE).delete().eq("id", str(empresa_id)).eq(
        "org_id", str(org_id)
    ).execute()

    return {
        "participacao_removida": True,
        "empresa_removida": True,
        "documentos": documentos,
    }


__all__ = [
    "APLICADO",
    "CAMPOS_CADASTRAIS",
    "CAMPOS_PATCH_EDITAVEIS",
    "CNPJ_DIVERGENTE",
    "PROVENIENCIA_COLUNAS",
    "SEM_MUDANCA",
    "TABLE",
    "aplicar_cartao",
    "atualizar_manual",
    "confirmar_dados",
    "criar_ou_vincular_manual",
    "ensure_empresa",
    "get_empresa",
    "remover_participacao",
]
