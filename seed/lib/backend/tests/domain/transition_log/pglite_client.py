"""A PostgREST-shaped client over a live PGlite (`pglite_bridge.mjs`): `client.rpc(name, params).execute().data`.

Lets the REAL transition-log adapter run the shared conformance suite against real Postgres in a unit run
(no network, no Supabase project). Only `.rpc()` is modelled -- the adapter uses nothing else.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
BRIDGE = Path(__file__).with_name("pglite_bridge.mjs")
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"


def available() -> bool:
    return shutil.which("node") is not None and (NODE_DIR / "node_modules" / "@electric-sql").exists() and STUBS.exists()


class PgliteError(RuntimeError):
    def __init__(self, message: str, code: Optional[str]) -> None:
        super().__init__(message)
        self.code = code


class _Call:
    def __init__(self, client: "PgliteClient", fn: str, params: dict) -> None:
        self._client, self._fn, self._params = client, fn, params

    def execute(self) -> Any:
        return SimpleNamespace(data=self._client._send({"op": "rpc", "fn": self._fn, "params": self._params}), count=None)


class PgliteClient:
    """One fresh database per instance (Supabase stubs loaded). `schema` scopes `.rpc()` like `client.schema(s)`."""

    def __init__(self, schema: str) -> None:
        self.schema = schema
        self._proc = subprocess.Popen(
            ["node", "--input-type=module", "-e", BRIDGE.read_text(encoding="utf-8")],
            cwd=NODE_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        hello = self._read()
        if not hello.get("ready"):
            raise RuntimeError(f"PGlite bridge did not start: {hello}")
        self.exec(STUBS.read_text(encoding="utf-8"))

    def _read(self) -> dict:
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"PGlite bridge died: {self._proc.stderr.read()[-800:]}")
        return json.loads(line)

    def _send(self, req: dict) -> Any:
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        resp = self._read()
        if not resp.get("ok"):
            raise PgliteError(resp.get("error", "?"), resp.get("code"))
        return resp.get("data")

    def exec(self, sql: str) -> None:
        self._send({"op": "exec", "sql": sql})

    def query(self, sql: str) -> list[dict]:
        return self._send({"op": "query", "sql": sql})

    def rpc(self, name: str, params: Optional[dict] = None) -> _Call:
        return _Call(self, f"{self.schema}.{name}", dict(params or {}))

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
