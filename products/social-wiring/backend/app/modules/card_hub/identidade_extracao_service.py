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
1. **D1 — fill empty, never overwrite (owner decision, 2026-09-22,
   migration 153).** Any parsed value — at ANY confidence — fills an EMPTY
   `clientes` field, stamped with provenance (`<campo>_origem` = the
   document type, `_documento_id`, `_em`) and left machine-pending
   (`_confirmado_em IS NULL`) for the contract's validation gate, which is
   where a human vouches for it. A field already holding a value — typed by a
   human or written by an earlier extraction — is NEVER overwritten: a
   differing reading opens a `cliente_campo_conflitos` row and an admin is
   notified (`notificar_conflitos`). The confidence still lands on the
   document row, so the gate can show how sure the read was.

   This supersedes the earlier rule ("only `alta` is written; `baixa` waits
   as a suggestion; `nome_oficial` is overwritten by the newest document"),
   which left every vision-read field off the contract and let a later scan
   silently replace an earlier accepted name. The section above on
   `nome_oficial` still describes WHY registration and document names are
   two columns; it no longer describes an overwrite.

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

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    IdentityFields,
    TitularEsperado,
    canonical_gender,
    classificar_tipo_provavel,
    is_same_as_cpf,
    make_identity_extractor,
    nomes_compativeis,
    strip_accents_upper,
)
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.nacionalidade import canonico as nacionalidade_canonica
from noctusai_lib.integrations.documents.rg import only_alnum
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.proveniencia import fontes
from app.services import campo_conflitos
from app.services.api_keys_store import resolve_vision_provider
from app.modules.card_hub.services import _now, _t

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"
CLIENTES_TABLE = "clientes"

#: Document types worth reading fields off — derived from `proveniencia.
#: fontes.FONTES` (contract-gate S1), the ONE catalog that also backs
#: `imovel_hub/documentos_service.py`'s own `TIPOS_*` and is checked against
#: what the seed's extractor can actually produce (`capacidades.CAPACIDADES`).
#: Kept separate from `cliente_documento_tipos.identidade` on purpose: that
#: flag drives LGPD retention policy, this drives a processing decision, and
#: letting one silently change the other is how a retention edit turns into
#: an unplanned OCR bill.
#:
#: `cnh` was listed here BEFORE it had a row in `cliente_documento_tipos`
#: (migration 057 seeded rg/cpf only, so no CNH could be uploaded and this
#: entry was unreachable) — deliberately, because the extractor already
#: classified and read one, and adding the type later was meant to be a data
#: change, not a code change. Migration 142 is that data change: it seeds the
#: `cnh` catalogue row (`ativo = true`) so uploads and this extraction gate
#: both reach it now. No further change was needed here — this module was
#: already written against the day it would ship.
TIPOS_EXTRAIVEIS = frozenset(
    f.tipo_documento for f in fontes.FONTES.values() if f.dominio == "cliente"
)

#: Types whose reading may fill the `endereco_*` group — and, for these, ONLY
#: the address: a utility bill routinely names a spouse or a parent, so its
#: name/CPF are that person's, never evidence about this cliente's identity.
#: Conversely an identity document or a certidão never fills the address —
#: a certidão prints its CARTÓRIO's address, which is nobody's home.
#: (`comprovante_residencia` is an `atendimento_documentos` type — the
#: financing surface, a different table this pipeline does not read.)
TIPOS_ENDERECO = frozenset(
    f.tipo_documento
    for f in fontes.FONTES.values()
    if f.dominio == "cliente" and "endereco" in f.campos
)

#: Types whose vision rung must receive EVERY page, not the adapter's
#: 3-page default.
#:
#: 🔴 TRUNCATING ONE OF THESE INVERTS THE ANSWER — it does not merely lose
#: detail. A certidão de casamento states the marriage on page 1 as a
#: LABELLED form ("regime de bens: comunhão parcial") and records the
#: AVERBAÇÃO that dissolved it — the divorce, the name reversion — as prose
#: further in. Measured on the three certidões this org holds (2026-09-07):
#: all three parties are divorced, and all three documents read "casado,
#: comunhão parcial" on their first page.
#:
#: So this is not an optimisation knob. It is the reason `certidao_casamento`
#: is safe to make extractable at all: registering the type without it would
#: start writing confident wrong estado-civil values where today the document
#: is simply never read.
#:
#: `certidao_nascimento` joins it on the same terms (migration 110): a
#: marriage, divórcio or óbito is averbado on the margin of a birth
#: certificate too, further into the document than page 1 — see that
#: migration's header.
TIPOS_LEITURA_INTEGRAL = frozenset(
    f.tipo_documento for f in fontes.FONTES.values() if f.leitura_integral
)

#: How many times one document may be STARTED before the sweep gives up.
#: Bounds the vision bill on a deterministically-broken document — see
#: migration 072.
MAX_TENTATIVAS = 3

#: D3 (owner decision, 2026-09-22): a FAILED extraction (`erro`) is retried
#: automatically at most this many times — i.e. `MAX_TENTATIVAS - 1`, the
#: first attempt plus two retries — then it stays in `erro` for a human
#: (the `.../extrair` re-run route). No long loops, `insufficient_quota`
#: included: a provider out of credit is exactly the case where hammering it
#: hourly buys nothing.
MAX_RETENTATIVAS_ERRO = MAX_TENTATIVAS - 1

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
    #: Another CAMPO this one only makes sense beside. `rg_orgao_expedidor`
    #: names `rg`: an issuer is written only when the RG on the record (already
    #: there, or written by this same call) IS the number it was read next to
    #: — an SSP/SP beside somebody else's RG number qualifies nobody.
    depende_de: Optional[str] = None

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
    # 🔴 `sobrescreve=False` since migration 153 (owner decision D1,
    # 2026-09-22): a machine NEVER overwrites a value already on the record —
    # not even the document-owned `nome_oficial`. A later reading that
    # differs opens a conflict for an admin, exactly like every other field.
    CampoExtraido(
        item_key="nome_oficial",
        coluna_valor="extracao_nome",
        coluna_confianca="extracao_nome_confianca",
        coluna_rotulo="extracao_nome_rotulo",
        sobrescreve=False,
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
    # Migration 153 — the issuer gets its OWN provenance (it used to ride with
    # `rg` under the RG's decision), because the contract gate must know
    # whether a human has seen it. It still depends on `rg`: see `depende_de`.
    CampoExtraido(
        item_key="rg_orgao_expedidor",
        coluna_valor="extracao_rg_orgao",
        coluna_confianca="extracao_rg_orgao_confianca",
        coluna_rotulo="extracao_rg_orgao_rotulo",
        sobrescreve=False,
        depende_de="rg",
    ),
    # Migration 110 — the two `civil_status.py` predicted (see `IdentityFields`'
    # own docstring) and named on exactly the terms `cpf`/`rg` arrived on:
    # `sobrescreve=False` for the same reason those two are — neither has a
    # second column holding an operator's own spelling, so a later reading
    # that disagrees is a suggestion, never an overwrite.
    CampoExtraido(
        item_key="estado_civil",
        coluna_valor="extracao_estado_civil",
        coluna_confianca="extracao_estado_civil_confianca",
        coluna_rotulo="extracao_estado_civil_rotulo",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="regime_bens",
        coluna_valor="extracao_regime_bens",
        coluna_confianca="extracao_regime_bens_confianca",
        coluna_rotulo="extracao_regime_bens_rotulo",
        sobrescreve=False,
    ),
    # Migration 117 (contract F6). `sobrescreve=False`, same reasoning
    # `data_nascimento` gives: "a date is a date" with no registration-vs-
    # document tension to preserve. Unlike `data_nascimento`, only
    # `certidao_casamento` ever supplies it (`TIPOS_LEITURA_INTEGRAL` already
    # reads that type whole, for the estado_civil averbação — the same full
    # read now also carries the celebration date).
    CampoExtraido(
        item_key="data_casamento",
        coluna_valor="extracao_data_casamento",
        coluna_confianca="extracao_data_casamento_confianca",
        coluna_rotulo="extracao_data_casamento_rotulo",
        sobrescreve=False,
    ),
    # Resolves NOC-REMEDIATE[nacionalidade-identity-parser] (migration 146).
    # `sobrescreve=False`, on the same terms `genero`/`estado_civil` arrived
    # on: a REGISTRATION field with no second column holding an operator's
    # own spelling, so a typed value outranks a later document reading —
    # never overwritten, only offered as a suggestion.
    CampoExtraido(
        item_key="nacionalidade",
        coluna_valor="extracao_nacionalidade",
        coluna_confianca="extracao_nacionalidade_confianca",
        coluna_rotulo="extracao_nacionalidade_rotulo",
        sobrescreve=False,
    ),
    # Migration 153 — the seed's label-anchored `profession.py` (a certidão
    # de casamento prints it per spouse). `clientes.profissao`'s quintet
    # already existed (137, for matrícula confirmations).
    CampoExtraido(
        item_key="profissao",
        coluna_valor="extracao_profissao",
        coluna_confianca="extracao_profissao_confianca",
        coluna_rotulo="extracao_profissao_rotulo",
        sobrescreve=False,
    ),
)

#: The seven parts of the `endereco_*` group (migration 097's columns), in
#: the order `address.EnderecoLido.PARTES` reads them. ONE provenance quintet
#: (`endereco_origem/_documento_id/_em/_confirmado_por/_confirmado_em`,
#: migration 153) covers all seven.
ENDERECO_PARTES: tuple[str, ...] = (
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
)
ENDERECO_COLUNAS: tuple[str, ...] = tuple(f"endereco_{p}" for p in ENDERECO_PARTES)
#: The `campo` a `cliente_campo_conflitos` row uses for the whole group, and
#: the provenance prefix on `clientes`.
CAMPO_ENDERECO = "endereco"
#: Same for the spouse link (`conjuge_cliente_id`, provenance `conjuge_*`).
CAMPO_CONJUGE = "conjuge_cliente_id"
PREFIXO_CONJUGE = "conjuge"

#: 🔴 `data_emissao` (contract F6) is deliberately NOT a member of `CAMPOS` —
#: see `types.IdentityFields.data_emissao`'s own comment. It is the
#: certidão's OWN issuance date, not a fact about the holder, so there is no
#: `clientes` column for it to promote to and no suggestion to offer through
#: `sugestoes_pendentes` (which is `CAMPOS`-driven). It still rides on
#: `cliente_documentos` — `extracao_data_emissao` / `_confianca` / `_rotulo`
#: — written unconditionally in `extrair_identidade`, exactly like every
#: `CAMPOS` triple, just outside the generic loop. Read back by
#: `certidao_estado_civil_mais_recente` for the office's 90-day-freshness
#: rule.
_COLUNAS_DATA_EMISSAO = (
    "extracao_data_emissao",
    "extracao_data_emissao_confianca",
    "extracao_data_emissao_rotulo",
)

#: Document types `certidao_estado_civil_mais_recente` considers — the two
#: that carry an estado-civil-relevant `data_emissao` (see
#: `TIPOS_LEITURA_INTEGRAL`).
_TIPOS_CERTIDAO_ESTADO_CIVIL = ("certidao_casamento", "certidao_nascimento")

CAMPO_POR_CHAVE: dict[str, CampoExtraido] = {c.item_key: c for c in CAMPOS}

#: Kept as the flat `{item_key: coluna}` mapping earlier callers already read.
CAMPO_POR_ITEM: dict[str, str] = {c.item_key: c.coluna_valor for c in CAMPOS}

#: P0c contract §A.8/§C4 — Serasa Crednet's `nome_mae`, held OUTSIDE the
#: `CAMPOS` tuple deliberately: `extrair_identidade`'s per-document `lidos`
#: dict (`_valores_lidos`/`_lidos_vazios`) is keyed EXACTLY on `CAMPOS`, and
#: no `IdentityFields` (RG/CPF/CNH/certidão) attribute maps to a mother's
#: name — adding it to `CAMPOS` would `KeyError` the very next identity
#: document upload (`_valores_lidos` never populates a `"nome_mae"` key).
#: `CAMPO_POR_CHAVE` still needs to resolve it: `resolver_conflito` (the
#: admin's `PUT /conflitos/{id}/decidir` route) is generic over every
#: `cliente_campo_conflitos` row regardless of which extractor opened it, so
#: it is registered into the SAME lookup table, just not the SAME tuple.
CAMPO_NOME_MAE = CampoExtraido(
    item_key="nome_mae",
    coluna_valor="extracao_nome_mae",
    coluna_confianca="extracao_nome_mae_confianca",
    coluna_rotulo="extracao_nome_mae_rotulo",
    sobrescreve=False,
)
CAMPO_POR_CHAVE["nome_mae"] = CAMPO_NOME_MAE


def deve_extrair(tipo_documento: str) -> bool:
    """Is this a document we read fields from?"""
    return tipo_documento in TIPOS_EXTRAIVEIS


def paginas_maximas(tipo_documento: str) -> int | None:
    """Page cap for this type's vision rung.

    `None` = every page (see `TIPOS_LEITURA_INTEGRAL`); `-1` = "not
    specified", which lets the seed adapter apply its own default. Returning
    the sentinel rather than the literal 3 keeps the default in ONE place —
    the adapter that owns the cost trade-off — instead of copying it here
    where it would silently diverge the day it changes.
    """
    return None if tipo_documento in TIPOS_LEITURA_INTEGRAL else -1


def _valores_lidos(fields: IdentityFields) -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """`item_key -> (valor, confianca, rotulo, pode_persistir)`.

    The ONE place `IdentityFields`' per-field attribute names are mapped onto
    checklist item keys. Everything downstream is generic over `CAMPOS`.

    🔴 `pode_persistir` is "a value was read", at ANY confidence (owner
    decision D1, migration 153). It used to be `persistable_<campo>` — `alta`
    only — which left every low-confidence read off the record entirely, and
    with it every field the contract needed from a vision-read document. The
    confidence is still recorded on the document row, and the field lands
    machine-pending (`confirmado_em IS NULL`), so the contract's validation
    gate — not this function — is where a human vouches for it.
    """
    def item(valor: Any, confianca: Any, rotulo: Optional[str]) -> tuple:
        return (valor, getattr(confianca, "value", confianca), rotulo, bool(valor))

    return {
        "data_nascimento": item(
            fields.data_nascimento.isoformat() if fields.data_nascimento else None,
            fields.data_nascimento_confianca,
            fields.data_nascimento_rotulo,
        ),
        "nome_oficial": item(fields.nome, fields.nome_confianca, fields.nome_rotulo),
        "genero": item(
            canonical_gender(fields.genero) or fields.genero,
            fields.genero_confianca,
            fields.genero_rotulo,
        ),
        "cpf": item(fields.cpf, fields.cpf_confianca, fields.cpf_rotulo),
        "rg": item(fields.rg, fields.rg_confianca, fields.rg_rotulo),
        # The issuer has no label of its own — it is read BESIDE the RG
        # number, so the RG's label is the honest audit trail for it.
        "rg_orgao_expedidor": item(
            fields.rg_orgao,
            fields.rg_orgao_confianca,
            fields.rg_rotulo if fields.rg_orgao else None,
        ),
        "estado_civil": item(
            fields.estado_civil, fields.estado_civil_confianca, fields.estado_civil_rotulo
        ),
        "regime_bens": item(
            fields.regime_bens, fields.regime_bens_confianca, fields.regime_bens_rotulo
        ),
        "data_casamento": item(
            fields.data_casamento.isoformat() if fields.data_casamento else None,
            fields.data_casamento_confianca,
            fields.data_casamento_rotulo,
        ),
        "nacionalidade": item(
            fields.nacionalidade, fields.nacionalidade_confianca, fields.nacionalidade_rotulo
        ),
        "profissao": item(
            fields.profissao, fields.profissao_confianca, fields.profissao_rotulo
        ),
    }


def _lidos_vazios() -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """Every CAMPO absent — what an address-only document contributes."""
    return {c.item_key: (None, "nenhuma", None, False) for c in CAMPOS}


def _lidos_do_conjuge(conjuge: Any, fields: IdentityFields) -> dict[str, tuple]:
    """The OTHER spouse's `lidos`: their own per-person facts off the
    certidão, plus the couple-level facts (estado civil, regime, data do
    casamento), which belong to both spouses equally. Every identity-number
    field this spouse's certidão entry does not carry (rg, issuer) is absent.
    """
    lidos = _lidos_vazios()

    def item(valor: Any, confianca: Any, rotulo: Optional[str]) -> tuple:
        return (valor, getattr(confianca, "value", confianca), rotulo, bool(valor))

    rot = "certidão de casamento (cônjuge)"
    lidos["nome_oficial"] = item(conjuge.nome, "alta", "NOMES")
    lidos["cpf"] = item(conjuge.cpf, conjuge.cpf_confianca, rot)
    lidos["data_nascimento"] = item(
        conjuge.data_nascimento.isoformat() if conjuge.data_nascimento else None,
        conjuge.data_nascimento_confianca, rot,
    )
    lidos["genero"] = item(conjuge.genero, conjuge.genero_confianca, rot)
    lidos["nacionalidade"] = item(conjuge.nacionalidade, conjuge.nacionalidade_confianca, rot)
    lidos["profissao"] = item(conjuge.profissao, conjuge.profissao_confianca, rot)
    comuns = _valores_lidos(fields)
    for chave in ("estado_civil", "regime_bens", "data_casamento"):
        lidos[chave] = comuns[chave]
    return lidos


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


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _mesmo_valor(item_key: str, a: Any, b: Any) -> bool:
    """Do two values of `item_key` state the same FACT?

    Per-field, because "different string" is not "different fact": a CPF with
    and without punctuation, `Masculino` vs the matrícula's `m`, `brasileira`
    vs `brasileiro` (the same nationality in the other grammatical gender),
    `SSP/SP` vs `SSP-SP`. Treating those as disagreements opened conflicts for
    a human to adjudicate about facts that never differed — the noise that
    trains people to click "aceitar" without reading.
    """
    if _vazio(a) or _vazio(b):
        return False
    if item_key == "cpf":
        return only_digits(str(a)) == only_digits(str(b))
    if item_key in ("rg", "rg_orgao_expedidor"):
        return only_alnum(str(a)) == only_alnum(str(b))
    if item_key == "genero":
        ga, gb = canonical_gender(str(a)), canonical_gender(str(b))
        if ga is not None and gb is not None:
            return ga == gb
    if item_key == "nacionalidade":
        na, nb = nacionalidade_canonica(str(a)), nacionalidade_canonica(str(b))
        if na is not None and nb is not None:
            return na == nb
    if item_key == "estado_civil":
        # A human-typed legacy spelling (`Divorciado(a)`, `CASADA`) and the
        # extractor's canonical token (`divorciado`) are one fact — the same
        # normaliser the contract gate reads through. Local import: the
        # checklist service already imports this module.
        from app.modules.card_hub.documento_checklist_service import (
            _estado_civil_normalizado,
        )

        ea, eb = _estado_civil_normalizado(str(a)), _estado_civil_normalizado(str(b))
        if ea is not None and eb is not None:
            return ea == eb
    if item_key in ("data_nascimento", "data_casamento"):
        return str(a)[:10] == str(b)[:10]
    return _mesmo_nome(str(a), str(b))


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


CONFLITOS_TABLE = "cliente_campo_conflitos"


def _conflito_pendente_existente(
    client: Any, org_id: UUID, cliente_id: UUID, campo: str
) -> Optional[dict]:
    return campo_conflitos.conflito_pendente_existente(
        client, campo_conflitos.CLIENTE, org_id, cliente_id, campo
    )


def _registrar_conflito(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    campo: "CampoExtraido | str",
    *,
    valor_anterior: Any,
    origem_anterior: Optional[str],
    valor_proposto: Any,
    origem_proposto: str,
    confianca_proposta: Optional[str],
    fonte_tabela: Optional[str],
    fonte_id: Optional[UUID],
) -> Optional[dict]:
    """Migration 138 (owner directive, 2026-09-18, supersedes part of
    097/110's original design). A `sobrescreve=False` field that DISAGREES
    with what is already on `clientes` is no longer a silent skip: it opens
    (or reuses) a `cliente_campo_conflitos` row for an admin to adjudicate
    via `resolver_conflito`. `valor_anterior` is snapshotted HERE, once, and
    never touched again — the "way back" the directive requires.

    Returns the NEW row when one was actually inserted (so the caller can
    notify), or `None` when a pending conflict for this (cliente, campo)
    already existed — the partial UNIQUE index would refuse a second insert
    anyway; checking first avoids a doomed write AND a duplicate
    notification for a conflict an admin hasn't looked at yet.

    The open/dedupe mechanics are `app.services.campo_conflitos`' (P0c
    contract §H6, the N=3 formalization shared with `imovel_hub.
    campos_extraidos_service` and `app.modules.empresas`) — this wrapper
    keeps the historical `CampoExtraido | str` signature every caller here
    already uses.
    """
    chave = campo if isinstance(campo, str) else campo.item_key
    return campo_conflitos.registrar_conflito(
        client, campo_conflitos.CLIENTE, org_id, cliente_id, chave,
        valor_anterior=valor_anterior,
        origem_anterior=origem_anterior,
        valor_proposto=valor_proposto,
        origem_proposto=origem_proposto,
        confianca_proposta=confianca_proposta,
        fonte_tabela=fonte_tabela,
        fonte_id=fonte_id,
    )


def aplicar_campos_ao_cliente(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    origem: str,
    lidos: dict[str, tuple[Any, str, Optional[str], bool]],
    *,
    campos: tuple[CampoExtraido, ...] = CAMPOS,
    documento_id: Optional[UUID] = None,
    fonte_tabela: Optional[str] = None,
    fonte_id: Optional[UUID] = None,
    confirmado_por: Optional[Any] = None,
) -> tuple[dict[str, bool], list[dict]]:
    """Write what may be written onto the client record — owner decision D1.

    Generic over `campos`/`lidos` (migration 137) so a second source reuses
    the SAME field-level mechanics without forking this function.
    `extrair_identidade` is one caller (`campos=CAMPOS`); `app.modules
    .matriculas.qualificacao_service.confirmar` is another
    (`campos=CAMPOS_QUALIFICACAO`).

    🔴 D1 (migration 153, supersedes 110/138's policy on this path):

    - **Field EMPTY -> filled**, at any confidence, with provenance:
      `<campo>_origem=origem`, `_documento_id`, `_em`, and
      `_confirmado_por/_em` NULL — machine-pending, for the contract's
      validation gate — unless `confirmado_por` is given (a human just
      vouched for this source, e.g. a matrícula qualification they
      confirmed), in which case it is stamped confirmed.
    - **Field already SET and the reading DIFFERS -> conflict**, never an
      overwrite: whether the value was typed by a human or written by an
      earlier extraction, a `cliente_campo_conflitos` row opens (returned, so
      the caller notifies an admin). `nome_oficial` included — the old
      `sobrescreve=True` "newest document wins" is gone.
    - **Same fact, still machine-pending, and a human now vouches for it
      (`confirmado_por` given) -> promoted to confirmed**, `updates`-only on
      `_confirmado_por/_em`: a matrícula qualification auto-applied
      machine-pending (`persistir_sugestoes` -> `_aplicar_automatico`,
      `confirmado_por=None`) and a human later clicking `confirmar` on that
      SAME reading must not silently do nothing just because the value was
      already there — that would leave it machine-pending forever, invisible
      to `confirmar`'s own return payload, even though a human DID look at
      it. Provenance (`origem`/`documento_id`/`em`) is left exactly as the
      machine wrote it: confirming does not change WHO supplied the value,
      only that it is now reviewed — the same thing `contrato_gerador
      .validacao_extracao._patch_aceite` does generically for the D2 gate,
      reached here through this module's own confirm action instead.
      Already-confirmed -> nothing (re-confirming does not re-stamp).
    - **Same fact, no `confirmado_por` given -> nothing** (`_mesmo_valor`,
      per field) — the ordinary machine-vs-machine agreement case.
    - An operator who explicitly typed then CLEARED a field
      (`origem='manual'`, value empty) is still respected: that was a human
      decision about the field, and the reading stays on the document as a
      suggestion (`sugestoes_pendentes`).

    `documento_id=None` means this source has no `cliente_documentos` row to
    point at — the column is written as an explicit NULL.

    Returns `({item_key: foi_aplicado}, [conflito, ...])` — the second list
    holds every NEWLY opened conflict (this function never does async I/O;
    `notificar_conflitos` is the caller's next step).
    """
    colunas: list[str] = ["id"]
    for campo in campos:
        colunas += [campo.item_key, campo.origem, campo.confirmado_em]
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(dict.fromkeys(colunas)))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {c.item_key: False for c in campos}, []

    atual = rows[0]
    updates: dict[str, Any] = {}
    aplicados: dict[str, bool] = {}
    conflitos: list[dict] = []
    now = _now()

    for campo in campos:
        valor, confianca, _rotulo, pode = lidos.get(
            campo.item_key, (None, "nenhuma", None, False)
        )
        aplicados[campo.item_key] = False
        if not pode or _vazio(valor):
            continue
        if campo.item_key == "genero":
            valor = canonical_gender(str(valor)) or valor

        if campo.depende_de:
            # Only beside the value it was read with — see `depende_de`.
            lido_dep = lidos.get(campo.depende_de, (None,))[0]
            final_dep = updates.get(campo.depende_de, atual.get(campo.depende_de))
            if not _mesmo_valor(campo.depende_de, final_dep, lido_dep):
                continue

        # 🔴 An RG equal to the CPF is APPLIED, not declined — the new
        # Carteira de Identidade Nacional (CIN) uses the CPF number as the
        # identity number by design (contract 08's "TAUANE GONÇALVES DIAS
        # ... RG 448.864.938-66-IIGDR-SP e inscrita no CPF/MF
        # 448.864.938-66"). The contract-generation gate still shows it:
        # `contrato_gerador.derivacao._partes` raises `av.avisa("RG_IGUAL_
        # CPF", ...)`, never a block.
        presente = atual.get(campo.item_key)
        if not _vazio(presente):
            if not _mesmo_valor(campo.item_key, presente, valor):
                novo = _registrar_conflito(
                    client, org_id, cliente_id, campo,
                    valor_anterior=presente,
                    origem_anterior=atual.get(campo.origem),
                    valor_proposto=valor,
                    origem_proposto=origem,
                    confianca_proposta=confianca,
                    fonte_tabela=fonte_tabela,
                    fonte_id=fonte_id,
                )
                if novo is not None:
                    conflitos.append(novo)
            elif confirmado_por and _vazio(atual.get(campo.confirmado_em)):
                # Same fact, still machine-pending, a human now vouches for
                # it — promote to confirmed. See the docstring's D1 bullet.
                updates[campo.confirmado_por] = str(confirmado_por)
                updates[campo.confirmado_em] = now
                aplicados[campo.item_key] = True
            continue
        if atual.get(campo.origem) == "manual":
            continue

        updates[campo.item_key] = valor
        updates[campo.origem] = origem
        updates[campo.documento_id] = str(documento_id) if documento_id else None
        updates[campo.em] = now
        updates[campo.confirmado_por] = str(confirmado_por) if confirmado_por else None
        updates[campo.confirmado_em] = now if confirmado_por else None
        aplicados[campo.item_key] = True

    if updates:
        updates["updated_at"] = now
        _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()

    return aplicados, conflitos


# ─── The endereço group (migration 153) ──────────────────────────────────────


def _endereco_json(partes: dict[str, Any], **extra: Any) -> str:
    """A group value as the TEXT a `cliente_campo_conflitos` row holds —
    JSON, so `resolver_conflito` can write the seven parts back exactly and
    the admin notification still reads as the address it is."""
    corpo = {p: partes.get(p) for p in ENDERECO_PARTES}
    corpo.update({k: v for k, v in extra.items() if v is not None})
    return json.dumps(corpo, ensure_ascii=False)


def _mesmo_endereco(atual: dict[str, Any], proposto: dict[str, Any]) -> bool:
    """Same address iff every part the reading HAS agrees with the record.
    A part the reading lacks (no complemento on the bill) is not a
    disagreement."""
    for parte in ENDERECO_PARTES:
        novo = proposto.get(parte)
        if _vazio(novo):
            continue
        velho = atual.get(f"endereco_{parte}")
        if _vazio(velho):
            return False
        if parte == "cep":
            if only_digits(str(velho)) != only_digits(str(novo)):
                return False
        elif not _mesmo_nome(str(velho), str(novo)):
            return False
    return True


def aplicar_endereco_ao_cliente(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    origem: str,
    partes: dict[str, Any],
    *,
    titular_documento: Optional[str] = None,
    confianca: Optional[str] = None,
    documento_id: Optional[UUID] = None,
) -> tuple[bool, Optional[dict]]:
    """Apply one comprovante's address to the cliente as ONE group (D1).

    - The comprovante prints a holder whose name does NOT match this cliente
      (a bill in a spouse's or a parent's name, routinely) -> conflict, never
      a silent fill. The proposed value records whose name the bill carries.
    - Group EMPTY -> all seven parts written, `endereco_*` provenance,
      machine-pending.
    - Group SET and the reading differs -> conflict; same -> nothing.
    - Human-cleared group (`endereco_origem='manual'`, all parts empty) ->
      respected, like any other field.

    Returns `(aplicado, conflito_novo_ou_None)`.
    """
    if _vazio(partes.get("cep")) or _vazio(partes.get("logradouro")):
        return False, None
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(["id", "nome", "nome_completo", "nome_oficial",
                          "endereco_origem", *ENDERECO_COLUNAS]))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return False, None
    atual = rows[0]
    anterior = {p: atual.get(f"endereco_{p}") for p in ENDERECO_PARTES}
    tem_endereco = any(not _vazio(v) for v in anterior.values())

    def conflito() -> Optional[dict]:
        return _registrar_conflito(
            client, org_id, cliente_id, CAMPO_ENDERECO,
            valor_anterior=_endereco_json(anterior) if tem_endereco else None,
            origem_anterior=atual.get("endereco_origem"),
            valor_proposto=_endereco_json(partes, titular=titular_documento),
            origem_proposto=origem,
            confianca_proposta=confianca,
            fonte_tabela=DOCUMENTOS_TABLE if documento_id else None,
            fonte_id=documento_id,
        )

    if titular_documento:
        nomes = [atual.get("nome_oficial"), atual.get("nome_completo"), atual.get("nome")]
        if not any(nomes_compativeis(titular_documento, n) for n in nomes if n):
            return False, conflito()

    if tem_endereco:
        if _mesmo_endereco(atual, partes):
            return False, None
        return False, conflito()
    if atual.get("endereco_origem") == "manual":
        return False, None

    now = _now()
    updates: dict[str, Any] = {
        f"endereco_{p}": (None if _vazio(partes.get(p)) else partes.get(p))
        for p in ENDERECO_PARTES
    }
    updates.update(
        {
            "endereco_origem": origem,
            "endereco_documento_id": str(documento_id) if documento_id else None,
            "endereco_em": now,
            "endereco_confirmado_por": None,
            "endereco_confirmado_em": None,
            "updated_at": now,
        }
    )
    _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()
    return True, None


# ─── The spouse link (migration 153) ─────────────────────────────────────────


def vincular_conjuges(
    client: Any,
    org_id: UUID,
    cliente_a: UUID,
    cliente_b: UUID,
    *,
    origem: str,
    documento_id: Optional[UUID] = None,
) -> list[dict]:
    """Link two clientes as spouses, RECIPROCALLY, under D1.

    Each side independently: empty `conjuge_cliente_id` -> set (with
    `conjuge_*` provenance, machine-pending); already the other one ->
    nothing; linked to SOMEONE ELSE -> conflict (a remarriage, a stale link —
    a human decides). A human-cleared link (`conjuge_origem='manual'`, empty)
    is respected. Returns the newly opened conflicts.
    """
    if str(cliente_a) == str(cliente_b):
        return []
    conflitos: list[dict] = []
    now = _now()
    for eu, outro in ((cliente_a, cliente_b), (cliente_b, cliente_a)):
        rows = (
            _t(client, CLIENTES_TABLE)
            .select("id,conjuge_cliente_id,conjuge_origem")
            .eq("org_id", str(org_id))
            .eq("id", str(eu))
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            continue
        atual = rows[0]
        vinculo = atual.get("conjuge_cliente_id")
        if vinculo:
            if str(vinculo) != str(outro):
                novo = _registrar_conflito(
                    client, org_id, eu, CAMPO_CONJUGE,
                    valor_anterior=str(vinculo),
                    origem_anterior=atual.get("conjuge_origem"),
                    valor_proposto=str(outro),
                    origem_proposto=origem,
                    confianca_proposta=None,
                    fonte_tabela=DOCUMENTOS_TABLE if documento_id else None,
                    fonte_id=documento_id,
                )
                if novo is not None:
                    conflitos.append(novo)
            continue
        if atual.get("conjuge_origem") == "manual":
            continue
        _t(client, CLIENTES_TABLE).update(
            {
                "conjuge_cliente_id": str(outro),
                "conjuge_origem": origem,
                "conjuge_documento_id": str(documento_id) if documento_id else None,
                "conjuge_em": now,
                "conjuge_confirmado_por": None,
                "conjuge_confirmado_em": None,
                "updated_at": now,
            }
        ).eq("id", str(eu)).execute()
    return conflitos


# ─── Admin notification (migration 138's queue, now announced) ──────────────


async def notificar_conflitos(
    client: Any,
    org_id: Any,
    conflitos: list[dict],
    notification_service: Optional[Any],
    *,
    cliente_nome: Optional[str] = None,
) -> int:
    """Announce every NEWLY opened conflict to the org's admins.

    The ONE notification path for `cliente_campo_conflitos` — used by the
    unattended document extraction here AND by `matriculas.
    qualificacao_service.confirmar` (it used to carry its own copy of this
    loop). Best-effort per conflict: a down WhatsApp session or SMTP server
    is logged with its traceback and never fails the extraction that
    raised the conflict — the row itself is already committed and listed by
    `conflitos_pendentes`. `notificado_em` is stamped only on success, so an
    un-announced conflict stays identifiable.

    `notification_service=None` with conflicts to announce is logged as a
    WARNING naming them — never silent.

    The loop/try-except/`notificado_em` stamp is `app.services.
    campo_conflitos.notificar_conflitos`'s (P0c contract §H6) — this
    function keeps only the parts that ARE specific to `cliente_campo_
    conflitos`: this exact "no notifier" wording, and resolving (and
    caching) the cliente's display name per conflict before handing it to
    `notify_field_conflict`.
    """
    if not conflitos:
        return 0
    if notification_service is None:
        logger.warning(
            "%d conflito(s) aberto(s) sem notification_service — registrados, "
            "não anunciados: %s",
            len(conflitos), [c.get("campo") for c in conflitos],
        )
        return 0
    nomes: dict[str, str] = {}

    async def _notify_one(conflito: dict) -> None:
        nome = cliente_nome
        if nome is None:
            cid = str(conflito.get("cliente_id"))
            if cid not in nomes:
                rows = (
                    _t(client, CLIENTES_TABLE)
                    .select("nome,nome_oficial")
                    .eq("org_id", str(org_id))
                    .eq("id", cid)
                    .limit(1)
                    .execute()
                ).data or []
                linha = rows[0] if rows else {}
                nomes[cid] = linha.get("nome_oficial") or linha.get("nome") or ""
            nome = nomes[cid]
        await notification_service.notify_field_conflict(
            org_id=org_id, conflito=conflito, cliente_nome=nome
        )

    return await campo_conflitos.notificar_conflitos(
        client, campo_conflitos.CLIENTE, conflitos, _notify_one
    )


def conflitos_pendentes(
    client: Any, org_id: UUID, cliente_id: Optional[UUID] = None
) -> list[dict]:
    """The admin's queue — every unresolved `cliente_campo_conflitos` row,
    newest first. `cliente_id=None` lists every pending conflict in the org."""
    query = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("status", "pendente")
    )
    if cliente_id is not None:
        query = query.eq("cliente_id", str(cliente_id))
    rows = query.execute().data or []
    return sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)


def resolver_conflito(
    client: Any, org_id: UUID, conflito_id: UUID, *, aceitar: bool, decidido_por: Optional[UUID]
) -> dict:
    """An admin decides a pending conflict (migration 138).

    ACCEPT: the proposed (extracted) value overwrites `clientes.<campo>` —
    the same provenance-quintet write `confirmar_sugestao` already makes for
    a human-vouched value, `confirmado_por=decidido_por` because an admin is
    exactly that. `valor_anterior` on the conflict row is left untouched —
    it is the permanent way back, not a working copy to clear.

    REJECT: `clientes` is not touched at all — the value already there (the
    human input, or whatever prevailed before) simply keeps prevailing.

    Refuses (`ValidationError_`) a conflict that already has a decision —
    an admin's decision, once made, is not silently replaced by a second
    click.

    Group fields (migration 153): `campo='endereco'` writes the seven
    `endereco_*` parts from the JSON `valor_proposto` plus the `endereco_*`
    quintet; `campo='conjuge_cliente_id'` writes the link plus `conjuge_*`.

    (Was NOC-REMEDIATE[identidade-conflito-notificacao]: the background
    extraction now announces its conflicts through `notificar_conflitos`,
    the same path `qualificacao_service.confirmar` uses.)
    """
    rows = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(conflito_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(CONFLITOS_TABLE, str(conflito_id))
    conflito = rows[0]
    if conflito.get("status") != "pendente":
        raise ValidationError_(
            "Este conflito já foi decidido.", field="status"
        )

    now = _now()
    patch: dict[str, Any] = {
        "status": "aceito" if aceitar else "rejeitado",
        "decidido_por": str(decidido_por) if decidido_por else None,
        "decidido_em": now,
    }
    _t(client, CONFLITOS_TABLE).update(patch).eq("id", str(conflito_id)).execute()

    if aceitar:
        campo = CAMPO_POR_CHAVE.get(conflito["campo"])
        item_key = conflito["campo"]
        documento_fonte = (
            conflito.get("fonte_id")
            if conflito.get("fonte_tabela") == DOCUMENTOS_TABLE
            else None
        )
        quem = str(decidido_por) if decidido_por else None
        updates: dict[str, Any] = {"updated_at": now}
        if item_key == CAMPO_ENDERECO:
            proposto = json.loads(conflito["valor_proposto"])
            for parte in ENDERECO_PARTES:
                updates[f"endereco_{parte}"] = proposto.get(parte)
            prefixo = "endereco"
        elif item_key == CAMPO_CONJUGE:
            updates[CAMPO_CONJUGE] = conflito["valor_proposto"]
            prefixo = PREFIXO_CONJUGE
        else:
            updates[item_key] = conflito["valor_proposto"]
            prefixo = campo.item_key if campo is not None else None
        if prefixo is not None:
            updates[f"{prefixo}_origem"] = conflito["origem_proposto"]
            updates[f"{prefixo}_documento_id"] = documento_fonte
            updates[f"{prefixo}_em"] = now
            updates[f"{prefixo}_confirmado_por"] = quem
            updates[f"{prefixo}_confirmado_em"] = now
        else:
            # A field outside identidade_extracao_service.CAMPOS (e.g. a
            # future CAMPOS_QUALIFICACAO-only entry with no quintet of its
            # own) — write the bare value; no provenance columns to also set.
            logger.warning(
                "resolver_conflito: campo %r has no CAMPOS quintet — writing "
                "the bare value only", item_key,
            )
        _t(client, CLIENTES_TABLE).update(updates).eq(
            "id", str(conflito["cliente_id"])
        ).execute()

    return {**conflito, **patch}


def _titular_do_card(
    client: Any, org_id: UUID, cliente_id: UUID
) -> Optional[TitularEsperado]:
    """The card's own person, as the extractor's titular hint.

    `nome_oficial` (a document-read spelling) before `nome` (whatever the
    operator typed), plus the CPF when one is on file. A lookup failure
    returns None — the extraction then runs exactly as it did before the
    hint existed — but it is logged, never swallowed.
    """
    try:
        rows = (
            _t(client, CLIENTES_TABLE)
            .select("nome, nome_oficial, cpf")
            .eq("org_id", str(org_id))
            .eq("id", str(cliente_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 - detached job; degrade, log
        logger.warning("extracao: titular lookup failed for %s: %s", cliente_id, exc)
        return None
    if not rows:
        return None
    row = rows[0]
    nome = row.get("nome_oficial") or row.get("nome")
    cpf = row.get("cpf")
    if not nome and not cpf:
        return None
    return TitularEsperado(nome=nome, cpf=cpf)


async def extrair_identidade(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    extractor: Optional[Any] = None,
    notification_service: Optional[Any] = None,
) -> dict:
    """Read one identity document and record the outcome. Never raises.

    `notification_service` announces every conflict this read opens
    (`notificar_conflitos`); the routes and the sweep pass
    `deps.get_conflict_notification_service()`.

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

    # P0c contract §C3: Serasa Crednet's reading is not an `IdentityFields`
    # at all (own dataclass, own D1 fields, own empresas/certidão side
    # effects) — `crednet_service.aplicar_leitura` owns every step past the
    # blob read + access log above; the sweep and re-run inherit this branch
    # for free, since both call THIS function.
    if str(doc.get("tipo_documento")) == "serasa_crednet":
        from app.modules.card_hub import crednet_service

        crednet_extractor = extractor
        if crednet_extractor is None:
            from app.modules.card_hub.deps import _build_identity_extractor

            crednet_extractor = _build_identity_extractor(str(org_id), "serasa_crednet")
        return await crednet_service.aplicar_leitura(
            client, org_id, cliente_id, documento_id, doc, blob.data,
            extractor=crednet_extractor,
            notification_service=notification_service,
        )

    # 🔴 The page cap is chosen from the document's TYPE, not from a global
    # default — see `TIPOS_LEITURA_INTEGRAL`. A certidão de casamento must be
    # read whole or its averbação (the divorce) never reaches the model, and
    # the answer flips rather than degrades.
    #
    # This fallback is exercised directly by a caller with no pre-built
    # extractor (a test, or a future caller with none to offer) — every REAL
    # caller today (`router.upload_documento_route`,
    # `router.reextrair_documento_route`, and `varrer_extracoes_pendentes`'s
    # sweep) instead passes one pre-built through
    # `deps.get_identity_extractor_factory()`, which is ALSO keyed on
    # `tipo_documento` (2026-09-20 fix) — so both paths apply the same
    # `paginas_maximas` policy, and a certidão de casamento is read whole
    # regardless of which one built the extractor.
    extractor = extractor or make_identity_extractor(
        real=True,
        org_id=str(org_id),
        max_pages=paginas_maximas(str(doc.get("tipo_documento") or "")),
        provider=resolve_vision_provider(str(org_id)),
    )
    # The document was uploaded onto ONE person's card — tell the extractor
    # who, so a two-titular certidão de casamento selects that spouse's name
    # and CPF instead of declining both. A selector only: the extractor
    # returns a hinted value solely when the document printed it.
    fields: IdentityFields = await extractor.extract(
        blob.data,
        mimetype=doc.get("mime_type"),
        filename=doc.get("nome_original"),
        titular=_titular_do_card(client, org_id, cliente_id),
    )
    if fields.aviso:
        # Not a failure — the result is persisted below. Recorded so the
        # withheld fields are explainable from the logs.
        logger.info(
            "extracao %s: aviso %s — %s",
            documento_id, fields.aviso, fields.aviso_mensagem,
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

    tipo = str(doc["tipo_documento"])
    so_endereco = tipo in TIPOS_ENDERECO
    # An address document contributes its address and nothing else — see
    # `TIPOS_ENDERECO`. Its name/CPF are the bill holder's.
    lidos = _lidos_vazios() if so_endereco else _valores_lidos(fields)
    endereco = fields.endereco if so_endereco else None
    data_emissao = (
        fields.data_emissao.isoformat() if fields.data_emissao and not so_endereco else None
    )
    conjuges = [] if so_endereco else list(fields.conjuges or ())
    achou_algo = (
        data_emissao is not None
        or endereco is not None
        or bool(conjuges)
        or any(v is not None for v, _, _, _ in lidos.values())
    )

    # 🔴 MISFILE DETECTION — FLAGS, NEVER RETYPES (2026-09-23, owner
    # directive). Two independent signals, both content-only, both never
    # writing `tipo_documento` — a human confirms via the existing card_hub
    # UI, same posture as every other `aviso` in this family:
    #
    # 1. `fields.tipo_provavel` disagrees with the declared `tipo`. Real,
    #    measured: at least two CNHs were uploaded typed `rg`, read fine by
    #    this type-agnostic extractor (so the field yield never looked
    #    wrong), and nothing anywhere noticed the mismatch. `None` means no
    #    marker was recognised — NOT a claim of disagreement, so it never
    #    logs as one (see `classificar_tipo_provavel`'s own docstring).
    # 2. No marker recognised AT ALL (`tipo_provavel is None`) on a
    #    supposedly-identity `tipo` that came back with NOTHING extracted
    #    (`not achou_algo`) — a real-estate "roteiro" and an ads report have
    #    both been uploaded typed `rg` in production. Scoped OFF
    #    `TIPOS_ENDERECO`: this module has no positive address-content
    #    marker (see `classificar_tipo_provavel`'s scope note), so an
    #    ordinary illegible comprovante would otherwise flag on this signal
    #    alone for a reason that has nothing to do with misfiling.
    if fields.tipo_provavel and fields.tipo_provavel != tipo:
        logger.warning(
            "extracao %s: possivel tipo_documento incorreto — declarado=%s "
            "provavel=%s (documento nao foi retipado)",
            documento_id, tipo, fields.tipo_provavel,
        )
    elif fields.tipo_provavel is None and not achou_algo and not so_endereco:
        logger.warning(
            "extracao %s: nenhum marcador de identidade reconhecido para "
            "tipo declarado=%s e nada foi extraido (documento nao foi "
            "retipado)",
            documento_id, tipo,
        )

    # Recorded whether or not it lands on the client — the `_confianca` and
    # `_rotulo` columns let a human audit the reasoning without re-opening the
    # document (another logged access).
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
    # `data_emissao` rides outside the `CAMPOS` loop — see its own comment
    # above `_TIPOS_CERTIDAO_ESTADO_CIVIL`. Recorded on the document row the
    # same as every other extracted value, unconditionally; never promoted.
    marcacoes["extracao_data_emissao"] = data_emissao
    marcacoes["extracao_data_emissao_confianca"] = fields.data_emissao_confianca.value
    marcacoes["extracao_data_emissao_rotulo"] = fields.data_emissao_rotulo
    partes_endereco = endereco.partes() if endereco is not None else {}
    for parte in ENDERECO_PARTES:
        marcacoes[f"extracao_endereco_{parte}"] = partes_endereco.get(parte)
    marcacoes["extracao_endereco_titular"] = endereco.titular if endereco else None
    marcacoes["extracao_endereco_confianca"] = endereco.confianca if endereco else None
    marcacoes["extracao_endereco_rotulo"] = endereco.rotulo if endereco else None
    # Recorded BEFORE anything touches the client record, so a failure while
    # applying still leaves the reading (and a terminal status) on the
    # document rather than a row stuck in `processando`.
    _marcar(client, documento_id, **marcacoes)

    conflitos: list[dict] = []
    aplicados, abertos = aplicar_campos_ao_cliente(
        client,
        org_id,
        cliente_id,
        tipo,
        lidos,
        documento_id=documento_id,
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=documento_id,
    )
    conflitos += abertos

    if endereco is not None:
        aplicado_end, conflito_end = aplicar_endereco_ao_cliente(
            client, org_id, cliente_id, tipo, partes_endereco,
            titular_documento=endereco.titular,
            confianca=endereco.confianca,
            documento_id=documento_id,
        )
        aplicados[CAMPO_ENDERECO] = aplicado_end
        if conflito_end is not None:
            conflitos.append(conflito_end)

    # 🔴 BOTH SPOUSES (migration 153). The spouse the card belongs to was
    # applied above (the extractor's `titular` hint selected them and carried
    # their per-person facts onto `fields`). The OTHER spouse fills the
    # cliente they already are in this product — linked as `conjuge`, or a
    # party on one of this cliente's cards whose name/CPF matches — and
    # nobody is ever CREATED from a certidão: an unmatched spouse is recorded
    # on the document row (`extracao_conjuges`) and nothing more.
    registro_conjuges: list[dict] = []
    if conjuges:
        outro_id: Optional[str] = None
        titular_idx = next((i for i, c in enumerate(conjuges) if c.titular), None)
        if titular_idx is not None and len(conjuges) == 2:
            outro = conjuges[1 - titular_idx]
            outro_id = _cliente_do_outro_conjuge(client, org_id, cliente_id, outro)
            if outro_id is not None:
                _, abertos_outro = aplicar_campos_ao_cliente(
                    client, org_id, UUID(outro_id), tipo,
                    _lidos_do_conjuge(outro, fields),
                    documento_id=documento_id,
                    fonte_tabela=DOCUMENTOS_TABLE,
                    fonte_id=documento_id,
                )
                conflitos += abertos_outro
                conflitos += vincular_conjuges(
                    client, org_id, cliente_id, UUID(outro_id),
                    origem=tipo, documento_id=documento_id,
                )
        for i, c in enumerate(conjuges):
            if c.titular:
                alvo: Optional[str] = str(cliente_id)
            elif titular_idx is not None:
                alvo = outro_id
            else:
                alvo = None
            registro_conjuges.append(
                {
                    "nome": c.nome,
                    "cpf": c.cpf,
                    "data_nascimento": (
                        c.data_nascimento.isoformat() if c.data_nascimento else None
                    ),
                    "nacionalidade": c.nacionalidade,
                    "profissao": c.profissao,
                    "genero": c.genero,
                    "titular": bool(c.titular),
                    "cliente_id": alvo,
                }
            )
        _marcar(client, documento_id, extracao_conjuges=registro_conjuges)

    if conflitos:
        logger.info(
            "extracao %s: %d campo(s) opened an admin conflict instead of "
            "applying unattended: %s",
            documento_id, len(conflitos), [c["campo"] for c in conflitos],
        )
        await notificar_conflitos(client, org_id, conflitos, notification_service)
    return {
        "status": "ok" if achou_algo else "sem_dados",
        "data_nascimento": lidos["data_nascimento"][0],
        "nome_oficial": lidos["nome_oficial"][0],
        "confianca": lidos["data_nascimento"][1],
        "confianca_nome": lidos["nome_oficial"][1],
        "fonte": fields.source.value,
        "tentativas": tentativas,
        "aplicado_ao_cliente": aplicados,
        "conflitos_abertos": [c["campo"] for c in conflitos],
        "conjuges": registro_conjuges,
    }


def _pessoas_dos_cards(client: Any, org_id: UUID, cliente_id: UUID) -> list[str]:
    """Every OTHER person on any card this cliente is on — the titular of the
    atendimento and its `atendimento_partes` — as cliente ids."""
    atendimentos: set[str] = set()
    for row in (
        _t(client, "atendimentos")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []:
        atendimentos.add(str(row["id"]))
    for row in (
        _t(client, "atendimento_partes")
        .select("atendimento_id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []:
        atendimentos.add(str(row["atendimento_id"]))
    if not atendimentos:
        return []
    ids = list(atendimentos)
    pessoas: set[str] = set()
    for row in (
        _t(client, "atendimentos")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .in_("id", ids)
        .execute()
    ).data or []:
        if row.get("cliente_id"):
            pessoas.add(str(row["cliente_id"]))
    for row in (
        _t(client, "atendimento_partes")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .in_("atendimento_id", ids)
        .execute()
    ).data or []:
        pessoas.add(str(row["cliente_id"]))
    pessoas.discard(str(cliente_id))
    return sorted(pessoas)


def _e_a_pessoa(row: dict, conjuge: Any) -> bool:
    """Is this cliente row the spouse the certidão names? CPF when both
    sides have one (decisive either way), else the name."""
    if conjuge.cpf and row.get("cpf"):
        return only_digits(str(row["cpf"])) == only_digits(conjuge.cpf)
    nomes = [row.get("nome_oficial"), row.get("nome_completo"), row.get("nome")]
    return any(nomes_compativeis(conjuge.nome, n) for n in nomes if n)


def _cliente_do_outro_conjuge(
    client: Any, org_id: UUID, cliente_id: UUID, conjuge: Any
) -> Optional[str]:
    """The existing cliente the NON-titular spouse is, or None.

    1. The cliente already linked as this one's `conjuge_cliente_id` — only
       if it IS the person the certidão names (an old certidão from a
       previous marriage must not fill the current spouse's record).
    2. Else exactly one person on this cliente's cards who matches.
    Never creates a cliente.
    """
    colunas = "id,nome,nome_completo,nome_oficial,cpf"
    proprio = (
        _t(client, CLIENTES_TABLE)
        .select("id,conjuge_cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    vinculo = proprio[0].get("conjuge_cliente_id") if proprio else None
    if vinculo:
        rows = (
            _t(client, CLIENTES_TABLE)
            .select(colunas)
            .eq("org_id", str(org_id))
            .eq("id", str(vinculo))
            .limit(1)
            .execute()
        ).data or []
        if rows and _e_a_pessoa(rows[0], conjuge):
            return str(rows[0]["id"])

    candidatos = _pessoas_dos_cards(client, org_id, cliente_id)
    if not candidatos:
        return None
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(colunas)
        .eq("org_id", str(org_id))
        .in_("id", candidatos)
        .execute()
    ).data or []
    achados = [r for r in rows if _e_a_pessoa(r, conjuge)]
    return str(achados[0]["id"]) if len(achados) == 1 else None


# ─── The sweep: what happens when the process dies mid-read (migration 072) ──


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


_COLUNAS_VARREDURA = (
    "id,org_id,cliente_id,tipo_documento,extracao_status,"
    "extracao_tentativas,extracao_em,created_at"
)


def _candidatos_varredura(client: Any, limite: int) -> list[dict]:
    """The three kinds of row the sweep owns, oldest-first, de-duplicated.

    1. `pendente`/`processando` whose `extracao_em` is older than
       `STALE_APOS` — a job that started and died.
    2. `pendente` with `extracao_em IS NULL` whose `created_at` is older than
       `STALE_APOS` — 🔴 a job that NEVER started. `upload_documento` stamps
       `pendente` without an `extracao_em`, and the old single query's
       `extracao_em <= cutoff` silently excluded NULL, so exactly the rows
       migration 072 promised to recover (the worker died before the
       BackgroundTask ran) were never picked up. Aged on `created_at` so the
       sweep never races an upload whose task is about to run.
    3. `erro` rows with retries left (D3): `extracao_tentativas <
       MAX_TENTATIVAS` — the first attempt plus at most
       `MAX_RETENTATIVAS_ERRO` automatic retries — aged on `extracao_em` so a
       failure is not retried the minute it happens.

    Three explicit queries rather than one `.or_()` expression: each bound is
    then a real, individually-tested filter.
    """
    cutoff = _stale_cutoff()
    base = lambda: (  # noqa: E731
        _t(client, DOCUMENTOS_TABLE).select(_COLUNAS_VARREDURA).is_("deleted_at", "null")
    )
    parados = (
        base()
        .in_("extracao_status", list(_ESTADOS_NAO_TERMINAIS))
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    nunca_iniciados = (
        base()
        .eq("extracao_status", "pendente")
        .is_("extracao_em", "null")
        .lte("created_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    com_erro = (
        base()
        .eq("extracao_status", "erro")
        .lt("extracao_tentativas", MAX_TENTATIVAS)
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    vistos: set[str] = set()
    linhas: list[dict] = []
    for row in [*parados, *nunca_iniciados, *com_erro]:
        chave = str(row["id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(row)
    linhas.sort(key=lambda r: r.get("extracao_em") or r.get("created_at") or "")
    return linhas[:limite]


#: NOC-REMEDIATE[dry-extracao-varredura]: same shape as `imovel_hub.
#: matricula_extracao_service.varrer_pendentes` — see that function's own
#: marker (S2 contract §E3.3) — 2026-09-25.
async def varrer_extracoes_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
    notification_service: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    """Re-run extractions that were started and never finished — and, since
    D3 (2026-09-22), retry a FAILED one at most twice.

    🔴 WHY THIS EXISTS AT ALL. `extracao_status` moves to `processando` before
    the work and to a terminal value after it. If the process dies in between —
    a deploy, an OOM kill, a container restart — nothing ever moves it again.
    The document sits there, the checklist item never ticks, and NOTHING
    SURFACES. The same is true of `pendente` if the BackgroundTask was never
    scheduled because the request handler's process went away first.

    Which rows: see `_candidatos_varredura`. Two bounds keep this from
    becoming its own problem:

    - **Age.** Only documents idle longer than `STALE_APOS` are touched, so
      the sweep can never race a job that is simply still working.
    - **Attempts.** `MAX_TENTATIVAS` caps how many times one document is
      started (first attempt + `MAX_RETENTATIVAS_ERRO` retries). A stalled
      row that has exhausted it is moved to a terminal `erro` a human can see;
      an `erro` row that has exhausted it is simply no longer selected — it
      stays `erro` until a human re-runs it.
    """
    rows = _candidatos_varredura(client, limite)

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
            tipo_documento = str(row.get("tipo_documento") or "")
            extractor = (
                extractor_factory(str(org_id), tipo_documento)
                if extractor_factory
                else None
            )
            await extrair_identidade(
                client, storage, org_id, cliente_id, documento_id,
                extractor=extractor,
                notification_service=notification_service,
            )
            retomados += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.warning("sweep: documento %s failed: %s", documento_id, exc)
            falhas += 1

    if rows:
        logger.info(
            "extracao sweep: %d candidate(s), %d retried, %d exhausted, %d failed",
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


#: The issuing body a CIN prints beside its number ("448.864.938-66-IIGDR-SP",
#: contract 08). Matched as a substring of the órgão, case-insensitively.
ORGAO_CIN = "IIGDR"


def _e_cin(doc: dict, cliente: dict) -> bool:
    """Is this identity reading a CIN's — where RG == CPF is correct?

    Yes when the file was filed as a CIN, or when the órgão expedidor (read
    off this same document, or already on the record) is the CIN's IIGDR.
    """
    if doc.get("tipo_documento") == "cin":
        return True
    for orgao in (doc.get("extracao_rg_orgao"), cliente.get("rg_orgao_expedidor")):
        if isinstance(orgao, str) and ORGAO_CIN in orgao.upper():
            return True
    return False


def sugestoes_pendentes(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Per checklist-item, the newest extracted value still awaiting a decision.

    Newest-first when several documents disagree: the operator resolves one at
    a time, and discarding reveals the next rather than a pile to triage. A
    disagreement between two reads is exactly the case where showing both at
    once invites picking the wrong one quickly.
    """
    cliente_rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(["id", *CAMPO_POR_ITEM, "endereco_origem", *ENDERECO_COLUNAS]))
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
            # Flags a still-pending RG reading that matches the CPF on file —
            # confirm against the document. `None` for every other field and
            # every RG that is simply a normal pending suggestion.
            # 🔴 NEVER for a CIN (owner directive, 2026-09-23): a Carteira de
            # Identidade Nacional prints the CPF as the identity number, so
            # RG == CPF is its VALID state — see `_e_cin`.
            aviso = (
                "rg_igual_cpf"
                if campo.item_key == "rg"
                and is_same_as_cpf(valor, cliente.get("cpf"))
                and not _e_cin(doc, cliente)
                else None
            )
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
                "aviso": aviso,
            }
            break

    # The endereço group (migration 153): offered only while the record has
    # no address at all — a differing address is a conflict, not a
    # suggestion (`aplicar_endereco_ao_cliente`).
    if all(_vazio(cliente.get(c)) for c in ENDERECO_COLUNAS):
        for doc in candidatos:
            if _vazio(doc.get("extracao_endereco_cep")) or _vazio(
                doc.get("extracao_endereco_logradouro")
            ):
                continue
            out[CAMPO_ENDERECO] = {
                "valor": {p: doc.get(f"extracao_endereco_{p}") for p in ENDERECO_PARTES},
                "valor_atual": None,
                "documento_id": doc["id"],
                "documento_nome": doc.get("nome_original"),
                "tipo_documento": doc.get("tipo_documento"),
                "confianca": doc.get("extracao_endereco_confianca"),
                "fonte": doc.get("extracao_fonte"),
                "rotulo": doc.get("extracao_endereco_rotulo"),
                "titular_documento": doc.get("extracao_endereco_titular"),
                "substitui": False,
                "aviso": None,
            }
            break
    return out


def _confirmar_endereco(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    doc: dict,
    *,
    user_id: Optional[UUID],
) -> dict:
    """`confirmar_sugestao(item_key='endereco')` — the group, confirmed."""
    partes = {p: doc.get(f"extracao_endereco_{p}") for p in ENDERECO_PARTES}
    if _vazio(partes["cep"]) or _vazio(partes["logradouro"]):
        raise ValidationError_(
            "Este documento não tem um endereço extraído para confirmar.",
            field="extracao_endereco_cep",
        )
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(["id", *ENDERECO_COLUNAS]))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("clientes", str(cliente_id))
    if any(not _vazio(rows[0].get(c)) for c in ENDERECO_COLUNAS):
        raise ValidationError_(
            "Este cliente já tem um endereço registrado.", field=CAMPO_ENDERECO
        )
    now = _now()
    updates: dict[str, Any] = {
        f"endereco_{p}": (None if _vazio(v) else v) for p, v in partes.items()
    }
    updates.update(
        {
            "endereco_origem": doc["tipo_documento"],
            "endereco_documento_id": str(doc["id"]),
            "endereco_em": now,
            "endereco_confirmado_por": str(user_id) if user_id else None,
            "endereco_confirmado_em": now,
            "updated_at": now,
        }
    )
    _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()
    return {
        "confirmado": True,
        "item_key": CAMPO_ENDERECO,
        "valor": partes,
        "substituiu": None,
        "documento_id": str(doc["id"]),
    }


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
    campo = None if item_key == CAMPO_ENDERECO else _resolver_campo(item_key)

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
    if doc.get("extracao_descartada_em"):
        raise ValidationError_(
            "Esta sugestão já foi descartada.", field="extracao_descartada_em"
        )
    if campo is None:
        return _confirmar_endereco(client, org_id, cliente_id, doc, user_id=user_id)

    valor = doc.get(campo.coluna_valor)
    if not valor:
        raise ValidationError_(
            "Este documento não tem um valor extraído para confirmar.",
            field=campo.coluna_valor,
        )

    # 🔴 No `rg==cpf` refusal here (2026-09-22). It used to be — the same
    # collision `_aplicar_ao_cliente` used to decline, refused again on this
    # write path — but a CIN holder's RG legitimately equals their CPF (see
    # `clientes_service.update_cliente`'s comment for the contract-08
    # citation). Confirming applies the reading; the contract-generation
    # gate is what still surfaces it, as a warning (`derivacao._partes`'s
    # `av.avisa("RG_IGUAL_CPF", ...)`).
    cliente_rows = (
        _t(client, CLIENTES_TABLE)
        .select(f"{campo.item_key},{campo.origem},rg_orgao_expedidor")
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
    # Confirming an RG carries its issuer when the record has none: the
    # human vouched for the document line the issuer was read beside.
    orgao = doc.get("extracao_rg_orgao")
    if campo.item_key == "rg" and orgao and _vazio(cliente_rows[0].get("rg_orgao_expedidor")):
        oc = CAMPO_POR_CHAVE["rg_orgao_expedidor"]
        updates.update(
            {
                oc.item_key: orgao,
                oc.origem: doc["tipo_documento"],
                oc.documento_id: str(documento_id),
                oc.em: now,
                oc.confirmado_por: str(user_id) if user_id else None,
                oc.confirmado_em: now,
            }
        )
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
    chave = CAMPO_ENDERECO if item_key == CAMPO_ENDERECO else _resolver_campo(item_key).item_key

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
        "item_key": chave,
        "documento_id": str(documento_id),
    }


# ─── The certidão's own freshness (contract F6, migration 117) ───────────
#
# `data_emissao` rides on the document, never on the client — see
# `_TIPOS_CERTIDAO_ESTADO_CIVIL`'s comment. This is the one reader that
# answers the office's own rule: a certidão de estado civil must be under 90
# days old AS OF SIGNING.


def certidao_estado_civil_mais_recente(
    client: Any, org_id: UUID, cliente_id: UUID
) -> Optional[dict]:
    """The person's LATEST estado-civil certidão, by its OWN emission date —
    not by upload recency. An operator may upload an old certidão after a
    fresher one already sits on file, and the fresher document is the one
    that actually answers "is this current as of signing".

    Deleted and discarded rows are excluded, same posture `sugestoes_
    pendentes` takes: a document the client asked us to forget, or a
    reading a human turned down, cannot go on answering a freshness
    question.

    🔴 Migration 148 — ALSO compares against
    `clientes.certidao_estado_civil_emitida_em`, the human-typed emission
    date for a certidão nobody has uploaded (yet, or ever). Same "freshest
    reading wins" comparison this function already runs across multiple
    *uploaded* certidões, just extended to include the manual one; when the
    manual date wins, `documento_id` is `None` — there is no
    `cliente_documentos` row backing it, and callers (`contrato_gerador
    .derivacao`'s [Q11]) never dereference it, only `emitida_em`/`dias`.

    Returns `None` when neither source has a recorded emission date yet —
    legible with the fact simply absent, never an error.
    """
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id," + ",".join(_COLUNAS_DATA_EMISSAO))
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .in_("tipo_documento", list(_TIPOS_CERTIDAO_ESTADO_CIVIL))
        .is_("deleted_at", "null")
        .is_("extracao_descartada_em", "null")
        .not_.is_("extracao_data_emissao", "null")
        .execute()
    ).data or []

    candidatos: list[dict] = [
        {"documento_id": r["id"], "emitida_em": r["extracao_data_emissao"]}
        for r in rows
    ]

    cliente_rows = (
        _t(client, CLIENTES_TABLE)
        .select("certidao_estado_civil_emitida_em")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    manual = (cliente_rows[0] if cliente_rows else {}).get(
        "certidao_estado_civil_emitida_em"
    )
    if manual:
        candidatos.append({"documento_id": None, "emitida_em": manual})

    if not candidatos:
        return None

    mais_recente = max(candidatos, key=lambda c: c["emitida_em"])
    emitida_em = date.fromisoformat(mais_recente["emitida_em"])
    dias = (datetime.now(timezone.utc).date() - emitida_em).days
    return {
        "documento_id": mais_recente["documento_id"],
        "emitida_em": mais_recente["emitida_em"],
        "dias": dias,
    }


__all__ = [
    "CAMPOS",
    "CAMPO_CONJUGE",
    "CAMPO_ENDERECO",
    "ENDERECO_PARTES",
    "MAX_RETENTATIVAS_ERRO",
    "TIPOS_ENDERECO",
    "aplicar_campos_ao_cliente",
    "aplicar_endereco_ao_cliente",
    "notificar_conflitos",
    "resolver_conflito",
    "vincular_conjuges",
    "CAMPO_POR_CHAVE",
    "CAMPO_POR_ITEM",
    "MAX_TENTATIVAS",
    "STALE_APOS",
    "TIPOS_EXTRAIVEIS",
    "CampoExtraido",
    "certidao_estado_civil_mais_recente",
    "confirmar_sugestao",
    "descartar_sugestao",
    "deve_extrair",
    "extrair_identidade",
    "sugestoes_pendentes",
    "varrer_extracoes_pendentes",
]
