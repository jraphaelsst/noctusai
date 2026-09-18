"""noctus.dev.check_storage_no_public_buckets — the LIVE half of the
zero-public-bucket gate.

THE INCIDENT (2026-09-17). `erp-certidoes` (102 CPF-bearing objects) and
`erp-geral` were `public = true` in the LIVE database — a state no static
scan of migration files can ever fully prove or disprove, because a bucket
can be flipped public by a hand-run `ALTER`/dashboard toggle that never
touches a migration file at all. `noctus.dev.compliance.
check_storage_bucket_public` (the STATIC leg, pre-commit) proves no NEW
commit can introduce a public-bucket declaration; THIS tool proves the
RUNNING database has none, regardless of how it got that way — the same
division of labour `noctus.dev.ensure_schema_exposure` (static AST
derivation) vs. its own live-DB read already establishes for the
PGRST106-exposed-schema class.

THE RULE IS ABSOLUTE, NO EXCEPTION (owner directive, 2026-09-17): a public
bucket serves objects via `/object/public/{bucket}/{path}`, a route that
BYPASSES `storage.objects` RLS ENTIRELY — "RLS is on" is not "the data is
protected" the moment any bucket is public. Unlike this repo's other
live-DB gates (`noctus.dev.ensure_schema_exposure`'s `action='apply'`,
`noctus.dev.deploy_image`'s rollback), **this tool has NO `apply` /
`confirm=True` write path and NO parameter that suppresses a finding.**
It is READ-ONLY by construction — the fix (flip the bucket private) is a
single `ALTER`/dashboard toggle the operator runs directly, never
automated here, because a tool that can flip `public=false` could, by the
same code path, be asked to flip it back — and the whole point of this
gate is that there is no code path back.

FAIL-CLOSED POSTURE (mirrors `ensure_schema_exposure`'s `not_configured` /
`unavailable` handling, EXCEPT this gate blocks predeploy on ALL of them —
`schema_exposure`'s leg in `predeploy_check.py` already sets this
precedent: "we couldn't check" must never read as "it's fine"). Every
non-`clean` status is a FAILURE for `predeploy_check`'s `storage_bucket_
public` leg: `not_configured` (no credentials), `unavailable` (query
failed), and `violation` (a public bucket exists) all BLOCK. A bucket this
tool cannot inspect is a failure, not a skip.

Requires a Supabase Personal Access Token, resolved the SAME DB-first way
`noctus.dev.migrate_product` / `noctus.dev.ensure_schema_exposure` resolve
it (reuses `make_sql_executor`).

KB § PATTERNS/backend/database-rls.md § Storage buckets — never public.
"""
from __future__ import annotations

from typing import Any

from . import migrate_product as _mp

_PUBLIC_BUCKETS_SQL = "SELECT id, name, public FROM storage.buckets WHERE public = true;"

_SANCTIONED_ALTERNATIVE = (
    "A public Supabase Storage bucket bypasses storage.objects RLS entirely "
    "(the /object/public/{bucket}/{path} route serves objects without "
    "evaluating any policy). There is NO override for this gate. Flip the "
    "bucket private (UPDATE storage.buckets SET public = false WHERE id = "
    "'<bucket>';) and serve access exclusively via short-TTL signed URLs "
    "minted at read time — StorageService.get_signed_url / "
    "noctusai_lib.integrations.storage. See "
    "KB § PATTERNS/backend/database-rls.md § Storage buckets — never public."
)


def check_storage_no_public_buckets(
    *,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    executor: _mp.SqlExecutor | None = None,
) -> dict[str, Any]:
    """Query the LIVE `storage.buckets` table; FAIL on any `public = true`
    row, FAIL (never skip) when it cannot be verified at all.

    Platform-wide by design (no `product`/`products` filter) — a bucket
    belongs to the whole Supabase project, not to one product's schema, and
    the rule is "zero public buckets, in every product, forever", not
    "zero public buckets in the product currently being deployed".

    Returns a dict with keys: ``status`` ('clean' | 'violation' |
    'not_configured' | 'error'), ``public_buckets`` (list of
    ``{id, name}``), ``error``.
    """

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ok": status == "clean",
            "status": status,
            "public_buckets": [],
            "error": None,
        }
        base.update(overrides)
        return base

    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)
    if executor is None:
        # NOC-REMEDIATE[credentials]: no supabase_access_token resolved.
        # Same resolution path as noctus.dev.migrate_product /
        # noctus.dev.ensure_schema_exposure — see either for the tiers
        # tried. This is a FAILURE for predeploy_check, not a skip.
        return _result(
            "not_configured",
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Store it DB-first in platform_settings (key='supabase_access_token', "
                "global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env. "
                + _SANCTIONED_ALTERNATIVE
            ),
        )

    fetch = executor.execute(_PUBLIC_BUCKETS_SQL)
    if not fetch.get("ok"):
        return _result(
            "error",
            error=(
                "could not read storage.buckets: "
                + (fetch.get("error") or "unknown error")
                + " " + _SANCTIONED_ALTERNATIVE
            ),
        )

    public_buckets = [
        {"id": row.get("id"), "name": row.get("name")}
        for row in (fetch.get("rows") or [])
        if isinstance(row, dict)
    ]
    if public_buckets:
        return _result(
            "violation",
            public_buckets=public_buckets,
            error=(
                f"public bucket(s) found LIVE: {public_buckets}. "
                + _SANCTIONED_ALTERNATIVE
            ),
        )
    return _result("clean")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.check_storage_no_public_buckets",
        description=(
            "LIVE half of the zero-public-bucket gate (read-only, NO apply/"
            "confirm write path, NO override of any kind — owner directive "
            "2026-09-17). Queries the running storage.buckets table and FAILS "
            "on any public=true row, and FAILS (never skips) when it cannot "
            "verify at all — 'we couldn't check' must never read as 'it's "
            "fine'. Platform-wide (no product filter): a bucket belongs to "
            "the whole Supabase project. Wired into noctus.dev.predeploy_check "
            "as the storage_bucket_public leg. The sanctioned fix — flip the "
            "bucket private + serve access via short-TTL signed URLs — is "
            "named in every failure message; this tool never performs the "
            "flip itself. Returns {status, public_buckets, error}. "
            "KB § PATTERNS/backend/database-rls.md § Storage buckets — never public."
        ),
    )
    def _check_storage_no_public_buckets(
        project_ref: str = "nyplttplcoyiiqjrvtiw",
    ) -> dict:
        return check_storage_no_public_buckets(project_ref=project_ref)


__all__ = [
    "check_storage_no_public_buckets",
    "register",
]
