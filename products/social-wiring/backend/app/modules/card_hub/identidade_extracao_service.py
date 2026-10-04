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
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    AVISO_LEITURA_COMPROMETIDA,
    IdentityFields,
    TitularEsperado,
    canonical_gender,
    chave_nome,
    classificar_tipo_provavel,
    is_same_as_cpf,
    make_identity_extractor,
    nomes_compativeis,
    strip_accents_upper,
)
from noctusai_lib.integrations.cep import CepLookupAdapter
from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.nacionalidade import canonico as nacionalidade_canonica
from noctusai_lib.integrations.documents.nacionalidade_civil import (
    derivar_nacionalidade_civil,
)
from noctusai_lib.integrations.documents.rg import only_alnum
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.proveniencia import fontes
from app.services import campo_conflitos, divergencia_resolucao, extracao_job, table_reads
from app.services import identificadores as idf
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
#:
#: 🔴 `cin` ran the OPPOSITE gap (found on prod 2026-09-30, live test): its
#: `cliente_documento_tipos` row shipped FIRST (migration 164, 2026-09-23,
#: `ativo = true`) — uploads were reachable from day one — but `proveniencia.
#: fontes.FONTES` deliberately left `cin` out, per 164's own "no real CIN
#: exists yet" ruling. A CIN uploaded either checklist slot or via Anexos
#: therefore landed in `cliente_documentos` and was NEVER read:
#: `extracao_status` stayed `NULL`, `extracao_tentativas` stayed `0`, forever
#: — `deve_extrair` returning `False` for an `ativo` catalogue type is a
#: silent gap, not a `None`-vs-value honesty like `_extracao_servida`'s. The
#: seed grew a real CIN reader in the meantime (`real.py`'s `_achou_algo`,
#: hardened against the gov.br CIN PDF's shape on the P2 corpus,
#: 2026-09-28); `fontes.FONTES["cin"]` now closes this gap the same way
#: migration 142 closed `cnh`'s, mirror-imaged. The CINs already stranded
#: at `NULL` are read by the sweep's class-4 pass (`_candidatos_varredura`)
#: — and so is the backlog of any type that gains a reader later.
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
#: Migration 194 — the bairro's OWN provenance when it differs from the
#: group's (`endereco_origem`). NULL = same source as the group.
COLUNA_BAIRRO_ORIGEM = "endereco_bairro_origem"
#: `endereco_bairro_origem` for a bairro filled from the CEP lookup because
#: the document printed none (extraction defect, 2026-10-03).
ORIGEM_BAIRRO_CEP = "cep"
#: Same for the spouse link (`conjuge_cliente_id`, provenance `conjuge_*`).
CAMPO_CONJUGE = "conjuge_cliente_id"
PREFIXO_CONJUGE = "conjuge"

#: R3 (owner directive, 2026-09-30) — `endereco_origem` for a household
#: address INHERITED from a linked spouse's own document, never from a
#: document of this cliente's own. A tier BELOW any real document (`_
#: endereco_e_proprio` refuses to treat this origin as a propagation SOURCE
#: for the other half, and `_decisao_endereco_por_titular`'s "already has an
#: address from their own document" auto-reject guard excludes it too) —
#: `propagar_endereco_domicilio` is the only writer, and it un-writes this
#: exact value the moment the source no longer qualifies.
ORIGEM_CONJUGE_DOMICILIO = "conjuge_domicilio"

#: The address sources that carry no printed holder because the document IS
#: the party's own declaration — a `ficha_cadastral` row reaches a cliente
#: only after `ficha_cadastral_service.resolver_destino` matched that very
#: person (CPF first, name on the uploaded-to card as the fallback). For the
#: holder rule such an address is the party's OWN, never "titular unknown":
#: live prod test 2026-10-01 (deal 875) — the buyer's own older utility bill
#: (holder verified as the buyer) silently replaced the bank-form address the
#: signed contract actually used, because the form's holder read as `None`.
ORIGENS_ENDERECO_DECLARADO = frozenset({"ficha_cadastral"})

#: `extracao_aviso` for a comprovante whose printed holder matches nobody on
#: the card, applied anyway because the address group was EMPTY (owner rule
#: H1) — the human gate sees WHY the source deserves a second look.
AVISO_TITULAR_NAO_CONFERE = "comprovante_titular_nao_confere"

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

#: F4 (P5 audit, 2026-10-03): a certidão de NASCIMENTO that records no
#: averbação of a marriage is the document that proves "solteiro" — the
#: signed contracts qualify those parties as solteiros, yet no reader ever
#: produced the value (the averbação is what the parser looks for, and its
#: ABSENCE was read as "nothing"). Inferred only when the party has no
#: marriage evidence at all (no live certidão de casamento of their own or
#: of a linked spouse, no spouse link) — the D1 empty-fill rule then fills
#: an empty `estado_civil` machine-pending, and a DIFFERENT value on file
#: opens a conflict, never an overwrite.
ESTADO_CIVIL_SOLTEIRO = "solteiro"
ROTULO_SOLTEIRO_INFERIDO = "inferido: certidão de nascimento sem averbação de casamento"

CAMPO_POR_CHAVE: dict[str, CampoExtraido] = {c.item_key: c for c in CAMPOS}

#: Kept as the flat `{item_key: coluna}` mapping earlier callers already read.
CAMPO_POR_ITEM: dict[str, str] = {c.item_key: c.coluna_valor for c in CAMPOS}


def _coluna_lida_no_documento(campo: CampoExtraido) -> str:
    """The `cliente_documentos` column a document stores `campo` in.

    A `CampoExtraido` from a NON-document source (`qualificacao_service.
    CAMPOS_QUALIFICACAO`, `crednet`) carries `coluna_valor=""` — it has no
    column of its own — yet the apply path judges the ON-FILE side against
    the identity DOCUMENT behind it. Reading `documento.get("")` made every
    such document look like it had re-read to nothing: a false 'retratado'
    that let a matrícula overwrite a value its own CNH still asserted. The
    column is the document-extraction `CAMPOS` entry's, by `item_key`."""
    return campo.coluna_valor or CAMPO_POR_ITEM.get(campo.item_key, "")

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

#: [Migration 193] The escritura de pacto antenupcial the contract cites in a
#: married couple's qualification (`clientes.pacto_antenupcial_*`), written by
#: `pacto_antenupcial_service` through `aplicar_campos_ao_cliente` (D1: fill
#: an empty field machine-pending, conflict on a different value, never
#: overwrite). Held OUTSIDE `CAMPOS` for the same reason as `CAMPO_NOME_MAE`
#: (no `IdentityFields` attribute maps to them — `_valores_lidos` would
#: `KeyError`), but registered in `CAMPO_POR_CHAVE` so the admin's generic
#: `resolver_conflito` can decide a pacto conflict. No `cliente_documentos`
#: column of their own (the reading rides on the document's
#: `extracao_pacto_antenupcial` JSONB), hence `coluna_*=""` —
#: `_documento_sustenta` answers "cannot tell" for them, never "retracted".
CAMPOS_PACTO_ESCRITURA: tuple[CampoExtraido, ...] = tuple(
    CampoExtraido(
        item_key=f"pacto_antenupcial_{parte}",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    )
    for parte in ("data", "tabelionato", "livro", "folha")
)
for _campo_pacto in CAMPOS_PACTO_ESCRITURA:
    CAMPO_POR_CHAVE[_campo_pacto.item_key] = _campo_pacto


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
    """EMPTY for D1 — `campo_conflitos.valor_vazio`, the one predicate every
    apply path shares (P5 audit F1: a `'—'`/`'null'` placeholder on file read
    as a value and opened a conflict instead of being filled)."""
    return campo_conflitos.valor_vazio(valor)


def _limpo_por_humano(valor_atual: Any, origem_atual: Optional[str]) -> bool:
    """An operator explicitly CLEARED this field (`origem='manual'`, value
    genuinely blank) — a human decision the machine respects. A manual
    PLACEHOLDER (`'—'`, `'null'`) is not a clear: it says "unknown", and the
    first document fills it (owner rule H1)."""
    if origem_atual != "manual":
        return False
    return valor_atual is None or (isinstance(valor_atual, str) and not valor_atual.strip())


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
        return idf.iguais("cpf", a, b)
    if item_key == "rg":
        # The registry proves format-only differences AND an RG read without
        # its check digit (a CNH) against the full one (`30128742` ==
        # `30.128.742-9`) — `canonical-identifiers`, owner rule 2026-10-01.
        return idf.iguais("rg", a, b)
    if item_key == "rg_orgao_expedidor":
        return idf.iguais("orgao_expedidor", a, b) or (
            only_alnum(str(a)) == only_alnum(str(b))
        )
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
    if item_key in ("data_nascimento", "data_casamento", "pacto_antenupcial_data"):
        return str(a)[:10] == str(b)[:10]
    return _mesmo_nome(str(a), str(b))


def _nome_anterior_confirma_adocao(
    estado_civil: Any,
    presente: Any,
    nome_anterior: Optional[str],
    *,
    origem_atual: Optional[str],
    confirmado_em_atual: Any,
    cpf_atual: Optional[Any] = None,
    cpf_lido: Optional[Any] = None,
) -> bool:
    """Owner decision, 2026-09-28: for a party the certidão states is
    CASADO, the name it says they "passou a utilizar" (`ConjugeLido.nome`,
    already `nome_oficial`'s proposed value by the time this is consulted)
    is the contract/official name — not a second opinion on whatever is
    already on file, when what is on file is exactly the name the SAME
    certidão says they left behind (`nome_anterior`). That is a marriage
    changing a name, evidenced by the document itself, not a misread.

    `estado_civil` must normalise to `casado` — `civil_status.
    find_estado_civil`'s own AVERBAÇÃO precedence already resolves a
    divórcio/separação/óbito to its OWN canonical token before this ever
    sees it, so this never fires past one.

    🔴 OWNER DIRECTIVE, 2026-09-29 — REQUIRES CPF CORROBORATION WHEN
    AVAILABLE. Measured against the 10 signed P2 contracts: a certidão's own
    `nome_oficial` reading is only 60% precise (3/5) — good enough to name
    WHO adopted what only when nothing independently CONTRADICTS the match.
    `cpf_atual`/`cpf_lido` are the on-file CPF and this same reading's CPF
    for this party; when BOTH are present and they DISAGREE, this is refused
    — a misread party, or two different people coincidentally sharing a
    maiden -> married name pair — and falls through to the ordinary conflict
    path for a human. Either side ABSENT is not refused: the caller already
    anchored this `cliente_id` as the certidão's party before ever reaching
    this function (a manual `conjuge_cliente_id` link, or an earlier CPF/
    name match at `_e_a_pessoa`/`_cliente_do_outro_conjuge` time) — there is
    no weaker "no CPF at all" case this function would otherwise be silently
    trusting past that anchor.

    🔴 NOC-REMEDIATE[nome-anterior-pos-averbacao] — a divorciado/separado/
    viúvo party whose CNH/RG still carries a since-abandoned married name
    has no equivalent auto-resolution here: `civil_status.py` has no
    per-averbação "nome que voltou a usar" reader yet, so that case still
    falls through to today's conflict for a human — 2026-09-28.

    Never fires against a value a human already typed or confirmed — same
    guard `campo_conflitos.mesmo_documento_pendente` applies, for the same
    reason: a real person's decision about this field outranks any reading.
    """
    if not origem_atual or origem_atual == "manual":
        return False
    if confirmado_em_atual:
        return False
    # Local import: `_mesmo_valor`'s own `estado_civil` branch already
    # imports from here for the identical reason (avoids a module-level
    # cycle; `documento_checklist_service` imports this module).
    from app.modules.card_hub.documento_checklist_service import (
        _estado_civil_normalizado,
    )

    if _estado_civil_normalizado(str(estado_civil) if estado_civil else None) != "casado":
        return False
    if not _mesmo_valor("nome_oficial", presente, nome_anterior):
        return False
    if cpf_atual and cpf_lido and only_digits(str(cpf_atual)) != only_digits(str(cpf_lido)):
        return False
    return True


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


def _papeis_das_pessoas(client: Any, org_id: UUID, cliente_ids: list[str]) -> dict[str, str]:
    """Best-effort role label per cliente_id, for R4's rejection message —
    `atendimento_partes.papel` when this person is a party; the label
    "comprador" when they are instead an atendimento's own `cliente_id` (the
    implicit titular/comprador — same default `_pessoas_do_mesmo_lado`
    already uses). Never drives a decision, only the wording of a motivo a
    human might read — an id with no role found anywhere still gets a
    generic label rather than being dropped."""
    if not cliente_ids:
        return {}
    papeis: dict[str, str] = {}
    for row in (
        _t(client, "atendimento_partes")
        .select("cliente_id,papel")
        .eq("org_id", str(org_id))
        .in_("cliente_id", cliente_ids)
        .execute()
    ).data or []:
        cid = str(row.get("cliente_id"))
        if cid not in papeis and row.get("papel"):
            papeis[cid] = row["papel"]
    faltando = [c for c in cliente_ids if c not in papeis]
    if faltando:
        for row in (
            _t(client, "atendimentos")
            .select("cliente_id")
            .eq("org_id", str(org_id))
            .in_("cliente_id", faltando)
            .execute()
        ).data or []:
            papeis.setdefault(str(row.get("cliente_id")), "comprador")
    return papeis


def _valores_outras_pessoas(
    client: Any, org_id: UUID, cliente_id: UUID, campo_item_key: str
) -> list[tuple[Any, str]]:
    """R4 — every OTHER party's own `campo_item_key` value, across every
    `atendimento` `cliente_id` sits on (`_pessoas_dos_cards`), paired with a
    role label for the rejection message. `[]` when this cliente sits on no
    atendimento at all — the ordinary case for most identity reads."""
    outras = _pessoas_dos_cards(client, org_id, cliente_id)
    if not outras:
        return []
    papeis = _papeis_das_pessoas(client, org_id, outras)
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(f"id,{campo_item_key}")
        .eq("org_id", str(org_id))
        .in_("id", outras)
        .execute()
    ).data or []
    return [
        (r.get(campo_item_key), papeis.get(str(r.get("id")), "outra parte desta negociação"))
        for r in rows
    ]


def _valor_humano(row: Optional[dict], campo: CampoExtraido) -> bool:
    """A person typed (`origem='manual'`) or vouched for (`confirmado_por`
    set) this field's current value — the automatic resolver never
    overrides it (owner rule 2026-10-03, `divergencia_resolucao.
    resolver_divergencia(atual_humano=...)`)."""
    row = row or {}
    return row.get(campo.origem) == "manual" or bool(row.get(campo.confirmado_por))


def _cpf_proprio(lidos: dict, atual: dict, updates: dict) -> Optional[str]:
    """The CPF of the person being written — the one a CIN's RG may equal.
    A reading in this same apply wins over what is on file; an invalid one
    is no CPF at all."""
    for candidato in ((lidos.get("cpf") or (None,))[0], updates.get("cpf"), atual.get("cpf")):
        if candidato and cpf_valido(str(candidato)):
            return str(candidato)
    return None


def _canonico_do_presente(
    tipo_id: Optional[str], presente: Any, *, uf: Optional[str] = None
) -> Optional[str]:
    """The canonical form to upgrade a stored identifier to, or None when
    there is nothing to do (no registry type, already canonical, or the
    stored value does not fit its type — never rewritten)."""
    if tipo_id is None or _vazio(presente):
        return None
    g = idf.para_gravar(tipo_id, presente, uf=uf if tipo_id == "rg" else None)
    if g.canonico and g.valor is not None and g.valor != str(presente):
        return g.valor
    return None


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
    nomes_anteriores: Optional[dict[str, Optional[str]]] = None,
    avisos_outra_pessoa: Optional[list[str]] = None,
    avisos_cpf_invalido: Optional[list[str]] = None,
    avisos_tipo_trocado: Optional[list[str]] = None,
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
    - **Field already SET and the reading DIFFERS -> resolved automatically,
      or a conflict** (owner directive, 2026-09-29): `campo_conflitos.
      resolver_e_registrar` (`app.services.divergencia_resolucao`) tries
      validators -> corroboration -> measured source-precision tier FIRST;
      only a genuine same-tier/unmeasured tie still opens a `pendente`
      `cliente_campo_conflitos` row (returned, so the caller notifies an
      admin) — never an overwrite either way, and every automatic decision
      is written back to that SAME table as an auditable
      `'resolvido_automatico'` row (rule + evidence in `motivo_resolucao`).
      `nome_oficial` included — the old `sobrescreve=True` "newest document
      wins" is gone.
    - **Field already SET, the reading DIFFERS, but it's a RE-READ of the
      SAME still machine-pending document -> replaces, no conflict**
      (`campo_conflitos.mesmo_documento_pendente`, 2026-09-25): the stored
      value's own `<campo>_documento_id` equals THIS apply's `documento_id`
      and nothing confirmed/manual has touched it since — the earlier
      pass's own imperfection, not a second opinion. Any stale `pendente`
      conflict on this field is closed. A human-confirmed or manually-typed
      value is NEVER replaced this way — that still conflicts like any
      other disagreement.
    - **`nome_oficial` already SET, the reading DIFFERS, but the certidão
      says CASADO and the name it says the party LEFT BEHIND
      (`nomes_anteriores["nome_oficial"]`) equals what is already on file
      -> replaces, no conflict** (owner decision, 2026-09-28,
      `_nome_anterior_confirma_adocao`): the on-file value is the expected
      maiden/prior name, not a disagreeing read — a marriage the document
      itself evidences changing the name, not a second opinion. Never fires
      against a human-confirmed or manually-typed value, same guard as the
      re-read branch above; never fires past `casado` (a divorciado/
      separado/viúvo party still conflicts exactly as before —
      `NOC-REMEDIATE[nome-anterior-pos-averbacao]`).
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
    - **R4 (owner directive, 2026-09-30) — a proposed `nome_oficial`/`cpf`/
      `rg` that equals ANOTHER party's (or their attributed spouse's) own
      value in the same `atendimento` is auto-REJECTED**
      (`divergencia_resolucao.decisao_outra_pessoa`) before the fill-empty
      or conflict branches ever see it — a misfiled document is not
      evidence about THIS person, whether the field was empty or already
      set. Recorded the same auditable way as any other automatic
      resolution (`'resolvido_automatico'`, `motivo_resolucao`); the
      `item_key` is appended to `avisos_outra_pessoa` when given, so the
      caller (`extrair_identidade`) can flag the SOURCE document.

    🔴 A CPF whose mod-11 check digits FAIL is NOT READ (owner rule,
    2026-10-01, P4/871: an `rg` reading at `baixa` wrote a wrong CPF onto the
    cliente). Refused here — the one write chokepoint every source (identity
    docs, ficha cadastral, crednet, certidão spouse, matrícula) funnels
    through — so no reader can reintroduce it; `item_key` is appended to
    `avisos_cpf_invalido` when given so the caller can flag the document.

    🔴 CANONICAL ON WRITE (owner rule 2026-10-01, `KB § PATTERNS/common/
    canonical-identifiers.md`): a `cpf` / `rg` / `rg_orgao_expedidor` that
    FITS its type is stored in the registry's PUNCTUATED canonical form
    (`identificadores.para_gravar`); a value that does not fit is stored as
    read and stays visible (never silently rewritten); a value that is a
    valid instance of ANOTHER type (a CPF `297.556.088-50` in the RG field —
    except the CIN, whose RG IS the holder's own CPF) is NOT written, and
    its `item_key` is appended to `avisos_tipo_trocado` so the caller flags
    the source document for a human. A still-non-canonical stored value that
    is the SAME identifier as the incoming one is upgraded in place to the
    canonical form (provenance untouched).

    `documento_id=None` means this source has no `cliente_documentos` row to
    point at — the column is written as an explicit NULL.

    Returns `({item_key: foi_aplicado}, [conflito, ...])` — the second list
    holds every NEWLY opened conflict (this function never does async I/O;
    `notificar_conflitos` is the caller's next step).
    """
    colunas: list[str] = ["id"]
    for campo in campos:
        colunas += [
            campo.item_key, campo.origem, campo.documento_id, campo.confirmado_em,
            campo.confirmado_por,
        ]
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
        if campo.item_key == "cpf" and not cpf_valido(str(valor)):
            logger.warning(
                "cpf com dígitos verificadores inválidos NÃO gravado (cliente %s, origem %s)",
                cliente_id, origem,
            )
            if avisos_cpf_invalido is not None:
                avisos_cpf_invalido.append(campo.item_key)
            continue

        tipo_id = idf.TIPO_POR_CAMPO_CLIENTE.get(campo.item_key)
        uf_rg = None
        cpf_proprio = None
        if tipo_id is not None:
            cpf_proprio = _cpf_proprio(lidos, atual, updates)
            uf_rg = idf.uf_do_orgao(
                (lidos.get("rg_orgao_expedidor") or (None,))[0]
                or updates.get("rg_orgao_expedidor")
                or atual.get("rg_orgao_expedidor")
            )
            gravacao = idf.para_gravar(
                tipo_id, valor,
                uf=uf_rg if tipo_id == "rg" else None,
                cpf_proprio=cpf_proprio,
            )
            if gravacao.rejeitado_por_tipo:
                logger.warning(
                    "%s NÃO gravado: é um %s válido, não um %s "
                    "(cliente %s, origem %s)",
                    campo.item_key, gravacao.tipo_detectado, tipo_id,
                    cliente_id, origem,
                )
                if avisos_tipo_trocado is not None:
                    avisos_tipo_trocado.append(campo.item_key)
                continue
            valor = gravacao.valor

        if campo.depende_de:
            # Only beside the value it was read with — see `depende_de`.
            lido_dep = lidos.get(campo.depende_de, (None,))[0]
            final_dep = updates.get(campo.depende_de, atual.get(campo.depende_de))
            if not _mesmo_valor(campo.depende_de, final_dep, lido_dep):
                continue

        # 🔴 R4 (owner directive, 2026-09-30) — this value belongs to
        # ANOTHER party of the same negotiation, not this cliente: reject
        # unattended, whatever is or isn't already on file, rather than
        # fill an empty field or open a human conflict over a misfiled
        # document. Scoped to `CAMPOS_IDENTIDADE_EXCLUSIVA` — the DB lookup
        # this needs (every OTHER atendimento party's own value) is only
        # worth paying for the fields that rule actually covers.
        decisao_outra = None
        if campo.item_key in divergencia_resolucao.CAMPOS_IDENTIDADE_EXCLUSIVA:
            decisao_outra = divergencia_resolucao.decisao_outra_pessoa(
                campo.item_key, valor,
                mesmo_valor=_mesmo_valor,
                valores_outras_pessoas=_valores_outras_pessoas(
                    client, org_id, cliente_id, campo.item_key
                ),
            )
        if decisao_outra is not None:
            campo_conflitos.registrar_decisao_automatica(
                client, campo_conflitos.CLIENTE, org_id, cliente_id, campo.item_key,
                valor_anterior=atual.get(campo.item_key),
                origem_anterior=atual.get(campo.origem),
                valor_proposto=valor,
                origem_proposto=origem,
                confianca_proposta=confianca,
                fonte_tabela=fonte_tabela,
                fonte_id=fonte_id,
                decisao=decisao_outra,
            )
            if avisos_outra_pessoa is not None:
                avisos_outra_pessoa.append(campo.item_key)
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
                if campo_conflitos.mesmo_documento_pendente(
                    origem_atual=atual.get(campo.origem),
                    confirmado_em_atual=atual.get(campo.confirmado_em),
                    documento_id_atual=atual.get(campo.documento_id),
                    documento_id_proposto=documento_id,
                ):
                    # Not a disagreement — a RE-READ of the SAME document
                    # whose earlier pass is still machine-pending (D1
                    # same-document-re-read refinement, see
                    # `campo_conflitos.mesmo_documento_pendente`'s own
                    # docstring). The fresh reading replaces the stale
                    # one instead of opening a conflict with itself, and
                    # any stale pending conflict on this field is closed.
                    updates[campo.item_key] = valor
                    updates[campo.origem] = origem
                    updates[campo.documento_id] = (
                        str(documento_id) if documento_id else None
                    )
                    updates[campo.em] = now
                    updates[campo.confirmado_por] = None
                    updates[campo.confirmado_em] = None
                    aplicados[campo.item_key] = True
                    campo_conflitos.fechar_conflitos_pendentes(
                        client, campo_conflitos.CLIENTE, org_id, cliente_id,
                        campo.item_key, decidido_por=None,
                    )
                elif campo.item_key == "nome_oficial" and _nome_anterior_confirma_adocao(
                    lidos.get("estado_civil", (None,))[0],
                    presente,
                    (nomes_anteriores or {}).get("nome_oficial"),
                    origem_atual=atual.get(campo.origem),
                    confirmado_em_atual=atual.get(campo.confirmado_em),
                    cpf_atual=atual.get("cpf"),
                    cpf_lido=lidos.get("cpf", (None,))[0],
                ):
                    # Not a disagreement — the certidão itself says CASADO
                    # and names this exact on-file value as the name the
                    # party left BEHIND (owner decision, 2026-09-28, see
                    # `_nome_anterior_confirma_adocao`). The adopted name
                    # replaces it; nothing is lost — every document keeps
                    # its own reading, and `nome_anterior` still rides on
                    # `cliente_documentos.extracao_conjuges` for this one.
                    updates[campo.item_key] = valor
                    updates[campo.origem] = origem
                    updates[campo.documento_id] = (
                        str(documento_id) if documento_id else None
                    )
                    updates[campo.em] = now
                    updates[campo.confirmado_por] = None
                    updates[campo.confirmado_em] = None
                    aplicados[campo.item_key] = True
                    campo_conflitos.fechar_conflitos_pendentes(
                        client, campo_conflitos.CLIENTE, org_id, cliente_id,
                        campo.item_key, decidido_por=None,
                    )
                else:
                    # Owner directive, 2026-09-29 — resolve without a human
                    # FIRST, using the measured evidence table (validators ->
                    # corroboration -> source-precision tier); only what
                    # survives all three still opens a `pendente` conflict.
                    # See `app.services.divergencia_resolucao` + `campo_
                    # conflitos.resolver_e_registrar`'s own docstrings.
                    decisao = campo_conflitos.resolver_e_registrar(
                        client, campo_conflitos.CLIENTE, org_id, cliente_id,
                        campo.item_key,
                        valor_anterior=presente,
                        origem_anterior=atual.get(campo.origem),
                        valor_proposto=valor,
                        origem_proposto=origem,
                        confianca_proposta=confianca,
                        fonte_tabela=fonte_tabela,
                        fonte_id=fonte_id,
                        mesmo_valor=_mesmo_valor,
                        evidencia=_evidencia_ao_vivo(client, org_id, cliente_id, campo, presente),
                        uf=uf_rg,
                        cpf_proprio=cpf_proprio,
                        atual_humano=_valor_humano(atual, campo),
                    )
                    if decisao.requer_humano:
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
                    elif decisao.vencedor == "proposto":
                        # The resolver picked the NEW reading — apply it,
                        # same provenance shape (and same machine-pending
                        # posture — a human still sees it via `sugestoes_
                        # pendentes`/the checklist) the re-read/married-name
                        # branches above already write. The CONTRACT gate's
                        # own auto-validation (BUILD item 2) is a SEPARATE,
                        # read-only concern — see `validacao_extracao.
                        # CampoValidavel.pendente` — never this column.
                        updates[campo.item_key] = valor
                        updates[campo.origem] = origem
                        updates[campo.documento_id] = (
                            str(documento_id) if documento_id else None
                        )
                        updates[campo.em] = now
                        updates[campo.confirmado_por] = None
                        updates[campo.confirmado_em] = None
                        aplicados[campo.item_key] = True
                    # decisao.vencedor == "atual": the record already holds
                    # the fact — nothing to write, the audit row alone
                    # (`resolvido_automatico`) records the resolver ran.
            else:
                # Same identifier: bring a still-raw stored form to the
                # canonical one, provenance untouched (format-only).
                canonico_presente = _canonico_do_presente(tipo_id, presente, uf=uf_rg)
                if canonico_presente is not None:
                    updates[campo.item_key] = canonico_presente
                if confirmado_por and _vazio(atual.get(campo.confirmado_em)):
                    # Same fact, still machine-pending, a human now vouches
                    # for it — promote to confirmed. See the docstring's D1
                    # bullet.
                    updates[campo.confirmado_por] = str(confirmado_por)
                    updates[campo.confirmado_em] = now
                    aplicados[campo.item_key] = True
            continue
        if _limpo_por_humano(presente, atual.get(campo.origem)):
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

    # A CPF that just became known may be what an already-read bank form was
    # waiting for (it named this person before their identity document
    # existed and stored them unmatched). The form's STORED reading is applied
    # to this person right now — zero model calls (it used to be re-queued for
    # a full vision re-read, once per party whose CPF arrived later; owner rule
    # 2026-10-01, `canonical-identifiers`). Any conflict that apply opens
    # joins this call's own, so the caller announces it. Local import:
    # ficha_cadastral_service imports this module.
    if aplicados.get("cpf") and updates.get("cpf"):
        conflitos.extend(
            cpf_conhecido(client, org_id, cliente_id, updates["cpf"], excluir_documento_id=documento_id)
        )

    return aplicados, conflitos


def cpf_conhecido(
    client: Any, org_id: UUID, cliente_id: Any, cpf: Any,
    *, excluir_documento_id: Optional[UUID] = None,
) -> list[dict]:
    """A person's CPF just landed on file — by ANY path (an extraction, an
    admin accepting a conflict, a confirmed suggestion, the automatic
    resolver, a hand edit). Every already-read bank form of their card(s)
    that named this CPF but could not be attributed at read time is applied
    to them RIGHT NOW from its stored reading (`ficha_cadastral_service.
    reaplicar_fichas_pelo_cpf` — zero model calls, idempotent). The P4 live
    loop measured the alternative: a form re-queued for the sweep waited up
    to ~80 minutes for a CPF that was already known.

    Returns the conflict rows the re-apply opened (recorded and listed in the
    queue; an async caller announces them). Best-effort: a failure is logged
    loudly and never fails the write that made the CPF known. Local import:
    ficha_cadastral_service imports this module."""
    from app.modules.card_hub import ficha_cadastral_service

    try:
        out = ficha_cadastral_service.reaplicar_fichas_pelo_cpf(
            client, org_id, UUID(str(cliente_id)), cpf,
            excluir_documento_id=excluir_documento_id,
        )
    except Exception:  # noqa: BLE001 - the CPF write already landed
        logger.exception("cpf_conhecido: re-applying stored bank forms failed for %s", cliente_id)
        return []
    if out["pessoas"]:
        logger.info(
            "cpf_conhecido: %d bank-form person(s) applied to %s from %d stored reading(s)",
            out["pessoas"], cliente_id, len(out["documentos"]),
        )
    return out["conflitos"]


# ─── The endereço group (migration 153) ──────────────────────────────────────


def _endereco_json(partes: dict[str, Any], **extra: Any) -> str:
    """A group value as the TEXT a `cliente_campo_conflitos` row holds —
    JSON, so `resolver_conflito` can write the seven parts back exactly and
    the admin notification still reads as the address it is."""
    corpo = {p: partes.get(p) for p in ENDERECO_PARTES}
    if partes.get("bairro_origem") and not _vazio(partes.get("bairro")):
        # Migration 194 — a CEP-looked-up bairro says so on the conflict
        # row too, and `resolver_conflito` writes it back verbatim.
        corpo["bairro_origem"] = partes["bairro_origem"]
    corpo.update({k: v for k, v in extra.items() if v is not None})
    return json.dumps(corpo, ensure_ascii=False)


def _mesmo_endereco(atual: dict[str, Any], proposto: dict[str, Any]) -> bool:
    """Same address iff every part the reading HAS agrees with the record.
    A part the reading lacks (no complemento on the bill) is not a
    disagreement.

    🔴 Owner directive, 2026-09-29: `logradouro` is compared through
    `divergencia_resolucao.normalizar_logradouro` FIRST — "AV Paulista" and
    "Avenida Paulista" collapse to the same canonical string before
    `_mesmo_nome` ever runs, so an abbreviation/format difference (measured:
    4/9 logradouro precision against the P2 answer keys, largely AV/AVENIDA-
    shaped) no longer opens a conflict a human then has to resolve by eye.
    """
    for parte in ENDERECO_PARTES:
        novo = proposto.get(parte)
        if _vazio(novo):
            continue
        velho = atual.get(f"endereco_{parte}")
        if parte == "bairro" and proposto.get("bairro_origem") == ORIGEM_BAIRRO_CEP:
            # A CEP-looked-up bairro is a GAP-FILL, never a second opinion:
            # a recorded bairro (printed on a document) always wins, and a
            # record without one is filled by `_preencher_so_bairro`, not by
            # treating the whole group as a different address.
            continue
        if _vazio(velho):
            return False
        if parte == "cep":
            if only_digits(str(velho)) != only_digits(str(novo)):
                return False
        elif parte == "logradouro":
            if divergencia_resolucao.normalizar_logradouro(
                str(velho)
            ) != divergencia_resolucao.normalizar_logradouro(str(novo)):
                return False
        elif not _mesmo_nome(str(velho), str(novo)):
            return False
    return True


def _titular_do_documento(client: Any, org_id: UUID, documento_id: Optional[Any]) -> Optional[str]:
    """The RAW holder name a `cliente_documentos` row's own comprovante
    read carried (`extracao_endereco_titular`, written unconditionally by
    `extrair_identidade`) — the same signal for the CURRENT on-file address
    (looked up via `endereco_documento_id`) and a NEW reading (via its own
    `documento_id`), so the holder-tiebreak below compares two readings the
    SAME way regardless of which one already made it onto `clientes`."""
    if not documento_id:
        return None
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("extracao_endereco_titular")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0].get("extracao_endereco_titular") if rows else None


def _titular_e_parte_ou_conjuge(
    client: Any, org_id: UUID, cliente_row: dict, titular_nome: Optional[str]
) -> Optional[bool]:
    """Does `titular_nome` name THIS cliente, their linked spouse, or
    another PARTY of the same `atendimento` (R2, owner directive,
    2026-09-30 — a co-seller's/co-buyer's own bill is household evidence
    too, exactly like a spouse's)? `None` when there is nothing to check
    (no titular read at all) — never conflated with `False` (a titular that
    was read and named someone genuinely else), so a caller can tell
    "unknown" from "verified not them"."""
    if not titular_nome:
        return None
    if _nomes_bate(cliente_row, titular_nome):
        return True
    conjuge_id = cliente_row.get("conjuge_cliente_id")
    if conjuge_id:
        conjuge_rows = (
            _t(client, CLIENTES_TABLE)
            .select("nome,nome_completo,nome_oficial")
            .eq("org_id", str(org_id))
            .eq("id", str(conjuge_id))
            .limit(1)
            .execute()
        ).data or []
        if conjuge_rows and _nomes_bate(conjuge_rows[0], titular_nome):
            return True
    cliente_id = cliente_row.get("id")
    outras_ids = _pessoas_dos_cards(client, org_id, UUID(str(cliente_id))) if cliente_id else []
    if outras_ids:
        outras_rows = (
            _t(client, CLIENTES_TABLE)
            .select("nome,nome_completo,nome_oficial")
            .eq("org_id", str(org_id))
            .in_("id", outras_ids)
            .execute()
        ).data or []
        if any(_nomes_bate(r, titular_nome) for r in outras_rows):
            return True
    return False


#: Holder ranks for the address rule. A bill whose holder is the party (or
#: their linked spouse) is the party's OWN evidence; one whose holder is a
#: co-party of the atendimento (R2) is household evidence — weaker. Equal
#: ranks never auto-resolve (a human decides), so a gap beats a coin flip.
_TITULAR_PROPRIO, _TITULAR_PARTE, _TITULAR_NENHUM = 2, 1, 0


def _rank_titular(
    client: Any, org_id: UUID, cliente_row: dict,
    titular_nome: Optional[str], origem: Optional[str],
) -> tuple[int, Optional[bool]]:
    """`(rank, verificado)` for one side of an address disagreement.
    `verificado` keeps `_titular_e_parte_ou_conjuge`'s tri-state (`None` =
    nothing to check) for the R2 auto-reject branch. A declared-address
    source (`ORIGENS_ENDERECO_DECLARADO`) is the party's own by construction."""
    if origem in ORIGENS_ENDERECO_DECLARADO:
        return _TITULAR_PROPRIO, True
    if not titular_nome:
        return _TITULAR_NENHUM, None
    if _nomes_bate(cliente_row, titular_nome):
        return _TITULAR_PROPRIO, True
    conjuge_id = cliente_row.get("conjuge_cliente_id")
    if conjuge_id:
        conjuge_rows = (
            _t(client, CLIENTES_TABLE)
            .select("nome,nome_completo,nome_oficial")
            .eq("org_id", str(org_id))
            .eq("id", str(conjuge_id))
            .limit(1)
            .execute()
        ).data or []
        if conjuge_rows and _nomes_bate(conjuge_rows[0], titular_nome):
            return _TITULAR_PROPRIO, True
    verificado = _titular_e_parte_ou_conjuge(client, org_id, cliente_row, titular_nome)
    return (_TITULAR_PARTE if verificado else _TITULAR_NENHUM), verificado


#: F3: a cidade candidate this long, or carrying a digit, is not a real
#: city name — a whole-address string or a CEP fragment landed in the field
#: instead. Measured (live prod test, 2026-09-30): a `comprovante_endereco`
#: read a 57-char whole-address string into `cidade` for 2/19 people.
_CIDADE_MAX_CHARS = 40


def _cidade_suspeita(cidade: str) -> bool:
    return len(cidade) > _CIDADE_MAX_CHARS or bool(re.search(r"\d", cidade))


def _norm_bairro(valor: str) -> str:
    """Accent/case/space-insensitive bairro comparison — log-only use."""
    return " ".join(strip_accents_upper(valor).split())


def _enriquecer_endereco_via_cep(
    partes: dict[str, Any],
    cep_lookup: Optional[CepLookupAdapter],
    *,
    documento_id: Optional[UUID],
) -> dict[str, Any]:
    """F3 (live prod test, 2026-09-30): CEP is the AUTHORITY for cidade/uf
    once it resolves — the CEP printed on a document was correct for 15/19
    people measured while the document's own cidade/uf TEXT was wrong for
    4/19 (a neighbourhood-shaped value once, a whole-address string landed
    in `cidade` twice). `logradouro` stays the document's own read either
    way — a CEP range's logradouro is advisory, usually less specific than
    a document's own; a genuine disagreement is only LOGGED, never applied.

    No-op when `cep_lookup` is `None` (no adapter configured for this call
    site — every pre-existing caller keeps behaving exactly as before) or
    the group has no CEP to resolve. Never raises: a lookup failure is
    `cep_lookup`'s OWN job to log and return `None` for (see
    `noctusai_lib.integrations.cep`'s own docstring) — this function treats
    that `None` exactly like "nothing to enrich with".

    🔴 NEVER LOGS ADDRESS TEXT (LGPD) — lengths/booleans/IDs only, the same
    discipline every OTHER log line in this module already follows.
    """
    cidade = partes.get("cidade")
    if cidade and _cidade_suspeita(str(cidade)):
        logger.warning(
            "identidade_extracao: cidade descartada por formato suspeito "
            "(%d chars, contem_digito=%s), documento=%s",
            len(str(cidade)), bool(re.search(r"\d", str(cidade))), documento_id,
        )
        partes = {**partes, "cidade": None}

    if cep_lookup is None or _vazio(partes.get("cep")):
        return partes

    resultado = cep_lookup.lookup(str(partes["cep"]))
    if resultado is None:
        return partes

    partes = dict(partes)
    if partes.get("cidade") != resultado.cidade:
        partes["cidade"] = resultado.cidade
    if partes.get("uf") != resultado.uf:
        partes["uf"] = resultado.uf

    # Extraction defect (2026-10-03): a document that prints no bairro left
    # the group incomplete and the contract gate blocked on "Endereço
    # completo". The CEP's bairro fills ONLY that gap (`bairro_origem='cep'`,
    # migration 194). A document that DOES print a bairro keeps it, even when
    # the CEP's differs — a CEP range's bairro name is often the generic one
    # (a city-wide `NNNNN-000` CEP carries none at all).
    if resultado.bairro:
        if _vazio(partes.get("bairro")):
            partes["bairro"] = resultado.bairro
            partes["bairro_origem"] = ORIGEM_BAIRRO_CEP
        elif _norm_bairro(str(partes["bairro"])) != _norm_bairro(resultado.bairro):
            logger.info(
                "identidade_extracao: bairro do CEP diverge do documento — "
                "mantendo o do documento, documento=%s",
                documento_id,
            )

    logradouro_doc = partes.get("logradouro")
    if resultado.logradouro and logradouro_doc and (
        divergencia_resolucao.normalizar_logradouro(str(logradouro_doc))
        != divergencia_resolucao.normalizar_logradouro(resultado.logradouro)
    ):
        logger.info(
            "identidade_extracao: logradouro do CEP diverge do documento — "
            "mantendo o do documento, documento=%s",
            documento_id,
        )

    return partes


def _bairro_origem_da_leitura(partes: dict[str, Any]) -> Optional[str]:
    """`endereco_bairro_origem` for a whole-group write of `partes`: `'cep'`
    when the bairro came from the CEP lookup, NULL otherwise (the bairro, if
    any, shares the group's own `endereco_origem`)."""
    if _vazio(partes.get("bairro")):
        return None
    return partes.get("bairro_origem") or None


def _preencher_so_bairro(
    client: Any,
    cliente_id: UUID,
    atual: dict[str, Any],
    partes: dict[str, Any],
    origem: str,
    documento_id: Optional[UUID],
) -> bool:
    """The conflict-safe D1 gap-fill for the bairro ALONE (extraction defect,
    2026-10-03): the record already holds this very address (every OTHER
    part the reading has agrees) and is only missing the bairro — or holds a
    CEP-looked-up bairro the reading now prints for real (a document's
    bairro always beats the lookup's). Writes `endereco_bairro` + its own
    provenance (migration 194), nothing else: the group's provenance, and
    any human confirmation of the parts already there, stay untouched.

    Never fires on a human-typed/cleared group (`endereco_origem='manual'`),
    never replaces a bairro a document printed, and never lets a CEP bairro
    replace anything. Returns True when it wrote.
    """
    if atual.get("endereco_origem") == "manual":
        return False
    novo = partes.get("bairro")
    if _vazio(novo):
        return False
    velho = atual.get("endereco_bairro")
    novo_e_cep = partes.get("bairro_origem") == ORIGEM_BAIRRO_CEP
    if not _vazio(velho):
        if atual.get(COLUNA_BAIRRO_ORIGEM) != ORIGEM_BAIRRO_CEP or novo_e_cep:
            return False
        if _mesmo_nome(str(velho), str(novo)):
            return False
    sem_bairro = {p: v for p, v in partes.items() if p not in ("bairro", "bairro_origem")}
    if not _mesmo_endereco(atual, sem_bairro):
        return False
    if novo_e_cep:
        bairro_origem: Optional[str] = ORIGEM_BAIRRO_CEP
    elif documento_id is not None and str(documento_id) == str(
        atual.get("endereco_documento_id") or ""
    ):
        bairro_origem = None  # the group's own document — same source
    else:
        bairro_origem = origem
    _t(client, CLIENTES_TABLE).update(
        {"endereco_bairro": novo, COLUNA_BAIRRO_ORIGEM: bairro_origem, "updated_at": _now()}
    ).eq("id", str(cliente_id)).execute()
    logger.info(
        "identidade_extracao: bairro preenchido sozinho (origem=%s), cliente=%s documento=%s",
        bairro_origem or atual.get("endereco_origem"), cliente_id, documento_id,
    )
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
    cep_lookup: Optional[CepLookupAdapter] = None,
    avisos: Optional[list[str]] = None,
) -> tuple[bool, Optional[dict]]:
    """Apply one comprovante's address to the cliente as ONE group (D1).

    - Group EMPTY -> all seven parts written, `endereco_*` provenance,
      machine-pending — WHOEVER the bill names (owner rule H1, 2026-10-03:
      "the first document fills empty fields"; P5 audit F1/B5: a bill in a
      relative's name, or a joint "A E B" holder line, used to open a
      conflict against an EMPTY group, so the address never landed and a
      human had to accept it by hand). When the printed holder matches
      nobody, `AVISO_TITULAR_NAO_CONFERE` is appended to `avisos` so the
      caller flags the SOURCE document — the value stays machine-pending
      for the contract's validation gate either way.
    - Group SET and the comprovante prints a holder whose name does NOT
      match this cliente -> conflict (unless it states the address already
      on file), never a silent replace. The proposed value records whose
      name the bill carries.
    - Only the LOGRADOURO is required to apply (a bill whose CEP was not
      read still carries the address; the contract gate's completeness
      check is where a missing part is shown).
    - Group SET and the reading differs -> conflict; same -> nothing.
    - Group SET, the reading differs, but it's a RE-READ of the SAME still
      machine-pending document (`campo_conflitos.mesmo_documento_pendente`,
      D1 same-document-re-read refinement, 2026-09-25) -> replaces, no
      conflict — the earlier pass's own incompleteness, not a second
      opinion. A human-confirmed or manually-typed address is NEVER
      replaced this way.
    - Human-cleared group (`endereco_origem='manual'`, all parts empty) ->
      respected, like any other field.
    - **F3 (2026-09-30)** — before anything else runs, `cidade`/`uf` are
      enriched (or a garbage `cidade` withheld) via `_enriquecer_endereco_
      via_cep` when a `cep_lookup` adapter is given; every comparison,
      conflict and write below sees the ENRICHED `partes`, never the raw
      document read.

    Returns `(aplicado, conflito_novo_ou_None)`.
    """
    if _vazio(partes.get("logradouro")):
        return False, None
    partes = _enriquecer_endereco_via_cep(partes, cep_lookup, documento_id=documento_id)
    # Canonical ON WRITE (`canonical-identifiers`): a CEP that fits is stored
    # `13010-110`; one that does not fit stays as read.
    partes = {
        **partes,
        "cep": None if _vazio(partes.get("cep")) else idf.canonico_ou_bruto("cep", partes.get("cep")),
    }
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join([
            "id", "nome", "nome_completo", "nome_oficial", "conjuge_cliente_id",
            "endereco_origem", "endereco_documento_id", "endereco_confirmado_em",
            COLUNA_BAIRRO_ORIGEM, *ENDERECO_COLUNAS,
        ]))
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

    def escrever(agora: str) -> None:
        updates: dict[str, Any] = {
            f"endereco_{p}": (None if _vazio(partes.get(p)) else partes.get(p))
            for p in ENDERECO_PARTES
        }
        updates.update(
            {
                COLUNA_BAIRRO_ORIGEM: _bairro_origem_da_leitura(partes),
                "endereco_origem": origem,
                "endereco_documento_id": str(documento_id) if documento_id else None,
                "endereco_em": agora,
                "endereco_confirmado_por": None,
                "endereco_confirmado_em": None,
                "updated_at": agora,
            }
        )
        _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()

    grupo_limpo_por_humano = atual.get("endereco_origem") == "manual" and all(
        v is None or (isinstance(v, str) and not v.strip()) for v in anterior.values()
    )

    if titular_documento and not _nomes_bate(atual, titular_documento):
        if not tem_endereco:
            # Owner rule H1 — an EMPTY group is filled by the first
            # document, whoever the bill names; the mismatch is flagged on
            # the document, never turned into a conflict against nothing.
            if grupo_limpo_por_humano:
                return False, None
            if avisos is not None:
                avisos.append(AVISO_TITULAR_NAO_CONFERE)
            escrever(_now())
            return True, None
        # A bill in someone else's name that states the address ALREADY
        # on file asks nothing — there is no second value to choose
        # between (prod, 2026-09-29: two conflicts were a re-read of the
        # very document on file, same address, differing only in whose
        # name the bill carries).
        if _mesmo_endereco(atual, partes):
            return False, None
        return False, conflito()

    if tem_endereco:
        if _preencher_so_bairro(client, cliente_id, atual, partes, origem, documento_id):
            return True, None
        if _mesmo_endereco(atual, partes):
            return False, None
        if campo_conflitos.mesmo_documento_pendente(
            origem_atual=atual.get("endereco_origem"),
            confirmado_em_atual=atual.get("endereco_confirmado_em"),
            documento_id_atual=atual.get("endereco_documento_id"),
            documento_id_proposto=documento_id,
        ):
            escrever(_now())
            campo_conflitos.fechar_conflitos_pendentes(
                client, campo_conflitos.CLIENTE, org_id, cliente_id,
                CAMPO_ENDERECO, decidido_por=None,
            )
            return True, None
        # Owner directive, 2026-09-29 follow-up: a genuine two-comprovante
        # disagreement resolves by HOLDER — the comprovante whose printed
        # titular is verifiably this party OR their linked spouse wins over
        # one whose titular is neither. Ambiguous (both, neither, or a
        # titular this pass cannot read on one/both sides) still needs a
        # human — never a coin flip. Never fires against a value a human
        # already typed or confirmed (`origem='manual'`/`endereco_
        # confirmado_em` set) — same guard `mesmo_documento_pendente`/
        # `_nome_anterior_confirma_adocao` apply, for the same reason: a
        # real person's decision outranks any reading, automatic or not.
        origem_atual_grupo = atual.get("endereco_origem")
        pode_resolver_automaticamente = (
            bool(origem_atual_grupo)
            and origem_atual_grupo != "manual"
            and not atual.get("endereco_confirmado_em")
        )
        if not pode_resolver_automaticamente:
            decisao = divergencia_resolucao.Decisao(
                vencedor=None, regra="requer_humano",
                motivo=(
                    "endereco: o valor em registro foi digitado ou "
                    "confirmado por um humano — apenas um humano decide."
                ),
                requer_humano=True,
            )
        else:
            decisao = _decisao_endereco_por_titular(
                client, org_id, atual,
                _titular_do_documento(client, org_id, atual.get("endereco_documento_id")),
                titular_documento or _titular_do_documento(client, org_id, documento_id),
                origem_novo=origem,
            )
        campo_conflitos.registrar_decisao_automatica(
            client, campo_conflitos.CLIENTE, org_id, cliente_id, CAMPO_ENDERECO,
            valor_anterior=_endereco_json(anterior) if tem_endereco else None,
            origem_anterior=atual.get("endereco_origem"),
            valor_proposto=_endereco_json(partes, titular=titular_documento),
            origem_proposto=origem,
            confianca_proposta=confianca,
            fonte_tabela=DOCUMENTOS_TABLE if documento_id else None,
            fonte_id=documento_id,
            decisao=decisao,
        )
        if decisao.requer_humano:
            return False, conflito()
        if decisao.vencedor == "proposto":
            escrever(_now())
            campo_conflitos.fechar_conflitos_pendentes(
                client, campo_conflitos.CLIENTE, org_id, cliente_id,
                CAMPO_ENDERECO, decidido_por=None,
            )
            return True, None
        # decisao.vencedor == "atual": the record already holds the address
        # the verified holder printed — nothing to write, the audit row
        # alone records the resolver ran.
        return False, None
    if grupo_limpo_por_humano:
        return False, None

    escrever(_now())
    return True, None


# ─── Comprovante address attribution (P2, 2026-09-28) ───────────────────────
#
# Measured against the P2 corpus (9 real comprovantes vs 10 signed contracts):
# 7/9 bills named a party OF THE DEAL as the account holder, and in every such
# case the contract used that bill's address for that party AND their spouse.
# 1 bill was in a non-party's name and the contract did NOT use it; 1 was the
# buyer's own name but the contract used a DIFFERENT address (never applied
# unattended either way — see `aplicar_endereco_ao_cliente`'s own docstring).
#
# `aplicar_endereco_ao_cliente`'s `titular_documento` guard already refuses to
# fill THIS `cliente_id` when the bill names someone else — but a document is
# routinely uploaded onto one party's card while naming their SPOUSE or a
# CO-PARTY on the same deal, and that case must attribute the address to the
# right person instead of just conflicting the wrong one. `_pessoa_do_card_
# por_nome` resolves who on this card the bill's holder actually is (self,
# linked spouse, or a co-party on a shared atendimento) — `nobody` still falls
# through to the existing conflict path unchanged, which is the review queue.


def _nomes_bate(row: dict, nome: str) -> bool:
    candidatos = [row.get("nome_oficial"), row.get("nome_completo"), row.get("nome")]
    return any(
        nomes_compativeis(parte, n)
        for parte in _nomes_do_titular(nome)
        for n in candidatos
        if n
    )


#: A joint holder line — "ANA SOUZA E BRUNO SOUZA", "ANA SOUZA & BRUNO
#: SOUZA", "ANA SOUZA / BRUNO SOUZA" (P5 audit B5, deal 875: a comprovante
#: whose holder printed BOTH buyers matched neither, so the address never
#: landed). Each name is checked on its own.
_SEPARADOR_TITULARES = re.compile(r"\s+E\s+|\s*[&/;]\s*", re.IGNORECASE)


def _nomes_do_titular(titular: str) -> list[str]:
    """Every person a comprovante's holder line names — the whole line
    first (a single name is the common case), then each joint part."""
    partes = [p.strip() for p in _SEPARADOR_TITULARES.split(titular or "") if p and p.strip()]
    return list(dict.fromkeys([titular.strip(), *partes])) if titular and titular.strip() else []


def _pessoa_do_card_por_nome(
    client: Any, org_id: UUID, cliente_id: UUID, nome: str
) -> Optional[str]:
    """The cliente on this card whose own name matches `nome`, or None.

    `cliente_id` itself first (the common case — the bill's holder IS the
    person the document was uploaded onto), then the linked spouse (`conjuge_
    cliente_id` — authoritative, same order `_cliente_do_outro_conjuge` checks
    it in), then every OTHER person on a shared atendimento. More than one
    match among those others is ambiguous and resolves to None — silence over
    a guess, the same posture an ambiguous spouse candidate already takes.
    Never invents a cliente.
    """
    colunas = "id,nome,nome_completo,nome_oficial,conjuge_cliente_id"
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(colunas)
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    proprio = rows[0]
    if _nomes_bate(proprio, nome):
        return str(cliente_id)

    candidatos_ids: set[str] = set()
    vinculo = proprio.get("conjuge_cliente_id")
    if vinculo:
        candidatos_ids.add(str(vinculo))
    candidatos_ids.update(_pessoas_dos_cards(client, org_id, cliente_id))
    if not candidatos_ids:
        return None
    outras = (
        _t(client, CLIENTES_TABLE)
        .select("id,nome,nome_completo,nome_oficial")
        .eq("org_id", str(org_id))
        .in_("id", list(candidatos_ids))
        .execute()
    ).data or []
    achados = [r for r in outras if _nomes_bate(r, nome)]
    return str(achados[0]["id"]) if len(achados) == 1 else None


def _conjuge_vinculado(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[str]:
    """The cliente already linked as this one's spouse (`conjuge_cliente_id`),
    or None — used to propagate a comprovante's address onto both halves of an
    already-modelled couple once it has been applied to one of them."""
    rows = (
        _t(client, CLIENTES_TABLE)
        .select("conjuge_cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0].get("conjuge_cliente_id") if rows else None


# ─── R3: household address propagation (owner directive, 2026-09-30) ───────
#
# Measured live (5 historical deals re-run on prod): a married second spouse
# with no comprovante of their own ends with NO address on file in 5/5
# couples, even though the signed contract gives both spouses the household
# address. `aplicar_endereco_ao_cliente`'s own spouse-propagation (P2, above)
# only fires from the SAME comprovante at the moment it is applied; it never
# revisits a spouse whose empty address predates that fix, or one linked
# AFTER the first spouse's address already landed (a certidão read later).
# `propagar_endereco_domicilio` closes both gaps — called from `revalidar_
# negociacao` after every extraction, so it converges regardless of arrival
# order.


def _endereco_e_proprio(row: dict) -> bool:
    """Does this cliente row carry an address from a REAL document — never
    itself an `ORIGEM_CONJUGE_DOMICILIO` derivative? The only valid
    propagation SOURCE, and the bar `_decisao_endereco_por_titular`'s R2
    auto-reject guard also uses (`endereco_origem` truthy and not the
    derived tag)."""
    origem = row.get("endereco_origem")
    if not origem or origem == ORIGEM_CONJUGE_DOMICILIO:
        return False
    return any(not _vazio(row.get(f"endereco_{p}")) for p in ENDERECO_PARTES)


def _limpar_endereco_domicilio(client: Any, org_id: UUID, cliente_id: Any) -> None:
    """Un-fill a `conjuge_domicilio`-derived address — the source it was
    copied from no longer qualifies (retracted, cleared, or the spouse link
    itself is gone). Never touches a REAL document's address; the caller
    (`propagar_endereco_domicilio`) only calls this on a row it already
    confirmed carries the derived tag."""
    now = _now()
    updates: dict[str, Any] = {f"endereco_{p}": None for p in ENDERECO_PARTES}
    updates.update({
        COLUNA_BAIRRO_ORIGEM: None,
        "endereco_origem": None, "endereco_documento_id": None, "endereco_em": None,
        "endereco_confirmado_por": None, "endereco_confirmado_em": None,
        "updated_at": now,
    })
    _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()


def _escrever_endereco_domicilio(client: Any, org_id: UUID, cliente_id: Any, fonte: dict) -> None:
    """Copy `fonte`'s own address onto `cliente_id`, tagged `ORIGEM_CONJUGE_
    DOMICILIO` — machine-pending, like every other D1 write, never
    `manual`."""
    now = _now()
    updates: dict[str, Any] = {
        f"endereco_{p}": fonte.get(f"endereco_{p}") for p in ENDERECO_PARTES
    }
    updates.update({
        COLUNA_BAIRRO_ORIGEM: fonte.get(COLUNA_BAIRRO_ORIGEM),
        "endereco_origem": ORIGEM_CONJUGE_DOMICILIO,
        "endereco_documento_id": fonte.get("endereco_documento_id"),
        "endereco_em": now, "endereco_confirmado_por": None, "endereco_confirmado_em": None,
        "updated_at": now,
    })
    _t(client, CLIENTES_TABLE).update(updates).eq("id", str(cliente_id)).execute()


_COLUNAS_DOMICILIO = (
    "id,conjuge_cliente_id,endereco_origem,endereco_documento_id,"
    + COLUNA_BAIRRO_ORIGEM + "," + ",".join(ENDERECO_COLUNAS)
)


def propagar_endereco_domicilio(client: Any, org_id: UUID, cliente_id: UUID) -> None:
    """R3 — a cliente with an EMPTY address whose linked spouse has one from
    their OWN document inherits it (`ORIGEM_CONJUGE_DOMICILIO`, a tier below
    any real document — `_endereco_e_proprio` never treats a derived copy as
    a further propagation source, so it goes exactly one hop). Convergent
    and idempotent: safe to call after every extraction, on either half of a
    couple — it resolves both directions from whichever `cliente_id` it is
    given.

    Never touches a cliente whose address is their OWN (a real
    `endereco_origem`) or human-typed/confirmed (`'manual'`, or any
    `endereco_confirmado_em`) — same "never overwrite" D1 posture every
    other field group holds. Retraction: when a cliente's OWN CURRENT
    `endereco_origem` is already `ORIGEM_CONJUGE_DOMICILIO` but the spouse
    no longer offers a qualifying source (their document was retracted,
    their address changed, or the link itself is gone), the derived copy is
    cleared rather than left stale — a derived fact must never outlive the
    fact it was derived from.
    """
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(_COLUNAS_DOMICILIO)
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return
    eu = rows[0]
    conjuge_id = eu.get("conjuge_cliente_id")
    outro: Optional[dict] = None
    if conjuge_id:
        outro_rows = (
            _t(client, CLIENTES_TABLE)
            .select(_COLUNAS_DOMICILIO)
            .eq("org_id", str(org_id))
            .eq("id", str(conjuge_id))
            .limit(1)
            .execute()
        ).data or []
        outro = outro_rows[0] if outro_rows else None

    def sincronizar(alvo: dict, fonte: Optional[dict]) -> None:
        origem_alvo = alvo.get("endereco_origem")
        if origem_alvo not in (None, ORIGEM_CONJUGE_DOMICILIO):
            return  # a real address of their own — never touched
        fonte_valida = fonte is not None and _endereco_e_proprio(fonte)
        if not fonte_valida:
            if origem_alvo == ORIGEM_CONJUGE_DOMICILIO:
                _limpar_endereco_domicilio(client, org_id, alvo["id"])
            return
        fonte_partes = {p: fonte.get(f"endereco_{p}") for p in ENDERECO_PARTES}
        if origem_alvo == ORIGEM_CONJUGE_DOMICILIO and _mesmo_endereco(alvo, fonte_partes):
            return  # already in sync — no write needed
        _escrever_endereco_domicilio(client, org_id, alvo["id"], fonte)

    sincronizar(eu, outro)
    if outro is not None:
        sincronizar(outro, eu)


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
    # Paged: one unpaged read silently capped the org-wide queue (and the
    # identifier backfill that re-resolves it) at PostgREST's 1000 rows.
    eq_filters = {"status": "pendente"}
    if cliente_id is not None:
        eq_filters["cliente_id"] = str(cliente_id)
    rows = table_reads.paged_rows(
        client, CONFLITOS_TABLE, org_id, eq_filters=eq_filters
    )
    return sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)


#: `CampoExtraido.item_key` -> the key a `extracao_conjuges` entry carries
#: that fact under (the `registro_conjuges` shape `extrair_identidade`
#: writes). A per-person campo absent here (`rg`, `rg_orgao_expedidor`) is
#: one a certidão never states per spouse — it can never be attributed.
_CHAVE_CONJUGE: dict[str, str] = {
    "nome_oficial": "nome",
    "cpf": "cpf",
    "data_nascimento": "data_nascimento",
    "genero": "genero",
    "profissao": "profissao",
}


def _documentos_vivos(client: Any, org_id: UUID, cliente_ids: list[str]) -> list[dict]:
    """Every non-deleted `cliente_documentos` row of these clientes."""
    # Batched IN (URL length) x paged (row cap): neither bound may silently
    # truncate the evidence a backfill over many clientes judges against.
    return [
        row
        for lote in table_reads.batched(cliente_ids)
        for row in table_reads.paged_rows(
            client, DOCUMENTOS_TABLE, org_id,
            refine=lambda q, lote=lote: q.in_("cliente_id", lote).is_("deleted_at", "null"),
        )
    ]


def _entrada_conjuge_da_pessoa(
    conjuges: Any, cliente_id: str, cpf_cliente: Optional[str]
) -> Optional[dict]:
    """The `extracao_conjuges` entry that IS this person — attributed by
    `extrair_identidade` (`cliente_id`), else by a CPF match. `None` when no
    entry can be attributed (a pre-attribution read, or an unmatched pair)."""
    if isinstance(conjuges, str):
        try:
            conjuges = json.loads(conjuges)
        except ValueError:
            logger.warning("extracao_conjuges is not JSON for cliente %s", cliente_id)
            return None
    cpf = only_digits(str(cpf_cliente or ""))
    for e in conjuges or []:
        if not isinstance(e, dict):
            continue
        if e.get("cliente_id") == cliente_id or (cpf and only_digits(str(e.get("cpf") or "")) == cpf):
            return e
    return None


def evidencia_viva(
    campo: CampoExtraido,
    cliente_row: dict,
    documentos: list[dict],
    *,
    atual_sustentado: Optional[bool] = None,
    proposto_sustentado: Optional[bool] = None,
) -> divergencia_resolucao.EvidenciaViva:
    """What this person's live documents assert about `campo` right now —
    `divergencia_resolucao.EvidenciaViva`. `documentos` is the person's own
    non-deleted rows plus their linked spouse's (`_documentos_vivos`); the
    two `*_sustentado` flags come from `_sustentado`, per side.

    Attribution rules for `afirmacoes`:
    - An address-only type (`TIPOS_ENDERECO`) never asserts an identity fact
      — its printed name is the bill holder's (same rule `TIPOS_ENDERECO`
      documents for the apply path).
    - A two-person document (`divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS`)
      asserts a per-person fact only through the spouse entry that is this
      person (`_entrada_conjuge_da_pessoa`) — never its flat columns, which
      name nobody in particular. Couple-level facts read its flat columns.
    - A spouse's document counts ONLY through that attribution (it is the
      same certidão, uploaded on the other spouse's record)."""
    cliente_id = str(cliente_row["id"])
    afirmacoes: list[tuple[Any, str]] = []
    for d in documentos:
        tipo = d.get("tipo_documento")
        if not tipo or tipo in TIPOS_ENDERECO:
            continue
        if (
            tipo in divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS
            and campo.item_key in divergencia_resolucao.CAMPOS_POR_PESSOA
        ):
            valor = _valor_atribuido(campo, cliente_row, d)
        elif str(d.get("cliente_id")) != cliente_id:
            continue
        else:
            valor = d.get(_coluna_lida_no_documento(campo))
        if not _vazio(valor):
            afirmacoes.append((valor, tipo))
    return divergencia_resolucao.EvidenciaViva(
        afirmacoes=tuple(afirmacoes),
        atual_sustentado=atual_sustentado,
        proposto_sustentado=proposto_sustentado,
    )


def _valor_atribuido(campo: CampoExtraido, cliente_row: dict, documento: dict) -> Any:
    """A two-person document's reading of a per-person `campo` FOR THIS
    person — from the spouse entry attributed to them, never the flat
    columns. `None` when no entry is theirs or it does not state the fact."""
    entrada = _entrada_conjuge_da_pessoa(
        documento.get("extracao_conjuges"), str(cliente_row["id"]), cliente_row.get("cpf")
    )
    chave = _CHAVE_CONJUGE.get(campo.item_key)
    return entrada.get(chave) if entrada is not None and chave else None


#: Campos only ever written from their own extraction column — a re-read of
#: the document behind one that now carries NOTHING there has retracted it.
#: Others can be DERIVED onto `clientes` without their column (nacionalidade
#: from a civil RG issuer, f037cfbcf), so an empty column there says nothing.
_CAMPOS_SO_DA_PROPRIA_COLUNA = frozenset({"nome_oficial", "cpf", "rg", "data_nascimento"})


def _documento_sustenta(
    campo: CampoExtraido, cliente_row: dict, documento: Optional[dict], valor: Any
) -> Optional[bool]:
    """Does THIS document (the one a value came from) still assert `valor`?
    `False` on positive evidence only: the row is soft-deleted, it now
    reads a different value, it is a two-person document with no reading
    attributed to this person, or (for `_CAMPOS_SO_DA_PROPRIA_COLUNA`) its
    re-read carries nothing. `None` when it cannot tell."""
    if documento is None:
        # Documents are soft-deleted; an id with no row at all points
        # somewhere else (another table), not at a retraction.
        return None
    if documento.get("deleted_at"):
        return False
    if (
        documento.get("tipo_documento") in divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS
        and campo.item_key in divergencia_resolucao.CAMPOS_POR_PESSOA
    ):
        lido = _valor_atribuido(campo, cliente_row, documento)
        return False if _vazio(lido) else _mesmo_valor(campo.item_key, lido, valor)
    coluna = _coluna_lida_no_documento(campo)
    if not coluna:
        return None  # no document column for this campo — cannot tell
    lido = documento.get(coluna)
    if _vazio(lido):
        return False if campo.item_key in _CAMPOS_SO_DA_PROPRIA_COLUNA else None
    return _mesmo_valor(campo.item_key, lido, valor)


def _sustentado(
    client: Any,
    org_id: UUID,
    campo: CampoExtraido,
    cliente_row: dict,
    documento_id: Optional[Any],
    valor: Any,
    cache: dict[str, Optional[dict]],
    *,
    origem: Optional[str],
    vouched: bool = False,
) -> Optional[bool]:
    """`_documento_sustenta` for the document `documento_id` names (any
    owner — a certidão on the spouse's record counts). `None` — never
    judged retracted — when no document stands behind the value, when a
    human typed or confirmed it (`vouched`: a person now stands behind it,
    not only the document), or when the row's type is not `origem` (that
    id is not the document the value came from)."""
    if vouched or origem == "manual" or not documento_id or _vazio(valor):
        return None
    chave = str(documento_id)
    if chave not in cache:
        rows = (
            _t(client, DOCUMENTOS_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("id", chave)
            .limit(1)
            .execute()
        ).data or []
        cache[chave] = rows[0] if rows else None
    documento = cache[chave]
    if documento is not None and documento.get("tipo_documento") != origem:
        return None
    return _documento_sustenta(campo, cliente_row, documento, valor)


def _evidencia_ao_vivo(
    client: Any, org_id: UUID, cliente_id: UUID, campo: CampoExtraido, valor_atual: Any
) -> Optional[divergencia_resolucao.EvidenciaViva]:
    """`evidencia_viva` for the LIVE apply path. The proposed side is the
    reading being applied right now — its row may not be written yet — so
    only the on-file side is checked (`proposto_sustentado=None`)."""
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(f"id,cpf,conjuge_cliente_id,{campo.documento_id},{campo.origem},{campo.confirmado_em}")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    donos = [str(cliente_id)] + (
        [str(row["conjuge_cliente_id"])] if row.get("conjuge_cliente_id") else []
    )
    return evidencia_viva(
        campo, row, _documentos_vivos(client, org_id, donos),
        atual_sustentado=_sustentado(
            client, org_id, campo, row, row.get(campo.documento_id), valor_atual, {},
            origem=row.get(campo.origem), vouched=bool(row.get(campo.confirmado_em)),
        ),
    )


def _decisao_endereco_por_titular(
    client: Any,
    org_id: UUID,
    atual: dict,
    titular_atual: Optional[str],
    titular_novo: Optional[str],
    *,
    origem_novo: Optional[str] = None,
) -> divergencia_resolucao.Decisao:
    """The holder rule for two disagreeing comprovantes (owner directive,
    2026-09-29 follow-up, extended R2 2026-09-30): the bill whose printed
    titular is verifiably this party, their linked spouse, OR another party
    of the same `atendimento` (`_titular_e_parte_ou_conjuge`) wins over one
    whose titular is neither. Ambiguous (both, neither, or unreadable) needs
    a human — UNLESS the on-file address already came from a document of
    this cliente's own (a real `endereco_origem`, not the R3 household-
    propagation derivative): a definitely-unrelated new holder is then
    auto-REJECTED rather than left pending (R2) — the cliente's own document
    outranks a stranger's, no human needed to say so. The caller owns the
    manual/confirmed guard — this only compares holders.

    Ranked (2026-10-01): the party's/spouse's OWN evidence — including a
    declared-address source such as the bank form (`ORIGENS_ENDERECO_
    DECLARADO`, holder-less by nature) — outranks a co-party's bill, which
    outranks an unverified one. The higher rank wins; equal verified ranks
    (two of the party's own documents disagreeing) need a human, and so does
    a declared source PROPOSED against an on-file document (it defends, it
    never displaces)."""
    rank_atual, holder_atual = _rank_titular(
        client, org_id, atual, titular_atual, atual.get("endereco_origem"),
    )
    rank_novo, holder_novo = _rank_titular(
        client, org_id, atual, titular_novo, origem_novo,
    )
    # A declared source DEFENDS the address on file, but never WINS one: no
    # measured tier makes the bank form outrank a real document of the
    # party's, so a proposed declaration against any on-file document falls
    # through to a human (`ficha_cadastral_service` (d) — never a silent
    # overwrite).
    if rank_novo > rank_atual and origem_novo not in ORIGENS_ENDERECO_DECLARADO:
        return divergencia_resolucao.Decisao(
            vencedor="proposto", regra="endereco_titular",
            motivo=(
                f"endereco: o comprovante novo tem titular verificado "
                f"({titular_novo!r}) contra o em registro (titular "
                f"{titular_atual!r} nao e a parte nem o conjuge)."
            ),
            requer_humano=False,
        )
    if rank_atual > rank_novo:
        return divergencia_resolucao.Decisao(
            vencedor="atual", regra="endereco_titular",
            motivo=(
                f"endereco: o comprovante em registro tem titular "
                f"verificado ({titular_atual!r}) contra o novo (titular "
                f"{titular_novo!r} nao e a parte nem o conjuge)."
            ),
            requer_humano=False,
        )
    origem_propria = atual.get("endereco_origem")
    if (
        holder_novo is False
        and holder_atual is not True
        and origem_propria
        and origem_propria != ORIGEM_CONJUGE_DOMICILIO
    ):
        return divergencia_resolucao.Decisao(
            vencedor="atual", regra="outra_pessoa",
            motivo=(
                f"endereco: o titular do comprovante novo ({titular_novo!r}) "
                f"nao e a parte, o conjuge, nem outra parte desta "
                f"negociacao — mantido o endereco ja registrado por "
                f"documento proprio ({origem_propria!r})."
            ),
            requer_humano=False,
        )
    return divergencia_resolucao.Decisao(
        vencedor=None, regra="requer_humano",
        motivo=(
            "endereco: nenhum dos dois comprovantes tem titular "
            "verificado como a parte, o conjuge, ou outra parte da "
            "negociacao (ou ambos tem) — decisao humana necessaria."
        ),
        requer_humano=True,
    )


def _resolvido(vencedor: str, regra: str, motivo: str) -> divergencia_resolucao.Decisao:
    return divergencia_resolucao.Decisao(
        vencedor=vencedor, regra=regra, motivo=motivo, requer_humano=False
    )


def _documento_vivo(client: Any, org_id: UUID, documento_id: Optional[Any]) -> Optional[bool]:
    """`True` the row exists and is not deleted, `False` deleted/missing,
    `None` no id to check."""
    if not documento_id:
        return None
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id,deleted_at")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    return bool(rows) and not rows[0].get("deleted_at")


def _decidir_endereco_pendente(
    client: Any, org_id: UUID, row: dict
) -> tuple[Optional[divergencia_resolucao.Decisao], Optional[dict]]:
    """Re-consult one pending `endereco` conflict against what is true NOW.
    Returns `(decisao, partes_propostas)`, or `(None, None)` when there is
    nothing on file to compare against (the conflict is not a divergence
    this resolver can judge — reported as composite by the caller).

    🔴 R2 FIX (owner directive, 2026-09-30, live-test evidence): `valor_
    anterior` is legitimately `null` — `aplicar_endereco_ao_cliente`'s own
    `conflito()` writes it that way whenever the conflict opened against an
    EMPTY on-file address (a bill whose holder couldn't be matched at read
    time, with nothing else there yet). This used to be read as "not a
    JSON object" and bailed to `(None, None)` — `ignorado_composto`,
    forever, even once the missing evidence (a name, a co-party's own
    document) later landed; that row was never even reported as still
    needing a human, just silently skipped every backfill pass. `anterior`
    itself is never otherwise used below (the CURRENT `clientes` row,
    fetched fresh as `atual`, is what every branch compares against) — only
    `proposto` needs the shape check.

    Order: a human-typed/confirmed address is never overridden -> the same
    address under today's comparison (the conflict predates a normalisation
    fix, or re-read the very document already on file) -> a side whose
    document was deleted is retracted -> the holder rule."""
    try:
        proposto = json.loads(row.get("valor_proposto") or "null")
    except ValueError:
        logger.warning("endereco conflict %s holds non-JSON values", row.get("id"))
        return None, None
    if not isinstance(proposto, dict):
        return None, None
    atuais = (
        _t(client, CLIENTES_TABLE)
        .select(",".join([
            "id", "nome", "nome_completo", "nome_oficial", "conjuge_cliente_id",
            "endereco_origem", "endereco_documento_id", "endereco_confirmado_em",
            *ENDERECO_COLUNAS,
        ]))
        .eq("org_id", str(org_id))
        .eq("id", str(row["cliente_id"]))
        .limit(1)
        .execute()
    ).data or []
    if not atuais:
        return None, None
    atual = atuais[0]
    partes = {p: proposto.get(p) for p in ENDERECO_PARTES}
    if proposto.get("bairro_origem"):
        partes["bairro_origem"] = proposto["bairro_origem"]
    if atual.get("endereco_origem") == "manual" or atual.get("endereco_confirmado_em"):
        return divergencia_resolucao.Decisao(
            vencedor=None, regra="requer_humano",
            motivo="endereco: o valor em registro foi digitado ou confirmado por um humano.",
            requer_humano=True,
        ), partes
    if _mesmo_endereco(atual, partes):
        return _resolvido(
            "atual", "mesmo_endereco",
            "endereco: pela comparação atual (logradouro normalizado, partes "
            "ausentes não contam) o proposto é o mesmo endereço em registro.",
        ), partes
    proposta_viva = (
        _documento_vivo(client, org_id, row.get("fonte_id"))
        if row.get("fonte_tabela") == DOCUMENTOS_TABLE
        else None
    )
    registro_vivo = _documento_vivo(client, org_id, atual.get("endereco_documento_id"))
    if registro_vivo is False and proposta_viva is not False:
        return _resolvido(
            "proposto", "retratado",
            "endereco: o comprovante que sustentava o endereço em registro foi "
            "excluído; o proposto vem de um documento vivo.",
        ), partes
    if proposta_viva is False and registro_vivo is not False:
        return _resolvido(
            "atual", "retratado",
            "endereco: o comprovante da proposta foi excluído; o endereço em "
            "registro segue sustentado.",
        ), partes
    return _decisao_endereco_por_titular(
        client, org_id, atual,
        _titular_do_documento(client, org_id, atual.get("endereco_documento_id")),
        proposto.get("titular") or _titular_do_documento(client, org_id, row.get("fonte_id")),
        origem_novo=row.get("origem_proposto"),
    ), partes


#: `motivo_resolucao` rule name for a pending conflict whose on-file side
#: is EMPTY — settled by filling it (owner rule H1, P5 audit F1).
REGRA_VAZIO_PREENCHIDO = "vazio_preenchido"


def _preencher_conflito_vazio(
    client: Any, org_id: UUID, row: dict, cliente_row: Optional[dict], now: str,
) -> bool:
    """F1 data repair — a `pendente` conflict whose CURRENT value on
    `clientes` is empty was never a disagreement: D1/H1 says the document
    simply fills it. Applies `valor_proposto` with the document's own
    provenance (`<campo>_origem = origem_proposto`, `_documento_id = fonte`,
    machine-pending — the contract gate still asks a human to vouch), and
    closes the row `resolvido_automatico` (`decidido_por=NULL`,
    `motivo_resolucao='[vazio_preenchido] ... evidência: <documento>'`).

    Refuses (returns False, row left for the ordinary resolver) when the
    field is NOT empty today, when the conflict's own `valor_anterior`
    snapshot was not empty (a value cleared after the conflict opened is a
    human matter), when an operator explicitly cleared it
    (`origem='manual'`, genuinely blank), when the proposal itself is empty
    or an invalid CPF, and for the spouse link (a cliente id, decided by
    `vincular_conjuges`). Idempotent: a settled row is no longer `pendente`.
    """
    if cliente_row is None:
        return False
    if not _vazio(row.get("valor_anterior")):
        # The conflict opened against a REAL value that has since gone —
        # someone cleared it after the fact. Not the F1 shape; a human
        # decides.
        return False
    campo_chave = row["campo"]
    doc_fonte = row.get("fonte_id") if row.get("fonte_tabela") == DOCUMENTOS_TABLE else None
    updates: dict[str, Any]
    if campo_chave == CAMPO_ENDERECO:
        anterior = {p: cliente_row.get(f"endereco_{p}") for p in ENDERECO_PARTES}
        if any(not _vazio(v) for v in anterior.values()):
            return False
        if cliente_row.get("endereco_origem") == "manual" and all(
            v is None or (isinstance(v, str) and not v.strip()) for v in anterior.values()
        ):
            return False
        try:
            proposto = json.loads(row.get("valor_proposto") or "null")
        except ValueError:
            return False
        if not isinstance(proposto, dict) or _vazio(proposto.get("logradouro")):
            return False
        partes = {p: proposto.get(p) for p in ENDERECO_PARTES}
        if proposto.get("bairro_origem"):
            partes["bairro_origem"] = proposto["bairro_origem"]
        updates = {
            f"endereco_{p}": (None if _vazio(partes.get(p)) else partes.get(p))
            for p in ENDERECO_PARTES
        }
        updates.update({
            COLUNA_BAIRRO_ORIGEM: _bairro_origem_da_leitura(partes),
            "endereco_origem": row.get("origem_proposto"),
            "endereco_documento_id": doc_fonte,
            "endereco_em": now,
            "endereco_confirmado_por": None,
            "endereco_confirmado_em": None,
        })
    else:
        campo = CAMPO_POR_CHAVE.get(campo_chave)
        if campo_chave == CAMPO_CONJUGE or campo is None:
            return False
        presente = cliente_row.get(campo.item_key)
        if not _vazio(presente) or _limpo_por_humano(presente, cliente_row.get(campo.origem)):
            return False
        proposto = row.get("valor_proposto")
        if _vazio(proposto):
            return False
        if campo.item_key == "cpf" and not cpf_valido(str(proposto)):
            return False
        updates = {
            campo.item_key: proposto,
            campo.origem: row.get("origem_proposto"),
            campo.documento_id: doc_fonte,
            campo.em: now,
            campo.confirmado_por: None,
            campo.confirmado_em: None,
        }
    updates["updated_at"] = now
    _t(client, CLIENTES_TABLE).update(updates).eq("org_id", str(org_id)).eq(
        "id", str(row["cliente_id"])
    ).execute()
    cliente_row.update(updates)  # the caller's per-run snapshot stays truthful
    campo_conflitos.registrar_decisao_automatica(
        client, campo_conflitos.CLIENTE, org_id, row["cliente_id"], campo_chave,
        valor_anterior=row.get("valor_anterior"),
        origem_anterior=row.get("origem_anterior"),
        valor_proposto=row.get("valor_proposto"),
        origem_proposto=row.get("origem_proposto"),
        decisao=_resolvido(
            "proposto", REGRA_VAZIO_PREENCHIDO,
            f"{campo_chave}: o valor em registro estava vazio — o documento "
            "preenche o campo (D1/H1: o primeiro documento preenche campos vazios).",
        ),
        conflito_existente_id=row["id"],
        evidencia_ids=[doc_fonte] if doc_fonte else (),
    )
    if campo_chave == "cpf":
        cpf_conhecido(client, org_id, row["cliente_id"], row["valor_proposto"])
    return True


def backfill_resolver_conflitos_pendentes(
    client: Any, org_id: UUID, *, cliente_id: Optional[UUID] = None,
    campos: Optional[frozenset[str]] = None,
) -> dict[str, list[dict]]:
    """The callable BACKFILL owner directive (2026-09-29) explicitly asks
    for: re-consult `divergencia_resolucao` against every conflict ALREADY
    `pendente` in prod, exactly the same resolver the LIVE apply path
    (`aplicar_campos_ao_cliente`'s `else:` branch) runs the instant a NEW
    conflict would open. Not an HTTP route — none was asked for — call it
    directly (a script, a REPL, a future scheduled job) per org.

    Scoped to scalar `CAMPOS` fields, resolved via `CAMPO_POR_CHAVE` —
    `CAMPO_ENDERECO`/`CAMPO_CONJUGE` are composite writes with their own
    apply functions (`aplicar_endereco_ao_cliente`/`vincular_conjuges`, a
    JSON blob and a cliente-id respectively, not a single column) and are
    reported under `"ignorado_composto"` rather than silently skipped or
    mis-applied through a scalar write.

    `campos`, when given, restricts the pass to those `campo` names (the
    identifier backfill, `identificadores_backfill`, re-resolves only
    `cpf` / `rg` / `rg_orgao_expedidor`); `None` is every scalar field, as
    before.

    Returns `{"resolvidos": [...], "ainda_pendentes": [...],
    "ignorado_composto": [...]}` — one row (the original conflict, plus
    `decisao_regra`/`decisao_vencedor` on a resolved one) per conflict
    considered, so a caller can audit exactly what changed and why.
    """
    resolvidos: list[dict] = []
    ainda_pendentes: list[dict] = []
    ignorado_composto: list[dict] = []
    now = _now()
    pendentes = conflitos_pendentes(client, org_id, cliente_id)
    if campos is not None:
        pendentes = [r for r in pendentes if r.get("campo") in campos]

    # Live evidence, loaded once per cliente: their row + their own and
    # their linked spouse's non-deleted documents (`evidencia_viva`).
    ids = sorted({str(r["cliente_id"]) for r in pendentes})
    clientes_rows = {
        str(c["id"]): c
        for lote in table_reads.batched(ids)
        for c in (
            (
                _t(client, CLIENTES_TABLE)
                .select("*")
                .eq("org_id", str(org_id))
                .in_("id", lote)
                .execute()
            ).data or []
        )
    }
    donos = sorted(
        set(ids) | {str(c["conjuge_cliente_id"]) for c in clientes_rows.values() if c.get("conjuge_cliente_id")}
    )
    docs_por_cliente: dict[str, list[dict]] = {}
    cache_docs: dict[str, Optional[dict]] = {}
    for d in _documentos_vivos(client, org_id, donos):
        docs_por_cliente.setdefault(str(d["cliente_id"]), []).append(d)

    def documentos_de(cid: str) -> list[dict]:
        c = clientes_rows.get(cid) or {}
        conjuge = str(c["conjuge_cliente_id"]) if c.get("conjuge_cliente_id") else None
        return docs_por_cliente.get(cid, []) + (docs_por_cliente.get(conjuge, []) if conjuge else [])

    for row in pendentes:
        campo_chave = row["campo"]
        campo = CAMPO_POR_CHAVE.get(campo_chave)
        # F1 — a conflict against an EMPTY field is settled by filling it,
        # before any divergence rule runs (there is no divergence).
        if _preencher_conflito_vazio(
            client, org_id, row, clientes_rows.get(str(row["cliente_id"])), now,
        ):
            resolvidos.append(
                {**row, "decisao_regra": REGRA_VAZIO_PREENCHIDO, "decisao_vencedor": "proposto"}
            )
            continue
        if campo_chave == CAMPO_ENDERECO:
            decisao_end, partes = _decidir_endereco_pendente(client, org_id, row)
            if decisao_end is None:
                ignorado_composto.append(row)
                continue
            campo_conflitos.registrar_decisao_automatica(
                client, campo_conflitos.CLIENTE, org_id, row["cliente_id"], CAMPO_ENDERECO,
                valor_anterior=row.get("valor_anterior"),
                origem_anterior=row.get("origem_anterior"),
                valor_proposto=row.get("valor_proposto"),
                origem_proposto=row.get("origem_proposto"),
                decisao=decisao_end,
                conflito_existente_id=row["id"],
            )
            if decisao_end.requer_humano:
                ainda_pendentes.append(row)
                continue
            if decisao_end.vencedor == "proposto" and partes is not None:
                updates: dict[str, Any] = {
                    f"endereco_{p}": (None if _vazio(partes.get(p)) else partes.get(p))
                    for p in ENDERECO_PARTES
                }
                updates.update({
                    COLUNA_BAIRRO_ORIGEM: _bairro_origem_da_leitura(partes),
                    "endereco_origem": row.get("origem_proposto"),
                    "endereco_documento_id": (
                        row.get("fonte_id") if row.get("fonte_tabela") == DOCUMENTOS_TABLE else None
                    ),
                    "endereco_em": now,
                    "endereco_confirmado_por": None,
                    "endereco_confirmado_em": None,
                    "updated_at": now,
                })
                _t(client, CLIENTES_TABLE).update(updates).eq(
                    "id", str(row["cliente_id"])
                ).execute()
            resolvidos.append(
                {**row, "decisao_regra": decisao_end.regra, "decisao_vencedor": decisao_end.vencedor}
            )
            continue
        if campo_chave == CAMPO_CONJUGE or campo is None:
            ignorado_composto.append(row)
            continue
        cid = str(row["cliente_id"])
        evidencia = None
        cliente_row = clientes_rows.get(cid)
        if cliente_row is not None:
            # The on-file side's document is the one `clientes` still points
            # at — only while the record still holds that same value.
            doc_atual = (
                cliente_row.get(campo.documento_id)
                if _mesmo_valor(campo.item_key, cliente_row.get(campo.item_key), row.get("valor_anterior"))
                else None
            )
            doc_proposto = row.get("fonte_id") if row.get("fonte_tabela") == DOCUMENTOS_TABLE else None
            evidencia = evidencia_viva(
                campo, cliente_row, documentos_de(cid),
                atual_sustentado=_sustentado(
                    client, org_id, campo, cliente_row, doc_atual, row.get("valor_anterior"),
                    cache_docs, origem=row.get("origem_anterior"),
                    vouched=bool(cliente_row.get(campo.confirmado_em)),
                ),
                proposto_sustentado=_sustentado(
                    client, org_id, campo, cliente_row, doc_proposto, row.get("valor_proposto"),
                    cache_docs, origem=row.get("origem_proposto"),
                ),
            )
        decisao = campo_conflitos.resolver_e_registrar(
            client, campo_conflitos.CLIENTE, org_id, row["cliente_id"], campo_chave,
            valor_anterior=row.get("valor_anterior"),
            origem_anterior=row.get("origem_anterior"),
            valor_proposto=row.get("valor_proposto"),
            origem_proposto=row.get("origem_proposto"),
            confianca_proposta=row.get("confianca_proposta"),
            fonte_tabela=row.get("fonte_tabela"),
            fonte_id=row.get("fonte_id"),
            mesmo_valor=_mesmo_valor,
            conflito_existente_id=row["id"],
            evidencia=evidencia,
            uf=idf.uf_do_orgao((cliente_row or {}).get("rg_orgao_expedidor")),
            cpf_proprio=(cliente_row or {}).get("cpf"),
            atual_humano=(
                row.get("origem_anterior") == "manual" or _valor_humano(cliente_row, campo)
            ),
        )
        if decisao.requer_humano:
            ainda_pendentes.append(row)
            continue
        if decisao.vencedor == "proposto":
            _t(client, CLIENTES_TABLE).update(
                {
                    campo.item_key: row.get("valor_proposto"),
                    campo.origem: row.get("origem_proposto"),
                    campo.documento_id: (
                        row.get("fonte_id")
                        if row.get("fonte_tabela") == DOCUMENTOS_TABLE
                        else None
                    ),
                    campo.em: now,
                    campo.confirmado_por: None,
                    campo.confirmado_em: None,
                    "updated_at": now,
                }
            ).eq("id", str(row["cliente_id"])).execute()
            if campo.item_key == "cpf" and row.get("valor_proposto"):
                cpf_conhecido(client, org_id, row["cliente_id"], row["valor_proposto"])
        resolvidos.append(
            {**row, "decisao_regra": decisao.regra, "decisao_vencedor": decisao.vencedor}
        )
    return {
        "resolvidos": resolvidos,
        "ainda_pendentes": ainda_pendentes,
        "ignorado_composto": ignorado_composto,
    }


def revalidar_negociacao(client: Any, org_id: UUID, cliente_id: UUID) -> None:
    """R1 — re-resolution on new evidence (owner directive, 2026-09-30):
    "the system must work by itself and humans are to intervene only when
    the system actually can't resolve." Called at the end of `extrair_
    identidade`'s own `_processar`, once per document read — a name/CPF/
    address that just landed on ONE party's card may be exactly the
    evidence a PENDING conflict sitting on ANOTHER party (a bill-holder
    check with nothing to compare against yet, at the time it opened) was
    waiting on; nobody visits every card after every upload to notice.

    Reuses the SAME two mechanisms every other automatic resolution already
    goes through — no second resolver:
    - `propagar_endereco_domicilio` (R3) for `cliente_id` + their linked
      spouse, so a spouse's now-qualifying own address fills (or a
      no-longer-qualifying one retracts) the household half.
    - `backfill_resolver_conflitos_pendentes` (already the resolve-on-read
      backfill, 2026-09-29) for `cliente_id` and every OTHER party sharing
      an `atendimento` with them — not only `cliente_id`'s own queue.

    Best-effort per person: one person's DB error does not stop the sweep
    for the rest — logged, never silent, and never raised past this
    function (this runs inside `extrair_identidade`'s own try, so a failure
    here must not turn a successful extraction into a recorded `erro`)."""
    pessoas: set[str] = {str(cliente_id)}
    pessoas.update(_pessoas_dos_cards(client, org_id, cliente_id))
    conjuge_id = _conjuge_vinculado(client, org_id, cliente_id)
    if conjuge_id:
        pessoas.add(str(conjuge_id))
    for pid in sorted(pessoas):
        try:
            propagar_endereco_domicilio(client, org_id, UUID(pid))
        except Exception:  # noqa: BLE001 — one person's propagation must not block the sweep
            logger.exception(
                "revalidar_negociacao: propagar_endereco_domicilio falhou para %s", pid,
            )
    for pid in sorted(pessoas):
        try:
            inferir_solteiro_por_certidao_nascimento(client, org_id, UUID(pid))
        except Exception:  # noqa: BLE001 — one person's inference must not block the sweep
            logger.exception(
                "revalidar_negociacao: inferir_solteiro_por_certidao_nascimento falhou para %s", pid,
            )
    for pid in sorted(pessoas):
        try:
            backfill_resolver_conflitos_pendentes(client, org_id, cliente_id=UUID(pid))
        except Exception:  # noqa: BLE001 — one person's backlog must not block the sweep
            logger.exception(
                "revalidar_negociacao: backfill_resolver_conflitos_pendentes falhou para %s", pid,
            )


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
            updates[COLUNA_BAIRRO_ORIGEM] = _bairro_origem_da_leitura(proposto)
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
        if item_key == "cpf" and conflito.get("valor_proposto"):
            cpf_conhecido(client, org_id, conflito["cliente_id"], conflito["valor_proposto"])

    return {**conflito, **patch}


def _conjuge_esperado_do_card(
    client: Any, org_id: UUID, cliente_id: UUID
) -> tuple[Optional[str], Optional[str]]:
    """The couple's OTHER person for this card, as `(nome, cpf)` — the
    SAME selector contract `_titular_do_card` already documents for its own
    hint: only ever used to CONFIRM a name the certidão itself prints
    (`documents.conjuges`'s anchored fallback, P2 corpus, 2026-09-29), never
    a source. A hint that matches nothing on the document changes nothing.

    Linked spouse first (`conjuge_cliente_id`); else the ONE other party on
    this cliente's SAME side (`lado`) of the SAME atendimento
    (`_pessoas_do_mesmo_lado`) — the identical fallback
    `_conjuge_por_lado_unico` already uses AFTER extraction to resolve who
    to LINK the second spouse's facts to; this runs BEFORE extraction so
    the extractor gets both names up front. A placeholder role label
    ("Comprador 2") or an empty name is never a usable hint. Best-effort: a
    lookup failure returns `(None, None)`, never raises — same posture
    `_titular_do_card` already takes.
    """
    try:
        proprio = (
            _t(client, CLIENTES_TABLE)
            .select("conjuge_cliente_id")
            .eq("org_id", str(org_id))
            .eq("id", str(cliente_id))
            .limit(1)
            .execute()
        ).data or []
        candidato_id = proprio[0].get("conjuge_cliente_id") if proprio else None
        if not candidato_id:
            candidatos = _pessoas_do_mesmo_lado(client, org_id, cliente_id)
            candidato_id = candidatos[0] if len(candidatos) == 1 else None
        if not candidato_id:
            return (None, None)
        rows = (
            _t(client, CLIENTES_TABLE)
            .select("nome, nome_oficial, cpf")
            .eq("org_id", str(org_id))
            .eq("id", str(candidato_id))
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            return (None, None)
        row = rows[0]
        nome = row.get("nome_oficial") or row.get("nome")
        if _nome_vazio_ou_placeholder(nome):
            nome = None
        return (nome, row.get("cpf"))
    except Exception as exc:  # noqa: BLE001 - detached job; degrade, log
        logger.warning(
            "extracao: conjuge esperado lookup failed for %s: %s", cliente_id, exc
        )
        return (None, None)


def _titular_do_card(
    client: Any, org_id: UUID, cliente_id: UUID
) -> Optional[TitularEsperado]:
    """The card's own person, as the extractor's titular hint — plus, when
    known, the couple's OTHER half (`conjuge_nome`/`conjuge_cpf`).

    `nome_oficial` (a document-read spelling) before `nome` (whatever the
    operator typed), plus the CPF when one is on file. A lookup failure
    returns None — the extraction then runs exactly as it did before the
    hint existed — but it is logged, never swallowed.

    `conjuge_nome`/`conjuge_cpf` (P2 corpus, 2026-09-29) feed `documents.
    conjuges.find_conjuges`'s anchored fallback — confirming a name the
    PLATFORM already knows directly against the certidão's text when a
    vision transcription's own run-to-run variance breaks every label the
    other readers depend on (measured: the SAME certidão flips between
    resolving both spouses and resolving none, run to run). Attached even
    when this card's own `nome`/`cpf` are both empty — a fresh cliente
    record with a document-less card can still anchor on its ALREADY-known
    spouse.
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
    conjuge_nome, conjuge_cpf = _conjuge_esperado_do_card(client, org_id, cliente_id)
    if not nome and not cpf and not conjuge_nome and not conjuge_cpf:
        return None
    return TitularEsperado(
        nome=nome, cpf=cpf, conjuge_nome=conjuge_nome, conjuge_cpf=conjuge_cpf
    )


def _nacionalidade_atual_confirmada(client: Any, org_id: UUID, cliente_id: UUID) -> bool:
    """Has a human already vouched for this party's `nacionalidade`?

    Consulted ONLY on the narrow path where `derivar_nacionalidade_civil`
    might otherwise fire (this document printed no nationality of its own,
    but carries an issuer worth deriving from) — never on the common path
    where nothing is inferred anyway. A lookup failure degrades to `False`
    (the derivation then goes through `aplicar_campos_ao_cliente`'s own
    fill-empty-or-conflict rule instead of silently skipping), same
    best-effort posture as `_titular_do_card`.
    """
    try:
        rows = (
            _t(client, CLIENTES_TABLE)
            .select("nacionalidade_confirmado_em")
            .eq("org_id", str(org_id))
            .eq("id", str(cliente_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 - detached job; degrade, log
        logger.warning(
            "extracao: nacionalidade lookup failed for %s: %s", cliente_id, exc
        )
        return False
    if not rows:
        return False
    return not _vazio(rows[0].get("nacionalidade_confirmado_em"))


async def extrair_identidade(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    extractor: Optional[Any] = None,
    notification_service: Optional[Any] = None,
    cep_lookup: Optional[CepLookupAdapter] = None,
) -> dict:
    """Read one identity document and record the outcome. Never raises.

    `notification_service` announces every conflict this read opens
    (`notificar_conflitos`); the routes and the sweep pass
    `deps.get_conflict_notification_service()`.

    `cep_lookup` (F3, 2026-09-30) is forwarded, unchanged, to every
    `aplicar_endereco_ao_cliente` call this function makes — `None` (the
    default) reproduces the exact pre-F3 behaviour; the routes and the
    sweep pass `deps.get_cep_lookup_adapter()`.

    Runs detached from the request that triggered it, so an exception here
    would surface nowhere and the document would sit in `processando` forever.
    Every failure path therefore ends in a recorded `extracao_status`, which is
    what makes `varrer_extracoes_pendentes` able to recover the one case this
    cannot record: the process dying mid-read.

    🔴 lesson G6 (2026-09-28): this used to stamp the TERMINAL `extracao_
    status` (`ok`/`sem_dados`) BEFORE calling `aplicar_campos_ao_cliente` —
    with no `try` around it at all. A transient DB error there left the
    document `ok` with the client record never filled and nothing to retry
    (the sweep never revisits an `ok` row). Now built on the shared
    `app.services.extracao_job` runner (see that module's own docstring):
    the preamble (fetch/validate/`processando`/blob/access-log) is shared
    via `extracao_job.preparar` — Crednet's OWN already G6-compliant
    pipeline reuses it too, below — and the generic identity path's apply
    steps run inside the runner's own try, terminal status last.
    """
    config = extracao_job.ExtractionJobConfig(
        table=DOCUMENTOS_TABLE,
        bucket=BUCKET,
        deve_extrair=deve_extrair,
        log_acesso=lambda org, doc_id: _log_acesso_extracao(client, org, doc_id),
    )
    doc, blob, erro = await extracao_job.preparar(client, storage, org_id, documento_id, config)
    if erro is not None:
        return erro

    tipo = str(doc["tipo_documento"])

    # P0c contract §C3: Serasa Crednet's reading is not an `IdentityFields`
    # at all (own dataclass, own D1 fields, own empresas/certidão side
    # effects) — `crednet_service.aplicar_leitura` owns every step past the
    # blob read + access log above (already G6-compliant on its own, so it
    # does not go through `executar_com_blob`'s `ler`/`processar` split);
    # the sweep and re-run inherit this branch for free, since both call
    # THIS function.
    if tipo == "serasa_crednet":
        from app.modules.card_hub import crednet_service
        from app.modules.empresas.deps import get_cnpj_registry_lookup

        crednet_extractor = extractor
        if crednet_extractor is None:
            from app.modules.card_hub.deps import _build_identity_extractor

            crednet_extractor = _build_identity_extractor(str(org_id), "serasa_crednet")
        return await crednet_service.aplicar_leitura(
            client, org_id, cliente_id, documento_id, doc, blob.data,
            extractor=crednet_extractor,
            cnpj_registry_lookup=get_cnpj_registry_lookup(),
            notification_service=notification_service,
        )

    # A ficha cadastral bancária names SEVERAL people, each applied to
    # their OWN card by CPF — not an `IdentityFields` single-titular read
    # either. Same dispatch shape as `serasa_crednet` above; see
    # `ficha_cadastral_service.aplicar_leitura`'s own module docstring for
    # the full sequence.
    if tipo == "ficha_cadastral":
        from app.modules.card_hub import ficha_cadastral_service

        ficha_extractor = extractor
        if ficha_extractor is None:
            from app.modules.card_hub.deps import _build_identity_extractor

            ficha_extractor = _build_identity_extractor(str(org_id), "ficha_cadastral")
        return await ficha_cadastral_service.aplicar_leitura(
            client, org_id, cliente_id, documento_id, doc, blob.data,
            extractor=ficha_extractor,
            notification_service=notification_service,
            cep_lookup=cep_lookup,
        )

    # A pacto antenupcial names the COUPLE — both spouses matched by CPF,
    # only `regime_bens` written onto each; see `pacto_antenupcial_service`.
    if tipo == "pacto_antenupcial":
        from app.modules.card_hub import pacto_antenupcial_service

        pacto_extractor = extractor
        if pacto_extractor is None:
            from app.modules.card_hub.deps import _build_identity_extractor

            pacto_extractor = _build_identity_extractor(str(org_id), "pacto_antenupcial")
        return await pacto_antenupcial_service.aplicar_leitura(
            client, org_id, cliente_id, documento_id, doc, blob.data,
            extractor=pacto_extractor,
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
        max_pages=paginas_maximas(tipo),
        provider=resolve_vision_provider(str(org_id)),
    )

    async def _ler(blob_bytes: bytes, doc_row: dict) -> IdentityFields:
        # The document was uploaded onto ONE person's card — tell the
        # extractor who, so a two-titular certidão de casamento selects
        # that spouse's name and CPF instead of declining both. A selector
        # only: the extractor returns a hinted value solely when the
        # document printed it.
        #
        # `tipo_documento=tipo` (P2 corpus, round 2, 2026-09-28) — this
        # module is the one place that KNOWS the declared type; the
        # extractor's own `classify_kind` filename guess is only ever
        # RG/CPF/CNH/UNKNOWN and can never tell a certidão or comprovante
        # apart from "unknown". Without this, `avaliar_legibilidade` had no
        # way to scope its signals and a genuine certidão's extenso dates /
        # cartório-footer CEP, or a comprovante's legitimate CNPJ/ICMS
        # lines, over-fired as `comprometida`.
        return await extractor.extract(
            blob_bytes,
            mimetype=doc_row.get("mime_type"),
            filename=doc_row.get("nome_original"),
            titular=_titular_do_card(client, org_id, cliente_id),
            tipo_documento=tipo,
        )

    async def _processar(fields: IdentityFields, doc_row: dict) -> dict:
        if fields.aviso:
            # Not a failure — the result is persisted below. Recorded so
            # the withheld fields are explainable from the logs.
            logger.info(
                "extracao %s: aviso %s — %s",
                documento_id, fields.aviso, fields.aviso_mensagem,
            )

        so_endereco = tipo in TIPOS_ENDERECO
        # An address document contributes its address and nothing else —
        # see `TIPOS_ENDERECO`. Its name/CPF are the bill holder's.
        lidos = _lidos_vazios() if so_endereco else _valores_lidos(fields)
        endereco = fields.endereco if so_endereco else None
        data_emissao = (
            fields.data_emissao.isoformat() if fields.data_emissao and not so_endereco else None
        )
        conjuges = [] if so_endereco else list(fields.conjuges or ())
        # Resolved here (not only where the OTHER spouse is filled, below)
        # so the titular's OWN `nome_oficial` apply can also consult their
        # own `nome_anterior` — owner decision, 2026-09-28, see
        # `_nome_anterior_confirma_adocao`. `titular_idx` is `.titular` on
        # `ConjugeLido`, set by the extractor's own titular-hint selection.
        titular_idx = next((i for i, c in enumerate(conjuges) if c.titular), None)
        nome_anterior_titular = (
            conjuges[titular_idx].nome_anterior if titular_idx is not None else None
        )
        # 🔴 R5 (owner directive, 2026-09-30) — AN UNATTRIBUTED FLAT
        # PER-PERSON FIELD ON A TWO-PERSON DOCUMENT MUST NEVER REACH THE
        # TITULAR, FOR ANY OF THEM — real, measured (live prod test,
        # 2026-09-30): a certidão de casamento names two co-equal holders,
        # and every `CAMPOS_POR_PESSOA` reading off `_valores_lidos` above
        # (`nome_oficial`, `cpf`, `rg`, `rg_orgao_expedidor`,
        # `data_nascimento`, `genero`, `profissao`) is a WHOLE-DOCUMENT
        # reading with no notion of which of the two it belongs to — the
        # extractor's own titular-hint attribution (`documents.real.
        # _conjuge_do_titular`, keyed on this card's already-known
        # name/CPF) is what marks the correct entry `.titular=True` and,
        # when it succeeds, ALREADY promotes that spouse's own fields into
        # `fields.*` at `alta` confidence — see that module's own comment.
        # `titular_idx is None` means that attribution did NOT resolve
        # (this card has no name/CPF on file yet that matches either
        # spouse, or matches ambiguously): every flat field here is exactly
        # the kind of positional/leftover reading that wrote an ex-spouse's
        # RG onto the wrong card in production (a divorce certidão, live
        # test, 2026-09-30) — this used to withhold `cpf` alone
        # (950c2c255); the SAME leftover risk applies to every other
        # per-person field this document type can carry, so all of
        # `CAMPOS_POR_PESSOA` are withheld together. Withheld the same way
        # an unresolved `titulares_multiplos` name already is — never
        # guessed. The per-spouse entry attributed to a person by
        # `_entrada_conjuge_da_pessoa` (cliente_id/CPF match) remains the
        # only way a certidão's per-person fact reaches a cliente going
        # forward.
        if (
            conjuges
            and tipo in divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS
            and titular_idx is None
        ):
            for campo_pessoa in divergencia_resolucao.CAMPOS_POR_PESSOA:
                if campo_pessoa in lidos:
                    lidos[campo_pessoa] = (None, "nenhuma", None, False)
        achou_algo = (
            data_emissao is not None
            or endereco is not None
            or bool(conjuges)
            or any(v is not None for v, _, _, _ in lidos.values())
        )

        # F4 — a certidão de nascimento with no averbação read and no
        # marriage evidence anywhere proves "solteiro" (see
        # `ESTADO_CIVIL_SOLTEIRO`). Same D1 path as every other field below.
        if (
            tipo == "certidao_nascimento"
            and not fields.leitura_comprometida
            and lidos["estado_civil"][0] is None
            and not _casamento_evidenciado(client, org_id, cliente_id)
        ):
            lidos["estado_civil"] = _solteiro_inferido()

        # Resolves the brief this module opened alongside `nacionalidade`
        # itself (migration 146): 12/26 of the P2 corpus's real identity
        # documents (older CNH models, some RGs/CINs) never print the field
        # at all. When THIS document read no nationality but did read an
        # issuer worth deriving from (`nacionalidade_civil.py`'s closed
        # state-civil whitelist — never RNE/RNM/CRNM/PF/MRE), and the party
        # has no OTHER nationality on file yet, offer a `baixa`,
        # explicitly-labelled `"inferida: ..."` suggestion through the SAME
        # `extracao_nacionalidade*` columns and the SAME `aplicar_campos_ao_
        # cliente` fill-empty-or-conflict rule every other CAMPO uses — a
        # human still confirms it, exactly like any other `baixa` read.
        # Never on a compromised transcription: an `rg_orgao` this module's
        # own legibilidade check does not trust is not evidence worth
        # inferring from either.
        if (
            not so_endereco
            and not fields.leitura_comprometida
            and lidos["nacionalidade"][0] is None
            and fields.rg_orgao
        ):
            ja_confirmada = _nacionalidade_atual_confirmada(client, org_id, cliente_id)
            derivado = derivar_nacionalidade_civil(
                fields.rg_orgao,
                nacionalidade_lida=None,
                nacionalidade_atual_confirmada=ja_confirmada,
            )
            if derivado[0] is not None:
                lidos["nacionalidade"] = (*derivado, True)

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

        # Recorded whether or not it lands on the client — the `_confianca`
        # and `_rotulo` columns let a human audit the reasoning without
        # re-opening the document (another logged access). NO terminal
        # status here (lesson G6) — that lands only after every apply step
        # below succeeds.
        marcacoes: dict[str, Any] = {"extracao_fonte": fields.source.value}
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
        # Migration 172: `fields.aviso`/`aviso_mensagem` survive on the
        # document row — unlike every OTHER `extracao_*` triple above,
        # `cliente_documentos` had no aviso column at all before this, so
        # `titulares_multiplos`/`data_nascimento_implausivel`/
        # `leitura_comprometida` used to reach only the logs.
        marcacoes["extracao_aviso"] = fields.aviso
        marcacoes["extracao_aviso_mensagem"] = fields.aviso_mensagem
        # Recorded BEFORE anything touches the client record, so a failure while
        # applying still leaves the reading on the document rather than a row
        # stuck in `processando` — the runner's own try/except (lesson G6) is
        # what turns a failure PAST this point into `erro`, never a false `ok`.
        _marcar(client, documento_id, **marcacoes)

        # 🔴 LEITURA COMPROMETIDA — NOTHING AUTO-APPLIED (owner directive,
        # 2026-09-28). `fields.leitura_comprometida` means
        # `legibilidade.avaliar_legibilidade` found the TRANSCRIPTION itself
        # suspect (a label/value type mismatch, a high ilegível-marker
        # share, or the holder name matching a FILIAÇÃO/parent name — see
        # that module's own docstring for the measured CNH-screenshot
        # failure). Every value is still recorded on THIS document row
        # (`marcacoes` above, unconditionally) — including through
        # `sugestoes_pendentes`, which reads those columns directly and does
        # not consult `pode_persistir` — so a human still sees and can
        # confirm a field that happens to be correct despite the warning.
        # What changes is `aplicar_campos_ao_cliente`'s `pode` gate: every
        # field is withheld from writing onto `clientes` at ANY confidence,
        # whether that write would have been a first-time machine-pending
        # fill (the exact shape the CNH-screenshot bug exploited: a wrong
        # nome + CPF written onto an otherwise-empty record) or a conflict
        # against an existing value — a compromised reading disagreeing with
        # the record is not evidence worth an admin's attention either.
        lidos_para_aplicar = (
            {chave: (valor, confianca, rotulo, False) for chave, (valor, confianca, rotulo, _pode) in lidos.items()}
            if fields.leitura_comprometida
            else lidos
        )

        conflitos: list[dict] = []
        avisos_outra_pessoa: list[str] = []
        avisos_cpf_invalido: list[str] = []
        avisos_tipo_trocado: list[str] = []
        aplicados, abertos = aplicar_campos_ao_cliente(
            client,
            org_id,
            cliente_id,
            tipo,
            lidos_para_aplicar,
            documento_id=documento_id,
            fonte_tabela=DOCUMENTOS_TABLE,
            fonte_id=documento_id,
            nomes_anteriores={"nome_oficial": nome_anterior_titular},
            avisos_outra_pessoa=avisos_outra_pessoa,
            avisos_cpf_invalido=avisos_cpf_invalido,
            avisos_tipo_trocado=avisos_tipo_trocado,
        )
        conflitos += abertos

        def _sinalizar(codigo: str, mensagem: Optional[str] = None) -> None:
            """Flag what the APPLY step found on the document row. The
            seed's own transcription aviso (`fields.aviso`) is KEPT and the
            apply code appended `+`-joined (the same multi-code shape the
            seed already writes) — it used to be dropped whenever the seed
            had flagged anything (P5 audit B5: an RG read with
            `campos_nucleo_ausentes` whose RG was then refused for an
            apply-side reason showed no reason at all for the empty field)."""
            aviso = f"{fields.aviso}+{codigo}" if fields.aviso else codigo
            partes_msg = [m for m in (fields.aviso_mensagem, mensagem) if m]
            extra: dict[str, Any] = {"extracao_aviso": aviso}
            if partes_msg:
                extra["extracao_aviso_mensagem"] = " | ".join(partes_msg)
            _marcar(client, documento_id, **extra)

        # One apply code per document, highest-precedence first — R4 (the
        # document belongs to another party) explains everything below it.
        if avisos_outra_pessoa:
            # R4 — this document read at least one field that belongs to
            # ANOTHER party of the negotiation (rejected above, never
            # applied). Flagged so the UI can suggest moving it.
            _sinalizar("documento_de_outra_parte")
            logger.info(
                "extracao %s: campo(s) %s pertencem a outra parte da "
                "negociação — rejeitados automaticamente, documento "
                "sinalizado",
                documento_id, avisos_outra_pessoa,
            )
        elif avisos_cpf_invalido:
            _sinalizar("cpf_invalido")
        elif avisos_tipo_trocado:
            # A reading that is a valid identifier of ANOTHER type (a CPF in
            # the RG field) was not written — flagged so the human sees WHY
            # the field stayed empty and can type the right one
            # (`canonical-identifiers`).
            _sinalizar(
                "identificador_de_outro_tipo",
                "O número lido em "
                + ", ".join(sorted(avisos_tipo_trocado)).upper()
                + " é válido como outro tipo de documento (ex.: um CPF no campo do RG) — "
                "não foi gravado; confira o documento.",
            )

        # A CPF read now may be the key a matrícula qualificação was waiting
        # for (it was segmented before this person's documents existed) —
        # re-link it so profissão/nacionalidade/RG from the registry act reach
        # this cliente. Local import: qualificacao_service imports this module.
        cpf_lido = re.sub(r"\D", "", str(fields.cpf or ""))
        if (
            len(cpf_lido) == 11
            and cpf_valido(cpf_lido)
            and not fields.leitura_comprometida
        ):
            try:
                from app.modules.matriculas.qualificacao_service import revincular_pendentes

                revincular_pendentes(client, org_id, cpf_normalizado=cpf_lido)
            except Exception:  # noqa: BLE001 — never fail an identity read on a re-link
                logger.exception("revincular matrícula qualificações falhou para %s", cliente_id)

        if endereco is not None:
            # Same leitura_comprometida gate as every field above — the
            # address group is written/conflicted as one unit
            # (`aplicar_endereco_ao_cliente`'s own contract), so it is
            # skipped as one unit here too. The reading still rides on the
            # document row (`marcacoes` above) for a human to review.
            if fields.leitura_comprometida:
                aplicados[CAMPO_ENDERECO] = False
            else:
                titular = endereco.titular
                alvo_id: UUID = cliente_id
                if titular:
                    achado = _pessoa_do_card_por_nome(client, org_id, cliente_id, titular)
                    if achado is not None:
                        alvo_id = UUID(achado)
                    # Titular present but matches nobody on this card: alvo_id
                    # stays `cliente_id`, and `aplicar_endereco_ao_cliente`'s
                    # own titular_documento guard below opens the review
                    # conflict (comprovante em nome de terceiro) — never a
                    # silent fill.
                else:
                    # P2, measured: 9/9 real comprovantes read with NO titular
                    # at all (see `address.py`'s own P2 comment) — applying
                    # unattended to whoever the file was uploaded onto is the
                    # pre-existing behaviour, kept unchanged here, but flagged
                    # so a human auditing the log knows attribution was never
                    # verified against a name.
                    logger.info(
                        "extracao %s: comprovante sem titular legivel — "
                        "endereco aplicado a %s sem verificacao de titularidade",
                        documento_id, cliente_id,
                    )
                # The guard only needs re-checking when we could NOT resolve
                # who the bill names to someone already ON this card —
                # `alvo_id == cliente_id` and a matched titular are mutually
                # exclusive with the "nobody matched" branch above.
                titular_guard = titular if alvo_id == cliente_id else None
                avisos_endereco: list[str] = []
                aplicado_end, conflito_end = aplicar_endereco_ao_cliente(
                    client, org_id, alvo_id, tipo, partes_endereco,
                    titular_documento=titular_guard,
                    confianca=endereco.confianca,
                    documento_id=documento_id,
                    cep_lookup=cep_lookup,
                    avisos=avisos_endereco,
                )
                if AVISO_TITULAR_NAO_CONFERE in avisos_endereco:
                    _sinalizar(
                        AVISO_TITULAR_NAO_CONFERE,
                        "O titular impresso no comprovante não confere com nenhuma "
                        "pessoa do card — o endereço preencheu o campo vazio e "
                        "aguarda confirmação.",
                    )
                aplicados[CAMPO_ENDERECO] = aplicado_end
                if conflito_end is not None:
                    conflitos.append(conflito_end)

                # Measured (P2): every bill naming a deal party had its
                # address applied to that party's SPOUSE too. Best-effort,
                # same group contract as the primary write — a disagreement
                # opens its OWN conflict on the spouse's record rather than
                # silently skipping or silently overwriting.
                if aplicado_end:
                    conjuge_id = _conjuge_vinculado(client, org_id, alvo_id)
                    if conjuge_id is not None:
                        _, conflito_conjuge_end = aplicar_endereco_ao_cliente(
                            client, org_id, UUID(conjuge_id), tipo, partes_endereco,
                            titular_documento=None,
                            confianca=endereco.confianca,
                            documento_id=documento_id,
                            cep_lookup=cep_lookup,
                        )
                        if conflito_conjuge_end is not None:
                            conflitos.append(conflito_conjuge_end)

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
            # `titular_idx` was already resolved above, before the titular's
            # own apply, so both applies consult the SAME resolution.
            if titular_idx is not None and len(conjuges) == 2:
                outro = conjuges[1 - titular_idx]
                outro_id = _cliente_do_outro_conjuge(client, org_id, cliente_id, outro)
                # `outro_id` is still resolved above (used below to attribute
                # `registro_conjuges`, a document-row RECORD, not a write to
                # any cliente) even when comprometida — only the WRITE to the
                # other spouse's record and the reciprocal link are gated.
                if outro_id is not None and not fields.leitura_comprometida:
                    _, abertos_outro = aplicar_campos_ao_cliente(
                        client, org_id, UUID(outro_id), tipo,
                        _lidos_do_conjuge(outro, fields),
                        documento_id=documento_id,
                        fonte_tabela=DOCUMENTOS_TABLE,
                        fonte_id=documento_id,
                        nomes_anteriores={"nome_oficial": outro.nome_anterior},
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
                        # The maiden/prior name, when the certidão states
                        # this spouse ADOPTED `nome` — never lost even when
                        # `nome_oficial` moves straight to the adopted name
                        # (owner decision, 2026-09-28; see
                        # `_nome_anterior_confirma_adocao`).
                        "nome_anterior": c.nome_anterior,
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

        # 🔴 R1 — RE-RESOLUTION ON NEW EVIDENCE (owner directive, 2026-09-30:
        # "the system must work by itself and humans are to intervene only
        # when the system actually can't resolve"). Whatever just landed on
        # THIS cliente may be exactly the evidence a PENDING conflict on
        # this cliente OR another party of the same negociação was waiting
        # on — see `revalidar_negociacao`'s own docstring. Run before
        # notifying so a conflict this very call is about to resolve is
        # never announced first; a conflict belonging to another cliente_id
        # was never going to be in THIS extraction's own `conflitos` list
        # regardless of when it resolves.
        revalidar_negociacao(client, org_id, cliente_id)

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
            "aplicado_ao_cliente": aplicados,
            "conflitos_abertos": [c["campo"] for c in conflitos],
            "conjuges": registro_conjuges,
            "leitura_comprometida": fields.leitura_comprometida,
        }

    identity_config = replace(
        config,
        ler=_ler,
        leitura_erro=lambda fields: fields.error,
        leitura_erro_mensagem=lambda fields: fields.error_message,
        leitura_fonte=lambda fields: fields.source.value,
        processar=_processar,
    )
    resultado = await extracao_job.executar_com_blob(
        client, identity_config, documento_id, doc, blob, tipo,
    )
    return {**resultado, "tentativas": doc.get("extracao_tentativas")}


def _casamento_evidenciado(client: Any, org_id: UUID, cliente_id: UUID) -> bool:
    """Is there ANY evidence this person married — a spouse link, or a live
    (not deleted, not discarded) certidão de casamento on their own card or
    their linked spouse's? `True` blocks F4's solteiro inference."""
    conjuge = _conjuge_vinculado(client, org_id, cliente_id)
    if conjuge:
        return True
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("tipo_documento", "certidao_casamento")
        .is_("deleted_at", "null")
        .is_("extracao_descartada_em", "null")
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def _solteiro_inferido() -> tuple[Any, str, Optional[str], bool]:
    """The `lidos` entry F4 contributes — `baixa`, labelled as an inference
    so a human reading the document row knows it was not printed."""
    return (ESTADO_CIVIL_SOLTEIRO, "baixa", ROTULO_SOLTEIRO_INFERIDO, True)


def inferir_solteiro_por_certidao_nascimento(
    client: Any, org_id: UUID, cliente_id: UUID,
) -> list[dict]:
    """F4 for certidões ALREADY read before the inference existed (and
    re-checked whenever the deal moves — `revalidar_negociacao`): the
    newest live, successfully read certidão de nascimento with no
    estado-civil reading and no compromised transcription proposes
    `solteiro` through the SAME `aplicar_campos_ao_cliente` D1 write (fill
    empty machine-pending, conflict when different, never overwrite).
    Fills an EMPTY field only: a DIFFERENT value already on file is the
    live read's job to conflict (`_processar`, once, when the certidão is
    read/re-read) — re-proposing it from here on every revalidation would
    re-run the resolver and stack audit rows. Idempotent — a no-op once the
    field holds any value. Returns the newly opened conflicts (none today,
    kept for the caller's notify contract)."""
    atual = (
        _t(client, CLIENTES_TABLE)
        .select("id,estado_civil,estado_civil_origem")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not atual or not _vazio(atual[0].get("estado_civil")):
        return []
    if _limpo_por_humano(atual[0].get("estado_civil"), atual[0].get("estado_civil_origem")):
        return []
    if _casamento_evidenciado(client, org_id, cliente_id):
        return []
    docs = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id,extracao_status,extracao_estado_civil,extracao_aviso,created_at")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("tipo_documento", "certidao_nascimento")
        .is_("deleted_at", "null")
        .is_("extracao_descartada_em", "null")
        .execute()
    ).data or []
    candidatos = [
        d for d in docs
        if d.get("extracao_status") == "ok"
        and (_vazio(d.get("extracao_estado_civil")) or d.get("extracao_estado_civil") == ESTADO_CIVIL_SOLTEIRO)
        and AVISO_LEITURA_COMPROMETIDA not in str(d.get("extracao_aviso") or "")
    ]
    if not candidatos:
        return []
    doc = max(candidatos, key=lambda d: str(d.get("created_at") or ""))
    if _vazio(doc.get("extracao_estado_civil")):
        valor, confianca, rotulo, _ = _solteiro_inferido()
        _marcar(
            client, UUID(str(doc["id"])),
            extracao_estado_civil=valor,
            extracao_estado_civil_confianca=confianca,
            extracao_estado_civil_rotulo=rotulo,
        )
    lidos = _lidos_vazios()
    lidos["estado_civil"] = _solteiro_inferido()
    _, conflitos = aplicar_campos_ao_cliente(
        client, org_id, cliente_id, "certidao_nascimento", lidos,
        documento_id=UUID(str(doc["id"])),
        fonte_tabela=DOCUMENTOS_TABLE,
        fonte_id=UUID(str(doc["id"])),
    )
    return conflitos


def backfill_solteiro_por_certidao_nascimento(client: Any, org_id: UUID) -> int:
    """Org-wide F4 one-shot (the "Resolver conflitos" button): every cliente
    with a successfully read certidão de nascimento gets
    `inferir_solteiro_por_certidao_nascimento`. Best-effort per cliente,
    logged. Returns how many clientes now hold an inferred `solteiro`."""
    ids = sorted({
        str(r["cliente_id"])
        for r in table_reads.paged_rows(
            client, DOCUMENTOS_TABLE, org_id,
            eq_filters={"tipo_documento": "certidao_nascimento", "extracao_status": "ok"},
            refine=lambda q: q.is_("deleted_at", "null"),
            select="id,cliente_id",
        )
        if r.get("cliente_id")
    })
    preenchidos = 0
    for cid in ids:
        try:
            inferir_solteiro_por_certidao_nascimento(client, org_id, UUID(cid))
        except Exception:  # noqa: BLE001 — one cliente must not stop the org-wide pass
            logger.exception("backfill_solteiro: cliente %s falhou", cid)
            continue
        row = (
            _t(client, CLIENTES_TABLE)
            .select("estado_civil,estado_civil_origem")
            .eq("org_id", str(org_id))
            .eq("id", cid)
            .limit(1)
            .execute()
        ).data or []
        if row and row[0].get("estado_civil") == ESTADO_CIVIL_SOLTEIRO and row[0].get(
            "estado_civil_origem"
        ) == "certidao_nascimento":
            preenchidos += 1
    return preenchidos


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
        if row.get("cliente_id"):  # a PJ party (migration 179) has none
            pessoas.add(str(row["cliente_id"]))
    pessoas.discard(str(cliente_id))
    return sorted(pessoas)


def _pessoas_do_mesmo_lado(client: Any, org_id: UUID, cliente_id: UUID) -> list[str]:
    """Every OTHER person on the SAME side (`lado`, migration 098) of the SAME
    atendimento as this cliente — narrower than `_pessoas_dos_cards`, which
    pools every atendimento's parties regardless of side.

    Used only by `_conjuge_por_lado_unico`'s fallback below: a comprador is
    never a vendedor's spouse, and a party on a DIFFERENT deal this cliente
    also happens to sit on is not a candidate either. `cliente_id` itself may
    be the atendimento's own titular (buyer side, implicit `lado='comprador'`
    — migration 073's header) or an `atendimento_partes` row (both sides,
    migration 098) — either way, every atendimento/lado pair it sits in is
    resolved first, then every OTHER person on that exact pair.
    """
    pares: set[tuple[str, str]] = set()
    for row in (
        _t(client, "atendimentos")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []:
        pares.add((str(row["id"]), "comprador"))
    for row in (
        _t(client, "atendimento_partes")
        .select("atendimento_id,lado")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []:
        pares.add((str(row["atendimento_id"]), row.get("lado") or "comprador"))
    if not pares:
        return []
    atendimento_ids = sorted({p[0] for p in pares})

    pessoas: set[str] = set()
    compradores = {aid for aid, lado in pares if lado == "comprador"}
    if compradores:
        for row in (
            _t(client, "atendimentos")
            .select("id,cliente_id")
            .eq("org_id", str(org_id))
            .in_("id", list(compradores))
            .execute()
        ).data or []:
            if row.get("cliente_id"):
                pessoas.add(str(row["cliente_id"]))
    for row in (
        _t(client, "atendimento_partes")
        .select("atendimento_id,lado,cliente_id")
        .eq("org_id", str(org_id))
        .in_("atendimento_id", atendimento_ids)
        .execute()
    ).data or []:
        chave = (str(row["atendimento_id"]), row.get("lado") or "comprador")
        if chave in pares and row.get("cliente_id"):  # PJ party: none (179)
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


# A generic role label typed as a stand-in before a document named the real
# person — "Comprador 2", "Vendedor 2", "Cônjuge" — never a real person's
# name, so it can never itself be evidence the certidão's spouse is someone
# else. Anchored (not a substring search): a REAL name that happens to
# contain one of these words ("Compradora Silva") must still count as a
# disagreeing name, not a placeholder.
_PLACEHOLDER_LADO_PAPEL = re.compile(
    r"^(COMPRADOR(A)?|VENDEDOR(A)?|CONJUGE|PARTE|CLIENTE)\s*\d*$"
)


def _nome_vazio_ou_placeholder(nome: Optional[str]) -> bool:
    """No usable name to disagree with — empty, or a generic role label."""
    chave = chave_nome(nome)
    return not chave or bool(_PLACEHOLDER_LADO_PAPEL.match(chave))


def _conjuge_por_lado_unico(
    client: Any, org_id: UUID, cliente_id: UUID, conjuge: Any
) -> Optional[str]:
    """Fallback spouse resolution (owner directive, 2026-09-29) for when the
    certidão names two spouses and the OTHER one matches nobody by name/CPF —
    because the party row has no usable name yet (a placeholder like
    "Comprador 2") or no identity document of their own has ever been read.

    Only fires when `_cliente_do_outro_conjuge` found zero named matches —
    a real name/CPF disagreement, or more than one match, is never
    second-guessed by this. Resolves to the only OTHER party on the SAME
    side (`lado`) of the SAME atendimento as `cliente_id`, and only when
    nothing about that candidate actively disagrees with the certidão:

    - CPF: the candidate has none on file, or it already equals the
      certidão's (a CPF that DISAGREES is a real conflict — no auto-pair).
    - Name: empty, a placeholder label, or already compatible with the
      certidão's name (`nomes_compativeis` — kept for symmetry, though a
      real match there would already have resolved above).

    Two or more same-side candidates, or a lone one that disagrees, is left
    for a human — the same posture `_pessoa_do_card_por_nome` already takes
    on ambiguity. Never creates or links a cliente on its own; the caller
    still runs `vincular_conjuges`, which records the pairing durably
    (`conjuge_cliente_id`, both ways) so later documents (a comprovante)
    propagate to this spouse too.
    """
    candidatos = _pessoas_do_mesmo_lado(client, org_id, cliente_id)
    if len(candidatos) != 1:
        return None
    rows = (
        _t(client, CLIENTES_TABLE)
        .select("id,nome,nome_completo,nome_oficial,cpf")
        .eq("org_id", str(org_id))
        .eq("id", candidatos[0])
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    if conjuge.cpf and row.get("cpf"):
        if only_digits(str(row["cpf"])) != only_digits(conjuge.cpf):
            return None  # a real CPF disagreement — human review, no guess
    nome_atual = next(
        (n for n in (row.get("nome_oficial"), row.get("nome_completo"), row.get("nome")) if n),
        None,
    )
    if (
        nome_atual is not None
        and not _nome_vazio_ou_placeholder(nome_atual)
        and not nomes_compativeis(conjuge.nome, nome_atual)
    ):
        return None  # a real, different name on file — not our guess to make
    return str(row["id"])


def _cliente_do_outro_conjuge(
    client: Any, org_id: UUID, cliente_id: UUID, conjuge: Any
) -> Optional[str]:
    """The existing cliente the NON-titular spouse is, or None.

    1. The cliente already linked as this one's `conjuge_cliente_id` — only
       if it IS the person the certidão names (an old certidão from a
       previous marriage must not fill the current spouse's record).
    2. Else exactly one person on this cliente's cards who matches by
       name/CPF.
    3. Else `_conjuge_por_lado_unico`'s same-side fallback — see its own
       docstring for why a name/CPF match is not the only signal a
       placeholder party or a document-less spouse can offer.
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
    achados: list[dict] = []
    if candidatos:
        rows = (
            _t(client, CLIENTES_TABLE)
            .select(colunas)
            .eq("org_id", str(org_id))
            .in_("id", candidatos)
            .execute()
        ).data or []
        achados = [r for r in rows if _e_a_pessoa(r, conjuge)]
    if len(achados) == 1:
        return str(achados[0]["id"])
    if achados:
        return None  # more than one named match — genuinely ambiguous
    return _conjuge_por_lado_unico(client, org_id, cliente_id, conjuge)


# ─── The sweep: what happens when the process dies mid-read (migration 072) ──


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


_COLUNAS_VARREDURA = (
    "id,org_id,cliente_id,tipo_documento,extracao_status,"
    "extracao_tentativas,extracao_em,created_at"
)


def _candidatos_varredura(client: Any, limite: int) -> list[dict]:
    """The four kinds of row the sweep owns, oldest-first, de-duplicated.

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
    4. 🔴 NEVER READ: `extracao_status IS NULL` for a type that IS in
       `TIPOS_EXTRAIVEIS` today, aged on `created_at` like (2). A document
       uploaded while its type had NO reader (every `cin` before
       `fontes.FONTES["cin"]` existed — prod live test 2026-09-30) was never
       stamped `pendente`, so classes 1–3 could never see it: it stayed
       unread forever, and the person owning the card had no signal that it
       would never tick. Once the reader ships, this class picks the backlog
       up by itself — no human re-read per document. Filtered on
       `TIPOS_EXTRAIVEIS` IN THE QUERY: a NULL status is also the CORRECT
       resting state of an intentionally-unread type (`outro`, `contrato`…),
       and those must never be selected — not even to be refused by
       `extracao_job.preparar`'s `deve_extrair` guard, which would stamp them
       `erro` and turn "not read by design" into a false failure.

    Four explicit queries rather than one `.or_()` expression: each bound is
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
    nunca_lidos = (
        base()
        .is_("extracao_status", "null")
        .in_("tipo_documento", sorted(TIPOS_EXTRAIVEIS))
        .lte("created_at", cutoff)
        .order("created_at")
        .limit(limite)
        .execute()
    ).data or []
    vistos: set[str] = set()
    linhas: list[dict] = []
    for row in [*parados, *nunca_iniciados, *com_erro, *nunca_lidos]:
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
    cep_lookup: Optional[CepLookupAdapter] = None,
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
                cep_lookup=cep_lookup,
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


def _doc_leitura_comprometida(doc: dict) -> bool:
    """Was the document THIS suggestion comes from flagged `leitura_
    comprometida` (migration 172)? Membership on the "+"-joined
    `extracao_aviso` string, mirroring `IdentityFields.leitura_
    comprometida` — a different code that merely CONTAINS this string must
    never match. Surfaced on every suggestion this document offers so the
    pessoa checklist warns a human BEFORE they click confirm (owner
    decision, 2026-09-28) — `aplicar_campos_ao_cliente` already refused to
    write it unattended; this is the same warning at the human's own
    decision point.
    """
    aviso = doc.get("extracao_aviso")
    return bool(aviso) and AVISO_LEITURA_COMPROMETIDA in str(aviso).split("+")


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
                "leitura_comprometida": _doc_leitura_comprometida(doc),
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
                "leitura_comprometida": _doc_leitura_comprometida(doc),
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
            COLUNA_BAIRRO_ORIGEM: None,
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
    if campo.item_key == "cpf" and valor:
        cpf_conhecido(client, org_id, cliente_id, valor, excluir_documento_id=documento_id)

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
    "ORIGEM_CONJUGE_DOMICILIO",
    "TIPOS_ENDERECO",
    "aplicar_campos_ao_cliente",
    "aplicar_endereco_ao_cliente",
    "notificar_conflitos",
    "propagar_endereco_domicilio",
    "resolver_conflito",
    "revalidar_negociacao",
    "cpf_conhecido",
    "vincular_conjuges",
    "CAMPOS_PACTO_ESCRITURA",
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
