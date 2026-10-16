"""Lais wave 12 -- Modelos (message templates, contract 14 / page-map 59.0 a4).

A modelo is a WhatsApp template the org drafts here and submits to Meta for approval. Body <= 1024 chars,
8 categories, a closed registry of 10 `{{parametro}}` placeholders (the ONLY ones a body may use; the ordered
list of those it does use is stored in `parametros` and is what a send fills positionally). Status
`rascunho -> enviado_meta -> aprovado | rejeitado`; only a draft or a rejected modelo is editable.

Everything here works on WAHA too (create / edit / preview / "Simule com exemplos"); only the submission to
Meta needs the Cloud transport and answers 409 `transporte_indisponivel` otherwise.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_transporte
from app.services.lais_transporte import Transporte

logger = logging.getLogger(__name__)

TABLE = "lais_modelos"
CORPO_MAX = 1024
NOME_MAX = 80

#: slug -> (label, Meta template category). Order = the page's category tabs.
CATEGORIAS: dict[str, tuple[str, str]] = {
    "administrativo": ("Administrativo", "UTILITY"),
    "campanha": ("Campanha", "MARKETING"),
    "cobranca": ("Cobrança", "UTILITY"),
    "documentacao": ("Documentação", "UTILITY"),
    "primeiro_contato": ("Primeiro contato", "MARKETING"),
    "reativacao": ("Reativação", "MARKETING"),
    "visita": ("Visita", "UTILITY"),
    "outros": ("Outros", "MARKETING"),
}

#: the 10-parameter registry: key -> (label, example value for "Simule com exemplos").
PARAMETROS: dict[str, tuple[str, str]] = {
    "nome_pessoa": ("Nome da pessoa", "Maria"),
    "nome_lais": ("Nome da Lais", "Julia"),
    "nome_imobiliaria": ("Nome da imobiliária", "Imobiliária Exemplo"),
    "mensagem": ("Mensagem", "Posso ajudar com mais alguma coisa?"),
    "data_visita": ("Data da visita", "20/10/2026"),
    "codigo_imovel": ("Código do imóvel", "AP0123"),
    "link_imovel": ("Link do imóvel", "https://exemplo.com.br/imovel/AP0123"),
    "nome_atendente": ("Nome do atendente", "Carlos"),
    "imovel_visita": ("Imóvel da visita", "Apartamento 3 dorm. no Centro"),
    "data_hora_visita": ("Data e horário da visita", "20/10/2026 às 15:00"),
}

STATUS = ("rascunho", "enviado_meta", "aprovado", "rejeitado")
EDITAVEIS = ("rascunho", "rejeitado")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalogo() -> dict[str, Any]:
    """What the page needs to draw its pickers: categories + the parameter registry."""
    return {
        "categorias": [{"slug": s, "label": v[0], "categoria_meta": v[1]} for s, v in CATEGORIAS.items()],
        "parametros": [{"chave": k, "label": v[0], "exemplo": v[1]} for k, v in PARAMETROS.items()],
        "corpo_max": CORPO_MAX,
    }


def extrair_parametros(corpo: str) -> list[str]:
    """Ordered, de-duplicated registry keys used by the body. An unknown placeholder is a 422."""
    chaves: list[str] = []
    for m in _PLACEHOLDER.finditer(corpo):
        chave = m.group(1)
        if chave not in PARAMETROS:
            raise AppException(
                "parametro_invalido", f"Parâmetro desconhecido: {{{{{chave}}}}}.", status_code=422,
                details={"parametro": chave, "validos": list(PARAMETROS)},
            )
        if chave not in chaves:
            chaves.append(chave)
    return chaves


def renderizar(corpo: str, valores: Optional[dict[str, str]] = None) -> str:
    """The body with every placeholder filled from `valores` (missing keys use the registry example)."""
    vals = {k: v[1] for k, v in PARAMETROS.items()}
    vals.update({k: str(v) for k, v in (valores or {}).items() if k in PARAMETROS})
    return _PLACEHOLDER.sub(lambda m: vals.get(m.group(1), m.group(0)), corpo)


def corpo_posicional(corpo: str) -> tuple[str, list[str]]:
    """Meta's positional form: `{{nome_pessoa}}` -> `{{1}}` by first appearance, plus that ordered key list."""
    chaves = extrair_parametros(corpo)
    return _PLACEHOLDER.sub(lambda m: "{{%d}}" % (chaves.index(m.group(1)) + 1), corpo), chaves


def nome_meta(modelo: dict[str, Any]) -> str:
    """The template name on Meta's side: stable, lowercase, unique per modelo."""
    return f"lais_{str(modelo['id']).replace('-', '')[:16]}"


def _validar(nome: Optional[str], categoria: Optional[str], corpo: Optional[str]) -> None:
    if nome is not None and not (1 <= len(nome.strip()) <= NOME_MAX):
        raise AppException("nome_invalido", f"O nome deve ter de 1 a {NOME_MAX} caracteres.", status_code=422)
    if categoria is not None and categoria not in CATEGORIAS:
        raise AppException("categoria_invalida", "Categoria desconhecida.", status_code=422,
                           details={"validas": list(CATEGORIAS)})
    if corpo is not None:
        if not (1 <= len(corpo.strip()) <= CORPO_MAX):
            raise AppException("corpo_invalido", f"O corpo deve ter de 1 a {CORPO_MAX} caracteres.", status_code=422)
        extrair_parametros(corpo)


def _nao_encontrado() -> AppException:
    return AppException("modelo_nao_encontrado", "Modelo não encontrado.", status_code=404)


def obter(db: Any, org_id: UUID | str, modelo_id: UUID | str) -> dict[str, Any]:
    rows = db.table(TABLE).select("*").eq("org_id", str(org_id)).eq("id", str(modelo_id)).limit(1).execute().data or []
    if not rows:
        raise _nao_encontrado()
    return rows[0]


def listar(db: Any, org_id: UUID | str, *, status: Optional[str] = None, categoria: Optional[str] = None) -> list[dict[str, Any]]:
    if status is not None and status not in STATUS:
        raise AppException("status_invalido", "Status desconhecido.", status_code=422, details={"validos": list(STATUS)})
    if categoria is not None and categoria not in CATEGORIAS:
        raise AppException("categoria_invalida", "Categoria desconhecida.", status_code=422)
    q = db.table(TABLE).select("*").eq("org_id", str(org_id))
    if status:
        q = q.eq("status", status)
    if categoria:
        q = q.eq("categoria", categoria)
    return sorted(q.limit(500).execute().data or [], key=lambda r: str(r.get("created_at") or ""), reverse=True)


def _nome_livre(db: Any, org_id: UUID | str, nome: str, ignorar: Optional[str] = None) -> None:
    for r in db.table(TABLE).select("id, nome").eq("org_id", str(org_id)).limit(1000).execute().data or []:
        if str(r["nome"]).strip().lower() == nome.strip().lower() and str(r["id"]) != str(ignorar):
            raise AppException("modelo_nome_duplicado", "Já existe um modelo com esse nome.", status_code=409)


def criar(db: Any, org_id: UUID | str, *, nome: str, categoria: str, corpo: str, user_id: Any = None) -> dict[str, Any]:
    _validar(nome, categoria, corpo)
    _nome_livre(db, org_id, nome)
    row = {
        "id": str(uuid4()), "org_id": str(org_id), "nome": nome.strip(), "categoria": categoria, "corpo": corpo.strip(),
        "parametros": extrair_parametros(corpo), "idioma": lais_transporte.IDIOMA_PADRAO, "status": "rascunho",
        "created_by": str(user_id) if user_id else None,
    }
    created = db.table(TABLE).insert(row).execute().data or []
    if not created:
        raise RuntimeError("lais: modelo insert returned no row")
    return created[0]


def atualizar(db: Any, org_id: UUID | str, modelo_id: UUID | str, patch: dict[str, Any]) -> dict[str, Any]:
    atual = obter(db, org_id, modelo_id)
    if atual["status"] not in EDITAVEIS:
        raise AppException(
            "modelo_nao_editavel", "Só modelos em rascunho ou rejeitados podem ser editados.", status_code=409,
        )
    campos = {k: v for k, v in patch.items() if k in ("nome", "categoria", "corpo") and v is not None}
    _validar(campos.get("nome"), campos.get("categoria"), campos.get("corpo"))
    if "nome" in campos:
        campos["nome"] = campos["nome"].strip()
        _nome_livre(db, org_id, campos["nome"], ignorar=str(modelo_id))
    if "corpo" in campos:
        campos["corpo"] = campos["corpo"].strip()
        campos["parametros"] = extrair_parametros(campos["corpo"])
    if campos:
        # an edit sends a rejected modelo back to the draft state
        campos.update(status="rascunho", motivo_rejeicao=None, meta_template_id=None, updated_at=_agora())
        db.table(TABLE).update(campos).eq("org_id", str(org_id)).eq("id", str(modelo_id)).execute()
    return obter(db, org_id, modelo_id)


def apagar(db: Any, org_id: UUID | str, modelo_id: UUID | str) -> None:
    obter(db, org_id, modelo_id)
    em_uso = db.table("lais_disparos").select("id").eq("org_id", str(org_id)).eq("modelo_id", str(modelo_id)).limit(1).execute().data
    if em_uso:
        raise AppException("modelo_em_uso", "Este modelo é usado por um disparo.", status_code=409)
    db.table(TABLE).delete().eq("org_id", str(org_id)).eq("id", str(modelo_id)).execute()


def preview(corpo: str, valores: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Live preview + "Simule com exemplos" (no persisted modelo needed)."""
    _validar(None, None, corpo)
    chaves = extrair_parametros(corpo)
    return {"texto": renderizar(corpo, valores), "parametros": chaves, "tamanho": len(corpo)}


async def enviar_para_aprovacao(
    db: Any, org_id: UUID | str, modelo_id: UUID | str, *, transporte: Transporte,
) -> dict[str, Any]:
    """Submit the modelo to Meta (Cloud only). The caller has already gated on the Cloud transport; a
    non-Cloud `transporte` still cannot get here because `WahaTransporte.submeter_modelo` refuses."""
    modelo = obter(db, org_id, modelo_id)
    if modelo["status"] not in EDITAVEIS:
        raise AppException(
            "modelo_ja_enviado", "Este modelo já foi enviado para aprovação.", status_code=409,
        )
    corpo, chaves = corpo_posicional(modelo["corpo"])
    exemplos = [PARAMETROS[c][1] for c in chaves]
    try:
        resp = await transporte.submeter_modelo(
            nome_meta(modelo), CATEGORIAS[modelo["categoria"]][1], corpo, exemplos, modelo.get("idioma") or lais_transporte.IDIOMA_PADRAO,
        )
    except lais_transporte.OperacaoRequerApiOficial as exc:
        raise lais_transporte.transporte_indisponivel() from exc
    db.table(TABLE).update({
        "status": "enviado_meta", "meta_template_id": str(resp.get("id") or ""), "motivo_rejeicao": None, "updated_at": _agora(),
    }).eq("org_id", str(org_id)).eq("id", str(modelo_id)).execute()
    return obter(db, org_id, modelo_id)


def registrar_resultado_meta(
    db: Any, org_id: UUID | str, modelo_id: UUID | str, *, aprovado: bool, motivo: Optional[str] = None,
) -> dict[str, Any]:
    """Meta's review verdict (called by the template-status webhook once the Cloud app is verified)."""
    modelo = obter(db, org_id, modelo_id)
    if modelo["status"] != "enviado_meta":
        raise AppException("modelo_nao_enviado", "O modelo não está aguardando a Meta.", status_code=409)
    db.table(TABLE).update({
        "status": "aprovado" if aprovado else "rejeitado",
        "motivo_rejeicao": None if aprovado else (motivo or "Rejeitado pela Meta."), "updated_at": _agora(),
    }).eq("org_id", str(org_id)).eq("id", str(modelo_id)).execute()
    return obter(db, org_id, modelo_id)


__all__ = [
    "CATEGORIAS", "CORPO_MAX", "PARAMETROS", "STATUS", "apagar", "atualizar", "catalogo", "corpo_posicional",
    "criar", "enviar_para_aprovacao", "extrair_parametros", "listar", "nome_meta", "obter", "preview",
    "registrar_resultado_meta", "renderizar",
]
