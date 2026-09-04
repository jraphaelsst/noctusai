"""Read identity fields off an uploaded document, once, and record why.

WHAT THIS IS FOR
----------------
When an RG or a CPF lands, the holder's full name and birthdate are printed on
it. The operator should not have to read them off a scan and key them in.

`data_nascimento` is a checklist item, and because the checklist is DERIVED
(`documento_checklist_service`), filling the column is the whole job — the tick
follows on the next read with nothing to notify and nothing to keep in sync.
`nome_oficial` is deliberately NOT a checklist item: whether we hold the
official document is already answered by the `rg` / `cpf` items, and asking it
twice would let a card look incomplete for a reason it has already satisfied.

🔴 THE NAME IS NOT RECONCILED. IT IS COMPARED.
----------------------------------------------
The registration name and the document name are TWO FACTS, and this module
never merges them.

**`nome_completo` / `nome` — the registration's, untouched.** Whatever the lead
form, Meta, OLX, Vista or the operator supplied stays exactly as supplied.
Extraction does not overwrite it, does not backfill it, does not "fill it in
when empty".

**`nome_oficial` — the document's.** Written only from a document read, never
by hand and never by an import.

An earlier draft had the document overwrite the registration name and keep the
displaced value in a `_anterior` column. It was rejected because overwriting
destroys the comparison that makes this worth doing: holding both is what lets
the question "how accurate is our registration data against official
documents?" be answered across the whole base at any time, instead of being
consumed one row at a time as documents arrive. `vw_nome_conferencia`
(migration 071) is that surface.

**`data_nascimento` — first writer wins.** "Whichever comes first" between RG
and CPF means exactly that. An existing value is never overwritten, and one
whose origin is `manual` is never touched at all. Re-uploading a document must
not silently rewrite a date someone already corrected by hand. The birthdate
has no registration-vs-document tension to preserve: a date is a date.

When two documents disagree about the name, the most recent high-confidence
read wins `nome_oficial`. Nothing is lost — every document keeps its own
`extracao_nome`, so the full set of readings stays on the documents and only
the current best answer is denormalised onto the client.

🔴 THREE MORE RULES THIS MODULE WILL NOT BEND
----------------------------------------------
1. **Only a high-confidence read is written unattended.** `IdentityFields`
   carries a confidence PER FIELD and a `persistable_<field>` gate. A
   low-confidence read is kept ON THE DOCUMENT ROW as a suggestion for a human
   to confirm and never touches the client record. Storing a guess as a fact is
   worse than storing nothing: nothing is visibly missing, a wrong name is not.

   For the name, "high confidence" additionally requires the text to have come
   off a PDF text layer rather than a vision pass — see
   `documents.real._temper_name_confidence`. A misread name is well-formed and
   plausible, so no structural check downstream can catch it; the text source
   is the only real evidence available.

2. **Extraction is a logged content access.** Opening the bytes is a read under
   migration 057's contract, so it appends to `cliente_documento_acessos` with
   `acao='extract'` (migration 068 widened the CHECK for it). Logging it as a
   `view` by a null user would launder a machine read as a human one and break
   the one question the log exists to answer.

3. **Every path ends in a recorded status.** A detached background job that
   raises surfaces nowhere. `extracao_status` is the record, and migration 072's
   `extracao_tentativas` is what lets `varrer_extracoes_pendentes` recover a run
   that died before it could write one — without retrying a doomed document
   forever.

WHY THIS RUNS IN THE BACKGROUND
-------------------------------
The ladder's second rung rasterizes pages and calls a vision model — seconds to
tens of seconds. Doing that inline would make uploading a document feel broken,
and would couple a successful upload to an LLM provider being up. The upload
commits; the read happens after, and its own failure is recorded on the
document rather than lost.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    IdentityFields,
    make_identity_extractor,
    strip_accents_upper,
)
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.services import _now, _t

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"
CLIENTES_TABLE = "clientes"

#: Document types worth reading fields off. Kept separate from
#: `cliente_documento_tipos.identidade` on purpose: that flag drives LGPD
#: retention policy, this drives a processing decision, and letting one silently
#: change the other is how a retention edit turns into an unplanned OCR bill.
#:
#: `cnh` is listed but is NOT currently a row in `cliente_documento_tipos`
#: (migration 057 seeds rg/cpf only), so no CNH can be uploaded and this entry
#: is unreachable today. It is here because the extractor already classifies and
#: reads one — adding the type later is then a data change, not a code change.
#: Stated rather than left to be discovered as a puzzling dead branch.
TIPOS_EXTRAIVEIS = frozenset({"rg", "cpf", "cnh"})

#: How many times one document may be STARTED before the sweep gives up.
#: Bounds the vision bill on a deterministically-broken document — see
#: migration 072.
MAX_TENTATIVAS = 3

#: How long a document may sit in a non-terminal state before the sweep treats
#: it as abandoned. Comfortably longer than a real extraction (tens of seconds)
#: so the sweep never races a job that is simply still working.
STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")


# ─── The extracted fields, as data ──────────────────────────────────────────
#
# Table-driven rather than parallel code paths. The fields differ ONLY in
# policy (`sobrescreve`) and in which columns hold them; expressing that as rows
# is what made adding `genero` (migration 073) a single entry here rather than
# another branch through apply/suggest/confirm. RG number and CPF number remain
# the obvious next ones, on the same terms.


@dataclass(frozen=True)
class CampoExtraido:
    """One field the extractor can lift off a document.

    `item_key` is the `clientes` column this field writes, and — for fields
    that are also checklist items — the checklist key. They are the same
    string by construction in `documento_checklist_service.ITENS`, and keeping
    them one value is what stops the two drifting apart. `nome_oficial` is a
    column but not a checklist item; that asymmetry is intentional and
    explained in the module docstring.
    """

    item_key: str
    coluna_valor: str          # on cliente_documentos — what was read
    coluna_confianca: str
    coluna_rotulo: str
    #: May a LATER document replace this field's value? True for the
    #: document-owned `nome_oficial` (the newest reading is the best answer,
    #: and every reading survives on its own document row); False for
    #: `data_nascimento`, where first-writer-wins protects a human's entry.
    #: This is NOT permission to overwrite a registration field — no entry in
    #: `CAMPOS` points at one.
    sobrescreve: bool

    @property
    def origem(self) -> str:
        return f"{self.item_key}_origem"

    @property
    def documento_id(self) -> str:
        return f"{self.item_key}_documento_id"

    @property
    def em(self) -> str:
        return f"{self.item_key}_em"

    @property
    def confirmado_por(self) -> str:
        return f"{self.item_key}_confirmado_por"

    @property
    def confirmado_em(self) -> str:
        return f"{self.item_key}_confirmado_em"


CAMPOS: tuple[CampoExtraido, ...] = (
    CampoExtraido(
        item_key="data_nascimento",
        coluna_valor="extracao_data_nascimento",
        # 068 named these before there was a second field; migration 071
        # attaches COMMENTs saying they describe the birthdate.
        coluna_confianca="extracao_confianca",
        coluna_rotulo="extracao_rotulo",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="nome_oficial",
        coluna_valor="extracao_nome",
        coluna_confianca="extracao_nome_confianca",
        coluna_rotulo="extracao_nome_rotulo",
        sobrescreve=True,
    ),
    # Migration 073. `sobrescreve=False`, like the birthdate and unlike the
    # name: `genero` is a REGISTRATION field an operator types into the card,
    # so first-writer-wins protects their entry. `nome_oficial` may overwrite
    # only because it is held BESIDE the registration name rather than being
    # it — there is no such second column here.
    CampoExtraido(
        item_key="genero",
        coluna_valor="extracao_genero",
        coluna_confianca="extracao_genero_confianca",
        coluna_rotulo="extracao_genero_rotulo",
        sobrescreve=False,
    ),
    # Migration 097 — the two the note above predicted, on exactly the terms
    # it named. Both `sobrescreve=False`.
    #
    # 🔴 WHY NOT `sobrescreve=True`, when a document is the AUTHORITY on a
    # document number? Because unlike `nome_oficial`, these have no second
    # column holding the human's version. `nome_oficial` may be overwritten
    # only because `nome_completo` sits beside it keeping the registration
    # spelling; there is no `cpf_completo`. Overwriting here would destroy an
    # operator's entry with no way back, so the newest reading loses to
    # whatever is already there and lands as a suggestion instead.
    CampoExtraido(
        item_key="cpf",
        coluna_valor="extracao_cpf",
        coluna_confianca="extracao_cpf_confianca",
        coluna_rotulo="extracao_cpf_rotulo",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="rg",
        coluna_valor="extracao_rg",
        coluna_confianca="extracao_rg_confianca",
        coluna_rotulo="extracao_rg_rotulo",
        sobrescreve=False,
    ),
)

CAMPO_POR_CHAVE: dict[str, CampoExtraido] = {c.item_key: c for c in CAMPOS}

#: Kept as the flat `{item_key: coluna}` mapping earlier callers already read.
CAMPO_POR_ITEM: dict[str, str] = {c.item_key: c.coluna_valor for c in CAMPOS}


def deve_extrair(tipo_documento: str) -> bool:
    """Is this a document we read fields from?"""
    return tipo_documento in TIPOS_EXTRAIVEIS


def _valores_lidos(fields: IdentityFields) -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """`item_key -> (valor, confianca, rotulo, pode_persistir)`.

    The ONE place `IdentityFields`' per-field attribute names are mapped onto
    checklist item keys. Everything downstream is generic over `CAMPOS`.
    """
    return {
        "data_nascimento": (
            fields.data_nascimento.isoformat() if fields.data_nascimento else None,
            fields.data_nascimento_confianca.value,
            fields.data_nascimento_rotulo,
            fields.persistable_data_nascimento,
        ),
        "nome_oficial": (
            fields.nome,
            fields.nome_confianca.value,
            fields.nome_rotulo,
            fields.persistable_nome,
        ),
        "genero": (
            fields.genero,
            fields.genero_confianca.value,
            fields.genero_rotulo,
            fields.persistable_genero,
        ),
        "cpf": (
            fields.cpf,
            fields.cpf_confianca.value,
            fields.cpf_rotulo,
            fields.persistable_cpf,
        ),
        "rg": (
            fields.rg,
            fields.rg_confianca.value,
            fields.rg_rotulo,
            fields.persistable_rg,
        ),
    }


def _mesmo_nome(a: Optional[str], b: Optional[str]) -> bool:
    """Are these the same name modulo accents, case and spacing?

    Used so a re-read of the same document is a no-op, and so a second
    document that spells the name identically does not restamp the
    provenance columns for no reason.
    """
    if not a or not b:
        return False
    norm = lambda s: " ".join(strip_accents_upper(s).split())  # noqa: E731
    return norm(a) == norm(b)


def _marcar(client: Any, documento_id: UUID, **updates: Any) -> None:
    _t(client, DOCUMENTOS_TABLE).update(updates).eq("id", str(documento_id)).execute()


def _log_acesso_extracao(client: Any, org_id: UUID, documento_id: UUID) -> None:
    """Append the machine read to the access log.

    `usuario_id` is null because no user performed it — that is the honest
    record, and `acao='extract'` is what keeps it distinguishable from a
    human's `view` rather than hiding inside it.
    """
    _t(client, "cliente_documento_acessos").insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "documento_id": str(documento_id),
            "usuario_id": None,
            "acao": "extract",
            "created_at": _now(),
        }
    ).execute()


def _aplicar_ao_cliente(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    tipo_documento: str,
    fields: IdentityFields,
) -> dict[str, bool]:
    """Write what may be written onto the client record.

    Returns `{item_key: foi_aplicado}`, so the caller can tell "read it and
    used it" from "read it and correctly declined to" per field.
    """
    colunas: list[str] = ["id"]
    for campo in CAMPOS:
        colunas += [campo.item_key, campo.origem]
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(colunas))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {c.item_key: False for c in CAMPOS}

    atual = rows[0]
    lidos = _valores_lidos(fields)
    updates: dict[str, Any] = {}
    aplicados: dict[str, bool] = {}
    now = _now()

    for campo in CAMPOS:
        valor, _confianca, _rotulo, pode = lidos[campo.item_key]
        aplicados[campo.item_key] = False
        if not pode or valor is None:
            continue

        presente = atual.get(campo.item_key)

        if not campo.sobrescreve:
            # First writer wins. A value already present — or one a human
            # typed, even if it somehow reads empty — is left alone.
            if presente or atual.get(campo.origem) == "manual":
                continue
        else:
            # A document-owned field: the newest reading is the best answer.
            # Skip only when there is genuinely nothing to change — re-reading
            # the same document, or a second document that agrees. No previous
            # value is destroyed by this: what it replaces is an earlier
            # DOCUMENT reading, and that reading survives on its own document
            # row in `extracao_nome`.
            if _mesmo_nome(presente, valor):
                continue

        updates[campo.item_key] = valor
        updates[campo.origem] = tipo_documento
        updates[campo.documento_id] = str(documento_id)
        updates[campo.em] = now
        aplicados[campo.item_key] = True

        # 🔴 `rg_orgao_expedidor` RIDES ALONG — it is not a CAMPO and must
        # not become one. An issuing body with no number identifies nothing,
        # and a number without its issuer is an incomplete qualification on a
        # contract, so the pair is written together under the RG's decision or
        # not at all. `IdentityFields.rg_orgao` carries the same note.
        if campo.item_key == "rg" and fields.rg_orgao:
            updates["rg_orgao_expedidor"] = fields.rg_orgao

    if updates:
        updates["updated_at"] = now
        _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()

    return aplicados


async def extrair_identidade(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    extractor: Optional[Any] = None,
) -> dict:
    """Read one identity document and record the outcome. Never raises.

    Runs detached from the request that triggered it, so an exception here
    would surface nowhere and the document would sit in `processando` forever.
    Every failure path therefore ends in a recorded `extracao_status`, which is
    what makes `varrer_extracoes_pendentes` able to recover the one case this
    cannot record: the process dying mid-read.
    """
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        logger.warning("extracao: documento %s not found for org %s", documento_id, org_id)
        return {"status": "erro", "erro": "documento_nao_encontrado"}

    doc = rows[0]
    if doc.get("deleted_at"):
        # Deleted between upload and this job. Reading its bytes now would be
        # an access to something the client asked us to forget.
        return {"status": "erro", "erro": "documento_removido"}
    if not deve_extrair(doc["tipo_documento"]):
        return {"status": "erro", "erro": "tipo_nao_extraivel"}

    tentativas = int(doc.get("extracao_tentativas") or 0) + 1
    _marcar(
        client,
        documento_id,
        extracao_status="processando",
        extracao_em=_now(),
        extracao_tentativas=tentativas,
    )

    try:
        blob = await storage.get(bucket=BUCKET, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("extracao %s: storage read failed: %s", documento_id, exc)
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro=f"storage: {exc}", extracao_em=_now(),
        )
        return {"status": "erro", "erro": "storage"}

    if blob is None:
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro="objeto ausente no storage",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "objeto_ausente"}

    # Rule 2 — logged BEFORE the read, so a crash mid-extraction still leaves
    # the access recorded. An access log that only records successful reads is
    # not an access log.
    _log_acesso_extracao(client, org_id, documento_id)

    extractor = extractor or make_identity_extractor(real=True, org_id=str(org_id))
    fields: IdentityFields = await extractor.extract(
        blob.data,
        mimetype=doc.get("mime_type"),
        filename=doc.get("nome_original"),
    )

    if fields.error:
        _marcar(
            client, documento_id,
            extracao_status="erro",
            extracao_erro=f"{fields.error}: {fields.error_message or ''}".strip(": "),
            extracao_fonte=fields.source.value,
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": fields.error}

    lidos = _valores_lidos(fields)
    achou_algo = any(v is not None for v, _, _, _ in lidos.values())

    # Recorded whether or not it is persistable — a low-confidence read is a
    # suggestion the card can offer, and the `_rotulo` columns let a human
    # audit the reasoning without re-opening the document (another logged
    # access).
    marcacoes: dict[str, Any] = {
        "extracao_status": "ok" if achou_algo else "sem_dados",
        "extracao_fonte": fields.source.value,
        "extracao_erro": None,
        "extracao_em": _now(),
    }
    for campo in CAMPOS:
        valor, confianca, rotulo, _ = lidos[campo.item_key]
        marcacoes[campo.coluna_valor] = valor
        marcacoes[campo.coluna_confianca] = confianca
        marcacoes[campo.coluna_rotulo] = rotulo
    _marcar(client, documento_id, **marcacoes)

    aplicados = _aplicar_ao_cliente(
        client, org_id, cliente_id, documento_id, doc["tipo_documento"], fields
    )
    return {
        "status": "ok" if achou_algo else "sem_dados",
        "data_nascimento": lidos["data_nascimento"][0],
        "nome_oficial": lidos["nome_oficial"][0],
        "confianca": lidos["data_nascimento"][1],
        "confianca_nome": lidos["nome_oficial"][1],
        "fonte": fields.source.value,
        "tentativas": tentativas,
        "aplicado_ao_cliente": aplicados,
    }


# ─── The sweep: what happens when the process dies mid-read (migration 072) ──


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


async def varrer_extracoes_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    """Re-run extractions that were started and never finished.

    🔴 WHY THIS EXISTS AT ALL. `extracao_status` moves to `processando` before
    the work and to a terminal value after it. If the process dies in between —
    a deploy, an OOM kill, a container restart — nothing ever moves it again.
    The document sits there, the checklist item never ticks, and NOTHING
    SURFACES. The same is true of `pendente` if the BackgroundTask was never
    scheduled because the request handler's process went away first.

    Two bounds keep this from becoming its own problem:

    - **Age.** Only documents stalled longer than `STALE_APOS` are touched, so
      the sweep can never race a job that is simply still working.
    - **Attempts.** `MAX_TENTATIVAS` caps how many times one document is
      retried. A deterministically-broken document (corrupt bytes, a
      password-protected PDF, an object deleted from storage) would otherwise
      be re-read on every pass forever, paying for a vision call each time.
      Exhausted rows are moved to a terminal `erro` a human can see — the
      opposite of the silent `processando` this function exists to end.
    """
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id,org_id,cliente_id,extracao_status,extracao_tentativas,extracao_em")
        .in_("extracao_status", list(_ESTADOS_NAO_TERMINAIS))
        .is_("deleted_at", "null")
        .lte("extracao_em", _stale_cutoff())
        .limit(limite)
        .execute()
    ).data or []

    retomados = 0
    esgotados = 0
    falhas = 0

    for row in rows:
        documento_id = UUID(str(row["id"]))
        tentativas = int(row.get("extracao_tentativas") or 0)

        if tentativas >= MAX_TENTATIVAS:
            _marcar(
                client,
                documento_id,
                extracao_status="erro",
                extracao_erro=(
                    f"extração abandonada após {tentativas} tentativas "
                    f"(limite {MAX_TENTATIVAS})"
                ),
                extracao_em=_now(),
            )
            esgotados += 1
            continue

        try:
            org_id = UUID(str(row["org_id"]))
            cliente_id = UUID(str(row["cliente_id"]))
            extractor = extractor_factory(str(org_id)) if extractor_factory else None
            await extrair_identidade(
                client, storage, org_id, cliente_id, documento_id,
                extractor=extractor,
            )
            retomados += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.warning("sweep: documento %s failed: %s", documento_id, exc)
            falhas += 1

    if rows:
        logger.info(
            "extracao sweep: %d stalled, %d retried, %d exhausted, %d failed",
            len(rows), retomados, esgotados, falhas,
        )
    return {
        "encontrados": len(rows),
        "retomados": retomados,
        "esgotados": esgotados,
        "falhas": falhas,
    }


# ─── Suggestions: what a low-confidence read is FOR (migration 069) ──────────
#
# A high-confidence read writes itself and disappears into the record. A
# low-confidence one has nowhere to go — 068 deliberately keeps it off
# `clientes` — so without this it would be correct, possibly useful, and
# invisible. These three functions are the decision surface that makes it
# actionable without ever letting it become a fact by default.


def _oferecer(campo: CampoExtraido, atual: Optional[str], valor: Any) -> bool:
    """Is this extracted value still an open question?

    The rule follows the field's write policy, because "already answered"
    means different things for the two:

    - **First-writer-wins field.** A value present at all closes it. There is
      nothing left to decide.
    - **Overwriting field.** A value present does NOT close it — the document
      is supposed to win. It stays open until the recorded value AGREES with
      what the document says, which is the only state in which confirming
      would change nothing.
    """
    if not valor:
        return False
    if campo.sobrescreve:
        return not _mesmo_nome(atual, str(valor))
    return not atual


def sugestoes_pendentes(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Per checklist-item, the newest extracted value still awaiting a decision.

    Newest-first when several documents disagree: the operator resolves one at
    a time, and discarding reveals the next rather than a pile to triage. A
    disagreement between two reads is exactly the case where showing both at
    once invites picking the wrong one quickly.
    """
    cliente_rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(["id", *CAMPO_POR_ITEM]))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not cliente_rows:
        return {}
    cliente = cliente_rows[0]

    docs = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []

    candidatos = [
        d for d in docs
        if not d.get("deleted_at") and not d.get("extracao_descartada_em")
    ]
    candidatos.sort(key=lambda d: d.get("extracao_em") or "", reverse=True)

    out: dict = {}
    for campo in CAMPOS:
        atual = cliente.get(campo.item_key)
        for doc in candidatos:
            valor = doc.get(campo.coluna_valor)
            if not _oferecer(campo, atual, valor):
                continue
            out[campo.item_key] = {
                "valor": valor,
                "valor_atual": atual,
                "documento_id": doc["id"],
                "documento_nome": doc.get("nome_original"),
                "tipo_documento": doc.get("tipo_documento"),
                "confianca": doc.get(campo.coluna_confianca),
                "fonte": doc.get("extracao_fonte"),
                "rotulo": doc.get(campo.coluna_rotulo),
                "substitui": bool(campo.sobrescreve and atual),
            }
            break
    return out


def _resolver_campo(item_key: Optional[str]) -> CampoExtraido:
    """`item_key` -> its spec, defaulting to the birthdate.

    The default keeps the pre-071 single-field callers working unchanged; an
    unknown key is a caller bug and says so rather than silently picking one.
    """
    if item_key is None:
        return CAMPO_POR_CHAVE["data_nascimento"]
    campo = CAMPO_POR_CHAVE.get(item_key)
    if campo is None:
        raise ValidationError_(
            f"Campo extraído desconhecido: {item_key!r}.", field="item_key"
        )
    return campo


def confirmar_sugestao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    item_key: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> dict:
    """A human vouches for a machine read: apply it to the client record.

    `<campo>_origem` is stamped with the DOCUMENT TYPE, not `'manual'`. The
    value genuinely came off the RG; what the human added is accountability,
    and that is `<campo>_confirmado_por`. Recording it as `'manual'` would
    erase the fact that a scan produced it — and would then outrank a later,
    better read for the wrong reason.

    For a first-writer-wins field this refuses when the field is already set:
    two operators on the same card otherwise race, and the loser silently
    overwrites the winner. For a document-owned field the newer reading is
    meant to win, so it is applied; the reading it replaces is still on its
    own document row.
    """
    campo = _resolver_campo(item_key)

    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError("cliente_documentos", str(documento_id))
    doc = rows[0]

    valor = doc.get(campo.coluna_valor)
    if not valor:
        raise ValidationError_(
            "Este documento não tem um valor extraído para confirmar.",
            field=campo.coluna_valor,
        )
    if doc.get("extracao_descartada_em"):
        raise ValidationError_(
            "Esta sugestão já foi descartada.", field="extracao_descartada_em"
        )

    cliente_rows = (
        _t(client, CLIENTES_TABLE)
        .select(f"{campo.item_key},{campo.origem}")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not cliente_rows:
        raise NotFoundError("clientes", str(cliente_id))
    presente = cliente_rows[0].get(campo.item_key)

    if not campo.sobrescreve and presente:
        raise ValidationError_(
            "Este cliente já tem um valor registrado para este campo.",
            field=campo.item_key,
        )

    now = _now()
    updates: dict[str, Any] = {
        campo.item_key: valor,
        campo.origem: doc["tipo_documento"],
        campo.documento_id: str(documento_id),
        campo.em: now,
        campo.confirmado_por: str(user_id) if user_id else None,
        campo.confirmado_em: now,
        "updated_at": now,
    }
    _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()

    return {
        "confirmado": True,
        "item_key": campo.item_key,
        "valor": valor,
        "substituiu": presente if (campo.sobrescreve and presente) else None,
        "documento_id": str(documento_id),
    }


def descartar_sugestao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    item_key: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> dict:
    """Turn down a suggestion so the card stops offering it.

    The extracted value is KEPT. Clearing it would destroy the evidence of what
    the extractor actually read, which is the only way to later distinguish a
    bad OCR pass from a bad decision about a good one.

    🔴 Discarding is per DOCUMENT, not per field: `extracao_descartada_em` is
    one column, so turning down a document's name also stops offering its
    birthdate. That is the honest behaviour for the case that matters — "this
    document does not belong to this client" — and the alternative (a
    per-field discard column each) would let a human accept a birthdate off a
    document they had just declared to be the wrong person's. `item_key` is
    accepted so the call site reads symmetrically with `confirmar_sugestao`
    and is recorded in the return value.
    """
    campo = _resolver_campo(item_key)

    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError("cliente_documentos", str(documento_id))

    now = _now()
    _t(client, DOCUMENTOS_TABLE).update(
        {
            "extracao_descartada_em": now,
            "extracao_descartada_por": str(user_id) if user_id else None,
        }
    ).eq("id", str(documento_id)).execute()
    return {
        "descartado": True,
        "item_key": campo.item_key,
        "documento_id": str(documento_id),
    }


__all__ = [
    "CAMPOS",
    "CAMPO_POR_CHAVE",
    "CAMPO_POR_ITEM",
    "MAX_TENTATIVAS",
    "STALE_APOS",
    "TIPOS_EXTRAIVEIS",
    "CampoExtraido",
    "confirmar_sugestao",
    "descartar_sugestao",
    "deve_extrair",
    "extrair_identidade",
    "sugestoes_pendentes",
    "varrer_extracoes_pendentes",
]
