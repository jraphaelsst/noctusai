/**
 * A page that owns sub-routes (seed `SectionTabsPage` / `FinanceRoutedPage`, one URL per tab) must be registered
 * with a trailing `/*`, or every tab URL is a 404.
 *
 * Regression (2026-11-19): Settings moved to `/configuracoes/<tab>` on 2026-10-26, but `App.tsx` kept the exact
 * `/configuracoes`, so the whole Configurações area 404'd on prod for ~3 weeks. `Settings.test.tsx` mounts its own
 * `/configuracoes/*` route, so it could never see this; only the real route table can. Read with the TypeScript AST,
 * never a regex.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname);
const ROUTED_TAB_ORGANS = /\b(SectionTabsPage|FinanceRoutedPage)\b/;

function parse(file: string): ts.SourceFile {
  return ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}

/** `const X = lazyWithReload(() => import("@/pages/Y"))` -> X -> absolute path of Y. */
function lazyPageModules(sf: ts.SourceFile): Map<string, string> {
  const out = new Map<string, string>();
  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      let spec: string | undefined;
      const find = (n: ts.Node): void => {
        if (ts.isCallExpression(n) && n.expression.kind === ts.SyntaxKind.ImportKeyword) {
          const arg = n.arguments[0];
          if (arg && ts.isStringLiteral(arg)) spec = arg.text;
        }
        ts.forEachChild(n, find);
      };
      find(node.initializer);
      if (spec?.startsWith("@/")) out.set(node.name.text, resolve(SRC, spec.slice(2)));
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

/** Every `{ path: "<literal>", component: <Identifier> }` object in the file. */
function routeObjects(sf: ts.SourceFile): Array<{ path: string; component: string }> {
  const out: Array<{ path: string; component: string }> = [];
  const visit = (node: ts.Node): void => {
    if (ts.isObjectLiteralExpression(node)) {
      let path: string | undefined;
      let component: string | undefined;
      for (const p of node.properties) {
        if (!ts.isPropertyAssignment(p) || !ts.isIdentifier(p.name)) continue;
        if (p.name.text === "path" && ts.isStringLiteralLike(p.initializer)) path = p.initializer.text;
        if (p.name.text === "component" && ts.isIdentifier(p.initializer)) component = p.initializer.text;
      }
      if (path !== undefined && component !== undefined) out.push({ path, component });
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

function readModule(base: string): string | undefined {
  for (const ext of [".tsx", ".ts", "/index.tsx", "/index.ts"]) {
    try {
      return readFileSync(base + ext, "utf8");
    } catch {
      // try the next extension; a page that resolves nowhere is reported by the assertion below
    }
  }
  return undefined;
}

describe("App route table", () => {
  const app = parse(resolve(SRC, "App.tsx"));
  const modules = lazyPageModules(app);
  const routes = routeObjects(app);

  const routedTabPages = [...modules.entries()].filter(([, file]) => ROUTED_TAB_ORGANS.test(readModule(file) ?? ""));

  it("finds the pages that own sub-routes (the check is not vacuous)", () => {
    expect(routedTabPages.map(([name]) => name)).toEqual(expect.arrayContaining(["Settings", "Financeiro"]));
  });

  it.each(routedTabPages.map(([name]) => name))("%s is registered with a trailing /*", (name) => {
    const mine = routes.filter((r) => r.component === name);
    expect(mine.length).toBeGreaterThan(0);
    for (const r of mine) expect(r.path.endsWith("/*"), `${name} at "${r.path}"`).toBe(true);
  });
});
