// noctus.dev.migration_replay — node half. Replays an ordered list of migration files
// on a FRESH PGlite and reports every failure as JSON on stdout. The Python half
// (mcp/noctusai/tools/noctus/dev/migration_replay.py) chooses the steps, compares
// against the per-product residue baseline and owns the verdict.
//
// stdin: {"stubs": "<sql>", "steps": [{"product", "file", "sql", "mode": "statements"|"file", "twice": bool}]}
// stdout: {"ok": true, "pglite": "<version>", "elapsed_ms", "steps": [{"product","file","mode","statements","failures":[...]}]}
//         {"ok": false, "error": "<why the harness could not measure>"}   (⇒ inconclusive, never green)
//
// mode "statements" — history: each top-level statement in autocommit, in order;
//   transaction control is skipped (comment-aware, split_sql.mjs) so one failure
//   never rolls back its neighbours. Mirrors "what does this chain leave behind".
// mode "file" — a new/changed migration: the WHOLE file in one simple-query call,
//   exactly how migrate_product sends it to Supabase (implicit transaction, atomic).
//   With twice=true it is sent a second time: that failure is an idempotency failure.
import fs from 'node:fs';
import { splitSql, isTransactionControl } from './split_sql.mjs';

const STRIP_EXTENSIONS = /CREATE\s+EXTENSION\s+(IF\s+NOT\s+EXISTS\s+)?"?(pg_net|pg_cron)"?[^;]*;/gi;

function fail(error) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(error) }));
  process.exit(0);
}

let input;
try {
  input = JSON.parse(fs.readFileSync(0, 'utf8'));
} catch (e) {
  fail(`bad input: ${e.message}`);
}

let PGlite, pg_trgm, vector, version;
try {
  ({ PGlite } = await import('@electric-sql/pglite'));
  ({ pg_trgm } = await import('@electric-sql/pglite/contrib/pg_trgm'));
  ({ vector } = await import('@electric-sql/pglite/vector'));
  version = JSON.parse(fs.readFileSync(new URL('../node_modules/@electric-sql/pglite/package.json', import.meta.url), 'utf8')).version;
} catch (e) {
  fail(`pglite not loadable (run \`npm ci\` in mcp/noctusai/node): ${e.message}`);
}

const started = Date.now();
let db;
try {
  db = new PGlite({ extensions: { pg_trgm, vector } });
  await db.exec(input.stubs);
} catch (e) {
  fail(`stubs did not load: ${e.message}`);
}

// Each migration starts a fresh Supabase session. PGlite's RESET ALL lands on
// search_path=pg_catalog, so pin Supabase's role default explicitly.
const SESSION_RESET = `RESET ALL; SET search_path TO "$user", public, extensions;`;

const errOf = (e) => ({ error: String(e.message || e).slice(0, 400), code: e.code || null });

async function run(sql) {
  try {
    await db.exec(sql);
    return null;
  } catch (e) {
    try { await db.exec('ROLLBACK'); } catch { /* no open transaction */ }
    return errOf(e);
  }
}

async function statements(sql, phase, failures) {
  const stmts = splitSql(sql);
  let n = 0;
  for (const [i, s] of stmts.entries()) {
    if (isTransactionControl(s)) continue;
    n++;
    const err = await run(s);
    if (err) failures.push({ phase, stmt_index: i, stmt_head: s.replace(/\s+/g, ' ').slice(0, 160), ...err });
  }
  return n;
}

const out = [];
try {
  for (const step of input.steps) {
    await run(SESSION_RESET);
    const sql = step.sql.replace(STRIP_EXTENSIONS, '');
    const failures = [];
    let count = 0;
    if (step.mode === 'file') {
      const err = await run(sql);
      if (err) {
        failures.push({ phase: 'apply', stmt_index: null, stmt_head: null, ...err });
        // keep the chain's state honest for later steps: land what can land
        await run(SESSION_RESET);
        count = await statements(sql, 'fallback', []);
      } else if (step.twice) {
        await run(SESSION_RESET);
        const again = await run(sql);
        if (again) failures.push({ phase: 'reapply', stmt_index: null, stmt_head: null, ...again });
      }
    } else {
      count = await statements(sql, 'apply', failures);
    }
    out.push({ product: step.product, file: step.file, mode: step.mode, statements: count, failures });
  }
} catch (e) {
  fail(`harness crashed mid-replay: ${e.message}`);
}
await db.close();
process.stdout.write(JSON.stringify({ ok: true, pglite: version, elapsed_ms: Date.now() - started, steps: out }));
