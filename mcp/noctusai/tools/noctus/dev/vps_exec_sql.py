"""noctus.vps.exec_sql — execute a SQL script inside a containerized DB on the VPS.

The cache-pg bringup (2026-05-26 evening, project `cache-pg-vps-bringup`)
surfaced a usability gap: piping SQL via `ssh vps "docker exec container psql
<<EOF ... EOF"` silently fails — the heredoc stream gets munged through one
of the SSH / docker-exec layers (zero stdout, schema not created, no error).
The working idiom is:

    (1) ssh vps "cat > /tmp/x.sql <<EOF ... EOF"
    (2) ssh vps "docker cp /tmp/x.sql <container>:/tmp/x.sql"
    (3) ssh vps "docker exec <container> psql -U <user> -d <db> -f /tmp/x.sql"
    (4) ssh vps "rm /tmp/x.sql && docker exec <container> rm /tmp/x.sql"

This module wraps the idiom so future VPS schema operations don't trial-
and-error past the broken heredoc path again.

**Why this is a separate module from `vps.py`.** `vps.py` bans `docker exec`
in its emitted-command guardrails (per-module `_BANNED_TOKENS` test); the
ban exists to prevent arbitrary-exec abuse via the operate-layer tools.
`exec_sql` is a fixed, narrow command (`psql -f <path>` against a
specific container+db) — the legitimate carve-out. Living in its own
module keeps `vps.py`'s ban tight + tests deterministic, and gives this
tool its own surface-tested contract.

Methodology: KB § PATTERNS/common/dispatch-with-project-and-notes.md §Tooling.
"""
from __future__ import annotations

import shlex
import uuid
from typing import Any, Callable

from ._vps_ssh import run_remote as _throttled_ssh


DEFAULT_HOST = "noctus-vps"
TMP_DIR = "/tmp"


def _run_remote_default(ssh_host: str, cmd: str) -> tuple[int, str, str]:
    """Default SSH runner. Returns (returncode, stdout, stderr). Routed through
    the shared throttled + circuit-broken chokepoint (`_vps_ssh`) so the 4-step
    exec-sql idiom can't burst-connect into a fail2ban ban during an edge blip."""
    return _throttled_ssh(ssh_host, cmd)


def exec_sql(
    sql: str,
    container: str,
    db: str,
    user: str | None = None,
    host: str = DEFAULT_HOST,
    cleanup: bool = True,
    ssh_runner: Callable[[str, str], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Execute a SQL script inside a containerized DB on a remote VPS.

    Steps (idempotent + cleanup-on-failure):
      1. Write SQL to ``/tmp/noctus-exec-sql-<uuid>.sql`` on the VPS host.
      2. ``docker cp`` it into the container at the same path.
      3. ``docker exec <container> psql -U <user> -d <db> -f <path>``.
      4. Cleanup the tmp file on host AND inside the container.

    Args:
      sql: The SQL script content. Non-empty.
      container: Docker container name (e.g. ``noctus-cache-pg``).
      db: Postgres database name.
      user: Postgres user. Defaults to ``db`` value (PG convention when the
        DB name matches the user name — true for noctus-cache-pg).
      host: SSH host alias from ``~/.ssh/config``. Defaults to ``noctus-vps``.
      cleanup: When False, the tmp file remains on host + in container
        (debugging only). Default True.
      ssh_runner: Injection seam for tests. Signature
        ``(ssh_host, cmd) -> (returncode, stdout, stderr)``. Defaults to
        the real subprocess.run-based runner.

    Returns:
      ``{ok, returncode, stdout, stderr, container, db, tmp_path, cleanup_ok}``.

      - ``ok`` is True only when the psql step succeeded (returncode == 0).
      - ``cleanup_ok`` reports whether the cleanup step ran cleanly; a
        failed cleanup does NOT flip ``ok`` to False (the SQL already ran).
      - On validation failure (empty inputs), returns
        ``{ok: False, error: ..., returncode: -1}`` without touching SSH.

    Examples:
      >>> exec_sql("CREATE SCHEMA IF NOT EXISTS noctus_cache;",
      ...          container="noctus-cache-pg", db="noctus_cache")
      {"ok": True, "returncode": 0, ...}

      >>> exec_sql("", container="x", db="y")
      {"ok": False, "error": "sql cannot be empty", "returncode": -1}
    """
    # ── Validation ───────────────────────────────────────────────────
    if not sql or not sql.strip():
        return {"ok": False, "error": "sql cannot be empty", "returncode": -1}
    if not container or not container.strip():
        return {"ok": False, "error": "container cannot be empty", "returncode": -1}
    if not db or not db.strip():
        return {"ok": False, "error": "db cannot be empty", "returncode": -1}

    effective_user = user or db
    run = ssh_runner or _run_remote_default
    tmp_name = f"noctus-exec-sql-{uuid.uuid4().hex[:12]}.sql"
    tmp_path = f"{TMP_DIR}/{tmp_name}"

    # ── 1. Write SQL to /tmp on VPS host via SSH heredoc ─────────────
    # We pass the SQL as a here-doc; uses a distinctive marker
    # (NOCTUS_EXEC_SQL_EOF_<uuid>) so a marker collision with the SQL body
    # is virtually impossible. The single-quote on the marker line
    # disables shell variable expansion inside the heredoc body.
    eof_marker = f"NOCTUS_EXEC_SQL_EOF_{uuid.uuid4().hex[:8]}"
    write_cmd = (
        f"cat > {shlex.quote(tmp_path)} <<'{eof_marker}'\n"
        f"{sql}\n"
        f"{eof_marker}"
    )
    rc, out, err = run(host, write_cmd)
    if rc != 0:
        return {
            "ok": False,
            "returncode": rc,
            "stdout": out,
            "stderr": err,
            "container": container,
            "db": db,
            "tmp_path": tmp_path,
            "step": "write-tmp-file",
            "error": f"failed to write SQL to {tmp_path} on {host}: {err.strip() or '<no stderr>'}",
        }

    cleanup_ok = True
    cleanup_err = ""
    try:
        # ── 2. docker cp tmp_path container:tmp_path ─────────────────
        cp_cmd = f"docker cp {shlex.quote(tmp_path)} {shlex.quote(container)}:{shlex.quote(tmp_path)}"
        rc, out, err = run(host, cp_cmd)
        if rc != 0:
            return {
                "ok": False,
                "returncode": rc,
                "stdout": out,
                "stderr": err,
                "container": container,
                "db": db,
                "tmp_path": tmp_path,
                "step": "docker-cp",
                "error": f"docker cp failed: {err.strip() or '<no stderr>'}",
            }

        # ── 3. docker exec container psql -f tmp_path ────────────────
        psql_cmd = (
            f"docker exec {shlex.quote(container)} "
            f"psql -U {shlex.quote(effective_user)} -d {shlex.quote(db)} "
            f"-f {shlex.quote(tmp_path)}"
        )
        rc, out, err = run(host, psql_cmd)
        psql_returncode = rc
        psql_stdout = out
        psql_stderr = err
    finally:
        # ── 4. Cleanup (host + container) — runs even on failure ─────
        if cleanup:
            cleanup_cmd = (
                f"rm -f {shlex.quote(tmp_path)} && "
                f"docker exec {shlex.quote(container)} rm -f {shlex.quote(tmp_path)} 2>/dev/null || true"
            )
            crc, _cout, cerr = run(host, cleanup_cmd)
            if crc != 0:
                cleanup_ok = False
                cleanup_err = cerr.strip()

    return {
        "ok": psql_returncode == 0,
        "returncode": psql_returncode,
        "stdout": psql_stdout,
        "stderr": psql_stderr,
        "container": container,
        "db": db,
        "user": effective_user,
        "tmp_path": tmp_path,
        "step": "psql-exec",
        "cleanup_ok": cleanup_ok,
        "cleanup_err": cleanup_err,
    }


def register(server) -> None:
    """Register the noctus.vps.exec_sql MCP tool."""

    @server.tool(
        name="noctus.vps.exec_sql",
        description=(
            "Execute a SQL script inside a containerized DB on the VPS. "
            "Wraps the 4-step idiom (write tmp on host · docker cp into "
            "container · docker exec psql -f · cleanup) that avoids the "
            "silent-fail `ssh vps \"docker exec ... psql <<EOF\"` heredoc "
            "path discovered during cache-pg bringup. Required args: sql, "
            "container, db. Optional: user (defaults to db), host (defaults "
            "to noctus-vps), cleanup (default True). Returns "
            "{ok, returncode, stdout, stderr, step, cleanup_ok}. "
            "KB § PATTERNS/devops/containerization-operations.md."
        ),
    )
    def _exec_sql(
        sql: str,
        container: str,
        db: str,
        user: str | None = None,
        host: str = DEFAULT_HOST,
        cleanup: bool = True,
    ) -> dict[str, Any]:
        return exec_sql(
            sql=sql,
            container=container,
            db=db,
            user=user,
            host=host,
            cleanup=cleanup,
        )
