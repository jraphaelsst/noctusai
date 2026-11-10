"""The exclusives showcase feed: One's exclusive listings, read from OUR mirror (`social_wiring.imoveis`), never Vista.

Selection (what the old static-site script published): Vista `Exclusivo = Sim` -- the `exclusivo` column, coerced by the
sync normalizer from the same `Exclusivo` key that `vista_raw` keeps --, listed on the site
(`ImovelSyncService._e_vitrine`: status in STATUS_VITRINE and `exibir_no_site` not false), and not removed in
`imovel_registry` (`ativo_no_vista=false` with `delistado_em`). Newest `data_cadastro` first.

The output carries PUBLIC listing fields only -- no broker, owner, street/number, phone or internal column. The set of keys
is pinned by `CAMPOS_SAIDA` (a test asserts the exact set), so a new mirror column can never leak by accident.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents_ascii

from app.services.imoveis_service import ImovelSyncService

_SCHEMA = "social_wiring"
DESC_MAX = 240
_PAGINA = 1000
_COLUNAS = (
    "codigo, titulo, categoria, status, cidade, bairro, uf, valor_venda, valor_locacao, valor_condominio, dormitorios, suites, "
    "vagas, area_privativa, area_total, foto_destaque, data_cadastro, descricao_web, exibir_no_site"
)
CAMPOS_SAIDA = frozenset({
    "codigo", "titulo", "categoria", "status", "cidade", "bairro", "valor_venda", "valor_locacao", "condominio", "dormitorios",
    "suites", "vagas", "area", "foto", "cadastro", "descricao", "url",
})


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold_accents_ascii(text).lower()).strip("-")


def normalize(row: dict, site_url: str) -> dict:
    """One mirror row -> one showcase card (same fields as the former static snapshot)."""
    dorms = int(_num(row.get("dormitorios")))
    area = _num(row.get("area_privativa")) or _num(row.get("area_total"))
    codigo = row["codigo"]
    slug = slugify("-".join(filter(None, [
        row.get("categoria"), row.get("bairro"), row.get("cidade"), (row.get("uf") or "sp").lower(),
        f"{dorms}-quartos" if dorms else "", f"{area:.0f}m2" if area else "",
    ])))
    desc = re.sub(r"\s+", " ", row.get("descricao_web") or "").strip()
    desc = re.sub(r"([.!?])(?=[A-ZÀ-Ý])", r"\1 ", desc)  # "fim.Começo" -> "fim. Começo"
    if len(desc) > DESC_MAX:
        desc = desc[:DESC_MAX].rsplit(" ", 1)[0] + "…"
    return {
        "codigo": codigo,
        "titulo": (row.get("titulo") or "").strip(),
        "categoria": row.get("categoria") or "",
        "status": row.get("status") or "",
        "cidade": row.get("cidade") or "",
        "bairro": row.get("bairro") or "",
        "valor_venda": _num(row.get("valor_venda")),
        "valor_locacao": _num(row.get("valor_locacao")),
        "condominio": _num(row.get("valor_condominio")),
        "dormitorios": dorms,
        "suites": int(_num(row.get("suites"))),
        "vagas": int(_num(row.get("vagas"))),
        "area": area,
        "foto": row.get("foto_destaque") or "",
        "cadastro": str(row.get("data_cadastro") or ""),
        "descricao": desc,
        "url": f"{site_url.rstrip('/')}/imovel/{slug}-{codigo}",
    }


class VitrineExclusivosService:
    def __init__(self, client: Any):
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def site_url(self, org_id: UUID) -> Optional[str]:
        """The org's opt-in row (active only); None = the org is not served."""
        rows = self._t("vitrine_exclusivos_orgs").select("site_url").eq("org_id", str(org_id)).eq("ativo", True).limit(1).execute().data or []
        return rows[0]["site_url"] if rows else None

    def _removidos(self, org_id: UUID) -> set[str]:
        saida: set[str] = set()
        inicio = 0
        while True:
            rows = (
                self._t("imovel_registry").select("codigo_canonical").eq("org_id", str(org_id)).eq("ativo_no_vista", False)
                .not_.is_("delistado_em", "null").range(inicio, inicio + _PAGINA - 1).execute().data or []
            )
            saida.update(r["codigo_canonical"] for r in rows)
            if len(rows) < _PAGINA:
                return saida
            inicio += _PAGINA

    def atualizado_em(self, org_id: UUID) -> Optional[str]:
        """Latest successful refresh of the org's mirror; else the newest `sincronizado_em`."""
        ok = (
            self._t("imoveis_sync_execucoes").select("finalizado_em").eq("org_id", str(org_id)).in_("status", ["ok", "incompleto"])
            .order("finalizado_em", desc=True).limit(1).execute().data or []
        )
        if ok and ok[0].get("finalizado_em"):
            return ok[0]["finalizado_em"]
        mirror = self._t("imoveis").select("sincronizado_em").eq("org_id", str(org_id)).order("sincronizado_em", desc=True).limit(1).execute().data or []
        return mirror[0].get("sincronizado_em") if mirror else None

    def exclusivos(self, org_id: UUID, site_url: str) -> list[dict]:
        removidos = self._removidos(org_id)
        linhas: list[dict] = []
        inicio = 0
        while True:
            rows = (
                self._t("imoveis").select(_COLUNAS).eq("org_id", str(org_id)).eq("exclusivo", True)
                .order("data_cadastro", desc=True).range(inicio, inicio + _PAGINA - 1).execute().data or []
            )
            linhas.extend(rows)
            if len(rows) < _PAGINA:
                break
            inicio += _PAGINA
        return [
            normalize(r, site_url) for r in linhas
            if r.get("codigo") and ImovelSyncService._e_vitrine(r) and r["codigo"].strip().upper() not in removidos
        ]
