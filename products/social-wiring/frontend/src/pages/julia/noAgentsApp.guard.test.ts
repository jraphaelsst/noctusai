/**
 * Guard (julia-line CONTRACT C3): the agents app is internal. SW users only provide business specifications, so no
 * Julia page/component may tell them to go configure anything there or link to the agents product.
 */
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOTS = [resolve(__dirname, "."), resolve(__dirname, "../../components/julia")];
// The Julia hooks carry user-facing sentences too (refusal messages) — scan them with the pages.
const HOOKS_DIR = resolve(__dirname, "../../hooks");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const FORBIDDEN: [string, RegExp][] = [
  ['"app de agentes"', /app de agentes/i],
  ["a link to the agents product", /agents_url|agentsUrl|urlConfigurarJulia|\/studio\/julia/i],
  ["the retired One Chat bot", /\bOne Chat\b/],
];

describe("Julia UI never points users at the agents app", () => {
  const hooks = readdirSync(HOOKS_DIR)
    .filter((n) => /^useJulia.*\.tsx?$/.test(n))
    .map((n) => join(HOOKS_DIR, n));
  // Owner 2026-11-05: the switch-on refusal (Julia not published / off in agents) is the ONE place that may link to agents.
  const LINK_ALLOWED = /(JuliaLigadaCard\.tsx|useJuliaRoteamento\.ts|Agente\.tsx)$/;
  const files = [...ROOTS.flatMap(walk), ...hooks].filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));
  it("scans the Julia hooks too", () => expect(files.some((f) => f.endsWith("useJuliaAgente.ts"))).toBe(true));

  it("scans a non-trivial set of files", () => expect(files.length).toBeGreaterThan(20));

  for (const [label, re] of FORBIDDEN) {
    it(`has no ${label}`, () => {
      const hits = files.filter(
        (f) => re.test(readFileSync(f, "utf8")) && !(label.startsWith("a link") && LINK_ALLOWED.test(f)),
      );
      expect(hits).toEqual([]);
    });
  }
});
