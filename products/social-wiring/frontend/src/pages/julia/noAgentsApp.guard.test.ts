/**
 * Guard (julia-line CONTRACT C3): the agents app is internal. SW users only provide business specifications, so no
 * Julia page/component may tell them to go configure anything there or link to the agents product.
 */
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOTS = [resolve(__dirname, "."), resolve(__dirname, "../../components/julia")];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const FORBIDDEN: [string, RegExp][] = [
  ['"app de agentes"', /app de agentes/i],
  ["a link to the agents product", /agents_url|agentsUrl|\/studio\/julia/i],
];

describe("Julia UI never points users at the agents app", () => {
  const files = ROOTS.flatMap(walk).filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));

  it("scans a non-trivial set of files", () => expect(files.length).toBeGreaterThan(20));

  for (const [label, re] of FORBIDDEN) {
    it(`has no ${label}`, () => {
      const hits = files.filter((f) => re.test(readFileSync(f, "utf8")));
      expect(hits).toEqual([]);
    });
  }
});
