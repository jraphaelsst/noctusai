#!/usr/bin/env node
/**
 * motion_import_scan.mjs — ts-morph AST scan behind `check_motion_import_boundary`
 * (`mcp/noctusai/tools/noctus/dev/compliance.py`).
 *
 * Motion (npm `motion`, formerly `framer-motion`) reaches the fleet ONLY through
 * `@noctusai/lib/marketing` (its `MotionProvider` hard-codes reduced-motion +
 * LazyMotion strict). Any other import is a bypass of that seam.
 * KB § PATTERNS/frontend/marketing-organs-and-motion.md.
 *
 * Reads `{files: [absPath, ...]}` on stdin, prints
 * `{ok, results: {absPath: [{line, spec, kind}]}, errors: {absPath: message}}`.
 * Detects (AST, never text): `import … from`, `import "x"`, `export … from`,
 * `import("x")`, `require("x")`.
 * Escape (same line or up to 3 lines above): `// noc-allow: motion-import — <why>`.
 */
import { readFileSync } from "node:fs";
import { Node, Project, ScriptKind, SyntaxKind } from "ts-morph";

const BANNED = /^(motion|framer-motion)(\/.*)?$/;
const ALLOW = /noc-allow:\s*motion-import\s*(?:—|–|-|:)\s*\S/;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function scan(project, file) {
  const text = readFileSync(file, "utf8");
  const sf = project.createSourceFile(file, text, {
    overwrite: true,
    scriptKind: file.endsWith(".tsx") ? ScriptKind.TSX : ScriptKind.TS,
  });
  const lines = text.split("\n");
  const found = [];
  const add = (node, spec, kind) => {
    if (!BANNED.test(spec)) return;
    const line = node.getStartLineNumber();
    for (let l = Math.max(1, line - 3); l <= line; l++) {
      if (ALLOW.test(lines[l - 1] || "")) return;
    }
    found.push({ line, spec, kind });
  };
  // Template placeholders (`from {{X}}`) yield a non-literal specifier; ts-morph's
  // getModuleSpecifierValue() throws on those — read the compiler node instead.
  const specOf = (d) => {
    const m = d.compilerNode.moduleSpecifier;
    return m && m.kind === SyntaxKind.StringLiteral ? m.text : null;
  };
  const lit = (n) => (n && Node.isStringLiteral(n) ? n.getLiteralValue() : null);
  for (const d of sf.getImportDeclarations()) {
    const s = specOf(d);
    if (s) add(d, s, "import");
  }
  for (const d of sf.getExportDeclarations()) {
    const s = specOf(d);
    if (s) add(d, s, "export-from");
  }
  for (const c of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = c.getExpression();
    const isDyn = callee.getKind() === SyntaxKind.ImportKeyword;
    const isReq = Node.isIdentifier(callee) && callee.getText() === "require";
    if (!isDyn && !isReq) continue;
    const s = lit(c.getArguments()[0]);
    if (s) add(c, s, isDyn ? "dynamic-import" : "require");
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
