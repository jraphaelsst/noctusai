import { describe, it, expect } from "vitest";
import { filterNavByPageStatus, stripNavRoutes, type StatusPagina } from "./page-status";

const st = (nome_pagina: string, status: StatusPagina["status"]): StatusPagina => ({
  id: nome_pagina,
  nome_pagina,
  status,
});
const it_ = (name: string, route: string) => ({ name, href: `/${route}`, route });

describe("filterNavByPageStatus nested", () => {
  const groups: any[] = [
    {
      key: "a",
      label: "A",
      items: [it_("A1", "a1")],
      groups: [
        { key: "a-b", label: "B", items: [it_("B1", "b1")], groups: [{ key: "a-b-c", label: "C", items: [it_("C1", "c1")] }] },
        { key: "a-d", label: "D", items: [it_("D1", "d1")] },
      ],
    },
    { key: "e", label: "E", items: [], groups: [{ key: "e-f", label: "F", items: [it_("F1", "f1")] }] },
  ];

  it("recurses, drops groups empty at any level, keeps DEV badge behaviour", () => {
    const status = [st("a1", "producao"), st("b1", "desenvolvimento"), st("c1", "desativado"), st("d1", "desativado"), st("f1", "desativado")];
    const out = filterNavByPageStatus(groups, status, "dev") as any[];
    expect(out.map((g) => g.key)).toEqual(["a"]);
    expect(out[0].groups.map((g: any) => g.key)).toEqual(["a-b"]);
    expect(out[0].groups[0].groups).toEqual([]);
    expect(out[0].groups[0].items[0].badge).toBe("DEV");
    expect(out[0].items[0]).not.toHaveProperty("route");
  });

  it("non-dev users do not see desenvolvimento items, groups vanish", () => {
    const status = [st("a1", "desativado"), st("b1", "desenvolvimento"), st("c1", "producao"), st("d1", "desativado"), st("f1", "producao")];
    const out = filterNavByPageStatus(groups, status, "member") as any[];
    expect(out.map((g) => g.key)).toEqual(["a", "e"]);
    expect(out[0].groups.map((g: any) => g.key)).toEqual(["a-b"]);
    expect(out[0].groups[0].items).toEqual([]);
    expect(out[0].groups[0].groups[0].items[0].name).toBe("C1");
  });

  it("flat groups produce no `groups` key (backward compat)", () => {
    const flat: any[] = [{ key: "x", label: "X", items: [it_("X1", "x1")] }];
    const out = filterNavByPageStatus(flat, [st("x1", "producao")], "member") as any[];
    expect(out[0]).not.toHaveProperty("groups");
  });

  it("stripNavRoutes removes route at every level", () => {
    const out = stripNavRoutes(groups);
    expect(out[0].groups[0].groups[0].items[0]).toEqual({ name: "C1", href: "/c1" });
  });
});
