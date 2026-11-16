"""Estruturas library service (estruturas-contract.md sections 3.1, 4.1, 6.0-6.2).

The library is PLATFORM-WIDE (no ``org_id`` on its tables): every member reads, only platform admins write.
This service therefore never filters the library by org -- the ONLY org-scoped reads are the brand's own
selection (``cs_biblioteca_referencias``) and the marca ownership check.

Reads go straight to the tables / the ``cs_estruturas_resumo`` view; EVERY write is ONE call to a SECURITY DEFINER
RPC of migration ``cs_estruturas`` that mutates and writes the event row in the same transaction (the service
role holds no direct write grant on the library tables). A refusal is a coded exception raised by the RPC and mapped
here to HTTP (:func:`mapear_erro_rpc`).

Responses are built from explicit whitelists (never ``select("*")`` passed through): the admin-only keys
(``proveniencia``, ``origem``, ``ref_externa``, ``referencia_rotulo``, ``formula_herdada_de``, ``pendente_revisao``,
the TipoBloco ``versao``/``sistema``, non-``ativa`` rows) are added in ONE place (``_admin_*``), so a non-admin
response cannot carry them by construction.

The service is synchronous (PostgREST + RPC); thumbnails / photos are private-bucket paths turned into short-TTL
signed URLs by the async :func:`assinar_urls` in the router (a missing thumbnail never fails a page).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.services import biblioteca_optout
from app.modules.media_creation.services.viral_card import sign_thumbnail

logger = logging.getLogger(__name__)

ESTRUTURAS = "cs_estruturas"
BLOCOS = "cs_estrutura_blocos"
TIPOS = "cs_estrutura_tipos_bloco"
RESUMO = "cs_estruturas_resumo"
PERFIS = "cs_perfis_monitorados"
VIRAIS = "cs_virais"
REFERENCIAS = "cs_biblioteca_referencias"

LIST_COLS = (
    "id,codigo,perfil_id,viral_id,formula_headline,formato,objetivos,status,updated_at,blocos_total,campos_pendentes,"
    "revisao_desuso_em"
)
ESTRUTURA_COLS = (
    "id,codigo,perfil_id,viral_id,formula_headline,formato,objetivos,status,origem,ref_externa,formula_herdada_de,"
    "referencia_rotulo,formula_origem,formato_origem,objetivos_origem,versao,updated_at,revisao_desuso_em"
)
BLOCO_COLS = (
    "id,ordem,tipo_id,nome,tempo,instrucao,nota,repeticoes,nome_origem,tipo_origem,tempo_origem,instrucao_origem"
)
TIPO_COLS = "id,nome,ordem,tempo_tipico,instrucao_referencia,ativo,sistema,versao"
PERFIL_COLS = "id,handle,nome,foto_path"
VIRAL_COLS = "id,codigo,permalink,thumbnail_path"
PENDENTES = frozenset(fmt.PROVENIENCIAS_PENDENTES)
#: Private-key prefix: a storage path waiting to be signed by :func:`assinar_urls` (never leaves the API).
_PATH = "_path"

STATUS_FILTROS = ("ativa", "rascunho", "arquivada", "todas")


class EstruturaError(Exception):
    """A refusal with its HTTP status; ``detail`` is a pt-BR string or ``{"code", "detail", ...extra}`` (section 0.2)."""

    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def coded(status: int, code: str, message: str, **extra: Any) -> EstruturaError:
    return EstruturaError(status, {"code": code, "detail": message, **extra})


# ── RPC error mapping ──────────────────────────────────────────────────────────────────────────────────────

#: RAISE EXCEPTION '<code>' of the migration's RPCs -> (status, code, pt-BR message).
_RPC_ERROS: dict[str, tuple[int, str, str]] = {
    "versao_desatualizada": (409, "versao_desatualizada", "Esta estrutura foi alterada por outra pessoa. Recarregue e tente de novo."),
    "estrutura_em_uso": (409, "estrutura_em_uso", "Esta estrutura já foi usada em headlines ou roteiros. Arquive-a em vez de excluir."),
    "estrutura_inativa": (409, "estrutura_inativa", "Esta estrutura não está ativa."),
    "rascunho_incompleto": (422, "rascunho_incompleto", "Para publicar, informe formato, ao menos um objetivo e ao menos um bloco."),
    "estrutura_incompleta": (422, "estrutura_incompleta", "Uma estrutura ativa precisa de formato, ao menos um objetivo e ao menos um bloco."),
    "formula_invalida": (422, "formula_invalida", "Informe a fórmula da headline."),
    "blocos_invalidos": (422, "blocos_invalidos", "A lista de blocos é inválida (1 a 60 blocos, sem ids repetidos)."),
    "campo_desconhecido": (422, "campo_desconhecido", "Campo desconhecido para confirmar."),
    "tipo_em_uso": (409, "tipo_em_uso", "Este tipo de bloco está em uso. Desative-o em vez de excluir."),
    "tipo_protegido": (409, "tipo_protegido", "O tipo \"Outro\" é do sistema e não pode ser alterado."),
    "tipo_invalido": (422, "tipo_invalido", "Informe o nome e a instrução do tipo de bloco."),
}
#: Not-found codes: (status, message). ``tipo_nao_encontrado`` / ``bloco_nao_encontrado`` are 404 when the id is the
#: resource of the route and 422 when it sits inside a request body (``corpo=True``).
_RPC_NAO_ENCONTRADO: dict[str, str] = {
    "estrutura_nao_encontrada": "Estrutura não encontrada.",
    "perfil_nao_encontrado": "Perfil não encontrado.",
    "viral_nao_encontrado": "Vídeo não encontrado.",
    "tipo_nao_encontrado": "Tipo de bloco não encontrado.",
    "bloco_nao_encontrado": "Bloco não encontrado.",
}
_UNICOS: dict[str, tuple[int, str, str]] = {
    "cs_estrutura_tipos_bloco_nome_uq": (422, "tipo_nome_duplicado", "Já existe um tipo de bloco com este nome."),
    "cs_estruturas_fonte_ref_uq": (409, "estrutura_ja_importada", "Esta estrutura já existe na biblioteca."),
    "cs_estruturas_viral_auto_uq": (409, "viral_ja_tem_rascunho", "Este vídeo já tem uma estrutura automática."),
}


def _rpc_detalhes(exc: BaseException) -> tuple[str, str, str]:
    """``(message, details, code)`` of a PostgREST ``APIError`` (or a duck-typed double)."""
    payload = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
    message = getattr(exc, "message", None) or payload.get("message") or ""
    details = getattr(exc, "details", None) or payload.get("details") or ""
    code = getattr(exc, "code", None) or payload.get("code") or ""
    return str(message).strip(), str(details).strip(), str(code)


def mapear_erro_rpc(exc: BaseException, *, corpo: bool = False) -> Optional[EstruturaError]:
    """The HTTP refusal for a coded RPC exception, or ``None`` when ``exc`` is not one of ours (a real failure:
    the caller re-raises it, never swallows)."""
    message, details, _code = _rpc_detalhes(exc)
    if message in _RPC_NAO_ENCONTRADO:
        status = 422 if corpo and message in ("tipo_nao_encontrado", "bloco_nao_encontrado") else 404
        return EstruturaError(status, _RPC_NAO_ENCONTRADO[message])
    if message in _RPC_ERROS:
        status, code, texto = _RPC_ERROS[message]
        extra: dict[str, Any] = {}
        if message in ("rascunho_incompleto", "estrutura_incompleta") and details:
            extra["faltando"] = [p for p in details.split(",") if p]
        return coded(status, code, texto, **extra)
    if is_unique_violation(exc):
        text = f"{message} {details}"
        for constraint, (status, code, texto) in _UNICOS.items():
            if constraint in text:
                return coded(status, code, texto)
    return None


# ── pure presenters ────────────────────────────────────────────────────────────────────────────────────────


def _pendente(*origens: Optional[str]) -> bool:
    return any(o in PENDENTES for o in origens)


def formula_trecho(formula: str, limite: int = 120) -> str:
    """The ``EstruturaRef.formula_trecho``: <= ``limite`` chars, cut at a word boundary with an ellipsis."""
    texto = " ".join((formula or "").split())
    if len(texto) <= limite:
        return texto
    corte = texto[: limite - 1].rsplit(" ", 1)[0] or texto[: limite - 1]
    return corte + "…"


def apresentar_tipo(row: dict[str, Any], *, admin: bool) -> dict[str, Any]:
    out = {
        "id": str(row["id"]), "nome": row["nome"], "ordem": row["ordem"], "tempo_tipico": row.get("tempo_tipico"),
        "instrucao_referencia": row["instrucao_referencia"], "ativo": bool(row.get("ativo", True)),
    }
    if admin:  # the PUT needs the version; the FE disables the controls of the protected row
        out["versao"] = row.get("versao", 1)
        out["sistema"] = bool(row.get("sistema", False))
    return out


class EstruturasService:
    def __init__(self, db: Any, *, org_id: str, user_id: str, is_admin: bool):
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id)
        self.is_admin = bool(is_admin)

    # ── low-level reads ───────────────────────────────────────────────────────────────────────────────────

    def _rows(self, table: str, cols: str, ids: Iterable[Any], key: str = "id") -> list[dict[str, Any]]:
        ordered = sorted({str(i) for i in ids if i})
        out: list[dict[str, Any]] = []
        for chunk in batched(ordered):
            out.extend(self.db.table(table).select(cols).in_(key, chunk).execute().data or [])
        return out

    def assert_marca(self, marca_id: str) -> None:
        rows = self.db.table("marcas").select("id").eq("id", str(marca_id)).eq("org_id", self.org_id).execute().data
        if not rows:
            raise EstruturaError(404, "Marca não encontrada")

    def perfis_selecionados(self, marca_id: str) -> set[str]:
        """The brand's selected profiles: ``modo='perfil'`` refs plus the profile of every ``modo='video'`` ref."""
        refs = (
            self.db.table(REFERENCIAS).select("modo,perfil_id,viral_id").eq("marca_id", str(marca_id))
            .eq("org_id", self.org_id).execute().data or []
        )
        perfis = {str(r["perfil_id"]) for r in refs if r.get("modo") == "perfil" and r.get("perfil_id")}
        videos = [r["viral_id"] for r in refs if r.get("modo") == "video" and r.get("viral_id")]
        perfis |= {str(v["perfil_id"]) for v in self._rows(VIRAIS, "id,perfil_id", videos) if v.get("perfil_id")}
        return perfis

    def _perfis_e_virais(self, rows: list[dict[str, Any]]) -> tuple[dict[str, dict], dict[str, dict]]:
        perfis = {str(p["id"]): p for p in self._rows(PERFIS, PERFIL_COLS, (r["perfil_id"] for r in rows))}
        virais = {str(v["id"]): v for v in self._rows(VIRAIS, VIRAL_COLS, (r.get("viral_id") for r in rows))}
        return perfis, virais

    def _perfil_ref(self, p: Optional[dict[str, Any]], perfil_id: Any) -> dict[str, Any]:
        """A client org sees the creator as handle + name ONLY (owner decision 2026-11-15, LGPD): the member shape has no
        photo key at all. An admin also gets the (to-be-signed) photo."""
        p = p or {}
        out: dict[str, Any] = {"id": str(perfil_id), "handle": p.get("handle") or "", "nome": p.get("nome")}
        if self.is_admin:
            out.update({"foto_url": None, _PATH: p.get("foto_path")})
        return out

    @staticmethod
    def _viral_ref(v: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not v:
            return None
        return {
            "id": str(v["id"]), "codigo": v.get("codigo"), "permalink": v.get("permalink") or "", "thumbnail_url": None,
            _PATH: v.get("thumbnail_path"),
        }

    # ── catalog ───────────────────────────────────────────────────────────────────────────────────────────

    def tipos_bloco(self) -> list[dict[str, Any]]:
        q = self.db.table(TIPOS).select(TIPO_COLS)
        if not self.is_admin:
            q = q.eq("ativo", True)
        rows = q.order("ordem").execute().data or []
        return [apresentar_tipo(r, admin=self.is_admin) for r in sorted(rows, key=lambda r: r["ordem"])]

    def _tipo(self, tipo_id: str) -> dict[str, Any]:
        rows = self.db.table(TIPOS).select(TIPO_COLS).eq("id", str(tipo_id)).execute().data
        if not rows:
            raise EstruturaError(404, "Tipo de bloco não encontrado.")
        return apresentar_tipo(rows[0], admin=True)

    # ── library reads ─────────────────────────────────────────────────────────────────────────────────────

    def listar(
        self, *, marca_id: Optional[str], perfil_id: Optional[str], q: Optional[str], formatos: list[str],
        objetivos: list[str], status: Optional[str], somente_pendentes_revisao: bool, limit: int, offset: int,
        revisao: Optional[str] = None,
    ) -> dict[str, Any]:
        selecionados: Optional[set[str]] = None
        if marca_id:
            self.assert_marca(marca_id)
            selecionados = self.perfis_selecionados(marca_id)
        query = self.db.table(RESUMO).select(LIST_COLS, count="exact")
        # A non-admin only ever sees `ativa` rows: the filters below are ignored for them (never an error).
        filtro_status = (status or "ativa") if self.is_admin else "ativa"
        if filtro_status != "todas":
            query = query.eq("status", filtro_status)
        if perfil_id:
            query = query.eq("perfil_id", str(perfil_id))
        if formatos:
            query = query.in_("formato", list(formatos))
        if objetivos:
            query = query.overlaps("objetivos", list(objetivos))
        if somente_pendentes_revisao and self.is_admin:
            query = query.gt("campos_pendentes", 0)
        if revisao == "pendente" and self.is_admin:  # the 24-month-unused review queue (admin-only; ignored for members)
            query = query.not_.is_("revisao_desuso_em", "null")
        if q and q.strip():
            query = query.text_search("busca", q.strip(), options={"config": "portuguese", "type": "websearch"})
        res = query.order("updated_at", desc=True).order("codigo", desc=True).range(offset, offset + limit - 1).execute()
        rows = res.data or []
        perfis, virais = self._perfis_e_virais(rows)
        items = [self._resumo(r, perfis, virais, selecionados) for r in rows]
        total = getattr(res, "count", None)
        return {"items": items, "total": total if total is not None else offset + len(items)}

    def _resumo(
        self, row: dict[str, Any], perfis: dict[str, dict], virais: dict[str, dict], selecionados: Optional[set[str]],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(row["id"]), "codigo": row["codigo"],
            "perfil": self._perfil_ref(perfis.get(str(row["perfil_id"])), row["perfil_id"]),
            "formula_headline": row["formula_headline"], "formato": row.get("formato"),
            "objetivos": list(row.get("objetivos") or []), "blocos_total": int(row.get("blocos_total") or 0),
            "viral": self._viral_ref(virais.get(str(row.get("viral_id")))) if row.get("viral_id") else None,
            "status": row["status"], "updated_at": row.get("updated_at"),
        }
        if selecionados is not None:
            out["selecionada_pela_marca"] = str(row["perfil_id"]) in selecionados
        if self.is_admin:
            out["pendente_revisao"] = int(row.get("campos_pendentes") or 0) > 0
            out["revisao_por_desuso"] = row.get("revisao_desuso_em")
        return out

    def detalhe(self, estrutura_id: str) -> dict[str, Any]:
        rows = self.db.table(ESTRUTURAS).select(ESTRUTURA_COLS).eq("id", str(estrutura_id)).execute().data
        # unknown id -> 404; a rascunho / arquivada is invisible to a non-admin (404, never 403)
        if not rows or (not self.is_admin and rows[0]["status"] != "ativa"):
            raise EstruturaError(404, "Estrutura não encontrada.")
        e = rows[0]
        blocos = self.db.table(BLOCOS).select(BLOCO_COLS).eq("estrutura_id", e["id"]).order("ordem").execute().data or []
        blocos = sorted(blocos, key=lambda b: b["ordem"])
        tipos = {str(t["id"]): t for t in self._rows(TIPOS, "id,nome", (b["tipo_id"] for b in blocos))}
        perfis, virais = self._perfis_e_virais([e])
        out = self._resumo({**e, "blocos_total": len(blocos), "campos_pendentes": self._campos_pendentes(e, blocos)},
                           perfis, virais, None)
        out["blocos"] = [self._bloco(b, tipos) for b in blocos]
        out["versao"] = e["versao"]
        if self.is_admin:
            out.update({
                "origem": e["origem"], "ref_externa": e.get("ref_externa"),
                "referencia_rotulo": e.get("referencia_rotulo"), "formula_herdada_de": e.get("formula_herdada_de"),
                "proveniencia": {
                    "formula_headline": e["formula_origem"], "formato": e["formato_origem"],
                    "objetivos": e["objetivos_origem"],
                },
            })
        return out

    @staticmethod
    def _campos_pendentes(e: dict[str, Any], blocos: list[dict[str, Any]]) -> int:
        n = sum(1 for o in (e["formula_origem"], e["formato_origem"], e["objetivos_origem"]) if o in PENDENTES)
        for b in blocos:
            n += sum(1 for o in (b["nome_origem"], b["tipo_origem"], b["tempo_origem"], b["instrucao_origem"]) if o in PENDENTES)
        return n

    def _bloco(self, b: dict[str, Any], tipos: dict[str, dict]) -> dict[str, Any]:
        tipo = tipos.get(str(b["tipo_id"])) or {}
        out = {
            "id": str(b["id"]), "ordem": b["ordem"], "nome": b["nome"],
            "tipo": {"id": str(b["tipo_id"]), "nome": tipo.get("nome") or ""},
            "tempo": b.get("tempo"), "instrucao": b.get("instrucao"), "nota": b.get("nota"),
            "repeticoes": b.get("repeticoes", 1),
        }
        if self.is_admin:
            out["proveniencia"] = {
                "nome": b["nome_origem"], "tipo": b["tipo_origem"], "tempo": b["tempo_origem"], "instrucao": b["instrucao_origem"],
            }
        return out

    # ── writes (admin; the router's guard enforces platform-admin, this re-checks) ────────────────────────

    def _exigir_admin(self) -> None:
        if not self.is_admin:  # defence in depth: the routers already gate on require_platform_admin
            raise EstruturaError(403, "Restrito a administradores da plataforma NoctusAI.")

    def _rpc(self, nome: str, params: dict[str, Any], *, corpo: bool = False) -> dict[str, Any]:
        """One RPC = one transaction. A coded refusal becomes its HTTP error; anything else propagates (logged)."""
        try:
            res = self.db.rpc(nome, params).execute()
        except Exception as exc:  # noqa: BLE001 - classified below; an unknown failure is re-raised, never swallowed
            erro = mapear_erro_rpc(exc, corpo=corpo)
            if erro is None:
                logger.exception("estruturas: rpc %s falhou", nome)
                raise
            raise erro from exc
        data = getattr(res, "data", None)
        if isinstance(data, list):
            data = data[0] if data else None
        return data if isinstance(data, dict) else {}

    def _assert_perfil(self, perfil_id: str) -> dict[str, Any]:
        rows = self.db.table(PERFIS).select("id,handle").eq("id", str(perfil_id)).execute().data
        if not rows:
            raise EstruturaError(404, "Perfil não encontrado.")
        if biblioteca_optout.esta_bloqueado(self.db, rows[0]["handle"]):
            raise coded(409, "perfil_optout", "Este criador pediu para não ser monitorado.")
        return rows[0]

    def _assert_viral(self, viral_id: str, perfil_id: Optional[str] = None) -> None:
        rows = self.db.table(VIRAIS).select("id,perfil_id").eq("id", str(viral_id)).execute().data
        if not rows:
            raise EstruturaError(404, "Vídeo não encontrado.")
        if perfil_id and str(rows[0]["perfil_id"]) != str(perfil_id):
            raise EstruturaError(422, "O vídeo escolhido não pertence a este perfil.")

    def _assert_tipos(self, blocos: list[dict[str, Any]], *, corpo: bool) -> None:
        ids = {str(b["tipo_id"]) for b in blocos}
        achados = {str(t["id"]) for t in self._rows(TIPOS, "id", ids)}
        if ids - achados:
            raise EstruturaError(422 if corpo else 404, "Tipo de bloco não encontrado.")

    @staticmethod
    def _bloco_payload(b: dict[str, Any]) -> dict[str, Any]:
        out = {
            "nome": b["nome"], "tipo_id": str(b["tipo_id"]), "tempo": b.get("tempo"), "instrucao": b.get("instrucao"),
            "nota": b.get("nota"), "repeticoes": b.get("repeticoes", 1),
        }
        if b.get("id"):
            out["id"] = str(b["id"])
        return out

    def criar(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /estruturas``: all provenance ``admin``, ``origem='manual'``, event ``criada``."""
        self._exigir_admin()
        self._assert_perfil(body["perfil_id"])
        if body.get("viral_id"):
            self._assert_viral(body["viral_id"], body["perfil_id"])
        self._assert_tipos(body["blocos"], corpo=False)
        res = self._rpc("cs_estrutura_criar", {"p": {
            "perfil_id": str(body["perfil_id"]), "viral_id": str(body["viral_id"]) if body.get("viral_id") else None,
            "formula_headline": body["formula_headline"], "formato": body["formato"], "objetivos": list(body["objetivos"]),
            "status": body.get("status", "ativa"), "origem": "manual", "ator_id": self.user_id, "ator_tipo": "admin",
            "blocos": [self._bloco_payload(b) for b in body["blocos"]],
        }})
        return self.detalhe(res["id"])

    def atualizar(self, estrutura_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._exigir_admin()
        expected = patch.pop("expected_versao")
        if patch.get("viral_id"):
            rows = self.db.table(ESTRUTURAS).select("id,perfil_id").eq("id", str(estrutura_id)).execute().data
            if not rows:
                raise EstruturaError(404, "Estrutura não encontrada.")
            self._assert_viral(patch["viral_id"], rows[0]["perfil_id"])  # the source video belongs to the Estrutura's perfil
        payload = {k: (str(v) if k == "viral_id" and v else v) for k, v in patch.items()}
        self._rpc("cs_estrutura_atualizar", {
            "p_id": str(estrutura_id), "p_expected_versao": expected, "p_patch": payload, "p_ator": self.user_id,
        })
        return self.detalhe(estrutura_id)

    def substituir_blocos(self, estrutura_id: str, expected_versao: int, blocos: list[dict[str, Any]]) -> dict[str, Any]:
        self._exigir_admin()
        self._assert_tipos(blocos, corpo=True)
        self._rpc("cs_estrutura_substituir_blocos", {
            "p_id": str(estrutura_id), "p_expected_versao": expected_versao,
            "p_blocos": [self._bloco_payload(b) for b in blocos], "p_ator": self.user_id,
        }, corpo=True)
        return self.detalhe(estrutura_id)

    def confirmar(self, estrutura_id: str, expected_versao: int, campos: Optional[list[str]], todos: bool) -> dict[str, Any]:
        self._exigir_admin()
        self._rpc("cs_estrutura_confirmar", {
            "p_id": str(estrutura_id), "p_expected_versao": expected_versao,
            "p_campos": ["*"] if todos else list(campos or []), "p_ator": self.user_id,
        })
        return self.detalhe(estrutura_id)

    def publicar(self, estrutura_id: str, expected_versao: int) -> dict[str, Any]:
        self._exigir_admin()
        self._rpc("cs_estrutura_publicar", {"p_id": str(estrutura_id), "p_expected_versao": expected_versao, "p_ator": self.user_id})
        return self.detalhe(estrutura_id)

    def arquivar(self, estrutura_id: str) -> dict[str, Any]:
        self._exigir_admin()
        self._rpc("cs_estrutura_arquivar", {"p_id": str(estrutura_id), "p_ator": self.user_id})
        return self.detalhe(estrutura_id)

    def restaurar(self, estrutura_id: str) -> dict[str, Any]:
        self._exigir_admin()
        self._rpc("cs_estrutura_restaurar", {"p_id": str(estrutura_id), "p_ator": self.user_id})
        return self.detalhe(estrutura_id)

    def excluir(self, estrutura_id: str) -> None:
        self._exigir_admin()
        self._rpc("cs_estrutura_excluir", {"p_id": str(estrutura_id), "p_ator": self.user_id})

    # catalog writes ---------------------------------------------------------------------------------------

    def tipo_criar(self, body: dict[str, Any]) -> dict[str, Any]:
        self._exigir_admin()
        payload = {k: v for k, v in body.items() if v is not None or k == "tempo_tipico"}
        res = self._rpc("cs_estrutura_tipo_salvar", {"p": {**payload, "ator_id": self.user_id}})
        return self._tipo(res["id"])

    def tipo_atualizar(self, tipo_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._exigir_admin()
        self._rpc("cs_estrutura_tipo_salvar", {"p": {**patch, "id": str(tipo_id), "ator_id": self.user_id}})
        return self._tipo(tipo_id)

    def tipo_excluir(self, tipo_id: str) -> None:
        self._exigir_admin()
        self._rpc("cs_estrutura_tipo_excluir", {"p_id": str(tipo_id), "p_ator": self.user_id})


async def assinar_urls(data: Any, storage: Optional[StorageBackend]) -> Any:
    """Turn every ``_path`` placeholder under ``perfil`` / ``viral`` into a short-TTL signed URL (in place).

    A missing / unsignable file yields ``None`` and never fails the page (``viral_card.sign_thumbnail``)."""
    items: list[dict[str, Any]]
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, dict):
        items = [data]
    else:
        items = []
    for item in items:
        perfil = item.get("perfil")
        if isinstance(perfil, dict):
            if _PATH in perfil:  # the member shape carries no photo key: nothing to sign (and nothing to add)
                perfil["foto_url"] = await sign_thumbnail(storage, perfil.pop(_PATH, None))
        viral = item.get("viral")
        if isinstance(viral, dict):
            viral["thumbnail_url"] = await sign_thumbnail(storage, viral.pop(_PATH, None))
    return data


__all__ = [
    "BLOCOS", "ESTRUTURAS", "EstruturaError", "EstruturasService", "RESUMO", "STATUS_FILTROS", "TIPOS",
    "apresentar_tipo", "assinar_urls", "coded", "formula_trecho", "mapear_erro_rpc",
]
