"""noctus.dev.image_pin -- the CONSTRUCTION half of the supply-chain pin keeper: resolve and write image digests.

**Why.** `check_supply_chain_pin` (compliance.py) refuses an unpinned image on the prod deploy surface
(`deploy/{fleet,services,legacy,tunnel}/*.yml`). A keeper that only says "no" makes every new image a failed commit;
the owner's rule is that the build produces the compliant state by default and the keeper is only a net. So this tool does the
pin: it resolves a tag to its registry digest and writes `name:tag@sha256:<digest>` into the compose file.

  action='check'   offline: the unpinned images (the keeper's own predicate, so the two cannot disagree)
  action='pin'     resolve a digest for every unpinned image and rewrite it in place (write=False = dry-run plan)
  action='bump'    image=<name> tag=<tag>: move every pinned/unpinned use of <name> to <tag> at its CURRENT digest
                   (the deliberate upgrade path; Dependabot's docker ecosystem opens the same change as a PR)

Keeping the tag beside the digest is deliberate: Dependabot (`package-ecosystem: docker`, deploy/**) bumps the digest
for a `name:tag@sha256:` ref and the human reads which tag it follows. Pinning what is RUNNING (so a deploy is a no-op
recreate) is `docker inspect` -> `bump`/edit by hand; `pin` resolves what the tag points at NOW.

Seam: `head(url, headers) -> (status, response_headers)` is injectable; tests make zero network calls.
KB § PATTERNS/devops/ci-security-gates.md § Supply-chain pins.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import compliance as _c

Head = Callable[[str, dict], "tuple[int, dict]"]
_ACCEPT = ("application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, "
           "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VAR_DEFAULT_RE = re.compile(r"^(?P<pre>\$\{[A-Za-z_][A-Za-z0-9_]*:-)(?P<d>[^}]*)(?P<post>\})$")


# ── pure ──────────────────────────────────────────────────────────────────

def split_ref(ref: str) -> tuple[str, str, str, str | None]:
    """-> (registry, repository, tag, digest). Docker Hub official images live under `library/`."""
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
    first, _, rest = ref.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, path = first, rest
    else:
        registry, path = "docker.io", ref
    repo, tag = (path.rsplit(":", 1) + ["latest"])[:2] if ":" in path.rsplit("/", 1)[-1] else (path, "latest")
    if registry == "docker.io" and "/" not in repo:
        repo = f"library/{repo}"
    return registry, repo, tag, digest


def retag(ref: str, tag: str | None) -> str:
    """`name[:tag][@digest]` -> `name:<tag>` (digest dropped; no tag given and none present => `latest` explicitly)."""
    base = ref.split("@", 1)[0]
    has_tag = ":" in base.rsplit("/", 1)[-1]
    if tag:
        base = base.rsplit(":", 1)[0] if has_tag else base
        return f"{base}:{tag}"
    return base if has_tag else f"{base}:latest"


def pinned(ref: str, digest: str, tag: str | None = None) -> str:
    """`name[:tag]` -> `name:tag@sha256:...` (an existing digest is replaced; `tag` re-tags; no tag => `latest`)."""
    if not _DIGEST_RE.match(digest):
        raise ValueError(f"not a sha256 digest: {digest!r}")
    return f"{retag(ref, tag)}@{digest}"


def pin_line(line: str, digest: str, tag: str | None = None) -> str:
    """Rewrite the `image:` value on one compose line (handles the `${VAR:-default}` form: the default is pinned)."""
    m = _c._SUPPLY_CHAIN_IMAGE_RE.match(line)
    if not m:
        return line
    raw = m.group("ref")
    quote = raw[0] if raw[:1] in "\"'" else ""
    val = raw.strip("\"'")
    v = _VAR_DEFAULT_RE.match(val)
    new = (v.group("pre") + pinned(v.group("d"), digest, tag) + v.group("post")) if v else pinned(val, digest, tag)
    return line.replace(raw, f"{quote}{new}{quote}", 1)


def _ref_of(line: str) -> str | None:
    m = _c._SUPPLY_CHAIN_IMAGE_RE.match(line)
    if not m:
        return None
    val = m.group("ref").strip("\"'")
    v = _VAR_DEFAULT_RE.match(val)
    return v.group("d") if v else (None if val.startswith("${") else val)


def _files(root: Path) -> list[Path]:
    return [f for pat in _c._SUPPLY_CHAIN_COMPOSE_GLOBS for f in sorted(root.glob(pat))]


def find_unpinned(root: Path) -> list[dict]:
    """Every image the keeper would refuse (same predicate + same `pin-ok` window), with its location."""
    out: list[dict] = []
    for f in _files(root):
        lines = f.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            ref = _ref_of(line)
            if ref is None or _c._supply_chain_image_violation(line.split("image:", 1)[1].strip().split()[0]) is None:
                continue
            if any("pin-ok" in w for w in [line, *lines[max(0, n - 6):n - 1]]):
                continue
            out.append({"file": str(f.relative_to(root)), "line": n, "ref": ref})
    return out


# ── io ────────────────────────────────────────────────────────────────────

def _real_head(url: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers, method="HEAD" if "/manifests/" in url else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - https only
            return r.status, {k.lower(): v for k, v in r.headers.items()} | (
                {"_body": r.read(65536).decode("utf-8", "replace")} if "/manifests/" not in url else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}


def resolve_digest(ref: str, head: Head | None = None) -> str:
    """The registry digest the tag points at right now (index digest for a multi-arch image)."""
    head = head or _real_head
    registry, repo, tag, _ = split_ref(ref)
    if registry == "docker.io":
        tok_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
        host = "registry-1.docker.io"
    elif registry == "ghcr.io":
        tok_url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repo}:pull"
        host = "ghcr.io"
    else:
        raise ValueError(f"registry {registry!r} is not supported (docker.io, ghcr.io) -- pin it by hand")
    st, hdr = head(tok_url, {})
    if st != 200:
        raise ValueError(f"token request for {repo} failed (HTTP {st})")
    try:
        bearer = json.loads(hdr.get("_body", "")).get("token", "")
    except ValueError:
        bearer = ""
    if not bearer:
        raise ValueError(f"no registry token for {repo}")
    st, hdr = head(f"https://{host}/v2/{repo}/manifests/{tag}", {"Authorization": f"Bearer {bearer}", "Accept": _ACCEPT})
    digest = hdr.get("docker-content-digest", "")
    if st != 200 or not _DIGEST_RE.match(digest):
        raise ValueError(f"could not resolve {repo}:{tag} (HTTP {st})")
    return digest


def image_pin(
    action: str = "check",
    *,
    write: bool = False,
    image: str | None = None,
    tag: str | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    head: Head | None = None,
) -> dict[str, Any]:
    root = Path(worktree_path or repo_root or Path(__file__).resolve().parents[5])
    if action == "check":
        bad = find_unpinned(root)
        return {"ok": not bad, "action": action, "status": "clean" if not bad else "unpinned", "unpinned": bad,
                **({} if not bad else {"fix": "noctus.dev.image_pin action='pin' write=True"})}
    if action not in ("pin", "bump"):
        return {"ok": False, "action": action, "error": "unknown action -- expected check | pin | bump"}
    changes: list[dict] = []
    errors: list[str] = []
    digests: dict[str, str] = {}

    def digest_for(ref: str) -> str:
        if ref not in digests:
            digests[ref] = resolve_digest(ref, head)
        return digests[ref]

    for f in _files(root):
        lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
        dirty = False
        for n, line in enumerate(lines, 1):
            ref = _ref_of(line)
            if ref is None:
                continue
            target = None
            if action == "pin":
                if _c._supply_chain_image_violation(line.split("image:", 1)[1].strip().split()[0]) is None:
                    continue
                if any("pin-ok" in w for w in [line, *lines[max(0, n - 6):n - 1]]):
                    continue
                target = ref
            else:
                if not image or not tag:
                    return {"ok": False, "action": action, "error": "bump needs image= and tag="}
                reg, repo, _, _ = split_ref(ref)
                breg, brepo, _, _ = split_ref(image)
                if (reg, repo) != (breg, brepo):
                    continue
                target = retag(ref, tag)
            try:
                d = digest_for(target)
            except ValueError as e:
                errors.append(f"{f.relative_to(root)}:{n} {ref}: {e}")
                continue
            new_line = pin_line(line, d, tag if action == "bump" else None)
            if new_line != line:
                changes.append({"file": str(f.relative_to(root)), "line": n, "from": ref, "to": _ref_of(new_line)})
                lines[n - 1] = new_line
                dirty = True
        if dirty and write:
            f.write_text("".join(lines), encoding="utf-8")
    return {"ok": not errors, "action": action, "status": ("written" if write else "planned") if changes else "nothing_to_do",
            "changes": changes, "errors": errors}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.image_pin",
        description=(
            "Resolve + write image digests on the prod deploy surface (deploy/{fleet,services,legacy,tunnel}) so the "
            "build produces the pinned state and the check_supply_chain_pin keeper is only a net. action='check' "
            "(offline, same predicate as the keeper) | 'pin' (digest for every unpinned image; write=True rewrites) | "
            "'bump' image=<name> tag=<tag> (deliberate upgrade to that tag's current digest). Registries: docker.io, "
            "ghcr.io. Writes `name:tag@sha256:...` so Dependabot's docker ecosystem keeps the pins moving."
        ),
    )
    def _image_pin(action: str = "check", write: bool = False, image: str = "", tag: str = "",
                   worktree_path: str = "") -> dict:
        return image_pin(action, write=write, image=image or None, tag=tag or None, worktree_path=worktree_path or None)


__all__ = ["image_pin", "register", "split_ref", "retag", "pinned", "pin_line", "find_unpinned", "resolve_digest"]
