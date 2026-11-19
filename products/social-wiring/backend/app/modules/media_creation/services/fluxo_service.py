"""The chat -> headline -> roteiro -> card flow (``specs/estruturas-contract.md`` section 9, UNI-1a part).

This slice owns the proposta persistence and **steps 1-3** of the ``escolher`` saga (section 9.2):

1. **claim** -- ``cs_chat_proposta_reivindicar`` (one transaction, row-locked): ``status='escolhida'`` + a 60 s resume
   lease. A concurrent double click loses the claim and gets the current state back (``ja_existia``), never a second headline.
2. **headline** -- ``cs_chat_proposta_salvar_headline`` (one transaction): the ``cs_headlines`` row (``favorita``,
   ``conversa_id``, ``proposta_id``; UNIQUE makes a retry a lookup), one ``cs_estrutura_usos`` row per cited Estrutura,
   ``fluxo_etapa='headline_salva'`` and the ``headline_salva`` event.
3. **pre-flight** -- fail fast, BEFORE anything expensive: worker on, IA key, IA budget, the daily roteiro cap. A refusal
   leaves the headline saved (``fluxo_etapa='headline_salva'``), gives the lease back and returns the coded error; the
   user retries the same click later.

Steps 4-7 (roteiro through ``RoteiroService``, the Esteira card, the finalizer job, the ``roteiro_gerado`` message; for
a chosen roteiro the generated headline job first) are ``services/fluxo_continuacao.py`` (RP-3), plugged in through the
seam :attr:`FluxoService.continuacao` by ``routers/chat.py``. A roteiro proposta (16.6) saves the script at step 2
(``cs_chat_proposta_salvar_roteiro``) and is held to the daily headline cap at step 3.

Every state change writes its intent-named ``cs_fluxo_eventos`` row in the SAME transaction (inside the RPCs); this
module never writes an event by hand.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from noctusai_lib.integrations.persistence.table_reads import batched

from app.config import settings
from app.modules.media_creation.limites_geracao import limite_geracao
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.chat_contexto import ChatError
from app.modules.media_creation.services.estruturas_service import _rpc_detalhes
from app.modules.media_creation.services.post_ref import post_refs
from app.modules.media_creation.services.roteiro_service import RoteiroError, check_ia_configurada

logger = logging.getLogger(__name__)

CONVERSAS = "cs_chat_conversas"
MENSAGENS = "cs_chat_mensagens"
PROPOSTAS = "cs_chat_propostas"
PROPOSTA_ESTRUTURAS = "cs_chat_proposta_estruturas"
EVENTOS = "cs_fluxo_eventos"
HEADLINES = "cs_headlines"
ROTEIROS = "cs_roteiros"
POSTS = "cs_posts"
ESTRUTURAS = "cs_estruturas"
PERFIS = "cs_perfis_monitorados"
USOS = "cs_estrutura_usos"

PROPOSTA_COLS = (
    "id,org_id,marca_id,conversa_id,mensagem_id,ordem,texto,gatilho_tag,status,fluxo_etapa,fluxo_erro_codigo,"
    "fluxo_lease_ate,headline_id,tipo,titulo,formato,roteiro_id"
)
ROTEIRO_COLS = "id,nome,status,formato,duracao,estrutura,versao"

LEASE_SEGUNDOS = 60
#: The saga's rolling-window cap on roteiros per user (the same window ``RoteiroService`` counts).
JANELA_ROTEIROS = timedelta(hours=24)
RETRY_AFTER_ROTEIROS_S = 3600
FORMULA_TRECHO_MAX = 80

MSG_PROPOSTA_NAO_ENCONTRADA = "Headline não encontrada."
MSG_ROTEIRO_PRIMEIRO_INDISPONIVEL = "Ainda não consigo criar a headline a partir deste roteiro. Tente novamente mais tarde."

#: ``Fluxo.direcao`` (contract 16.1): the proposta's ``tipo`` decides it, never a client flag.
DIRECAO_POR_TIPO = {"headline": "headline_primeiro", "roteiro": "roteiro_primeiro"}
MSG_LIMITE_ROTEIROS = "Limite diário de roteiros atingido. Tente novamente mais tarde."
MSG_LIMITE_HEADLINES = "Limite diário de headlines atingido. Tente novamente mais tarde."
MSG_IA_NAO_CONFIGURADA = "A IA não está configurada para esta conta."

#: RAISE EXCEPTION '<code>' of the migration's RPCs -> (status, code, pt-BR message).
_RPC_ERROS: dict[str, tuple[int, str, str]] = {
    "proposta_nao_encontrada": (404, "proposta_nao_encontrada", MSG_PROPOSTA_NAO_ENCONTRADA),
    "headline_nao_encontrada": (404, "proposta_nao_encontrada", MSG_PROPOSTA_NAO_ENCONTRADA),
    "conversa_nao_encontrada": (404, "proposta_nao_encontrada", MSG_PROPOSTA_NAO_ENCONTRADA),
    "proposta_nao_escolhida": (409, "proposta_nao_escolhida", "Esta headline ainda não foi escolhida."),
    # migration 358 (roteiro-first): a roteiro proposta whose tipo the claim did not return would reach the 3-arg headline
    # save and is refused here as a coded 409 -- never a 500, never a fake success.
    "headline_texto_ausente": (409, "roteiro_primeiro_indisponivel", MSG_ROTEIRO_PRIMEIRO_INDISPONIVEL),
    "roteiro_nao_salvo": (409, "roteiro_primeiro_indisponivel", MSG_ROTEIRO_PRIMEIRO_INDISPONIVEL),
    "proposta_nao_e_roteiro": (409, "proposta_nao_e_roteiro", "Esta proposta não é um roteiro."),
}

#: UNI-1b's insertion point: ``async (proposta: dict) -> None``, called after the pre-flight passed, holding the claim.
#: It runs steps 4-7 (roteiro, card, finalizer job, ``roteiro_gerado`` message).
Continuacao = Callable[[dict[str, Any]], Awaitable[None]]
#: ``(org_id) -> None``; raises ``HTTPException(503, orcamento_ia_excedido)`` -- the seed budget pre-check.
Orcamento = Callable[[Optional[str]], Awaitable[None]]


def get_fluxo_settings() -> Any:
    """DI seam for the flow's config (``geracao_worker_enabled``, ``roteiros_dia_usuario``). Tests override it."""
    return settings


def get_fluxo_orcamento() -> Orcamento:
    """DI seam for the IA-budget pre-check. Tests override it."""
    return geracao_jobs.assert_orcamento_ia


@dataclass
class ResultadoEscolher:
    proposta: dict[str, Any]
    fluxo: dict[str, Any]
    mensagem_id: Optional[str]
    ja_existia: bool
    em_andamento: bool

    def como_dict(self) -> dict[str, Any]:
        return {
            "proposta": self.proposta, "fluxo": self.fluxo, "mensagem_id": self.mensagem_id,
            "ja_existia": self.ja_existia, "em_andamento": self.em_andamento,
        }


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _id(valor: Any) -> Optional[str]:
    return str(valor) if valor else None


def _rpc_para_erro(exc: BaseException) -> Optional[ChatError]:
    """The HTTP refusal for a coded RPC exception, or ``None`` when ``exc`` is not one of ours (a real failure)."""
    mensagem, _detalhes, _code = _rpc_detalhes(exc)
    achado = _RPC_ERROS.get(mensagem)
    if achado is None:
        return None
    status, code, texto = achado
    return ChatError(status, texto, code=code)


def _formula_trecho(formula: Any) -> str:
    texto = " ".join(str(formula or "").split())
    return texto if len(texto) <= FORMULA_TRECHO_MAX else texto[: FORMULA_TRECHO_MAX - 1].rstrip() + "…"


def _tipo(proposta: dict[str, Any]) -> str:
    return proposta.get("tipo") or "headline"


def _perfil_ref(perfil: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(perfil["id"]), "handle": perfil.get("handle") or "", "nome": perfil.get("nome")}


class FluxoService:
    def __init__(
        self, db: Any, org_id: str, user_id: str, *, cfg: Any = None,
        ia_check: Callable[[Optional[str]], None] = check_ia_configurada,
        orcamento: Optional[Orcamento] = None,
        continuacao: Optional[Continuacao] = None,
    ) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.cfg = cfg if cfg is not None else settings
        self.ia_check = ia_check
        self.orcamento: Orcamento = orcamento if orcamento is not None else geracao_jobs.assert_orcamento_ia
        #: UNI-1b's seam (steps 4-7); ``None`` until it lands.
        self.continuacao = continuacao

    # ── RPC plumbing ─────────────────────────────────────────────────────────────────────────────────

    def _rpc(self, nome: str, params: dict[str, Any]) -> dict[str, Any]:
        """One RPC = one transaction. A coded refusal becomes its HTTP error; anything else propagates (logged)."""
        try:
            res = self.db.rpc(nome, params).execute()
        except Exception as exc:  # noqa: BLE001 - classified below; an unknown failure is re-raised, never swallowed
            erro = _rpc_para_erro(exc)
            if erro is None:
                logger.exception("fluxo: rpc %s falhou", nome)
                raise
            raise erro from exc
        data = getattr(res, "data", None)
        if isinstance(data, list):
            data = data[0] if data else None
        return data if isinstance(data, dict) else {}

    def _in(self, tabela: str, colunas: str, chave: str, ids: Iterable[Any], **eq: Any) -> list[dict[str, Any]]:
        alvo = sorted({str(i) for i in ids if i})
        rows: list[dict[str, Any]] = []
        for lote in batched(alvo):
            q = self.db.table(tabela).select(colunas).in_(chave, lote)
            for k, v in eq.items():
                q = q.eq(k, v)
            rows.extend(q.execute().data or [])
        return rows

    # ── reads: propostas + Estruturas ────────────────────────────────────────────────────────────────

    def _estruturas_info(self, estrutura_ids: Iterable[Any]) -> dict[str, dict[str, Any]]:
        """``{estrutura_id: {id, codigo, formula_trecho, perfil: {id, handle, nome}}}`` (two reads, never one per row)."""
        estruturas = self._in(ESTRUTURAS, "id,codigo,perfil_id,formula_headline", "id", estrutura_ids)
        perfis = {
            str(p["id"]): p
            for p in self._in(PERFIS, "id,handle,nome", "id", (e.get("perfil_id") for e in estruturas))
        }
        out: dict[str, dict[str, Any]] = {}
        for e in estruturas:
            perfil = perfis.get(str(e.get("perfil_id")))
            if perfil is None:  # the FK is NOT NULL + CASCADE: a missing profile is a bug, never a silent blank
                logger.error("fluxo: estrutura %s sem perfil %s", e["id"], e.get("perfil_id"))
                continue
            out[str(e["id"])] = {
                "id": str(e["id"]), "codigo": e["codigo"], "formula_trecho": _formula_trecho(e.get("formula_headline")),
                "perfil": _perfil_ref(perfil),
            }
        return out

    def apresentar_propostas(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """``Proposta[]`` (contract 6.5) for proposta rows, in the given order."""
        if not rows:
            return []
        links = self._in(
            PROPOSTA_ESTRUTURAS, "proposta_id,estrutura_id,ordem,principal", "proposta_id", (r["id"] for r in rows)
        )
        info = self._estruturas_info(link["estrutura_id"] for link in links)
        por_proposta: dict[str, list[dict[str, Any]]] = {}
        for link in sorted(links, key=lambda x: int(x.get("ordem") or 0)):
            est = info.get(str(link["estrutura_id"]))
            if est is None:
                continue
            por_proposta.setdefault(str(link["proposta_id"]), []).append(
                {"id": est["id"], "codigo": est["codigo"], "perfil": est["perfil"], "principal": bool(link.get("principal"))}
            )
        return [
            {
                "id": str(r["id"]), "ordem": r["ordem"], "texto": r["texto"], "gatilho_tag": r.get("gatilho_tag"),
                "estruturas": por_proposta.get(str(r["id"]), []), "status": r["status"],
                "headline_id": _id(r.get("headline_id")),
                # contract 16.5 (always emitted; a pre-358 row reads as a headline)
                "tipo": _tipo(r), "titulo": r.get("titulo"), "formato": r.get("formato"),
                "roteiro_id": _id(r.get("roteiro_id")),
            }
            for r in rows
        ]

    def propostas_por_mensagem(self, mensagem_ids: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
        """``{mensagem_id: Proposta[]}`` for a page of messages (org-scoped, ordered by ``ordem``)."""
        rows = self._in(PROPOSTAS, PROPOSTA_COLS, "mensagem_id", mensagem_ids, org_id=self.org_id)
        rows.sort(key=lambda r: (str(r["mensagem_id"]), int(r["ordem"])))
        out: dict[str, list[dict[str, Any]]] = {}
        for r, p in zip(rows, self.apresentar_propostas(rows)):
            out.setdefault(str(r["mensagem_id"]), []).append(p)
        return out

    def get_proposta(self, proposta_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(PROPOSTAS).select(PROPOSTA_COLS)
            .eq("id", proposta_id).eq("org_id", self.org_id).execute().data
        )
        return rows[0] if rows else None

    # ── reads: the Fluxo, composed from the truth tables (never stored) ──────────────────────────────

    def compor_fluxo(self, proposta: dict[str, Any]) -> dict[str, Any]:
        """``Fluxo`` (contract 6.5 + 16.5): the direction, the headline, the roteiro/card once they exist, the Estruturas
        used, the caption state. Headline-first finds the roteiro by its headline; roteiro-first by ``roteiro_id``
        (the script saved from the proposta), and its headline is the generated one (``null`` until it exists)."""
        direcao = DIRECAO_POR_TIPO[_tipo(proposta)]
        headline_id = _id(proposta.get("headline_id"))
        roteiro: Optional[dict[str, Any]] = None
        if direcao == "roteiro_primeiro":
            roteiro_id = _id(proposta.get("roteiro_id"))
            if roteiro_id:
                achados = (
                    self.db.table(ROTEIROS).select(ROTEIRO_COLS).eq("org_id", self.org_id).eq("id", roteiro_id)
                    .limit(1).execute().data
                )
                roteiro = achados[0] if achados else None
            headline = self._headline(headline_id) if headline_id else None
        else:
            if headline_id:
                achados = (
                    self.db.table(ROTEIROS).select(ROTEIRO_COLS)
                    .eq("org_id", self.org_id).eq("headline_id", headline_id).eq("conversa_id", str(proposta["conversa_id"]))
                    .order("created_at", desc=True).limit(1).execute().data
                )
                roteiro = achados[0] if achados else None
            headline = {"id": headline_id, "texto": proposta["texto"]}
        post = None
        legenda = "pendente"
        if roteiro:
            post = post_refs(self.db, self.org_id, "roteiro_id", [roteiro["id"]]).get(str(roteiro["id"]))
            if post:
                cartao = (
                    self.db.table(POSTS).select("id,legenda").eq("id", post["id"]).eq("org_id", self.org_id).execute().data
                )
                if cartao and (cartao[0].get("legenda") or "").strip():
                    legenda = "gerada"
        eventos = self._tipos_de_evento(str(proposta["id"]))
        if legenda == "pendente" and "legenda_falhou" in eventos:
            legenda = "indisponivel"
        if direcao == "roteiro_primeiro":
            etapa = self._etapa_roteiro_primeiro(proposta, roteiro, headline, post, "headline_gerando" in eventos)
        else:
            etapa = self._etapa(proposta, roteiro)
        return {
            "proposta_id": str(proposta["id"]),
            "direcao": direcao,
            "etapa": etapa,
            "headline": headline,
            "roteiro": None if roteiro is None else {
                "id": str(roteiro["id"]), "nome": roteiro["nome"], "status": roteiro["status"],
                "formato": roteiro.get("formato") or "reels", "duracao": roteiro.get("duracao") or "auto",
                "ordem_cta": roteiro.get("estrutura"), "versao": roteiro.get("versao"),
            },
            "post": post,
            "estruturas": self._usos(str(proposta["id"])),
            "legenda": legenda,
            "erro_codigo": proposta.get("fluxo_erro_codigo"),
        }

    def _headline(self, headline_id: str) -> Optional[dict[str, Any]]:
        rows = self.db.table(HEADLINES).select("id,texto").eq("id", headline_id).eq("org_id", self.org_id).execute().data
        if not rows:  # ON DELETE SET NULL would have cleared the link: a dangling id is a bug, never a fake text
            logger.error("fluxo: headline %s da proposta não encontrada", headline_id)
            return None
        return {"id": str(rows[0]["id"]), "texto": rows[0]["texto"]}

    @staticmethod
    def _etapa(proposta: dict[str, Any], roteiro: Optional[dict[str, Any]]) -> str:
        if proposta.get("fluxo_etapa") == "falhou" or (roteiro and roteiro["status"] == "falha"):
            return "falhou"
        if roteiro is None:
            return "headline_salva"
        return "roteiro_pronto" if roteiro["status"] == "completo" else "roteiro_gerando"

    @staticmethod
    def _etapa_roteiro_primeiro(
        proposta: dict[str, Any], roteiro: Optional[dict[str, Any]], headline: Optional[dict[str, Any]],
        post: Optional[dict[str, Any]], headline_gerando: bool,
    ) -> str:
        """Roteiro-first read state (contract 16.5 + tech-lead clarification 2026-11-17): ``roteiro_salvo`` (saved, the
        headline job not yet claimed) -> ``headline_gerando`` (job pending/running, or the headline exists but the card
        is not bound yet) -> ``roteiro_pronto`` (headline AND card) | ``falhou``."""
        if proposta.get("fluxo_etapa") == "falhou" or (roteiro and roteiro["status"] == "falha"):
            return "falhou"
        if headline is not None and post is not None:
            return "roteiro_pronto"
        if headline is not None or headline_gerando:
            return "headline_gerando"
        return "roteiro_salvo"

    def _tipos_de_evento(self, proposta_id: str) -> set[str]:
        """The read-relevant ledger facts of one flow (one indexed read): a failed caption, a pending headline job."""
        rows = (
            self.db.table(EVENTOS).select("tipo").eq("org_id", self.org_id).eq("proposta_id", proposta_id)
            .in_("tipo", ["legenda_falhou", "headline_gerando"]).execute().data
        )
        return {r["tipo"] for r in rows or []}

    def _usos(self, proposta_id: str) -> list[dict[str, Any]]:
        """``EstruturaUso[]``: the Estruturas written for this proposta (``cs_estrutura_usos``) + the blocks used."""
        usos = (
            self.db.table(USOS).select("estrutura_id,papel,ordem,bloco_ids")
            .eq("org_id", self.org_id).eq("proposta_id", proposta_id).order("ordem").execute().data or []
        )
        info = self._estruturas_info(u["estrutura_id"] for u in usos)
        out = []
        for u in usos:
            est = info.get(str(u["estrutura_id"]))
            if est is None:
                continue
            out.append({
                "id": est["id"], "codigo": est["codigo"], "perfil": est["perfil"], "formula_trecho": est["formula_trecho"],
                "papel": u["papel"], "blocos": [],  # the blocks used are recorded by the roteiro step (UNI-1b)
            })
        return out

    def mensagem_roteiro_gerado(self, proposta_id: str) -> Optional[str]:
        rows = (
            self.db.table(MENSAGENS).select("id").eq("org_id", self.org_id).eq("proposta_id", proposta_id)
            .eq("tipo", "roteiro_gerado").limit(1).execute().data
        )
        return _id(rows[0]["id"]) if rows else None

    # ── the saga, steps 1-3 ──────────────────────────────────────────────────────────────────────────

    def _conversa_propria(self, conversa_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(CONVERSAS).select("id,marca_id").eq("id", conversa_id)
            .eq("org_id", self.org_id).eq("user_id", self.user_id).execute().data
        )
        if not rows:
            raise ChatError(404, MSG_PROPOSTA_NAO_ENCONTRADA, code="proposta_nao_encontrada")
        return rows[0]

    def _preparar_sync(self, conversa_id: str, proposta_id: Optional[str], headline_id: Optional[str]) -> tuple[dict[str, Any], bool]:
        """Steps 0-2: ownership, the synthesised proposta for an ``@`` headline, the claim, the headline.
        Returns ``(proposta row, claimed)``; a lost claim stops here (the caller answers with the current state)."""
        self._conversa_propria(conversa_id)
        if headline_id:
            proposta_id = str(self._rpc("cs_chat_proposta_sintetizar", {
                "p_org": self.org_id, "p_user": self.user_id, "p_conversa": conversa_id, "p_headline": headline_id,
            }).get("proposta_id"))
        reivindicacao = self._rpc("cs_chat_proposta_reivindicar", {
            "p_proposta": proposta_id, "p_org": self.org_id, "p_conversa": conversa_id, "p_user": self.user_id,
            "p_lease_s": LEASE_SEGUNDOS,
        })
        if not reivindicacao.get("claimed"):
            return reivindicacao["proposta"], False
        # step 2 by direction (16.6): a roteiro proposta saves the script as-is; a headline proposta saves the headline
        salvar = "cs_chat_proposta_salvar_roteiro" if _tipo(reivindicacao.get("proposta") or {}) == "roteiro" else "cs_chat_proposta_salvar_headline"
        self._rpc(salvar, {"p_proposta": proposta_id, "p_org": self.org_id, "p_user": self.user_id})
        atual = self.get_proposta(str(proposta_id))
        if atual is None:  # claimed and saved a moment ago: its absence is a bug, not a 404
            raise RuntimeError(f"proposta {proposta_id} desapareceu depois do claim")
        return atual, True

    def _liberar_sync(self, proposta_id: str, erro: Optional[str]) -> None:
        self._rpc("cs_chat_proposta_liberar", {
            "p_proposta": proposta_id, "p_org": self.org_id, "p_user": self.user_id, "p_erro": erro,
        })

    def _roteiros_hoje(self) -> int:
        """Roteiros this user created in the rolling window (capped read: never needs more than the cap)."""
        cap = limite_geracao("roteiros_dia_usuario", self.org_id, self.cfg)
        rows = (
            self.db.table(ROTEIROS).select("id").eq("org_id", self.org_id).eq("created_by", self.user_id)
            .gte("created_at", (_agora() - JANELA_ROTEIROS).isoformat()).limit(cap).execute().data or []
        )
        return len(rows)

    def _headlines_hoje(self) -> int:
        """Headlines generated from a roteiro by this user in the rolling window (capped read)."""
        cap = limite_geracao("headline_lotes_dia_usuario", self.org_id, self.cfg)
        rows = (
            self.db.table(HEADLINES).select("id").eq("org_id", self.org_id).eq("created_by", self.user_id)
            .eq("modo", "do_roteiro").gte("created_at", (_agora() - JANELA_ROTEIROS).isoformat()).limit(cap).execute().data
            or []
        )
        return len(rows)

    async def preflight(self, tipo: str = "headline") -> None:
        """Step 3: every refusal that must come BEFORE the expensive step (contract 9.2; no format gate: every
        formato is supported). ``geracao_jobs`` raises ``HTTPException`` with a coded detail. Roteiro-first (16.6) is
        held to the daily HEADLINE cap (its expensive step is the generated headline), headline-first to the roteiro cap."""
        geracao_jobs.assert_geracao_disponivel(self.cfg)
        try:
            await run_in_threadpool(self.ia_check, self.org_id)  # resolves a key: may read the DB
        except RoteiroError as exc:
            detalhe = exc.detail if isinstance(exc.detail, dict) else {}
            raise ChatError(
                exc.status, detalhe.get("detail") or MSG_IA_NAO_CONFIGURADA, code=detalhe.get("code") or "ia_nao_configurada"
            ) from exc
        await self.orcamento(self.org_id)
        if tipo == "roteiro":
            if await run_in_threadpool(self._headlines_hoje) >= limite_geracao(
                "headline_lotes_dia_usuario", self.org_id, self.cfg
            ):
                raise ChatError(
                    429, MSG_LIMITE_HEADLINES, code="limite_diario_headlines",
                    headers={"Retry-After": str(RETRY_AFTER_ROTEIROS_S)},
                )
            return
        if await run_in_threadpool(self._roteiros_hoje) >= limite_geracao("roteiros_dia_usuario", self.org_id, self.cfg):
            raise ChatError(
                429, MSG_LIMITE_ROTEIROS, code="limite_diario_roteiros",
                headers={"Retry-After": str(RETRY_AFTER_ROTEIROS_S)},
            )

    @staticmethod
    def _codigo_da_recusa(exc: BaseException) -> str:
        if isinstance(exc, ChatError) and exc.code:
            return exc.code
        if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) and exc.detail.get("code"):
            return str(exc.detail["code"])
        return "recusado"

    async def escolher(
        self, conversa_id: str, *, proposta_id: Optional[str] = None, headline_id: Optional[str] = None
    ) -> ResultadoEscolher:
        """The click on a headline. Exactly one of ``proposta_id`` / ``headline_id``."""
        if (proposta_id is None) == (headline_id is None):
            raise ValueError("escolher: informe exatamente um entre proposta_id e headline_id")
        proposta, claimed = await run_in_threadpool(self._preparar_sync, conversa_id, proposta_id, headline_id)
        if not claimed:
            # a concurrent double click (lease held) or an already finished flow: the current state, not an error
            return await run_in_threadpool(self._resultado, proposta, True, proposta.get("fluxo_etapa") != "concluido")
        try:
            await self.preflight(_tipo(proposta))
        except (ChatError, HTTPException) as exc:
            # the headline stays saved; give the lease back so the same click can be retried at once
            await run_in_threadpool(self._liberar_sync, str(proposta["id"]), self._codigo_da_recusa(exc))
            raise
        if self.continuacao is not None:
            # UNI-1b: steps 4-7. The lease stays held either way (it is what makes a rapid second click a
            # `ja_existia`, not a second flow); it expires on its own and any later click resumes from `fluxo_etapa`.
            await self.continuacao(proposta)
        return await run_in_threadpool(self._resultado, proposta, False, False)

    # ── the batch pick (criacao-pipeline-contract 4) ─────────────────────────────────────────────────

    def _propostas_para_selecao(self, ids: list[str], conversa_id: Optional[str] = None) -> dict[str, dict[str, Any]]:
        """The proposta rows of ``ids`` -- ALL of them the caller's (org + own conversation) or a 404, before any claim: an
        id that is foreign or unknown is the same answer (ids are not enumerable) and the batch has no side effect yet."""
        rows = {str(r["id"]): r for r in self._in(PROPOSTAS, PROPOSTA_COLS, "id", ids, org_id=self.org_id)}
        conversas = {
            str(c["id"]) for c in self._in(
                CONVERSAS, "id", "id", (r["conversa_id"] for r in rows.values()), org_id=self.org_id, user_id=self.user_id
            )
        }
        if (
            set(rows) != set(ids) or any(str(r["conversa_id"]) not in conversas for r in rows.values())
            or (conversa_id is not None and any(str(r["conversa_id"]) != conversa_id for r in rows.values()))
        ):
            raise ChatError(404, MSG_PROPOSTA_NAO_ENCONTRADA, code="proposta_nao_encontrada")
        return rows

    def _evento_selecao(self, rows: Iterable[dict[str, Any]]) -> None:
        """``opcoes_selecionadas`` once per conversation of the batch, ``contagem`` = how many options were picked there."""
        por_conversa: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            por_conversa.setdefault(str(r["conversa_id"]), []).append(r)
        self.db.table(EVENTOS).insert([
            {"id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": itens[0]["marca_id"], "conversa_id": conversa,
             "ator_id": self.user_id, "tipo": "opcoes_selecionadas", "contagem": len(itens)}
            for conversa, itens in por_conversa.items()
        ]).execute()

    async def selecionar(self, ids: list[str], conversa_id: Optional[str] = None) -> dict[str, Any]:
        """Pick N proposals at once. One saga per id, in the given order -- each its own claim, so a retried batch (or a
        double click) is ``ja_existia`` per proposta and never a second card -- and one refused item (a cap, a refusal of the
        saga) never stops the rest: every item answers with its own outcome."""
        rows = await run_in_threadpool(self._propostas_para_selecao, ids, conversa_id)
        await run_in_threadpool(self._evento_selecao, rows.values())
        itens: list[dict[str, Any]] = []
        for pid in ids:
            try:
                r = await self.escolher(str(rows[pid]["conversa_id"]), proposta_id=pid)
            except (ChatError, HTTPException) as exc:
                codigo = self._codigo_da_recusa(exc)
                itens.append({
                    "proposta_id": pid, "ok": False,
                    "erro": {"code": codigo, "detail": exc.detail if isinstance(exc, ChatError) else codigo,
                             "status": getattr(exc, "status", None) or getattr(exc, "status_code", 500)},
                })
            except Exception:  # noqa: BLE001 - one item's crash must not take the batch down: logged, and reported as its own item
                logger.exception("fluxo: selecionar proposta=%s falhou", pid)
                itens.append({"proposta_id": pid, "ok": False, "erro": {"code": "falha_inesperada", "detail": "Falha inesperada.", "status": 500}})
            else:
                itens.append({"proposta_id": pid, "ok": True, **r.como_dict()})
        # S11's shape: three id lists; a falha carries the id and its refusal code. ``itens`` keeps the full per-item outcome.
        return {
            "criados": [i["proposta_id"] for i in itens if i["ok"] and not i["ja_existia"]],
            "ja_existiam": [i["proposta_id"] for i in itens if i["ok"] and i["ja_existia"]],
            "falhas": [{"id": i["proposta_id"], **i["erro"]} for i in itens if not i["ok"]],
            "itens": itens,
        }

    def _resultado(self, proposta: dict[str, Any], ja_existia: bool, em_andamento: bool) -> ResultadoEscolher:
        atual = self.get_proposta(str(proposta["id"])) or proposta
        return ResultadoEscolher(
            proposta=self.apresentar_propostas([atual])[0], fluxo=self.compor_fluxo(atual),
            mensagem_id=self.mensagem_roteiro_gerado(str(atual["id"])), ja_existia=ja_existia, em_andamento=em_andamento,
        )


__all__ = [
    "Continuacao", "DIRECAO_POR_TIPO", "FluxoService", "LEASE_SEGUNDOS", "MSG_ROTEIRO_PRIMEIRO_INDISPONIVEL", "MSG_LIMITE_ROTEIROS", "MSG_PROPOSTA_NAO_ENCONTRADA",
    "Orcamento", "ResultadoEscolher", "RETRY_AFTER_ROTEIROS_S", "get_fluxo_orcamento", "get_fluxo_settings",
]
