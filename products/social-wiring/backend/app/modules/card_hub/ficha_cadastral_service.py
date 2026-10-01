"""Ficha cadastral bancária — one upload, several people, each applied to
their OWN card (live prod test, 2026-09-30: the biggest remaining address
gap — see `noctusai_lib.integrations.documents.ficha_cadastral`'s own
module docstring for the measured numbers).

`identidade_extracao_service.extrair_identidade` routes `tipo_documento ==
'ficha_cadastral'` here, right after the blob read + access log it already
did — same "differently-shaped reader" dispatch `crednet_service.
aplicar_leitura` uses (the seed's own reading is `FichaCadastralLida`, not
`IdentityFields`, so the generic single-titular apply path never fits).

`aplicar_leitura`, in order:

    (a) record the WHOLE reading on the document (`extracao_ficha_
        cadastral`, migration 176) — before touching any cliente at all;
    (b) match EVERY person the form named to a party of the SAME
        atendimento(s) this upload's own cliente sits on, primarily by CPF
        (exact digits) against a party who already has one on file —
        `identidade_extracao_service._pessoas_dos_cards` is the existing
        "every party of every atendimento this cliente is on" query (R4's
        own collaborator), reused rather than re-derived. FALLBACK: the
        card this document was UPLOADED onto, matched by name — a ficha is
        routinely the FIRST document a fresh card sees, so CPF alone could
        never fill the very CPF field it is meant to fill (see
        `_resolver_destino`'s own docstring);
    (c) per MATCHED person, apply their identity fields (`nome_oficial`,
        `cpf`, `rg`(+`rg_orgao_expedidor`), `data_nascimento`,
        `estado_civil`, `regime_bens`, `nacionalidade`, `profissao`)
        through the SAME D1 machinery (`identidade_extracao_service.
        aplicar_campos_ao_cliente`) every other identity source uses —
        this is what makes identity fields CORROBORATION-ONLY without any
        new code: `app.services.divergencia_resolucao.PRECISAO` carries no
        `"ficha_cadastral"` cell (deliberately unmeasured — see that
        module's own docstring), so a disagreement with an already-set
        value can never win on tier alone, only fill an empty field or
        feed the corroboration count;
    (d) their address, via `_aplicar_endereco_ficha` — same generic D1
        group-apply `aplicar_endereco_ao_cliente` gives every address
        source, with one addition: a household-propagated address
        (`ORIGEM_CONJUGE_DOMICILIO`, R3 — the weakest tier, by design) is
        cleared FIRST, so the ficha's own address always outranks it
        without needing a new tier concept. An address already on file
        from the person's OWN document (a real `comprovante_endereco`, or
        an earlier `ficha_cadastral`) is never silently overwritten — a
        genuine disagreement opens the SAME conflict a comprovante
        disagreement would, unattended-safe exactly the way "no measured
        precision yet" is supposed to behave;
    (e) unmatched persons are IGNORED — never create a `clientes` row, per
        owner scope (a misfiled/unrelated form is not evidence about
        anyone this atendimento does not already know).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.name import nomes_compativeis
from noctusai_lib.integrations.documents.ficha_cadastral import (
    FichaCadastralLida,
    PessoaFichaCadastral,
)

from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.services import _now, _t
from app.services import extracao_job

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"

#: `NOC-REMEDIATE[extracao-job-runner-adopt]`-shaped — the named `erro`
#: code recorded when `_processar` (below) raises. Mirrors `crednet_
#: service.ERRO_SIDE_EFFECTS_FAILED`.
ERRO_SIDE_EFFECTS_FAILED = "side_effects_failed"

#: The identity-adjacent `CampoExtraido`s a ficha cadastral reading may
#: write onto `clientes`, PER MATCHED PARTY — every field `PessoaFicha
#: Cadastral` carries except `endereco` (its own GROUP apply, see
#: `_aplicar_endereco_ficha`), `telefone`/`email` (no `clientes` column —
#: contact fields are not part of this product's D1 provenance quintets
#: today) and `papel` (form-section metadata, not a fact about the person).
CAMPOS_FICHA: tuple = tuple(
    identidade_svc.CAMPO_POR_CHAVE[chave]
    for chave in (
        "nome_oficial", "cpf", "rg", "rg_orgao_expedidor", "data_nascimento",
        "estado_civil", "regime_bens", "nacionalidade", "profissao",
    )
)


def _lidos_pessoa(pessoa: PessoaFichaCadastral) -> dict[str, tuple]:
    """`CAMPOS_FICHA`'s `item_key -> (valor, confianca, rotulo,
    pode_persistir)` — the same shape `identidade_extracao_service.
    _valores_lidos` builds for an identity document, built here from
    `PessoaFichaCadastral` instead. `pode_persistir` is "a value was read,
    at any confidence" (owner decision D1, migration 153) — the confidence
    itself is what keeps it machine-pending until a human (or corroboration)
    vouches for it, not a gate here."""
    rotulo = "FICHA CADASTRAL"

    def item(valor: Any, confianca: Any) -> tuple:
        return (valor, getattr(confianca, "value", confianca), rotulo, bool(valor))

    return {
        "nome_oficial": item(pessoa.nome, pessoa.nome_confianca),
        "cpf": item(pessoa.cpf, pessoa.cpf_confianca),
        "rg": item(pessoa.rg, pessoa.rg_confianca),
        "rg_orgao_expedidor": item(pessoa.rg_orgao, pessoa.rg_orgao_confianca),
        "data_nascimento": item(
            pessoa.data_nascimento.isoformat() if pessoa.data_nascimento else None,
            pessoa.data_nascimento_confianca,
        ),
        "estado_civil": item(pessoa.estado_civil, pessoa.estado_civil_confianca),
        "regime_bens": item(pessoa.regime_bens, pessoa.regime_bens_confianca),
        "nacionalidade": item(pessoa.nacionalidade, pessoa.nacionalidade_confianca),
        "profissao": item(pessoa.profissao, pessoa.profissao_confianca),
    }


def _linhas_do_atendimento(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """Every party (INCLUDING `cliente_id` itself) of every atendimento
    this upload's own cliente sits on. `identidade_extracao_service.
    _pessoas_dos_cards` already answers "every OTHER person on any card
    this cliente is on" (R4's own collaborator) — this adds the titular
    back in, since a ficha uploaded onto a proponente's OWN card routinely
    also names their cônjuge, and the proponente's own block must still be
    a candidate for their own card."""
    outras = identidade_svc._pessoas_dos_cards(client, org_id, cliente_id)
    todos = list(dict.fromkeys([str(cliente_id), *outras]))
    return (
        _t(client, identidade_svc.CLIENTES_TABLE)
        .select("id,cpf,nome,nome_completo,nome_oficial")
        .eq("org_id", str(org_id))
        .in_("id", todos)
        .execute()
    ).data or []


def _mapa_cpf(linhas: list[dict]) -> dict[str, str]:
    """digits-only CPF -> `cliente_id`, for every party with one ALREADY on
    file — the brief's own primary attribution rule."""
    mapa: dict[str, str] = {}
    for row in linhas:
        digits = only_digits(row.get("cpf") or "")
        if digits and cpf_valido(digits):
            mapa[digits] = str(row["id"])
    return mapa


def _resolver_destino(
    pessoa: PessoaFichaCadastral,
    *,
    cliente_id: UUID,
    mapa_cpf: dict[str, str],
    titular_row: Optional[dict],
    ja_atribuidos: set[str],
) -> Optional[str]:
    """Which atendimento party this person's own block belongs to.

    Primary rule (the brief's own): an EXACT CPF match against a party who
    already has one on file — covers every OTHER named person (a spouse/
    co-seller whose own identity document already ran).

    Fallback: the CARD'S OWN titular, by NAME — needed because a ficha is
    routinely the FIRST document a fresh card sees (CPF is empty on both
    sides, so CPF matching alone could never fill it — the exact gap this
    feature exists to close). Never claims a card TWICE in the same
    reading (`ja_atribuidos`), so a two-person form's second page cannot
    also land on the card its first page already matched by name.
    """
    digits = only_digits(pessoa.cpf or "")
    if digits and digits in mapa_cpf:
        return mapa_cpf[digits]
    if titular_row is None or str(cliente_id) in ja_atribuidos:
        return None
    nomes = [
        titular_row.get("nome_oficial"), titular_row.get("nome_completo"),
        titular_row.get("nome"),
    ]
    if pessoa.nome and any(n and nomes_compativeis(pessoa.nome, n) for n in nomes):
        return str(cliente_id)
    return None


def _aplicar_endereco_ficha(
    client: Any, org_id: UUID, cliente_id: str, endereco: Any, *,
    documento_id: UUID, cep_lookup: Optional[Any] = None,
) -> tuple[bool, Optional[dict]]:
    """`aplicar_endereco_ao_cliente`'s own D1 group-apply, with ONE
    addition: a household-propagated address (R3, `ORIGEM_CONJUGE_
    DOMICILIO` — the weakest tier, by design, `propagar_endereco_
    domicilio`'s own docstring) is cleared FIRST. Without this, the
    generic apply would see a non-empty group and run its HOLDER-based
    conflict machinery (built for two independent comprovantes
    disagreeing) against a fact that was never this person's own to begin
    with — the ficha's own address must simply win, not "win a resolver
    round". An address already on file from a REAL document (this
    person's own comprovante, or an earlier ficha_cadastral) is untouched
    here and falls straight into that same generic machinery — a genuine
    disagreement opens a conflict, exactly as "no measured precision yet"
    (unmeasured `PRECISAO` for address entirely — see `divergencia_
    resolucao.py`) is supposed to behave: never a silent overwrite either
    way.
    """
    atual = (
        _t(client, identidade_svc.CLIENTES_TABLE)
        .select("id,endereco_origem")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if atual and atual[0].get("endereco_origem") == identidade_svc.ORIGEM_CONJUGE_DOMICILIO:
        agora = _now()
        limpar: dict[str, Any] = {f"endereco_{p}": None for p in identidade_svc.ENDERECO_PARTES}
        limpar.update(
            {
                "endereco_origem": None, "endereco_documento_id": None, "endereco_em": None,
                "endereco_confirmado_por": None, "endereco_confirmado_em": None,
                "updated_at": agora,
            }
        )
        _t(client, identidade_svc.CLIENTES_TABLE).update(limpar).eq(
            "id", str(cliente_id)
        ).execute()
    return identidade_svc.aplicar_endereco_ao_cliente(
        client, org_id, cliente_id, "ficha_cadastral", endereco.partes(),
        confianca=endereco.confianca, documento_id=documento_id,
        cep_lookup=cep_lookup,
    )


def _serializar_pessoa(pessoa: PessoaFichaCadastral, cliente_id: Optional[str]) -> dict:
    return {
        "papel": pessoa.papel,
        "nome": pessoa.nome,
        "cpf": pessoa.cpf,
        "rg": pessoa.rg,
        "rg_orgao": pessoa.rg_orgao,
        "data_nascimento": (
            pessoa.data_nascimento.isoformat() if pessoa.data_nascimento else None
        ),
        "estado_civil": pessoa.estado_civil,
        "regime_bens": pessoa.regime_bens,
        "nacionalidade": pessoa.nacionalidade,
        "profissao": pessoa.profissao,
        "endereco": pessoa.endereco.partes() if pessoa.endereco else None,
        "telefone": pessoa.telefone,
        "email": pessoa.email,
        # Not personal data of its own — a foreign key into THIS org's own
        # `clientes`, or `None` when unmatched (never created).
        "cliente_id_aplicado": cliente_id,
    }


def _serializar(lida: FichaCadastralLida, destinos: list[Optional[str]]) -> dict:
    return {
        "pessoas": [
            _serializar_pessoa(p, destino) for p, destino in zip(lida.pessoas, destinos)
        ],
        "aviso": lida.aviso,
        "source": getattr(lida.source, "value", lida.source),
    }


async def aplicar_leitura(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    doc: dict,
    blob_data: bytes,
    *,
    extractor: Any,
    notification_service: Optional[Any] = None,
    cep_lookup: Optional[Any] = None,
) -> dict:
    """The whole sequence, built on the shared `app.services.extracao_job`
    runner (`NOC-REMEDIATE[extracao-job-runner-adopt]`-shaped — see
    `crednet_service.aplicar_leitura`'s own docstring for why this shape:
    the reading is persisted, every D1 apply runs INSIDE `_processar`'s
    own try, the TERMINAL `extracao_status` is written LAST). `doc` is the
    already-fetched `cliente_documentos` row, `blob_data` the already-
    fetched bytes — `identidade_extracao_service.extrair_identidade` does
    both before branching here. `cep_lookup` (F3) is forwarded, unchanged,
    to `_aplicar_endereco_ficha`'s own `aplicar_endereco_ao_cliente` call.
    Never raises.
    """

    async def _ler(blob_bytes: bytes, doc_row: dict) -> FichaCadastralLida:
        return await extractor.extract(
            blob_bytes, mimetype=doc_row.get("mime_type"), filename=doc_row.get("nome_original"),
        )

    async def _processar(lida: FichaCadastralLida, doc_row: dict) -> dict:
        linhas = _linhas_do_atendimento(client, org_id, cliente_id)
        mapa_cpf = _mapa_cpf(linhas)
        titular_row = next((r for r in linhas if str(r["id"]) == str(cliente_id)), None)
        conflitos: list[dict] = []
        destinos: list[Optional[str]] = []
        aplicados_por_pessoa: list[dict] = []
        ja_atribuidos: set[str] = set()

        for pessoa in lida.pessoas:
            destino = _resolver_destino(
                pessoa, cliente_id=cliente_id, mapa_cpf=mapa_cpf,
                titular_row=titular_row, ja_atribuidos=ja_atribuidos,
            )
            destinos.append(destino)
            if destino is None:
                # Unmatched — never create a cliente, per owner scope.
                aplicados_por_pessoa.append({"cliente_id": None, "aplicados": {}})
                continue
            ja_atribuidos.add(destino)

            aplicados, novos_conflitos = identidade_svc.aplicar_campos_ao_cliente(
                client, org_id, destino, "ficha_cadastral", _lidos_pessoa(pessoa),
                campos=CAMPOS_FICHA, documento_id=documento_id,
                fonte_tabela=DOCUMENTOS_TABLE, fonte_id=documento_id,
            )
            conflitos.extend(novos_conflitos)

            endereco_aplicado = False
            if pessoa.endereco is not None and pessoa.endereco.presente:
                endereco_aplicado, conflito_endereco = _aplicar_endereco_ficha(
                    client, org_id, destino, pessoa.endereco, documento_id=documento_id,
                    cep_lookup=cep_lookup,
                )
                if conflito_endereco is not None:
                    conflitos.append(conflito_endereco)

            aplicados_por_pessoa.append(
                {"cliente_id": destino, "aplicados": aplicados, "endereco": endereco_aplicado}
            )

        extracao_job.marcar(
            client, DOCUMENTOS_TABLE, documento_id,
            extracao_ficha_cadastral=_serializar(lida, destinos),
        )

        if conflitos:
            await identidade_svc.notificar_conflitos(client, org_id, conflitos, notification_service)

        achou_algo = bool(lida.pessoas)
        return {
            "status": extracao_job.OK if achou_algo else extracao_job.SEM_DADOS,
            "pessoas_encontradas": len(lida.pessoas),
            "pessoas_correspondidas": sum(1 for d in destinos if d is not None),
            "aplicados": aplicados_por_pessoa,
            "conflitos": len(conflitos),
        }

    config = extracao_job.ExtractionJobConfig(
        table=DOCUMENTOS_TABLE,
        bucket=BUCKET,
        deve_extrair=identidade_svc.deve_extrair,
        ler=_ler,
        leitura_erro=lambda lida: lida.error,
        leitura_erro_mensagem=lambda lida: lida.error_message,
        leitura_fonte=lambda lida: getattr(lida.source, "value", lida.source),
        processar=_processar,
        erro_aplicar_codigo=ERRO_SIDE_EFFECTS_FAILED,
    )
    # `preparar` already ran in `extrair_identidade` (this branch reuses its
    # `doc`/`blob_data`, never re-reading storage) — mirrors `crednet_
    # service.aplicar_leitura`'s own wrapping.
    blob = SimpleNamespace(data=blob_data)
    return await extracao_job.executar_com_blob(
        client, config, documento_id, doc, blob, "ficha_cadastral",
    )


def reenfileirar_fichas_pelo_cpf(
    client: Any, org_id: UUID, cliente_id: UUID, cpf: Any,
    *, excluir_documento_id: Optional[UUID] = None,
) -> list[str]:
    """A party just got `cpf` on file: re-queue every already-read
    `ficha_cadastral` of the same atendimento(s) that named a person with
    that CPF and could NOT attribute them at read time.

    A bank form is routinely a card's FIRST document, read before the other
    parties' identity documents — their CPF was unknown, so `_resolver_
    destino` stored them unmatched (`cliente_id_aplicado` null) and they were
    never applied. The stored reading drops per-field confidences, so it is
    never re-applied from the stored JSON: the document goes back to
    `pendente` and the existing sweep (`varrer_extracoes_pendentes`) re-reads
    it, now resolving that person by CPF.

    Loop guard: only a ficha that is terminal-`ok`, whose stored reading has
    an UNMATCHED person with exactly this CPF, and that still has attempts
    left (`extracao_tentativas < MAX_TENTATIVAS`, the D3 accounting every read
    increments) is re-queued; one read that now matches stops satisfying the
    first condition. Returns the re-queued document ids.
    """
    digits = only_digits(str(cpf or ""))
    if len(digits) != 11:
        return []
    ids = [str(r["id"]) for r in _linhas_do_atendimento(client, org_id, cliente_id)]
    docs = (
        _t(client, DOCUMENTOS_TABLE)
        .select("id,extracao_status,extracao_tentativas,extracao_ficha_cadastral")
        .eq("org_id", str(org_id))
        .eq("tipo_documento", "ficha_cadastral")
        .in_("cliente_id", ids)
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    enfileirados: list[str] = []
    for doc in docs:
        if excluir_documento_id and str(doc["id"]) == str(excluir_documento_id):
            continue
        if doc.get("extracao_status") != extracao_job.OK:
            continue
        if int(doc.get("extracao_tentativas") or 0) >= identidade_svc.MAX_TENTATIVAS:
            continue
        pessoas = (doc.get("extracao_ficha_cadastral") or {}).get("pessoas") or []
        if not any(
            not p.get("cliente_id_aplicado") and only_digits(p.get("cpf") or "") == digits
            for p in pessoas
        ):
            continue
        extracao_job.marcar(
            client, DOCUMENTOS_TABLE, UUID(str(doc["id"])),
            extracao_status="pendente", extracao_erro=None, extracao_em=None,
        )
        enfileirados.append(str(doc["id"]))
    return enfileirados


__all__ = ["CAMPOS_FICHA", "aplicar_leitura", "reenfileirar_fichas_pelo_cpf"]
