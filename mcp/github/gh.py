"""GitHub `gh` CLI runner — the external-service seam for this connector.

Every `github.*` tool talks to GitHub *through the operator's
authenticated `gh` CLI*. `run_gh` is the single subprocess boundary.

**Test seam.** `gh`/GitHub is an external service, so tests
`unittest.mock.patch("github.gh.run_gh", ...)` to feed canned payloads
without a network call — sanctioned by CLAUDE.md §1 ("monkeypatching ...
for external services (LLM APIs, transcription, network) is fine"; this
is the same class). Our own code is never patched.

**Gated-capability honesty** (CLAUDE.md §1). `gh` absent /
unauthenticated is a typed, never-faked signal: read tools return a
`GitHubCliError` envelope, `github.diagnostics.connection_status`
reports `gh_available=false`. We never fabricate a success.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Optional


class GitHubCliError(Exception):
    """A `gh` invocation could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — `gh` binary absent / not authenticated (dependency unmet)
    - 502 — `gh` ran but errored / timed out / returned unparseable output
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(GitHubCliError):
    """A write/outward-facing tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    """

    def __init__(self, action: str):
        super().__init__(
            f"'{action}' is a write/outward-facing action. Re-call with "
            f"confirm=true to perform it. NO side-effect was performed.",
            status=412,
        )


def gh_available(gh_path: str = "gh") -> bool:
    """True when the `gh` binary resolves on PATH."""
    return shutil.which(gh_path) is not None


def run_gh(
    args: list[str],
    *,
    gh_path: str = "gh",
    repo: Optional[str] = None,
    timeout: float = 20.0,
    parse_json: bool = True,
    allow_nonzero: bool = False,
) -> object:
    """Run `gh <args>` and return parsed JSON (or raw stdout when
    `parse_json=False`).

    `repo` ⇒ appended as `--repo OWNER/REPO` (else `gh` infers from cwd).
    Raises `GitHubCliError` (typed `status`) on ANY failure — never
    returns a partial or fabricated success.

    `allow_nonzero` — for the few `gh` subcommands that encode *result
    state* in the exit code rather than *invocation failure* (notably
    `gh pr checks`: exit 8 = checks pending, exit 1 = checks failing,
    both with valid JSON on stdout). When True, a non-zero exit with
    non-empty stdout is NOT an error (the payload is returned); an empty
    stdout still raises (a genuine failure — bad auth/repo).
    """
    if not gh_available(gh_path):
        raise GitHubCliError(
            f"`{gh_path}` not found on PATH — install the GitHub CLI and "
            f"run `gh auth login`.",
            status=424,
        )
    cmd = [gh_path, *args]
    if repo:
        cmd += ["--repo", repo]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        raise GitHubCliError(
            f"`gh {' '.join(args)}` timed out after {timeout}s", status=502
        ) from e
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not (allow_nonzero and out):
        stderr = (proc.stderr or "").strip()
        low = stderr.lower()
        status = 424 if ("auth" in low and "login" in low) else 502
        raise GitHubCliError(
            f"`gh {' '.join(args)}` exited {proc.returncode}: "
            f"{stderr or '(no stderr)'}",
            status=status,
        )
    if not parse_json:
        return out
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise GitHubCliError(
            f"`gh {' '.join(args)}` returned non-JSON output", status=502
        ) from e


__all__ = [
    "run_gh",
    "gh_available",
    "GitHubCliError",
    "ConfirmationRequiredError",
]
