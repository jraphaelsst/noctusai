#!/usr/bin/env node
/**
 * polling_budget_scan.mjs — ts-morph AST scan behind `check_polling_request_budget`
 * (`mcp/noctusai/tools/noctus/dev/polling_request_budget.py`), rule R4.
 *
 * A browser poll is a request per open tab per interval, forever. KB § PATTERNS/backend/polling-request-budget.md.
 *
 * Reads `{files: [absPath, ...]}` on stdin, prints
 * `{ok, results: {absPath: [{line, rule, construct}]}, errors: {absPath: message}}` where each result is an
 * UNDECLARED hit. Detects (AST, never text):
 *   - `refetchInterval:` (property or shorthand) whose value is not literal `false` / `undefined` / `0`;
 *   - any `setInterval(...)` / `window.setInterval(...)` call;
 *   - `refetchIntervalInBackground: true`  (rule `ts_background_poll`: needs `hidden=runs` in its declaration).
 * Declaration (same line or up to 3 lines above), valid only with a number followed by `/day`:
 *   `// poll-budget: <cadence>; <k> calls/tick; worst <N>/day per open tab; hidden=<paused|runs>`
 */
import { readFileSync } from "node:fs";
import { Node, Project, ScriptKind, SyntaxKind } from "ts-morph";

const DECL = /poll-budget:/;
const DAY = /\d[\d.,]*\s*[kKmM]?\s*\/day/;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function offValue(init) {
  if (!init) return false;
  const k = init.getKind();
  if (k === SyntaxKind.FalseKeyword) return true;
  if (k === SyntaxKind.NumericLiteral && Number(init.getText()) === 0) return true;
  if (k === SyntaxKind.Identifier && init.getText() === "undefined") return true;
  return false;
}

function scan(project, file) {
  const text = readFileSync(file, "utf8");
  const sf = project.createSourceFile(file, text, {
    overwrite: true,
    scriptKind: file.endsWith(".tsx") ? ScriptKind.TSX : ScriptKind.TS,
  });
  const lines = text.split("\n");
  const found = [];
  // The declaration lives in a comment: look at lines [line-3, line] for `poll-budget:` + a `<n>/day` figure.
  const declared = (line, extra) => {
    for (let l = Math.max(1, line - 3); l <= line; l++) {
      const t = lines[l - 1] || "";
      const i = t.indexOf("//") >= 0 ? t.indexOf("//") : t.indexOf("/*") >= 0 ? t.indexOf("/*") : t.indexOf("{/*");
      if (i < 0) continue;
      const c = t.slice(i);
      if (DECL.test(c) && DAY.test(c) && (!extra || extra.test(c))) return true;
    }
    return false;
  };
  const add = (node, rule, construct, extra) => {
    const line = node.getStartLineNumber();
    if (!declared(line, extra)) found.push({ line, rule, construct });
  };
  for (const p of sf.getDescendantsOfKind(SyntaxKind.PropertyAssignment)) {
    const name = p.getName();
    if (name === "refetchInterval" && !offValue(p.getInitializer())) {
      add(p, "ts_refetch_interval", `refetchInterval: ${(p.getInitializer()?.getText() || "").slice(0, 60).replace(/\s+/g, " ")}`);
    } else if (name === "refetchIntervalInBackground" && p.getInitializer()?.getKind() === SyntaxKind.TrueKeyword) {
      add(p, "ts_background_poll", "refetchIntervalInBackground: true", /hidden=runs/);
    }
  }
  for (const p of sf.getDescendantsOfKind(SyntaxKind.ShorthandPropertyAssignment)) {
    if (p.getName() === "refetchInterval") add(p, "ts_refetch_interval", "refetchInterval (shorthand)");
  }
  for (const c of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = c.getExpression();
    const name = Node.isIdentifier(callee)
      ? callee.getText()
      : Node.isPropertyAccessExpression(callee)
        ? callee.getName()
        : "";
    if (name === "setInterval") add(c, "ts_set_interval", "setInterval(...)");
  }
  project.removeSourceFile(sf);
  return found;
}

const req = JSON.parse(await readStdin());
const project = new Project({ skipAddingFilesFromTsConfig: true, useInMemoryFileSystem: true });
const results = {};
const errors = {};
for (const f of req.files || []) {
  try {
    const r = scan(project, f);
    if (r.length) results[f] = r;
  } catch (e) {
    errors[f] = String(e && e.message ? e.message : e);
  }
}
process.stdout.write(JSON.stringify({ ok: true, results, errors }));
