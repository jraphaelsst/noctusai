"""Estruturas retrieval for the AI (estruturas-contract.md sections 8.1-8.3, 8.6): the POOL and the deterministic,
pre-LLM free-text PROFILE-NAME resolver.

The seed LLM layer has no tool use (``NOC-REMEDIATE[llm-tool-use]``), so retrieval is a server step that runs
BEFORE the single model call; its result is put in a ``<material>`` block by ``prompts/estruturas_contexto.py``.
When the seed gains tool calling, :func:`resolver_perfis_no_texto` and :func:`montar_pool` become tools with no
API change.

Everything here reads the PLATFORM-WIDE library (no ``org_id`` on ``cs_estruturas`` / profiles); the only
org-scoped input is the brand's own selection, read through :meth:`EstruturasService.perfis_selecionados`.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.primitives.accents import fold_accents

logger = logging.getLogger(__name__)

ESTRUTURAS = "cs_estruturas"
BLOCOS = "cs_estrutura_blocos"
TIPOS = "cs_estrutura_tipos_bloco"
PERFIS = "cs_perfis_monitorados"

#: The chat's per-context cap on offered Estruturas (the per-lote cap of batches is the caller's).
MAX_ESTRUTURAS = 12
#: How long the in-process profile index lives (section 8.3).
INDICE_TTL_S = 60.0
#: Hard ceiling of the profile index; the contract sizes it at ~600 rows -- more is logged, never silently cut.
INDICE_MAX_PERFIS = 2000
MAX_CANDIDATOS = 5
MAX_SUGESTOES = 3
_MAX_TOKENS_TRECHO = 4

# ── normalisation ───────────────────────────────────────────────────────────────────────────────────────────

_QUEBRA_RE = re.compile(r"[,;:!?\n()\[\]{}]|\.(?=\s|$)")
_FORA_RE = re.compile(r"[^a-z0-9@._| ]")
_ESPACOS_RE = re.compile(r"\s+")
_QUEBRAS_SEGUIDAS_RE = re.compile(r"\|(?: \|)+")


def normalizar(texto: str) -> str:
    """NFKD accent fold -> casefold -> keep ``[a-z0-9@._ ]`` -> collapse spaces. Clause breaks
    (``, ; : ! ? ( )``, newline, a dot followed by a space/end) become a ``|`` marker so a trigger span never
    runs across them; ``.`` stays inside a handle."""
    t = fold_accents(texto).casefold()  # NFKD fold: also covers the NFKC compatibility characters
    t = _QUEBRA_RE.sub(" | ", t)
    t = _ESPACOS_RE.sub(" ", _FORA_RE.sub(" ", t)).strip()
    return _QUEBRAS_SEGUIDAS_RE.sub("|", t)


def _sem_separadores(handle: str) -> str:
    return re.sub(r"[._]", "", handle)


def _tokens(texto: str) -> list[str]:
    return [t for t in re.split(r"[ ._]+", texto) if t and t != "|"]


# ── the profile index ───────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PerfilIndexado:
    id: str
    handle: str
    nome: Optional[str]
    handle_norm: str = ""
    handle_plano: str = ""  # handle without ``._`` separators
    handle_tokens: tuple[str, ...] = ()
    nome_norm: str = ""
    nome_tokens: tuple[str, ...] = ()
    sem_estruturas: bool = False

    @classmethod
    def criar(cls, perfil_id: str, handle: str, nome: Optional[str], sem_estruturas: bool = False) -> "PerfilIndexado":
        h = normalizar(handle).lstrip("@")
        n = normalizar(nome or "")
        return cls(
            id=str(perfil_id), handle=handle, nome=nome, handle_norm=h, handle_plano=_sem_separadores(h),
            handle_tokens=tuple(_tokens(h)), nome_norm=n, nome_tokens=tuple(_tokens(n)), sem_estruturas=sem_estruturas,
        )

    def como_candidato(self) -> dict[str, Any]:
        return {"perfil_id": self.id, "handle": self.handle, "nome": self.nome}


@dataclass
class _EntradaCache:
    db: Any
    ts: float
    indice: list[PerfilIndexado]


class CacheIndice:
    """One in-process entry (a profile index per DB client), TTL 60 s. Holding the client keeps ``is`` honest
    (an ``id()`` could be reused by a different client)."""

    def __init__(self, ttl_s: float = INDICE_TTL_S, relogio: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s = ttl_s
        self.relogio = relogio
        self._entrada: Optional[_EntradaCache] = None

    def invalidar(self) -> None:
        self._entrada = None

    def obter(self, db: Any) -> list[PerfilIndexado]:
        e = self._entrada
        agora = self.relogio()
        if e is not None and e.db is db and agora - e.ts < self.ttl_s:
            return e.indice
        indice = carregar_indice(db)
        self._entrada = _EntradaCache(db=db, ts=agora, indice=indice)
        return indice


_CACHE = CacheIndice()


def indice_de_perfis(db: Any) -> list[PerfilIndexado]:
    """The cached library-profile index (handle, nome; ``sem_estruturas`` when no ``ativa`` Estrutura)."""
    return _CACHE.obter(db)


def invalidar_indice() -> None:
    _CACHE.invalidar()


def carregar_indice(db: Any) -> list[PerfilIndexado]:
    perfis = list(iter_paged_rows(
        lambda a, b: db.table(PERFIS).select("id,handle,nome").order("id").range(a, b).execute().data,
        label="cs_perfis_monitorados (profile index)", max_pages=INDICE_MAX_PERFIS // 500 + 1, page_size=500,
    ))
    if len(perfis) > INDICE_MAX_PERFIS:
        logger.warning("estruturas_retrieval: %d perfis no índice (esperado <= ~600); resolução continua completa", len(perfis))
    com_estruturas = {
        str(r["perfil_id"]) for r in iter_paged_rows(
            lambda a, b: db.table(ESTRUTURAS).select("id,perfil_id").eq("status", "ativa").order("id").range(a, b).execute().data,
            label="cs_estruturas (ativa, profile flags)", page_size=1000, max_pages=200,
        ) if r.get("perfil_id")
    }
    return [
        PerfilIndexado.criar(str(p["id"]), p.get("handle") or "", p.get("nome"), str(p["id"]) not in com_estruturas)
        for p in perfis if p.get("handle")
    ]


# ── the resolver ────────────────────────────────────────────────────────────────────────────────────────────

_ARROBA_RE = re.compile(r"(?<![a-z0-9._])@([a-z0-9._]{2,40})")
#: Triggers that introduce a profile name (matched on the normalised text; the span is the <= 4 tokens after).
_GATILHOS_RE = re.compile(
    r"(?:\bno estilo(?: d[oae]s?)?|\bestilo d[oae]s?|\bcomo (?:o|a)|\bparecid[oa] com|\binspirad[oa] (?:n[oa]|em)"
    r"|\bdo perfil|\bperfil d[oae]|\bbaseado em)\b"
)
_ARTIGOS = frozenset({"o", "a", "os", "as", "do", "da", "de", "dos", "das", "no", "na", "um", "uma", "e", "para", "com"})
_DISTINTIVO_MIN = 5
_SUBSTRING_MIN = 4

LIMIAR_RESOLVIDO = 0.8
LIMIAR_AMBIGUO = 0.6
MARGEM = 0.15


@dataclass(frozen=True)
class Resolvido:
    perfil_id: str
    handle: str
    nome: Optional[str]
    via: str  # "mencao" | "handle" | "nome"
    confianca: float
    sem_estruturas: bool = False

    def como_dict(self) -> dict[str, Any]:
        return {"perfil_id": self.perfil_id, "handle": self.handle, "nome": self.nome, "via": self.via,
                "confianca": self.confianca}


@dataclass(frozen=True)
class Ambiguo:
    trecho: str
    candidatos: tuple[PerfilIndexado, ...]

    def como_dict(self) -> dict[str, Any]:
        return {"trecho": self.trecho, "candidatos": [c.como_candidato() for c in self.candidatos]}


@dataclass(frozen=True)
class NaoEncontrado:
    trecho: str
    sugestoes: tuple[PerfilIndexado, ...]

    def como_dict(self) -> dict[str, Any]:
        return {"trecho": self.trecho, "sugestoes": [c.como_candidato() for c in self.sugestoes]}


@dataclass
class ResolucaoPerfis:
    resolvidos: list[Resolvido] = field(default_factory=list)
    ambiguos: list[Ambiguo] = field(default_factory=list)
    nao_encontrados: list[NaoEncontrado] = field(default_factory=list)

    @property
    def vazia(self) -> bool:
        return not (self.resolvidos or self.ambiguos or self.nao_encontrados)

    def como_dict(self) -> dict[str, Any]:
        return {
            "resolvidos": [r.como_dict() for r in self.resolvidos],
            "ambiguos": [a.como_dict() for a in self.ambiguos],
            "nao_encontrados": [n.como_dict() for n in self.nao_encontrados],
        }

    def eventos(self) -> list[dict[str, Any]]:
        """One row per outcome kind with its count (``cs_fluxo_eventos``: ``perfil_resolvido|perfil_ambiguo|
        perfil_nao_encontrado`` + ``contagem``), written by the chat flow."""
        out = [
            {"tipo": tipo, "contagem": n}
            for tipo, n in (("perfil_resolvido", len(self.resolvidos)), ("perfil_ambiguo", len(self.ambiguos)),
                            ("perfil_nao_encontrado", len(self.nao_encontrados)))
            if n
        ]
        return out


def _pontuar(tokens: Sequence[str], p: PerfilIndexado) -> float:
    """Section 8.3 score of one span against one profile."""
    if not tokens:
        return 0.0
    junto = "".join(tokens)
    if len(tokens) == 1 and tokens[0] == p.handle_norm:
        return 1.0
    if " ".join(tokens) == p.nome_norm and p.nome_norm:
        return 0.95
    if p.nome_tokens and all(t in p.nome_tokens for t in tokens):
        return 0.8
    if len(junto) >= _SUBSTRING_MIN and junto in p.handle_plano:
        return 0.8
    for t in tokens:
        if len(t) >= _DISTINTIVO_MIN and (t in p.nome_tokens or t in p.handle_plano or t in p.nome_norm):
            return 0.6
    return 0.0


def _sobreposicao(tokens: Sequence[str], p: PerfilIndexado) -> int:
    alvo = set(p.nome_tokens) | set(p.handle_tokens) | {p.handle_plano}
    return sum(1 for t in tokens if t in alvo or (len(t) >= 3 and t in p.handle_plano))


def _ranquear(tokens: Sequence[str], indice: Sequence[PerfilIndexado]) -> list[tuple[float, PerfilIndexado]]:
    pontos = [(_pontuar(tokens, p), p) for p in indice]
    return sorted((x for x in pontos if x[0] > 0), key=lambda x: (-x[0], x[1].handle))


def _decidir(ranque: Sequence[tuple[float, PerfilIndexado]]) -> str:
    if not ranque:
        return "nao_encontrado"
    topo = ranque[0][0]
    segundo = ranque[1][0] if len(ranque) > 1 else 0.0
    if topo >= LIMIAR_RESOLVIDO and topo - segundo >= MARGEM:
        return "resolvido"
    return "ambiguo" if topo >= LIMIAR_AMBIGUO else "nao_encontrado"


def _trechos_apos_gatilho(norm: str) -> list[list[str]]:
    """For each trigger occurrence, the tokens that follow it up to a clause break (<= 4 kept per prefix attempt)."""
    out: list[list[str]] = []
    for m in _GATILHOS_RE.finditer(norm):
        resto = norm[m.end():].strip().split(" ")
        toks: list[str] = []
        for tok in resto:
            if tok == "|" or not tok or tok.startswith("@"):  # a clause break, or an @handle (its own span)
                break
            toks.append(tok)
            if len(toks) >= _MAX_TOKENS_TRECHO:
                break
        while toks and toks[0] in _ARTIGOS:
            toks.pop(0)
        if toks:
            out.append(toks)
    return out


def _melhor_prefixo(toks: list[str], indice: Sequence[PerfilIndexado]):
    """Of the prefixes of the span, the one whose decision is best: resolved > ambiguous > none, then the higher
    top score, then the longer prefix ("fernando segredo sobre implantes" -> "fernando segredo")."""
    melhor = None
    for n in range(len(toks), 0, -1):
        pref = toks[:n]
        while pref and pref[-1] in _ARTIGOS:
            pref = pref[:-1]
        if not pref:
            continue
        ranque = _ranquear(pref, indice)
        dec = _decidir(ranque)
        chave = ({"resolvido": 2, "ambiguo": 1, "nao_encontrado": 0}[dec], ranque[0][0] if ranque else 0.0, len(pref))
        if melhor is None or chave > melhor[0]:
            melhor = (chave, pref, ranque, dec)
    return melhor


def resolver_perfis_no_texto(
    texto: str, indice: Sequence[PerfilIndexado], *, reportar_arroba_desconhecido: bool = True,
) -> ResolucaoPerfis:
    """Deterministic free-text profile-name resolution (no model call). ``@handle`` and the <= 4 tokens after a
    trigger ("estilo do ...", "como o ...", ...) are candidate spans; a text with neither resolves nothing."""
    res = ResolucaoPerfis()
    norm = normalizar(texto)
    if not norm:
        return res
    vistos: set[str] = set()
    por_handle = {p.handle_norm: p for p in indice}

    def adicionar(p: PerfilIndexado, via: str, conf: float) -> None:
        if p.id not in vistos:
            vistos.add(p.id)
            res.resolvidos.append(Resolvido(p.id, p.handle, p.nome, via, conf, p.sem_estruturas))

    for m in _ARROBA_RE.finditer(norm):
        h = m.group(1).rstrip("._")
        p = por_handle.get(h)
        if p is not None:
            adicionar(p, "mencao", 1.0)
        elif reportar_arroba_desconhecido:
            res.nao_encontrados.append(NaoEncontrado(f"@{h}", _sugestoes([h], indice)))

    for toks in _trechos_apos_gatilho(norm):
        escolhido = _melhor_prefixo(toks, indice)
        if escolhido is None:
            continue
        _, pref, ranque, dec = escolhido
        trecho = " ".join(pref)
        if dec == "resolvido":
            top = ranque[0]
            adicionar(top[1], "handle" if top[0] == 1.0 else "nome", top[0])
        elif dec == "ambiguo":
            res.ambiguos.append(Ambiguo(trecho, tuple(p for _, p in ranque[:MAX_CANDIDATOS])))
        else:
            res.nao_encontrados.append(NaoEncontrado(trecho, _sugestoes(pref, indice)))
    return res


def _sugestoes(tokens: Sequence[str], indice: Sequence[PerfilIndexado]) -> tuple[PerfilIndexado, ...]:
    pontos = sorted(((_sobreposicao(tokens, p), p) for p in indice), key=lambda x: (-x[0], x[1].handle))
    return tuple(p for n, p in pontos[:MAX_SUGESTOES] if n > 0)


# ── the pool ────────────────────────────────────────────────────────────────────────────────────────────────

def _chave_semente(semente: str, valor: str) -> str:
    return hashlib.sha256(f"{semente}|{valor}".encode()).hexdigest()


def selecionar_ids(linhas: Iterable[dict[str, Any]], *, semente: str, limite: int) -> list[str]:
    """Round-robin across profiles (diversity), within a profile by a deterministic seeded shuffle, never by
    recency. The profile rotation order is seeded too, so a re-run is stable and different seeds vary."""
    por_perfil: dict[str, list[str]] = {}
    for r in linhas:
        por_perfil.setdefault(str(r.get("perfil_id") or ""), []).append(str(r["id"]))
    filas = [
        sorted(ids, key=lambda i: _chave_semente(semente, i))
        for _, ids in sorted(por_perfil.items(), key=lambda kv: _chave_semente(semente, "perfil:" + kv[0]))
    ]
    out: list[str] = []
    n = 0
    while len(out) < limite and any(n < len(f) for f in filas):
        for f in filas:
            if n < len(f) and len(out) < limite:
                out.append(f[n])
        n += 1
    return out


@dataclass(frozen=True)
class BlocoPool:
    ordem: int
    tipo: str
    nome: str
    tempo: Optional[str]
    instrucao: Optional[str]
    nota: Optional[str]
    repeticoes: int


@dataclass(frozen=True)
class EstruturaPool:
    id: str
    codigo: str
    perfil_id: Optional[str]
    handle: Optional[str]
    formato: Optional[str]
    objetivos: tuple[str, ...]
    formula: str
    blocos: tuple[BlocoPool, ...]


@dataclass(frozen=True)
class FiltrosPool:
    perfil_ids: Optional[Sequence[str]] = None  # scope (selected profiles, or the explicitly named ones)
    formato: Optional[str] = None
    objetivos: Sequence[str] = ()
    estrutura_ids: Optional[Sequence[str]] = None


def montar_pool(db: Any, filtros: FiltrosPool, *, semente: str, limite: int = MAX_ESTRUTURAS) -> list[EstruturaPool]:
    """The ``ativa`` Estruturas offered to the model (section 8.2): scoped, filtered, round-robin + seeded
    order, capped. ``perfil_ids=None`` = the whole library; an EMPTY sequence = nothing (never "everything")."""
    linhas = _linhas_candidatas(db, filtros)
    ids = selecionar_ids(linhas, semente=semente, limite=limite)
    return carregar_estruturas(db, ids)


def _linhas_candidatas(db: Any, f: FiltrosPool) -> list[dict[str, Any]]:
    def query(filtro):
        def pagina(a: int, b: int):
            q = db.table(ESTRUTURAS).select("id,perfil_id,formato,objetivos").eq("status", "ativa")
            if f.formato:
                q = q.eq("formato", f.formato)
            q = filtro(q)
            return q.order("id").range(a, b).execute().data
        return pagina

    if f.estrutura_ids is not None:
        rows: list[dict[str, Any]] = []
        for lote in batched(sorted({str(i) for i in f.estrutura_ids})):
            rows += list(iter_paged_rows(query(lambda q, lote=lote: q.in_("id", lote)), label="cs_estruturas (ids)", page_size=500))
    elif f.perfil_ids is not None:
        rows = []
        for lote in batched(sorted({str(i) for i in f.perfil_ids})):
            rows += list(iter_paged_rows(query(lambda q, lote=lote: q.in_("perfil_id", lote)), label="cs_estruturas (perfis)", page_size=500))
    else:
        rows = list(iter_paged_rows(query(lambda q: q), label="cs_estruturas (biblioteca)", page_size=1000, max_pages=200))
    if f.estrutura_ids is not None and f.perfil_ids is not None:
        escopo = {str(p) for p in f.perfil_ids}
        rows = [r for r in rows if str(r.get("perfil_id")) in escopo]
    if f.objetivos:
        quer = set(f.objetivos)
        rows = [r for r in rows if quer & set(r.get("objetivos") or [])]
    return rows


def carregar_estruturas(db: Any, ids: Sequence[str]) -> list[EstruturaPool]:
    """Full rows (+ blocks, block types, profile handle) of ``ids``, returned in the ORDER of ``ids``."""
    if not ids:
        return []
    estruturas: dict[str, dict[str, Any]] = {}
    blocos: dict[str, list[dict[str, Any]]] = {}
    for lote in batched(list(ids)):
        for e in db.table(ESTRUTURAS).select("id,codigo,perfil_id,formato,objetivos,formula_headline").in_("id", lote).execute().data or []:
            estruturas[str(e["id"])] = e
        for b in db.table(BLOCOS).select("estrutura_id,ordem,tipo_id,nome,tempo,instrucao,nota,repeticoes").in_("estrutura_id", lote).execute().data or []:
            blocos.setdefault(str(b["estrutura_id"]), []).append(b)
    tipo_ids = sorted({str(b["tipo_id"]) for bs in blocos.values() for b in bs if b.get("tipo_id")})
    tipos: dict[str, dict[str, Any]] = {}
    for lote in batched(tipo_ids):
        for t in db.table(TIPOS).select("id,nome,instrucao_referencia").in_("id", lote).execute().data or []:
            tipos[str(t["id"])] = t
    perfil_ids = sorted({str(e["perfil_id"]) for e in estruturas.values() if e.get("perfil_id")})
    handles: dict[str, str] = {}
    for lote in batched(perfil_ids):
        for p in db.table(PERFIS).select("id,handle").in_("id", lote).execute().data or []:
            handles[str(p["id"])] = p.get("handle") or ""
    out: list[EstruturaPool] = []
    for i in ids:
        e = estruturas.get(str(i))
        if e is None:
            continue
        bs = []
        for b in sorted(blocos.get(str(i), []), key=lambda x: x["ordem"]):
            tipo = tipos.get(str(b.get("tipo_id"))) or {}
            bs.append(BlocoPool(
                ordem=b["ordem"], tipo=tipo.get("nome") or "", nome=b.get("nome") or "", tempo=b.get("tempo"),
                # a block with no instrucao shows its type's reference instruction (section 8.1)
                instrucao=b.get("instrucao") or tipo.get("instrucao_referencia"), nota=b.get("nota"),
                repeticoes=int(b.get("repeticoes") or 1),
            ))
        pid = str(e["perfil_id"]) if e.get("perfil_id") else None
        out.append(EstruturaPool(
            id=str(e["id"]), codigo=str(e["codigo"]), perfil_id=pid, handle=handles.get(pid or ""), formato=e.get("formato"),
            objetivos=tuple(e.get("objetivos") or ()), formula=e.get("formula_headline") or "", blocos=tuple(bs),
        ))
    return out


__all__ = [
    "Ambiguo", "BlocoPool", "CacheIndice", "EstruturaPool", "FiltrosPool", "INDICE_TTL_S", "MAX_ESTRUTURAS",
    "NaoEncontrado", "PerfilIndexado", "ResolucaoPerfis", "Resolvido", "carregar_estruturas", "indice_de_perfis",
    "invalidar_indice", "montar_pool", "normalizar", "resolver_perfis_no_texto", "selecionar_ids",
]
