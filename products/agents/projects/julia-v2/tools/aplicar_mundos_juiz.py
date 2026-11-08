"""Write the repo mirror's per-case WORLD (``roteiro``) onto the judge cases in the Studio (PATCH), dry-run by default.

    python aplicar_mundos_juiz.py [--confirm]        # needs NOCTUS_AGENTS_URL + NOCTUS_AGENTS_CONTENT_TOKEN (~/.config/noctus/agents.env)

Only valid AFTER the agents release that accepts ``roteiro`` on a ``comportamento`` case (before it, the store answers 400).
Prints slug and verdict only. Idempotent: a case whose stored world already equals the mirror is left alone.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

EVALS = Path(__file__).resolve().parent.parent / "content-v3" / "evals"


def _env() -> tuple[str, str]:
    for linha in (Path.home() / ".config/noctus/agents.env").read_text().splitlines():
        k, _, v = linha.partition("=")
        os.environ.setdefault(k.strip(), v.strip())
    return os.environ["NOCTUS_AGENTS_URL"].rstrip("/"), os.environ["NOCTUS_AGENTS_CONTENT_TOKEN"]


def _chamar(url: str, token: str, metodo: str, corpo: dict | None = None):
    req = urllib.request.Request(
        url, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    base, token = _env()
    cases = {c["slug"]: c for c in _chamar(f"{base}/api/studio/agents/julia/evals/cases", token, "GET")["items"] if c.get("suite") == "comportamento"}
    for f in sorted(EVALS.glob("*.json")):
        d = json.loads(f.read_text())
        if not (isinstance(d, dict) and d.get("roteiro") and d.get("slug") in cases):
            continue
        caso = cases[d["slug"]]
        if caso.get("roteiro") == d["roteiro"]:
            print(d["slug"], "ja igual")
        elif not a.confirm:
            print(d["slug"], "atualizaria (dry-run)")
        else:
            _chamar(f"{base}/api/studio/agents/julia/evals/cases/{caso['id']}", token, "PATCH", {"roteiro": d["roteiro"]})
            print(d["slug"], "atualizado")


if __name__ == "__main__":
    main()
