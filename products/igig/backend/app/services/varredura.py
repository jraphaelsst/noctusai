"""Cross-org sweep discovery — the ONE helper every daily/periodic job composes.

`Repositorios`/`RecordStore` require an `org_id` on every call by
construction (the SQLite dev adapter cannot even express a cross-org
query) — deliberately, so a product router can never forget tenant scoping.
A sweep that runs ACROSS every org therefore cannot use them for its
discovery step and reads the raw service-role client directly instead, then
hands off to `Repositorios`-scoped writes per row/org from there.

Before this module existed that discovery step was written out independently
three times over — `automacoes.varrer_sla`, `financeiro_service.
atualizar_inadimplencia`, `notificacoes.processar_lembretes_pendentes` — and
a fourth shape (`publicacao_publisher.orgs_com_publicacao_pendente`) had
already converged on `iter_paged_rows` by hand. All FOUR are migrated onto
:func:`linhas_cross_org` here.

The convergence is not just DRY: three of the four ORIGINAL call sites ran
their discovery query as a bare ``.select().execute()`` — no pagination —
which is exactly the silent-truncation hazard
``noctusai_lib.integrations.persistence.paging`` exists to close (PostgREST's
default 1000-row cap, no error, no signal). An agency whose open `fatura`
count, active `automacao` rule count, or pending lembrete count crossed 1000
would have silently dropped rows with no test able to see it — the same
class of bug that hit ``negociações`` in commit ``98377d26``. Routing every
cross-org discovery through this one paged helper closes that for good: a
new sweep gets pagination for free instead of having to remember it.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from noctusai_lib.integrations.persistence import Record
from noctusai_lib.integrations.persistence.paging import DEFAULT_PAGE_SIZE, iter_paged_rows

__all__ = ["linhas_cross_org", "orgs_distintos"]


def linhas_cross_org(
    db: Any,
    tabela: str,
    *,
    select: str = "*",
    filtros: Callable[[Any], Any] = lambda query: query,
    id_key: str = "id",
    label: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[Record]:
    """Every row of `tabela`, across ALL orgs, paged.

    `db` is the igig service-role client (`portas.db` / `admin_db` —
    whichever the caller's job already resolves). `filtros` composes
    additional predicates onto the query BEFORE ordering, e.g.
    ``lambda q: q.eq("ativo", True)`` — the same `.eq`/`.lte`/`.is_` chain
    every original call site built inline. The `select` MUST include
    `id_key` (default `"id"`) even when the caller does not otherwise need
    it: `iter_paged_rows`'s progress guard dedupes on that column and
    raises rather than silently degrading if it is missing from a row.

    Returns a materialised `list` (every original call site consumed its
    result as one) rather than the lazy iterator `iter_paged_rows` yields —
    a sweep's row count is bounded by "how much one org/rule/lembrete can
    accumulate", not by platform scale, so eager collection costs nothing
    a periodic job would notice.
    """
    def _pagina(inicio: int, fim: int) -> Any:
        query = filtros(db.table(tabela).select(select))
        return query.order(id_key).range(inicio, fim).execute().data

    return list(iter_paged_rows(
        _pagina, id_key=id_key, page_size=page_size, label=label or f"igig.{tabela} (cross-org)"
    ))


def orgs_distintos(linhas: Iterable[Record]) -> list[str]:
    """Distinct, sorted `org_id`s out of a set of cross-org rows.

    The per-org fan-out list a sweep hands to its per-org worker once
    discovery is done — mirrors the shape
    `publicacao_publisher.processar_fila_publicacao`'s caller already used.
    """
    return sorted({str(linha["org_id"]) for linha in linhas})
