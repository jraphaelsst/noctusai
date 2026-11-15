"""Estruturas library -- the PURE LOADER (estruturas-contract.md section 7, EST-3).

Reads a parsed JSON document of one of two vendor-shaped files, validates it row by row, maps it to library
Estruturas and upserts them idempotently ONLY through the EST-1 SECURITY DEFINER RPCs (``cs_estrutura_criar`` /
``cs_estrutura_atualizar`` / ``cs_estrutura_substituir_blocos``): the RPC mutates and writes the event row in ONE
transaction. There is NO model call, NO prompt, NO ``saida_ia`` and no AI provenance in this module (a test greps its
imports): the owner's reference dataset is already complete; the loader reads, validates, maps and writes.

Two entry points share one planner so a simulation and an apply can never disagree about the mapping:

* :func:`parse_documento` -- PURE: ``(fonte, conteudo, catalogo)`` -> validated :class:`LinhaPlano` rows + coded ignores.
* :func:`executar` -- the I/O half: reconciles the rows against the library (``created / updated / unchanged /
  ignored``) and, when ``aplicar`` is true, writes. Every row ends in exactly ONE bucket
  (``criadas + atualizadas + inalteradas + ignoradas == linhas_total``).

Privacy: the documents are vendor-derived (third-party creators' content plus the owner's reference fill). Nothing from
a row -- not a formula, a block name, a note -- is ever logged, put in an exception message, an error string or a
report: the only things that leave this module are counts and reason codes.

Idempotency (section 7.3): key ``(fonte_externa, ref_externa)`` + ``fonte_hash`` (sha256 of the normalised row). Same
hash -> ``inalteradas``. A changed hash updates ONLY the fields whose ``*_origem`` is ``fonte`` / ``referencia``: a
field an admin touched or confirmed (``admin``) is never overwritten (it is re-sent as it is, with its provenance).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.primitives.accents import fold_accents

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO

logger = logging.getLogger(__name__)

FONTES: tuple[str, ...] = ("referencia", "maquina_de_roteiros")
FONTE_EXTERNA: dict[str, str] = {"referencia": "corestudio", "maquina_de_roteiros": "maquina_de_roteiros"}
ORIGEM_ESTRUTURA: dict[str, str] = {"referencia": "import_corestudio", "maquina_de_roteiros": "import_maquina"}
_ORIGEM_POR_FONTE_EXTERNA: dict[str, str] = {FONTE_EXTERNA[f]: ORIGEM_ESTRUTURA[f] for f in FONTES}

MAX_LINHAS = 20_000
#: Fields of the Maquina file the owner kept OUT of the library (contract 7.2): reported in every plan so nothing is
#: lost silently.
CAMPOS_NAO_IMPORTADOS: dict[str, tuple[str, ...]] = {
    "referencia": (),
    "maquina_de_roteiros": (
        "quandoUsar", "quandoNaoUsar", "validacao", "exemplo", "aprovado", "criadoEm", "perfis.dna", "perfis.ganchos",
        "perfis.nuncaFaz", "perfis.pilares", "perfis.publico", "perfis.tom", "marcas", "roteiros",
    ),
}
#: The Maquina molde has no formula field; its ``nome`` stands in (required, non-empty) and is flagged PENDING review.
ROTULO_MAQUINA = "maquina-de-roteiros: nome do molde usado como fórmula"

# ── coded ignore reasons (never silent) ───────────────────────────────────────────────────────────────────
M_HANDLE = "handle_invalido"
M_ID = "id_invalido"
M_ID_DUP = "id_duplicado"
M_FORMULA_AUSENTE = "formula_ausente"
M_FORMULA_INVALIDA = "formula_invalida"
M_BLOCOS_AUSENTES = "blocos_ausentes"
M_ORDEM = "ordem_invalida"
M_BLOCO = "bloco_invalido"
M_TIPO = "tipo_desconhecido"
M_FORMATO = "formato_invalido"
M_OBJETIVOS = "objetivos_invalidos"
M_OPTOUT = "perfil_optout"
M_PERFIL_AUSENTE = "perfil_ausente"
M_LINHA = "linha_invalida"
M_INATIVA = "estrutura_inativa"
M_CONFLITO = "conflito_versao"
M_GRAVACAO = "erro_gravacao"
M_LIMITE = "limite_perfis"
MOTIVOS: tuple[str, ...] = (
    M_HANDLE, M_ID, M_ID_DUP, M_FORMULA_AUSENTE, M_FORMULA_INVALIDA, M_BLOCOS_AUSENTES, M_ORDEM, M_BLOCO, M_TIPO,
    M_FORMATO, M_OBJETIVOS, M_OPTOUT, M_PERFIL_AUSENTE, M_LINHA, M_INATIVA, M_CONFLITO, M_GRAVACAO, M_LIMITE,
)

_HANDLE_RE = re.compile(r"^[a-z0-9._]{1,30}$")
_ID_NUM_RE = re.compile(r"^\d+$")
_ID_MAQUINA_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


class ArquivoInvalido(Exception):
    """The document does not have the expected top-level shape (``motivo`` is a short code, never row text)."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


# ── pure helpers ───────────────────────────────────────────────────────────────────────────────────────────


def normalizar_handle(valor: Any) -> Optional[str]:
    """``@Foo`` -> ``foo``; ``None`` when it is not a valid Instagram handle (``^[a-z0-9._]{1,30}$``)."""
    if not isinstance(valor, str):
        return None
    h = valor.strip().lstrip("@").strip().lower()
    return h if _HANDLE_RE.match(h) else None


def normalizar_nome(valor: str) -> str:
    """Accent-, case- and whitespace-insensitive key for matching a block name to a catalog type."""
    return " ".join(fold_accents(valor).casefold().split())


def json_canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_documento(conteudo: Any) -> str:
    """The file identity both the API and the MCP tool compute: sha256 of the canonical JSON of the parsed document."""
    return hashlib.sha256(json_canonico(conteudo).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BlocoPlano:
    nome: str
    tipo_nome: str
    tempo: Optional[str]
    instrucao: Optional[str]
    nota: Optional[str]
    repeticoes: int
    nome_origem: str
    tipo_origem: str
    tempo_origem: str
    instrucao_origem: str


@dataclass(frozen=True)
class LinhaPlano:
    indice: int
    fonte_externa: str
    ref_externa: str
    handle: str
    perfil_nome: Optional[str]
    formula: str
    formula_origem: str
    formula_herdada_de: Optional[str]
    formato: str
    formato_origem: str
    objetivos: tuple[str, ...]
    objetivos_origem: str
    rotulo: Optional[str]
    blocos: tuple[BlocoPlano, ...]

    @property
    def hash(self) -> str:
        return hashlib.sha256(json_canonico({
            "fe": self.fonte_externa, "re": self.ref_externa, "h": self.handle, "f": self.formula, "fo": self.formula_origem,
            "hd": self.formula_herdada_de, "fm": self.formato, "fmo": self.formato_origem, "ob": list(self.objetivos),
            "obo": self.objetivos_origem, "ro": self.rotulo,
            "b": [[b.nome, b.tipo_nome, b.tempo, b.instrucao, b.nota, b.repeticoes, b.nome_origem, b.tipo_origem,
                   b.tempo_origem, b.instrucao_origem] for b in self.blocos],
        }).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Parseado:
    linhas_total: int
    linhas: tuple[LinhaPlano, ...]
    ignoradas: tuple[tuple[int, str], ...]  # (indice, motivo)
    campos_nao_importados: tuple[str, ...]


def _texto(valor: Any, maximo: int, *, obrigatorio: bool = False) -> tuple[bool, Optional[str]]:
    """``(ok, normalised)``: ``None`` for an empty optional text; not ok when it is not a string or too long."""
    if valor is None and not obrigatorio:
        return True, None
    if not isinstance(valor, str):
        return False, None
    texto = valor.strip()
    if not texto:
        return (not obrigatorio), None
    if len(texto) > maximo:
        return False, None
    return True, texto


def _bloco(raw: Any, *, nome_key: str, tipo_nome: Optional[str], origens: tuple[str, str, str, str], completo: bool) -> Optional[BlocoPlano]:
    if not isinstance(raw, dict):
        return None
    ok_n, nome = _texto(raw.get(nome_key), fmt.BLOCO_NOME_MAX, obrigatorio=True)
    ok_t, tempo = _texto(raw.get("tempo"), fmt.BLOCO_TEMPO_MAX)
    ok_i, instrucao = _texto(raw.get("instrucao"), fmt.BLOCO_INSTRUCAO_MAX)
    if completo:
        ok_o, nota = _texto(raw.get("nota"), fmt.BLOCO_NOTA_MAX)
        rep = raw.get("repeticoes", 1)
        ok_r = isinstance(rep, int) and not isinstance(rep, bool) and 1 <= rep <= fmt.BLOCO_REPETICOES_MAX
    else:
        ok_o, nota, rep, ok_r = True, None, 1, True
    if not (ok_n and ok_t and ok_i and ok_o and ok_r) or nome is None or tipo_nome is None:
        return None
    return BlocoPlano(nome, tipo_nome, tempo, instrucao, nota, int(rep), *origens)


def _objetivos(valor: Any) -> Optional[tuple[str, ...]]:
    if not isinstance(valor, list) or not 1 <= len(valor) <= fmt.MAX_OBJETIVOS:
        return None
    if not all(isinstance(o, str) and o in fmt.OBJETIVOS for o in valor) or len(set(valor)) != len(valor):
        return None
    return tuple(valor)


def _formula(valor: Any) -> tuple[Optional[str], Optional[str]]:
    """``(formula, motivo)``."""
    if not isinstance(valor, str) or not valor.strip():
        return None, M_FORMULA_AUSENTE
    texto = valor.strip()
    return (texto, None) if len(texto) <= fmt.FORMULA_MAX else (None, M_FORMULA_INVALIDA)


def _linha_referencia(i: int, raw: Any, tipos: frozenset[str]) -> LinhaPlano | str:
    if not isinstance(raw, dict):
        return M_LINHA
    handle = normalizar_handle(raw.get("perfil"))
    if handle is None:
        return M_HANDLE
    ref = raw.get("corestudio_id")
    if not isinstance(ref, str) or not _ID_NUM_RE.match(ref):
        return M_ID
    herdada = raw.get("formula_herdada_de")
    if herdada is not None:
        if isinstance(herdada, int) and not isinstance(herdada, bool):
            herdada = str(herdada)
        if not isinstance(herdada, str) or not _ID_NUM_RE.match(herdada):
            return M_ID
    formula, motivo = _formula(raw.get("formula_headline"))
    if formula is None:
        return motivo or M_FORMULA_AUSENTE
    formato = raw.get("formato")
    if not isinstance(formato, str) or formato not in fmt.FORMATOS:
        return M_FORMATO
    objetivos = _objetivos(raw.get("objetivos"))
    if objetivos is None:
        return M_OBJETIVOS
    blocos_raw = raw.get("blocos")
    if not isinstance(blocos_raw, list) or not 1 <= len(blocos_raw) <= fmt.BLOCOS_MAX:
        return M_BLOCOS_AUSENTES
    if not all(isinstance(b, dict) and isinstance(b.get("ordem"), int) and not isinstance(b.get("ordem"), bool) for b in blocos_raw):
        return M_ORDEM
    ordenados = sorted(blocos_raw, key=lambda b: b["ordem"])
    if [b["ordem"] for b in ordenados] != list(range(1, len(ordenados) + 1)):
        return M_ORDEM
    blocos: list[BlocoPlano] = []
    for b in ordenados:
        tipo = b.get("tipo")
        tipo = tipo.strip() if isinstance(tipo, str) else None
        if tipo is None or tipo not in tipos:
            return M_TIPO
        plano = _bloco(b, nome_key="nome_original", tipo_nome=tipo, origens=("fonte", "referencia", "referencia", "referencia"), completo=True)
        if plano is None:
            return M_BLOCO
        blocos.append(plano)
    rotulo = raw.get("preenchido_por")
    ok_r, rotulo = _texto(rotulo, 200)
    if not ok_r:
        return M_LINHA
    return LinhaPlano(
        indice=i, fonte_externa=FONTE_EXTERNA["referencia"], ref_externa=ref, handle=handle, perfil_nome=None,
        formula=formula, formula_origem="referencia" if herdada else "fonte", formula_herdada_de=herdada,
        formato=formato, formato_origem="referencia", objetivos=objetivos, objetivos_origem="referencia",
        rotulo=rotulo, blocos=tuple(blocos),
    )


def _linha_maquina(i: int, raw: Any, perfis: Mapping[str, tuple[Optional[str], Optional[str]]], tipos_norm: Mapping[str, str]) -> LinhaPlano | str:
    if not isinstance(raw, dict):
        return M_LINHA
    ref = raw.get("id")
    if not isinstance(ref, str) or not _ID_MAQUINA_RE.match(ref):
        return M_ID
    perfil_id = raw.get("perfilId")
    if not isinstance(perfil_id, str) or perfil_id not in perfis:
        return M_PERFIL_AUSENTE
    handle, nome_perfil = perfis[perfil_id]
    if handle is None:
        return M_HANDLE
    formula, motivo = _formula(raw.get("nome"))
    if formula is None:
        return motivo or M_FORMULA_AUSENTE
    formato = raw.get("formato")
    if not isinstance(formato, str) or formato not in fmt.FORMATOS:
        return M_FORMATO
    objetivos = _objetivos(raw.get("objetivos"))
    if objetivos is None:
        return M_OBJETIVOS
    blocos_raw = raw.get("blocos")
    if not isinstance(blocos_raw, list) or not 1 <= len(blocos_raw) <= fmt.BLOCOS_MAX:
        return M_BLOCOS_AUSENTES
    blocos: list[BlocoPlano] = []
    for b in blocos_raw:
        nome_bruto = b.get("nome") if isinstance(b, dict) else None
        tipo = tipos_norm.get(normalizar_nome(nome_bruto), NOME_OUTRO) if isinstance(nome_bruto, str) else NOME_OUTRO
        plano = _bloco(b, nome_key="nome", tipo_nome=tipo, origens=("fonte", "fonte", "fonte", "fonte"), completo=False)
        if plano is None:
            return M_BLOCO
        blocos.append(plano)
    return LinhaPlano(
        indice=i, fonte_externa=FONTE_EXTERNA["maquina_de_roteiros"], ref_externa=ref, handle=handle, perfil_nome=nome_perfil,
        formula=formula, formula_origem="referencia", formula_herdada_de=None, formato=formato, formato_origem="fonte",
        objetivos=objetivos, objetivos_origem="fonte", rotulo=ROTULO_MAQUINA, blocos=tuple(blocos),
    )


def parse_documento(fonte: str, conteudo: Any, tipos: Iterable[str]) -> Parseado:
    """Validate + map the whole document. ``tipos`` = the catalog type NAMES. Raises :class:`ArquivoInvalido` on a bad
    top-level shape; every row problem is a coded ignore (a row is never dropped silently)."""
    if fonte not in FONTES:
        raise ArquivoInvalido("fonte_desconhecida")
    nomes = frozenset(tipos)
    if NOME_OUTRO not in nomes:
        raise ArquivoInvalido("catalogo_sem_outro")
    if fonte == "referencia":
        if not isinstance(conteudo, list):
            raise ArquivoInvalido("esperado_array")
        rows: list[Any] = conteudo
        perfis: dict[str, tuple[Optional[str], Optional[str]]] = {}
    else:
        colecoes = conteudo.get("colecoes") if isinstance(conteudo, dict) else None
        if not isinstance(colecoes, dict) or not isinstance(colecoes.get("perfis"), list) or not isinstance(colecoes.get("moldes"), list):
            raise ArquivoInvalido("esperado_colecoes_perfis_moldes")
        rows = colecoes["moldes"]
        perfis = {}
        for p in colecoes["perfis"]:
            if isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"] not in perfis:
                nome = p.get("nome")
                perfis[p["id"]] = (normalizar_handle(p.get("handle")), nome.strip()[:200] or None if isinstance(nome, str) else None)
    if len(rows) > MAX_LINHAS:
        raise ArquivoInvalido("linhas_demais")
    tipos_norm = {normalizar_nome(n): n for n in nomes}
    linhas: list[LinhaPlano] = []
    ignoradas: list[tuple[int, str]] = []
    vistos: set[str] = set()
    for i, raw in enumerate(rows):
        res = _linha_referencia(i, raw, nomes) if fonte == "referencia" else _linha_maquina(i, raw, perfis, tipos_norm)
        if isinstance(res, str):
            ignoradas.append((i, res))
        elif res.ref_externa in vistos:
            ignoradas.append((i, M_ID_DUP))
        else:
            vistos.add(res.ref_externa)
            linhas.append(res)
    return Parseado(len(rows), tuple(linhas), tuple(ignoradas), CAMPOS_NAO_IMPORTADOS[fonte])


# ── payload builders (pure; what is sent to the RPCs) ──────────────────────────────────────────────────────


def _bloco_payload(b: BlocoPlano, tipo_id: str, bloco_id: Optional[str] = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "nome": b.nome, "tipo_id": tipo_id, "tempo": b.tempo, "instrucao": b.instrucao, "nota": b.nota, "repeticoes": b.repeticoes,
        "nome_origem": b.nome_origem, "tipo_origem": b.tipo_origem, "tempo_origem": b.tempo_origem, "instrucao_origem": b.instrucao_origem,
    }
    if bloco_id:
        out["id"] = bloco_id
    return out


def payload_criar(l: LinhaPlano, *, perfil_id: str, tipo_ids: Mapping[str, str], importacao_id: str, ator_id: Optional[str]) -> dict[str, Any]:
    """``cs_estrutura_criar(p)`` for a NEW row: ``ator_tipo='sistema_import'`` (event ``importada``), all provenance as mapped."""
    return {
        "perfil_id": perfil_id, "formula_headline": l.formula, "formato": l.formato, "objetivos": list(l.objetivos),
        "status": "ativa", "origem": _ORIGEM_POR_FONTE_EXTERNA[l.fonte_externa],
        "fonte_externa": l.fonte_externa, "ref_externa": l.ref_externa, "fonte_hash": l.hash,
        "formula_herdada_de": l.formula_herdada_de, "referencia_rotulo": l.rotulo, "formula_origem": l.formula_origem,
        "formato_origem": l.formato_origem, "objetivos_origem": l.objetivos_origem, "ator_id": ator_id,
        "ator_tipo": "sistema_import", "importacao_id": importacao_id,
        "blocos": [_bloco_payload(b, tipo_ids[b.tipo_nome]) for b in l.blocos],
    }


def _admin(origem: Any) -> bool:
    return origem == "admin"


def montar_patch(l: LinhaPlano, existente: Mapping[str, Any], *, importacao_id: str) -> dict[str, Any]:
    """``cs_estrutura_atualizar`` patch: a field whose ``*_origem`` is ``admin`` is NOT in the patch (never overwritten).
    ``fonte_hash`` is always stamped (so the next run of the same file is ``inalteradas``)."""
    patch: dict[str, Any] = {"fonte_hash": l.hash, "_ator_tipo": "sistema_import", "_evento": "atualizada_import", "_importacao_id": importacao_id}
    if not _admin(existente.get("formula_origem")):
        patch.update(formula_headline=l.formula, formula_origem=l.formula_origem, formula_herdada_de=l.formula_herdada_de, referencia_rotulo=l.rotulo)
    if not _admin(existente.get("formato_origem")):
        patch.update(formato=l.formato, formato_origem=l.formato_origem)
    if not _admin(existente.get("objetivos_origem")):
        patch.update(objetivos=list(l.objetivos), objetivos_origem=l.objetivos_origem)
    return patch


_CAMPOS_COM_ORIGEM = ("nome", "tipo", "tempo", "instrucao")


def _bloco_tocado_por_admin(eb: Mapping[str, Any]) -> bool:
    return any(_admin(eb.get(f"{c}_origem")) for c in _CAMPOS_COM_ORIGEM)


def montar_blocos(
    l: LinhaPlano, existentes: Sequence[Mapping[str, Any]], tipo_ids: Mapping[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """The FULL ordered block list for ``cs_estrutura_substituir_blocos`` + how many blocks it adds.

    Blocks are matched to the existing ones by position. For a matched block an ``admin``-origin field keeps its
    existing value AND provenance; a block an admin touched at all also keeps ``nota`` / ``repeticoes`` (which carry no
    provenance column). Existing blocks beyond the file's are removed unless an admin touched them (kept at the end)."""
    por_ordem = {int(b["ordem"]): b for b in existentes}
    out: list[dict[str, Any]] = []
    for pos, nb in enumerate(l.blocos, start=1):
        eb = por_ordem.get(pos)
        item = _bloco_payload(nb, tipo_ids[nb.tipo_nome], str(eb["id"]) if eb else None)
        if eb:
            for campo in _CAMPOS_COM_ORIGEM:
                if _admin(eb.get(f"{campo}_origem")):
                    item["tipo_id" if campo == "tipo" else campo] = eb["tipo_id"] if campo == "tipo" else eb.get(campo)
                    item[f"{campo}_origem"] = "admin"
            if _bloco_tocado_por_admin(eb):
                item["nota"], item["repeticoes"] = eb.get("nota"), eb.get("repeticoes", 1)
        out.append(item)
    for pos in sorted(p for p in por_ordem if p > len(l.blocos)):
        eb = por_ordem[pos]
        if _bloco_tocado_por_admin(eb):
            out.append({
                "id": str(eb["id"]), "nome": eb["nome"], "tipo_id": eb["tipo_id"], "tempo": eb.get("tempo"), "instrucao": eb.get("instrucao"),
                "nota": eb.get("nota"), "repeticoes": eb.get("repeticoes", 1), "nome_origem": eb.get("nome_origem", "admin"),
                "tipo_origem": eb.get("tipo_origem", "admin"), "tempo_origem": eb.get("tempo_origem", "admin"),
                "instrucao_origem": eb.get("instrucao_origem", "admin"),
            })
    novos = sum(1 for it in out if "id" not in it)
    return out, novos


def blocos_iguais(novos: Sequence[Mapping[str, Any]], existentes: Sequence[Mapping[str, Any]]) -> bool:
    """True when sending ``novos`` would change nothing (same ids, order, content, provenance) -- skips the RPC."""
    if len(novos) != len(existentes):
        return False
    ordenados = sorted(existentes, key=lambda b: int(b["ordem"]))
    campos = ("nome", "tipo_id", "tempo", "instrucao", "nota", "repeticoes", "nome_origem", "tipo_origem", "tempo_origem", "instrucao_origem")
    for n, e in zip(novos, ordenados):
        if str(n.get("id") or "") != str(e["id"]) or any(n.get(c) != e.get(c) for c in campos):
            return False
    return True


# ── I/O seam ───────────────────────────────────────────────────────────────────────────────────────────────


class ImportStore(Protocol):
    """Everything the loader reads / writes. The real one (:class:`SupabaseImportStore`) speaks PostgREST + the RPCs."""

    def tipos(self) -> dict[str, str]: ...  # name -> id (every catalog row, active or not)
    def optouts(self, handles: Iterable[str]) -> set[str]: ...
    def perfis(self, handles: Iterable[str]) -> dict[str, str]: ...  # handle -> platform perfil id
    def total_perfis(self) -> int: ...
    def existentes(self, fonte_externa: str, refs: Iterable[str]) -> dict[str, dict[str, Any]]: ...
    def blocos_de(self, estrutura_id: str) -> list[dict[str, Any]]: ...
    def criar_perfil(self, handle: str, nome: Optional[str], ator_id: Optional[str]) -> str: ...
    def evento_perfil(self, perfil_id: str, handle: str, tipo: str, ator_id: Optional[str]) -> None: ...
    def rpc(self, nome: str, params: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class Contadores:
    linhas_total: int = 0
    perfis_criados: int = 0
    perfis_mesclados: int = 0
    estruturas_criadas: int = 0
    estruturas_atualizadas: int = 0
    estruturas_inalteradas: int = 0
    estruturas_ignoradas: int = 0
    blocos_criados: int = 0
    ignoradas_motivos: dict[str, int] = field(default_factory=dict)

    def ignorar(self, motivo: str) -> None:
        self.estruturas_ignoradas += 1
        self.ignoradas_motivos[motivo] = self.ignoradas_motivos.get(motivo, 0) + 1

    def fechado(self) -> bool:
        """Every row is in exactly one bucket."""
        return (self.estruturas_criadas + self.estruturas_atualizadas + self.estruturas_inalteradas + self.estruturas_ignoradas) == self.linhas_total

    def como_dict(self) -> dict[str, Any]:
        return {
            "linhas_total": self.linhas_total, "perfis_criados": self.perfis_criados, "perfis_mesclados": self.perfis_mesclados,
            "estruturas_criadas": self.estruturas_criadas, "estruturas_atualizadas": self.estruturas_atualizadas,
            "estruturas_inalteradas": self.estruturas_inalteradas, "estruturas_ignoradas": self.estruturas_ignoradas,
            "blocos_criados": self.blocos_criados, "ignoradas_motivos": dict(sorted(self.ignoradas_motivos.items())),
        }


def _codigo_rpc(exc: BaseException) -> Optional[str]:
    """The coded refusal of an RPC (``RAISE EXCEPTION '<code>'``) or ``None`` for an unexpected failure."""
    from app.modules.media_creation.services.estruturas_service import mapear_erro_rpc

    mapped = mapear_erro_rpc(exc)
    if mapped is None:
        return None
    detail = mapped.detail
    return str(detail.get("code")) if isinstance(detail, dict) else "recusada"


def executar(
    store: ImportStore, fonte: str, conteudo: Any, *, aplicar: bool, importacao_id: str, ator_id: Optional[str],
    limite_perfis: int, progresso: Optional[Any] = None,
) -> Contadores:
    """Plan (``aplicar=False``: reads only) or apply (writes through the RPCs) the whole document.

    Unexpected failures (infra, an RPC refusal that is not one of ours) PROPAGATE: the job retries and a re-run is safe
    (idempotent). A coded per-row refusal is an ignore with ``erro_gravacao`` / ``conflito_versao`` / ``estrutura_inativa``.
    ``progresso(contadores)`` is called after every profile batch."""
    tipos = store.tipos()
    parseado = parse_documento(fonte, conteudo, tipos)
    c = Contadores(linhas_total=parseado.linhas_total)
    for _indice, motivo in parseado.ignoradas:
        c.ignorar(motivo)

    por_handle: dict[str, list[LinhaPlano]] = {}
    for linha in parseado.linhas:
        por_handle.setdefault(linha.handle, []).append(linha)
    bloqueados = store.optouts(por_handle)
    existentes_perfil = store.perfis(por_handle)
    novos_planejados = 0
    total_atual = store.total_perfis() if any(h not in existentes_perfil for h in por_handle) else 0

    for handle in sorted(por_handle):
        linhas = por_handle[handle]
        if handle in bloqueados:
            for _ in linhas:
                c.ignorar(M_OPTOUT)
            continue
        perfil_id = existentes_perfil.get(handle)
        novo = perfil_id is None
        if novo and total_atual + novos_planejados >= limite_perfis:
            for _ in linhas:
                c.ignorar(M_LIMITE)
            continue
        if novo:
            novos_planejados += 1
            c.perfis_criados += 1
            if aplicar:
                nome = next((l.perfil_nome for l in linhas if l.perfil_nome), None)
                perfil_id = store.criar_perfil(handle, nome, ator_id)
                store.evento_perfil(perfil_id, handle, "criado", ator_id)
        else:
            c.perfis_mesclados += 1
        if aplicar and perfil_id:
            store.evento_perfil(perfil_id, handle, "importado", ator_id)

        refs_por_fonte: dict[str, dict[str, dict[str, Any]]] = {}
        for l in linhas:
            if l.fonte_externa not in refs_por_fonte:
                refs_por_fonte[l.fonte_externa] = store.existentes(l.fonte_externa, [x.ref_externa for x in linhas if x.fonte_externa == l.fonte_externa])
        for l in linhas:
            _processar(store, c, l, refs_por_fonte[l.fonte_externa].get(l.ref_externa), perfil_id, tipos, aplicar=aplicar,
                       importacao_id=importacao_id, ator_id=ator_id)
        if progresso is not None:
            progresso(c)
    if not c.fechado():  # a bug, never a silent miscount
        raise RuntimeError("importação: contagem não fecha com o total de linhas")
    return c


def _processar(
    store: ImportStore, c: Contadores, l: LinhaPlano, existente: Optional[dict[str, Any]], perfil_id: Optional[str],
    tipos: Mapping[str, str], *, aplicar: bool, importacao_id: str, ator_id: Optional[str],
) -> None:
    if existente is None:
        if aplicar:
            try:
                store.rpc("cs_estrutura_criar", {"p": payload_criar(l, perfil_id=str(perfil_id), tipo_ids=tipos, importacao_id=importacao_id, ator_id=ator_id)})
            except Exception as exc:  # noqa: BLE001 - a coded refusal is a row ignore; anything else propagates
                if _codigo_rpc(exc) is None:
                    raise
                logger.warning("estruturas.importar: linha %s recusada na criação (%s)", l.indice, _codigo_rpc(exc))
                c.ignorar(M_GRAVACAO)
                return
        c.estruturas_criadas += 1
        c.blocos_criados += len(l.blocos)
        return
    if existente.get("fonte_hash") == l.hash:
        c.estruturas_inalteradas += 1
        return
    if existente.get("status") == "arquivada":
        c.ignorar(M_INATIVA)
        return
    blocos_existentes = store.blocos_de(str(existente["id"]))
    blocos, novos = montar_blocos(l, blocos_existentes, tipos)
    if not aplicar:
        c.estruturas_atualizadas += 1
        c.blocos_criados += novos
        return
    versao = int(existente["versao"])
    try:
        if not blocos_iguais(blocos, blocos_existentes):
            # blocks FIRST, the hash stamp LAST: a failure between the two leaves the old hash, so a re-run redoes the row
            res = store.rpc("cs_estrutura_substituir_blocos", {
                "p_id": str(existente["id"]), "p_expected_versao": versao,
                "p_blocos": {"blocos": blocos, "ator_tipo": "sistema_import", "evento": "atualizada_import", "importacao_id": importacao_id},
                "p_ator": ator_id,
            })
            versao = int(res.get("versao", versao))
        store.rpc("cs_estrutura_atualizar", {
            "p_id": str(existente["id"]), "p_expected_versao": versao,
            "p_patch": montar_patch(l, existente, importacao_id=importacao_id), "p_ator": ator_id,
        })
    except Exception as exc:  # noqa: BLE001 - coded refusals are row ignores; anything else propagates
        codigo = _codigo_rpc(exc)
        if codigo is None:
            raise
        logger.warning("estruturas.importar: linha %s recusada na atualização (%s)", l.indice, codigo)
        c.ignorar({"versao_desatualizada": M_CONFLITO, "estrutura_inativa": M_INATIVA}.get(codigo, M_GRAVACAO))
        return
    c.estruturas_atualizadas += 1
    c.blocos_criados += novos


# ── the real store ─────────────────────────────────────────────────────────────────────────────────────────

TIPOS_T = "cs_estrutura_tipos_bloco"
ESTRUTURAS_T = "cs_estruturas"
BLOCOS_T = "cs_estrutura_blocos"
PERFIS_T = "cs_perfis_monitorados"
PERFIL_EVENTOS_T = "cs_perfil_eventos"
OPTOUTS_T = "cs_biblioteca_optouts"
EXISTENTE_COLS = "id,ref_externa,versao,status,fonte_hash,formula_origem,formato_origem,objetivos_origem"
BLOCO_COLS = "id,ordem,tipo_id,nome,tempo,instrucao,nota,repeticoes,nome_origem,tipo_origem,tempo_origem,instrucao_origem"


class SupabaseImportStore:
    """PostgREST reads + RPC writes. The library tables are service-role READ-only; every Estrutura write is an RPC.

    NOC-REMEDIATE[est3-perfil-write]: the platform profile + its ``cs_perfil_eventos`` row are inserted directly (no
    RPC exists for them in migration 350); this relies on migration 351 (EST-2: ``org_id`` nullable, ``monitorar``,
    ``cs_perfil_eventos``) granting the service role INSERT. Move to an RPC if EST-2 ships one. -- 2026-11-15"""

    def __init__(self, db: Any):
        self.db = db

    def tipos(self) -> dict[str, str]:
        rows = self.db.table(TIPOS_T).select("id,nome").execute().data or []
        return {str(r["nome"]): str(r["id"]) for r in rows}

    def optouts(self, handles: Iterable[str]) -> set[str]:
        out: set[str] = set()
        for chunk in batched(sorted(set(handles))):
            out |= {str(r["handle"]) for r in (self.db.table(OPTOUTS_T).select("handle").in_("handle", chunk).execute().data or [])}
        return out

    def perfis(self, handles: Iterable[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for chunk in batched(sorted(set(handles))):
            rows = self.db.table(PERFIS_T).select("id,handle").eq("rede", "instagram").is_("org_id", "null").in_("handle", chunk).execute().data or []
            out.update({str(r["handle"]): str(r["id"]) for r in rows})
        return out

    def total_perfis(self) -> int:
        res = self.db.table(PERFIS_T).select("id", count="exact").is_("org_id", "null").execute()
        return res.count if getattr(res, "count", None) is not None else len(res.data or [])

    def existentes(self, fonte_externa: str, refs: Iterable[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for chunk in batched(sorted(set(refs))):
            rows = self.db.table(ESTRUTURAS_T).select(EXISTENTE_COLS).eq("fonte_externa", fonte_externa).in_("ref_externa", chunk).execute().data or []
            out.update({str(r["ref_externa"]): r for r in rows})
        return out

    def blocos_de(self, estrutura_id: str) -> list[dict[str, Any]]:
        return self.db.table(BLOCOS_T).select(BLOCO_COLS).eq("estrutura_id", str(estrutura_id)).order("ordem").execute().data or []

    def criar_perfil(self, handle: str, nome: Optional[str], ator_id: Optional[str]) -> str:
        row = {"rede": "instagram", "handle": handle, "nome": nome, "org_id": None, "monitorar": False, "status": "aguardando", "created_by": ator_id}
        return str(self.db.table(PERFIS_T).insert(row).execute().data[0]["id"])

    def evento_perfil(self, perfil_id: str, handle: str, tipo: str, ator_id: Optional[str]) -> None:
        self.db.table(PERFIL_EVENTOS_T).insert({
            "perfil_id": str(perfil_id), "handle": handle, "tipo": tipo, "ator_id": ator_id, "ator_tipo": "sistema_import",
        }).execute()

    def rpc(self, nome: str, params: dict[str, Any]) -> dict[str, Any]:
        data = self.db.rpc(nome, params).execute().data
        return data if isinstance(data, dict) else {}



# ── the load run (lote) lifecycle ──────────────────────────────────────────────────────────────────────────

IMPORTACOES_T = "cs_estrutura_importacoes"
JOB_TYPE = "estruturas.importar"
SIMULACAO_VALIDADE_HORAS = 24
PREFIXO_BLOB = "importacoes/"
LISTA_MAX = 20
IMPORTACAO_COLS = (
    "id,fonte,arquivo_sha256,arquivo_nome,status,dry_run,linhas_total,perfis_criados,perfis_mesclados,estruturas_criadas,"
    "estruturas_atualizadas,estruturas_inalteradas,estruturas_ignoradas,blocos_criados,ignoradas_motivos,erro,created_at,finished_at"
)
ERRO_ARQUIVO_INDISPONIVEL = "arquivo_indisponivel"
ERRO_JOB_FALHOU = "job_falhou"


class ImportacaoError(Exception):
    """A refusal with its HTTP status; ``detail`` is ``{"code", "detail", ...}`` (the flat coded shape, EST-1)."""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(code)
        self.status = status
        self.detail = {"code": code, "detail": message, **extra}


def apresentar_relatorio(row: Mapping[str, Any]) -> dict[str, Any]:
    """The ``ImportacaoRelatorio`` of contract 6.3 (counts + codes only -- a lote row never holds row text)."""
    fonte = row["fonte"]
    return {
        "id": str(row["id"]), "fonte": fonte, "status": row["status"], "dry_run": bool(row["dry_run"]),
        "arquivo_sha256": row["arquivo_sha256"], "linhas_total": int(row.get("linhas_total") or 0),
        "perfis_criados": int(row.get("perfis_criados") or 0), "perfis_mesclados": int(row.get("perfis_mesclados") or 0),
        "estruturas_criadas": int(row.get("estruturas_criadas") or 0), "estruturas_atualizadas": int(row.get("estruturas_atualizadas") or 0),
        "estruturas_inalteradas": int(row.get("estruturas_inalteradas") or 0), "estruturas_ignoradas": int(row.get("estruturas_ignoradas") or 0),
        "ignoradas_motivos": dict(row.get("ignoradas_motivos") or {}), "blocos_criados": int(row.get("blocos_criados") or 0),
        "campos_nao_importados": list(CAMPOS_NAO_IMPORTADOS.get(fonte, ())), "erro": row.get("erro"),
        "created_at": row.get("created_at"), "finished_at": row.get("finished_at"),
    }


def _agora_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ImportacaoService:
    """Simulate / start / read load runs. Platform admins only (the router's gate); ``user_id`` = the admin."""

    def __init__(self, db: Any, *, user_id: str, limite_perfis: int, store: Optional[ImportStore] = None):
        self.db = db
        self.user_id = str(user_id)
        self.limite_perfis = int(limite_perfis)
        self.store: ImportStore = store or SupabaseImportStore(db)

    def _validar(self, fonte: str, conteudo: Any) -> Parseado:
        try:
            return parse_documento(fonte, conteudo, self.store.tipos())
        except ArquivoInvalido as exc:
            raise ImportacaoError(422, "arquivo_invalido", "O arquivo de importação não tem o formato esperado.", motivo=exc.motivo) from exc

    def simular(self, fonte: str, conteudo: Any, arquivo_nome: Optional[str]) -> dict[str, Any]:
        """Dry-run: reads + plans; the ONLY write is the ``simulada`` lote row (counters, no row text)."""
        self._validar(fonte, conteudo)
        lote_id = _uuid()
        try:
            contadores = executar(self.store, fonte, conteudo, aplicar=False, importacao_id=lote_id, ator_id=self.user_id, limite_perfis=self.limite_perfis)
        except ArquivoInvalido as exc:
            raise ImportacaoError(422, "arquivo_invalido", "O arquivo de importação não tem o formato esperado.", motivo=exc.motivo) from exc
        agora = _agora_iso()
        row = self.db.table(IMPORTACOES_T).insert({
            "id": lote_id, "fonte": fonte, "arquivo_sha256": sha256_documento(conteudo), "arquivo_nome": _nome_arquivo(arquivo_nome),
            "status": "simulada", "dry_run": True, "iniciada_por": self.user_id, "created_at": agora, "finished_at": agora, **contadores.como_dict(),
        }).execute().data[0]
        return apresentar_relatorio(row)

    def _simulacao_recente(self, fonte: str, sha: str) -> bool:
        from datetime import datetime, timedelta, timezone

        desde = (datetime.now(timezone.utc) - timedelta(hours=SIMULACAO_VALIDADE_HORAS)).isoformat()
        rows = (
            self.db.table(IMPORTACOES_T).select("id").eq("arquivo_sha256", sha).eq("fonte", fonte).eq("status", "simulada")
            .gte("created_at", desde).limit(1).execute().data
        )
        return bool(rows)

    def iniciar(self, fonte: str, conteudo: Any, arquivo_nome: Optional[str]) -> dict[str, Any]:
        """Apply, step 1: refuse without a same-sha simulation (409) or while another run is in progress (409), then
        record the ``em_andamento`` lote. The router stores the document + enqueues the job."""
        parseado = self._validar(fonte, conteudo)
        sha = sha256_documento(conteudo)
        if not self._simulacao_recente(fonte, sha):
            raise ImportacaoError(409, "simulacao_obrigatoria", "Rode a simulação deste arquivo antes de aplicar.")
        if self.db.table(IMPORTACOES_T).select("id").eq("status", "em_andamento").limit(1).execute().data:
            raise ImportacaoError(409, "importacao_em_andamento", "Já existe uma importação em andamento.")
        try:
            row = self.db.table(IMPORTACOES_T).insert({
                "id": _uuid(), "fonte": fonte, "arquivo_sha256": sha, "arquivo_nome": _nome_arquivo(arquivo_nome), "status": "em_andamento",
                "dry_run": False, "linhas_total": parseado.linhas_total, "iniciada_por": self.user_id, "created_at": _agora_iso(),
            }).execute().data[0]
        except Exception as exc:  # noqa: BLE001 - the partial unique index = a concurrent run won
            from noctusai_lib.primitives.postgrest_errors import is_unique_violation

            if is_unique_violation(exc):
                raise ImportacaoError(409, "importacao_em_andamento", "Já existe uma importação em andamento.") from exc
            raise
        return apresentar_relatorio(row)

    def falhar(self, importacao_id: str, erro: str) -> None:
        """Settle an ``em_andamento`` lote as ``falhou`` (a terminal lote is left alone). ``erro`` is a CODE."""
        self.db.table(IMPORTACOES_T).update({"status": "falhou", "erro": erro[:200], "finished_at": _agora_iso(), "updated_at": _agora_iso()}) \
            .eq("id", str(importacao_id)).eq("status", "em_andamento").execute()

    def obter(self, importacao_id: str) -> dict[str, Any]:
        rows = self.db.table(IMPORTACOES_T).select(IMPORTACAO_COLS).eq("id", str(importacao_id)).execute().data
        if not rows:
            raise ImportacaoError(404, "importacao_nao_encontrada", "Importação não encontrada.")
        return apresentar_relatorio(rows[0])

    def listar(self, limit: int, offset: int) -> dict[str, Any]:
        res = (
            self.db.table(IMPORTACOES_T).select(IMPORTACAO_COLS, count="exact").order("created_at", desc=True)
            .range(offset, offset + min(limit, LISTA_MAX) - 1).execute()
        )
        items = [apresentar_relatorio(r) for r in (res.data or [])]
        return {"items": items, "total": res.count if getattr(res, "count", None) is not None else len(items)}


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def _nome_arquivo(nome: Optional[str]) -> Optional[str]:
    """The upload's file name, bounded (the column CHECK is 300). A name is operator-chosen provenance, not row text."""
    return nome.strip()[:300] or None if isinstance(nome, str) else None


def chave_blob(importacao_id: str) -> str:
    return f"{PREFIXO_BLOB}{importacao_id}.json"


# ── job handler: ``estruturas.importar`` ────────────────────────────────────────────────────────────────────


def _progresso(db: Any, importacao_id: str):
    def grava(c: Contadores) -> None:
        db.table(IMPORTACOES_T).update({**c.como_dict(), "updated_at": _agora_iso()}).eq("id", importacao_id).eq("status", "em_andamento").execute()

    return grava


async def executar_job(
    db: Any, storage: Any, importacao_id: str, *, limite_perfis: int, ultima_tentativa: bool, store: Optional[ImportStore] = None,
) -> None:
    """Run one ``em_andamento`` lote to its end. A lote that is not ``em_andamento`` is a no-op (idempotent redelivery).

    Unexpected failures re-raise (the worker retries; a re-run is idempotent). On the LAST attempt the lote is settled
    ``falhou`` with a code and the stored document is deleted. The document is also deleted on success."""
    import asyncio

    from noctusai_lib.domain.jobs import DeadLetterError

    from app.modules.media_creation.deps import BIBLIOTECA_BUCKET

    rows = db.table(IMPORTACOES_T).select("id,fonte,status,iniciada_por").eq("id", importacao_id).execute().data
    if not rows:
        raise DeadLetterError("importação inexistente")
    lote = rows[0]
    if lote["status"] != "em_andamento":
        return
    svc = ImportacaoService(db, user_id=str(lote.get("iniciada_por") or ""), limite_perfis=limite_perfis, store=store)
    chave = chave_blob(importacao_id)
    try:
        blob = await storage.get(bucket=BIBLIOTECA_BUCKET, key=chave)
        if blob is None:
            svc.falhar(importacao_id, ERRO_ARQUIVO_INDISPONIVEL)
            raise DeadLetterError(ERRO_ARQUIVO_INDISPONIVEL)
        conteudo = json.loads(blob.data)
        contadores = await asyncio.to_thread(
            executar, svc.store, lote["fonte"], conteudo, aplicar=True, importacao_id=importacao_id,
            ator_id=str(lote["iniciada_por"]) if lote.get("iniciada_por") else None, limite_perfis=limite_perfis,
            progresso=_progresso(db, importacao_id),
        )
        db.table(IMPORTACOES_T).update({
            **contadores.como_dict(), "status": "concluida", "erro": None, "finished_at": _agora_iso(), "updated_at": _agora_iso(),
        }).eq("id", importacao_id).eq("status", "em_andamento").execute()
    except DeadLetterError:
        await storage.delete(bucket=BIBLIOTECA_BUCKET, key=chave)
        raise
    except ArquivoInvalido as exc:
        svc.falhar(importacao_id, f"arquivo_invalido:{exc.motivo}")
        await storage.delete(bucket=BIBLIOTECA_BUCKET, key=chave)
        raise DeadLetterError("arquivo_invalido") from exc
    except Exception as exc:
        # only the exception CLASS is recorded: a message may carry row text
        logger.error("estruturas.importar: lote %s falhou (%s)", importacao_id, type(exc).__name__)
        if ultima_tentativa:
            svc.falhar(importacao_id, f"erro:{type(exc).__name__}")
            await storage.delete(bucket=BIBLIOTECA_BUCKET, key=chave)
        raise
    await storage.delete(bucket=BIBLIOTECA_BUCKET, key=chave)


async def handle_importar(job: Any) -> None:
    from app.config import settings
    from app.dependencies import get_admin_client
    from app.modules.certidoes.deps import storage_for
    from noctusai_lib.domain.jobs import DeadLetterError

    importacao_id = (job.payload or {}).get("importacao_id")
    if not importacao_id:
        raise DeadLetterError("payload sem importacao_id")
    db = get_admin_client()
    if db is None:
        raise RuntimeError("sem cliente admin do Supabase")  # retried by the worker policy
    await executar_job(
        db, storage_for(db), str(importacao_id), limite_perfis=int(settings.biblioteca_max_perfis_plataforma),
        ultima_tentativa=job.retry_count >= job.max_retries,
    )


def reconciliar_dead_letter(db: Any, job: Any) -> None:
    """``on_dead_letter``: a dead-lettered queue row settles its still-running lote as ``falhou`` (terminal ones stay)."""
    importacao_id = (job.payload or {}).get("importacao_id")
    if not importacao_id:
        return
    db.table(IMPORTACOES_T).update({"status": "falhou", "erro": ERRO_JOB_FALHOU, "finished_at": _agora_iso(), "updated_at": _agora_iso()}) \
        .eq("id", str(importacao_id)).eq("status", "em_andamento").execute()


def register() -> None:
    """Register the ``estruturas.importar`` handler + dead-letter reconciler (idempotent)."""
    from app.modules.media_creation.services import geracao_jobs

    geracao_jobs.register_handler(JOB_TYPE, handle_importar, on_dead_letter=reconciliar_dead_letter)


register()


__all__ = [
    "ArquivoInvalido", "BlocoPlano", "ImportacaoError", "ImportacaoService", "JOB_TYPE", "apresentar_relatorio", "chave_blob", "executar_job", "handle_importar", "reconciliar_dead_letter", "register", "CAMPOS_NAO_IMPORTADOS", "Contadores", "FONTES", "ImportStore", "LinhaPlano", "MOTIVOS",
    "Parseado", "SupabaseImportStore", "blocos_iguais", "executar", "json_canonico", "montar_blocos", "montar_patch",
    "normalizar_handle", "normalizar_nome", "parse_documento", "payload_criar", "sha256_documento",
]
