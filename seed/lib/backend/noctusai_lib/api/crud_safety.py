"""CRUD safety helpers — DELETE-with-existence-check + 404 convenience wrapper.

**Why this exists.** A common anti-pattern in Supabase-backed services is to
treat `.delete().execute()` as a 404 detector:

```python
# ANTI-PATTERN — `result.data` from .delete() is NOT a reliable 404 signal
result = db.table("X").delete().eq("id", x_id).execute()
if not result.data:
    raise NotFound("X")
```

The shape is unreliable in two ways:

1. **RLS-collapsed rows look identical to absent rows.** When RLS hides a row
   from the caller, `.delete()` matches nothing and returns `data=[]` — the
   service incorrectly reports 404 instead of 403, leaking information about
   row existence across tenants.
2. **Some PostgREST drivers return the deleted row, some don't.** Relying on
   `result.data` couples the service to driver behavior that's allowed to
   change.

**The fix shape (canonical across PF after `personal-finance-wiring` Phase 2):**

```python
check = db.table("X").select("id").eq("id", x_id).eq("org_id", self.org_id).execute()
if not check.data:
    raise HTTPException(status_code=404, detail="X nao encontrado")
db.table("X").delete().eq("id", x_id).eq("org_id", self.org_id).execute()
```

This helper formalizes that pattern at N=3 cross-product recurrence
(`personal-finance` recorrentes + `erp-imobiliario` meta_periodos + regras_pontuacao).

**Raise-shape injection.** ERP services raise `LookupError`; PF routers raise
`HTTPException(404)`. The helper accepts a caller-provided exception factory so
both conventions consume the same helper without forking the seed module.

**Variadic predicates.** Some tables scope by `(id, org_id)`; others (e.g.
`orcamento_itens` where RLS-via-parent removes the need for explicit org scope)
take only `(id,)`. The helper accepts `*predicates` chained as `.eq(col, val)`.

See `KB § PATTERNS/backend.md § DELETE-with-existence-check helper` for usage.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException


def delete_with_existence_check(
    db,
    table: str,
    *predicates: tuple[str, Any],
    not_found_exc: Callable[[], Exception],
) -> None:
    """Pre-check existence via SELECT; raise if absent; DELETE on success.

    Replaces the `.delete().execute()` + `if not result.data: raise` shape that's
    an unreliable 404 detector when RLS collapses the row to invisible.

    Args:
        db: Supabase client (or any object exposing `.table(name)` with the
            standard `.select`/`.delete`/`.eq`/`.execute` chain).
        table: Table name.
        *predicates: Tuples of `(column, value)` chained as `.eq(col, val)` on
            BOTH the existence-check SELECT and the DELETE. Use the same
            scoping predicates on both so that RLS-aware filters match.
        not_found_exc: Caller-provided zero-arg callable returning the
            exception instance to raise when the row is absent. The helper
            does NOT hardcode `HTTPException(404)` so ERP-style
            `LookupError("X nao encontrado")` is a valid raise shape.

    Returns:
        None. Side effect: the matching row is deleted.

    Raises:
        Whatever `not_found_exc()` returns when the existence check fails.

    Note:
        The existence-check SELECT uses the FIRST predicate column as the
        projection column (e.g. `select("id")` when the first predicate is
        `("id", x)`; `select("key")` for `platform_settings` keyed on `key`).
        This avoids hardcoding `"id"` for tables whose primary key is named
        differently. The column is guaranteed to exist because the caller is
        already filtering by it.
    """
    if not predicates:
        raise ValueError("delete_with_existence_check requires at least one predicate")
    projection_col = predicates[0][0]
    check = db.table(table).select(projection_col)
    for col, val in predicates:
        check = check.eq(col, val)
    if not check.execute().data:
        raise not_found_exc()
    builder = db.table(table).delete()
    for col, val in predicates:
        builder = builder.eq(col, val)
    builder.execute()


def delete_or_404(
    db,
    table: str,
    *predicates: tuple[str, Any],
    message: str = "Not found",
) -> None:
    """HTTPException-flavored convenience wrapper around `delete_with_existence_check`.

    Equivalent to:

    ```python
    delete_with_existence_check(
        db, table, *predicates,
        not_found_exc=lambda: HTTPException(status_code=404, detail=message),
    )
    ```

    Args:
        db: Supabase client.
        table: Table name.
        *predicates: Tuples of `(column, value)` chained as `.eq(col, val)`.
        message: HTTPException `detail` string raised on absence (default
            `"Not found"`).

    Raises:
        fastapi.HTTPException with status 404 when the row is absent.
    """
    delete_with_existence_check(
        db,
        table,
        *predicates,
        not_found_exc=lambda: HTTPException(status_code=404, detail=message),
    )


__all__ = [
    "delete_with_existence_check",
    "delete_or_404",
]
