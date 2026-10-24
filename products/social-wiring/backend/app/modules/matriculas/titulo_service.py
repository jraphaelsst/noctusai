"""What the contract asks of a matrícula's acts (migration 115): confirmed act
details, the título aquisitivo phrase, the ônus creditor, and the previous
owners of the last registered sale.

WHERE THE ANSWERS COME FROM
---------------------------
Never from free text and never from a guess — from the TYPED DETAILS of the
acts the operator already chose in 109:

- título phrase    <- `imovel_dados.titulo_aquisitivo_ato_id`'s instrumento,
  rendered by the seed's `frase_titulo_aquisitivo`;
- ônus creditor    <- the `credor` of each act in `imovel_dados.onus_fonte_atos`;
- previous owners  <- the transmitentes of the CONFIRMED título aquisitivo
  act, when its nature is one that transfers ownership for consideration
  (`NATUREZAS_ULTIMA_TRANSFERENCIA`); otherwise the LAST such act anywhere in
  the imóvel's título extraction (or its newest concluded extraction), by
  `ordem`. [migration 152] When neither exists, an operator's manual
  override (a typed date, or an explicit "não consta transferência
  registrada" statement) answers it instead.

🔴 UPDATED FOR MIGRATION 154's D1 WRITE POLICY (2026-09-23, migration 166).
`obter_titulo`/`obter_onus_credor` below still recompute a live SUGGESTION on
every read (`sugestao`, from the acts) and never store it directly — but
`imovel_dados.titulo_aquisitivo_texto` / `onus_credor` are no longer
confirmed-only, as 115 originally shipped them. Two paths write the stored
value now, exactly like every other contract-feeding `imovel_dados` field:
`preenchimento_service.preencher_sincrono` (154) machine-fills it from the
confirmed título act's instrumento — MACHINE-PENDING (`_origem` set,
`_confirmado_em` NULL, D2) until a human validates it — and
`confirmar_titulo`/`confirmar_onus_credor` below is the human's own edit,
always stamped `origem='manual'` + the confirmation together
(`_patch_confirmacao`). `imovel_dados_titulo_aquisitivo_texto_pareado` /
`imovel_dados_onus_credor_pareado` (migration 166, replacing 115's
confirmed-only CHECKs) enforce that the value and `_origem` always travel
together and a confirmation timestamp never appears without a value — NOT
that the value is always confirmed. The CONTRACT still only accepts the
CONFIRMED wording (`contrato_gerador.validacao_extracao`'s
`CAMPOS_IMOVEL` — a machine-pending phrase alone does not satisfy the
readiness gate), so "the confirmation is what the contract uses" remains
true; what changed is that a stored, unconfirmed suggestion is now a
legal, expected intermediate state instead of a database contradiction.

🔴 OFFICE RULE — CERTIDÕES OF THE PREVIOUS OWNERS
------------------------------------------------
Required when the last registered TRANSFER OF OWNERSHIP is LESS than
`ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS` years old (exactly five years is not
"less than five"). When a transfer IS found but its registration date is
unknown, `exige_certidoes` is TRUE and `data_desconhecida` says why: an
unreadable date must lead to asking for the certidões, never to silently
waiving them.

[Owner directive, 2026-10-22] ANY transmissão of propriedade counts as "the
last transfer" — `NATUREZAS_ULTIMA_TRANSFERENCIA` IS the seed's
`NATUREZAS_TRANSFERENCIA` (compra e venda, doação, permuta, partilha/herança,
dação, arrematação, adjudicação, integralização). The previous, narrower
rule (2026-09-22: consideration-only) read a 1985 compra e venda as the last
transfer of an imóvel whose true last one was a 1988 DOAÇÃO to the current
owners; the antigos proprietários of a doação are the doadores. An operator
who wants a donation NOT to count uses the manual override ("não consta
transferência registrada"), not a re-classification.

When the current matrícula carries no transmission act of its own (it opens
with "REGISTRO ANTERIOR: R-04/M-21.748 …"), the derivation continues on the
imóvel's CLOSED predecessor matrículas (`cadeia_dominial`) instead of
answering "nenhum ato".

🔴 LGPD: every route here that returns details without the act text logs
`detalhes_view` (`ato_detalhes_service.log_leitura_detalhes`) before answering.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import (
    NATUREZAS_TRANSFERENCIA,
    Parte,
    normalizar_nome_parte,
    parse_detalhes_json,
    partes_de_bloco,
    qualificar_por_referencia,
    transmitentes_por_referencia,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from noctusai_lib.primitives.accents import fold_accents_ascii

from app.modules.imovel_hub import dados_service, vinculo_legal
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import cadeia_dominial
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads
from app.services.documento_store import now_iso, today

ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS = 5

NATUREZA_COMPRA_E_VENDA = "compra_e_venda"

#: [Q9] Natures that count as "the imóvel changed hands" for the previous-
#: owner certidões rule: every transmissão of propriedade the seed types
#: (owner 2026-10-22 — see this module's docstring).
NATUREZAS_ULTIMA_TRANSFERENCIA: frozenset[str] = NATUREZAS_TRANSFERENCIA

#: Why a GET has no suggestion — a machine-readable reason for the FE.
MOTIVO_SEM_TITULO = "sem_titulo_confirmado"
#: A HUMAN-confirmed título pointer quotes a matrícula whose documento was
#: removed: surfaced as a pendência (never silently re-pointed over the
#: human's choice).
MOTIVO_MATRICULA_REMOVIDA = "matricula_removida"
MENSAGEM_MATRICULA_REMOVIDA = (
    "A matrícula do título aquisitivo confirmado foi removida — escolha outra."
)
MOTIVO_SEM_ONUS = "sem_onus_confirmado"
MOTIVO_SEM_DETALHES = "sem_detalhes"
MOTIVO_SEM_INSTRUMENTO = "sem_instrumento"
MOTIVO_SEM_CREDOR = "sem_credor"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _codigo(codigo: str) -> str:
    canonico = (codigo or "").strip().upper()
    if not canonico:
        raise ValidationError_("O código do imóvel é obrigatório.", field="codigo")
    return canonico


def _ato_ref(ato: dict) -> Optional[str]:
    if ato.get("numero") is None:
        return None
    return f"{ato['kind']}-{ato['numero']}"


def _atos_e_detalhes(
    client: Any, org_id: UUID, extracao: dict
) -> tuple[dict[str, dict], dict[str, dict]]:
    atos = estrutura_svc.atos_da_extracao(client, org_id, extracao)
    return (
        {str(r["id"]): r for r in atos},
        detalhes_svc.detalhes_por_ato(client, org_id, extracao, atos),
    )


def _confirmacao(linha: dict, coluna: str, chave: str) -> Optional[dict]:
    valor = linha.get(coluna)
    if valor is None:
        return None
    resolved = table_reads.resolve_actors({linha.get(f"{coluna}_confirmado_por")} - {None})
    return {
        chave: valor,
        "confirmado_por": table_reads.actor(resolved, linha.get(f"{coluna}_confirmado_por")),
        "confirmado_em": linha.get(f"{coluna}_confirmado_em"),
        # Migration 154 — `matricula` when the value was machine-filled from
        # the acts and not yet confirmed (the D2 gate lists it as pending).
        "origem": linha.get(f"{coluna}_origem"),
    }


_DATA_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_REF_RE = re.compile(r"\b(r|av)\s*[-.]?\s*(\d+)\b", re.I)
_TIPOS_INSTRUMENTO = (
    "particular", "publica", "escritura", "formal de partilha", "arrematacao",
    "adjudicacao", "carta de", "contrato", "sentenca", "mandado", "permuta",
)
_LIVRO_RE = re.compile(
    r"\b(?:livro|l[º°])\.?\s*(?:n[o.º°]{0,2}\s*)?([0-9][\w./-]*?)(?=[\s,;]|\.(?:\s|$)|$)", re.I
)
_FOLHAS_RE = re.compile(
    r"\b(?:fls?|folhas?)\b\.?\s*(?:n[o.º°]{0,2}\s*)?(\d+(?:\s*(?:/|-|a|e)\s*\d+)?)", re.I
)
_TABELIONATO_RE = re.compile(
    r"(?:\d+\s*[º°oª]?\s*)?tabeli(?:ão|ao|onato)(?:\s+de\s+notas)?", re.I
)
_NOME_PROPRIO = r"[A-ZÀ-Ý][\wÀ-ÿ'-]*"
_CIDADE_RE = re.compile(
    r"(?:tabeli(?:ão|ao|onato)(?:\s+de\s+notas)?\s+de|,\s*em)\s+"
    rf"({_NOME_PROPRIO}(?:\s+(?:d[aeo]s?\s+)?{_NOME_PROPRIO})*)",
    re.I,
)

#: The individually-checked facts of a título phrase, in display order. The FE
#: contract (`divergencias[].fato`) — each is judged ON ITS OWN (owner
#: 2026-10-06: "one check doesn't fail others when others are ok").
FATOS_TITULO: tuple[str, ...] = (
    "data", "registro", "natureza", "tipo", "livro", "folhas", "tabelionato", "cidade",
)

#: What a título phrase says about the transaction itself -> canonical key.
_NATUREZAS_NO_TEXTO: tuple[tuple[str, str], ...] = (
    ("doacao", "doacao"),
    ("venda e compra", "compra_e_venda"),
    ("compra e venda", "compra_e_venda"),
    ("permuta", "permuta"),
    ("dacao", "dacao"),
    ("arrematacao", "arrematacao"),
    ("adjudicacao", "adjudicacao"),
    ("integralizacao", "integralizacao"),
    ("partilha", "partilha"),
)


def _sem_acento(texto: str) -> str:
    return fold_accents_ascii(texto).lower()


def _num_canonico(valor: str) -> str:
    """`071/076` == `71/76`: leading zeros are not a different folha."""
    return re.sub(r"\d+", lambda m: str(int(m.group())), valor)


#: A fact's readings: canonical key -> display text as written.
_Leituras = dict[str, str]


def _leituras_do_titulo(texto: Optional[str]) -> dict[str, _Leituras]:
    """Per-fact readings of a título phrase: `{fato: {chave: exibicao}}`. A
    fact absent from the text is simply not a key of the result."""
    if not texto:
        return {}
    norm = _sem_acento(texto)
    out: dict[str, _Leituras] = {}

    def _add(fato: str, chave: str, exibicao: str) -> None:
        out.setdefault(fato, {}).setdefault(chave, exibicao)

    for m in _DATA_RE.finditer(texto):
        d, mes, a = m.group().split("/")
        _add("data", f"{int(d)}/{int(mes)}/{a}", m.group())
    for m in _REF_RE.finditer(texto):
        _add("registro", f"{m.group(1).lower()}-{int(m.group(2))}", f"{m.group(1).upper()}-{m.group(2)}")
    for t in _TIPOS_INSTRUMENTO:
        if t in norm:
            _add("tipo", t, t)
    for termo, chave in _NATUREZAS_NO_TEXTO:
        if termo in norm:
            _add("natureza", chave, termo)
    m = _LIVRO_RE.search(texto)
    if m:
        bruto = m.group(1).rstrip(".,;")
        _add("livro", _num_canonico(bruto.lower()), bruto)
    m = _FOLHAS_RE.search(texto)
    if m:
        _add("folhas", _num_canonico(re.sub(r"\s+", "", m.group(1))), m.group(1).strip())
    m = _TABELIONATO_RE.search(texto)
    if m:
        chave = _sem_acento(m.group()).replace("tabeliao", "tabelionato")
        chave = re.sub(r"(\d+)\s*[o]?\s*tabelionato", r"\1 tabelionato", chave)
        _add("tabelionato", re.sub(r"\s+", " ", chave).strip(), m.group().strip())
    m = _CIDADE_RE.search(texto)
    if m:
        _add("cidade", _sem_acento(m.group(1)), m.group(1).strip())
    return out


def fatos_do_titulo(texto: Optional[str]) -> dict[str, tuple[str, ...]]:
    """The material facts a título phrase carries, ONE ENTRY PER FACT
    (`data`, `registro`, `tipo`, `livro`, `folhas`, `tabelionato`, `cidade`):
    `{fato: (valores como escritos...)}`. A fact the phrase does not state is
    absent. Facts are independent — comparing two phrasings is done fact by
    fact (`divergencias_do_titulo`), never as one bundled set."""
    return {f: tuple(v.values()) for f, v in _leituras_do_titulo(texto).items()}


def _comparar_fatos(texto: Optional[str], sugestao: Optional[str]) -> list[dict]:
    """One entry per fact whose readings differ between `texto` (what is
    stored) and `sugestao`: `{fato, atual, sugerido, so_no_atual}`.
    `so_no_atual` marks a value the stored text carries that the suggestion
    does not and that is NOT merely a different reading of the same slot —
    the fact (or an extra element of it) would be LOST by realigning."""
    atual, sug = _leituras_do_titulo(texto), _leituras_do_titulo(sugestao)
    out: list[dict] = []
    for fato in FATOS_TITULO:
        a, s = atual.get(fato, {}), sug.get(fato, {})
        if set(a) == set(s):
            continue
        so_atual = bool(a) and (not s or len(a) > len(s))
        out.append(
            {
                "fato": fato,
                "atual": ", ".join(a.values()) or None,
                "sugerido": ", ".join(s.values()) or None,
                "so_no_atual": so_atual,
            }
        )
    return out


def divergencias_do_titulo(texto: Optional[str], sugestao: Optional[str]) -> list[dict]:
    """`[{fato, atual, sugerido}]` — one entry per título fact whose value
    differs between the stored `texto` and the `sugestao` (different values,
    or present on one side only). Each fact is its own entry: a wrong
    `folhas` never flags `livro`, `data` or `registro`. Empty when either side
    is missing (nothing to compare)."""
    if not texto or not sugestao:
        return []
    return [
        {k: d[k] for k in ("fato", "atual", "sugerido")} for d in _comparar_fatos(texto, sugestao)
    ]


def fatos_so_no_texto(texto: Optional[str], sugestao: Optional[str]) -> list[str]:
    """Facts the stored `texto` states that realigning to `sugestao` would
    LOSE (absent from the suggestion, or extra elements beyond it)."""
    if not texto or not sugestao:
        return []
    return [d["fato"] for d in _comparar_fatos(texto, sugestao) if d["so_no_atual"]]


def menos_informativo(texto: Optional[str], sugestao: Optional[str]) -> bool:
    """True when `texto` lacks or misstates at least one fact `sugestao`
    carries (any divergent fact where the suggestion has a value)."""
    return any(d["sugerido"] is not None for d in divergencias_do_titulo(texto, sugestao))


def _divergencia_automatica(linha: dict, divergencias: list[dict]) -> bool:
    """An AUTO ("ia", no human behind it) confirmation with at least one
    divergent fact — the card must show it to a human. Manual/human-confirmed
    texts are never reported as needing realignment."""
    if not divergencias or linha.get("titulo_aquisitivo_texto_origem") != "ia":
        return False
    return not linha.get("titulo_aquisitivo_texto_confirmado_por")


ORIGEM_EXTRAIDO_CONFIRMADO = "matricula"


def _mesma_frase(a: Optional[str], b: Optional[str]) -> bool:
    """Byte-identical modulo surrounding/inner whitespace runs (the textarea
    may re-wrap) — NOT a semantic match: any wording edit is `manual`."""
    return bool(a and b) and " ".join(a.split()) == " ".join(b.split())


def _patch_confirmacao(
    coluna: str,
    valor: Optional[str],
    usuario_id: Optional[Any],
    *,
    origem: str = "manual",
) -> dict:
    """An operator's PUT: the value, its provenance (migration 154 — `manual`
    so a later extraction reading a different phrase opens a conflict instead
    of overwriting; `matricula` + a confirmation when the operator accepted
    the machine suggestion unchanged = "extracted, human-confirmed", F72),
    and the confirmation. Clearing clears all of it."""
    texto = (valor or "").strip() or None
    return {
        coluna: texto,
        f"{coluna}_origem": origem if texto else None,
        f"{coluna}_confirmado_por": str(usuario_id) if texto and usuario_id else None,
        f"{coluna}_confirmado_em": now_iso() if texto else None,
    }


# ─── act details ──────────────────────────────────────────────────────────


def confirmar_detalhes_ato(
    client: Any,
    org_id: UUID,
    ato_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[Any],
) -> dict:
    """`PUT /atos/{ato_id}/detalhes` — confirm/edit one act's details."""
    rows = (
        _t(client, estrutura_svc.ATOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(ato_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(estrutura_svc.ATOS_TABLE, str(ato_id))
    ato = rows[0]
    extracao = estrutura_svc.exigir_extracao(client, org_id, ato["extracao_id"])
    linha = detalhes_svc.confirmar(
        client,
        org_id,
        extracao=extracao,
        ato_row=ato,
        existente=detalhes_svc.linha_do_ato(client, org_id, ato["id"]),
        valores=valores,
        usuario_id=usuario_id,
    )
    detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
    resolved = table_reads.resolve_actors({linha.get("confirmado_por")} - {None})
    return {
        "ato_id": str(ato["id"]),
        "extracao_id": str(extracao["id"]),
        "kind": ato["kind"],
        "numero": ato.get("numero"),
        "ato_ref": _ato_ref(ato),
        "detalhes": detalhes_svc.detalhes_saida(linha, resolved),
    }


# ─── título aquisitivo phrase ─────────────────────────────────────────────


def _curar_ponteiro_morto(client: Any, org_id: UUID, codigo: str) -> bool:
    """Re-derive a MACHINE título pointer that quotes a removed documento's
    extraction, from the LIVE chain (the current matrícula, else its closed
    predecessors — the same rule `preenchimento_service` chose it by), and
    write it back in place. True when healed; False when the live chain has
    no título act (the pointer then stays, and the caller reports no
    suggestion)."""
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
    linha_propria = dados_service.linha(client, org_id, codigo) or {}
    # Healing writes the imóvel's OWN row; a pointer read through a vínculo
    # that is not that row is left to its owner.
    if str(linha_propria.get("titulo_aquisitivo_ato_id") or "") != str(
        linha.get("titulo_aquisitivo_ato_id") or ""
    ):
        return False
    fontes: list[dict] = []
    atual = _extracao_do_imovel(client, org_id, codigo, linha)
    if atual is not None and atual.get("status") == estrutura_svc.STATUS_CONCLUIDA:
        fontes.append(atual)
    fontes.extend(cadeia_dominial.extracoes_predecessoras(client, org_id, codigo))
    for fonte in fontes:
        atos = estrutura_svc.atos_da_extracao(client, org_id, fonte)
        detalhes = detalhes_svc.detalhes_por_ato(client, org_id, fonte, atos)
        texto = fonte.get("texto_extraido") or estrutura_svc.texto_da_extracao(
            client, org_id, fonte["id"]
        )
        titulo = (estrutura_svc.sugerir(texto or "", atos, detalhes) or {}).get(
            "titulo_aquisitivo"
        )
        if not titulo:
            continue
        estrutura_svc.definir_fontes(
            client,
            org_id,
            fonte["id"],
            valores={"titulo_aquisitivo_ato_id": titulo["ato_id"]},
            usuario_id=None,
        )
        return True
    return False


def obter_titulo(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    usuario_id: Optional[Any] = None,
    _curar: bool = True,
) -> dict:
    """The suggested título phrase (from the confirmed título act) + the
    operator's confirmed wording."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}

    ato_saida: Optional[dict] = None
    sugestao: Optional[str] = None
    motivo: Optional[str] = None
    ato_id = linha.get("titulo_aquisitivo_ato_id")
    if not ato_id:
        motivo = MOTIVO_SEM_TITULO
    else:
        extracao = estrutura_svc.extracao_viva(
            client, org_id, linha["titulo_aquisitivo_extracao_id"]
        )
        if extracao is None:
            humano = bool(linha.get("titulo_aquisitivo_confirmado_por")) or (
                linha.get("titulo_aquisitivo_origem") != "sugerido"
            )
            if humano:
                # A human's choice into a dead extraction: a pendência, never
                # a silent swap.
                motivo = MOTIVO_MATRICULA_REMOVIDA
            elif _curar and _curar_ponteiro_morto(client, org_id, codigo):
                return obter_titulo(
                    client, org_id, codigo, usuario_id=usuario_id, _curar=False
                )
            else:
                motivo = MOTIVO_SEM_TITULO
        if extracao is not None:
            por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
            ato = por_id.get(str(ato_id))
            if ato is None:
                # 109's RESTRICT FK makes this unreachable in the database.
                raise ValueError(
                    f"imóvel {codigo}: título aponta para o ato {ato_id}, ausente da "
                    f"extração {extracao['id']}"
                )
            det = detalhes.get(str(ato_id))
            ato_saida = {
                "extracao_id": str(extracao["id"]),
                "ato_id": str(ato["id"]),
                "kind": ato["kind"],
                "numero": ato.get("numero"),
                "ato_ref": _ato_ref(ato),
                "detalhes_origem": det.get("origem") if det else None,
            }
            if det is None:
                motivo = MOTIVO_SEM_DETALHES
            else:
                detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
                sugestao = cadeia_dominial.frase_titulo(
                    ato, det, cadeia_dominial.matricula_origem(client, org_id, extracao)
                )
                if sugestao is None:
                    motivo = MOTIVO_SEM_INSTRUMENTO

    divergencias = divergencias_do_titulo(linha.get("titulo_aquisitivo_texto"), sugestao)
    return {
        "codigo": codigo,
        "ato": ato_saida,
        "sugestao": sugestao,
        "motivo_sem_sugestao": motivo,
        "mensagem_pendencia": (
            MENSAGEM_MATRICULA_REMOVIDA if motivo == MOTIVO_MATRICULA_REMOVIDA else None
        ),
        "confirmado": _confirmacao(linha, "titulo_aquisitivo_texto", "texto"),
        # An automatic confirmation that diverges from the current suggestion
        # (owner 2026-10-06): shown, never silently kept.
        "divergente_da_sugestao": _divergencia_automatica(linha, divergencias),
        # Per-fact divergences (any origin) — each fact judged on its own.
        "divergencias": divergencias,
    }


def confirmar_titulo(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    texto: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    # F72 — provenance is decided HERE, server-side, against the CURRENT
    # suggestion (never a client flag): unchanged => extracted+confirmed
    # (`matricula` with `_confirmado_por`/`_em` set, so it is not pending);
    # anything else => operator-typed (`manual`).
    sugestao = obter_titulo(client, org_id, codigo, usuario_id=usuario_id).get("sugestao")
    origem = ORIGEM_EXTRAIDO_CONFIRMADO if _mesma_frase(texto, sugestao) else "manual"
    dados_service.gravar_texto_contrato(
        client,
        org_id,
        codigo,
        _patch_confirmacao("titulo_aquisitivo_texto", texto, usuario_id, origem=origem),
    )
    return obter_titulo(client, org_id, codigo, usuario_id=usuario_id)


# ─── endereço do registro (migration 139) ─────────────────────────────────


def obter_endereco_registro(client: Any, org_id: UUID, codigo: str) -> dict:
    """The operator's confirmed short address ("situado à ...") — NEVER a
    recomputed suggestion (see `imovel_dados.endereco_registro_texto`'s
    column comment): a wrong split of free legal prose into a compact
    address is exactly the guess this feature must not make.

    🔴 Does NOT reuse `_confirmacao`/`_patch_confirmacao`: those assume the
    confirmation columns are `{coluna}_confirmado_por/em` — true for
    `titulo_aquisitivo_texto`/`onus_credor`, but migration 139 named this
    pair `endereco_registro_confirmado_por/em`, dropping the `_texto`
    infix. Reusing the generic helper here reached for a column
    (`endereco_registro_texto_confirmado_por`) that does not exist —
    `dados_service.gravar_texto_contrato`'s own refusal-by-name caught it.
    """
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
    valor = linha.get("endereco_registro_texto")
    confirmado = None
    if valor is not None:
        resolved = table_reads.resolve_actors(
            {linha.get("endereco_registro_confirmado_por")} - {None}
        )
        confirmado = {
            "texto": valor,
            "confirmado_por": table_reads.actor(
                resolved, linha.get("endereco_registro_confirmado_por")
            ),
            "confirmado_em": linha.get("endereco_registro_confirmado_em"),
        }
    return {"codigo": codigo, "confirmado": confirmado}


def confirmar_endereco_registro(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    texto: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    valor = (texto or "").strip() or None
    patch = {
        "endereco_registro_texto": valor,
        "endereco_registro_confirmado_por": str(usuario_id) if valor and usuario_id else None,
        "endereco_registro_confirmado_em": now_iso() if valor else None,
    }
    dados_service.gravar_texto_contrato(client, org_id, codigo, patch)
    return obter_endereco_registro(client, org_id, codigo)


# ─── descrição do imóvel (migration 306) ──────────────────────────────────


def obter_descricao_imovel(
    client: Any, org_id: UUID, codigo: str, *, usuario_id: Optional[Any] = None
) -> dict:
    """The IMÓVEL: description the contract's OBJETO clause quotes.

    `derivado` is the matrícula abertura's `descricao_imovel` block read off
    the imóvel's current transcription (`None` when there is none, or no
    `IMÓVEL:` label was recognised); `confirmado` is the operator-typed
    override (migration 306), which WINS in the contract loader and is never
    touched by a later transcription."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}

    derivado: Optional[str] = None
    extracao = _extracao_do_imovel(client, org_id, codigo, linha)
    if extracao is not None and extracao.get("status") == estrutura_svc.STATUS_CONCLUIDA:
        derivado = estrutura_svc.descricao_imovel_da_extracao(
            client, org_id, extracao, usuario_id=usuario_id
        )

    valor = linha.get("descricao_imovel_texto")
    confirmado = None
    if valor is not None:
        resolved = table_reads.resolve_actors(
            {linha.get("descricao_imovel_confirmado_por")} - {None}
        )
        confirmado = {
            "texto": valor,
            "confirmado_por": table_reads.actor(
                resolved, linha.get("descricao_imovel_confirmado_por")
            ),
            "confirmado_em": linha.get("descricao_imovel_confirmado_em"),
        }
    return {
        "codigo": codigo,
        "derivado": derivado,
        "confirmado": confirmado,
        "efetivo": (confirmado or {}).get("texto") or derivado,
        "origem": "manual" if confirmado else ("matricula" if derivado else None),
    }


def confirmar_descricao_imovel(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    texto: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    """`PUT /imoveis/{codigo}/descricao-imovel` — type/confirm the IMÓVEL:
    description; blank or `null` clears the override (the derived block
    answers again)."""
    codigo = _codigo(codigo)
    valor = (texto or "").strip() or None
    patch = {
        "descricao_imovel_texto": valor,
        "descricao_imovel_confirmado_por": str(usuario_id) if valor and usuario_id else None,
        "descricao_imovel_confirmado_em": now_iso() if valor else None,
    }
    dados_service.gravar_texto_contrato(client, org_id, codigo, patch)
    return obter_descricao_imovel(client, org_id, codigo, usuario_id=usuario_id)


# ─── ônus creditor ────────────────────────────────────────────────────────


def obter_onus_credor(
    client: Any, org_id: UUID, codigo: str, *, usuario_id: Optional[Any] = None
) -> dict:
    """The creditor(s) read from the confirmed ônus acts + the confirmation."""
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}

    atos_saida: list[dict] = []
    credores: list[str] = []
    motivo: Optional[str] = None
    extracao_id = linha.get("onus_fonte_extracao_id")
    fonte = linha.get("onus_fonte_atos") or []
    if not extracao_id or not fonte:
        motivo = MOTIVO_SEM_ONUS
    else:
        extracao = estrutura_svc.exigir_extracao(client, org_id, extracao_id)
        por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
        leu = False
        for ref in fonte:
            ato = por_id.get(str(ref["ato_id"]))
            if ato is None:
                raise ValueError(
                    f"imóvel {codigo}: ônus aponta para o ato {ref['ato_id']}, ausente "
                    f"da extração {extracao['id']}"
                )
            det = detalhes.get(str(ato["id"]))
            leu = leu or det is not None
            credor = det.get("credor") if det else None
            atos_saida.append(
                {
                    "ato_id": str(ato["id"]),
                    "kind": ato["kind"],
                    "numero": ato.get("numero"),
                    "ato_ref": _ato_ref(ato),
                    "natureza": det.get("natureza") if det else None,
                    "credor": credor,
                    "credor_confianca": (det.get("credor_confianca") if det else None)
                    or "nenhuma",
                    "detalhes_origem": det.get("origem") if det else None,
                }
            )
            if credor and credor not in credores:
                credores.append(credor)
        if leu:
            detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)
        if not credores:
            motivo = MOTIVO_SEM_CREDOR

    return {
        "codigo": codigo,
        "extracao_id": extracao_id,
        "atos": atos_saida,
        "sugestao": "; ".join(credores) or None,
        "motivo_sem_sugestao": motivo,
        "confirmado": _confirmacao(linha, "onus_credor", "credor"),
    }


def confirmar_onus_credor(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    credor: Optional[str],
    usuario_id: Optional[Any],
) -> dict:
    codigo = _codigo(codigo)
    dados_service.gravar_texto_contrato(
        client, org_id, codigo, _patch_confirmacao("onus_credor", credor, usuario_id)
    )
    return obter_onus_credor(client, org_id, codigo, usuario_id=usuario_id)


# ─── previous owners ──────────────────────────────────────────────────────


def _anos_antes(dia: date, anos: int) -> date:
    try:
        return dia.replace(year=dia.year - anos)
    except ValueError:  # 29 Feb -> 28 Feb
        return dia.replace(year=dia.year - anos, day=28)


def _extracao_do_imovel(
    client: Any, org_id: UUID, codigo: str, linha: dict
) -> Optional[dict]:
    """The título's own extraction when one is confirmed; otherwise the
    imóvel's newest concluded transcription."""
    if linha.get("titulo_aquisitivo_extracao_id"):
        # A pointer into a REMOVED documento's extraction is stale: ignored
        # (falls through to the live ones), never read.
        apontada = estrutura_svc.extracao_viva(
            client, org_id, linha["titulo_aquisitivo_extracao_id"]
        )
        if apontada is not None:
            return apontada
    # The matrícula is the PROPERTY's: a Vista código linked to a manual
    # imóvel falls back to the manual one's transcription (`vinculo_legal`).
    for fonte in vinculo_legal.codigos_leitura(client, org_id, codigo):
        rows = (
            _t(client, estrutura_svc.EXTRACOES_TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("codigo", fonte)
            .eq("status", estrutura_svc.STATUS_CONCLUIDA)
            .order("created_at", desc=True)
            .execute()
        ).data or []
        # A CLOSED (transferred) matrícula is a predecessor: never the current
        # reading, however recently transcribed (`cadeia_dominial`).
        for linha_extracao in rows:
            if estrutura_svc.documento_removido(client, org_id, linha_extracao):
                continue
            if not cadeia_dominial.extracao_e_predecessora(client, org_id, linha_extracao):
                return linha_extracao
    return None


def _manual_ultima_transferencia(linha: dict) -> Optional[dict]:
    """The RAW manual-override state (migration 152) — always returned so the
    property page can show/edit it regardless of whether a derivation below
    is currently the effective source. `None` means no override was ever
    confirmed."""
    confirmado_em = linha.get("ultima_transferencia_manual_confirmado_em")
    if confirmado_em is None:
        return None
    resolved = table_reads.resolve_actors(
        {linha.get("ultima_transferencia_manual_confirmado_por")} - {None}
    )
    bruto = linha.get("ultima_transferencia_manual_data")
    return {
        "data_registro": str(bruto)[:10] if bruto else None,
        "natureza": linha.get("ultima_transferencia_manual_natureza"),
        "sem_registro": bool(linha.get("ultima_transferencia_manual_sem_registro")),
        # Migration 306 — who sold, typed (names only).
        "transmitentes": list(linha.get("ultima_transferencia_manual_transmitentes") or []),
        "confirmado_por": table_reads.actor(
            resolved, linha.get("ultima_transferencia_manual_confirmado_por")
        ),
        "confirmado_em": confirmado_em,
    }


def _transmitentes_qualificados(
    extracao: dict, ato: dict, partes: list[dict]
) -> list[dict]:
    """The act's sellers as `{nome, cpf_cnpj[, qualificado_em]}`. A seller the
    act names only as "já qualificado" carries the CPF/CNPJ the most recent
    EARLIER act of the same matrícula qualified him with (F97 — the seed's
    `qualificar_por_referencia`, the same mechanism `extrair_detalhes_ato`
    runs at parse). A machine row already carries it; a HUMAN-confirmed row
    (never re-derived) is resolved here, at read, off the stored text — the
    confirmation is never rewritten, a document the human left blank is only
    completed when the text proves whose it is."""
    lidas = [Parte.from_json(p) for p in partes if p.get("nome")]
    texto = extracao.get("texto_extraido")
    if (
        texto
        and ato.get("char_inicio") is not None
        and any(not p.cpf_cnpj for p in lidas)
    ):
        inicio, fim = int(ato["char_inicio"]), int(ato["char_fim"])
        (lidas,) = qualificar_por_referencia((lidas,), texto[inicio:fim], texto[:inicio])
    saida = []
    for p in lidas:
        item = {"nome": normalizar_nome_parte(p.nome), "cpf_cnpj": p.cpf_cnpj}
        if p.qualificado_em:
            item["qualificado_em"] = p.qualificado_em
        saida.append(item)
    # A stored party with a document but no name stays as it was.
    saida += [
        {"nome": None, "cpf_cnpj": p.get("cpf_cnpj")} for p in partes if not p.get("nome")
    ]
    return saida


def _transmitentes_por_referencia(
    client: Any, org_id: UUID, extracao: dict, ato: dict, det: dict
) -> list[dict]:
    """The sellers of an act that names them only by back-reference ("os
    proprietários retro nomeados e qualificados transmitiram ..."): the owners
    at that point of the chain — the adquirentes of the latest earlier
    ownership-transferring act of the SAME matrícula, else the abertura's
    PROPRIETÁRIOS. `[]` when the act is not a back-reference or nothing can be
    resolved (never a phrase stored as a name)."""
    texto = extracao.get("texto_extraido")
    if not texto or ato.get("char_inicio") is None:
        return []
    texto_ato = texto[int(ato["char_inicio"]) : int(ato["char_fim"])]
    if not transmitentes_por_referencia(texto_ato, parse_detalhes_json(det)):
        return []
    por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
    anteriores = [
        por_id[ato_id]
        for ato_id, d in detalhes.items()
        if ato_id in por_id
        and por_id[ato_id].get("kind") != "abertura"
        and por_id[ato_id]["ordem"] < ato["ordem"]
        and d.get("natureza") in NATUREZAS_TRANSFERENCIA
        and d.get("adquirentes")
    ]
    if anteriores:
        ultimo = max(anteriores, key=lambda r: r["ordem"])
        return [
            {"nome": normalizar_nome_parte(p.get("nome")), "cpf_cnpj": p.get("cpf_cnpj")}
            for p in detalhes[str(ultimo["id"])]["adquirentes"]
            if p.get("nome")
        ]
    for bloco in estrutura_svc.blocos_abertura_da_extracao(client, org_id, extracao):
        if bloco.get("campo") == "proprietarios":
            return [
                {"nome": p.nome, "cpf_cnpj": p.cpf_cnpj}
                for p in partes_de_bloco(
                    texto[int(bloco["char_inicio"]) : int(bloco["char_fim"])]
                )
            ]
    return []


def antigos_proprietarios(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    usuario_id: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> dict:
    """`_antigos_proprietarios_derivados` + the operator-typed sellers
    (migration 306): a non-empty typed name list WINS over the names read
    off the act — it is a human's correction, protected from any later
    re-read. `transmitentes_origem` says which answered (`matricula` |
    `manual` | `None` when nobody is known)."""
    saida = _antigos_proprietarios_derivados(
        client, org_id, codigo, usuario_id=usuario_id, hoje=hoje
    )
    nomes = ((saida.get("manual") or {}).get("transmitentes")) or []
    if nomes:
        saida["transmitentes"] = [{"nome": nome, "cpf_cnpj": None} for nome in nomes]
        saida["transmitentes_origem"] = "manual"
    else:
        saida["transmitentes_origem"] = "matricula" if saida["transmitentes"] else None
    return saida


def _antigos_proprietarios_derivados(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    usuario_id: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> dict:
    """Who sold the imóvel in its last registered transfer of ownership,
    when, and whether the office rule requires their certidões.

    Priority for `ultima_transferencia` [migration 152]:
    1. The CONFIRMED título aquisitivo act, when its `natureza` is one of
       `NATUREZAS_ULTIMA_TRANSFERENCIA` — an operator already verified this
       act IS how the current owner acquired, so it is trusted over a blind
       re-scan (fixes the permuta dead end: a confirmed título act whose
       nature is `permuta` was invisible to the old compra-e-venda-only
       search).
    2. Otherwise, the LATEST such act anywhere in the extraction (by
       `ordem`) — the original heuristic, now recognising every nature in
       `NATUREZAS_ULTIMA_TRANSFERENCIA` instead of `compra_e_venda` alone.
    3. Otherwise, the operator's manual override: a typed date, or an
       explicit "não consta transferência registrada" statement that
       resolves `exige_certidoes` to `False` instead of leaving it unknown.
       ALSO the answer when 1./2. found an act whose `data_registro` is
       blank: a dateless act cannot answer "when", the override can (the
       act is still reported as `ato_sem_data`, and its `transmitentes`).
    `manual` in the response always reports the raw override state, even
    when a derivation above wins — the property page shows/edits it either
    way.
    """
    codigo = _codigo(codigo)
    dados_service.ensure_imovel(client, org_id, codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
    hoje = hoje or today()

    extracao = _extracao_do_imovel(client, org_id, codigo, linha)
    saida: dict[str, Any] = {
        "codigo": codigo,
        "extracao_id": str(extracao["id"]) if extracao else None,
        "ultima_transferencia": None,
        "transmitentes": [],
        "exige_certidoes": False,
        "data_desconhecida": False,
        "sem_registro": False,
        "origem": None,
        "manual": _manual_ultima_transferencia(linha),
    }

    ato: Optional[dict] = None
    det: Optional[dict] = None
    origem_derivacao: Optional[str] = None
    #: The extraction the derived act LIVES in (the current one, or a closed
    #: predecessor matrícula's — `cadeia_dominial`).
    extracao_do_ato = extracao

    if extracao is not None and extracao.get("status") == estrutura_svc.STATUS_CONCLUIDA:
        por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)

        ato_id_titulo = linha.get("titulo_aquisitivo_ato_id")
        det_titulo = detalhes.get(str(ato_id_titulo)) if ato_id_titulo else None
        if (
            ato_id_titulo
            and str(ato_id_titulo) in por_id
            and det_titulo is not None
            and det_titulo.get("natureza") in NATUREZAS_ULTIMA_TRANSFERENCIA
        ):
            ato, det, origem_derivacao = (
                por_id[str(ato_id_titulo)],
                det_titulo,
                "titulo_confirmado",
            )
        else:
            transferencias = [
                por_id[ato_id]
                for ato_id, d in detalhes.items()
                if d.get("natureza") in NATUREZAS_ULTIMA_TRANSFERENCIA and ato_id in por_id
            ]
            if transferencias:
                ato = max(transferencias, key=lambda r: r["ordem"])
                det = detalhes[str(ato["id"])]
                origem_derivacao = "extracao"

    if ato is None:
        # The current matrícula has no transmission act of its own (it opens
        # with "REGISTRO ANTERIOR: …"): the last transfer lives on a closed
        # predecessor. Newest predecessor first; the latest act wins.
        for anterior in cadeia_dominial.extracoes_predecessoras(client, org_id, codigo):
            por_id_ant, detalhes_ant = _atos_e_detalhes(client, org_id, anterior)
            candidatas = [
                por_id_ant[ato_id]
                for ato_id, d in detalhes_ant.items()
                if d.get("natureza") in NATUREZAS_ULTIMA_TRANSFERENCIA and ato_id in por_id_ant
            ]
            if candidatas:
                ato = max(candidatas, key=lambda r: r["ordem"])
                det = detalhes_ant[str(ato["id"])]
                origem_derivacao = "matricula_anterior"
                extracao_do_ato = anterior
                break

    manual = saida["manual"]
    manual_responde = bool(manual and (manual.get("data_registro") or manual.get("sem_registro")))
    data_registro: Optional[date] = None
    if ato is not None and det is not None:
        detalhes_svc.log_leitura_detalhes(client, org_id, extracao_do_ato["id"], usuario_id)
        bruto = det.get("data_registro")
        data_registro = date.fromisoformat(str(bruto)[:10]) if bruto else None
        # The derived act's sellers are still who sold, whatever answers the
        # date question below.
        saida["transmitentes"] = _transmitentes_qualificados(
            extracao_do_ato, ato, det.get("transmitentes") or []
        )
        if not saida["transmitentes"]:
            saida["transmitentes"] = _transmitentes_por_referencia(
                client, org_id, extracao_do_ato, ato, det
            )
    if ato is not None and det is not None and (data_registro is not None or not manual_responde):
        limite = _anos_antes(hoje, ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS)
        saida.update(
            {
                "ultima_transferencia": {
                    "ato_id": str(ato["id"]),
                    "ato_ref": _ato_ref(ato),
                    "natureza": det.get("natureza"),
                    "data_registro": data_registro.isoformat() if data_registro else None,
                    "detalhes_origem": det.get("origem"),
                    "extracao_id": str(extracao_do_ato["id"]),
                    "matricula_origem": cadeia_dominial.matricula_origem(
                        client, org_id, extracao_do_ato
                    ),
                },
                "exige_certidoes": data_registro is None or data_registro > limite,
                "data_desconhecida": data_registro is None,
                "origem": origem_derivacao,
            }
        )
        return saida

    # [2026-10-03 fix, deal 859] Reached ALSO when a transfer act WAS derived
    # but carries no `data_registro` (reader left it blank) and an operator
    # confirmed an override: the override answers the question the act
    # cannot. Returning the dateless act first used to make the property
    # page's "confirme na página do imóvel" a dead end — the override was
    # stored but never read, so `data_desconhecida` stayed True forever.
    # The dateless act stays visible as `ato_sem_data` (never silently lost).
    if ato is not None:
        saida["ato_sem_data"] = {"ato_id": str(ato["id"]), "ato_ref": _ato_ref(ato)}
    if manual and manual.get("sem_registro"):
        saida["sem_registro"] = True
        saida["origem"] = "manual"
        return saida
    if manual and manual.get("data_registro"):
        data_registro = date.fromisoformat(manual["data_registro"])
        limite = _anos_antes(hoje, ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS)
        saida.update(
            {
                "ultima_transferencia": {
                    "ato_id": None,
                    "ato_ref": None,
                    "natureza": manual.get("natureza"),
                    "data_registro": manual["data_registro"],
                    "detalhes_origem": "manual",
                },
                "exige_certidoes": data_registro > limite,
                "data_desconhecida": False,
                "origem": "manual",
            }
        )
    return saida


def texto_da_matricula(client: Any, org_id: UUID, codigo: str) -> Optional[str]:
    """The imóvel's newest CONCLUDED matrícula transcription (raw text), or
    `None` — a fact source for readers that scan the whole matrícula (the RG
    an averbação states). Same extraction pick as `antigos_proprietarios`."""
    codigo = _codigo(codigo)
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
    extracao = _extracao_do_imovel(client, org_id, codigo, linha)
    if extracao is None or extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA:
        return None
    return extracao.get("texto_extraido") or None


def titularidade_atual(
    client: Any, org_id: UUID, codigo: str, *, usuario_id: Optional[Any] = None
) -> dict:
    """Who OWNS the imóvel now, per its matrícula: the adquirentes of the LAST
    ownership-transferring act (the WIDE `NATUREZAS_TRANSFERENCIA` — an heir
    or a donee IS the owner, unlike `antigos_proprietarios`' narrower
    "sold for consideration" set), plus that act's `natureza` and
    `transmitentes` (the DOADORES when the act is a doação).

    `{"natureza": None, "proprietarios": [], "transmitentes": []}` when no
    concluded matrícula or no such act exists — owners UNKNOWN, which the
    contract gate reads as "nothing to check", never as "nobody owns it".
    Each entry is `{"nome", "cpf_cnpj"}` as the act printed it."""
    codigo = _codigo(codigo)
    vazio: dict[str, Any] = {"natureza": None, "proprietarios": [], "transmitentes": []}
    linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
    extracao = _extracao_do_imovel(client, org_id, codigo, linha)
    if extracao is None or extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA:
        return vazio
    por_id, detalhes = _atos_e_detalhes(client, org_id, extracao)
    transferencias = [
        por_id[ato_id]
        for ato_id, d in detalhes.items()
        if d.get("natureza") in NATUREZAS_TRANSFERENCIA
        and ato_id in por_id
        and por_id[ato_id].get("kind") != "abertura"
    ]
    if not transferencias:
        return vazio
    ato = max(transferencias, key=lambda r: r["ordem"])
    det = detalhes[str(ato["id"])]
    detalhes_svc.log_leitura_detalhes(client, org_id, extracao["id"], usuario_id)

    def _partes(chave: str) -> list[dict]:
        return [
            {"nome": p.get("nome"), "cpf_cnpj": p.get("cpf_cnpj")}
            for p in det.get(chave) or []
            if p.get("nome")
        ]

    return {
        "natureza": det.get("natureza"),
        "proprietarios": _partes("adquirentes"),
        "transmitentes": _partes("transmitentes"),
    }


def _nomes_limpos(nomes: Optional[list[str]]) -> list[str]:
    """Typed names: trimmed, inner whitespace collapsed, blanks dropped,
    exact repeats dropped (order kept)."""
    saida: list[str] = []
    for nome in nomes or []:
        limpo = " ".join(str(nome or "").split())
        if limpo and limpo not in saida:
            saida.append(limpo)
    return saida


def confirmar_ultima_transferencia_manual(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    data: Optional[date],
    natureza: Optional[str],
    sem_registro: bool,
    usuario_id: Optional[Any],
    transmitentes: Optional[list[str]] = None,
) -> dict:
    """`PUT /imoveis/{codigo}/ultima-transferencia` [migration 152] — the
    manual fallback for [Q9]'s previous-owner rule, always available on the
    property page next to "Antigos proprietários": a typed date (+ optional
    nature), or an explicit "não consta transferência registrada" statement
    — which the gate must treat as an ANSWER (`exige_antigo_proprietario`
    resolves to `False`), never as still-unknown. `data=None, natureza=None,
    sem_registro=False` clears the override.

    `transmitentes` (migration 306) — the sellers' names, typed. A full
    replace (the body carries the whole override); a list alone is a valid
    override (an act was found, its sellers were not read). Refused next to
    `sem_registro` — names of who sold contradict "no transfer".
    """
    codigo = _codigo(codigo)
    nomes = _nomes_limpos(transmitentes)
    if nomes and sem_registro:
        raise ValidationError_(
            "Não informe transmitentes quando não consta transferência registrada.",
            field="transmitentes",
        )
    if data is not None and sem_registro:
        raise ValidationError_(
            "Informe uma data OU marque que não consta transferência registrada — não os dois.",
            field="sem_registro",
        )
    if natureza is not None and data is None:
        raise ValidationError_(
            "A natureza da transferência exige uma data de registro.", field="natureza"
        )
    if natureza is not None and natureza not in NATUREZAS_ULTIMA_TRANSFERENCIA:
        raise ValidationError_(
            f"Natureza inválida para a última transferência: {natureza}", field="natureza"
        )

    limpar = data is None and not sem_registro and not nomes
    patch = {
        "ultima_transferencia_manual_data": data,
        "ultima_transferencia_manual_natureza": natureza if data is not None else None,
        "ultima_transferencia_manual_sem_registro": bool(sem_registro),
        "ultima_transferencia_manual_transmitentes": nomes,
        "ultima_transferencia_manual_confirmado_por": (
            None if limpar else (str(usuario_id) if usuario_id else None)
        ),
        "ultima_transferencia_manual_confirmado_em": None if limpar else now_iso(),
    }
    dados_service.gravar_ultima_transferencia_manual(client, org_id, codigo, patch)
    return antigos_proprietarios(client, org_id, codigo, usuario_id=usuario_id)


__all__ = [
    "ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS",
    "NATUREZAS_ULTIMA_TRANSFERENCIA",
    "antigos_proprietarios",
    "confirmar_descricao_imovel",
    "obter_descricao_imovel",
    "texto_da_matricula",
    "titularidade_atual",
    "confirmar_detalhes_ato",
    "confirmar_onus_credor",
    "confirmar_titulo",
    "confirmar_ultima_transferencia_manual",
    "divergencias_do_titulo",
    "fatos_do_titulo",
    "fatos_so_no_texto",
    "menos_informativo",
    "obter_onus_credor",
    "obter_titulo",
]
