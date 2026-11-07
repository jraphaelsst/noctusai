// Test-only bridge: ONE long-lived PGlite (PG16/WASM) answering line-delimited JSON on stdin/stdout, so the
// transition log's REAL adapter (`SupabaseTransitionLog`) can run the shared conformance suite against real
// Postgres. Run with cwd = mcp/noctusai/node (bare imports resolve from its node_modules), via
// `node --input-type=module -e <this file's text>`.
//   in : {"op":"exec"|"query","sql":"..."} | {"op":"rpc","fn":"schema.name","params":{...}}
//   out: {"ok":true,"data":...} | {"ok":false,"error":"...","code":"..."}
import readline from 'node:readline';

const { PGlite } = await import('@electric-sql/pglite');
const { vector } = await import('@electric-sql/pglite/vector');  // the Supabase stubs install pgvector
const db = new PGlite({ extensions: { vector } });
const out = (o) => process.stdout.write(JSON.stringify(o) + '\n');
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
      const res = await db.query(req.sql);
      out({ ok: true, data: res.rows });
    } else if (req.op === 'rpc') {
      const names = Object.keys(req.params || {});
      if (!/^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(req.fn) || names.some((n) => !/^p_[a-z0-9_]+$/.test(n))) {
        throw new Error(`refusing unsafe rpc name/params: ${req.fn}`);
      }
      // PostgREST-style named call; every argument travels as an untyped parameter (text) and is coerced
      // by Postgres to the function's declared type, exactly as PostgREST hands JSON scalars over.
      const args = names.map((n, i) => `${n} => $${i + 1}`).join(', ');
      const vals = names.map((n) => {
        const v = req.params[n];
        if (v === null || v === undefined) return null;
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
