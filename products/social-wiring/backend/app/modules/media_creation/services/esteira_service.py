"""Esteira de reels — board, posts, stage moves, headline/roteiro binding (esteira-contract.md 3-5).

Org/user scoped: a foreign id is a 404 (never 403). Coded refusals carry the FastAPI-style detail
dict ``{"code", "detail", ...extra}`` — the shape the FE reads (``headline_ja_em_post`` carries
``post_id``; ``pendencias`` carries ``faltando`` and ``post_id``).

The board is ONE more ``PipelineConfig`` on the shared ``pipeline_stages`` /
``pipeline_movimentos``: stage CRUD, grouping, ordering and the history-writing move are the seed
(``noctusai_lib.domain.pipeline``). Code keys only on stage ROLES (gravacao / postado / cancelado),
never on slugs or labels, so a renamed stage keeps its gate.

The headline/roteiro services belong to BE-2 and are NOT imported here: the binding lives on the
post (FK columns), so it needs only the ``cs_headlines`` / ``cs_roteiros`` rows themselves.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.domain.pipeline import (
    ensure_default_stages,
    group_into_colunas,
    list_stages,
    move_card,
    orphan_cards,
    position_for_index,
    position_of,
    position_on_top,
)
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched, in_batched_rows, paged_rows
from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.esteira_config import (
    ESTEIRA_PADRAO,
    PIPELINE_ESTEIRA,
    ROLE_CANCELADO,
    ROLE_GRAVACAO,
    ROLE_POSTADO,
)

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
HEADLINES = "cs_headlines"
ROTEIROS = "cs_roteiros"
LOTES = "cs_headline_lotes"
CFG = PIPELINE_ESTEIRA
LIMITE_PADRAO = 50
PERMALINK_RE = re.compile(r"^https://(www\.)?instagram\.com/")
LOTE_ATIVO = ("criando", "processando")
#: Columns a PATCH may clear with an explicit null.
_NULLABLE = (
    "conta_id", "gravacao_em", "legenda", "primeiro_comentario", "permalink", "ig_media_id",
    "data_inicio", "data_entrega", "lembrete_minutos_antes", "recorrencia",
)
# NOC-REMEDIATE[esteira-datas-lembrete]: `lembrete_minutos_antes` is stored on the post but no
# `cs_post_lembretes` row is materialised from it: the generated hub table has no scope column
# (unlike SW's `agendamento_id`), so seed `sync_lembrete` could only cancel EVERY pending reminder of
# the post, including the user's ad-hoc ones. Next step = a scope column on the hub table (seed emitter),
# then `sync_lembrete(scope=...)` here. Delivery itself is the seed's reminder-delivery gap. — 2026-10-10


class EsteiraError(Exception):
    """A refusal with an HTTP status; ``detail`` is a pt-BR string or a ``{code, detail, ...}`` dict."""

    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def coded(status: int, code: str, message: str, **extra: Any) -> EsteiraError:
    return EsteiraError(status, {"code": code, "detail": message, **extra})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rpc_true(data: Any) -> bool:
    """PostgREST returns a scalar boolean RPC as ``true``; tolerate the list/dict wrappers."""
    if isinstance(data, list):
        if not data:
            return False
        data = data[0]
    if isinstance(data, dict):
        data = next(iter(data.values()), None)
    return data is True


def _paged_pairs(db: Any, table: str, org_id: str, in_col: str, ids: list[str], keys: tuple[str, str]) -> list[dict]:
    """Rows of a composite-key link table (no ``id`` column) for ``in_col IN ids``, paged.

    The pager dedupes on one column, so a synthetic ``_k`` joins the two key columns."""
    out: list[dict] = []
    for batch in batched(sorted(set(ids)), 100):

        def fetch(start: int, end: int, _b=batch):
            rows = (
                db.table(table)
                .select("*")
                .eq("org_id", org_id)
                .in_(in_col, _b)
                .order(keys[0])
                .order(keys[1])
                .range(start, end)
                .execute()
                .data
            ) or []
            return [{**r, "_k": f"{r.get(keys[0])}:{r.get(keys[1])}"} for r in rows]

        out.extend(iter_paged_rows(fetch, id_key="_k", label=f"{table}.{in_col} for org_id={org_id}"))
    return out


class EsteiraService:
    def __init__(self, db: Any, org_id: str, user_id: Optional[str]):
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id) if user_id else None

    # ── guards / lookups ────────────────────────────────────────────────────

    def _stages(self, *, incluir_inativas: bool = False) -> list[dict]:
        ensure_default_stages(self.db, CFG, ESTEIRA_PADRAO, org_id=self.org_id)
        return list_stages(self.db, CFG, incluir_inativas=incluir_inativas, org_id=self.org_id)

    def _assert_marca(self, marca_id: str) -> None:
        rows = self.db.table("marcas").select("id").eq("id", marca_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise EsteiraError(404, "Marca não encontrada")

    def _row(self, post_id: str) -> dict:
        rows = self.db.table(POSTS).select("*").eq("id", str(post_id)).eq("org_id", self.org_id).execute().data
        if not rows:
            raise EsteiraError(404, "Post não encontrado")
        return rows[0]

    def _library_row(self, table: str, row_id: str, label: str, marca_id: str, code: str) -> dict:
        rows = self.db.table(table).select("*").eq("id", str(row_id)).eq("org_id", self.org_id).execute().data
        if not rows:
            raise EsteiraError(404, f"{label} não encontrado(a)")
        row = rows[0]
        if str(row.get("marca_id")) != str(marca_id):
            raise coded(422, code, f"{label} pertence a outra marca.")
        return row

    def _post_holding(self, column: str, value: str, *, exclude: Optional[str] = None) -> Optional[dict]:
        q = self.db.table(POSTS).select("id").eq("org_id", self.org_id).eq(column, str(value))
        for row in q.execute().data or []:
            if exclude is None or str(row["id"]) != str(exclude):
                return row
        return None

    def _conta(self, conta_id: str, marca_id: str) -> None:
        rows = (
            self.db.table("integration_accounts")
            .select("id,marca_id")
            .eq("id", str(conta_id))
            .eq("org_id", self.org_id)
            .execute()
            .data
        )
        if not rows:
            raise EsteiraError(404, "Conta não encontrada")
        if str(rows[0].get("marca_id")) != str(marca_id):
            raise coded(422, "conta_de_outra_marca", "A conta pertence a outra marca.")

    # ── presenters ──────────────────────────────────────────────────────────

    def _enrich(self, rows: list[dict], stages: list[dict]) -> list[dict]:
        """``PostCard`` dicts for ``rows`` — every related read is batched (one per table)."""
        if not rows:
            return []
        org = self.org_id
        ids = [str(r["id"]) for r in rows]
        marcas = {
            m["id"]: m.get("name")
            for m in in_batched_rows(self.db, "marcas", org, "id", [str(r["marca_id"]) for r in rows], select="id,name")
        }
        hl_ids = [str(r["headline_id"]) for r in rows if r.get("headline_id")]
        headlines = {h["id"]: h for h in in_batched_rows(self.db, HEADLINES, org, "id", hl_ids, select="id,texto,favorita")}
        rt_ids = [str(r["roteiro_id"]) for r in rows if r.get("roteiro_id")]
        roteiros = {
            r["id"]: r for r in in_batched_rows(self.db, ROTEIROS, org, "id", rt_ids, select="id,nome,status,headline_id")
        }
        links = _paged_pairs(self.db, "cs_post_membros", org, "post_id", ids, ("post_id", "equipe_id"))
        equipe = {
            m["id"]: m
            for m in in_batched_rows(self.db, "cs_equipe", org, "id", [l["equipe_id"] for l in links], select="id,nome,cor")
        }
        membros: dict[str, list[dict]] = {}
        for link in links:
            m = equipe.get(link["equipe_id"])
            if m:
                membros.setdefault(str(link["post_id"]), []).append({"id": m["id"], "nome": m["nome"], "cor": m.get("cor")})
        for lst in membros.values():
            lst.sort(key=lambda m: m["nome"])

        notas = in_batched_rows(self.db, "cs_post_notas", org, "post_id", ids, select="id,post_id,tipo")
        comentarios: dict[str, int] = {}
        for n in notas:
            if n.get("tipo") == "comentario":
                comentarios[str(n["post_id"])] = comentarios.get(str(n["post_id"]), 0) + 1
        cks = in_batched_rows(self.db, "cs_post_checklists", org, "post_id", ids, select="id,post_id")
        ck_post = {c["id"]: str(c["post_id"]) for c in cks}
        itens = in_batched_rows(self.db, "cs_post_checklist_itens", org, "checklist_id", list(ck_post), select="id,checklist_id,concluido")
        checklist: dict[str, dict] = {}
        for it in itens:
            pid = ck_post.get(it["checklist_id"])
            if pid is None:
                continue
            c = checklist.setdefault(pid, {"feitos": 0, "total": 0})
            c["total"] += 1
            c["feitos"] += 1 if it.get("concluido") else 0

        role_of = {s["id"]: s.get("papel") for s in stages}
        out = []
        for r in rows:
            pid = str(r["id"])
            h = headlines.get(str(r["headline_id"])) if r.get("headline_id") else None
            ro = roteiros.get(str(r["roteiro_id"])) if r.get("roteiro_id") else None
            out.append(
                {
                    "id": pid,
                    "marca_id": r["marca_id"],
                    "marca_nome": marcas.get(r["marca_id"]) or "",
                    "titulo": r["titulo"],
                    "formato": r.get("formato") or "reel",
                    "etapa_id": r["etapa_id"],
                    "kanban_pos": str(position_of(r)),
                    "headline": (
                        {"id": h["id"], "texto": h["texto"], "favorita": bool(h.get("favorita"))} if h else None
                    ),
                    "roteiro": (
                        {
                            "id": ro["id"],
                            "nome": ro.get("nome") or "",
                            "status": ro["status"],
                            "headline_id": ro.get("headline_id"),
                            "headline_diferente": ro.get("headline_id") is not None
                            and str(ro.get("headline_id")) != str(r.get("headline_id")),
                        }
                        if ro
                        else None
                    ),
                    "membros": membros.get(pid, []),
                    "gravacao_em": r.get("gravacao_em"),
                    "data_entrega": r.get("data_entrega"),
                    "entrega_concluida": bool(r.get("entrega_concluida")),
                    "postado_em": r.get("postado_em"),
                    # the reason belongs to the BLOCKED state: shown only while in the cancelado stage
                    "motivo_bloqueio": r.get("motivo_bloqueio") if role_of.get(r["etapa_id"]) == ROLE_CANCELADO else None,
                    "arquivado": bool(r.get("arquivado")),
                    "checklist": checklist.get(pid, {"feitos": 0, "total": 0}),
                    "comentarios": comentarios.get(pid, 0),
                }
            )
        return out

    def _detalhe(self, row: dict) -> dict:
        stages = self._stages(incluir_inativas=True)
        card = self._enrich([row], stages)[0]
        conta = None
        if row.get("conta_id"):
            rows = (
                self.db.table("integration_accounts")
                .select("id,account_label")
                .eq("id", row["conta_id"])
                .eq("org_id", self.org_id)
                .execute()
                .data
            )
            if rows:
                conta = {"id": rows[0]["id"], "account_label": rows[0]["account_label"]}
        lotes = (
            self.db.table(LOTES)
            .select("id,status,etapa,created_at")
            .eq("org_id", self.org_id)
            .eq("post_id", row["id"])
            .execute()
            .data
            or []
        )
        ativos = sorted((l for l in lotes if l.get("status") in LOTE_ATIVO), key=lambda l: l.get("created_at") or "", reverse=True)
        lote = {"id": ativos[0]["id"], "status": ativos[0]["status"], "etapa": ativos[0].get("etapa")} if ativos else None
        return {
            **card,
            "conta": conta,
            "legenda": row.get("legenda"),
            "hashtags": list(row.get("hashtags") or []),
            "primeiro_comentario": row.get("primeiro_comentario"),
            "links_producao": list(row.get("links_producao") or []),
            "permalink": row.get("permalink"),
            "ig_media_id": row.get("ig_media_id"),
            "lote_ativo": lote,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    # ── board ───────────────────────────────────────────────────────────────

    def board(
        self,
        *,
        marca_id: Optional[str],
        busca: Optional[str],
        membro_id: Optional[str],
        incluir_arquivados: bool,
        limite_por_etapa: int,
    ) -> dict:
        stages = self._stages()
        if marca_id:
            self._assert_marca(marca_id)
        eq: dict[str, Any] = {"marca_id": marca_id} if marca_id else {}
        refine = None if incluir_arquivados else (lambda q: q.eq("arquivado", False))
        rows = paged_rows(self.db, POSTS, self.org_id, eq_filters=eq, refine=refine)

        if membro_id:
            links = _paged_pairs(self.db, "cs_post_membros", self.org_id, "equipe_id", [str(membro_id)], ("equipe_id", "post_id"))
            com_membro = {str(l["post_id"]) for l in links}
            rows = [r for r in rows if str(r["id"]) in com_membro]
        if busca and busca.strip():
            termo = busca.strip().lower()
            hl_ids = [str(r["headline_id"]) for r in rows if r.get("headline_id")]
            textos = {h["id"]: (h.get("texto") or "") for h in in_batched_rows(self.db, HEADLINES, self.org_id, "id", hl_ids, select="id,texto")}
            rows = [
                r
                for r in rows
                if termo in (r.get("titulo") or "").lower() or termo in textos.get(str(r.get("headline_id")), "").lower()
            ]

        orfaos = len(orphan_cards(stages, rows))
        colunas = group_into_colunas(CFG, stages, rows, value_of=lambda _c: 0, limite_cards=limite_por_etapa)
        visiveis = [c for col in colunas for c in col["cards"]]
        por_id = {c["id"]: c for c in self._enrich(visiveis, stages)}
        for col in colunas:
            col["cards"] = [por_id[str(c["id"])] for c in col["cards"]]
        return {"colunas": colunas, "orfaos": orfaos}

    # ── create / read / update / delete ─────────────────────────────────────

    def _pendencias(self, row: dict) -> list[str]:
        faltando: list[str] = []
        if not row.get("headline_id"):
            faltando.append("headline")
        if not row.get("roteiro_id"):
            faltando.append("roteiro")
        else:
            rt = self.db.table(ROTEIROS).select("id,status").eq("id", row["roteiro_id"]).eq("org_id", self.org_id).execute().data
            if not rt or rt[0].get("status") != "completo":
                faltando.append("roteiro_incompleto")
        return faltando

    @staticmethod
    def _gated(stages: list[dict], target: dict) -> bool:
        """True when ``target`` is at or after the ``gravacao`` role stage (except the cancel stage)."""
        if target.get("papel") == ROLE_CANCELADO:
            return False
        grav = next((s for s in stages if s.get("papel") == ROLE_GRAVACAO), None)
        if grav is None:
            return False
        order = [s["id"] for s in stages]
        return order.index(target["id"]) >= order.index(grav["id"])

    def _check_gate(self, row: dict, stages: list[dict], target: dict) -> None:
        if self._gated(stages, target):
            faltando = self._pendencias(row)
            if faltando:
                raise coded(
                    409,
                    "pendencias",
                    "Faltam itens para avançar este post.",
                    faltando=faltando,
                    post_id=str(row["id"]),
                )

    def _top_position(self, etapa_id: str, *, exclude: Optional[str] = None):
        cards = (
            self.db.table(POSTS).select("id,kanban_pos,created_at").eq("org_id", self.org_id).eq("etapa_id", etapa_id).execute().data
            or []
        )
        return position_on_top([c for c in cards if str(c["id"]) != str(exclude)])

    def criar(self, body: Any) -> dict:
        marca_id = str(body.marca_id)
        self._assert_marca(marca_id)
        headline = None
        if body.headline_id:
            headline = self._library_row(HEADLINES, str(body.headline_id), "Headline", marca_id, "headline_de_outra_marca")
            held = self._post_holding("headline_id", headline["id"])
            if held:
                raise coded(409, "headline_ja_em_post", "Esta headline já está em um post.", post_id=str(held["id"]))
        titulo = body.titulo or (headline["texto"][:200].strip() if headline else None)
        if not titulo:
            raise coded(422, "titulo_obrigatorio", "Informe o título do post (ou uma headline).")
        if body.conta_id:
            self._conta(str(body.conta_id), marca_id)

        stages = self._stages()
        if not stages:
            raise coded(409, "sem_etapas", "O quadro não tem etapas ativas.")
        if body.etapa_id:
            target = next((s for s in stages if s["id"] == body.etapa_id), None)
            if target is None:
                raise coded(409, "etapa_invalida", "A etapa informada não está ativa neste quadro.")
        else:
            target = stages[1] if (headline and len(stages) > 1) else stages[0]

        row = {
            "id": str(uuid.uuid4()),
            "org_id": self.org_id,
            "marca_id": marca_id,
            "formato": "reel",
            "arquivado": False,
            "titulo": titulo[:200],
            "etapa_id": target["id"],
            "kanban_pos": str(self._top_position(target["id"])),
            "headline_id": str(headline["id"]) if headline else None,
            "conta_id": str(body.conta_id) if body.conta_id else None,
            "gravacao_em": body.gravacao_em.isoformat() if body.gravacao_em else None,
            "data_entrega": body.data_entrega.isoformat() if body.data_entrega else None,
            "created_by": self.user_id,
        }
        self._check_gate(row | {"id": "novo"}, stages, target)
        try:
            created = self.db.table(POSTS).insert(row).execute().data
        except Exception as exc:  # noqa: BLE001 - mapped below, anything else re-raised
            if headline and is_unique_violation(exc):
                held = self._post_holding("headline_id", headline["id"])
                raise coded(
                    409, "headline_ja_em_post", "Esta headline já está em um post.", post_id=str(held["id"]) if held else None
                ) from exc
            raise
        return self._detalhe(created[0])

    def detalhe(self, post_id: str) -> dict:
        return self._detalhe(self._row(post_id))

    def atualizar(self, post_id: str, patch: dict) -> dict:
        row = self._row(post_id)
        values = {k: v for k, v in patch.items() if v is not None or k in _NULLABLE}
        if values.get("conta_id"):
            self._conta(str(values["conta_id"]), row["marca_id"])
        for key in ("conta_id",):
            if values.get(key) is not None:
                values[key] = str(values[key])
        if values.get("links_producao") is not None:
            values["links_producao"] = list(values["links_producao"])
        if not values:
            return self._detalhe(row)
        updated = self.db.table(POSTS).update(values).eq("id", row["id"]).eq("org_id", self.org_id).execute().data
        return self._detalhe(updated[0] if updated else {**row, **values})

    def excluir(self, post_id: str) -> None:
        row = self._row(post_id)
        # The library rows stay (the FK lives on the post); the hub tables CASCADE.
        self.db.table(POSTS).delete().eq("id", row["id"]).eq("org_id", self.org_id).execute()

    # ── stage move ──────────────────────────────────────────────────────────

    def mover(self, post_id: str, body: Any) -> dict:
        row = self._row(post_id)
        todas = self._stages(incluir_inativas=True)
        ativas = [s for s in todas if s.get("ativo", True)]
        alvo = next((s for s in todas if s["id"] == body.para_etapa_id), None)
        if alvo is None:
            raise EsteiraError(404, "Etapa não encontrada")
        if not alvo.get("ativo", True):
            raise coded(409, "etapa_invalida", "A etapa de destino está inativa.")
        atual = next((s for s in todas if s["id"] == row["etapa_id"]), None)
        motivo = (body.motivo or "").strip() or None

        if row["etapa_id"] == alvo["id"]:
            extra: dict[str, Any] = {}
            mudou = False
        else:
            mudou = True
            voltando = atual is not None and alvo.get("posicao", 0) < atual.get("posicao", 0)
            saindo_cancelado = atual is not None and atual.get("papel") == ROLE_CANCELADO
            if (alvo.get("papel") == ROLE_CANCELADO or voltando or saindo_cancelado) and not motivo:
                raise coded(422, "motivo_obrigatorio", "Informe o motivo desta movimentação.")
            self._check_gate(row, ativas, alvo)
            extra = {}
            if alvo.get("papel") == ROLE_POSTADO:
                if not row.get("postado_em"):
                    extra["postado_em"] = _now()
                if body.permalink:
                    extra["permalink"] = body.permalink
            if alvo.get("papel") == ROLE_CANCELADO:
                extra["motivo_bloqueio"] = motivo

        if body.novo_indice is not None:
            vizinhos = (
                self.db.table(POSTS)
                .select("id,kanban_pos,created_at")
                .eq("org_id", self.org_id)
                .eq("etapa_id", alvo["id"])
                .execute()
                .data
                or []
            )
            vizinhos = sorted(
                (v for v in vizinhos if str(v["id"]) != str(row["id"])),
                key=lambda r: (position_of(r), r.get("created_at") or ""),
            )
            posicao = position_for_index(vizinhos, body.novo_indice)
        elif mudou:
            posicao = self._top_position(alvo["id"], exclude=row["id"])
        else:
            posicao = None

        try:
            moved = move_card(
                self.db,
                CFG,
                card_id=row["id"],
                to_stage_id=alvo["id"],
                user_id=self.user_id,
                nova_posicao=posicao,
                motivo=motivo,
                extra_updates=extra or None,
                org_id=self.org_id,
            )
        except NotFoundError as exc:
            raise EsteiraError(404, "Post não encontrado") from exc
        return self._enrich([moved], todas)[0]

    # ── headline binding ────────────────────────────────────────────────────

    def vincular_headline(self, post_id: str, body: Any) -> dict:
        row = self._row(post_id)
        if body.headline_id:
            headline = self._library_row(HEADLINES, str(body.headline_id), "Headline", row["marca_id"], "headline_de_outra_marca")
            held = self._post_holding("headline_id", headline["id"], exclude=row["id"])
            if held:
                raise coded(409, "headline_ja_em_post", "Esta headline já está em um post.", post_id=str(held["id"]))
        else:
            headline = (
                self.db.table(HEADLINES)
                .insert(
                    {
                        "org_id": self.org_id,
                        "marca_id": row["marca_id"],
                        "lote_id": None,
                        "texto": body.texto,
                        "modo": "manual",
                        "created_by": self.user_id,
                    }
                )
                .execute()
                .data[0]
            )
        if str(row.get("headline_id")) != str(headline["id"]):
            try:
                self.db.table(POSTS).update({"headline_id": headline["id"]}).eq("id", row["id"]).eq("org_id", self.org_id).execute()
            except Exception as exc:  # noqa: BLE001
                if is_unique_violation(exc):
                    held = self._post_holding("headline_id", headline["id"], exclude=row["id"])
                    raise coded(
                        409, "headline_ja_em_post", "Esta headline já está em um post.", post_id=str(held["id"]) if held else None
                    ) from exc
                raise
        return self._detalhe(self._row(post_id))

    def desvincular_headline(self, post_id: str) -> None:
        row = self._row(post_id)
        self.db.table(POSTS).update({"headline_id": None}).eq("id", row["id"]).eq("org_id", self.org_id).execute()

    # ── roteiro binding ─────────────────────────────────────────────────────

    def vincular_roteiro(self, post_id: str, roteiro_id: str) -> dict:
        row = self._row(post_id)
        roteiro = self._library_row(ROTEIROS, roteiro_id, "Roteiro", row["marca_id"], "roteiro_de_outra_marca")
        held = self._post_holding("roteiro_id", roteiro["id"], exclude=row["id"])
        if held:
            raise coded(409, "roteiro_ja_em_post", "Este roteiro já está em um post.", post_id=str(held["id"]))
        if str(row.get("roteiro_id")) != str(roteiro["id"]):
            # Atomic, row-locked take-over (migration 241): false = the post's roteiro changed meanwhile.
            try:
                res = self.db.rpc(
                    "cs_rebind_roteiro",
                    {"p_org": self.org_id, "p_post": row["id"], "p_old": row.get("roteiro_id"), "p_new": roteiro["id"]},
                ).execute()
            except Exception as exc:  # noqa: BLE001
                if is_unique_violation(exc):
                    raise coded(409, "roteiro_ja_em_post", "Este roteiro já está em um post.") from exc
                raise
            if not _rpc_true(getattr(res, "data", None)):
                raise coded(409, "post_mudou", "O post foi alterado por outra pessoa; recarregue e tente de novo.")
        return self._detalhe(self._row(post_id))

    def desvincular_roteiro(self, post_id: str) -> None:
        row = self._row(post_id)
        self.db.table(POSTS).update({"roteiro_id": None}).eq("id", row["id"]).eq("org_id", self.org_id).execute()
