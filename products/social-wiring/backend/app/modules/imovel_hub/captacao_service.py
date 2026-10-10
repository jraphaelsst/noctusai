"""Manual captação — an imóvel an agent registers by hand (migration 226,
sw-lead-to-contract CONTRACT §8).

WHERE THE DATA LIVES
--------------------
Identity: `imovel_registry` (`origem_descoberta='manual'`), written by the SAME
insert `dados_service.registrar_imovel` uses (`dados_service.inserir_registry`)
— never a second registration implementation. Listing data only a manual
imóvel has: `imovel_captacao` (column names IDENTICAL to `imoveis`, so one
serializer serves both). Address / empreendimento / em_condominio / deal refs:
`imovel_dados`. The Vista mirror `imoveis` is NEVER written: a manual row there
would force `_last_sync_at` to re-sync forever, be flipped by the sweep and be
overwritten by a later Vista listing of the same código.

CÓDIGO
------
`SW-NNNN`, generated, already uppercase (`busca_service.canonical`): next = max
existing `SW-n` in the org's registry + 1 (numeric, never lexicographic —
`SW-10000` sorts before `SW-9999`). Two requests can compute the same next; the
registry's unique `(org_id, codigo_canonical)` decides and the loser retries,
bounded, then fails LOUDLY.

PARTIAL FAILURE
---------------
Registry → captação → imovel_dados is three writes without a transaction (the
house shape). A failure after the registry row exists is reported as
`imovel_registro_incompleto` carrying the código, never swallowed;
`PATCH /manuais/{codigo}` on a manual código that has no captação row yet
creates it (upsert), so a retry with the returned código
converges.

NEVER AUTO-MERGED with a later Vista listing: matrícula/address stay on
`imovel_dados`, so a future "possível duplicado" hint stays buildable.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service as dados_svc
from app.services import table_reads

logger = logging.getLogger(__name__)

CAPTACAO_TABLE = "imovel_captacao"
REGISTRY_TABLE = dados_svc.REGISTRY_TABLE
PREFIXO_CODIGO = "SW-"
_CODIGO_RE = re.compile(r"^SW-(\d+)$")
MAX_TENTATIVAS_CODIGO = 5

#: The `imovel_captacao` columns a caller may set (everything but identity /
#: audit columns).
CAMPOS_CAPTACAO: tuple[str, ...] = (
    "titulo", "categoria", "status", "finalidades",
    "valor_venda", "valor_locacao", "valor_condominio", "valor_iptu",
    "area_total", "area_privativa", "area_construida",
    "dormitorios", "suites", "vagas",
    "descricao_web", "observacoes",
)

#: Every column of the Vista mirror `imoveis` (+ the generated `codigo_norm`):
#: a manual imóvel is serialized with EXACTLY these keys, nulls for what a
#: manual imóvel cannot have, so the FE never branches on a missing key. A test
#: pins this tuple against the migration-derived column set of `imoveis`.
MIRROR_COLUMNS: tuple[str, ...] = (
    "org_id", "codigo", "codigo_imobiliaria", "titulo", "categoria", "status",
    "finalidades", "cep", "logradouro", "numero", "complemento", "bairro",
    "cidade", "uf", "empreendimento", "latitude", "longitude",
    "valor_venda", "valor_locacao", "valor_condominio", "valor_iptu",
    "area_total", "area_privativa", "area_construida",
    "dormitorios", "suites", "vagas", "banheiro_social",
    "foto_destaque", "fotos", "corretores", "construtora",
    "data_cadastro", "data_atualizacao",
    "caracteristicas", "caracteristicas_raw", "vista_raw",
    "sincronizado_em", "created_at", "updated_at",
    "descricao_web", "observacoes",
    "ano_construcao", "situacao", "ocupacao", "pavimentos", "posicao",
    "elevador", "portaria", "exclusivo", "aceita_permuta",
    "aceita_financiamento", "destaque_web", "super_destaque_web",
    "exibir_no_site", "chave", "zona", "regiao",
    "area_terreno", "frente", "fundos", "closet",
    "referencia", "matricula_vista", "inscricao_municipal",
    "video_destaque", "tour_360",
    "codigo_norm",
)

#: The mirror's real `finalidades` vocabulary (lowercase; 2084 venda / 267
#: aluguel on prod). The FE derives it from `status`.
FINALIDADES_VALIDAS = frozenset({"venda", "aluguel"})


def validar_finalidades(valores: dict) -> None:
    """`finalidades ⊆ {"venda","aluguel"}` — 400 naming the field."""
    if "finalidades" not in valores:
        return
    invalidas = sorted(
        {str(f) for f in (valores["finalidades"] or []) if f not in FINALIDADES_VALIDAS}
    )
    if invalidas:
        raise ValidationError_(
            f"finalidades inválidas: {', '.join(invalidas)} (use venda e/ou aluguel)",
            field="finalidades",
        )


_ENDERECO_DE_DADOS = {
    "cep": "endereco_manual_cep",
    "logradouro": "endereco_manual_logradouro",
    "numero": "endereco_manual_numero",
    "complemento": "endereco_manual_complemento",
    "bairro": "endereco_manual_bairro",
    "cidade": "endereco_manual_cidade",
    "uf": "endereco_manual_uf",
}


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def formatar_codigo(numero: int) -> str:
    return f"{PREFIXO_CODIGO}{numero:04d}"


def proximo_numero(client: Any, org_id: UUID) -> int:
    """Max existing `SW-n` in the org's registry + 1 (1 when there is none).

    Paged (PostgREST caps a response at 1 000 rows silently) and compared
    NUMERICALLY in Python — a lexicographic max would hand out a duplicate
    once the sequence passes 9999.
    """
    rows = table_reads.paged_rows(
        client, REGISTRY_TABLE, org_id,
        order_col="codigo_canonical", id_key="codigo_canonical",
        select="codigo_canonical",
        refine=lambda q: q.ilike("codigo_canonical", f"{PREFIXO_CODIGO}%"),
    )
    maior = 0
    for row in rows:
        m = _CODIGO_RE.match(str(row.get("codigo_canonical") or ""))
        if m:
            maior = max(maior, int(m.group(1)))
    return maior + 1


# ─── reads ────────────────────────────────────────────────────────────────


def _um(client: Any, tabela: str, org_id: UUID, coluna: str, codigo: str) -> Optional[dict]:
    rows = (
        _t(client, tabela)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(coluna, codigo)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def captacao_da_linha(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    return _um(client, CAPTACAO_TABLE, org_id, "codigo_canonical", codigo)


def _dia(valor: Any) -> Optional[str]:
    return str(valor)[:10] if valor else None


def imovel_manual_out(registry: dict, captacao: Optional[dict], dados: Optional[dict]) -> dict:
    """The `Imovel` wire shape of a manual imóvel: every `imoveis` column
    (null/empty where a manual imóvel cannot have it — fotos, corretores,
    caracteristicas, publication flags, Vista ids), the mirror's two derived
    presentation keys, plus `fonte`, `referencias` and `em_condominio`."""
    dados = dados or {}
    # A REGISTRY-ONLY manual imóvel (the picker's typed-código registration)
    # has no captação row: the same shape, `titulo` and every listing field
    # null/empty, address/empreendimento from `imovel_dados`.
    captacao = captacao or {}
    out: dict = {coluna: None for coluna in MIRROR_COLUMNS}
    out.update(
        org_id=registry.get("org_id"),
        codigo=registry.get("codigo_display") or registry["codigo_canonical"],
        codigo_norm=registry["codigo_canonical"],
        fotos=[], corretores=[], caracteristicas=[],
        caracteristicas_raw={}, vista_raw={},
        finalidades=captacao.get("finalidades") or [],
        empreendimento=dados.get("empreendimento_manual"),
        data_cadastro=_dia(captacao.get("created_at") or registry.get("created_at")),
        data_atualizacao=_dia(
            captacao.get("updated_at") or registry.get("updated_at") or registry.get("created_at")
        ),
        created_at=captacao.get("created_at") or registry.get("created_at"),
        updated_at=captacao.get("updated_at") or registry.get("updated_at"),
    )
    for campo in CAMPOS_CAPTACAO:
        if campo != "finalidades":
            out[campo] = captacao.get(campo)
    for campo, coluna in _ENDERECO_DE_DADOS.items():
        out[campo] = dados.get(coluna)
    out.update(
        orientacao_solar=[],
        dias_desde_atualizacao=None,
        fonte="manual",
        em_condominio=dados.get("em_condominio"),
        referencias=dados_svc.referencias_da_linha(dados),
    )
    return out


def obter_manual(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    """The full `Imovel` for a manual código, or `None` when it is not one: a
    manual imóvel is a registry row with `origem_descoberta='manual'` (with or
    without a captação row) — a Vista imóvel, an unknown código or another
    org's row is `None`."""
    canonico = codigo.strip().upper()
    registry = _um(client, REGISTRY_TABLE, org_id, "codigo_canonical", canonico)
    if registry is None or registry.get("origem_descoberta") != "manual":
        return None
    captacao = captacao_da_linha(client, org_id, canonico)
    return imovel_manual_out(registry, captacao, dados_svc.linha(client, org_id, canonico))


# ─── writes ───────────────────────────────────────────────────────────────


def _captacao_patch(valores: dict, usuario_id: Optional[UUID]) -> dict:
    patch = {k: valores[k] for k in CAMPOS_CAPTACAO if k in valores}
    if "finalidades" in patch:
        patch["finalidades"] = list(patch["finalidades"] or [])
    patch["updated_por"] = str(usuario_id) if usuario_id else None
    patch["updated_at"] = dados_svc._now()
    return patch


def _inserir_captacao(
    client: Any, org_id: UUID, codigo: str, valores: dict, usuario_id: Optional[UUID]
) -> None:
    _t(client, CAPTACAO_TABLE).insert(
        {
            "org_id": str(org_id),
            "codigo_canonical": codigo,
            **{k: valores[k] for k in CAMPOS_CAPTACAO if k in valores},
            "finalidades": list(valores.get("finalidades") or []),
            "created_por": str(usuario_id) if usuario_id else None,
            "updated_por": str(usuario_id) if usuario_id else None,
        }
    ).execute()


def _escrever_dados(
    client: Any, org_id: UUID, codigo: str, valores: dict, usuario_id: Optional[UUID]
) -> None:
    """The `imovel_dados` half, through the existing authors only."""
    endereco = valores.get("endereco")
    if endereco:
        dados_svc.gravar_endereco_manual(
            client, org_id, codigo,
            valores={f"endereco_manual_{k}": v for k, v in endereco.items()},
            mirror={}, usuario_id=usuario_id,
        )
    extras = {}
    if "empreendimento" in valores:
        extras["empreendimento_manual"] = valores["empreendimento"]
    if "em_condominio" in valores:
        extras["em_condominio"] = valores["em_condominio"]
    if extras:
        dados_svc.atualizar(client, org_id, codigo, valores=extras, usuario_id=usuario_id)
    refs = {k: valores[k] for k in ("processo_atual_numero", "drive_folder_url") if k in valores}
    if refs:
        dados_svc.gravar_referencias(client, org_id, codigo, valores=refs)


def _incompleto(codigo: str, etapa: str, exc: Exception) -> AppException:
    logger.error("captacao manual: org write failed at %s for %s: %s", etapa, codigo, exc)
    return AppException(
        code="imovel_registro_incompleto",
        message=(
            f"O imóvel {codigo} foi registrado, mas a gravação falhou na etapa "
            f"'{etapa}'. Reenvie os dados para este código (editar imóvel) para concluir."
        ),
        status_code=500,
        details={"codigo": codigo, "etapa": etapa},
    )


def registrar_manual(
    client: Any, org_id: UUID, valores: dict, *, usuario_id: Optional[UUID]
) -> dict:
    """`POST /manuais`: registry (manual) → captação → imovel_dados.

    `valores` is the validated body as a dict (`endereco` nested). Drive link
    and every other input were validated by the caller's schema / by
    `parse_drive_folder_url` here BEFORE the first write, so known-bad input
    leaves nothing behind.
    """
    validar_finalidades(valores)
    if "drive_folder_url" in valores:
        dados_svc.parse_drive_folder_url(valores["drive_folder_url"])

    codigo = None
    for _ in range(MAX_TENTATIVAS_CODIGO):
        candidato = formatar_codigo(proximo_numero(client, org_id))
        try:
            dados_svc.inserir_registry(
                client, org_id, candidato, display=candidato, origem="manual"
            )
        except Exception as exc:  # noqa: BLE001 — re-raised unless it is the unique race
            if table_reads.is_unique_violation(exc):
                logger.warning("captacao manual: %s taken concurrently, retrying", candidato)
                continue
            raise
        codigo = candidato
        break
    if codigo is None:
        raise AppException(
            code="imovel_codigo_indisponivel",
            message="Não foi possível reservar um código para o imóvel. Tente novamente.",
            status_code=503,
            details={"tentativas": MAX_TENTATIVAS_CODIGO},
        )

    try:
        _inserir_captacao(client, org_id, codigo, valores, usuario_id)
    except Exception as exc:  # noqa: BLE001 — surfaced with the código
        raise _incompleto(codigo, "captacao", exc) from exc
    try:
        _escrever_dados(client, org_id, codigo, valores, usuario_id)
    except Exception as exc:  # noqa: BLE001 — surfaced with the código
        raise _incompleto(codigo, "dados", exc) from exc
    return obter_manual(client, org_id, codigo)


def _exigir_manual(client: Any, org_id: UUID, codigo: str) -> None:
    """404 unknown/other org; 409 `imovel_vista_somente_leitura` when the
    registry knows it through any path but 'manual' (a Vista mirror row is a
    read-only cache: Vista rejects writes on this key)."""
    registro = _um(client, REGISTRY_TABLE, org_id, "codigo_canonical", codigo)
    if registro is None:
        raise NotFoundError("Imóvel", codigo)
    if registro.get("origem_descoberta") != "manual":
        raise AppException(
            code="imovel_vista_somente_leitura",
            message=f"O imóvel {codigo} vem do catálogo Vista e é somente leitura.",
            status_code=409,
            details={"codigo": codigo},
        )


def atualizar_manual(
    client: Any, org_id: UUID, codigo: str, valores: dict, *, usuario_id: Optional[UUID]
) -> dict:
    """`PATCH /manuais/{codigo}`: partial update (absence = leave alone).

    A manual código that has NO captação row yet (a typed-código registration,
    or the leftover of a partially failed `POST /manuais`) gets one here
    (upsert); `titulo` is required on CREATE only."""
    canonico = codigo.strip().upper()
    _exigir_manual(client, org_id, canonico)
    validar_finalidades(valores)
    if "drive_folder_url" in valores:
        dados_svc.parse_drive_folder_url(valores["drive_folder_url"])

    existente = captacao_da_linha(client, org_id, canonico)
    if existente is None:
        _inserir_captacao(client, org_id, canonico, valores, usuario_id)
    else:
        patch = _captacao_patch(valores, usuario_id)
        _t(client, CAPTACAO_TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "codigo_canonical", canonico
        ).execute()
    _escrever_dados(client, org_id, canonico, valores, usuario_id)
    return obter_manual(client, org_id, canonico)
