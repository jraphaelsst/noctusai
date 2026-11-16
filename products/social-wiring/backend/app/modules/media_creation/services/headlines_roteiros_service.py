"""Headlines e Roteiros -- the saved-work list of a marca (estruturas-contract.md section 6.9, tier ``org``).

Read-only composition over ``cs_headlines`` / ``cs_roteiros`` / ``cs_estrutura_usos`` / ``cs_estruturas`` /
``cs_chat_conversas`` / ``cs_posts``; it writes nothing, so it records no event (the events belong to the writers).

Which rows are listed: a headline that is ``favorita`` OR carries a ``conversa_id`` OR has a roteiro, **plus every
roteiro without a headline** (Roteiro Avancado with a free ``headline_texto``). One item per roteiro, and one item
per headline that has no roteiro: a headline with two roteiros appears twice (``roteiro`` differs), a roteiro never
appears without its headline when it has one.

Also the home of the two presenters :mod:`esteira_origem_service` shares (``EstruturaUso``, the roteiro summary,
the conversation link) so the list and the card origin answer the same shapes.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.primitives.accents import fold_accents_ascii

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.prompts.headline_geracao import acima_recomendado
from app.modules.media_creation.prompts.roteiro_geracao import ESTRUTURA_PADRAO
from app.modules.media_creation.services.estruturas_service import formula_trecho
from app.modules.media_creation.services.post_ref import post_refs

logger = logging.getLogger(__name__)

HEADLINES = "cs_headlines"
ROTEIROS = "cs_roteiros"
USOS = "cs_estrutura_usos"
ESTRUTURAS = "cs_estruturas"
BLOCOS = "cs_estrutura_blocos"
PERFIS = "cs_perfis_monitorados"
CONVERSAS = "cs_chat_conversas"
MARCAS = "marcas"

HEADLINE_COLS = "id,texto,favorita,created_at,conversa_id"
ROTEIRO_COLS = "id,nome,status,duracao,estrutura,versao,headline_id,headline_texto,conversa_id,formato,created_at"
ROTEIRO_STATUS_FILTROS = ("criando", "processando", "completo", "falha", "sem_roteiro")
APROVACAO_ESTADOS = ("pendente", "aprovado", "rejeitado")


class HeadlinesRoteirosError(Exception):
    """A refusal with its HTTP status and a pt-BR message (a foreign / unknown id is a 404, never a 403)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def assert_marca(db: Any, org_id: str, marca_id: str) -> None:
    rows = db.table(MARCAS).select("id").eq("id", str(marca_id)).eq("org_id", str(org_id)).execute().data
    if not rows:
        raise HeadlinesRoteirosError(404, "Marca não encontrada")


def _rows(db: Any, table: str, cols: str, ids: Iterable[Any], key: str = "id") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in batched(sorted({str(i) for i in ids if i})):
        out.extend(db.table(table).select(cols).in_(key, chunk).execute().data or [])
    return out


def _normalizar(texto: Optional[str]) -> str:
    return fold_accents_ascii((texto or "").casefold())


# -- shared presenters --------------------------------------------------------------------------------------------


def apresentar_roteiro(row: dict[str, Any]) -> dict[str, Any]:
    """The roteiro summary both endpoints answer (``approval`` is added by the list, never here)."""
    formato = row.get("formato")
    return {
        "id": str(row["id"]), "nome": row["nome"], "status": row["status"],
        "formato": formato if formato in fmt.FORMATOS else "reels",
        "duracao": row.get("duracao") or "auto",
        "ordem_cta": row.get("estrutura") or ESTRUTURA_PADRAO,
        "versao": int(row.get("versao") or 1),
    }


def estruturas_usadas(
    db: Any, org_id: str, *, roteiro_ids: Iterable[Any] = (), headline_ids: Iterable[Any] = (),
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """``{("roteiro"|"headline", id): EstruturaUso[]}``.

    A use row can be linked to a headline, a roteiro or both (the chat flow records it at the headline step, the
    roteiro step adds ``roteiro_id`` + the blocks). Per Estrutura the roteiro-linked row wins (it names the blocks);
    ordered principal first, then by ``ordem``. Org-scoped; the Estrutura itself is platform-wide, so an archived
    Estrutura still shows on the work it served.
    """
    r_ids = sorted({str(i) for i in roteiro_ids if i})
    h_ids = sorted({str(i) for i in headline_ids if i})
    cols = "estrutura_id,papel,ordem,bloco_ids,headline_id,roteiro_id"
    usos: list[dict[str, Any]] = []
    for chunk in batched(r_ids):
        usos.extend(db.table(USOS).select(cols).eq("org_id", str(org_id)).in_("roteiro_id", chunk).execute().data or [])
    for chunk in batched(h_ids):
        usos.extend(db.table(USOS).select(cols).eq("org_id", str(org_id)).in_("headline_id", chunk).execute().data or [])
    if not usos:
        return {}
    estruturas = {
        str(e["id"]): e
        for e in _rows(db, ESTRUTURAS, "id,codigo,perfil_id,formula_headline", (u["estrutura_id"] for u in usos))
    }
    perfis = {str(p["id"]): p for p in _rows(db, PERFIS, "id,handle,nome", (e["perfil_id"] for e in estruturas.values()))}
    bloco_ids = {str(b) for u in usos for b in (u.get("bloco_ids") or [])}
    blocos = {str(b["id"]): b for b in _rows(db, BLOCOS, "id,nome,ordem", bloco_ids)}

    def uso_de(u: dict[str, Any]) -> Optional[dict[str, Any]]:
        e = estruturas.get(str(u["estrutura_id"]))
        if e is None:
            return None
        p = perfis.get(str(e["perfil_id"])) or {}
        usados = [blocos[str(b)] for b in (u.get("bloco_ids") or []) if str(b) in blocos]
        return {
            "id": str(e["id"]), "codigo": e["codigo"],
            "perfil": {"id": str(e["perfil_id"]), "handle": p.get("handle") or "", "nome": p.get("nome")},
            "formula_trecho": formula_trecho(e.get("formula_headline") or ""),
            "papel": u["papel"],
            "blocos": [{"id": str(b["id"]), "nome": b["nome"]} for b in sorted(usados, key=lambda b: b.get("ordem") or 0)],
        }

    por_chave: dict[tuple[str, str], dict[str, tuple[int, int, dict[str, Any]]]] = {}

    def juntar(chave: tuple[str, str], u: dict[str, Any], tem_roteiro: bool) -> None:
        uso = uso_de(u)
        if uso is None:
            return
        rank = (0 if tem_roteiro else 1, int(u.get("ordem") or 0))
        atual = por_chave.setdefault(chave, {}).get(uso["id"])
        if atual is None or rank < (atual[0], atual[1]):
            por_chave[chave][uso["id"]] = (rank[0], rank[1], uso)

    for u in usos:
        if u.get("roteiro_id"):
            juntar(("roteiro", str(u["roteiro_id"])), u, True)
        if u.get("headline_id"):
            juntar(("headline", str(u["headline_id"])), u, False)
    return {
        chave: [
            uso for _, _, uso in sorted(
                porestrutura.values(), key=lambda t: (t[2]["papel"] != "principal", t[1], t[2]["codigo"]),
            )
        ]
        for chave, porestrutura in por_chave.items()
    }


def conversas_visiveis(db: Any, org_id: str, user_id: str, ids: Iterable[Any]) -> dict[str, dict[str, str]]:
    """``{conversa_id: {id, titulo}}`` for the conversations that belong to ``user_id``.

    A conversation is private to its author (migration 229): a colleague who sees the same saved headline gets
    ``conversa: null``, never another person's conversation title.
    """
    out: dict[str, dict[str, str]] = {}
    for c in _rows(db, CONVERSAS, "id,titulo,user_id,org_id", ids):
        if str(c.get("org_id")) == str(org_id) and str(c.get("user_id")) == str(user_id):
            out[str(c["id"])] = {"id": str(c["id"]), "titulo": c["titulo"]}
    return out


# -- the list -----------------------------------------------------------------------------------------------------


def _aprovacoes(db: Any, org_id: str, roteiro_ids: Iterable[Any]) -> dict[str, dict[str, str]]:
    """``{roteiro_id: {estado}}``. Always empty until the roteiro approval (S3) lands: ``aprovacao`` is ``null``.

    NOC-REMEDIATE[hr-aprovacao-s3]: read the approvals organ here once S3 ships -- 2026-11-15
    """
    return {}


class HeadlinesRoteirosService:
    def __init__(self, db: Any, *, org_id: str, user_id: str):
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id)

    def _paged(self, table: str, cols: str, marca_id: str, **eq: Any) -> list[dict[str, Any]]:
        def page(start: int, end: int) -> Any:
            q = self.db.table(table).select(cols).eq("org_id", self.org_id).eq("marca_id", marca_id)
            for k, v in eq.items():
                q = q.eq(k, v)
            return q.order("id").range(start, end).execute().data

        return list(iter_paged_rows(page, id_key="id", label=f"{table} da marca"))

    def _candidatos(self, marca_id: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """(headlines by id, roteiros) of the marca that qualify for the list."""
        roteiros = self._paged(ROTEIROS, ROTEIRO_COLS, marca_id)
        headlines: dict[str, dict[str, Any]] = {}
        for h in self._paged(HEADLINES, HEADLINE_COLS, marca_id, favorita=True):
            headlines[str(h["id"])] = h
        for h in self._paged_conversa(marca_id):
            headlines[str(h["id"])] = h
        faltam = [r["headline_id"] for r in roteiros if r.get("headline_id") and str(r["headline_id"]) not in headlines]
        for h in _rows(self.db, HEADLINES, HEADLINE_COLS + ",marca_id,org_id", faltam):
            if str(h.get("org_id")) == self.org_id and str(h.get("marca_id")) == marca_id:
                headlines[str(h["id"])] = h
        return headlines, roteiros

    def _paged_conversa(self, marca_id: str) -> list[dict[str, Any]]:
        def page(start: int, end: int) -> Any:
            return (
                self.db.table(HEADLINES).select(HEADLINE_COLS).eq("org_id", self.org_id).eq("marca_id", marca_id)
                .not_.is_("conversa_id", "null").order("id").range(start, end).execute().data
            )

        return list(iter_paged_rows(page, id_key="id", label="cs_headlines com conversa"))

    def listar(
        self, marca_id: str, *, q: Optional[str] = None, estrutura_id: Optional[str] = None,
        perfil_id: Optional[str] = None, roteiro_status: Optional[str] = None, aprovacao: Optional[str] = None,
        limit: int = 20, offset: int = 0,
    ) -> dict[str, Any]:
        assert_marca(self.db, self.org_id, marca_id)
        headlines, roteiros = self._candidatos(marca_id)

        # (headline row | None, roteiro row | None) pairs
        pares: list[tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]] = []
        com_roteiro: set[str] = set()
        for r in roteiros:
            h = headlines.get(str(r["headline_id"])) if r.get("headline_id") else None
            if h is not None:
                com_roteiro.add(str(h["id"]))
            pares.append((h, r))
        pares += [(h, None) for hid, h in headlines.items() if hid not in com_roteiro]

        def criado(par: tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]) -> str:
            h, r = par
            return str((r or h or {}).get("created_at") or "")

        pares.sort(key=lambda p: (criado(p), str((p[1] or p[0] or {}).get("id"))), reverse=True)

        def texto(par: tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]) -> str:
            h, r = par
            return (h["texto"] if h else (r or {}).get("headline_texto")) or ""

        if roteiro_status:
            pares = [p for p in pares if (p[1] is None if roteiro_status == "sem_roteiro" else (p[1] or {}).get("status") == roteiro_status)]
        if q:
            alvo = _normalizar(q)
            pares = [p for p in pares if alvo in _normalizar(texto(p)) or alvo in _normalizar((p[1] or {}).get("nome"))]
        if aprovacao:
            ap = _aprovacoes(self.db, self.org_id, (p[1]["id"] for p in pares if p[1]))
            pares = [p for p in pares if p[1] and ap.get(str(p[1]["id"]), {}).get("estado") == aprovacao]

        usos: Optional[dict[tuple[str, str], list[dict[str, Any]]]] = None
        if estrutura_id or perfil_id:
            usos = self._usos(pares)
            pares = [p for p in pares if self._bate(self._estruturas_do_par(p, usos), estrutura_id, perfil_id)]

        total = len(pares)
        pagina = pares[offset: offset + limit]
        if usos is None or offset or limit < total:
            usos = self._usos(pagina)
        ap = _aprovacoes(self.db, self.org_id, (p[1]["id"] for p in pagina if p[1]))
        conversas = conversas_visiveis(
            self.db, self.org_id, self.user_id,
            ((p[1] or {}).get("conversa_id") or (p[0] or {}).get("conversa_id") for p in pagina),
        )
        posts_r = post_refs(self.db, self.org_id, "roteiro_id", (p[1]["id"] for p in pagina if p[1]))
        posts_h = post_refs(self.db, self.org_id, "headline_id", (p[0]["id"] for p in pagina if p[0]))

        items = []
        for par in pagina:
            h, r = par
            conversa_id = (r or {}).get("conversa_id") or (h or {}).get("conversa_id")
            roteiro = None
            if r:
                roteiro = {**apresentar_roteiro(r), "aprovacao": ap.get(str(r["id"]))}
            items.append({
                "headline": None if h is None else {
                    "id": str(h["id"]), "texto": h["texto"], "favorita": bool(h.get("favorita")),
                    "created_at": h.get("created_at"), "acima_recomendado": acima_recomendado(h["texto"]),
                },
                "headline_texto": texto(par),
                "roteiro": roteiro,
                "estruturas": self._estruturas_do_par(par, usos),
                "conversa": conversas.get(str(conversa_id)) if conversa_id else None,
                "post": (posts_r.get(str(r["id"])) if r else None) or (posts_h.get(str(h["id"])) if h else None),
                "created_at": (r or h or {}).get("created_at"),
            })
        return {"items": items, "total": total}

    def _usos(self, pares: list[tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        return estruturas_usadas(
            self.db, self.org_id,
            roteiro_ids=(p[1]["id"] for p in pares if p[1]), headline_ids=(p[0]["id"] for p in pares if p[0]),
        )

    @staticmethod
    def _estruturas_do_par(par: tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]], usos: dict[tuple[str, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        h, r = par
        # The roteiro's own list wins; a roteiro whose uso rows are still headline-only reads the headline's.
        if r and usos.get(("roteiro", str(r["id"]))):
            return usos[("roteiro", str(r["id"]))]
        if h:
            return usos.get(("headline", str(h["id"])), [])
        return []

    @staticmethod
    def _bate(estruturas: list[dict[str, Any]], estrutura_id: Optional[str], perfil_id: Optional[str]) -> bool:
        if estrutura_id and not any(e["id"] == str(estrutura_id) for e in estruturas):
            return False
        if perfil_id and not any(e["perfil"]["id"] == str(perfil_id) for e in estruturas):
            return False
        return True
