"""Dashboard de criação (geracao-contract.md §4.7, endpoint 49).

Read-only aggregation, org- AND marca-scoped. There is no activity table: the
"Histórico" is derived by UNION-ing the latest events of the tables that already
record them (lotes created, roteiros completed, brains synthesized, profile updated,
research items approved per day).
"""
import logging
from collections import defaultdict
from typing import Any, Optional

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.media_creation.services.viral_card import viral_cards

logger = logging.getLogger(__name__)

HISTORICO_MAX = 30
SUGERIDAS_MAX = 20
#: How many recent automatic headlines are ranked before the top ``SUGERIDAS_MAX`` are kept.
SUGERIDAS_POOL = 100
ORDENS = ("data_desc", "data_asc", "tipo")

_ORIGEM_TEXTO = {
    "form_me": "Gerou headlines com a sua pesquisa",
    "form_public": "Gerou headlines com a pesquisa do público",
    "form_viral": "Gerou headlines a partir de virais",
    "biblioteca": "Gerou headlines a partir de um viral da Biblioteca",
    "sugestao_auto": "Receberam-se headlines sugeridas",
}


class DashboardError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def saudacao_nome(user: Any) -> str:
    """Display name for "Olá, {nome}!" -- cosmetic only, never an authorization input."""
    meta = getattr(user, "user_metadata", None) or {}
    nome = str(meta.get("full_name") or meta.get("name") or "").strip()
    if nome:
        return nome.split()[0]
    email = str(getattr(user, "email", "") or "")
    return email.split("@")[0] if email else ""


def _metrica(viral: Optional[dict[str, Any]]) -> float:
    if not viral:
        return -1.0
    if viral.get("views") is not None:
        return float(viral["views"])
    return float((viral.get("likes") or 0) + (viral.get("comments") or 0))


class DashboardCriacaoService:
    def __init__(self, db, org_id: str, storage: Optional[StorageBackend] = None):
        self.db = db
        self.org_id = org_id
        self.storage = storage

    def _q(self, table: str, cols: str, marca_id: str, **count):
        return self.db.table(table).select(cols, **count).eq("org_id", self.org_id).eq("marca_id", marca_id)

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id")
            .eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise DashboardError(404, "Marca não encontrada")

    def _count(self, query) -> int:
        res = query.execute()
        return res.count if getattr(res, "count", None) is not None else len(res.data or [])

    # ── KPIs ────────────────────────────────────────────────────────────

    def kpis(self, marca_id: str) -> dict[str, int]:
        return {
            "headlines_geradas": self._count(self._q("cs_headlines", "id", marca_id, count="exact")),
            "roteiros_gerados": self._count(
                self._q("cs_roteiros", "id", marca_id, count="exact").eq("status", "completo")
            ),
            "itens_pendentes": self._count(
                self._q("cs_research_items", "id", marca_id, count="exact").eq("status", "pending")
            ),
        }

    # ── Histórico ───────────────────────────────────────────────────────

    def historico(self, marca_id: str, ordem: str) -> list[dict[str, Any]]:
        eventos: list[dict[str, Any]] = []

        for r in (
            self._q("cs_headline_lotes", "origem,created_at", marca_id)
            .order("created_at", desc=True).limit(HISTORICO_MAX).execute().data or []
        ):
            eventos.append({"tipo": "headline", "texto": _ORIGEM_TEXTO.get(r["origem"], "Gerou headlines"),
                            "ator": None, "em": r["created_at"]})

        for r in (
            self._q("cs_roteiros", "nome,finished_at", marca_id).eq("status", "completo")
            .order("finished_at", desc=True).limit(HISTORICO_MAX).execute().data or []
        ):
            if r.get("finished_at"):
                eventos.append({"tipo": "roteiro", "texto": f"Concluiu o roteiro \"{r['nome']}\"",
                                "ator": None, "em": r["finished_at"]})

        for r in (
            self._q("cs_brains", "name,synthesized_at", marca_id)
            .order("synthesized_at", desc=True).limit(HISTORICO_MAX).execute().data or []
        ):
            if r.get("synthesized_at"):
                eventos.append({"tipo": "cerebro", "texto": f"Atualizou o cérebro \"{r['name']}\"",
                                "ator": None, "em": r["synthesized_at"]})

        for r in self._q("cs_marca_perfil", "updated_at", marca_id).execute().data or []:
            if r.get("updated_at"):
                eventos.append({"tipo": "perfil", "texto": "Atualizou o Meu Perfil", "ator": None,
                                "em": r["updated_at"]})

        # Approved research items are grouped per day: one line per day, stamped with its latest approval.
        por_dia: dict[str, list[str]] = defaultdict(list)
        for r in (
            self._q("cs_research_items", "updated_at", marca_id).eq("status", "approved")
            .order("updated_at", desc=True).limit(200).execute().data or []
        ):
            por_dia[str(r["updated_at"])[:10]].append(str(r["updated_at"]))
        for stamps in por_dia.values():
            n = len(stamps)
            eventos.append({
                "tipo": "pesquisa",
                "texto": f"Aprovou {n} {'item' if n == 1 else 'itens'} de pesquisa",
                "ator": None, "em": max(stamps),
            })

        eventos.sort(key=lambda e: str(e["em"]), reverse=True)
        eventos = eventos[:HISTORICO_MAX]
        if ordem == "data_asc":
            eventos.reverse()
        elif ordem == "tipo":
            eventos.sort(key=lambda e: str(e["em"]), reverse=True)
            eventos.sort(key=lambda e: e["tipo"])
        return eventos

    # ── Sugeridas ───────────────────────────────────────────────────────

    async def sugeridas(self, marca_id: str) -> list[dict[str, Any]]:
        rows = (
            self._q(
                "cs_headlines",
                "id,lote_id,viral_id,template_metodo,texto,texto_original,angulo,itens_usados,favorita,modo,created_at",
                marca_id,
            ).eq("modo", "automatico").order("created_at", desc=True).limit(SUGERIDAS_POOL).execute().data or []
        )
        virais = await self._virais({r["viral_id"] for r in rows if r.get("viral_id")})
        roteiros = self._roteiros_por_headline([r["id"] for r in rows])
        items = [
            {
                "id": r["id"], "marca_id": marca_id, "lote_id": r.get("lote_id"), "texto": r["texto"],
                "texto_original": r.get("texto_original"), "angulo": r.get("angulo"),
                "viral": virais.get(r.get("viral_id")), "template_metodo": r.get("template_metodo"),
                "itens_usados": r.get("itens_usados") or [], "favorita": bool(r.get("favorita")),
                "modo": r.get("modo"), "roteiro_id": roteiros.get(r["id"]), "created_at": r["created_at"],
            }
            for r in rows
        ]
        items.sort(key=lambda h: str(h["created_at"]), reverse=True)
        items.sort(key=lambda h: _metrica(h["viral"]), reverse=True)
        return items[:SUGERIDAS_MAX]

    def _roteiros_por_headline(self, headline_ids: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for i in range(0, len(headline_ids), 100):
            for r in (
                self.db.table("cs_roteiros").select("id,headline_id,created_at")
                .eq("org_id", self.org_id).in_("headline_id", headline_ids[i:i + 100]).execute().data or []
            ):
                out.setdefault(r["headline_id"], r["id"])
        return out

    async def _virais(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        """``ViralCard`` per viral id via the shared presenter (signed thumbnail)."""
        return await viral_cards(self.db, self.org_id, self.storage, sorted(ids))

    # ── Whole payload ───────────────────────────────────────────────────

    async def dashboard(self, marca_id: str, ordem: str, user: Any) -> dict[str, Any]:
        if ordem not in ORDENS:
            raise DashboardError(422, "Ordenação inválida")
        self.assert_marca(marca_id)
        return {
            "saudacao_nome": saudacao_nome(user),
            "kpis": self.kpis(marca_id),
            "historico": self.historico(marca_id, ordem),
            "sugeridas": await self.sugeridas(marca_id),
        }
