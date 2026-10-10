"""env_bootstrap — the ONE dotenv-loading path shared by the MCP server
(`server.py`) and the CLI/hooks (`cli.py`).

🔴 WHY THIS EXISTS (root-caused 2026-08-31 for the server; 2026-09-14 for the
CLI) — ``.mcp.json`` launches the MCP server with no ``env`` block and no
dotenv loading, so ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` /
``SUPABASE_ACCESS_TOKEN`` were absent from the server's ``os.environ`` even
though the repo-root ``.env`` has them (fixed 2026-08-31 by loading the
repo-root ``.env`` at server import time — see the git-blame history on this
module for the original ``server._load_repo_root_dotenv``). That fix covered
ONLY the server's own process: ``scripts/hooks/pre-push`` invokes
``cli.py`` directly, never imports ``server.py``, and ``cli.py`` never loaded
``.env`` at all — so ``check_migration_applied_ledger_drift`` kept SKIPping
("no supabase_access_token resolved") from the CLI/hook path even though the
SAME ``.env``, on the SAME disk, has ``SUPABASE_ACCESS_TOKEN`` set. Both
defects have the identical shape (a real credential sits in a gitignored
``.env`` and the consuming process's ``os.environ`` never sees it) — this
module is the single shared fix so no THIRD entry point can reintroduce the
gap under a different name.

Worktree wrinkle. A worktree never carries its own ``.env`` copy (gitignored,
not part of a worktree checkout), yet the CLI legitimately runs with
``settings.REPO_ROOT`` pointed AT a worktree — ``scripts/hooks/pre-push``
resolves ``cli.py`` from the pushing worktree deliberately, so the code under
review is what gets checked (KB § architect/seed-workspace.md worktree-
boundary detection). :func:`load_repo_env` therefore tries ``.env`` at
``repo_root`` first, then — via ``git rev-parse --git-common-dir`` — at the
PRIMARY checkout the worktree shares git state with, since secrets live ONLY
there. Same resolver shape as
``tools.noctus.dev.cache_backend._git_common_dir`` (kept independent here:
this module must be importable at CLI/server bootstrap time, before
``tools.*`` exists on ``sys.path``).

🔴 SUBPROCESS-ENV HYGIENE (root-caused 2026-09-27) — this module fixes the
server/CLI's OWN ``os.environ``, but ``noctus.dev.task_branch action=
'integrate'``'s merged-tip check (``gate_sweep.py``) spawns pytest/vitest as
CHILD subprocesses of that same process, and a bare ``subprocess.run(...)``
with no ``env=`` override inherits the FULL parent environment — including
every secret this module just loaded from ``.env``. CI runs the exact same
seed/mcp-toolkit suites from a scrubbed ``env -i`` (see
``.github/workflows/test.yml``'s "Seed Backend Tests (pytest)" / "Tooling
Tests (pytest)" jobs — both are sized green from ``env -i``, no ``.env``, no
``SUPABASE_*``), so a test asserting "unset env -> raises / -> None / -> a
named fallback" is correct there and a PERMANENT false-red in a gate
subprocess that inherited real credentials instead of an absent variable —
the harness, not the code, per ``KB § PATTERNS/common/methodology-execution-
discipline.md`` § 7. It got WORSE than a false-red once, the same day: the
failing assertion line — a real Resend API key — was copied verbatim into
the gate's ``summary`` and handed back in an MCP tool result, which lands
directly in a model's context window. :func:`sanitize_subprocess_env` and
:func:`redact_secrets_in_text` are the two-legged fix — strip the exact keys
THIS module injected before spawning a gate subprocess, and mask any secret
shape that still reaches a returned string as a backstop.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

_DOTENV_FILENAME = ".env"

# Names newly added to ``os.environ`` by THIS process's ``load_repo_env()``
# call(s) — never values (see :class:`EnvBootstrapResult`'s own contract).
# Module-level because the gate-subprocess callers (``gate_sweep.py``) run
# long after ``load_repo_env`` returned, inside the same long-lived MCP
# server / CLI process, and need to know which keys to strip WITHOUT
# re-parsing ``.env`` themselves (a second read could drift from what
# actually landed in ``os.environ`` on ``override=False``).
_loaded_keys: set[str] = set()

# Provenance that SURVIVES A PROCESS HOP (2026-10-09). `_loaded_keys` is
# per-process: a child spawned with this process's env (the toolkit-
# staleness fresh-subprocess fallback, any `cli.py` re-exec) inherits the
# `.env` VALUES as plain env vars, its own `load_repo_env` sees them as
# "already set" (0 new keys) and its `sanitize_subprocess_env()` strips
# NOTHING — the merged-tip pytest gate then ran on the developer's `.env`
# and false-redded every "unset key → X" test. So the names ride along as
# this marker (names only, never values) and `get_loaded_keys()` honours
# an inherited one.
LOADED_KEYS_ENV_MARKER = "NOCTUS_ENV_BOOTSTRAP_KEYS"


def _inherited_loaded_keys() -> set[str]:
    """Names a PARENT process's ``load_repo_env`` injected (via the marker),
    restricted to keys still present here."""
    raw = os.environ.get(LOADED_KEYS_ENV_MARKER, "")
    return {k for k in raw.split(",") if k and k in os.environ}


@dataclass(frozen=True)
class EnvBootstrapResult:
    """Diagnostic result of a :func:`load_repo_env` call.

    Booleans + paths only — NEVER a secret value. Callers (e.g. the
    ``check_migration_applied_ledger_drift`` SKIP message) use this to name
    which sources were tried instead of a generic "not resolved".
    """

    attempted: tuple[Path, ...]
    loaded_from: tuple[Path, ...]
    dotenv_installed: bool
    supabase_url_present: bool
    supabase_service_role_key_present: bool
    supabase_access_token_present: bool


def _git_common_dir(repo_root: Path) -> Path:
    """Return the directory git uses for shared state across worktrees.

    For the primary tree: ``<repo>/.git``. For a linked worktree: still
    ``<primary>/.git`` (worktrees carry a stub ``.git`` file pointing back).
    Falls back to ``<repo_root>/.git`` when git is unavailable or
    ``repo_root`` isn't inside a git work tree at all (e.g. a bare tmp dir
    in a test).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        path_str = out.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return repo_root / ".git"
    common = Path(path_str)
    if not common.is_absolute():
        common = (repo_root / common).resolve()
    return common


def _candidate_roots(repo_root: Path) -> tuple[Path, ...]:
    """``.env`` search order: ``repo_root`` itself, then — only when
    ``repo_root`` resolves to a linked worktree — the PRIMARY checkout.
    Deduplicated; order preserved.
    """
    repo_root = repo_root.resolve()
    primary_root = _git_common_dir(repo_root).parent.resolve()
    candidates = [repo_root]
    if primary_root != repo_root:
        candidates.append(primary_root)
    return tuple(candidates)


def load_repo_env(
    repo_root: Path,
    *,
    logger: logging.Logger | None = None,
) -> EnvBootstrapResult:
    """Load the repo's ``.env`` into this process's environment.

    Never raises. A missing ``.env`` at every candidate root is not an error
    (fresh clone / CI must still boot) — logged once at INFO.
    ``override=False`` throughout: an already-set process env var always
    wins over any ``.env`` value, from either candidate root — this never
    clobbers a value the caller (shell, CI, launcher) deliberately set.

    ``logger`` defaults to this module's own logger; pass the caller's
    logger (e.g. ``logging.getLogger("server")``) to keep log provenance
    attributed to the calling entry point.
    """
    log = logger or logging.getLogger(__name__)
    try:
        from dotenv import load_dotenv
        dotenv_installed = True
    except ImportError as exc:  # pragma: no cover — dependency is pinned
        log.warning(
            "env_bootstrap: python-dotenv not installed (%s); relying on "
            "already-set env. Run `pip install -r "
            "mcp/noctusai/requirements.txt`.",
            exc,
        )
        dotenv_installed = False
        load_dotenv = None  # type: ignore[assignment]

    attempted = _candidate_roots(repo_root)
    loaded_from: list[Path] = []

    if dotenv_installed:
        for candidate in attempted:
            env_path = candidate / _DOTENV_FILENAME
            if not env_path.exists():
                continue
            keys_before = set(os.environ)
            load_dotenv(env_path, override=False)
            newly_set = set(os.environ) - keys_before
            _loaded_keys.update(newly_set)
            loaded_from.append(env_path)
            log.info(
                "env_bootstrap: loaded %s (%s new key(s), override=False so "
                "an already-set env var always wins).",
                env_path, len(newly_set),
            )

    # Publish provenance for any child process (see LOADED_KEYS_ENV_MARKER).
    known = get_loaded_keys()
    if known:
        os.environ[LOADED_KEYS_ENV_MARKER] = ",".join(sorted(known))

    if not loaded_from:
        tried = ", ".join(str(c / _DOTENV_FILENAME) for c in attempted)
        log.info(
            "env_bootstrap: no repo-root .env found (tried: %s); relying on "
            "already-set process env (expected on a fresh clone / CI).",
            tried,
        )

    return EnvBootstrapResult(
        attempted=attempted,
        loaded_from=tuple(loaded_from),
        dotenv_installed=dotenv_installed,
        supabase_url_present=bool(os.environ.get("SUPABASE_URL")),
        supabase_service_role_key_present=bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        ),
        supabase_access_token_present=bool(os.environ.get("SUPABASE_ACCESS_TOKEN")),
    )


def get_loaded_keys() -> frozenset[str]:
    """Names (never values) of every environment key this process's
    :func:`load_repo_env` call(s) actually injected from a ``.env`` file so
    far. Empty before the first :func:`load_repo_env` call — a bare unit
    test importing this module directly, or a process that legitimately
    found no ``.env`` at all, must treat that as "nothing known to strip",
    never as an error. Includes names a PARENT process injected and handed
    down via :data:`LOADED_KEYS_ENV_MARKER` — provenance must survive the
    hop, or a re-exec'd child strips nothing."""
    return frozenset(_loaded_keys | _inherited_loaded_keys())


# Env-var NAME shapes presumed secret regardless of provenance — catches a
# credential a caller's shell exported directly (never touched `.env`, so
# `get_loaded_keys()` alone would miss it).
_SECRET_NAME_RE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD)", re.IGNORECASE)

# A value shorter than this is far more likely a flag/enum ("true", "prod")
# than a credential; masking it would just corrupt unrelated output for no
# safety gain.
_MIN_MASKABLE_VALUE_LENGTH = 6

# Common credential SHAPES, matched even when we have no env-var NAME to
# pin them to (e.g. a token baked into a fixture, or echoed by a vendor
# SDK's own error message). Order matters: a more SPECIFIC prefix (`sk-
# ant-`) must be tried before the more GENERAL one it is also a substring
# of (`sk-`), same "specific-before-general" discipline as
# `harness_signatures.HARNESS_SIGNATURES`.
_TOKEN_SHAPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}"), "sk-ant-***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "sk-***"),
    (re.compile(r"re_[A-Za-z0-9_-]{8,}"), "re_***"),
    (re.compile(r"ghp_[A-Za-z0-9_-]{20,}"), "ghp_***"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"), "eyJ***"),
)

# The exact placeholder every existing per-connector redactor in this repo
# already uses (`noctusai_lib.integrations.imovelweb.errors.
# SECRET_REDACTION_PLACEHOLDER`, `olx.errors.redact_secret`) — kept as a
# literal here (not imported) because this module must stay importable at
# CLI/server bootstrap time, before `noctusai_lib` is necessarily on
# `sys.path`; matching the SAME string keeps a redacted transcript
# consistent regardless of which redactor touched it.
_KNOWN_VALUE_REDACTION_PLACEHOLDER = "***REDACTED***"


# ---------------------------------------------------------------------------
# Worktree `.env` — SCRUBBED, never the primary's (2026-10-10).
#
# THE INCIDENT. `task_branch` wire_env used to SYMLINK the primary `.env`
# (production service-role key included) into every worktree, because the
# seed's `ProductSettings.env_file` and Vite's `envDir` both read the TREE
# ROOT `.env`. On 2026-10-09 a social-wiring test run from a worktree read
# those real credentials and wrote into production. `gate_subprocess_env`
# only scrubbed the gate subprocess's ENVIRONMENT; the product read the FILE.
#
# By construction now: a worktree gets a generated `.env` with the public
# `VITE_*` keys only (Vite ships them to every browser); the backend runs as
# in CI, with no `.env`. The toolkit is unaffected: `load_repo_env`
# still reads the PRIMARY `.env` by path (`_candidate_roots`). CI runs every
# product suite with no `.env` at all, so product tests need none of the
# secrets.
# ---------------------------------------------------------------------------

#: A URL carrying `user:password@` (DATABASE_URL, REDIS_URL with auth, …).
_CREDENTIALED_URL_RE = re.compile(r"://[^/\s:@]+:[^@\s]+@")
#: The marker heading a generated worktree `.env` — `task_branch` overwrites a
#: file carrying it, and refuses to touch one that doesn't (someone's own).
SCRUBBED_DOTENV_MARKER = "# noctus: scrubbed worktree .env"


def is_secret_entry(key: str, value: str | None) -> bool:
    """The ONE secret classifier for an env entry: a secret-shaped NAME
    (`KEY|SECRET|TOKEN|PASSWORD` — the same `_SECRET_NAME_RE` the redactor
    masks by), a known credential VALUE shape (`_TOKEN_SHAPE_PATTERNS`), or a
    URL with embedded credentials."""
    if _SECRET_NAME_RE.search(key):
        return True
    if not value:
        return False
    return (any(p.search(value) for p, _ in _TOKEN_SHAPE_PATTERNS)
            or bool(_CREDENTIALED_URL_RE.search(value)))


def scrub_dotenv(values: Mapping[str, str | None]) -> tuple[dict[str, str], list[str]]:
    """(kept entries, dropped key names) for a worktree `.env`: ONLY `VITE_*`
    keys — the frontend's build-time config, public by construction (Vite
    ships them to every browser) — except one whose value is a credentialed
    URL (a password behind a `VITE_` name is a secret about to leak into a
    bundle). Token SHAPES are deliberately not applied here: the Supabase
    publishable/anon key is a JWT and is public by design — the SPA can't
    boot without it. Everything else is dropped: the backend gets exactly what CI
    gives it — nothing. Measured 2026-10-10: a kept non-secret `REDIS_URL`
    flips every product into shared-Redis session mode (which then demands
    an encryption key), `SENTRY_DSN` would ship test errors to prod Sentry,
    `SUPABASE_URL` trips the seed live-DB guard. Names only are returned for
    the dropped side — never values."""
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        if key.startswith("VITE_") and not _CREDENTIALED_URL_RE.search(value):
            kept[key] = value
        else:
            dropped.append(key)
    return kept, sorted(dropped)


def render_scrubbed_dotenv(source: Path) -> tuple[str, list[str]]:
    """The text of a scrubbed worktree `.env` built from ``source`` (the
    primary `.env`), and the dropped key names."""
    from dotenv import dotenv_values

    kept, dropped = scrub_dotenv(dotenv_values(source))
    lines = [
        SCRUBBED_DOTENV_MARKER,
        "# Generated by task_branch wire_env from the primary .env: VITE_* keys",
        "# only (the frontend's public config). The backend runs as in CI, with no",
        "# .env; secrets live ONLY in the primary .env, read by the toolkit by path.",
        "# Never replace this file with the primary's.",
        f"# dropped ({len(dropped)}): " + ", ".join(dropped),
    ]
    for key, value in kept.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    return "\n".join(lines) + "\n", dropped


def sanitize_subprocess_env(
    base_env: Mapping[str, str] | None = None,
    *,
    extra_strip: Iterable[str] = (),
) -> dict[str, str]:
    """A copy of ``base_env`` (default: the current ``os.environ``) with
    every key :func:`load_repo_env` injected from a ``.env`` file removed.

    Use this for ANY subprocess a long-running server/CLI process spawns to
    run a test/build suite — see this module's docstring for the
    2026-09-27 incident it fixes. Only the keys THIS module actually
    injected are stripped: ``PATH``/``HOME``/the active venv/anything the
    caller's own shell or CI job set stays untouched, because CI's own
    job-level ``env:`` blocks (e.g. ``NOCTUS_DISABLE_AUTO_CACHE_PULL`` in
    ``.github/workflows/test.yml``'s mcp-toolkit-tests job) are exactly
    what proves a gate genuinely needs those — never a `.env` secret.

    ``extra_strip`` lets a caller name additional keys to remove beyond
    what was auto-tracked (e.g. a key set by hand outside `.env`, matching
    this same threat shape)."""
    env = dict(base_env if base_env is not None else os.environ)
    for key in get_loaded_keys():
        env.pop(key, None)
    env.pop(LOADED_KEYS_ENV_MARKER, None)
    for key in extra_strip:
        env.pop(key, None)
    return env


def dotenv_residue(env: Mapping[str, str], repo_root: Path) -> list[str]:
    """Names (never values) of keys in ``env`` whose value is IDENTICAL to the
    repo ``.env``'s (any candidate root) — i.e. the developer's ``.env`` is
    still in a gate subprocess's env even after :func:`sanitize_subprocess_env`
    (a shell that ran ``set -a; . .env``, or a parent that dropped the
    provenance marker). A gate run on such an env judges the ``.env``, not
    the code (verdict-channel integrity) — ``gate_sweep`` refuses to run it.
    Values shorter than ``_MIN_MASKABLE_VALUE_LENGTH`` are ignored (a flag or
    enum like ``true`` coinciding is not evidence of provenance). Never
    raises: unreadable ``.env`` / no python-dotenv ⇒ ``[]``."""
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover — dependency is pinned
        return []
    residue: set[str] = set()
    for candidate in _candidate_roots(repo_root):
        env_path = candidate / _DOTENV_FILENAME
        if not env_path.exists():
            continue
        try:
            values = dotenv_values(env_path)
        except (OSError, UnicodeDecodeError):
            continue
        for key, value in values.items():
            if (value is not None and len(value) >= _MIN_MASKABLE_VALUE_LENGTH
                    and env.get(key) == value):
                residue.add(key)
    return sorted(residue)


def gate_subprocess_env(repo_root: Path, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The env a GATE subprocess (test/build suite) runs with: the provenance-
    based :func:`sanitize_subprocess_env` PLUS a value-based scrub of every key
    whose value is identical to the repo ``.env``'s (:func:`dotenv_residue`).

    The scrub is what makes gates runnable however the server was launched —
    an MCP server started before the provenance marker existed, or from a shell
    that sourced ``.env``, carries the values with no marker (2026-10-09: 4/4
    integrates ``inconclusive`` on ``env_free_of_dotenv``). A value equal to the
    developer ``.env``'s is by definition that ``.env`` leaking in, never a
    deliberate override, and CI runs these suites with no ``.env`` at all."""
    env = sanitize_subprocess_env(base_env)
    for key in dotenv_residue(env, repo_root):
        env.pop(key, None)
    return env


def _known_secret_values() -> dict[str, str]:
    """Env values presumed sensitive RIGHT NOW: everything
    :func:`load_repo_env` injected from ``.env``, plus anything else
    already in ``os.environ`` whose NAME looks like a secret. Names only
    decide WHICH values count; the values themselves are read fresh on
    every call — never cached — so a rotated secret is never masked
    against its stale former value only."""
    names = set(get_loaded_keys())
    names.update(k for k in os.environ if _SECRET_NAME_RE.search(k))
    out: dict[str, str] = {}
    for name in names:
        value = os.environ.get(name)
        if value and len(value) >= _MIN_MASKABLE_VALUE_LENGTH:
            out[name] = value
    return out


def redact_secrets_in_text(text: str) -> str:
    """Mask every known-secret env VALUE and every common secret-token
    SHAPE out of ``text`` before it can reach a caller.

    🔴 THE INCIDENT THIS CLOSES (2026-09-27) — ``noctus.dev.gate_sweep``'s
    ``summary`` field once copied a failing pytest assertion line
    VERBATIM, which included a real Resend API key value read straight out
    of ``os.environ`` — printed into an MCP tool result, which lands
    directly in a model's context window (same boundary
    ``noctusai_lib.integrations.imovelweb.errors.redact_secrets`` already
    enforces for that connector's own secrets; see that module's
    docstring). Two independent legs, because either can fire without the
    other: a value we ALREADY KNOW is a secret (its env-var name matches,
    or ``.env`` injected it) is masked by exact substring match; a value we
    have no name for but that LOOKS like a token (``re_...``, ``sk-...``,
    ``sk-ant-...``, ``ghp_...``, a JWT) is masked by shape. Never raises;
    an empty/``None``-ish ``text`` is returned unchanged."""
    if not text:
        return text
    redacted = text
    for value in sorted(_known_secret_values().values(), key=len, reverse=True):
        if value and value in redacted:
            redacted = redacted.replace(value, _KNOWN_VALUE_REDACTION_PLACEHOLDER)
    for pattern, replacement in _TOKEN_SHAPE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


__all__ = [
    "EnvBootstrapResult",
    "load_repo_env",
    "get_loaded_keys",
    "sanitize_subprocess_env",
    "dotenv_residue",
    "gate_subprocess_env",
    "LOADED_KEYS_ENV_MARKER",
    "redact_secrets_in_text",
]
