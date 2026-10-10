// Statement splitter + transaction-control detection for noctus.dev.migration_replay.
//
// Respects '...' and "..." quoting (with doubled-quote escapes), $tag$...$tag$
// dollar quoting, -- line comments and /* */ block comments. Never a SQL parser:
// it only has to find top-level `;` boundaries, which is all statement-level
// replay needs.

const DOLLAR_TAG = /^\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$/;

export function splitSql(sql) {
  const out = [];
  let cur = '';
  let i = 0;
  while (i < sql.length) {
    const c = sql[i];
    const two = sql.slice(i, i + 2);
    if (two === '--') {
      const j = sql.indexOf('\n', i);
      const end = j < 0 ? sql.length : j;
      cur += sql.slice(i, end);
      i = end;
      continue;
    }
    if (two === '/*') {
      const j = sql.indexOf('*/', i + 2);
      const end = j < 0 ? sql.length : j + 2;
      cur += sql.slice(i, end);
      i = end;
      continue;
    }
    if (c === "'" || c === '"') {
      let j = i + 1;
      while (j < sql.length) {
        if (sql[j] === c) {
          if (sql[j + 1] === c) { j += 2; continue; }
          break;
        }
        j++;
      }
      cur += sql.slice(i, j + 1);
      i = j + 1;
      continue;
    }
    if (c === '$') {
      const m = DOLLAR_TAG.exec(sql.slice(i));
      if (m) {
        const j = sql.indexOf(m[0], i + m[0].length);
        const end = j < 0 ? sql.length : j + m[0].length;
        cur += sql.slice(i, end);
        i = end;
        continue;
      }
    }
    if (c === ';') {
      if (hasCode(cur)) out.push(cur.trim());
      cur = '';
      i++;
      continue;
    }
    cur += c;
    i++;
  }
  if (hasCode(cur)) out.push(cur.trim());
  return out;
}

export function stripComments(stmt) {
  return stmt.replace(/\/\*[\s\S]*?\*\//g, '').replace(/--.*$/gm, '');
}

function hasCode(stmt) {
  return stripComments(stmt).trim().length > 0;
}

const TX_CONTROL = /^\s*(BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK|END)(\s+(WORK|TRANSACTION|ISOLATION\s+LEVEL[\s\S]*|READ\s+(ONLY|WRITE)))?\s*$/i;

// A statement-level replay must SKIP transaction control. The check runs on the
// comment-stripped text: a file reading "-- note\nBEGIN" otherwise slips past a
// naive ^BEGIN test, opens a transaction, and the next error's ROLLBACK silently
// wipes every object created since — the 2026-10-10 measurement read 2749 false
// failures in social-wiring that way.
export function isTransactionControl(stmt) {
  return TX_CONTROL.test(stripComments(stmt).trim());
}
