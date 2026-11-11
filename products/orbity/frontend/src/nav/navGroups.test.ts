/**
 * Orbity sidebar on the seed module manifests (W3-O1): canonical group order,
 * every pre-W3-O1 nav URL + status_pagina key still present in exactly one place,
 * empty groups omitted, permission filtering (`filterNavByPageStatus`) unchanged.
 */
import { describe, it, expect } from "vitest";
import { MODULE_GROUP_ORDER, MODULE_GROUP_LABELS } from "@noctusai/lib/design-system";
import { filterNavByPageStatus } from "@noctusai/lib";

import { NAV_FALLBACK, NAV_GROUPS, STANDALONE_ITEMS } from "./navGroups";

/** Frozen pre-W3-O1 snapshot: href -> status_pagina key. Deep links and keys never move. */
const PRE_EXISTING: Record<string, string> = {
  "/": "dashboard",
  "/equipe": "equipe",
  "/financeiro": "financeiro",
  "/clientes": "clientes",
  "/funil": "funil",
  "/tarefas": "tarefas",
  "/agenda": "agenda",
  "/rotinas": "rotinas",
  "/conteudo": "conteudo",
  "/trafego": "trafego",
  "/automacao": "automacao",
  "/whatsapp": "whatsapp",
  "/relatorios": "relatorios",
};

const EXPECTED: Record<string, string[]> = {
  crm: ["/clientes", "/funil", "/agenda"],
  "redes-sociais": ["/conteudo", "/trafego", "/whatsapp", "/automacao"],
  erp: ["/financeiro", "/tarefas", "/rotinas", "/relatorios"],
  configuracoes: ["/equipe"],
};

describe("orbity nav", () => {
  it("groups follow the seed canonical order, with seed pt-BR labels", () => {
    const keys = NAV_GROUPS.map((g) => g.key);
    const rank = (k: string) => (MODULE_GROUP_ORDER as readonly string[]).indexOf(k);
    expect(keys.every((k) => rank(k) >= 0)).toBe(true);
    expect([...keys].sort((a, b) => rank(a) - rank(b))).toEqual(keys);
    for (const g of NAV_GROUPS) expect(g.label).toBe((MODULE_GROUP_LABELS as Record<string, string>)[g.key]);
  });

  it("each page lands in its group; groups without pages are omitted", () => {
    expect(NAV_GROUPS.map((g) => g.key)).toEqual(["crm", "redes-sociais", "erp", "configuracoes"]);
    for (const [key, hrefs] of Object.entries(EXPECTED)) {
      const g = NAV_GROUPS.find((x) => x.key === key)!;
      expect(g.items.map((i) => i.href).sort()).toEqual([...hrefs].sort());
    }
  });

  it("every pre-existing URL + status_pagina key survives, in exactly one place", () => {
    const all = [...NAV_GROUPS.flatMap((g) => g.items), ...STANDALONE_ITEMS];
    expect(all.length).toBe(Object.keys(PRE_EXISTING).length);
    for (const [href, route] of Object.entries(PRE_EXISTING)) {
      const hits = all.filter((i) => i.href === href);
      expect(hits).toHaveLength(1);
      expect(hits[0].route).toBe(route);
    }
  });

  it("dashboard is the standalone item", () => {
    expect(STANDALONE_ITEMS.map((i) => i.href)).toEqual(["/"]);
  });

  it("permission-hidden pages stay hidden (gate keys on the same route keys)", () => {
    const rows = ["clientes", "financeiro"].map((n) => ({ id: n, nome_pagina: n, status: "producao" as const }));
    const out = filterNavByPageStatus(NAV_GROUPS, rows, "member");
    const hrefs = out.flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs.sort()).toEqual(["/clientes", "/financeiro"]);
    expect(out.map((g) => g.key)).toEqual(["crm", "erp"]);
  });

  it("ungated fallback derives from the gated source and carries no route key", () => {
    expect(NAV_FALLBACK.map((g) => g.key)).toEqual(NAV_GROUPS.map((g) => g.key));
    for (const g of NAV_FALLBACK) for (const i of g.items) expect("route" in i).toBe(false);
  });
});
