/**
 * Sidebar nav — the Julia group (owner decision 2026-10-13) and the derived
 * ungated fallback.
 */
import { describe, it, expect } from "vitest";

import { NAV_FALLBACK, NAV_GROUPS } from "./navGroups";
import { JULIA_LABEL, JULIA_NAV_KEY, JULIA_PAGES } from "./julia";

type AnyGroup = { key: string; label: string; items: any[]; groups?: AnyGroup[] };

function allItems(groups: AnyGroup[]): any[] {
  return groups.flatMap((g) => [...g.items, ...allItems(g.groups ?? [])]);
}

const byKey = (groups: AnyGroup[], key: string) => groups.find((g) => g.key === key);

describe.each([
  ["NAV_GROUPS", NAV_GROUPS as AnyGroup[]],
  ["NAV_FALLBACK", NAV_FALLBACK as AnyGroup[]],
])("%s", (_name, groups) => {
  it("Conexões no longer lists WhatsApp", () => {
    const conexoes = byKey(groups, "conexoes")!;
    expect(conexoes).toBeTruthy();
    expect(conexoes.items.map((i) => i.name)).toEqual(["Marcas", "Monitor", "YouTube", "Meta", "n8n"]);
  });

  it("Roteiros sits under Core Studio › Headlines, and only there (owner request 2026-10-17)", () => {
    const all = (gs: AnyGroup[]): AnyGroup[] => gs.flatMap((g) => [g, ...all(g.groups ?? [])]);
    const headlines = all(groups).find((g) => g.key === "media-creation-headlines")!;
    expect(headlines.items.map((i) => i.href)).toContain("/media-creation/roteiros");
    expect(allItems(groups).filter((i) => i.href === "/media-creation/roteiros")).toHaveLength(1);
  });

  it("nothing in the nav links to the retired /whatsapp-chat route", () => {
    expect(allItems(groups).some((i) => i.href === "/whatsapp-chat")).toBe(false);
  });

  it("has the Julia group directly after Principal, with Painel + Conversas + Configurações", () => {
    const keys = groups.map((g) => g.key);
    expect(keys.indexOf(JULIA_NAV_KEY)).toBe(keys.indexOf("principal") + 1);
    const julia = byKey(groups, JULIA_NAV_KEY)!;
    expect(julia.label).toBe(JULIA_LABEL);
    // The group IS JULIA_PAGES, in order (derived -- each Julia wave adds one JULIA_PAGES entry, never edits this test).
    expect(julia.items.map((i) => [i.name, i.href])).toEqual(Object.values(JULIA_PAGES).map((p) => [p.name, p.href]));
    // The first three are fixed (page 0 + the original group).
    expect(julia.items.slice(0, 3).map((i) => [i.name, i.href])).toEqual([
      ["Painel", "/julia/painel"],
      ["Conversas", "/julia/conversas"],
      ["Configurações", "/julia/configuracoes"],
    ]);
  });
});

describe("route keys", () => {
  it("every Julia item is gated by its own julia_* status_pagina key (one migration row per page)", () => {
    const julia = byKey(NAV_GROUPS as AnyGroup[], JULIA_NAV_KEY)!;
    const routes = julia.items.map((i) => (i as { route?: string }).route);
    expect(routes).toEqual(Object.values(JULIA_PAGES).map((p) => p.route));
    expect(routes.every((r) => typeof r === "string" && r.startsWith("julia_"))).toBe(true);
    expect(new Set(routes).size).toBe(routes.length);
  });

  it("the fallback is NAV_GROUPS minus every route key (derived, cannot drift)", () => {
    expect(allItems(NAV_FALLBACK as AnyGroup[]).some((i) => "route" in i)).toBe(false);
    expect(allItems(NAV_FALLBACK as AnyGroup[]).map((i) => i.href)).toEqual(
      allItems(NAV_GROUPS as AnyGroup[]).map((i) => i.href),
    );
  });

  it("the Julia group is built from JULIA_PAGES (one list to extend)", () => {
    const julia = byKey(NAV_GROUPS as AnyGroup[], JULIA_NAV_KEY)!;
    expect(julia.items.map((i) => i.href)).toEqual(Object.values(JULIA_PAGES).map((p) => p.href));
  });
});
