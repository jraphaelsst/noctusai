"""A throwaway REAL Postgres server for tests that need TWO connections (concurrency proofs).

PGlite (`noctusai_lib.testing.pglite`) is one connection, so it cannot show what happens while another
transaction is still open -- snapshot visibility, `FOR UPDATE SKIP LOCKED`, a late-committing writer. This
helper gives a test a disposable cluster instead:

    from noctusai_lib.testing.pgserver import disposable_postgres

    with disposable_postgres() as dsn:            # None -> no server could be provided (skip, visibly)
        a = psycopg2.connect(dsn); b = psycopg2.connect(dsn)

Resolution order (first that works):

1. ``NOCTUS_TEST_PG_DSN`` -- an existing server the caller owns (it is used as-is; the test must create its
   own schema). NEVER point this at a shared or production database.
2. Postgres binaries (``initdb`` + ``pg_ctl``): ``NOCTUS_TEST_PG_BIN``, then ``PATH``, then the usual
   install dirs (``/usr/lib/postgresql/*/bin`` -- present on GitHub's ubuntu runners --, Homebrew, Postgres.app).
   A fresh cluster is created in a temp dir, listening on a unix socket only (no TCP), and removed on exit.

Nothing resolvable -> yields ``None``; the caller skips with a reason. A skip is not a pass -- so under
``NOC_REQUIRE_REAL_PG=1`` (set in CI) nothing resolvable RAISES `RealPgUnavailable` instead.
"""
from __future__ import annotations

import contextlib
import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from .pglite import REQUIRE_REAL_PG_ENV, RealPgUnavailable, real_pg_required

__all__ = ["disposable_postgres", "find_pg_bin", "SUPABASE_ROLE_STUBS"]

#: The Supabase API roles + the org helper the seed organs reference -- the minimum a rendered seed
#: migration needs on a vanilla Postgres (the full `migration_replay` stubs also install pgvector, which a
#: stock server may not have).
SUPABASE_ROLE_STUBS = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
END $$;
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

_CANDIDATE_DIRS = (
    "/usr/lib/postgresql/*/bin",
    "/opt/homebrew/opt/postgresql@*/bin",
    "/usr/local/opt/postgresql@*/bin",
    "/Applications/Postgres.app/Contents/Versions/*/bin",
)


def find_pg_bin() -> Optional[Path]:
    """The directory holding ``initdb`` and ``pg_ctl`` (newest version first), or None."""
    explicit = os.environ.get("NOCTUS_TEST_PG_BIN")
    if explicit:
        d = Path(explicit)
        return d if (d / "initdb").exists() and (d / "pg_ctl").exists() else None
    on_path = shutil.which("initdb")
    if on_path and shutil.which("pg_ctl"):
        return Path(on_path).parent
    found: list[Path] = []
    for pattern in _CANDIDATE_DIRS:
        found += [Path(p) for p in glob.glob(pattern) if (Path(p) / "initdb").exists() and (Path(p) / "pg_ctl").exists()]

    def version(p: Path) -> tuple:
        digits = "".join(c if c.isdigit() else " " for c in str(p)).split()
        return tuple(int(x) for x in digits) or (0,)

    return sorted(found, key=version, reverse=True)[0] if found else None


@contextlib.contextmanager
def disposable_postgres() -> Iterator[Optional[str]]:
    dsn = os.environ.get("NOCTUS_TEST_PG_DSN")
    if dsn:
        yield dsn
        return
    bin_dir = find_pg_bin()
    if bin_dir is None:
        if real_pg_required():
            raise RealPgUnavailable(
                f"no Postgres server: NOCTUS_TEST_PG_DSN unset and no initdb/pg_ctl (NOCTUS_TEST_PG_BIN, PATH, "
                f"{', '.join(_CANDIDATE_DIRS)}) while {REQUIRE_REAL_PG_ENV}=1")
        yield None
        return
    # A short path: the unix socket path must fit in ~100 bytes.
    root = Path(tempfile.mkdtemp(prefix="noc-pg-"))
    data, sock = root / "data", root / "s"
    sock.mkdir()
    user = "noc_test"
    try:
        subprocess.run([str(bin_dir / "initdb"), "-D", str(data), "-U", user, "-A", "trust", "--no-sync", "-E", "UTF8"],
                       check=True, capture_output=True, text=True, timeout=120)
        opts = f"-c listen_addresses='' -c unix_socket_directories='{sock}' -c fsync=off -c max_connections=20"
        subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(data), "-o", opts, "-l", str(root / "log"), "-w", "-t", "60", "start"],
                       check=True, capture_output=True, text=True, timeout=120)
        try:
            yield f"host={sock} dbname=postgres user={user}"
        finally:
            subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"],
                           capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(root, ignore_errors=True)
