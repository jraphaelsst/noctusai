#!/usr/bin/env node
/**
 * module_page_keys_scan.mjs — ts-morph AST scan behind `check_module_page_status_rows`
 * (`mcp/noctusai/tools/noctus/dev/compliance.py`).
 *
 * Reads `{files: [absPath, ...]}` on stdin, prints
 * `{ok, results: {absPath: [{line, key}]}, errors: {absPath: message}}`.
 * For every `defineModule({ ..., items: [...] })` call (the FE half of a `ModuleSpec`,
 * `seed/lib/frontend/src/modules/define.ts`) it lists each declared `pageKey` string literal, children
 * included. A page key that is not a string literal cannot be checked statically and is skipped.
 * Escape (same line or up to 3 lines above): `// noc-allow: module-page-status-row — <why>`.
 * KB § PATTERNS/frontend/status-pagina-dev-visibility.md.
 */
import { readFileSync } from "node:fs";
import { Node, Project, ScriptKind, SyntaxKind } from "ts-morph";

const ALLOW = /noc-allow:\s*module-page-status-row\s*(?:—|–|-|:)\s*\S/;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function prop(obj, name) {
  const p = obj.getProperty(name);
  return p && Node.isPropertyAssignment(p) ? p.getInitializer() : undefined;
}

function collect(items, lines, found) {
  if (!items || !Node.isArrayLiteralExpression(items)) return;
  for (const el of items.getElements()) {
    if (!Node.isObjectLiteralExpression(el)) continue;
    const pk = prop(el, "pageKey");
    if (pk && (Node.isStringLiteral(pk) || Node.isNoSubstitutionTemplateLiteral(pk))) {
      const line = pk.getStartLineNumber();
      let allowed = false;
      for (let l = Math.max(1, line - 3); l <= line; l++) if (ALLOW.test(lines[l - 1] || "")) allowed = true;
      if (!allowed) found.push({ line, key: pk.getLiteralValue() });
    }
    collect(prop(el, "children"), lines, found);
  }
}

function scan(project, file) {
  const text = readFileSync(file, "utf8");
  const sf = project.createSourceFile(file, text, {
    overwrite: true,
    scriptKind: file.endsWith(".tsx") ? ScriptKind.TSX : ScriptKind.TS,
  });
  const lines = text.split("\n");
  const found = [];
  for (const c of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = c.getExpression();
    if (!Node.isIdentifier(callee) || callee.getText() !== "defineModule") continue;
    const arg = c.getArguments()[0];
    if (arg && Node.isObjectLiteralExpression(arg)) collect(prop(arg, "items"), lines, found);
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
