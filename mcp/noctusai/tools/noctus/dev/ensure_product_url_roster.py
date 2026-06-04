"""noctus.dev.ensure_product_url_roster — closed, registry-derived PRODUCT_URL roster.

WHY THIS TOOL EXISTS
--------------------
core's CORS allowlist is built by ``derive_cors_origins`` (source b: explicit
``PRODUCT_URL_<SLUG>`` env vars).  In the slim prod container there is no
``start.sh``, so ``PRODUCT_URL_PATTERN`` is silently ignored for CORS — only
explicit per-product vars count.  Every time a new product joins the registry
it is CORS-invisible until someone hand-adds ``PRODUCT_URL_<SLUG>`` to the VPS
``.env`` and recreates the core container.  That manual step broke orbity's SSO
("Failed to fetch").

An open ``*.noctusai.com`` regex was REJECTED by security review (the SSO
endpoint returns session tokens; an open subdomain-regex exposes them to
subdomain-takeover).

This tool keeps a **closed, registry-derived** set: it derives the full
``PRODUCT_URL_<SLUG>`` roster from the canonical ``start.sh`` registry,
renders a sentinel-bounded **managed block** in the VPS ``.env``, and writes it
safely over SSH (temp-file-then-move, never a partial write).

SLUG ≠ SUBDOMAIN (critical subtlety)
--------------------------------------
Some products have *short-name* overrides:
  - ``erp-imobiliario`` → ``https://erp.noctusai.com``
  - ``social-wiring``   → ``https://social.noctusai.com``
  - ``core``            → ``https://noctusai.com``

These are declared as explicit ``PRODUCT_URL_*`` overrides in the VPS ``.env``.
The tool **preserves** every existing override and only **pattern-fills** the
gaps.  Products following the ``{slug}.noctusai.com`` convention (orbity, most
future products) auto-get their origin with zero manual config.

MANAGED BLOCK
-------------
The tool manages a sentinel-bounded section inside the VPS ``.env``::

    # BEGIN_PRODUCT_URL_ROSTER (managed by noctus.dev.ensure_product_url_roster)
    PRODUCT_URL_PATTERN=https://{slug}.noctusai.com
    PRODUCT_URL_CORE=https://noctusai.com
    PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com
    ...
    # END_PRODUCT_URL_ROSTER

On the first run, any bare ``PRODUCT_URL_*`` lines outside the block are
ABSORBED into it (deduplication: no bare lines remain after absorption).
Subsequent runs are idempotent.

IO SEAM (Protocol + Fake + Real)
---------------------------------
``SshTransport`` Protocol (read / write / recreate_core); ``FakeSshTransport``
for unit tests; ``SubprocessSshTransport`` as the Real over ``subprocess.run``.
The pure transform ``compute_roster_block`` is tested WITHOUT SSH.

RETURN SHAPE
------------
``{
    ok: bool,
    status: 'dry_run' | 'applied' | 'up_to_date' | 'error',
    added:     list[str],   # slugs newly added to the managed block
    preserved: list[str],   # slugs whose override was kept as-is
    unresolved:list[str],   # slugs with no override AND no pattern (warning)
    rendered_block: str,    # the sentinel block text (for dry-run preview)
    error: str | None,
}``

KB § PATTERNS/frontend/core-url-routing.md § 6 (new-product CORS step)
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess
import uuid
from typing import Any, Callable, Protocol, runtime_checkable

from settings import REPO_ROOT

from noctusai_lib.config.cors_registry import parse_products_registry

logger = logging.getLogger(__name__)

# ── Managed-block sentinels ───────────────────────────────────────────────────

_BLOCK_BEGIN = "# BEGIN_PRODUCT_URL_ROSTER (managed by noctus.dev.ensure_product_url_roster)"
_BLOCK_END = "# END_PRODUCT_URL_ROSTER"

# Env-var prefix + pattern key
_URL_PREFIX = "PRODUCT_URL_"
_PATTERN_KEY = "PRODUCT_URL_PATTERN"

# Matches a bare PRODUCT_URL_* line (key=value, with or without export/quotes).
_BARE_URL_RE = re.compile(
    r"^(?:export\s+)?(PRODUCT_URL_\w+)\s*=\s*(.*)$"
)

# Default VPS values
_DEFAULT_SSH_HOST = "noctus-vps"
_DEFAULT_ENV_PATH = "/opt/noctus/noctusai/.env"
_DOCKER_COMPOSE_FILE = "deploy/fleet/docker-compose.prod.yml"


# ── Helper ────────────────────────────────────────────────────────────────────


def _slug_to_env_key(slug: str) -> str:
    """``erp-imobiliario`` → ``PRODUCT_URL_ERP_IMOBILIARIO``."""
    return f"{_URL_PREFIX}{slug.replace('-', '_').upper()}"


def _pattern_fill(slug: str, pattern: str) -> str:
    """Apply PRODUCT_URL_PATTERN substitution for a given slug."""
    return (
        pattern
        .replace("{slug}", slug)
        .replace("{slug_underscored}", slug.replace("-", "_"))
        .rstrip("/")
    )


# ── Pure transform (testable without SSH) ────────────────────────────────────


def compute_roster_block(
    env_text: str,
    registry_slugs: list[str],
    pattern: str | None,
) -> tuple[str, dict[str, Any]]:
    """Compute the new .env text with the managed PRODUCT_URL block.

    Pure function (no I/O).  Called by the live tool and the unit tests.

    Args:
        env_text:        The current content of the VPS .env file.
        registry_slugs:  All product slugs from start.sh (in registry order).
        pattern:         The value of PRODUCT_URL_PATTERN (may be None).

    Returns:
        ``(new_env_text, report)`` where report contains::

            added:      slugs whose origin was pattern-filled (new)
            preserved:  slugs whose existing override was kept verbatim
            unresolved: slugs with no override AND no pattern (warning only)
            rendered_block: the sentinel block text (for preview)
    """
    lines = env_text.splitlines(keepends=True)

    # ── 1. Parse the existing managed block (if any) ──────────────────────────
    block_start_idx: int | None = None
    block_end_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == _BLOCK_BEGIN:
            block_start_idx = i
        elif line.strip() == _BLOCK_END:
            block_end_idx = i

    # ── 2. Collect ALL existing PRODUCT_URL_* values (inside block + bare) ────
    # Precedence: block > bare lines outside block.
    existing_overrides: dict[str, str] = {}  # KEY → value

    # First pass: bare lines OUTSIDE the current block (absorption candidates).
    in_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == _BLOCK_BEGIN:
            in_block = True
            continue
        if stripped == _BLOCK_END:
            in_block = False
            continue
        if not in_block:
            m = _BARE_URL_RE.match(stripped)
            if m:
                key, val = m.group(1), m.group(2).strip().strip("\"'")
                existing_overrides[key] = val

    # Second pass: lines INSIDE the existing block (overwrite bare values if
    # the block holds a newer/explicit entry — block is authoritative on re-run).
    if block_start_idx is not None and block_end_idx is not None:
        for i in range(block_start_idx + 1, block_end_idx):
            stripped = lines[i].strip()
            m = _BARE_URL_RE.match(stripped)
            if m:
                key, val = m.group(1), m.group(2).strip().strip("\"'")
                existing_overrides[key] = val

    # Extract pattern from the existing overrides (may be present inside the
    # block or as a bare line).
    effective_pattern = existing_overrides.pop(_PATTERN_KEY, None) or pattern

    # ── 3. Compute the desired roster ─────────────────────────────────────────
    added: list[str] = []
    preserved: list[str] = []
    unresolved: list[str] = []

    roster_lines: list[str] = []

    # Emit PRODUCT_URL_PATTERN first (if present).
    if effective_pattern:
        roster_lines.append(f"{_PATTERN_KEY}={effective_pattern}")
    elif pattern:
        roster_lines.append(f"{_PATTERN_KEY}={pattern}")

    for slug in registry_slugs:
        key = _slug_to_env_key(slug)
        if key in existing_overrides:
            # Preserve the existing override verbatim.
            roster_lines.append(f"{key}={existing_overrides[key]}")
            preserved.append(slug)
        elif effective_pattern:
            # Pattern-fill the gap.
            value = _pattern_fill(slug, effective_pattern)
            roster_lines.append(f"{key}={value}")
            added.append(slug)
        else:
            # No override, no pattern — log a warning but don't emit a broken value.
            logger.warning(
                "ensure_product_url_roster: slug '%s' has no override and "
                "PRODUCT_URL_PATTERN is not set — skipping (unresolved origin)",
                slug,
            )
            unresolved.append(slug)

    rendered_block = (
        _BLOCK_BEGIN + "\n"
        + "\n".join(roster_lines) + "\n"
        + _BLOCK_END
    )

    # ── 4. Rebuild the file text ───────────────────────────────────────────────
    # Remove existing block lines (if any).
    if block_start_idx is not None and block_end_idx is not None:
        # Preserve everything outside the block.
        before = lines[:block_start_idx]
        after = lines[block_end_idx + 1:]
    else:
        before = list(lines)
        after = []

    # Remove bare PRODUCT_URL_* lines that are now inside the managed block
    # (absorption: first run moves them in; subsequent runs they're already gone).
    def _is_bare_url_line(line: str) -> bool:
        return bool(_BARE_URL_RE.match(line.strip()))

    before_clean = [ln for ln in before if not _is_bare_url_line(ln)]
    after_clean = [ln for ln in after if not _is_bare_url_line(ln)]

    # Assemble: non-URL lines before the block + managed block + non-URL lines after.
    # Ensure there is exactly one trailing newline before the block.
    before_text = "".join(before_clean).rstrip("\n")
    after_text = "".join(after_clean)

    new_text = (
        (before_text + "\n\n" if before_text else "")
        + rendered_block + "\n"
        + (after_text if after_text.startswith("\n") else ("\n" + after_text if after_text else ""))
    ).lstrip("\n")

    report: dict[str, Any] = {
        "added": added,
        "preserved": preserved,
        "unresolved": unresolved,
        "rendered_block": rendered_block,
    }
    return new_text, report


# ── SSH transport seam ────────────────────────────────────────────────────────


@runtime_checkable
class SshTransport(Protocol):
    """Narrow DI seam for the three SSH operations the tool needs."""

    def read_env(self, env_path: str) -> tuple[bool, str, str]:
        """Read the remote .env file.  Returns (ok, content, error)."""
        ...  # pragma: no cover

    def write_env(self, env_path: str, content: str) -> tuple[bool, str]:
        """Safe-write the remote .env (temp + mv).  Returns (ok, error)."""
        ...  # pragma: no cover

    def recreate_core(self, compose_file: str, project_dir: str) -> tuple[bool, str]:
        """docker compose up -d --force-recreate --no-deps core, run from
        ``project_dir`` (the compose file path is relative to it).  Returns (ok, error)."""
        ...  # pragma: no cover


class FakeSshTransport:
    """In-memory transport for unit tests.

    ``read_content``:   the .env text to return from read_env.
    ``read_ok``:        whether read_env succeeds (default True).
    ``write_ok``:       whether write_env succeeds (default True).
    ``recreate_ok``:    whether recreate_core succeeds (default True).
    ``written``:        populated by write_env with the written content.
    ``recreated``:      list of compose files passed to recreate_core.
    """

    def __init__(
        self,
        *,
        read_content: str = "",
        read_ok: bool = True,
        write_ok: bool = True,
        recreate_ok: bool = True,
    ) -> None:
        self.read_content = read_content
        self.read_ok = read_ok
        self.write_ok = write_ok
        self.recreate_ok = recreate_ok
        self.written: str | None = None
        self.recreated: list[str] = []

    def read_env(self, env_path: str) -> tuple[bool, str, str]:
        if self.read_ok:
            return True, self.read_content, ""
        return False, "", "fake-read-failure"

    def write_env(self, env_path: str, content: str) -> tuple[bool, str]:
        if self.write_ok:
            self.written = content
            return True, ""
        return False, "fake-write-failure"

    def recreate_core(self, compose_file: str, project_dir: str) -> tuple[bool, str]:
        self.recreated.append(compose_file)
        self.recreated_in: str = project_dir
        if self.recreate_ok:
            return True, ""
        return False, "fake-recreate-failure"


class SubprocessSshTransport:
    """Real SSH transport using subprocess.run.

    Follows the same safe-write idiom as exec_sql:
    write to a unique temp file on the VPS, validate (by re-reading it), then
    ``mv`` into place — never a partial write.
    """

    def __init__(self, ssh_host: str) -> None:
        self._host = ssh_host

    def _run(self, cmd: str) -> tuple[int, str, str]:
        r = subprocess.run(
            ["ssh", self._host, cmd],
            capture_output=True,
            text=True,
        )
        return r.returncode, (r.stdout or ""), (r.stderr or "")

    def read_env(self, env_path: str) -> tuple[bool, str, str]:
        rc, out, err = self._run(f"cat {shlex.quote(env_path)}")
        if rc != 0:
            logger.error(
                "ensure_product_url_roster: failed to read %s from %s: %s",
                env_path,
                self._host,
                err.strip(),
            )
            return False, "", f"SSH read failed (rc={rc}): {err.strip() or '<no stderr>'}"
        return True, out, ""

    def write_env(self, env_path: str, content: str) -> tuple[bool, str]:
        tmp_path = f"/tmp/noctus-env-roster-{uuid.uuid4().hex[:12]}.env"
        eof_marker = f"NOCTUS_ROSTER_EOF_{uuid.uuid4().hex[:8]}"

        # Write to temp file using a collision-safe heredoc marker (single-quote
        # disables variable expansion inside the heredoc body — critical for an
        # .env file that contains values with $ characters).
        write_cmd = (
            f"cat > {shlex.quote(tmp_path)} <<'{eof_marker}'\n"
            f"{content}\n"
            f"{eof_marker}"
        )
        rc, _out, err = self._run(write_cmd)
        if rc != 0:
            logger.error(
                "ensure_product_url_roster: failed to write temp file %s on %s: %s",
                tmp_path,
                self._host,
                err.strip(),
            )
            return False, f"SSH write temp failed (rc={rc}): {err.strip() or '<no stderr>'}"

        # Validate: confirm the file is non-empty before moving.
        rc_check, check_out, _ = self._run(f"wc -l < {shlex.quote(tmp_path)}")
        if rc_check != 0 or not check_out.strip():
            self._run(f"rm -f {shlex.quote(tmp_path)}")
            return False, "temp file validation failed (empty or unreadable)"

        # Atomic move into place.
        rc_mv, _out2, err2 = self._run(
            f"mv {shlex.quote(tmp_path)} {shlex.quote(env_path)}"
        )
        if rc_mv != 0:
            logger.error(
                "ensure_product_url_roster: mv failed (%s → %s): %s",
                tmp_path,
                env_path,
                err2.strip(),
            )
            self._run(f"rm -f {shlex.quote(tmp_path)}")
            return False, f"mv failed (rc={rc_mv}): {err2.strip() or '<no stderr>'}"

        return True, ""

    def recreate_core(self, compose_file: str, project_dir: str) -> tuple[bool, str]:
        # The compose file path is relative to the project root on the VPS; SSH's
        # default CWD is the login home (/root), so cd into project_dir first or
        # docker compose can't find deploy/fleet/docker-compose.prod.yml.
        cmd = (
            f"cd {shlex.quote(project_dir)} && "
            f"docker compose -f {shlex.quote(compose_file)} "
            f"up -d --force-recreate --no-deps core"
        )
        rc, _out, err = self._run(cmd)
        if rc != 0:
            logger.error(
                "ensure_product_url_roster: docker compose recreate core failed: %s",
                err.strip(),
            )
            return False, f"docker compose failed (rc={rc}): {err.strip() or '<no stderr>'}"
        return True, ""


def _make_transport(ssh_host: str) -> SubprocessSshTransport:
    """Factory — returns the real subprocess transport."""
    return SubprocessSshTransport(ssh_host=ssh_host)


# ── Core function ─────────────────────────────────────────────────────────────


def ensure_product_url_roster(
    *,
    confirm: bool = False,
    recreate_core: bool = True,
    ssh_host: str = _DEFAULT_SSH_HOST,
    env_path: str = _DEFAULT_ENV_PATH,
    apply: bool = True,
    transport: SshTransport | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Ensure the VPS .env carries a closed, registry-derived PRODUCT_URL roster.

    Args:
        confirm:       False (default) = dry-run; returns the computed diff
                       without writing.  True = writes the new .env over SSH
                       and (if ``recreate_core``) recreates the core container.
        recreate_core: When True (default) and ``confirm=True``, runs
                       ``docker compose ... up -d --force-recreate --no-deps core``
                       after writing the .env.
        ssh_host:      SSH host alias from ``~/.ssh/config``.  Default ``noctus-vps``.
        env_path:      Path to the VPS .env file.  Default ``/opt/noctus/noctusai/.env``.
        apply:         When False, skips the write even with ``confirm=True``
                       (safety override for tests that inject transport directly
                       but still want the computed diff).
        transport:     Injection seam for tests.  When None, uses the real
                       SubprocessSshTransport.
        repo_root:     Override REPO_ROOT (injection for tests).

    Returns a dict with keys::

        ok, status, added, preserved, unresolved, rendered_block, error
    """
    _repo_root = repo_root or REPO_ROOT

    # ── 1. Parse the canonical registry ──────────────────────────────────────
    from pathlib import Path
    start_sh = Path(_repo_root) / "start.sh"
    entries = parse_products_registry(start_sh)
    if not entries:
        logger.error(
            "ensure_product_url_roster: empty product registry from %s", start_sh
        )
        return {
            "ok": False,
            "status": "error",
            "added": [],
            "preserved": [],
            "unresolved": [],
            "rendered_block": "",
            "error": f"empty product registry — start.sh missing or unparseable: {start_sh}",
        }
    registry_slugs = [e["slug"] for e in entries]

    # ── 2. Read the remote VPS .env ────────────────────────────────────────────
    t: SshTransport = transport or _make_transport(ssh_host)
    ok_read, env_text, read_err = t.read_env(env_path)
    if not ok_read:
        return {
            "ok": False,
            "status": "error",
            "added": [],
            "preserved": [],
            "unresolved": [],
            "rendered_block": "",
            "error": f"could not read VPS .env ({env_path}): {read_err}",
        }

    # Extract the pattern from the remote .env for the pure transform.
    # We don't use _parse_env_file here; a lightweight single-key search suffices.
    pattern: str | None = None
    for raw_line in env_text.splitlines():
        stripped = raw_line.strip()
        m = _BARE_URL_RE.match(stripped)
        if m and m.group(1) == _PATTERN_KEY:
            pattern = m.group(2).strip().strip("\"'")
            break

    # ── 3. Compute the desired roster (pure) ──────────────────────────────────
    new_env_text, report = compute_roster_block(env_text, registry_slugs, pattern)

    if new_env_text == env_text:
        logger.debug("ensure_product_url_roster: .env is already up-to-date (idempotent)")
        return {
            "ok": True,
            "status": "up_to_date",
            "added": report["added"],
            "preserved": report["preserved"],
            "unresolved": report["unresolved"],
            "rendered_block": report["rendered_block"],
            "error": None,
        }

    # ── 4. Dry-run: return diff without writing ─────────────────────────────
    if not confirm:
        return {
            "ok": True,
            "status": "dry_run",
            "added": report["added"],
            "preserved": report["preserved"],
            "unresolved": report["unresolved"],
            "rendered_block": report["rendered_block"],
            "error": None,
        }

    # ── 5. Confirm=True: safe-write the new .env over SSH ─────────────────────
    if apply:
        ok_write, write_err = t.write_env(env_path, new_env_text)
        if not ok_write:
            return {
                "ok": False,
                "status": "error",
                "added": report["added"],
                "preserved": report["preserved"],
                "unresolved": report["unresolved"],
                "rendered_block": report["rendered_block"],
                "error": f"failed to write VPS .env: {write_err}",
            }

        logger.info(
            "ensure_product_url_roster: .env written (%d added, %d preserved, %d unresolved)",
            len(report["added"]),
            len(report["preserved"]),
            len(report["unresolved"]),
        )

        # ── 6. Optional: recreate core ─────────────────────────────────────────
        if recreate_core:
            # The compose path is relative to the deploy project root, which is
            # the directory holding the .env (e.g. /opt/noctus/noctusai).
            import os as _os
            project_dir = _os.path.dirname(env_path) or "/opt/noctus/noctusai"
            ok_rc, rc_err = t.recreate_core(_DOCKER_COMPOSE_FILE, project_dir)
            if not ok_rc:
                # Non-fatal: .env is already correct; surface the recreate failure.
                logger.warning(
                    "ensure_product_url_roster: core recreate failed (not fatal — "
                    ".env was written): %s",
                    rc_err,
                )
                return {
                    "ok": True,
                    "status": "applied",
                    "added": report["added"],
                    "preserved": report["preserved"],
                    "unresolved": report["unresolved"],
                    "rendered_block": report["rendered_block"],
                    "error": f"WARNING: .env written but core recreate failed: {rc_err}",
                }
            logger.info("ensure_product_url_roster: core container recreated")

    return {
        "ok": True,
        "status": "applied",
        "added": report["added"],
        "preserved": report["preserved"],
        "unresolved": report["unresolved"],
        "rendered_block": report["rendered_block"],
        "error": None,
    }


# ── MCP registration ──────────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ensure_product_url_roster",
        description=(
            "Ensure the VPS .env carries a CLOSED, registry-derived PRODUCT_URL "
            "roster so every product's SSO origin is in core's CORS allowlist "
            "by-construction — without a manual per-product step. "
            "Parses the canonical start.sh registry → reads the remote .env → "
            "computes the managed block (PRESERVES existing short-name overrides "
            "like PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com; "
            "PATTERN-FILLS gaps for pattern-convention products like orbity). "
            "DRY-RUN by default (confirm=False — returns rendered_block + "
            "added/preserved/unresolved diff without writing). "
            "confirm=True → safe-write the .env (temp+mv, never partial) + "
            "optionally recreate the core container "
            "(recreate_core=True, default). "
            "Idempotent: running twice with no registry change → up_to_date. "
            "Returns {ok, status, added, preserved, unresolved, rendered_block, error}. "
            "KB § PATTERNS/frontend/core-url-routing.md § 6."
        ),
    )
    def _ensure_product_url_roster(
        confirm: bool = False,
        recreate_core: bool = True,
        ssh_host: str = _DEFAULT_SSH_HOST,
        env_path: str = _DEFAULT_ENV_PATH,
    ) -> dict:
        return ensure_product_url_roster(
            confirm=confirm,
            recreate_core=recreate_core,
            ssh_host=ssh_host,
            env_path=env_path,
        )


__all__ = [
    "ensure_product_url_roster",
    "compute_roster_block",
    "SshTransport",
    "FakeSshTransport",
    "SubprocessSshTransport",
    "_make_transport",
    "_slug_to_env_key",
    "_pattern_fill",
    "_BLOCK_BEGIN",
    "_BLOCK_END",
    "register",
]
