"""In-memory deterministic `VistaCRMAdapter` for dev + tests.

Distinct from `FakeVistaClient` (the low-level endpoint-shape fake) —
this is the domain-shape fake: seed it with `{code: PropertyData}` and
calls return the seeded PropertyData (or ``None`` when the code isn't
registered).

Use this in product tests / dev when you don't want to drive raw Vista
payloads through the showcase normalizers.

**Both halves of the seam live here.** When `VistaCRMAdapter` grew
`get_imovel` / `list_imoveis` (roadmap P2.0b), this Fake grew them in the
same commit. A Protocol method with only a Real implementation is a
half-shipped seam: it silently forces every consumer of the new method into
integration tests against a live tenant, which is the failure
`KB § PATTERNS/backend/seed-fake-real-adapter.md` exists to prevent.
"""

from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.integrations.vista.client import VistaNotFound, VistaRecordUnpublished
from noctusai_lib.domain.real_estate import (
    Imovel,
    ImovelFoto,
    ImovelPage,
    PropertyData,
    parse_imovel_fotos,
)


#: Vista `filter` key -> `Imovel` attribute, for the keys `search_imoveis` can evaluate in memory.
_FILTER_ATTRS = {
    "Codigo": "codigo", "Status": "status", "Categoria": "categoria", "Bairro": "bairro", "Cidade": "cidade",
    "ValorVenda": "valor_venda", "ValorLocacao": "valor_locacao", "Dormitorios": "dormitorios", "Suites": "suites",
    "Vagas": "vagas", "Empreendimento": "empreendimento", "DataAtualizacao": "data_atualizacao",
}
_COMPARATORS = (">", "<", ">=", "<=", "like", "!=")


def _norm(value: Any) -> Any:
    return value.casefold() if isinstance(value, str) else value


def _num(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _like(text: Any, pattern: Any) -> bool:
    import re

    if text is None:
        return False
    rx = "".join(".*" if ch == "%" else re.escape(ch) for ch in str(pattern))
    return re.fullmatch(rx, str(text), flags=re.IGNORECASE | re.DOTALL) is not None


def _match(actual: Any, wanted: Any) -> bool:
    """One filter clause, Vista's operator grammar: equality, list-IN, `[lo, hi]` range, `[op, value]` comparison."""
    if isinstance(wanted, list):
        if len(wanted) == 2 and wanted[0] in _COMPARATORS:
            op, ref = wanted
            if op == "like":
                return _like(actual, ref)
            if op == "!=":
                return _norm(actual) != _norm(ref)
            if actual is None:
                return False
            a, r = (_num(actual), _num(ref)) if not hasattr(actual, "isoformat") else (actual.isoformat(), str(ref))
            return {">": a > r, "<": a < r, ">=": a >= r, "<=": a <= r}[op]
        if len(wanted) == 2 and all(isinstance(x, (int, float)) for x in wanted):
            return actual is not None and wanted[0] <= _num(actual) <= wanted[1]
        return _norm(actual) in {_norm(x) for x in wanted}
    return _norm(actual) == _norm(wanted)


class FakeVistaAdapter:
    """In-memory ``VistaCRMAdapter`` stand-in.

    Seed at construction (``data={...}`` for `PropertyData`, ``imoveis={...}``
    for `Imovel`) or via ``add_property`` / ``add_imovel``. Getters return the
    seeded value or ``None``; never raise.

    The two stores are independent on purpose — a test exercising only the
    YouTube fan-out seeds `PropertyData` and never thinks about `Imovel`,
    and vice versa.
    """

    def __init__(
        self,
        data: dict[str, PropertyData] | None = None,
        imoveis: dict[str, Imovel] | None = None,
        fotos: dict[str, dict[str, Any]] | None = None,
        corretores: list[dict[str, Any]] | None = None,
        clientes: list[dict[str, Any]] | None = None,
    ) -> None:
        self._data: dict[str, PropertyData] = dict(data or {})
        self._imoveis: dict[str, Imovel] = dict(imoveis or {})
        # Dict-shaped like the real ``Foto`` payload (keyed by photo code),
        # NOT pre-parsed `ImovelFoto`s — so `list_imovel_fotos` exercises
        # `parse_imovel_fotos`'s dict-keyed normalization on the Fake too.
        self._fotos: dict[str, dict[str, Any]] = dict(fotos or {})
        # The broker roster, Vista's own dict shape (`Codigo`, `Nome`, ...), served page by page like `/corretores/listar`.
        self._corretores: list[dict[str, Any]] = [dict(c) for c in (corretores or [])]
        # Vista's client list, Vista's own dict shape (`Codigo`, `Nome`, `Celular`, ...), paged like `/clientes/listar`.
        self._clientes: list[dict[str, Any]] = [dict(c) for c in (clientes or [])]
        self.clientes_fields_asked: list[Optional[list[str]]] = []

    # ── PropertyData surface ──

    def add_property(self, code: str, prop: PropertyData) -> None:
        self._data[code] = prop

    async def get_property(self, code: str) -> PropertyData | None:
        return self._data.get(code)

    # ── Imovel surface ──

    def add_imovel(self, imovel: Imovel) -> None:
        """Register an `Imovel`, keyed by its own `codigo`.

        Takes the model rather than a ``(code, model)`` pair — the code is
        already on it, and accepting both invites them to disagree.
        """
        self._imoveis[imovel.codigo] = imovel

    async def get_imovel(self, code: str) -> Optional[Imovel]:
        return self._imoveis.get(code)

    # ── Corretor roster surface ──

    def add_corretor(self, corretor: dict[str, Any]) -> None:
        """Register one roster row in Vista's own shape (`{"Codigo": "16", "Nome": "...", "Email": ...}`)."""
        self._corretores.append(dict(corretor))

    def clear_corretores(self) -> None:
        self._corretores.clear()

    async def list_corretores(
        self, *, page: int = 1, page_size: int = 50, fields: Optional[list[str]] = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Paginate the seeded roster. `fields` is honoured by projecting the row (a key that ignores it answers every seeded key)."""
        total = len(self._corretores)
        inicio = max(0, (page - 1) * page_size)
        itens = [dict(c) for c in self._corretores[inicio : inicio + page_size]]
        return itens, {"total": total, "paginas": max(1, (total + page_size - 1) // page_size), "pagina": page, "quantidade": page_size}

    # ── Cliente surface ──

    def add_cliente(self, cliente: dict[str, Any]) -> None:
        self._clientes.append(dict(cliente))

    async def list_clientes(
        self, *, page: int = 1, page_size: int = 50, fields: Optional[list[str]] = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Paginate the seeded clients; `fields` projects each row (plus `Codigo`) and is recorded in `clientes_fields_asked`."""
        self.clientes_fields_asked.append(list(fields) if fields is not None else None)
        total = len(self._clientes)
        inicio = max(0, (page - 1) * page_size)
        itens = []
        for c in self._clientes[inicio : inicio + page_size]:
            itens.append(dict(c) if fields is None else {k: v for k, v in c.items() if k in set(fields) | {"Codigo"}})
        return itens, {"total": total, "paginas": max(1, (total + page_size - 1) // page_size), "pagina": page, "quantidade": page_size}

    # ── Foto surface ──

    def add_imovel_fotos(self, codigo: str, fotos_raw: dict[str, Any]) -> None:
        """Seed one imóvel's gallery with a raw, dict-keyed-by-photo-code
        payload — the same wire shape Vista sends, e.g.
        ``{"1": {"Codigo": "1", "Foto": "https://...", "Destaque": "Sim"}}``.
        """
        self._fotos[codigo] = fotos_raw

    async def list_imovel_fotos(self, codigo: str) -> list[ImovelFoto]:
        """Read-only photo gallery for one imóvel; ``[]`` when unseeded."""
        return parse_imovel_fotos(self._fotos.get(codigo, {}))

    def set_destaques(self, codes: list[str]) -> None:
        self._destaques = list(codes)

    async def refresh_imovel(self, code: str) -> Imovel:
        """Detalhes-only read: the seeded imóvel WITHOUT its listar-only fields; `VistaNotFound` when unseeded,
        `VistaRecordUnpublished` when seeded with `exibir_no_site=False` (same split as the Real)."""
        imovel = self._imoveis.get(code)
        if imovel is None:
            raise VistaNotFound(404, f"imovel {code!r} does not exist", "/imoveis/detalhes")
        if imovel.exibir_no_site is False:
            # The stub body keeps the persistent `Corretor` relation (dict keyed by broker code), like the Real.
            relacao = {str(c.codigo or n): {"Codigo": c.codigo, "Nome": c.nome, "Email": c.email, "Fone": c.fone} for n, c in enumerate(imovel.corretores)}
            raise VistaRecordUnpublished(code, "/imoveis/detalhes", ["Corretor"], {"Corretor": relacao})
        return imovel.model_copy(update={"foto_destaque": None, "banheiro_social": None, "codigo_imobiliaria": None})

    async def list_destaques(self) -> list[str]:
        return list(getattr(self, "_destaques", []))

    async def search_imoveis(
        self,
        *,
        filter_: Optional[dict] = None,
        order: Optional[dict] = None,
        max_results: int = 200,
        with_detalhes: bool = False,
    ) -> ImovelPage:
        """Evaluate a Vista `filter` over the seeded imóveis (same operator grammar as the Real).

        Supported keys: `_FILTER_ATTRS` plus `ExibirNoSite` ("Sim" matches anything not explicitly
        unpublished, mirroring the real key's published-only grant). An unsupported key raises
        `ValueError` rather than silently matching everything -- a Fake that ignores a filter would
        let a consumer's wrong filter pass its tests. `with_detalhes` is accepted and ignored.
        """
        items = list(self._imoveis.values())
        for key, wanted in (filter_ or {}).items():
            if key == "ExibirNoSite":
                want_pub = _norm(wanted) == "sim"
                items = [i for i in items if (i.exibir_no_site is not False) == want_pub]
            elif key in _FILTER_ATTRS:
                attr = _FILTER_ATTRS[key]
                items = [i for i in items if _match(getattr(i, attr), wanted)]
            else:
                raise ValueError(f"FakeVistaAdapter.search_imoveis: unsupported filter key {key!r}")
        for key, direction in (order or {}).items():
            attr = _FILTER_ATTRS.get(key)
            if attr is None:
                raise ValueError(f"FakeVistaAdapter.search_imoveis: unsupported order key {key!r}")
            items.sort(key=lambda i, a=attr: (getattr(i, a) is None, getattr(i, a)), reverse=str(direction).lower() == "desc")
        total = len(items)
        return ImovelPage(items=items[:max_results], total=total, page=1, pages=max(1, (total + 49) // 50))

    async def list_imoveis(
        self, *, page: int = 1, page_size: int = 50, with_detalhes: bool = False
    ) -> ImovelPage:
        """Paginate the seeded imóveis in insertion order.

        `with_detalhes` is accepted and ignored: the Fake's imóveis are
        already whole, so there is no second call to make. Honouring the
        signature still matters — a consumer that passes it must not break
        when swapped onto the Fake, which is the point of the seam.
        """
        items = list(self._imoveis.values())
        total = len(items)
        pages = max(1, (total + page_size - 1) // page_size)
        start = max(0, (page - 1) * page_size)
        return ImovelPage(
            items=items[start : start + page_size],
            total=total,
            page=page,
            pages=pages,
        )
