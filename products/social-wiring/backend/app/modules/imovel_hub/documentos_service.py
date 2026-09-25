"""Imóvel documents — the matrícula and the guia de IPTU (migration 075).

🔴 WHY THIS IS **NOT** A COPY OF `card_hub/documentos_service.py`
-----------------------------------------------------------------
The two look alike (upload → storage → row → signed URL → soft delete) and
they are deliberately not shared, because the half that dominates that file
does not apply here at all:

- **An access log — reversed by migration 109.** This module originally
  shipped WITHOUT one, on the claim that a matrícula is a public registry
  document about a property and has no personal data to log. That claim was
  wrong: a certidão de matrícula names every owner with CPF, estado civil,
  cônjuge and regime de bens. Once the contract flow started keeping and
  re-opening these PDFs routinely (`app.modules.matriculas`), the posture was
  aligned with 078/106: every CONTENT read (a minted signed URL) and every
  delete appends to `imovel_documento_acessos`, attributed to the user.
- **No LGPD category column, and the retention clock came late (111).** This
  module was written without a `retencao_ate` — 079's header explains why:
  offering a retention control with nothing logging its use would be a lying
  UI, and this surface had no access log until 109. Now that it does,
  migration 111 gives it one, resolved through the SAME `documento_retencao`
  two-tier policy `cliente`/`atendimento` use (`superficie="imovel"`),
  anchored at `envio` — a property has no single `closed_at` an `atendimento`
  can anchor to, so upload time is the only clock that makes sense here.
- **No `ativo` allow-list table.** The client-side type list is DATA so that
  enabling a withheld, sensitive type is a data change rather than a deploy.
  There is nothing sensitive to withhold here, so the type list is code
  (`TIPOS_DOCUMENTO`) — which also means adding "certidão negativa" is a
  tuple entry, not a seeded row.

What IS shared is the part that genuinely is one idea — the org-scoped paged
read and the actor-name resolution — via `app.services.table_reads`.

The size/mime limits ARE duplicated as values, and that is intentional: they
are policy for a DIFFERENT surface. A matrícula is a multi-page scanned PDF
and routinely larger than a photo of an ID, so the two ceilings must be free
to diverge without one silently dragging the other.

🔴 MIGRATION 118 — STRUCTURED FIELDS FOR THE CONTRACT'S IMÓVEL CND GROUP
--------------------------------------------------------------------------
The contract's certidões clause needs, for the imóvel side: the IPTU CND
(número + data de emissão + resultado), the condomínio debt certificate
(data de emissão + resultado) and the matrícula certidão's own emissão date
— all of which the office treats as stale past 30 days at signing. Two new
tipos (`cnd_iptu`, `cnd_condominio`) join the tuple below, and every
extraction-eligible tipo gains a SECOND, independent structured read
(`extrair_estrutura`) alongside whatever it already had:
`numero`/`emitida_em`/`validade_ate`/`resultado`/`inscricao_imobiliaria`,
each `origem`d `ia` or `manual` and, once a human looks at it,
`confirmado_por`/`confirmado_em`. It reuses the SAME LLM client and
credential-resolution seam `certidoes.service._analyze_estrutura_with_ai`
established — see `_analisar_estrutura` — extended with
`inscricao_imobiliaria`, which that seam never needed. Unlike the número-de-
matrícula job (`matricula_extracao_service`), there is no status/tentativas
lifecycle for it: it is a best-effort suggestion, not a due-diligence
record, and a failure logs its reason and leaves the row untouched rather
than parking it in a "processando" a sweep would need to recover.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.card_hub.proveniencia import fontes
from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub.deps import BUCKET
from app.services import documento_retencao, extracao_retentativa, table_reads
from app.services.documento_store import DocumentoStore, documento_base, now_iso, today

logger = logging.getLogger(__name__)

TABLE = "imovel_documentos"

#: The document types an imóvel accepts — derived from `proveniencia.
#: fontes.FONTES_REGISTRO` (contract-gate S1), the ONE catalog that also
#: backs `card_hub/identidade_extracao_service.py`'s own `TIPOS_*`. Order
#: preserved from that tuple's own declaration order, per migration 075's
#: note: the set will grow (certidão negativa, habite-se, convenção de
#: condomínio) and a CHECK constraint would make each addition a migration.
#: `cnd_iptu` / `cnd_condominio` joined in migration 118 — the contract's
#: imóvel CND group.
TIPOS_DOCUMENTO: tuple[str, ...] = tuple(
    f.tipo_documento for f in fontes.FONTES_REGISTRO if f.dominio == "imovel"
)

#: Which types are worth reading a número de matrícula off. Only the matrícula
#: itself — a guia de IPTU carries an inscrição imobiliária, a DIFFERENT
#: number that would be wrong in this column.
TIPOS_EXTRAIVEIS = frozenset(
    f.tipo_documento
    for f in fontes.FONTES.values()
    if f.dominio == "imovel" and "numero_matricula" in f.campos
)

#: Which types get the migration-118 structured read (`numero`/`emitida_em`/
#: `validade_ate`/`resultado`/`inscricao_imobiliaria`, per-tipo subset below).
#: Runs ALONGSIDE `TIPOS_EXTRAIVEIS`'s número-de-matrícula job for `matricula`
#: — two different questions asked of the same PDF, so two independent jobs.
TIPOS_ESTRUTURA_EXTRAIVEL = frozenset(
    f.tipo_documento
    for f in fontes.FONTES.values()
    if f.dominio == "imovel" and f.estrutura_extraivel
)

#: Which structured fields matter per tipo. The AI prompt asks for exactly
#: this subset — a model answering with extra keys must not smuggle a field
#: this tipo_documento never requested into the row (`_parse_json_estrutura`
#: filters on it too).
CAMPOS_ESTRUTURA_POR_TIPO: dict[str, tuple[str, ...]] = {
    "cnd_iptu": (
        "numero", "emitida_em", "validade_ate", "resultado",
        "inscricao_imobiliaria",
    ),
    "cnd_condominio": ("emitida_em", "resultado"),
    "guia_iptu": ("inscricao_imobiliaria",),
    # Only the certidão's OWN emissão date — its número de matrícula is a
    # different job (`matricula_extracao_service`, `TIPOS_EXTRAIVEIS` above).
    "matricula": ("emitida_em",),
}

#: The imóvel CND vocabulary — deliberately narrower than
#: `certidoes.registry.RESULTADO_VALUES` (no `nao_emitida`): every document
#: in `CAMPOS_ESTRUTURA_POR_TIPO` is one this module ALREADY HOLDS, so "not
#: yet emitted" cannot be this row's answer the way it can for a pending
#: InfoSimples consulta.
RESULTADO_VALUES: tuple[str, ...] = (
    "negativa", "positiva", "positiva_com_efeito_de_negativa",
)

#: `imovel_documentos.origem` — who last wrote the structured fields above.
#: Mirrors `certidao_resultados.resultado_origem`'s two write-only values
#: (migration 107); there is no `api` leg here, only `ia` and `manual`.
ORIGENS_ESTRUTURA: tuple[str, ...] = ("ia", "manual")

#: Vision pages the structured-fields read may bill. Unlike
#: `certidoes._extract_pdf_text`'s scheduler-driven `CERTIDAO_MAX_VISION_
#: PAGES=0`, this runs once per upload (never on a loop), and every tipo in
#: `TIPOS_ESTRUTURA_EXTRAIVEL` is a short document (a CND/guia is 1-3 pages,
#: not the 20-40-page matrícula scan `matricula_extracao_service` budgets
#: for) — so a small vision cap is affordable here.
MAX_VISION_PAGES_ESTRUTURA = 5

#: The certidões `GET /{codigo}/certidoes` surfaces — every tipo the imóvel
#: CND clause needs a date for. `guia_iptu` is excluded: it carries an
#: inscrição cadastral, not a resultado/emissão of its own.
CERTIDOES_TIPOS: tuple[str, ...] = ("cnd_iptu", "cnd_condominio", "matricula")

#: 40 MB. Higher than the client-document ceiling (25 MB) on purpose: a
#: certidão de matrícula with decades of averbações is routinely 20-40 pages
#: of scan, where an RG is one photo.
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp"}
)

#: 🔴 `acessos_table` is SET (migration 109). It was `None` until then, on a
#: claim this module now records as wrong — see the module docstring. A
#: matrícula names its owners with CPF and estado civil; every content read
#: and every delete is logged, same posture as `atendimento_documentos`.
STORE = DocumentoStore(
    table=TABLE,
    owner_col="codigo",
    prefixo="imoveis",
    bucket=BUCKET,
    tipos=TIPOS_DOCUMENTO,
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table="imovel_documento_acessos",
)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        **documento_base(row, resolved),
        "codigo": row["codigo"],
        # Extraction state, surfaced so the UI can show "lendo…" / "não
        # encontrei um número" rather than an empty field that looks broken.
        "extracao_status": row.get("extracao_status"),
        "extracao_matricula": row.get("extracao_matricula"),
        "extracao_confianca": row.get("extracao_confianca"),
        "extracao_rotulo": row.get("extracao_rotulo"),
        "extracao_erro": row.get("extracao_erro"),
        # Migration 118 — the structured CND/guia/matrícula fields.
        "numero": row.get("numero"),
        "emitida_em": row.get("emitida_em"),
        "validade_ate": row.get("validade_ate"),
        "resultado": row.get("resultado"),
        "inscricao_imobiliaria": row.get("inscricao_imobiliaria"),
        "origem": row.get("origem"),
        "confirmado_por": table_reads.actor(resolved, row.get("confirmado_por")),
        "confirmado_em": row.get("confirmado_em"),
    }


def listar(client: Any, org_id: UUID, codigo: str) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    rows = STORE.listar_linhas(client, org_id, codigo)
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in rows if r.get("enviado_por")}
        | {r["confirmado_por"] for r in rows if r.get("confirmado_por")}
    )
    items = [_documento_out(r, resolved) for r in rows]
    return {"items": items, "total": len(items)}


def validar_upload(
    *,
    tipo_documento: str,
    content_type: str,
    tamanho_bytes: int,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> None:
    """Refuse an upload we will not store, naming the limit it hit.

    Thin alias over the store's own validator, kept so this module's tests and
    callers read in its own vocabulary. `max_bytes` is a parameter so no test
    has to monkeypatch the constant — see `DocumentoStore.validar`.
    """
    STORE.validar(
        tipo_documento=tipo_documento,
        content_type=content_type,
        tamanho_bytes=tamanho_bytes,
        max_bytes=max_bytes,
    )


def deve_extrair(tipo_documento: str) -> bool:
    return tipo_documento in TIPOS_EXTRAIVEIS


def deve_extrair_estrutura(tipo_documento: str) -> bool:
    """Does this tipo get the migration-118 structured read?"""
    return tipo_documento in TIPOS_ESTRUTURA_EXTRAIVEL


async def upload(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    # 🔴 Stamped at UPLOAD (migration 111) — same anchor `cliente_documentos`
    # uses and for the same reason: there is no deal-level `closed_at` a
    # standalone matrícula upload can anchor to. `None` when there is no
    # policy row OR the policy says keep indefinitely — both read the same
    # way to the sweep ("does not expire").
    dias = documento_retencao.dias_para(client, org_id, "imovel", tipo_documento)
    retencao_ate = (today() + timedelta(days=dias)).isoformat() if dias else None
    row = await STORE.guardar(
        client,
        storage,
        org_id,
        codigo,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=enviado_por,
        extra={
            # Queued the moment it lands. `pendente` is set HERE rather than
            # by the background job so a job that never starts — worker died,
            # process recycled mid-request — is visibly waiting instead of
            # invisibly lost, and the sweeper can find it.
            "extracao_status": "pendente" if deve_extrair(tipo_documento) else None,
            "extracao_tentativas": 0,
            # Migration 154 — the structured read gets the same lifecycle
            # (D3): `pendente` at upload so a job that never ran is visible
            # and the sweep can find it.
            "estrutura_status": "pendente" if deve_extrair_estrutura(tipo_documento) else None,
            "estrutura_tentativas": 0,
            "retencao_ate": retencao_ate,
        },
    )
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


async def url_do_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> dict:
    """A short-TTL signed URL. Minted per request, never stored.

    Appends a `view` to `imovel_documento_acessos` attributed to `usuario_id`
    (migration 109 — see the module docstring for why this surface is logged).
    """
    return await STORE.url(
        client, storage, org_id, codigo, documento_id, usuario_id=usuario_id
    )


def remover(
    client: Any,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID] = None,
) -> None:
    """Soft delete.

    🔴 The imóvel's `numero_matricula` is deliberately NOT cleared, even when
    the deleted document is the one it was read off. The number is a fact
    about the property that happens to have been sourced here; the document is
    evidence. Removing the evidence does not un-know the fact, and silently
    blanking a field the user did not ask to blank is the kind of cascade that
    loses data nobody agreed to lose.

    `numero_matricula_documento_id` keeps pointing at the soft-deleted row, so
    the provenance stays readable.
    """
    STORE.remover(
        client, org_id, codigo, documento_id, motivo=motivo, usuario_id=usuario_id
    )


def listar_acessos(client: Any, org_id: UUID, codigo: str, documento_id: UUID) -> dict:
    """The LGPD access log for one imóvel document (migration 109/111).

    Mirrors `card_hub.documentos_service.list_acessos` / `.listar_acessos`
    (financiamento): actor names resolved, not raw ids, and readable even for
    a soft-deleted document — soft delete is not erasure, so its own `delete`
    entry (and everything before it) must stay visible.

    A lighter existence check than `STORE.exigir` — that one 404s a
    soft-deleted document, which would make its own delete entry unreachable
    through this route.
    """
    existe = (
        table_reads.table(client, TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not existe:
        raise NotFoundError(TABLE, str(documento_id))

    rows = STORE.listar_acessos(client, org_id, documento_id)
    resolved = table_reads.resolve_actors(
        {r["usuario_id"] for r in rows if r.get("usuario_id")}
    )
    items = [
        {
            "id": r["id"],
            "acao": r["acao"],
            "usuario": table_reads.actor(resolved, r.get("usuario_id")),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


# ─── Structured extraction (migration 118) ─────────────────────────────


def _marcar(client: Any, documento_id: UUID, **updates: Any) -> None:
    _t(client, TABLE).update(updates).eq("id", str(documento_id)).execute()


class EstruturaFalhou(Exception):
    """The structured read FAILED (provider unreachable, no key, call error)
    — as opposed to reading fine and finding nothing. Only a failure is
    `erro` and retried (D3); "nothing found" is `sem_dados`, terminal.

    `codigo` is the machine code `extracao_retentativa.retentavel` judges."""

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo


_DESCRICAO_CAMPO: dict[str, str] = {
    "numero": "numero (string ou null) - o numero de controle/protocolo do documento",
    "emitida_em": (
        "emitida_em (formato YYYY-MM-DD ou null) - data de emissao impressa "
        "no documento"
    ),
    "validade_ate": (
        "validade_ate (formato YYYY-MM-DD ou null) - data de validade "
        "impressa no documento, quando houver"
    ),
    "resultado": (
        "resultado (um destes valores exatos: negativa, positiva, "
        "positiva_com_efeito_de_negativa - ou null se nao for possivel "
        "determinar com confianca)"
    ),
    "inscricao_imobiliaria": (
        "inscricao_imobiliaria (string ou null) - o numero de inscricao "
        "cadastral do imovel junto a prefeitura"
    ),
}


def _prompt_estrutura(campos: tuple[str, ...]) -> str:
    itens = "; ".join(_DESCRICAO_CAMPO[c] for c in campos)
    return (
        "Voce e um analista imobiliario. Leia este documento e responda "
        "APENAS com um JSON (sem markdown, sem texto adicional) com estas "
        f"chaves: {itens}."
    )


def _data_valida(value: Any) -> bool:
    """Is `value` a well-formed `YYYY-MM-DD`? Sanitizes an LLM's JSON answer
    before it reaches a `DATE` column — mirrors `certidoes.service.
    _is_iso_date`."""
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_json_estrutura(raw: Optional[str], campos: tuple[str, ...]) -> Optional[dict]:
    """Defensive JSON parse of the structured-fields prompt's answer.

    Mirrors `certidoes.service._parse_json_resultado`'s posture: fenced
    markdown is stripped before parsing, and any field outside `campos` or
    the closed vocabularies (`RESULTADO_VALUES`, ISO dates) is DROPPED
    rather than written — a malformed AI answer must never reach the
    database looking confident. Only keys the caller actually asked for are
    kept, so a model answering with extra keys cannot smuggle a field this
    tipo_documento never requested into the row.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        logger.warning(
            "extracao estrutura: resposta da IA nao e JSON valido: %r", raw[:200]
        )
        return None
    if not isinstance(parsed, dict):
        return None

    out: dict = {}
    if "numero" in campos:
        valor = parsed.get("numero")
        if isinstance(valor, str) and valor.strip():
            out["numero"] = valor.strip()
    for campo in ("emitida_em", "validade_ate"):
        if campo in campos and _data_valida(parsed.get(campo)):
            out[campo] = parsed[campo]
    if "resultado" in campos and parsed.get("resultado") in RESULTADO_VALUES:
        out["resultado"] = parsed["resultado"]
    if "inscricao_imobiliaria" in campos:
        valor = parsed.get("inscricao_imobiliaria")
        if isinstance(valor, str) and valor.strip():
            out["inscricao_imobiliaria"] = valor.strip()
    return out or None


async def _analisar_estrutura(
    texto: str, tipo_documento: str, org_id: Optional[str]
) -> Optional[dict]:
    """Ask the seed `chat_completion` wrapper for this tipo's structured
    fields — numero/emitida_em/validade_ate/resultado/inscricao_imobiliaria,
    per `CAMPOS_ESTRUTURA_POR_TIPO`.

    🔴 REUSES THE SEAM `certidoes.service._analyze_estrutura_with_ai`
    established, extended with `inscricao_imobiliaria` (which that seam has
    no reason to ask for) — the SAME `chat_completion` client, the SAME
    credential resolution (`resolve_chat_provider` → `resolve_key` →
    `provider_api_key`), the SAME model table. Imported lazily so importing
    this module never drags in `certidoes.service`'s heavier dependencies
    (httpx, xhtml2pdf) — the same reason `matricula_extracao_service` lazy-
    imports its own real extractor.

    Never raises: every failure (unreadable provider setting, no key
    configured, the call itself failing) is logged and returns `None`, same
    posture as the seam it reuses — this runs detached from the upload
    request, and an exception here would surface nowhere.
    """
    campos = CAMPOS_ESTRUTURA_POR_TIPO.get(tipo_documento)
    if not campos:
        return None

    from app.modules.certidoes.credentials import provider_api_key, resolve_key
    from app.modules.certidoes.service import ANALYSIS_MODELS, DEFAULT_ANALYSIS_PROVIDER
    from app.services.api_keys_store import resolve_chat_provider

    try:
        provider = resolve_chat_provider(org_id)
    except Exception as exc:  # noqa: BLE001 - surfaced as a recorded erro
        logger.error(
            "extracao estrutura: nao foi possivel ler o provedor de IA para "
            "org=%s: %s",
            org_id, exc,
        )
        raise EstruturaFalhou("provider_setting", str(exc)) from exc

    modelo = ANALYSIS_MODELS.get(provider, ANALYSIS_MODELS[DEFAULT_ANALYSIS_PROVIDER])
    api_key = resolve_key(provider_api_key(provider), org_id)
    if not api_key:
        logger.warning(
            "extracao estrutura: %s nao configurada (provedor selecionado)",
            provider_api_key(provider),
        )
        raise EstruturaFalhou(
            "missing_credentials", f"{provider_api_key(provider)} nao configurada"
        )

    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": _prompt_estrutura(campos)},
                {"role": "user", "content": texto},
            ],
            model=modelo,
            provider=provider,
            org_id=org_id,
            max_tokens=300,
        )
    except Exception as e:  # noqa: BLE001 - surfaced as a recorded erro
        logger.error("extracao estrutura: chamada de IA falhou: %s", e)
        raise EstruturaFalhou("chat_failed", str(e)) from e

    return _parse_json_estrutura(raw, campos)


async def _extrair_texto(
    conteudo: bytes, mimetype: Optional[str], org_id: Optional[str]
) -> Optional[str]:
    """Bytes → text, via the seed transcription ladder (`noctusai_lib.
    integrations.documents.make_document_transcriber`) — the "seed documents
    pipeline" half of the reused seam. Text-layer first, vision second, up to
    `MAX_VISION_PAGES_ESTRUTURA` pages.

    Never raises: a failed or empty transcription returns `None`, logged.
    """
    try:
        from noctusai_lib.integrations.documents import make_document_transcriber

        from app.services.api_keys_store import resolve_vision_provider

        provider = (
            resolve_vision_provider(org_id)
            if MAX_VISION_PAGES_ESTRUTURA > 0
            else None
        )
        transcriber = make_document_transcriber(
            real=True,
            org_id=org_id,
            max_vision_pages=MAX_VISION_PAGES_ESTRUTURA,
            provider=provider,
        )
        resultado = await transcriber.transcribe(
            conteudo, mimetype=mimetype or "application/pdf"
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a recorded erro
        logger.warning("extracao estrutura: leitura de texto falhou: %s", exc)
        raise EstruturaFalhou("transcription_exception", str(exc)) from exc
    if not resultado.ok:
        # A transcription that FAILED (no credits, rate limit, corrupt PDF)
        # is not "the document has no text" — the code says which, and
        # decides whether the sweep retries it.
        raise EstruturaFalhou(
            resultado.error or "transcription_failed", resultado.error_message or ""
        )
    return resultado.text or None


#: tipo → (structured field, `imovel_dados` field it feeds under D1). The
#: guia de IPTU and the CND de IPTU both print the inscrição cadastral; if
#: they disagree with each other (or with the matrícula's CADASTRO MUNICIPAL
#: block), that is a real discrepancy and becomes a conflict for a human —
#: which is why both may feed the field now that D1 never overwrites.
_ALIMENTA_IMOVEL_DADOS: dict[str, tuple[str, str]] = {
    "guia_iptu": ("inscricao_imobiliaria", "prefeitura_cadastro_imobiliario"),
    "cnd_iptu": ("inscricao_imobiliaria", "prefeitura_cadastro_imobiliario"),
}


def _preencher_onus_certidao_em(
    client: Any, org_id: UUID, codigo: str, emitida_em: str
) -> bool:
    """A matrícula certidão's own emissão date → `imovel_dados.
    onus_certidao_em`, EMPTY column only. Not a D1 field (it has no
    provenance columns and is not in the contract's validation set) — the
    certidão date the contract gate checks is the document's own
    `emitida_em`, which the certidões rollup reads directly."""
    atual = dados_service.linha(client, org_id, codigo)
    if atual and atual.get("onus_certidao_em"):
        return False
    dados_service.atualizar(
        client, org_id, codigo, valores={"onus_certidao_em": emitida_em}, usuario_id=None
    )
    return True


async def extrair_estrutura(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    extract_text: Optional[Any] = None,
    analyze_estrutura: Optional[Any] = None,
    notificador: Optional[Any] = None,
) -> dict:
    """Read numero/emitida_em/validade_ate/resultado/inscricao_imobiliaria
    off a CND/guia/matrícula upload, and feed `imovel_dados` (migration 118).

    NEVER raises — this runs detached from the upload request.

    LIFECYCLE (migration 154, D3). `estrutura_status` moves `pendente` →
    `processando` → `ok` | `sem_dados` | `erro` | `ignorado`, and
    `estrutura_tentativas` counts attempts. Only `erro` (a FAILED read — see
    `EstruturaFalhou`) is retried by `varrer_estrutura_pendentes`, at most
    twice; `sem_dados` (read fine, nothing there) is terminal.

    🔴 A HUMAN'S CONFIRMATION IS NEVER OVERWRITTEN. `origem == "manual"` (or
    a non-null `confirmado_por`) means a human already reviewed this
    document's fields — a retry must never silently override that.

    🔴 `imovel_dados` IS FED ONLY THROUGH D1 (`campos_extraidos_service.
    aplicar`): the inscrição fills an empty `prefeitura_cadastro_imobiliario`
    (origem = this document's tipo) or opens a conflict — never an
    overwrite, and never stamped as if a human had typed it.

    `extract_text` / `analyze_estrutura` are DI seams (default: the real
    `_extrair_texto` / `_analisar_estrutura`) — a test injects a stub instead
    of patching this module's own functions. A seam signals FAILURE by
    raising `EstruturaFalhou`, and "nothing found" by returning None.
    → KB § PATTERNS/backend/di-test-seam.md
    """
    from app.modules.imovel_hub import campos_extraidos_service as campos_svc

    extract_text = extract_text or _extrair_texto
    analyze_estrutura = analyze_estrutura or _analisar_estrutura

    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        logger.warning(
            "extracao estrutura: documento %s not found for org %s",
            documento_id, org_id,
        )
        return {"status": "erro", "erro": "documento_nao_encontrado"}

    doc = rows[0]
    if doc.get("deleted_at"):
        return {"status": "erro", "erro": "documento_removido"}
    tipo = doc["tipo_documento"]
    if not deve_extrair_estrutura(tipo):
        return {"status": "erro", "erro": "tipo_nao_extraivel"}
    if doc.get("origem") == "manual" or doc.get("confirmado_por"):
        _marcar(client, documento_id, estrutura_status="ignorado", estrutura_em=now_iso())
        return {"status": "ignorado", "erro": "confirmado_manualmente"}

    tentativas = int(doc.get("estrutura_tentativas") or 0) + 1
    _marcar(
        client,
        documento_id,
        estrutura_status="processando",
        estrutura_tentativas=tentativas,
        estrutura_em=now_iso(),
    )

    def _falhou(codigo_erro: str, mensagem: str) -> dict:
        _marcar(
            client,
            documento_id,
            estrutura_status="erro",
            estrutura_erro=f"{codigo_erro}: {mensagem}".strip(": "),
            estrutura_em=now_iso(),
        )
        return {"status": "erro", "erro": codigo_erro, "tentativas": tentativas}

    try:
        blob = await storage.get(bucket=BUCKET, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.warning(
            "extracao estrutura %s: storage read failed: %s", documento_id, exc
        )
        return {**_falhou("storage", str(exc)), "erro": "storage"}
    if blob is None:
        logger.warning(
            "extracao estrutura %s: objeto ausente no storage", documento_id
        )
        return _falhou("objeto_ausente", "objeto ausente no storage")

    try:
        texto = await extract_text(blob.data, doc.get("mime_type"), str(org_id))
        via_ia = await analyze_estrutura(texto, tipo, str(org_id)) if texto else None
    except EstruturaFalhou as falha:
        return _falhou(falha.codigo, str(falha).split(": ", 1)[-1])
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.error(
            "extracao estrutura %s: unexpected failure: %s", documento_id, exc, exc_info=True
        )
        return _falhou("erro_inesperado", str(exc))

    if not texto:
        logger.info("extracao estrutura %s: sem texto legivel", documento_id)
        _marcar(
            client, documento_id,
            estrutura_status="sem_dados", estrutura_erro=None, estrutura_em=now_iso(),
        )
        return {"status": "sem_dados", "erro": "sem_texto"}
    if not via_ia:
        _marcar(
            client, documento_id,
            estrutura_status="sem_dados", estrutura_erro=None, estrutura_em=now_iso(),
        )
        return {"status": "sem_dados"}

    _marcar(
        client,
        documento_id,
        **via_ia,
        origem="ia",
        estrutura_status="ok",
        estrutura_erro=None,
        estrutura_em=now_iso(),
    )

    sugerido = False
    conflitos: list[dict] = []
    try:
        alimenta = _ALIMENTA_IMOVEL_DADOS.get(tipo)
        if alimenta and via_ia.get(alimenta[0]):
            resultado = campos_svc.aplicar(
                client,
                org_id,
                codigo,
                alimenta[1],
                via_ia[alimenta[0]],
                origem=tipo,
                documento_id=documento_id,
                fonte_tabela=campos_svc.FONTE_DOCUMENTOS,
                fonte_id=documento_id,
            )
            sugerido = resultado.preenchido
            if resultado.conflito is not None:
                conflitos.append(resultado.conflito)
        if tipo == "matricula" and via_ia.get("emitida_em"):
            sugerido = _preencher_onus_certidao_em(
                client, org_id, codigo, via_ia["emitida_em"]
            ) or sugerido
    except Exception as exc:  # noqa: BLE001 - the read itself is recorded above
        logger.error(
            "extracao estrutura %s: read recorded but imovel_dados not fed: %s",
            documento_id, exc, exc_info=True,
        )
    await campos_svc.notificar(client, org_id, codigo, conflitos, notificador)

    return {
        "status": "ok",
        "campos": sorted(via_ia),
        "sugerido_em_dados": sugerido,
        "conflito_aberto": bool(conflitos),
        "tentativas": tentativas,
    }


#: A read stuck in a non-terminal state longer than this was orphaned by a
#: process that died — the same 20 minutes the número read uses.
ESTRUTURA_STALE_APOS = timedelta(minutes=20)


#: NOC-REMEDIATE[dry-extracao-varredura]: same shape as `matricula_
#: extracao_service.varrer_pendentes` — see that function's own marker
#: (S2 contract §E3.3) — 2026-09-25.
async def varrer_estrutura_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    notificador: Optional[Any] = None,
    extract_text: Optional[Any] = None,
    analyze_estrutura: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    """Re-run structured reads that never finished, and retry FAILED ones —
    at most `extracao_retentativa.MAX_RETENTATIVAS` times (D3), then leave
    them `erro` for a human. Called from the imovel_hub hourly sweep.
    `extract_text`/`analyze_estrutura` pass straight to `extrair_estrutura`
    (its DI seams; None = the real ones)."""
    cutoff = (datetime.now(timezone.utc) - ESTRUTURA_STALE_APOS).isoformat()
    base = lambda: (  # noqa: E731 - three variants of one bounded select
        _t(client, TABLE).select("*").is_("deleted_at", "null")
    )
    # postgrest-unbounded-ok: every variant carries `.limit(limite)`.
    presos = (
        base().in_("estrutura_status", ["pendente", "processando"])
        .lt("estrutura_em", cutoff).limit(limite).execute()
    ).data or []
    nunca = (
        base().eq("estrutura_status", "pendente").is_("estrutura_em", "null")
        .limit(limite).execute()
    ).data or []
    falhos = [
        r
        for r in (
            base().eq("estrutura_status", "erro")
            .lt("estrutura_tentativas", extracao_retentativa.MAX_TENTATIVAS)
            .lt("estrutura_em", cutoff).limit(limite).execute()
        ).data or []
        if extracao_retentativa.retentavel(
            extracao_retentativa.codigo_de_erro(r.get("estrutura_erro"))
        )
    ]

    vistos: set[str] = set()
    reprocessados = desistidos = 0
    for row in [*presos, *nunca, *falhos]:
        if row["id"] in vistos:
            continue
        vistos.add(row["id"])
        if int(row.get("estrutura_tentativas") or 0) >= extracao_retentativa.MAX_TENTATIVAS:
            _marcar(
                client,
                UUID(str(row["id"])),
                estrutura_status="erro",
                estrutura_erro=(
                    f"desistiu apos {extracao_retentativa.MAX_TENTATIVAS} tentativas"
                ),
                estrutura_em=now_iso(),
            )
            desistidos += 1
            continue
        await extrair_estrutura(
            client,
            storage,
            UUID(str(row["org_id"])),
            row["codigo"],
            UUID(str(row["id"])),
            notificador=notificador,
            extract_text=extract_text,
            analyze_estrutura=analyze_estrutura,
        )
        reprocessados += 1
    return {"encontrados": len(vistos), "reprocessados": reprocessados, "desistidos": desistidos}


def confirmar_extracao(
    client: Any,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    """`PATCH /{codigo}/documentos/{documento_id}/extracao` — the operator
    confirms or corrects the structured extraction (migration 118).

    Always stamps `origem="manual"` + `confirmado_por`/`confirmado_em`, even
    when `valores` is empty — a pure "I reviewed this and it is correct" is a
    confirmation too, and it is what LOCKS the row against `extrair_estrutura`
    ever overwriting it on a later retry (mirrors `certidoes.service.
    confirmar_resultado`'s reasoning for the same lock).
    """
    dados_service.ensure_imovel(client, org_id, codigo)
    doc = STORE.exigir(client, org_id, codigo, documento_id)

    campos = CAMPOS_ESTRUTURA_POR_TIPO.get(doc["tipo_documento"], ())
    recusados = sorted(set(valores) - set(campos))
    if recusados:
        raise ValidationError_(
            f"Campos não aplicáveis a {doc['tipo_documento']}: "
            f"{', '.join(recusados)}",
            field=recusados[0],
        )

    patch = {
        **{
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in valores.items()
        },
        "origem": "manual",
        "confirmado_por": str(usuario_id) if usuario_id else None,
        "confirmado_em": now_iso(),
    }
    _marcar(client, documento_id, **patch)

    row = {**doc, **patch}
    resolved = table_reads.resolve_actors({usuario_id} if usuario_id else set())
    return _documento_out(row, resolved)


def certidoes(client: Any, org_id: UUID, codigo: str) -> dict:
    """`GET /{codigo}/certidoes` — the latest structured read per tipo, for
    the contract's imóvel CND clause (IPTU CND, condomínio, and the
    matrícula certidão's own emissão date) — all of it in one call so the
    office's 30-day-old rule can be checked without opening each document.
    """
    dados_service.ensure_imovel(client, org_id, codigo)
    rows = STORE.listar_linhas(client, org_id, codigo)  # already newest-first

    por_tipo: dict[str, dict] = {}
    for row in rows:
        tipo = row["tipo_documento"]
        if tipo in CERTIDOES_TIPOS and tipo not in por_tipo:
            por_tipo[tipo] = row

    items = [
        {
            "tipo": tipo,
            "documento_id": row["id"],
            "numero": row.get("numero"),
            "emitida_em": row.get("emitida_em"),
            "validade_ate": row.get("validade_ate"),
            "resultado": row.get("resultado"),
            "inscricao_imobiliaria": row.get("inscricao_imobiliaria"),
            "confirmado": row.get("origem") == "manual" or bool(row.get("confirmado_por")),
        }
        for tipo in CERTIDOES_TIPOS
        for row in [por_tipo.get(tipo)]
        if row is not None
    ]
    return {"items": items, "total": len(items)}


__all__ = [
    "ALLOWED_MIME_TYPES",
    "CAMPOS_ESTRUTURA_POR_TIPO",
    "CERTIDOES_TIPOS",
    "MAX_UPLOAD_BYTES",
    "ORIGENS_ESTRUTURA",
    "RESULTADO_VALUES",
    "TABLE",
    "TIPOS_DOCUMENTO",
    "TIPOS_ESTRUTURA_EXTRAIVEL",
    "TIPOS_EXTRAIVEIS",
    "certidoes",
    "confirmar_extracao",
    "deve_extrair",
    "deve_extrair_estrutura",
    "EstruturaFalhou",
    "extrair_estrutura",
    "varrer_estrutura_pendentes",
    "validar_upload",
    "listar",
    "listar_acessos",
    "remover",
    "upload",
    "url_do_documento",
]
