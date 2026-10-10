"""Campanhas CRUD — which Meta objects (and which imóveis) a campanha names.

sw-lead-to-contract CONTRACT §1.1. Fills mig 065's `campanhas` /
`campanha_imoveis` / `campanha_veiculacoes` (+ mig 218's `nivel`,
`deleted_at`). Intake (`meta_ingest_service`, §1.2) then resolves a lead's
ad / adset / campaign / form id to the campanha's imóveis.

Rules that carry the weight:
  · imóvel códigos resolve through `CampanhasService.resolve_imovel_ref` (the
    one registry normalizer). An unknown código is reported, never created,
    never dropped.
  · One Meta object resolves to ONE campanha per org (unique index
    `campanha_veiculacoes_meta_ref_unico`) — checked up front to NAME the
    other campanha, and the index stays the real guard against a race.
  · DELETE is soft AND drops the veiculacoes: a deleted campanha must never
    resolve a lead, and its Meta ids become reusable.
  · PATCH `imovel_codigos` / `veiculacoes` REPLACE the sets when present.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence import iter_paged_rows

from app.services.campanhas_service import (
    CampanhaError,
    CampanhasService,
    ImovelDesconhecido,
)
from app.services.table_reads import PAGE_SIZE, batched, in_batched_rows, paged_rows

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_CANAL_META = "meta_ads"
_REF_TABELA_META = "ads_objects"
NIVEIS = ("campaign", "adset", "ad", "form")


class CampanhaNaoEncontrada(CampanhaError):
    """Unknown, other-org or soft-deleted campanha id."""


class CodigosDesconhecidos(CampanhaError):
    def __init__(self, codigos: list[str]) -> None:
        super().__init__(", ".join(codigos))
        self.codigos = codigos


class VeiculacaoInvalida(CampanhaError):
    """The payload names the same Meta object twice."""


class VeiculacaoEmUso(CampanhaError):
    def __init__(self, nivel: str, ref_codigo: str, campanha_nome: Optional[str]) -> None:
        self.nivel = nivel
        self.ref_codigo = ref_codigo
        self.campanha_nome = campanha_nome
        super().__init__(f"{nivel}:{ref_codigo}")


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc)
    return "campanha_veiculacoes_meta_ref_unico" in text or "23505" in text or (
        "duplicate key" in text.lower()
    )


class CampanhasVeiculacaoService:
    def __init__(self, client: Any) -> None:
        self._client = client
        self._registry = CampanhasService(client)

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    # ─── reads ──────────────────────────────────────────────────────────

    def listar(self, org_id: UUID) -> list[dict]:
        rows = paged_rows(
            self._client.schema(_SCHEMA), "campanhas", org_id,
            refine=lambda q: q.is_("deleted_at", "null"),
        )
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return self._hydrate(org_id, rows)

    def obter(self, org_id: UUID, campanha_id: str) -> dict:
        return self._hydrate(org_id, [self._get_row(org_id, campanha_id)])[0]

    def _get_row(self, org_id: UUID, campanha_id: str) -> dict:
        try:
            UUID(str(campanha_id))
        except ValueError as exc:
            raise CampanhaNaoEncontrada(campanha_id) from exc
        resp = (
            self._t("campanhas").select("*")
            .eq("org_id", str(org_id)).eq("id", str(campanha_id))
            .is_("deleted_at", "null").limit(1).execute()
        )
        if not resp.data:
            raise CampanhaNaoEncontrada(campanha_id)
        return resp.data[0]

    def _hydrate(self, org_id: UUID, campanhas: list[dict]) -> list[dict]:
        ids = [c["id"] for c in campanhas]
        if not ids:
            return []
        scoped = self._client.schema(_SCHEMA)
        links = self._links(org_id, ids)
        reg_ids = sorted({link["imovel_ref_id"] for link in links})
        registry = {
            r["id"]: r
            for r in in_batched_rows(
                scoped, "imovel_registry", org_id, "id", reg_ids,
                select="id,codigo_canonical,codigo_display,snap_titulo",
            )
        }
        veics = self._veiculacoes(org_id, ids)

        imoveis_by: dict[str, list[dict]] = {i: [] for i in ids}
        for link in links:
            reg = registry.get(link["imovel_ref_id"])
            if reg is None:
                continue
            codigo = reg.get("codigo_display") or reg["codigo_canonical"]
            imoveis_by[link["campanha_id"]].append(
                {"codigo": codigo, "titulo": reg.get("snap_titulo") or codigo}
            )
        veic_by: dict[str, list[dict]] = {i: [] for i in ids}
        for v in veics:
            veic_by[v["campanha_id"]].append({
                "id": v["id"], "canal": v["canal"],
                "nivel": v.get("nivel"), "ref_codigo": v.get("ref_codigo"),
            })
        return [
            {
                "id": c["id"], "nome": c["nome"],
                "imoveis": sorted(imoveis_by[c["id"]], key=lambda i: i["codigo"]),
                "veiculacoes": sorted(
                    veic_by[c["id"]], key=lambda v: (v["nivel"] or "", v["ref_codigo"] or "")
                ),
                "created_at": c.get("created_at"),
            }
            for c in campanhas
        ]

    def _links(self, org_id: UUID, campanha_ids: list[str]) -> list[dict]:
        """campanha_imoveis has a composite key (no `id`): page on a synthesized one."""
        out: list[dict] = []
        for batch in batched(sorted(set(campanha_ids))):

            def fetch_page(start: int, end: int, _b=batch):
                rows = (
                    self._t("campanha_imoveis")
                    .select("campanha_id,imovel_ref_id")
                    .eq("org_id", str(org_id)).in_("campanha_id", _b)
                    .order("campanha_id").order("imovel_ref_id")
                    .range(start, end).execute().data
                ) or []
                return [{**r, "_k": f"{r['campanha_id']}:{r['imovel_ref_id']}"} for r in rows]

            out.extend(iter_paged_rows(
                fetch_page, page_size=PAGE_SIZE, id_key="_k",
                label=f"campanha_imoveis for org_id={org_id}",
            ))
        return out

    def _veiculacoes(self, org_id: UUID, campanha_ids: list[str]) -> list[dict]:
        return in_batched_rows(
            self._client.schema(_SCHEMA), "campanha_veiculacoes", org_id,
            "campanha_id", campanha_ids,
            select="id,campanha_id,canal,nivel,ref_codigo",
        )

    # ─── validation ─────────────────────────────────────────────────────

    def _resolve_codigos(self, org_id: UUID, codigos: list[str]) -> list[str]:
        ref_ids: list[str] = []
        unknown: list[str] = []
        for raw in codigos:
            try:
                ref_id = self._registry.resolve_imovel_ref(org_id, raw)
            except ImovelDesconhecido as exc:
                unknown.append(str(exc))
                continue
            if ref_id not in ref_ids:
                ref_ids.append(ref_id)
        if unknown:
            raise CodigosDesconhecidos(unknown)
        return ref_ids

    def _check_veiculacoes(
        self, org_id: UUID, veiculacoes: list[dict], *, own_campanha_id: Optional[str]
    ) -> None:
        seen: set[tuple[str, str]] = set()
        for v in veiculacoes:
            key = (v["nivel"], v["ref_codigo"])
            if key in seen:
                raise VeiculacaoInvalida(f"{v['nivel']}:{v['ref_codigo']} repetida")
            seen.add(key)
        for nivel, ref in sorted(seen):
            resp = (
                self._t("campanha_veiculacoes").select("id,campanha_id")
                .eq("org_id", str(org_id)).eq("canal", _CANAL_META)
                .eq("nivel", nivel).eq("ref_codigo", ref).limit(1).execute()
            )
            hit = (resp.data or [None])[0]
            if hit and str(hit["campanha_id"]) != str(own_campanha_id):
                raise VeiculacaoEmUso(nivel, ref, self._nome_da(org_id, hit["campanha_id"]))

    def _nome_da(self, org_id: UUID, campanha_id: str) -> Optional[str]:
        resp = (
            self._t("campanhas").select("nome")
            .eq("org_id", str(org_id)).eq("id", str(campanha_id)).limit(1).execute()
        )
        return resp.data[0]["nome"] if resp.data else None

    # ─── writes ─────────────────────────────────────────────────────────

    def criar(
        self, org_id: UUID, *, nome: str, imovel_codigos: list[str],
        veiculacoes: list[dict], created_by: Optional[str] = None,
    ) -> dict:
        ref_ids = self._resolve_codigos(org_id, imovel_codigos)
        self._check_veiculacoes(org_id, veiculacoes, own_campanha_id=None)
        row = {"org_id": str(org_id), "nome": nome}
        if created_by:
            row["created_by"] = str(created_by)
        created = self._t("campanhas").insert(row).execute().data[0]
        try:
            self._insert_imoveis(org_id, created["id"], ref_ids)
            self._insert_veiculacoes(org_id, created["id"], veiculacoes)
        except Exception as exc:
            self._rollback_criar(org_id, created["id"])
            raise self._translate(org_id, exc, veiculacoes) from exc
        return self.obter(org_id, created["id"])

    def atualizar(
        self, org_id: UUID, campanha_id: str, *, nome: Optional[str] = None,
        imovel_codigos: Optional[list[str]] = None,
        veiculacoes: Optional[list[dict]] = None,
    ) -> dict:
        self._get_row(org_id, campanha_id)
        ref_ids = (
            self._resolve_codigos(org_id, imovel_codigos) if imovel_codigos is not None else None
        )
        if veiculacoes is not None:
            self._check_veiculacoes(org_id, veiculacoes, own_campanha_id=campanha_id)

        if nome is not None:
            self._t("campanhas").update({"nome": nome}).eq(
                "org_id", str(org_id)).eq("id", campanha_id).execute()
        if ref_ids is not None:
            old = [l["imovel_ref_id"] for l in self._links(org_id, [campanha_id])]
            self._t("campanha_imoveis").delete().eq(
                "org_id", str(org_id)).eq("campanha_id", campanha_id).execute()
            try:
                self._insert_imoveis(org_id, campanha_id, ref_ids)
            except Exception:
                self._insert_imoveis(org_id, campanha_id, old)
                raise
        if veiculacoes is not None:
            old_v = self._veiculacoes(org_id, [campanha_id])
            self._t("campanha_veiculacoes").delete().eq(
                "org_id", str(org_id)).eq("campanha_id", campanha_id).execute()
            try:
                self._insert_veiculacoes(org_id, campanha_id, veiculacoes)
            except Exception as exc:
                self._insert_veiculacoes(org_id, campanha_id, [
                    {"canal": v["canal"], "nivel": v["nivel"], "ref_codigo": v["ref_codigo"]}
                    for v in old_v
                ])
                raise self._translate(org_id, exc, veiculacoes, campanha_id) from exc
        return self.obter(org_id, campanha_id)

    def excluir(self, org_id: UUID, campanha_id: str) -> None:
        """Soft delete + free the Meta ids (a deleted campanha never resolves a lead)."""
        self._get_row(org_id, campanha_id)
        self._t("campanha_veiculacoes").delete().eq(
            "org_id", str(org_id)).eq("campanha_id", campanha_id).execute()
        self._t("campanhas").update(
            {"deleted_at": datetime.now(timezone.utc).isoformat()}
        ).eq("org_id", str(org_id)).eq("id", campanha_id).execute()

    # ─── helpers ────────────────────────────────────────────────────────

    def _insert_imoveis(self, org_id: UUID, campanha_id: str, ref_ids: list[str]) -> None:
        if ref_ids:
            self._t("campanha_imoveis").insert([
                {"campanha_id": campanha_id, "imovel_ref_id": r, "org_id": str(org_id)}
                for r in ref_ids
            ]).execute()

    def _insert_veiculacoes(self, org_id: UUID, campanha_id: str, veics: list[dict]) -> None:
        if veics:
            self._t("campanha_veiculacoes").insert([
                {
                    "org_id": str(org_id), "campanha_id": campanha_id,
                    "canal": v["canal"], "nivel": v["nivel"],
                    "ref_tabela": _REF_TABELA_META, "ref_codigo": v["ref_codigo"],
                }
                for v in veics
            ]).execute()

    def _rollback_criar(self, org_id: UUID, campanha_id: str) -> None:
        # No transaction across PostgREST calls: undo the half-made campanha.
        try:
            self._t("campanha_veiculacoes").delete().eq("campanha_id", campanha_id).execute()
            self._t("campanha_imoveis").delete().eq("campanha_id", campanha_id).execute()
            self._t("campanhas").delete().eq("org_id", str(org_id)).eq("id", campanha_id).execute()
        except Exception:
            logger.error("campanha %s: rollback of a failed create also failed", campanha_id,
                         exc_info=True)

    def _translate(
        self, org_id: UUID, exc: Exception, veics: list[dict], own: Optional[str] = None
    ) -> Exception:
        """A race past the pre-check surfaces as the unique index firing."""
        if _is_unique_violation(exc) and veics:
            for v in veics:
                try:
                    self._check_veiculacoes(org_id, [v], own_campanha_id=own)
                except VeiculacaoEmUso as em_uso:
                    return em_uso
            return VeiculacaoEmUso(veics[0]["nivel"], veics[0]["ref_codigo"], None)
        return CampanhaError(f"campanha write failed: {exc}")


def build_campanhas_veiculacao_service(client: Any) -> CampanhasVeiculacaoService:
    return CampanhasVeiculacaoService(client)
