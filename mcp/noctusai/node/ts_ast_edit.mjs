#!/usr/bin/env node
/**
 * ts_ast_edit.mjs — real ts-morph AST edits for `noctus.dev.ts_ast_*` MCP tools.
 *
 * Invoked by `mcp/noctusai/tools/noctus/dev/ts_ast_edit.py` as a child
 * process. Reads ONE JSON operation object from stdin, performs the AST
 * edit via ts-morph (the TypeScript Compiler API wrapper — see
 * `KB § PATTERNS/common/ast.md`), writes the result back to disk via
 * `SourceFile#saveSync()` (formatting-preserving), and prints ONE JSON
 * result object to stdout. Never touches stdout with anything but that
 * final JSON line — callers parse stdout as JSON.
 *
 * Supported ops (payload.op):
 *   - "rename_symbol": scope-aware rename of a top-level declared symbol
 *     (function / const / let / var / class / interface / type alias) and
 *     every reference to it *within this file*. This is the operation
 *     regex cannot do correctly: a same-spelled string literal, JSX prop
 *     value, comment, or unrelated identifier is left untouched because
 *     ts-morph resolves the identifier through the real binder, not text
 *     matching.
 *
 * Error contract: every failure path returns `{ok: false, status, error}`
 * on stdout with exit code 0 (the Python side distinguishes failure via
 * the `ok` field, not the process exit code — a genuine node crash /
 * unexpected exception still produces a non-zero exit + stderr, which the
 * Python side surfaces honestly as a "node_crashed" status). No silent
 * fallback to "did nothing" — an op that can't find its target reports a
 * typed error, it does not exit 0 with an empty edit.
 */
import { Project, SyntaxKind } from "ts-morph";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

/** Find the top-level named declaration node for `name` in `sourceFile`.
 * Covers the declaration shapes `outline_typescript.py` already enumerates
 * as "top-level structural declarations": function / class / interface /
 * type alias / variable (const|let|var). Returns the ts-morph node that
 * exposes `.rename()`, or `null` if nothing top-level matches. */
function findRenameableDeclaration(sourceFile, name) {
  const fn = sourceFile.getFunction(name);
  if (fn) return fn;

  const cls = sourceFile.getClass(name);
  if (cls) return cls;

  const iface = sourceFile.getInterface(name);
  if (iface) return iface;

  const typeAlias = sourceFile.getTypeAlias(name);
  if (typeAlias) return typeAlias;

  const varDecl = sourceFile.getVariableDeclaration(name);
  if (varDecl) return varDecl;

  return null;
}

function opRenameSymbol(payload) {
  const { path: filePath, oldName, newName } = payload;
  if (!filePath || !oldName || !newName) {
    return {
      ok: false,
      status: "bad_request",
      error: "rename_symbol requires path, oldName, newName",
    };
  }

  const project = new Project({ useInMemoryFileSystem: false });
  let sourceFile;
  try {
    sourceFile = project.addSourceFileAtPath(filePath);
  } catch (err) {
    return {
      ok: false,
      status: "parse_error",
      error: `could not load/parse ${filePath}: ${String(err && err.message ? err.message : err)}`,
    };
  }

  const declaration = findRenameableDeclaration(sourceFile, oldName);
  if (!declaration) {
    return {
      ok: false,
      status: "symbol_not_found",
      error: `no top-level function/class/interface/type/const/let/var named "${oldName}" in ${filePath}`,
    };
  }

  // getNameNode() exists on all the declaration kinds above (VariableDeclaration,
  // FunctionDeclaration, ClassDeclaration, InterfaceDeclaration, TypeAliasDeclaration).
  const nameNode = typeof declaration.getNameNode === "function" ? declaration.getNameNode() : declaration;
  if (!nameNode) {
    return {
      ok: false,
      status: "symbol_not_renameable",
      error: `"${oldName}" was found but exposes no renameable name node`,
    };
  }

  // findReferencesAsNodes() BEFORE the rename gives us an honest count of
  // what actually changed — the thing a regex `s/old/new/g` cannot report
  // truthfully (it would "succeed" even against 0 real references, or over-
  // match unrelated same-spelled text).
  let referenceNodes;
  try {
    referenceNodes = nameNode.findReferencesAsNodes();
  } catch (err) {
    return {
      ok: false,
      status: "reference_resolution_failed",
      error: `findReferencesAsNodes failed for "${oldName}": ${String(err && err.message ? err.message : err)}`,
    };
  }

  try {
    nameNode.rename(newName);
  } catch (err) {
    return {
      ok: false,
      status: "rename_failed",
      error: `ts-morph rename("${newName}") failed: ${String(err && err.message ? err.message : err)}`,
    };
  }

  sourceFile.saveSync();

  return {
    ok: true,
    status: "renamed",
    path: filePath,
    oldName,
    newName,
    referencesUpdated: referenceNodes.length, // excludes the declaration itself; declaration renamed unconditionally
    declarationKind: SyntaxKind[declaration.getKind()],
  };
}

const OPS = {
  rename_symbol: opRenameSymbol,
};

async function main() {
  const raw = await readStdin();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (err) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        status: "bad_payload",
        error: `stdin was not valid JSON: ${String(err && err.message ? err.message : err)}`,
      }),
    );
    return;
  }

  const op = OPS[payload.op];
  if (!op) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        status: "unknown_op",
        error: `unknown op "${payload.op}"; supported: ${Object.keys(OPS).join(", ")}`,
      }),
    );
    return;
  }

  const result = op(payload);
  process.stdout.write(JSON.stringify(result));
}

main().catch((err) => {
  // A genuine crash (bug in this script, ts-morph internal error, etc.) —
  // never swallow it. stderr + non-zero exit so the Python caller's
  // subprocess check surfaces it as "node_crashed", not a fake success.
  process.stderr.write(String(err && err.stack ? err.stack : err));
  process.exitCode = 1;
});
