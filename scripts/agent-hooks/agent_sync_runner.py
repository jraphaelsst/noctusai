#!/usr/bin/env python3
"""Hook runner for Agent Packages sync (CONTRACT A5) — stdlib launcher over the noctusai toolkit.

  agent_sync_runner.py consumer --repo <consumer repo>
      agent_context_sync + agent_learnings_push (confirm=True). Used by the consumer `.githooks/pre-push`.
  agent_sync_runner.py publish --repo-root <noc tree> --keys a,b [--marker-dir <dir>]
      agent_package_publish (confirm=True) per key, plus any keys left in the marker. Used by noc's pre-push.

The toolkit is located via ``NOCTUS_HOME`` (else this file's own checkout). Contract A5: a failure is LOUD
(stderr) and leaves ``.agents-sync-pending``; a clean run clears it; the exit code is ALWAYS 0 — the hook
never blocks a push. The token is never printed (the tools redact it).
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def _toolkit_root() -> Path:
    home = os.environ.get("NOCTUS_HOME")
    return Path(home).expanduser() if home else Path(__file__).resolve().parents[2]


def _loud(lines: list[str]) -> None:
    print("", file=sys.stderr)
    for ln in lines:
        print(ln, file=sys.stderr)


def _consumer(repo: Path) -> int:
    from tools.noctus.dev import agent_sync_client as cl
    from tools.noctus.dev.agent_context_sync import agent_context_sync
    from tools.noctus.dev.agent_learnings_push import agent_learnings_push

    prior = cl.read_marker(repo)
    if prior:
        print("[agents-sync] retrying a previously failed sync (.agents-sync-pending)", file=sys.stderr)
    failures: list[dict] = []
    for step, fn in (("context_sync", agent_context_sync), ("learnings_push", agent_learnings_push)):
        try:
            res = fn(repo=str(repo), confirm=True)
        except Exception as exc:  # noqa: BLE001 — a hook must report, never crash the push
            res = {"ok": False, "status": "crashed", "error_code": "exception", "errors": [f"{type(exc).__name__}: {exc}"]}
            traceback.print_exc(file=sys.stderr)
        line = f"[agents-sync] {step}: {res.get('status')}"
        if res.get("summary"):
            line += f" {res['summary']}"
        if res.get("pushed"):
            line += f" {res['pushed']}"
        print(line, file=sys.stderr)
        for w in res.get("warnings", []) or []:
            print(f"[agents-sync]   warning: {w}", file=sys.stderr)
        if not res.get("ok"):
            failures.append({"step": step, "code": res.get("error_code"), "errors": res.get("errors", [])})
    if failures:
        cl.write_marker(repo, failures)
        _loud(["🔴 agents-sync FAILED — the push is NOT blocked; will retry on the next push (.agents-sync-pending):"]
              + [f"   - {f['step']}: {f['code']}: {'; '.join(f['errors'])}" for f in failures])
    else:
        if cl.clear_marker(repo):
            print("[agents-sync] pending marker cleared", file=sys.stderr)
    return 0


def _publish(repo_root: Path, keys: list[str], marker_dir: Path) -> int:
    from tools.noctus.dev import agent_sync_client as cl
    from tools.noctus.dev.agent_package_publish import agent_package_publish

    prior = cl.read_marker(marker_dir) or {}
    retry = [k for k in prior.get("keys", []) if isinstance(k, str)]
    todo = sorted(set(keys) | set(retry))
    if not todo:
        return 0
    failed: list[str] = []
    failures: list[dict] = []
    for key in todo:
        if not (repo_root / "products" / "agents" / "packages" / key / "package.yaml").is_file():
            print(f"[agents-publish] {key}: package no longer exists in this tree — skipped", file=sys.stderr)
            continue
        try:
            res = agent_package_publish(key=key, confirm=True, repo_root=str(repo_root))
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "status": "crashed", "error_code": "exception", "errors": [f"{type(exc).__name__}: {exc}"]}
            traceback.print_exc(file=sys.stderr)
        print(f"[agents-publish] {key}: {res.get('status')}", file=sys.stderr)
        for w in res.get("warnings", []) or []:
            _loud([f"🟠 agents-publish: {w}"])
        if not res.get("ok"):
            failed.append(key)
            failures.append({"step": f"publish:{key}", "code": res.get("error_code") or res.get("status"),
                             "errors": res.get("errors", [])})
    if failures:
        cl.write_marker(marker_dir, failures, {"keys": failed})
        _loud(["🔴 agents-publish FAILED — the push is NOT blocked; will retry on the next push (.agents-sync-pending):"]
              + [f"   - {f['step']}: {f['code']}: {'; '.join(f['errors'])}" for f in failures])
    elif cl.clear_marker(marker_dir):
        print("[agents-publish] pending marker cleared", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("consumer")
    c.add_argument("--repo", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--keys", default="")
    p.add_argument("--marker-dir", default=None)
    args = ap.parse_args(argv)
    try:
        sys.path.insert(0, str(_toolkit_root() / "mcp" / "noctusai"))
        # Use the SAME checkout's seed lib as the tools (not whatever copy the venv has installed):
        # tools and seed must match, or a new seed API used by a tool is missing at hook time.
        seed = _toolkit_root() / "seed" / "lib" / "backend"
        if seed.is_dir():
            sys.path.insert(0, str(seed))
        if args.mode == "consumer":
            return _consumer(Path(args.repo))
        keys = [k for k in args.keys.split(",") if k]
        root = Path(args.repo_root)
        return _publish(root, keys, Path(args.marker_dir) if args.marker_dir else root)
    except Exception as exc:  # noqa: BLE001 — import/setup failure: loud + marker, never block
        traceback.print_exc(file=sys.stderr)
        _loud([f"🔴 agents-sync: runner failed before syncing: {type(exc).__name__}: {exc}"])
        target = Path(args.repo if args.mode == "consumer" else (args.marker_dir or args.repo_root))
        try:
            import json
            from datetime import datetime, timezone
            (target / ".agents-sync-pending").write_text(json.dumps({
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "failures": [{"step": "runner", "errors": [f"{type(exc).__name__}: {exc}"]}],
                **({"keys": [k for k in getattr(args, "keys", "").split(",") if k]} if args.mode == "publish" else {}),
            }) + "\n", encoding="utf-8")
        except OSError:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
