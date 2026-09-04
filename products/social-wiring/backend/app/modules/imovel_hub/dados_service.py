"""The cartório data we author for an imóvel (migration 075).

`imoveis` is a Vista sync MIRROR — `imoveis_service.sync()` upserts every
property from the CRM. This table is ours: número de matrícula, número do
registro de imóveis, prefeitura do cadastro imobiliário, and the captador
who brought the property in. See migration 075's header for why authored
data does not live inside a mirror of somebody else's system.

🔴 AND WHY IT KEYS TO `imovel_registry`, NOT TO THE MIRROR (migration 076).
075 made that argument and then FK'd to the mirror anyway. The mirror holds
only what Vista lists TODAY; the registry holds every código we have ever
seen and is append-only. A property leaves the Vista catalog when it is
SOLD — so keying to the mirror would have made this feature 404 exactly the
imóveis whose paperwork is being handled.

WRITE SEMANTICS FOR `numero_matricula`
--------------------------------------
The column has a provenance quintuple, mirroring `clientes.data_nascimento`
(migration 068), and the same rule: **first writer wins.** A number a human
typed is never overwritten by a machine read, and a machine read never
overwrites a machine read. The extraction path (`matricula_extracao_service`)
offers a value; only an empty column accepts it unattended.

That asymmetry is deliberate and is the opposite of `nome`'s (where the
official document is meant to win). A matrícula number has no plausibility
gate — see `noctusai_lib.integrations.documents.matricula_extractor` — so
letting a read overwrite a human's entry would trade a value somebody
verified for one nobody can check.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.services import table_reads

TABLE = "imovel_dados"

#: 🔴 The REGISTRY, never the `imoveis` mirror — see migration 076.
#:
#: `imoveis` holds what Vista says TODAY and shrinks when a property leaves
#: the catalog. `imovel_registry` is append-only: one row per código we have
#: ever seen. Measured on prod 2026-08-25, 1062 of 3017 registered imóveis
#: (35%) were already absent from the mirror — and an imóvel leaves the
#: catalog because it was SOLD, i.e. exactly when its matrícula is in play.
#: Checking the mirror would 404 the properties this feature exists for.
REGISTRY_TABLE = "imovel_registry"
REGISTRY_CODIGO = "codigo_canonical"

#: The fields a human may set through the API. `numero_matricula` is here —
#: a human typing it is the FIRST writer and the most trusted one — but its
#: provenance columns are not: those are stamped by whichever path wrote the
#: value, never accepted from a request body.
CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "numero_matricula",
    "numero_registro_imoveis",
    "prefeitura_cadastro_imobiliario",
    "captador_user_id",
    # Migration 099 — situação de ônus. The first clause of every promessa de
    # compra e venda asserts the property is sold "livre e desembaraçado de
    # quaisquer ônus reais"; until now nothing in the schema could back that
    # sentence. `atendimento_financiamento` records the BUYER's financing,
    # which is the opposite side of the transaction from the SELLER's debt.
    #
    # 🔴 NO RULES ATTACHED, on purpose. The vocabulary below is what the UI
    # offers; nothing refuses to emit a document on a stale certidão and
    # nothing ties these fields to each other. The user asked for the field
    # now and the rules later, and a gate written before its policy is decided
    # is a gate that gets worked around.
    "situacao_onus",
    "onus_observacoes",
    "onus_certidao_em",
    "onus_documento_id",
)

#: What the UI offers for `situacao_onus`. Here rather than as a schema CHECK
#: for the reason migration 099 gives: the vocabulary is a product decision and
#: freezing a guessed enum in the database makes each addition a migration.
#: NOT enforced as a whitelist — see `atualizar`.
SITUACOES_ONUS: tuple[str, ...] = (
    "livre",
    "hipoteca",
    "alienacao_fiduciaria",
    "penhora",
    "usufruto",
    "indisponibilidade",
    "outro",
)

#: Provenance columns — stamped, never accepted from a body. Listed so the
#: refusal below names them rather than silently dropping them, which is the
#: silent-error shape this codebase forbids.
CAMPOS_PROVENIENCIA: tuple[str, ...] = (
    "numero_matricula_origem",
    "numero_matricula_documento_id",
    "numero_matricula_em",
    "numero_matricula_confirmado_por",
    "numero_matricula_confirmado_em",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def ensure_imovel(client: Any, org_id: UUID, codigo: str) -> dict:
    """The imóvel must be KNOWN before we can author data for it.

    "Known" means present in `imovel_registry` — every código we have ever
    seen, from any source — NOT present in the Vista catalog today. See the
    `REGISTRY_TABLE` note above for why the distinction decides whether this
    feature works for a sold property.

    Checked explicitly rather than left to the FK: a foreign-key violation
    surfaces as a 500 from the driver, and "imóvel não encontrado" is a 404
    the caller can act on.
    """
    rows = (
        _t(client, REGISTRY_TABLE)
        .select(REGISTRY_CODIGO)
        .eq("org_id", str(org_id))
        .eq(REGISTRY_CODIGO, codigo)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(REGISTRY_TABLE, codigo)
    return rows[0]


def _linha(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _saida(codigo: str, row: Optional[dict], resolved: dict) -> dict:
    """The response shape. An imóvel with no row yet is NOT an error and NOT
    an empty object — it is every field, null. A caller that had to tell
    "no row" apart from "row with nothing in it" would branch on it at every
    call site, and the two mean the same thing to a user."""
    row = row or {}
    return {
        "codigo": codigo,
        "numero_matricula": row.get("numero_matricula"),
        "numero_matricula_origem": row.get("numero_matricula_origem"),
        "numero_matricula_documento_id": row.get("numero_matricula_documento_id"),
        "numero_matricula_em": row.get("numero_matricula_em"),
        "numero_matricula_confirmado_por": table_reads.actor(
            resolved, row.get("numero_matricula_confirmado_por")
        ),
        "numero_matricula_confirmado_em": row.get("numero_matricula_confirmado_em"),
        "numero_registro_imoveis": row.get("numero_registro_imoveis"),
        "prefeitura_cadastro_imobiliario": row.get("prefeitura_cadastro_imobiliario"),
        "captador": table_reads.actor(resolved, row.get("captador_user_id")),
        "situacao_onus": row.get("situacao_onus"),
        "onus_observacoes": row.get("onus_observacoes"),
        # The date printed ON the certidão, not when it was uploaded — a
        # certidão's validity runs from its own emission, so the upload
        # timestamp answers a different question.
        "onus_certidao_em": row.get("onus_certidao_em"),
        "onus_documento_id": row.get("onus_documento_id"),
        "onus_registrado_por": table_reads.actor(
            resolved, row.get("onus_registrado_por")
        ),
        "onus_registrado_em": row.get("onus_registrado_em"),
        "situacoes_onus": list(SITUACOES_ONUS),
        "updated_at": row.get("updated_at"),
    }


def obter(client: Any, org_id: UUID, codigo: str) -> dict:
    ensure_imovel(client, org_id, codigo)
    row = _linha(client, org_id, codigo)
    ids = {
        (row or {}).get("captador_user_id"),
        (row or {}).get("numero_matricula_confirmado_por"),
        (row or {}).get("onus_registrado_por"),
    }
    return _saida(codigo, row, table_reads.resolve_actors(ids))


def atualizar(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    """Upsert the authored fields. Only keys present in `valores` are touched.

    `None` is a real value here — clearing a wrongly-typed matrícula number
    has to be possible — so absence, not null, is what means "leave alone".
    """
    ensure_imovel(client, org_id, codigo)

    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        # Named, not dropped. A body field that is silently ignored is
        # indistinguishable from one that was saved.
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}",
            field=recusados[0],
        )

    atual = _linha(client, org_id, codigo)
    patch = {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}

    # A human typing the number IS the provenance. Stamped here rather than
    # left null so a later extraction can tell the column is already spoken
    # for — that check is what makes first-writer-wins work.
    if "numero_matricula" in patch and patch["numero_matricula"]:
        patch["numero_matricula_origem"] = "manual"
        patch["numero_matricula_documento_id"] = None
        patch["numero_matricula_em"] = _now()
        patch["numero_matricula_confirmado_por"] = (
            str(usuario_id) if usuario_id else None
        )
        patch["numero_matricula_confirmado_em"] = _now()
    elif "numero_matricula" in patch:
        # Cleared. Its provenance must go with it — a stale origin pointing
        # at a number that is no longer there is worse than none.
        for coluna in CAMPOS_PROVENIENCIA:
            patch[coluna] = None

    if "captador_user_id" in patch and patch["captador_user_id"] is not None:
        patch["captador_user_id"] = str(patch["captador_user_id"])

    if atual is None:
        row = {"org_id": str(org_id), "codigo": codigo, **patch, "created_at": _now()}
        _t(client, TABLE).insert(row).execute()
    else:
        patch["updated_at"] = _now()
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "codigo", codigo
        ).execute()

    return obter(client, org_id, codigo)


def aplicar_matricula_extraida(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    numero: str,
    documento_id: UUID,
) -> bool:
    """Write an extracted number into an EMPTY column. Returns whether it landed.

    🔴 FIRST WRITER WINS, CHECKED AGAINST THE ROW, NOT AGAINST A FLAG.
    Re-read immediately before the write rather than trusting anything the
    caller passed: the extraction runs detached, minutes may separate the
    upload from this call, and a human may well have typed the number in
    between. Returning `False` here is the normal, correct outcome in that
    race — not a failure.
    """
    ensure_imovel(client, org_id, codigo)
    atual = _linha(client, org_id, codigo)
    if atual and atual.get("numero_matricula"):
        return False

    patch = {
        "numero_matricula": numero,
        "numero_matricula_origem": "matricula",
        "numero_matricula_documento_id": str(documento_id),
        "numero_matricula_em": _now(),
        # Deliberately NOT confirmed: a machine read is attributable to a
        # document, never to a person. `confirmado_por` stays null until a
        # human agrees with it.
        "numero_matricula_confirmado_por": None,
        "numero_matricula_confirmado_em": None,
    }
    if atual is None:
        _t(client, TABLE).insert(
            {"org_id": str(org_id), "codigo": codigo, **patch, "created_at": _now()}
        ).execute()
    else:
        patch["updated_at"] = _now()
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "codigo", codigo
        ).execute()
    return True


__all__ = [
    "CAMPOS_EDITAVEIS",
    "CAMPOS_PROVENIENCIA",
    "TABLE",
    "aplicar_matricula_extraida",
    "atualizar",
    "ensure_imovel",
    "obter",
]
