"""Shared client plumbing for the Agent Packages sync tools (CONTRACT §F/§G/§H, A5/A8).

Used by ``agent_package_publish`` / ``agent_context_sync`` / ``agent_learnings_push`` /
``agent_learnings_promote`` and the hook runner (``scripts/agent-hooks/agent_sync_runner.py``).

* Credentials: ``NOCTUS_AGENTS_URL`` + ``NOCTUS_AGENTS_TOKEN`` from the process env, else from
  ``~/.config/noctus/agents.env`` (``KEY=value`` lines). NEVER from the repo. The token is never logged:
  every message that leaves this module is passed through :func:`redact`.
* HTTP: stdlib ``urllib`` (no extra dependency in a consumer's hook), JSON in/out, a browser-ish UA
  (the agents host sits behind Cloudflare's WAF).
* Pending marker (A5): ``.agents-sync-pending`` at a repo root — written on any sync failure, cleared on
  the next fully successful run. A failure is never silent and never blocks the push.
* Per-agent advisory lock: a project-source sync changes the compiled hash, so it must not interleave with
  a publish pipeline (import → eval → publish) for the same agent.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger("noctus.dev.agent_sync_client")

ENV_URL = "NOCTUS_AGENTS_URL"
ENV_TOKEN = "NOCTUS_AGENTS_TOKEN"
DEFAULT_ENV_FILE = Path("~/.config/noctus/agents.env")
MARKER_NAME = ".agents-sync-pending"
USER_AGENT = "Mozilla/5.0 (compatible; noctus-agent-sync/1.0)"


class SyncError(Exception):
    """A sync step failed. ``code`` is machine-readable; the message is already redacted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── credentials ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Credentials:
    url: str
    token: str
    source: str  # "env" | "file" | "env+file"

    def __repr__(self) -> str:  # never print the token, even by accident
        return f"Credentials(url={self.url!r}, token=<redacted>, source={self.source!r})"


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load_credentials(env: dict[str, str] | None = None, env_file: str | Path | None = None) -> Credentials | None:
    """Env wins over the file. ``None`` when either value is missing."""
    environ = os.environ if env is None else env
    path = Path(env_file or environ.get("NOCTUS_AGENTS_ENV_FILE") or DEFAULT_ENV_FILE).expanduser()
    file_vals = parse_env_file(path)
    url = environ.get(ENV_URL) or file_vals.get(ENV_URL) or ""
    token = environ.get(ENV_TOKEN) or file_vals.get(ENV_TOKEN) or ""
    if not url or not token:
        return None
    from_env = bool(environ.get(ENV_URL) or environ.get(ENV_TOKEN))
    from_file = bool(file_vals.get(ENV_URL) or file_vals.get(ENV_TOKEN))
    source = "env+file" if (from_env and from_file) else ("env" if from_env else "file")
    return Credentials(url=url.rstrip("/"), token=token, source=source)


def credentials_or_error(env: dict[str, str] | None = None, env_file: str | Path | None = None) -> Credentials:
    creds = load_credentials(env, env_file)
    if creds is None:
        raise SyncError(
            "not_configured",
            f"{ENV_URL}/{ENV_TOKEN} not found (env or {DEFAULT_ENV_FILE}) — "
            "mint a pk_ token (Studio → Configurações → API tokens) and put both in that file",
        )
    return creds


def redact(text: str, token: str | None) -> str:
    return text.replace(token, "<token>") if token and token in text else text


# ── HTTP ────────────────────────────────────────────────────────────────────


@dataclass
class HttpResult:
    status: int
    data: Any  # parsed JSON, else None
    text: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def code(self) -> str | None:
        """The flat-error ``code`` (Studio §D): ``{"detail": ..., "code": ...}`` (maybe under ``detail``)."""
        d = self.data
        if isinstance(d, dict):
            if isinstance(d.get("code"), str):
                return d["code"]
            inner = d.get("detail")
            if isinstance(inner, dict) and isinstance(inner.get("code"), str):
                return inner["code"]
        return None

    def detail(self) -> str:
        d = self.data
        if isinstance(d, dict):
            inner = d.get("detail", d)
            if isinstance(inner, dict):
                inner = inner.get("detail", inner)
            return inner if isinstance(inner, str) else json.dumps(inner, ensure_ascii=False)[:500]
        return self.text[:300]


def http_json(
    method: str,
    creds: Credentials,
    path: str,
    body: Any = None,
    query: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> HttpResult:
    """One JSON request. Network failures raise :class:`SyncError` (redacted)."""
    url = creds.url + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {creds.token}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-configured https URL
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SyncError("network", redact(f"{method} {path}: {exc}", creds.token)) from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return HttpResult(status=status, data=parsed, text=redact(text, creds.token))


def http_failure(res: HttpResult, what: str) -> SyncError:
    """Map a non-2xx into a SyncError with a stable code (``auth_insufficient`` for the scope gaps)."""
    code = res.code or f"http_{res.status}"
    if res.status in (401, 403):
        why = {"user_required": "this route is user-only (a pk_ token cannot reach it)",
               "scope_missing": "the token lacks the required scope"}.get(code, "authentication/authorization refused")
        return SyncError("auth_insufficient" if res.status == 403 else "unauthorized", f"{what}: HTTP {res.status} {code} — {why}")
    return SyncError(code, f"{what}: HTTP {res.status} {code} — {res.detail()}")


# ── pending marker (A5) ─────────────────────────────────────────────────────


def marker_path(repo: str | Path) -> Path:
    return Path(repo) / MARKER_NAME


def read_marker(repo: str | Path) -> dict[str, Any] | None:
    p = marker_path(repo)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"raw": str(data)}
    except json.JSONDecodeError:
        return {"raw": p.read_text(encoding="utf-8", errors="replace")[:500]}


def write_marker(repo: str | Path, failures: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> Path:
    p = marker_path(repo)
    payload: dict[str, Any] = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "failures": failures}
    payload.update(extra or {})
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def clear_marker(repo: str | Path) -> bool:
    p = marker_path(repo)
    if p.is_file():
        p.unlink()
        return True
    return False


# ── per-agent advisory lock ─────────────────────────────────────────────────


@contextlib.contextmanager
def agent_lock(key: str, lock_dir: str | Path | None = None, timeout_s: float = 120.0) -> Iterator[None]:
    """Serialise publish pipeline vs project-source sync for one agent (they both move the compiled hash)."""
    import fcntl

    d = Path(lock_dir or os.environ.get("NOCTUS_AGENTS_LOCK_DIR") or "~/.config/noctus").expanduser()
    d.mkdir(parents=True, exist_ok=True)
    fh = open(d / f"agent-sync-{key}.lock", "w")  # noqa: SIM115 — held for the context's lifetime
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SyncError("lock_timeout", f"another sync/publish for agent {key!r} is running (waited {timeout_s:.0f}s)")
                time.sleep(0.2)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
