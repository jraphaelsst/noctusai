"""Roteiros (Roteiro Avançado) — request side, queue handlers, dead-letter reconcile.

Contract: ``projects/core-studio-build/specs/geracao-contract.md`` sections 2.5, 3, 4.5 and 6.1. Both
prompts are DRAFT for owner validation.

Two halves:

* :class:`RoteiroService` — org/user scoped (create, list, get, answer questions, generate, save,
  feedback, reprocess, delete). Refusals happen BEFORE anything is enqueued.
* :func:`executar_perguntas` / :func:`executar_geracao` — the ``roteiro.perguntas`` and
  ``roteiro.gerar`` queue handlers, registered with the ``geracao`` worker at import (with a
  dead-letter reconciler that moves the row to ``falha``). A database exception PROPAGATES so the
  worker retries; an LLM failure settles the row (``falha``) on the last attempt, or immediately
  when retrying cannot help (no key / budget).

Status machine: ``criando -> perguntas -> processando -> completo | falha`` (``perguntas`` waits for
the USER, so it is never stale). Every transition is a conditional update on the expected status,
so a late job can never resurrect a row the stale sweep already failed.

NOC-REMEDIATE[roteiro-web-search]: ``fonte='web'`` needs a web-search provider (none exists in the
seed or core); next step = a seed web-search seam, or the Anthropic server-side web-search tool once
seed tool calling lands. 2026-10-10
NOC-REMEDIATE[roteiro-link-source]: ``fonte='link'`` (fetch a user-given URL) stays closed behind
the URL-sources security review (``cerebro-contract.md`` section 10.3). 2026-10-10
``Roteiro.viral`` is the shared ``viral_card`` presenter (signed thumbnail from the private library bucket);
swap in the BE-2 library presenter when ``services/biblioteca_service.py`` lands. 2026-10-10
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.approvals import ApprovalError, ApprovalService
from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.llm import LLMBudgetExceeded, LLMNotConfigured, chat_completion, resolve_api_key

from app.modules.media_creation.geracao_scheduler import MSG_JOB_FAILED
from app.modules.media_creation.prompts.roteiro_geracao import (
    ESTRUTURA_PADRAO,
    ESTRUTURAS,
    build_geracao_user_message,
    prompt_versao,
    system_prompt,
)
from app.modules.media_creation.prompts.roteiro_perguntas import (
    ROTEIRO_PERGUNTAS_SYSTEM_PROMPT,
    PerguntasParseError,
    build_perguntas_user_message,
    parse_perguntas,
)
from app.modules.media_creation.prompts import roteiro_formatos
from app.modules.media_creation.prompts.estruturas_contexto import renderizar_estrutura
from app.modules.media_creation.saida_ia import SaidaIaFalha, validar_roteiro, validar_roteiro_formato
from app.modules.media_creation.schemas.roteiros import MAX_CONTEUDO, MAX_ESTRUTURAS, MAX_INSTRUCOES, MAX_NOME
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.roteiro_aprovacao import (
    NOTA_EDITADO,
    NOTA_GERADO,
    SUBJECT_KIND,
    AprovacaoRoteiroError,
    make_approvals,
    present_estado,
    solicitar_aprovacao_roteiro,
)
from app.modules.media_creation.services.estruturas_retrieval import carregar_estruturas
from app.modules.media_creation.services.post_ref import post_refs
from app.modules.media_creation.services.viral_card import viral_cards

logger = logging.getLogger(__name__)

ROTEIROS = "cs_roteiros"
HEADLINES = "cs_headlines"
BRAINS = "cs_brains"
VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"
MARCA_PERFIL = "cs_marca_perfil"
POSTS = "cs_posts"
TABELA_ESTRUTURAS = "cs_estruturas"
ESTRUTURA_BLOCOS = "cs_estrutura_blocos"
USOS = "cs_estrutura_usos"
CONVERSAS = "cs_chat_conversas"
FLUXO_EVENTOS = "cs_fluxo_eventos"
REBIND_RPC = "cs_rebind_roteiro"
JOB_PERGUNTAS = "roteiro.perguntas"
JOB_GERAR = "roteiro.gerar"
WINDOW = timedelta(hours=24)
#: Rolling-window cap: the client may retry after an hour at the latest.
RETRY_AFTER_S = 3600

ETAPA_PERGUNTAS = "Preparando as perguntas…"
ETAPA_AGUARDANDO = "Aguardando as suas respostas"
ETAPA_GERANDO = "Escrevendo o roteiro…"
MSG_SEM_PERGUNTAS = "Não foi possível gerar perguntas; o roteiro será criado sem elas."
MSG_IA_FALHOU = "A IA não conseguiu gerar o roteiro. Tente novamente."
MSG_IA_NAO_CONFIGURADA = "A IA não está configurada para esta conta."
MSG_ORCAMENTO = "O orçamento de IA da organização foi excedido."
MSG_SAIDA_INVALIDA = "A IA devolveu um roteiro inválido ({codigo}). Tente novamente."

ROTEIRO_COLS = (
    "id,marca_id,created_by,nome,headline_id,headline_texto,instrucoes,fonte,duracao,brain_id,viral_id,"
    "perguntas,status,etapa,erro,conteudo,versao,fontes,feedback,feedback_motivo,estrutura,created_at"
)

#: ``(system_prompt, user_message, org_id) -> raw model reply`` (same shape as the cerebro seam).
RoteiroLlm = Callable[[str, str, Optional[str]], Awaitable[str]]
#: ``(org_id) -> None``; raises ``HTTPException(503, ia_nao_configurada)`` when no key resolves.
IaCheck = Callable[[Optional[str]], None]


class RoteiroError(Exception):
    """A refusal with an HTTP status; ``detail`` is a pt-BR string or a ``{code, message}`` dict."""

    def __init__(self, status: int, detail: Any, headers: Optional[dict[str, str]] = None):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail
        self.headers = headers


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── the LLM seam (Anthropic pinned, model from config) ──────────────────────────


def make_chat_roteiro_llm(cfg: Any = None, *, max_tokens: int = 4096) -> RoteiroLlm:
    """Anthropic + ``geracao_llm_model`` (priced in the seed catalog, so ``enforce_budget`` is armed)."""

    async def chat(system_prompt: str, user_message: str, org_id: Optional[str]) -> str:
        nonlocal cfg
        if cfg is None:
            from app.config import settings as cfg
        return await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            provider="anthropic",
            model=cfg.geracao_llm_model,
            org_id=org_id,
            temperature=0.7,
            max_tokens=max_tokens,
            cache=False,
        )

    return chat


def get_roteiro_llm() -> RoteiroLlm:
    """DI seam for the roteiro LLM. Tests override with a fake callable."""
    return make_chat_roteiro_llm()


def check_ia_configurada(org_id: Optional[str]) -> None:
    """Submit-side guard: no resolvable Anthropic key => 503 ``ia_nao_configurada`` (help_chat's code)."""
    try:
        resolve_api_key("anthropic", org_id)
    except LLMNotConfigured as exc:
        raise RoteiroError(503, {"code": "ia_nao_configurada", "detail": MSG_IA_NAO_CONFIGURADA}) from exc


def get_roteiro_ia_check() -> IaCheck:
    """DI seam for :func:`check_ia_configurada`. Tests override with a no-op."""
    return check_ia_configurada


# ── presenters ────────────────────────────────────────────────────────────────


def present_resumo(row: dict[str, Any], post: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """``RoteiroResumo`` (contract 4.8); ``post`` = the bound Esteira post ref, if any (contract 5.3)."""
    return {
        "id": row["id"],
        "nome": row["nome"],
        "headline_texto": row["headline_texto"],
        "headline_id": row.get("headline_id"),
        "status": row["status"],
        "post": post,
        "created_at": row.get("created_at"),
    }


def present_perguntas(raw: Any) -> list[dict[str, Any]]:
    out = []
    for p in raw or []:
        resposta = p.get("resposta")
        out.append({
            "id": p["id"],
            "pergunta": p["pergunta"],
            "resposta": resposta if resposta else None,
        })
    return out


def present_roteiro(
    row: dict[str, Any], viral: Optional[dict[str, Any]] = None, post: Optional[dict[str, Any]] = None,
    aprovacao: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``Roteiro`` (contract 4.8) + ``aprovacao`` (CoreStudio S3: ``{status, versao, decidido_por, decidido_em, motivo}``)."""
    return {
        **present_resumo(row, post),
        "instrucoes": row.get("instrucoes") or "",
        "fonte": row.get("fonte") or "ia",
        "duracao": row.get("duracao") or "auto",
        "estrutura": row.get("estrutura") or ESTRUTURA_PADRAO,
        "brain_id": row.get("brain_id"),
        "viral": viral,
        "perguntas": present_perguntas(row.get("perguntas")),
        "etapa": row.get("etapa"),
        "conteudo": row.get("conteudo") or None,
        "fontes": row.get("fontes"),
        "versao": int(row.get("versao") or 1),
        "feedback": row.get("feedback"),
        "feedback_motivo": row.get("feedback_motivo"),
        "erro": row.get("erro"),
        "aprovacao": aprovacao,
    }


def _default_nome(headline: str) -> str:
    h = " ".join(headline.split())
    return f"Roteiro: {h[:100]}"[:MAX_NOME]


# ── request side ────────────────────────────────────────────────────────────


class RoteiroService:
    def __init__(
        self,
        db,
        org_id: str,
        user_id: Optional[str],
        *,
        cfg: Any,
        jobs: Optional[JobRepository] = None,
        ia_check: IaCheck = check_ia_configurada,
        storage: Optional[StorageBackend] = None,
        approvals: Optional[ApprovalService] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.cfg = cfg
        self.jobs = jobs
        self.ia_check = ia_check
        self.storage = storage
        self.approvals = approvals or make_approvals(db)

    # guards / lookups (everything is scoped to the org: a foreign id is a 404)

    def _table(self):
        return self.db.table(ROTEIROS)

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id").eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise RoteiroError(404, "Marca não encontrada")

    def _exists(self, table: str, row_id: str, message: str, *, marca_id: Optional[str] = None) -> None:
        q = self.db.table(table).select("id").eq("id", row_id).eq("org_id", self.org_id)
        if marca_id is not None:
            q = q.eq("marca_id", marca_id)
        if not q.execute().data:
            raise RoteiroError(404, message)

    def _estruturas_do_pedido(self, body: Any) -> tuple[str, list[str]]:
        """EST-RO (estruturas-contract 6.7): ``(formato, estrutura_ids)``. With Estruturas the formato is the principal's
        (an explicit different one, a mix of formatos, more than 3, or an unknown / inactive one is a coded 422);
        without, it is the request's (default ``reels``)."""
        pedidas = [str(e) for e in (getattr(body, "estrutura_ids", None) or [])]
        explicito = getattr(body, "formato", None)
        if not pedidas:
            return explicito or "reels", []
        if len(pedidas) > MAX_ESTRUTURAS:
            raise RoteiroError(422, {"code": "muitas_estruturas", "detail": f"Use no máximo {MAX_ESTRUTURAS} Estruturas."})
        if len(set(pedidas)) != len(pedidas):
            raise RoteiroError(422, {"code": "estrutura_obrigatoria_invalida", "detail": "Estrutura repetida."})
        rows = self.db.table(TABELA_ESTRUTURAS).select("id,formato,status").in_("id", pedidas).execute().data or []
        por_id = {str(r["id"]): r for r in rows}
        if any(por_id.get(e, {}).get("status") != "ativa" for e in pedidas):
            raise RoteiroError(422, {"code": "estrutura_obrigatoria_invalida", "detail": "Estrutura não encontrada ou inativa."})
        formatos = {por_id[e].get("formato") or "reels" for e in pedidas}
        if len(formatos) > 1:
            raise RoteiroError(422, {"code": "formatos_misturados", "detail": "As Estruturas têm formatos diferentes."})
        formato = por_id[pedidas[0]].get("formato") or "reels"
        if explicito and explicito != formato:
            raise RoteiroError(422, {"code": "formato_diferente_da_estrutura",
                                     "detail": "O formato informado é diferente do formato da Estrutura."})
        return formato, pedidas

    def _assert_conversa(self, conversa_id: Optional[Any]) -> Optional[str]:
        if not conversa_id:
            return None
        rows = (
            self.db.table(CONVERSAS).select("id").eq("id", str(conversa_id)).eq("org_id", self.org_id)
            .eq("user_id", self.user_id).execute().data
        )
        if not rows:
            raise RoteiroError(404, "Conversa não encontrada")
        return str(conversa_id)

    def _get_row(self, roteiro_id: str) -> dict[str, Any]:
        rows = (
            self._table().select(ROTEIRO_COLS).eq("id", roteiro_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise RoteiroError(404, "Roteiro não encontrado")
        return rows[0]

    async def _viral_for(self, viral_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not viral_id:
            return None
        return (await viral_cards(self.db, self.org_id, self.storage, [viral_id])).get(str(viral_id))

    async def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        post = post_refs(self.db, self.org_id, "roteiro_id", [row["id"]]).get(str(row["id"]))
        aprovacao = present_estado(self.approvals.state(self.org_id, SUBJECT_KIND, str(row["id"])))
        return present_roteiro(row, await self._viral_for(row.get("viral_id")), post, aprovacao)

    def _usage_hoje(self) -> int:
        """Roteiros this user created in the rolling window (capped read: never needs more than the cap)."""
        cap = int(self.cfg.roteiros_dia_usuario)
        rows = (
            self._table().select("id")
            .eq("org_id", self.org_id).eq("created_by", self.user_id)
            .gte("created_at", _iso(_now() - WINDOW)).limit(cap).execute().data or []
        )
        return len(rows)

    async def _assert_pode_gerar(self) -> None:
        """Refusals shared by every path that spends LLM money, BEFORE a row is written."""
        geracao_jobs.assert_geracao_disponivel(self.cfg)
        self.ia_check(self.org_id)
        await geracao_jobs.assert_orcamento_ia(self.org_id)
        if self._usage_hoje() >= int(self.cfg.roteiros_dia_usuario):
            raise RoteiroError(
                429, "Limite diário de roteiros atingido", headers={"Retry-After": str(RETRY_AFTER_S)}
            )

    async def _enqueue(self, roteiro_id: str, job_type: str) -> str:
        if self.jobs is None:
            raise RoteiroError(503, {"code": "geracao_indisponivel", "detail": "A geração está indisponível no momento."})
        try:
            queued = await self.jobs.enqueue(
                type=job_type, payload={"roteiro_id": roteiro_id},
                dedupe_key=f"{job_type}:{roteiro_id}", max_retries=2,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as 503, row settled as falha
            logger.error("roteiro: enqueue %s failed for %s: %s", job_type, roteiro_id, exc)
            self._table().update({
                "status": "falha", "erro": "Falha ao iniciar a geração", "etapa": None, "finished_at": _iso(_now()),
            }).eq("id", roteiro_id).eq("org_id", self.org_id).execute()
            raise RoteiroError(
                503, {"code": "geracao_indisponivel", "detail": "Falha ao iniciar a geração. Tente novamente."}
            ) from exc
        return queued.id

    def _patch(self, roteiro_id: str, patch: dict[str, Any], *, where_status: Optional[list[str]] = None) -> dict[str, Any]:
        q = self._table().update({**patch, "updated_at": _iso(_now())}).eq("id", roteiro_id).eq("org_id", self.org_id)
        if where_status:
            q = q.in_("status", where_status)
        rows = q.execute().data
        if not rows:
            raise RoteiroError(409, "O roteiro mudou; recarregue a página")
        return rows[0]

    # Esteira binding (contract 3.5)

    def _post_para_vinculo(self, body: Any, marca_id: str) -> Optional[dict[str, Any]]:
        """The post a new roteiro will bind to, validated BEFORE anything is written or spent."""
        if not body.post_id:
            return None
        rows = (
            self.db.table(POSTS).select("id,marca_id,headline_id,roteiro_id")
            .eq("id", str(body.post_id)).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise RoteiroError(404, "Post não encontrado")
        post = rows[0]
        if str(post["marca_id"]) != marca_id:
            raise RoteiroError(422, {"code": "post_de_outra_marca", "detail": "O post pertence a outra marca"})
        if post.get("roteiro_id") and not body.substituir:
            raise RoteiroError(
                409,
                {"code": "post_ja_tem_roteiro", "detail": "Este post já tem um roteiro", "roteiro_id": str(post["roteiro_id"])},
            )
        return post

    def _vincular_novo(self, post: dict[str, Any], roteiro_id: str) -> None:
        """Bind the new row to the post. The write only lands if the post still holds the roteiro we
        read (or none): a post that moved on in between is a 409 and the orphan row is dropped."""
        atual = post.get("roteiro_id")
        q = (
            self.db.table(POSTS).update({"roteiro_id": roteiro_id, "updated_at": _iso(_now())})
            .eq("id", str(post["id"])).eq("org_id", self.org_id)
        )
        q = q.eq("roteiro_id", str(atual)) if atual else q.is_("roteiro_id", "null")
        if not q.execute().data:
            self._table().delete().eq("id", roteiro_id).eq("org_id", self.org_id).execute()
            raise RoteiroError(409, {"code": "post_mudou", "detail": "O post mudou; recarregue a página"})

    def _post_do_roteiro(self, roteiro_id: str) -> Optional[str]:
        rows = self.db.table(POSTS).select("id").eq("roteiro_id", roteiro_id).eq("org_id", self.org_id).execute().data
        return str(rows[0]["id"]) if rows else None

    def _transferir_vinculo(self, post_id: str, antigo: str, novo: str) -> None:
        """``cs_rebind_roteiro``: row-locked take-over; false = the post's roteiro changed meanwhile."""
        data = self.db.rpc(
            REBIND_RPC, {"p_org": self.org_id, "p_post": post_id, "p_old": antigo, "p_new": novo},
        ).execute().data
        if isinstance(data, list):
            data = data[0] if data else None
        if data is not True:
            self._table().delete().eq("id", novo).eq("org_id", self.org_id).execute()
            raise RoteiroError(409, {"code": "post_mudou", "detail": "O post mudou; recarregue a página"})

    # reads

    def list(self, marca_id: str, *, q: Optional[str], limit: int, offset: int) -> dict[str, Any]:
        self.assert_marca(marca_id)
        query = (
            self._table().select("id,nome,headline_texto,headline_id,status,created_at", count="exact")
            .eq("org_id", self.org_id).eq("marca_id", marca_id)
        )
        if q and q.strip():
            # PostgREST `or` grammar: strip its separators/quotes/wildcards from the user's term.
            termo = " ".join("".join(c for c in q if c not in '%*,()"\\').split())
            if termo:
                query = query.or_(f'nome.ilike."*{termo}*",headline_texto.ilike."*{termo}*"')
        res = query.order("created_at", desc=True).order("id").range(offset, offset + limit - 1).execute()
        rows = res.data or []
        total = res.count if getattr(res, "count", None) is not None else len(rows)
        posts = post_refs(self.db, self.org_id, "roteiro_id", [r["id"] for r in rows])
        return {"items": [present_resumo(r, posts.get(str(r["id"]))) for r in rows], "total": total}

    async def get(self, roteiro_id: str) -> dict[str, Any]:
        return await self._present(self._get_row(roteiro_id))

    # writes

    async def create(self, body: Any) -> dict[str, Any]:
        if body.fonte != "ia":
            # NOC-REMEDIATE[roteiro-web-search] / NOC-REMEDIATE[roteiro-link-source] (module docstring)
            raise RoteiroError(422, "Fonte ainda não disponível")
        marca_id = str(body.marca_id)
        self.assert_marca(marca_id)
        if body.headline_id:
            self._exists(HEADLINES, str(body.headline_id), "Headline não encontrada", marca_id=marca_id)
        if body.brain_id:
            self._exists(BRAINS, str(body.brain_id), "Cérebro não encontrado")
        formato, estrutura_ids = self._estruturas_do_pedido(body)
        conversa_id = self._assert_conversa(getattr(body, "conversa_id", None))
        # EST-RO: ``viral_id`` is deprecated and ignored when Estruturas are given
        viral_id = None if estrutura_ids else (str(body.viral_id) if body.viral_id else None)
        if viral_id:
            self._exists(VIRAIS, viral_id, "Vídeo viral não encontrado")
        headline = body.headline_texto.strip()
        if not headline:
            raise RoteiroError(422, "Informe a headline")
        post = self._post_para_vinculo(body, marca_id)
        await self._assert_pode_gerar()

        roteiro_id = str(uuid.uuid4())
        # Inside a post the roteiro is written for the post's own headline (contract 3.5).
        headline_id = str((post or {}).get("headline_id") or body.headline_id or "") or None
        pergunta_primeiro = bool(body.gerar_perguntas)
        row = {
            "id": roteiro_id, "org_id": self.org_id, "marca_id": marca_id, "created_by": self.user_id,
            "nome": _default_nome(headline), "headline_id": headline_id,
            "headline_texto": headline, "instrucoes": body.instrucoes.strip(), "fonte": "ia",
            "duracao": body.duracao, "estrutura": body.estrutura,
            "brain_id": str(body.brain_id) if body.brain_id else None,
            "viral_id": viral_id, "perguntas": [], "formato": formato, "estrutura_ids": estrutura_ids,
            "conversa_id": conversa_id,
            "status": "criando" if pergunta_primeiro else "processando",
            "etapa": ETAPA_PERGUNTAS if pergunta_primeiro else ETAPA_GERANDO,
            "conteudo": "", "versao": 1, "modelo": self.cfg.geracao_llm_model,
            "created_at": _iso(_now()), "updated_at": _iso(_now()),
        }
        inserted = self._table().insert(row).execute().data
        saved = inserted[0] if inserted else row
        if post is not None:
            self._vincular_novo(post, roteiro_id)
        queue_id = await self._enqueue(roteiro_id, JOB_PERGUNTAS if pergunta_primeiro else JOB_GERAR)
        upd = self._table().update({"queue_job_id": queue_id}).eq("id", roteiro_id).eq("org_id", self.org_id).execute().data
        return await self._present(upd[0] if upd else {**saved, "queue_job_id": queue_id})

    async def responder(self, roteiro_id: str, respostas: list[Any]) -> dict[str, Any]:
        row = self._get_row(roteiro_id)
        if row["status"] != "perguntas":
            raise RoteiroError(409, "O roteiro não está aguardando respostas")
        perguntas = list(row.get("perguntas") or [])
        known = {p["id"] for p in perguntas}
        by_id: dict[str, str] = {}
        for r in respostas:
            if r.id not in known:
                raise RoteiroError(422, "Pergunta não encontrada neste roteiro")
            by_id[r.id] = r.resposta.strip()
        merged = [{**p, "resposta": by_id.get(p["id"], p.get("resposta") or "")} for p in perguntas]
        saved = self._patch(roteiro_id, {"perguntas": merged}, where_status=["perguntas"])
        return await self._present({**row, **saved})

    async def gerar(self, roteiro_id: str, *, pular_perguntas: bool) -> dict[str, Any]:
        row = self._get_row(roteiro_id)
        permitido = ["perguntas", "criando"] if pular_perguntas else ["perguntas"]
        if row["status"] not in permitido:
            raise RoteiroError(409, "O roteiro não pode ser gerado neste estado")
        geracao_jobs.assert_geracao_disponivel(self.cfg)
        self.ia_check(self.org_id)
        await geracao_jobs.assert_orcamento_ia(self.org_id)
        patch: dict[str, Any] = {"status": "processando", "etapa": ETAPA_GERANDO, "erro": None}
        if pular_perguntas:
            patch["perguntas"] = []
        saved = self._patch(roteiro_id, patch, where_status=permitido)
        queue_id = await self._enqueue(roteiro_id, JOB_GERAR)
        upd = self._table().update({"queue_job_id": queue_id}).eq("id", roteiro_id).eq("org_id", self.org_id).execute().data
        return await self._present({**row, **saved, **(upd[0] if upd else {"queue_job_id": queue_id})})

    async def salvar(self, roteiro_id: str, body: Any) -> dict[str, Any]:
        row = self._get_row(roteiro_id)
        if row["status"] != "completo":
            raise RoteiroError(409, "O roteiro ainda não está pronto para edição")
        if int(row.get("versao") or 1) != body.expected_versao:
            raise RoteiroError(409, "O roteiro mudou; recarregue a página")
        patch: dict[str, Any] = {"versao": body.expected_versao + 1}
        if body.nome is not None:
            patch["nome"] = body.nome.strip()
        if body.conteudo is not None:
            patch["conteudo"] = body.conteudo
        # Optimistic concurrency: the write only lands if nobody bumped `versao` in between.
        rows = (
            self._table().update({**patch, "updated_at": _iso(_now())})
            .eq("id", roteiro_id).eq("org_id", self.org_id).eq("versao", body.expected_versao).execute().data
        )
        if not rows:
            raise RoteiroError(409, "O roteiro mudou; recarregue a página")
        # Editing invalidates a previous decision: the new versao is submitted (pending) and must be approved again.
        self._submeter(roteiro_id, int(rows[0].get("versao") or body.expected_versao + 1), NOTA_EDITADO)
        return await self._present({**row, **rows[0]})

    # approval (CoreStudio S3): any org member decides; approval is always required

    def _submeter(self, roteiro_id: str, versao: int, nota: str) -> None:
        try:
            self.approvals.submit(self.org_id, SUBJECT_KIND, roteiro_id, versao, actor_id=self.user_id, note=nota)
        except ApprovalError as exc:
            raise self._aprovacao_erro(exc) from exc

    @staticmethod
    def _aprovacao_erro(exc: ApprovalError) -> RoteiroError:
        return RoteiroError(exc.status_code, {"code": exc.code, "message": exc.message})

    def _row_aprovavel(self, roteiro_id: str) -> dict[str, Any]:
        row = self._get_row(roteiro_id)
        if row["status"] != "completo":
            raise RoteiroError(409, {"code": "roteiro_incompleto", "message": "O roteiro ainda não está pronto para aprovação."})
        # Idempotent: a roteiro whose generation-time submit was lost (or that predates this feature) is submitted now.
        self._submeter(roteiro_id, int(row.get("versao") or 1), NOTA_GERADO)
        return row

    async def aprovacao(self, roteiro_id: str) -> dict[str, Any]:
        self._get_row(roteiro_id)
        return present_estado(self.approvals.state(self.org_id, SUBJECT_KIND, roteiro_id))

    async def solicitar_aprovacao(self, roteiro_id: str) -> dict[str, Any]:
        try:
            return solicitar_aprovacao_roteiro(self.db, self.org_id, roteiro_id, actor_id=self.user_id, approvals=self.approvals)
        except AprovacaoRoteiroError as exc:
            raise RoteiroError(exc.status, {"code": exc.codigo, "message": exc.mensagem}) from exc
        except ApprovalError as exc:
            raise self._aprovacao_erro(exc) from exc

    async def aprovar(self, roteiro_id: str, versao: int) -> dict[str, Any]:
        self._row_aprovavel(roteiro_id)
        try:
            state = self.approvals.approve(self.org_id, SUBJECT_KIND, roteiro_id, versao, actor_id=self.user_id)
        except ApprovalError as exc:
            raise self._aprovacao_erro(exc) from exc
        return present_estado(state)

    async def reprovar(self, roteiro_id: str, versao: int, motivo: Optional[str]) -> dict[str, Any]:
        self._row_aprovavel(roteiro_id)
        try:
            state = self.approvals.reject(self.org_id, SUBJECT_KIND, roteiro_id, versao, actor_id=self.user_id, motivo=motivo)
        except ApprovalError as exc:
            raise self._aprovacao_erro(exc) from exc
        return present_estado(state)

    async def feedback(self, roteiro_id: str, feedback: str, motivo: Optional[str]) -> dict[str, Any]:
        row = self._get_row(roteiro_id)
        if row["status"] != "completo":
            raise RoteiroError(409, "O feedback só vale para roteiros concluídos")
        saved = self._patch(
            roteiro_id,
            {"feedback": feedback, "feedback_motivo": (motivo or "").strip() or None},
            where_status=["completo"],
        )
        return await self._present({**row, **saved})

    async def reprocessar(self, roteiro_id: str, instrucoes_adicionais: Optional[str]) -> dict[str, Any]:
        origem = self._get_row(roteiro_id)
        if origem["status"] not in ("completo", "falha"):
            raise RoteiroError(409, "Aguarde o roteiro terminar para reprocessar")
        instrucoes = (origem.get("instrucoes") or "").strip()
        extra = (instrucoes_adicionais or "").strip()
        if extra:
            instrucoes = f"{instrucoes}\n\n{extra}".strip()
        if len(instrucoes) > MAX_INSTRUCOES:
            raise RoteiroError(422, f"As instruções passam de {MAX_INSTRUCOES} caracteres")
        await self._assert_pode_gerar()
        novo_id = str(uuid.uuid4())
        row = {
            "id": novo_id, "org_id": self.org_id, "marca_id": origem["marca_id"], "created_by": self.user_id,
            "nome": origem["nome"][:MAX_NOME], "headline_id": origem.get("headline_id"),
            "headline_texto": origem["headline_texto"], "instrucoes": instrucoes, "fonte": origem.get("fonte") or "ia",
            "duracao": origem.get("duracao") or "auto", "estrutura": origem.get("estrutura") or ESTRUTURA_PADRAO,
            "brain_id": origem.get("brain_id"),
            "viral_id": origem.get("viral_id"), "perguntas": list(origem.get("perguntas") or []),
            "status": "processando", "etapa": ETAPA_GERANDO, "conteudo": "", "versao": 1,
            "modelo": self.cfg.geracao_llm_model, "created_at": _iso(_now()), "updated_at": _iso(_now()),
        }
        inserted = self._table().insert(row).execute().data
        saved = inserted[0] if inserted else row
        post_id = self._post_do_roteiro(roteiro_id)
        if post_id:
            self._transferir_vinculo(post_id, roteiro_id, novo_id)
        queue_id = await self._enqueue(novo_id, JOB_GERAR)
        upd = self._table().update({"queue_job_id": queue_id}).eq("id", novo_id).eq("org_id", self.org_id).execute().data
        return await self._present(upd[0] if upd else {**saved, "queue_job_id": queue_id})

    def excluir(self, ids: list[str]) -> dict[str, Any]:
        rows = self._table().delete().in_("id", ids).eq("org_id", self.org_id).execute().data or []
        return {"excluidos": len(rows)}


# ── queue handlers ────────────────────────────────────────────────────────────


def _fetch(db, roteiro_id: str) -> Optional[dict[str, Any]]:
    rows = db.table(ROTEIROS).select("*").eq("id", roteiro_id).execute().data
    return rows[0] if rows else None


def _settle(db, roteiro_id: str, patch: dict[str, Any], *, from_status: list[str]) -> bool:
    """Conditional update: only a row still in ``from_status`` moves. Returns whether it moved."""
    rows = (
        db.table(ROTEIROS).update({**patch, "updated_at": _iso(_now())})
        .eq("id", roteiro_id).in_("status", from_status).execute().data
    )
    return bool(rows)


def _falha(db, roteiro_id: str, mensagem: str, *, from_status: list[str]) -> None:
    _settle(
        db, roteiro_id,
        {"status": "falha", "erro": mensagem, "etapa": None, "finished_at": _iso(_now())},
        from_status=from_status,
    )


def _contexto(db, row: dict[str, Any]) -> dict[str, Any]:
    """The untrusted-material inputs of a prompt: profile, brain content, viral reference text."""
    perfil = db.table(MARCA_PERFIL).select("bio,apresentacao_magnetica,ctas").eq("marca_id", row["marca_id"]).execute().data
    perfil = perfil[0] if perfil else {}
    cerebro = None
    if row.get("brain_id"):
        b = db.table(BRAINS).select("content").eq("id", row["brain_id"]).eq("org_id", row["org_id"]).execute().data
        cerebro = (b[0].get("content") if b else None) or None
    referencia = None
    if row.get("viral_id"):
        v = (
            db.table(VIRAIS).select("transcricao_texto,caption")
            .eq("id", row["viral_id"]).eq("org_id", row["org_id"]).execute().data
        )
        if v:
            referencia = (v[0].get("transcricao_texto") or v[0].get("caption") or "").strip() or None
    return {
        "bio": perfil.get("bio") or "",
        "apresentacao_magnetica": perfil.get("apresentacao_magnetica") or "",
        "ctas": perfil.get("ctas") or "",
        "cerebro": cerebro,
        "referencia_viral": referencia,
    }


def _ultima_tentativa(job: Job) -> bool:
    return int(job.retry_count) >= int(job.max_retries)


async def executar_perguntas(
    job: Job, *, db: Any, llm: RoteiroLlm, jobs: Optional[JobRepository] = None,
) -> None:
    """``roteiro.perguntas``: 3-5 questions -> ``perguntas``; ANY failure of the questions step falls
    through to ``processando`` with no questions (and the UI is told), per contract 6.1."""
    roteiro_id = str(job.payload.get("roteiro_id") or "")
    row = _fetch(db, roteiro_id) if roteiro_id else None
    if row is None:
        raise DeadLetterError(f"roteiro {roteiro_id or '?'} não existe")
    if row["status"] != "criando":
        return  # already moved on (skipped by the user, failed by the sweep): nothing to do
    ctx = _contexto(db, row)
    perguntas: list[str] = []
    try:
        reply = await llm(
            ROTEIRO_PERGUNTAS_SYSTEM_PROMPT,
            build_perguntas_user_message(
                headline=row["headline_texto"], instrucoes=row.get("instrucoes") or "", bio=ctx["bio"],
                duracao=row.get("duracao") or "auto", cerebro=ctx["cerebro"], referencia_viral=ctx["referencia_viral"],
            ),
            row["org_id"],
        )
        perguntas = parse_perguntas(reply)
    except (PerguntasParseError, LLMNotConfigured, LLMBudgetExceeded) as exc:
        logger.warning("roteiro %s: sem perguntas (%s)", roteiro_id, exc)
    except Exception as exc:  # noqa: BLE001 - the questions are optional; the script is the product
        logger.warning("roteiro %s: perguntas falharam (%s: %s)", roteiro_id, type(exc).__name__, exc)

    if perguntas:
        _settle(
            db, roteiro_id,
            {
                "status": "perguntas", "etapa": ETAPA_AGUARDANDO,
                "perguntas": [{"id": uuid.uuid4().hex[:8], "pergunta": q, "resposta": ""} for q in perguntas],
            },
            from_status=["criando"],
        )
        return
    if _settle(db, roteiro_id, {"status": "processando", "etapa": MSG_SEM_PERGUNTAS}, from_status=["criando"]):
        repo = jobs or geracao_jobs.make_jobs_repository(db)
        await repo.enqueue(
            type=JOB_GERAR, payload={"roteiro_id": roteiro_id},
            dedupe_key=f"{JOB_GERAR}:{roteiro_id}", max_retries=2,
        )


async def executar_geracao(job: Job, *, db: Any, llm: RoteiroLlm, cfg: Any = None) -> None:
    """``roteiro.gerar``: the script -> ``completo``."""
    if cfg is None:
        from app.config import settings as cfg
    roteiro_id = str(job.payload.get("roteiro_id") or "")
    row = _fetch(db, roteiro_id) if roteiro_id else None
    if row is None:
        raise DeadLetterError(f"roteiro {roteiro_id or '?'} não existe")
    if row["status"] != "processando":
        return
    formato = row.get("formato") or "reels"
    estrutura_ids = [str(e) for e in (row.get("estrutura_ids") or [])]
    if formato != "reels" or estrutura_ids:
        # EST-RO: every format, and the Estruturas' block order; the legacy reels path below stays byte-identical
        await _gerar_por_formato(job, db=db, llm=llm, cfg=cfg, row=row, formato=formato, estrutura_ids=estrutura_ids)
        return
    # A row written before migration 250 has no ``estrutura``: it was generated with the cta_inicio
    # order (the column's default). A value outside the contract fails the row loudly, never a fallback.
    estrutura = row.get("estrutura") or ESTRUTURA_PADRAO
    if estrutura not in ESTRUTURAS:
        logger.error("roteiro %s: estrutura desconhecida %r", roteiro_id, estrutura)
        _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
        return
    ctx = _contexto(db, row)
    try:
        reply = await llm(
            system_prompt(estrutura),
            build_geracao_user_message(
                headline=row["headline_texto"], instrucoes=row.get("instrucoes") or "",
                duracao=row.get("duracao") or "auto", perguntas=list(row.get("perguntas") or []),
                bio=ctx["bio"], apresentacao_magnetica=ctx["apresentacao_magnetica"], ctas=ctx["ctas"],
                cerebro=ctx["cerebro"], referencia_viral=ctx["referencia_viral"],
            ),
            row["org_id"],
        )
    except LLMNotConfigured:
        _falha(db, roteiro_id, MSG_IA_NAO_CONFIGURADA, from_status=["processando"])
        return
    except LLMBudgetExceeded:
        _falha(db, roteiro_id, MSG_ORCAMENTO, from_status=["processando"])
        return
    except Exception as exc:  # noqa: BLE001 - retry until the last attempt, then settle the row
        logger.error("roteiro %s: geração falhou (%s: %s)", roteiro_id, type(exc).__name__, exc)
        if _ultima_tentativa(job):
            _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
            return
        raise
    conteudo = (reply or "").strip()
    if not conteudo:
        logger.error("roteiro %s: a IA devolveu um roteiro vazio", roteiro_id)
        _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
        return
    # S6 guard: schema + length caps + no URLs / storage paths. A rejected output is a coded `falha`, never trimmed.
    try:
        conteudo = validar_roteiro(conteudo)["conteudo"]
    except SaidaIaFalha as falha:
        logger.error("roteiro %s: saída da IA rejeitada (%s)", roteiro_id, falha)
        _falha(db, roteiro_id, MSG_SAIDA_INVALIDA.format(codigo=falha.codigo), from_status=["processando"])
        return
    if len(conteudo) > MAX_CONTEUDO:  # unreachable while MAX_ROTEIRO <= MAX_CONTEUDO; kept as a loud guard, not a trim
        _falha(db, roteiro_id, MSG_SAIDA_INVALIDA.format(codigo="saida_limite_excedido"), from_status=["processando"])
        return
    moved = _settle(
        db, roteiro_id,
        {
            "status": "completo", "etapa": None, "erro": None, "conteudo": conteudo, "conteudo_original": conteudo,
            "modelo": cfg.geracao_llm_model, "prompt_versao": prompt_versao(estrutura), "finished_at": _iso(_now()),
        },
        from_status=["processando"],
    )
    if moved:
        _submeter_geracao(db, row, versao=1)


async def _chamar_llm(job: Job, db: Any, llm: RoteiroLlm, row: dict[str, Any], system: str, user: str) -> Optional[str]:
    """The model call with the same settle rules as the legacy path; ``None`` when the row was settled as ``falha``."""
    roteiro_id = str(row["id"])
    try:
        reply = await llm(system, user, row["org_id"])
    except LLMNotConfigured:
        _falha(db, roteiro_id, MSG_IA_NAO_CONFIGURADA, from_status=["processando"])
        return None
    except LLMBudgetExceeded:
        _falha(db, roteiro_id, MSG_ORCAMENTO, from_status=["processando"])
        return None
    except Exception as exc:  # noqa: BLE001 - retry until the last attempt, then settle the row
        logger.error("roteiro %s: geração falhou (%s: %s)", roteiro_id, type(exc).__name__, exc)
        if _ultima_tentativa(job):
            _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
            return None
        raise
    return reply


def _evento_roteiro(db: Any, row: dict[str, Any], tipo: str, contagem: int) -> None:
    """A content-free event of a chat roteiro (``cs_fluxo_eventos`` needs the conversation; elsewhere it is logged)."""
    if not row.get("conversa_id"):
        logger.warning("roteiro %s: %s (%s) fora de uma conversa", row.get("id"), tipo, contagem)
        return
    db.table(FLUXO_EVENTOS).insert({
        "id": str(uuid.uuid4()), "org_id": row["org_id"], "marca_id": row["marca_id"], "conversa_id": row["conversa_id"],
        "roteiro_id": row["id"], "proposta_id": row.get("proposta_id"), "ator_id": row.get("created_by"), "tipo": tipo,
        "contagem": int(contagem),
    }).execute()


def _gravar_usos(db: Any, row: dict[str, Any], estruturas: list[Any], separada: Any) -> None:
    """EST-RO usos (estruturas-contract 6.7): one ``cs_estrutura_usos`` row per offered Estrutura (principal first),
    ``bloco_ids`` = the block names the model attributed that match the Estrutura's own blocks. A missing sentinel is
    ``atribuicao_ausente``; unmatched citations are counted in ``citacao_rejeitada``. Never a failure."""
    if not estruturas:
        return
    ids = [e.id for e in estruturas]
    blocos = db.table(ESTRUTURA_BLOCOS).select("id,estrutura_id,nome").in_("estrutura_id", ids).execute().data or []
    oferecidas: dict[str, dict[str, str]] = {e.codigo: {} for e in estruturas}
    codigo_de = {e.id: e.codigo for e in estruturas}
    for b in blocos:
        oferecidas[codigo_de[str(b["estrutura_id"])]][str(b["id"])] = b["nome"]
    resolvidos = roteiro_formatos.resolver_usos(separada.usos, oferecidas)
    ja = {
        str(u["estrutura_id"])
        for u in db.table(USOS).select("estrutura_id").eq("roteiro_id", row["id"]).execute().data or []
    }
    novos = [
        {"id": str(uuid.uuid4()), "org_id": row["org_id"], "marca_id": row["marca_id"], "estrutura_id": e.id,
         "contexto": "chat" if row.get("conversa_id") else "roteiro_avancado",
         "papel": "principal" if i == 1 else "mistura", "ordem": i,
         "bloco_ids": list(resolvidos.blocos_por_codigo.get(e.codigo, ())), "roteiro_id": row["id"],
         "headline_id": None, "proposta_id": row.get("proposta_id"), "created_by": row.get("created_by")}
        for i, e in enumerate(estruturas, start=1) if e.id not in ja
    ]
    if novos:
        db.table(USOS).insert(novos).execute()
    if not separada.sentinela_presente:
        _evento_roteiro(db, row, "atribuicao_ausente", 1)
    if resolvidos.rejeitados:
        _evento_roteiro(db, row, "citacao_rejeitada", resolvidos.rejeitados)


async def _gerar_por_formato(
    job: Job, *, db: Any, llm: RoteiroLlm, cfg: Any, row: dict[str, Any], formato: str, estrutura_ids: list[str],
) -> None:
    """``roteiro.gerar`` for a non-reels formato or a roteiro that follows Estruturas (EST-RO 6.7, prompts EST-FMT 8.7)."""
    roteiro_id = str(row["id"])
    ordem_cta = row.get("estrutura") or ESTRUTURA_PADRAO
    if ordem_cta not in ESTRUTURAS or (formato != "reels" and formato not in roteiro_formatos.PROMPT_VERSOES):
        logger.error("roteiro %s: estrutura/formato desconhecido (%r, %r)", roteiro_id, ordem_cta, formato)
        _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
        return
    estruturas = carregar_estruturas(db, estrutura_ids)
    if len(estruturas) != len(estrutura_ids):  # deleted after the request was accepted: loud, never a silent fallback
        logger.error("roteiro %s: %d de %d Estruturas não existem mais", roteiro_id, len(estrutura_ids) - len(estruturas), len(estrutura_ids))
        _falha(db, roteiro_id, MSG_IA_FALHOU, from_status=["processando"])
        return
    ctx = _contexto(db, row)
    reply = await _chamar_llm(
        job, db, llm, row,
        roteiro_formatos.system_prompt(formato, com_estruturas=bool(estruturas), ordem_cta=ordem_cta),
        roteiro_formatos.build_user_message(
            formato, headline=row["headline_texto"], estruturas=[renderizar_estrutura(e) for e in estruturas],
            instrucoes=row.get("instrucoes") or "", duracao=row.get("duracao") or "auto",
            perguntas=list(row.get("perguntas") or []), bio=ctx["bio"],
            apresentacao_magnetica=ctx["apresentacao_magnetica"], ctas=ctx["ctas"], cerebro=ctx["cerebro"],
        ),
    )
    if reply is None:
        return
    separada = roteiro_formatos.separar_sentinela((reply or "").strip())
    try:
        if formato == "reels":
            conteudo = validar_roteiro(separada.roteiro)["conteudo"]
        else:
            conteudo = validar_roteiro_formato(formato, separada.roteiro, headline=row["headline_texto"])["conteudo"]
    except SaidaIaFalha as falha:
        logger.error("roteiro %s: saída da IA rejeitada (%s)", roteiro_id, falha)
        _falha(db, roteiro_id, MSG_SAIDA_INVALIDA.format(codigo=falha.codigo), from_status=["processando"])
        return
    if not conteudo or len(conteudo) > MAX_CONTEUDO:
        _falha(db, roteiro_id, MSG_SAIDA_INVALIDA.format(codigo="saida_limite_excedido"), from_status=["processando"])
        return
    moved = _settle(
        db, roteiro_id,
        {
            "status": "completo", "etapa": None, "erro": None, "conteudo": conteudo, "conteudo_original": conteudo,
            "modelo": cfg.geracao_llm_model, "prompt_versao": roteiro_formatos.prompt_versao(formato, ordem_cta),
            "finished_at": _iso(_now()),
        },
        from_status=["processando"],
    )
    if moved:
        _gravar_usos(db, row, estruturas, separada)
        _submeter_geracao(db, row, versao=1)


def _submeter_geracao(db: Any, row: dict[str, Any], *, versao: int) -> None:
    """T3: the generated versao goes up for approval (event ``submitted`` = ``roteiro_gerado``).

    Not fatal: the roteiro is already ``completo`` and a retry would see it settled, so a lost submit is healed by the
    idempotent submit every approval call (and the Esteira gate's ``roteiro_nao_aprovado``) performs. It is logged at error."""
    try:
        make_approvals(db).submit(str(row["org_id"]), SUBJECT_KIND, str(row["id"]), versao, actor_id=None, note=NOTA_GERADO)
    except Exception:  # noqa: BLE001 - healed by the idempotent submit on the next approval call; never fails the job
        logger.exception("roteiro %s: falha ao submeter a versao %s para aprovação", row.get("id"), versao)


def reconcile_dead_letter(db: Any, job: Job) -> None:
    """A dead-lettered roteiro job can never finish: its row goes to ``falha`` (idempotent)."""
    roteiro_id = str((job.payload or {}).get("roteiro_id") or "")
    if roteiro_id:
        _falha(db, roteiro_id, MSG_JOB_FAILED, from_status=["criando", "processando"])


def _admin_db():
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client()


async def _handle_perguntas(job: Job) -> None:
    await executar_perguntas(job, db=_admin_db(), llm=get_roteiro_llm())


async def _handle_gerar(job: Job) -> None:
    await executar_geracao(job, db=_admin_db(), llm=get_roteiro_llm())


def register_handlers() -> None:
    """Register both handlers (+ reconciler) with the ``geracao`` worker. Idempotent; runs at import."""
    geracao_jobs.register_handler(JOB_PERGUNTAS, _handle_perguntas, on_dead_letter=reconcile_dead_letter)
    geracao_jobs.register_handler(JOB_GERAR, _handle_gerar, on_dead_letter=reconcile_dead_letter)


register_handlers()

__all__ = [
    "RoteiroError",
    "RoteiroService",
    "executar_geracao",
    "executar_perguntas",
    "get_roteiro_ia_check",
    "get_roteiro_llm",
    "present_roteiro",
    "reconcile_dead_letter",
]
