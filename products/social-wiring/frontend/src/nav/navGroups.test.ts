/**
 * Sidebar nav — the Lais group (owner decision 2026-10-13) and the derived
 * ungated fallback.
 */
import { describe, it, expect } from "vitest";

import { NAV_FALLBACK, NAV_GROUPS } from "./navGroups";
import { LAIS_LABEL, LAIS_NAV_KEY, LAIS_PAGES } from "./lais";

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

  it("nothing in the nav links to the retired /whatsapp-chat route", () => {
    expect(allItems(groups).some((i) => i.href === "/whatsapp-chat")).toBe(false);
  });

  it("has the Lais group directly after Principal, with Conversas + Configurações + Agente", () => {
    const keys = groups.map((g) => g.key);
    expect(keys.indexOf(LAIS_NAV_KEY)).toBe(keys.indexOf("principal") + 1);
    const lais = byKey(groups, LAIS_NAV_KEY)!;
    expect(lais.label).toBe(LAIS_LABEL);
    expect(lais.items.map((i) => [i.name, i.href])).toEqual([
      ["Conversas", "/lais/conversas"],
      ["Configurações", "/lais/configuracoes"],
      ["Agente", "/lais/agente"],
      ["Conhecimento", "/lais/conhecimento"],
    ]);
  });
});

describe("route keys", () => {
  it("Lais items are gated by lais_conversas / lais_configuracoes / lais_agente / lais_conhecimento (migrations 252, 259)", () => {
    const lais = byKey(NAV_GROUPS as AnyGroup[], LAIS_NAV_KEY)!;
    expect(lais.items.map((i) => i.route)).toEqual(["lais_conversas", "lais_configuracoes", "lais_agente", "lais_conhecimento"]);
  });

  it("the fallback is NAV_GROUPS minus every route key (derived, cannot drift)", () => {
    expect(allItems(NAV_FALLBACK as AnyGroup[]).some((i) => "route" in i)).toBe(false);
    expect(allItems(NAV_FALLBACK as AnyGroup[]).map((i) => i.href)).toEqual(
      allItems(NAV_GROUPS as AnyGroup[]).map((i) => i.href),
    );
  });

  it("the Lais group is built from LAIS_PAGES (one list to extend)", () => {
    const lais = byKey(NAV_GROUPS as AnyGroup[], LAIS_NAV_KEY)!;
    expect(lais.items.map((i) => i.href)).toEqual(Object.values(LAIS_PAGES).map((p) => p.href));
  });
});
