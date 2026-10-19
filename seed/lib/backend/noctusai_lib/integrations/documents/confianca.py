"""Trust gate after the PRIMARY read: a deterministic per-field verdict,
`confiavel` | `duvidoso` (+ reasons) | `ausente`.

WHY THIS EXISTS (owner direction 2026-10-13)
--------------------------------------------
"Use the comparison and disagreement data to learn the models' accuracy and
choose the best model per data and document, the second best as fallback;
then conciliation only on low-reliability extractions that don't pass the
first model's quality and trust gate. Always debating every run is too
expensive." This module IS that quality and trust gate. `real.
LadderIdentityExtractor` reads once with the routed primary model
(`roteamento.rota`), asks this module about every critical field, and pays
for ONE fallback read only when a critical field comes back `duvidoso` (or a
core field is missing). Pure and deterministic: no IO, no model call.

THE RULES (each emits a stable reason code)
-------------------------------------------
Document level — apply to every field of the read:
- `leitura_comprometida` — the legibility gate flagged the transcription.
- `ancora_falhou` — a CPF / 32-digit matrícula in the text failed its check
  digit: the model mis-copied digits on this page.
- `resolucao_reduzida` — the page was rendered at reduced resolution (an aviso
  the transcriber raises). SOFT: a field whose own check digit verifies, or
  that another document corroborates, still passes.

Field level:
- cpf: check digit (`primitives.identificador`) -> `dv_invalido`.
- rg: SP check digit / shape (`identificador.ler("rg")`, `rg_anomalia`) ->
  `dv_invalido` / `formato_anomalo`.
- rne: the RNE/CRNM mask -> `mascara_invalida`.
- matricula_certidao: the 32-digit RCPN matrícula, DV mod-11 weights 31->2,
  `11-r`, 10/11 -> 0 (`identificador.validar_matricula_rcpn`) -> `dv_invalido`.
- estado_civil / regime_bens / profissao: closed vocabularies ->
  `vocabulario_invalido`.
- data_nascimento / data_casamento: plausible dates -> `data_implausivel`.
- nome: at least two words -> `nome_incompleto`.
- conjuges (certidão de casamento): both spouses -> `conjuges_incompletos`.
- parser confidence: `nenhuma` on a present value is always doubt; `baixa`
  only on fields whose parser emits a CALIBRATED confidence
  (`_CONFIANCA_CALIBRADA` — on the real benchmark every correct cpf /
  estado_civil / regime_bens read was `alta` and both wrong CPFs were
  `baixa`; nome/rg OCR confidence is capped at `baixa` by design, so it
  carries no signal) -> `confianca_parser_baixa` (SOFT).
- measured precision: the routing table's residual precision of (primary
  model, doc type, field) — precision among reads that passed every rule
  above — below `roteamento.LIMIAR_PRECISAO` with a sample that clears the
  minimum-sample rule -> `precisao_medida_baixa` (SOFT). A thin sample gives
  no verdict either way (`precisao_nao_medida`, informational only).
- cross-document corroboration (when the caller passes `confirmados`): the
  value already confirmed on the cliente from ANOTHER document agrees ->
  `corroborado_outro_documento`, which clears SOFT doubts; it disagrees ->
  `diverge_de_valor_confirmado` (doubt).

Never-overridable doubts (HARD): a failed check digit, a vocabulary miss,
an implausible date, a compromised read, a failed anchor, a contradicted
confirmed value. Corroboration never launders those.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.documents import autoridade
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
)
# `AVISO_RESOLUCAO_REDUZIDA` — the aviso a transcription raises when a page
# reached the vision model below its legibility floor. Owned by
# `vision_tiling` (carried onto the read by `releitura.
# marcar_resolucao_reduzida`); this gate only consumes it.
from noctusai_lib.integrations.documents.vision_tiling import AVISO_RESOLUCAO_REDUZIDA
from noctusai_lib.primitives import identificador as _ident

CONFIAVEL = "confiavel"
DUVIDOSO = "duvidoso"
AUSENTE = "ausente"


#: Critical identity fields the gate judges (`releitura.CAMPOS_CRITICOS` plus
#: the two document-level groups). Kept in `releitura` as the one list.
def campos_criticos() -> tuple[str, ...]:
    from noctusai_lib.integrations.documents.releitura import CAMPOS_CRITICOS

    return (*CAMPOS_CRITICOS, "conjuges", "matricula_certidao")


#: Non-critical fields the gate also judges (reported, never a fallback
#: trigger on their own).
CAMPOS_INFORMATIVOS: tuple[str, ...] = ("profissao", "genero", "nacionalidade")

#: Fields whose parser emits a calibrated confidence (see module docstring).
_CONFIANCA_CALIBRADA = frozenset({"cpf", "estado_civil", "regime_bens"})

#: Critical fields whose vision-read confidence is CAPPED at `baixa` by
#: design (`real._temper_name_confidence`) — their `baixa` carries no signal
#: on its own, so evidence found by this gate may raise it (`calibrar`).
_CONFIANCA_LIMITADA = frozenset({"nome", "rg", "rne"})

#: Reasons that corroboration or a verified check digit can clear.
MOTIVOS_SUAVES = frozenset({
    "confianca_parser_baixa", "precisao_medida_baixa", AVISO_RESOLUCAO_REDUZIDA,
})
#: Informational reasons (never doubt).
MOTIVOS_INFORMATIVOS = frozenset({
    "precisao_nao_medida", "corroborado_outro_documento", "dv_verificado",
    "precisao_medida_ok",
})

#: 🔴 CONFIDENCE CALIBRATION (deal 876, 2026-10-19) — the POSITIVE evidence
#: that lets a gate-cleared `baixa` reading be stored as `media`
#: (`calibrar`). Each is deterministic and independent of the model's own
#: say-so: a check digit that verifies, another document that already holds
#: the same value, or a measured per-(model, type, field) precision at or
#: above `roteamento.LIMIAR_PRECISAO` on a sufficient sample. A verdict that
#: is `confiavel` only because nothing was measured (`precisao_nao_medida`)
#: carries NONE of these and stays `baixa` — the real low-confidence reads
#: keep their flag.
MOTIVOS_EVIDENCIA = frozenset({
    "dv_verificado", "corroborado_outro_documento", "precisao_medida_ok",
})

_ANO_MINIMO = 1900


@dataclass(frozen=True)
class Veredito:
    estado: str
    motivos: tuple[str, ...] = ()

    @property
    def duvidoso(self) -> bool:
        return self.estado == DUVIDOSO


def _codigos(aviso: Optional[str]) -> set[str]:
    return set(aviso.split("+")) if aviso else set()


def _valor(fields: IdentityFields, campo: str) -> Any:
    return getattr(fields, campo, None)


def _presente(fields: IdentityFields, campo: str) -> bool:
    if campo == "conjuges":
        return bool(fields.conjuges)
    return bool(_valor(fields, campo))


def _confianca(fields: IdentityFields, campo: str) -> Optional[ExtractionConfidence]:
    return getattr(fields, f"{campo}_confianca", None)


def _dv_verificado(campo: str, valor: Any) -> bool:
    if campo == "cpf":
        return _ident.ler("cpf", str(valor)).dv_ok is True
    if campo == "matricula_certidao":
        r = _ident.validar_matricula_rcpn(valor)
        return bool(r.valido and not r.avisos)
    if campo == "rg":
        return _ident.ler("rg", str(valor)).dv_ok is True
    return False


def _data_implausivel(valor: Any, *, minimo: Optional[date] = None) -> bool:
    if not isinstance(valor, date):
        return False
    if valor > date.today() or valor.year < _ANO_MINIMO:
        return True
    return minimo is not None and valor < minimo


def _regras_campo(fields: IdentityFields, campo: str, tipo: Optional[str]) -> list[str]:
    """HARD/SOFT field-level reasons (no document-level, precision or
    corroboration reasons — those are added by `avaliar`)."""
    from noctusai_lib.integrations.documents.civil_status import (
        ESTADO_CIVIL_DOCUMENTAL,
        REGIME_BENS_VALORES,
    )

    valor = _valor(fields, campo)
    motivos: list[str] = []
    if campo == "cpf":
        if _ident.ler("cpf", str(valor)).dv_ok is not True:
            motivos.append("dv_invalido")
    elif campo == "rg":
        from noctusai_lib.integrations.documents.rg import separar_orgao_uf

        uf = separar_orgao_uf(fields.rg_orgao)[1]
        leitura = _ident.ler("rg", str(valor), uf=uf)
        if leitura.motivo == "dv_invalido":
            motivos.append("dv_invalido")
        elif _ident.rg_anomalia(valor, uf=uf) is not None:
            motivos.append("formato_anomalo")
    elif campo == "rne":
        if not _ident.validar_rne(valor).valido:
            motivos.append("mascara_invalida")
    elif campo == "matricula_certidao":
        if not _dv_verificado(campo, valor):
            motivos.append("dv_invalido")
    elif campo == "estado_civil":
        if str(valor) not in ESTADO_CIVIL_DOCUMENTAL:
            motivos.append("vocabulario_invalido")
    elif campo == "regime_bens":
        if str(valor) not in REGIME_BENS_VALORES:
            motivos.append("vocabulario_invalido")
    elif campo == "profissao":
        from noctusai_lib.integrations.documents.profession import avaliar_profissao

        if not avaliar_profissao(str(valor))[0]:
            motivos.append("vocabulario_invalido")
    elif campo == "data_nascimento":
        if _data_implausivel(valor):
            motivos.append("data_implausivel")
    elif campo == "data_casamento":
        if _data_implausivel(valor, minimo=fields.data_nascimento):
            motivos.append("data_implausivel")
    elif campo == "nome":
        if len(re.findall(r"[^\W\d_]{2,}", str(valor))) < 2:
            motivos.append("nome_incompleto")
    elif campo == "conjuges":
        if autoridade.tipo_normalizado(tipo) == "CERTIDAO_CASAMENTO" and len(fields.conjuges) != 2:
            motivos.append("conjuges_incompletos")

    if campo not in ("conjuges", "matricula_certidao"):
        conf = _confianca(fields, campo)
        if conf is ExtractionConfidence.NENHUMA:
            motivos.append("confianca_parser_baixa")
        elif conf is ExtractionConfidence.BAIXA and campo in _CONFIANCA_CALIBRADA:
            motivos.append("confianca_parser_baixa")
    return motivos


def campos_avaliados(fields: IdentityFields, tipo_documento: Optional[str]) -> tuple[str, ...]:
    """The critical fields this type may emit (authority table), plus the
    informative ones it may emit."""
    autorizados = autoridade.campos_autorizados(tipo_documento)
    out = []
    for campo in (*campos_criticos(), *CAMPOS_INFORMATIVOS):
        if autorizados is None or campo in autorizados:
            out.append(campo)
    return tuple(out)


def avaliar(
    fields: IdentityFields,
    tipo_documento: Optional[str],
    *,
    modelo: Optional[str] = None,
    confirmados: Optional[Mapping[str, Any]] = None,
    medir_precisao: bool = True,
) -> dict[str, Veredito]:
    """The per-field verdict of ONE read. `modelo` is the model that produced
    it (for the measured-precision rule); `confirmados` maps a critical field
    to the value already confirmed on the cliente from ANOTHER document;
    `medir_precisao=False` gives the purely deterministic verdict (what the
    recalibration measures residual precision against)."""
    from noctusai_lib.integrations.documents import roteamento
    from noctusai_lib.integrations.documents.releitura import _mesmo_valor

    codigos = _codigos(fields.aviso)
    documento: list[str] = []
    if fields.error is not None:
        documento.append("erro_leitura")
    if fields.leitura_comprometida:
        documento.append("leitura_comprometida")
    if fields.ancora_falhou:
        documento.append("ancora_falhou")
    if AVISO_RESOLUCAO_REDUZIDA in codigos:
        documento.append(AVISO_RESOLUCAO_REDUZIDA)

    vereditos: dict[str, Veredito] = {}
    for campo in campos_avaliados(fields, tipo_documento):
        if not _presente(fields, campo):
            vereditos[campo] = Veredito(AUSENTE)
            continue
        valor = _valor(fields, campo)
        motivos = [*documento, *_regras_campo(fields, campo, tipo_documento)]
        if _dv_verificado(campo, valor):
            motivos.append("dv_verificado")
        if medir_precisao and modelo and campo != "conjuges":
            medida = roteamento.precisao(modelo, tipo_documento, campo)
            if medida is None or medida.precisao_residual is None:
                motivos.append("precisao_nao_medida")
            elif medida.precisao_residual < roteamento.LIMIAR_PRECISAO:
                motivos.append("precisao_medida_baixa")
            else:
                motivos.append("precisao_medida_ok")
        confirmado = (confirmados or {}).get(campo)
        if confirmado not in (None, "") and campo != "conjuges":
            if _mesmo_valor(campo, confirmado, valor):
                motivos.append("corroborado_outro_documento")
            else:
                motivos.append("diverge_de_valor_confirmado")
        vereditos[campo] = Veredito(_estado(motivos), tuple(motivos))
    return vereditos


def _estado(motivos: list[str]) -> str:
    duvidas = [m for m in motivos if m not in MOTIVOS_INFORMATIVOS]
    if not duvidas:
        return CONFIAVEL
    if all(m in MOTIVOS_SUAVES for m in duvidas) and (
        "corroborado_outro_documento" in motivos or "dv_verificado" in motivos
    ):
        return CONFIAVEL
    return DUVIDOSO


def calibrar(
    fields: IdentityFields,
    vereditos: Mapping[str, Veredito],
    *,
    excluir: tuple[str, ...] = (),
    original: Optional[IdentityFields] = None,
) -> IdentityFields:
    """Raise a gate-cleared, EVIDENCE-backed `baixa` field to `media`.

    WHY (deal 876 legal review, 2026-10-19): every vision-read `nome` / `rg`
    leaves the extractor at `baixa` BY CONSTRUCTION
    (`real._temper_name_confidence`: "a field with no structural
    self-evidence may not be written unattended off a transcription"), and
    nothing ever raised it again — not even when the trust gate below had
    just found the very self-evidence that rule says is missing. The legal
    review panel shows the document's stored confidence, so 5 of its 37
    rows on deal 876 were correct RG/CNH reads flagged "baixa": noise that
    trains the reviewer to ignore the flag the real low reads depend on.

    The rule — `media`, never `alta` (`ExtractionConfidence.MEDIA`'s
    "some evidence stronger than a bare guess", not "safe unattended"):

    - only a field whose `baixa` is the vision CAP, not a parser judgement
      (`_CONFIANCA_LIMITADA`: `nome`/`rg`/`rne` — the ones
      `_temper_name_confidence` demotes). A CALIBRATED parser's `baixa`
      (`_CONFIANCA_CALIBRADA`: an unlabelled CPF, which may be a parent's)
      IS the low-confidence signal and is never raised;
    - its verdict is `confiavel` (no HARD or SOFT doubt left standing);
    - AND it carries POSITIVE evidence (`MOTIVOS_EVIDENCIA`): a verified
      check digit, corroboration by another document, or a measured
      precision at/above the routing threshold.

    A `confiavel` verdict resting only on "nothing was measured" stays
    `baixa`; `nenhuma`/`media`/`alta` are never touched; a field in
    `excluir` (one a fallback read just reconciled — its confidence is
    `releitura.conciliar`'s to set) is left alone, and so is any field whose
    value no longer equals the read the verdicts judged (`original`, when
    the caller reconciled). Pure: returns a copy.
    """
    from noctusai_lib.integrations.documents.releitura import _mesmo_valor

    novos: dict[str, Any] = {}
    for campo, v in vereditos.items():
        if campo not in _CONFIANCA_LIMITADA or campo in excluir or v.estado != CONFIAVEL:
            continue
        if not MOTIVOS_EVIDENCIA.intersection(v.motivos):
            continue
        if original is not None and not _mesmo_valor(
            campo, getattr(fields, campo, None), getattr(original, campo, None)
        ):
            continue
        atributo = f"{campo}_confianca"
        if getattr(fields, atributo, None) is ExtractionConfidence.BAIXA:
            novos[atributo] = ExtractionConfidence.MEDIA
        if campo == "rg" and "dv_verificado" in v.motivos and _orgao_sp(fields):
            # The RG check digit EXISTS only for São Paulo (`identificador.
            # _RG_UFS_CONHECIDAS`): a verified one is the SP issuer's own
            # evidence, so the `.../SP` issuer read beside it rides along.
            novos["rg_orgao_confianca"] = ExtractionConfidence.MEDIA
    return replace(fields, **novos) if novos else fields


def _orgao_sp(fields: IdentityFields) -> bool:
    from noctusai_lib.integrations.documents.rg import separar_orgao_uf

    return (
        fields.rg_orgao_confianca is ExtractionConfidence.BAIXA
        and separar_orgao_uf(fields.rg_orgao)[1] == "SP"
    )


def impressao(campo: str, valor: Any) -> Optional[str]:
    """A 24-bit fingerprint of a field value (6 hex chars of SHA-256 over the
    field name + the value normalised the way the agreement gate compares
    it). Two readings of the same fact share it; the value cannot be read
    back from it — 24 bits over a 10^9-value space like the CPF leaves ~60
    candidates per fingerprint (no PII in the learning-loop rows), while two
    DIFFERENT readings of one field collide ~1 time in 16 million."""
    import hashlib

    from noctusai_lib.integrations.documents.name import chave_nome
    from noctusai_lib.integrations.documents.text import strip_accents_upper

    if valor in (None, "", (), []):
        return None
    if campo == "conjuges":
        texto = "|".join(sorted(chave_nome(c.nome) for c in valor if getattr(c, "nome", None)))
    elif hasattr(valor, "isoformat"):
        texto = valor.isoformat()
    elif campo in ("cpf", "matricula_certidao"):
        texto = re.sub(r"\D", "", str(valor))
    elif campo == "rg":
        # An RG with and without its check digit is the same RG.
        texto = re.sub(r"[^0-9X]", "", strip_accents_upper(str(valor)))[:8]
    elif campo == "rne":
        texto = re.sub(r"[^0-9A-Z]", "", strip_accents_upper(str(valor)))
    elif campo == "nome":
        texto = chave_nome(str(valor))
    else:
        texto = strip_accents_upper(str(valor)).strip()
    if not texto:
        return None
    return hashlib.sha256(f"{campo}:{texto}".encode()).hexdigest()[:6]


def criticos_duvidosos(
    vereditos: Mapping[str, Veredito],
    fields: IdentityFields,
    tipo_documento: Optional[str],
) -> tuple[str, ...]:
    """The critical fields that justify ONE fallback read: every critical
    field judged `duvidoso`.

    A MISSING core field is deliberately NOT a trigger (measured, real
    benchmark 2026-10-13, Sonnet 5 primary): with it, 12/12 RG reads paid a
    fallback for a CPF most RGs never print, and 20/39 certidão reads for
    spouses the parser did not resolve — while the candidate fallback model
    recovers a missing CNH CPF no better (Opus 5.5 CNH cpf accuracy 0.78 vs
    Sonnet 0.81). An absent field is not a wrong stored value: it already
    raises `campos_nucleo_ausentes` for a human. `fields`/`tipo_documento`
    stay in the signature for that future, data-backed rule.
    """
    del fields, tipo_documento
    criticos = set(campos_criticos())
    return tuple(c for c, v in vereditos.items() if c in criticos and v.duvidoso)


__all__ = [
    "AUSENTE",
    "AVISO_RESOLUCAO_REDUZIDA",
    "CAMPOS_INFORMATIVOS",
    "CONFIAVEL",
    "DUVIDOSO",
    "MOTIVOS_SUAVES",
    "MOTIVOS_EVIDENCIA",
    "Veredito",
    "avaliar",
    "calibrar",
    "campos_avaliados",
    "campos_criticos",
    "criticos_duvidosos",
    "impressao",
]
