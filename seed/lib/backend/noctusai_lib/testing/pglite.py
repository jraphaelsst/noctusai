"""A PostgREST-shaped client over a live PGlite (PG16/WASM): `client.rpc(name, params).execute().data`.

Lets a seed primitive's REAL Supabase adapter run its conformance suite against real Postgres in a unit run
(no network, no Supabase project): the adapter only ever calls `client.rpc(...)`, and this client answers
those calls by running the rendered SQL functions on a fresh PGlite. Promoted 2026-11-07 from
`tests/domain/transition_log/` (instance #2 was the event store) -- KB § PATTERNS/backend/event-store.md.

    from noctusai_lib.testing.pglite import PgliteClient, pglite_available

    if not pglite_available():
        pytest.skip("PGlite unavailable")            # a skip is not a pass -- say so in the reason
    db = PgliteClient("my_schema")                    # fresh database, Supabase stubs loaded
    db.exec(my_migration_sql)
    out = db.rpc("my_fn", {"p_x": 1}).execute().data  # PostgREST-style named call
    rows = db.query("SELECT ...")
    db.close()

Limits (by construction, not by accident): PGlite is ONE connection, so nothing here can interleave two
transactions -- a concurrency proof needs a real server (`noctusai_lib.testing.pgserver`). Only `.rpc()` is
modelled; table builders (`.table().select()`) are not.

Needs `node` on PATH and the toolkit's PGlite install (`mcp/noctusai/node/node_modules/@electric-sql`, the
same pin `noctus.dev.migration_replay` uses). `NOCTUS_PGLITE_NODE_DIR` overrides the node directory.
`NOC_REQUIRE_REAL_PG=1` (set in CI) turns "harness unavailable" from a skip into a failure.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Sequence

__all__ = ["BRIDGE_JS", "REQUIRE_REAL_PG_ENV", "PgliteClient", "PgliteError", "RealPgUnavailable", "node_dir",
           "pglite_available", "real_pg_required", "stubs_path"]

#: seed/lib/backend/noctusai_lib/testing/pglite.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]

#: The node side: ONE long-lived PGlite answering line-delimited JSON on stdin/stdout. Run with
#: cwd = the toolkit node dir (bare imports resolve from its node_modules) via `node --input-type=module -e`.
#:   in : {"op":"exec","sql":...} | {"op":"query","sql":...,"params":[...]} | {"op":"rpc","fn":"schema.name","params":{...}}
#:   out: {"ok":true,"data":...} | {"ok":false,"error":"...","code":"..."}
BRIDGE_JS = r"""
import readline from 'node:readline';

const { PGlite } = await import('@electric-sql/pglite');
const { vector } = await import('@electric-sql/pglite/vector');  // the Supabase stubs install pgvector
const db = new PGlite({ extensions: { vector } });
const out = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const typeCache = new Map();
async function argTypes(fn) {
  if (!typeCache.has(fn)) {
    const [schema, name] = fn.split('.');
    const res = await db.query(
      `SELECT unnest(p.proargnames) AS n, unnest(p.proargtypes::regtype[]::text[]) AS t
         FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
        WHERE ns.nspname = $1 AND p.proname = $2`, [schema, name]);
    typeCache.set(fn, Object.fromEntries(res.rows.map((r) => [r.n, r.t])));
  }
  return typeCache.get(fn);
}
const pgArray = (a) => '{' + a.map((x) => (x === null ? 'NULL'
  : '"' + String(x).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"')).join(',') + '}';
out({ ok: true, ready: true });

const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  let req;
  try { req = JSON.parse(line); } catch (e) { out({ ok: false, error: `bad request: ${e.message}` }); continue; }
  try {
    if (req.op === 'exec') {
      await db.exec(req.sql);
      out({ ok: true, data: null });
    } else if (req.op === 'query') {
      const res = await db.query(req.sql, req.params || []);
      out({ ok: true, data: res.rows });
    } else if (req.op === 'rpc') {
      const names = Object.keys(req.params || {});
      if (!/^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(req.fn) || names.some((n) => !/^p_[a-z0-9_]+$/.test(n))) {
        throw new Error(`refusing unsafe rpc name/params: ${req.fn}`);
      }
      // PostgREST-style named call; every argument travels as an untyped parameter (text) and is coerced
      // by Postgres to the function's declared type, exactly as PostgREST hands JSON scalars over. A JSON
      // array bound to a SQL array parameter (text[], uuid[]) becomes an array literal, as PostgREST does;
      // bound to json/jsonb it stays JSON.
      const types = await argTypes(req.fn);
      const args = names.map((n, i) => `${n} => $${i + 1}`).join(', ');
      const vals = names.map((n) => {
        const v = req.params[n];
        if (v === null || v === undefined) return null;
        if (Array.isArray(v) && (types[n] || '').endsWith('[]')) return pgArray(v);
        return typeof v === 'object' ? JSON.stringify(v) : String(v);
      });
      const res = await db.query(`SELECT ${req.fn}(${args}) AS r`, vals);
      out({ ok: true, data: res.rows[0].r });
    } else {
      out({ ok: false, error: `unknown op ${req.op}` });
    }
  } catch (e) {
    out({ ok: false, error: String(e.message || e), code: e.code || null });
  }
}
"""


def node_dir() -> Path:
    override = os.environ.get("NOCTUS_PGLITE_NODE_DIR")
    return Path(override) if override else _REPO_ROOT / "mcp" / "noctusai" / "node"


def stubs_path() -> Path:
    """The Supabase platform-surface stubs (roles, `auth`, `storage`, extensions) `migration_replay` loads too."""
    return node_dir() / "migration_replay" / "stubs.sql"


#: Set to ``1`` where a real-Postgres harness MUST run (CI's seed-backend-tests job). There a missing harness
#: is a broken setup, not a reason to skip: a skipped proof reads as green in a pytest summary.
REQUIRE_REAL_PG_ENV = "NOC_REQUIRE_REAL_PG"


class RealPgUnavailable(RuntimeError):
    """A real-Postgres test harness is missing while ``NOC_REQUIRE_REAL_PG=1`` says it must run."""


def real_pg_required() -> bool:
    return os.environ.get(REQUIRE_REAL_PG_ENV, "").strip() == "1"


def pglite_available() -> bool:
    """True when node + the toolkit's PGlite install are present.

    Under ``NOC_REQUIRE_REAL_PG=1`` a missing harness RAISES `RealPgUnavailable` instead of returning False, so
    every ``if not pglite_available(): pytest.skip(...)`` call site fails loudly in CI rather than skipping.
    """
    missing = [what for what, ok in (
        ("`node` on PATH", shutil.which("node") is not None),
        (f"{node_dir() / 'node_modules' / '@electric-sql'} (run `npm ci` in {node_dir()})",
         (node_dir() / "node_modules" / "@electric-sql").exists()),
        (f"{stubs_path()}", stubs_path().exists()),
    ) if not ok]
    if missing and real_pg_required():
        raise RealPgUnavailable(f"PGlite harness unavailable (missing: {', '.join(missing)}) while "
                                f"{REQUIRE_REAL_PG_ENV}=1 -- a skipped real-Postgres proof is not a pass")
    return not missing


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

    def __init__(self, schema: str, *, stubs: bool = True) -> None:
        if not pglite_available():
            raise RuntimeError("PGlite unavailable: needs `node` on PATH and mcp/noctusai/node/node_modules (npm ci)")
        self.schema = schema
        self._proc = subprocess.Popen(
            ["node", "--input-type=module", "-e", BRIDGE_JS],
            cwd=node_dir(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        hello = self._read()
        if not hello.get("ready"):
            raise RuntimeError(f"PGlite bridge did not start: {hello}")
        if stubs:
            self.exec(stubs_path().read_text(encoding="utf-8"))

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

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> list[dict]:
        return self._send({"op": "query", "sql": sql, "params": list(params or [])})

    def rpc(self, name: str, params: Optional[dict] = None) -> _Call:
        return _Call(self, f"{self.schema}.{name}", dict(params or {}))

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def __enter__(self) -> "PgliteClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
