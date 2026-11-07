#!/usr/bin/env node
/**
 * route_paths_scan.mjs — ts-morph extraction of route PATHS for the
 * core-host-retirement fitness test (`mcp/noctusai/tests/test_core_website_route_disjoint.py`).
 *
 * stdin : {"coreMain": "<abs main.tsx>", "websiteRoutes": "<abs website/lib/routes.ts>"}
 * stdout: {"core": [path,...], "website": [{"path": str, "dynamic": bool}, ...]}
 *   core    = every `path: '<literal>'` property in main.tsx (routes + publicRoutes).
 *   website = every `pt:`/`en:` property in routes.ts; a template literal
 *             (`/produtos/${slug}`) is reported as its static head, dynamic=true.
 */
import { Project, SyntaxKind } from "ts-morph";

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  const { coreMain, websiteRoutes } = JSON.parse(raw);
  const project = new Project({ skipAddingFilesFromTsConfig: true });

  const core = [];
  for (const prop of project.addSourceFileAtPath(coreMain).getDescendantsOfKind(SyntaxKind.PropertyAssignment)) {
    if (prop.getName() !== "path") continue;
    const init = prop.getInitializer();
    if (init && init.getKind() === SyntaxKind.StringLiteral) core.push(init.getLiteralValue());
  }

  const website = [];
  for (const prop of project.addSourceFileAtPath(websiteRoutes).getDescendantsOfKind(SyntaxKind.PropertyAssignment)) {
    if (!["pt", "en"].includes(prop.getName())) continue;
    const init = prop.getInitializer();
    if (!init) continue;
    const k = init.getKind();
    if (k === SyntaxKind.StringLiteral || k === SyntaxKind.NoSubstitutionTemplateLiteral) {
      website.push({ path: init.getLiteralValue(), dynamic: false });
    } else if (k === SyntaxKind.TemplateExpression) {
      website.push({ path: init.getHead().getLiteralText(), dynamic: true });
    }
  }
  process.stdout.write(JSON.stringify({ core, website }));
});
