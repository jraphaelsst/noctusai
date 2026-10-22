/** Julia v2 tier matrix (CONTRACT §0.4): the SERVER's `definition_scope` picks the tab set; role strings are not read. */
import { describe, expect, it } from "vitest";
import { studioTier, visibleTabsFor } from "../studioTabs";

const ids = (agent: Parameters<typeof visibleTabsFor>[0], isOrgAdmin: boolean, platformAdminHint = false) =>
  visibleTabsFor(agent, { isOrgAdmin, platformAdminHint }).map((t) => t.id);

describe("studioTier", () => {
  it("maps the server's definition_scope", () => {
    expect(studioTier({ definition_scope: "plataforma" })).toBe("plataforma");
    expect(studioTier({ definition_scope: "instancia" })).toBe("organizacao");
    expect(studioTier({ definition_scope: "org" })).toBe("legado");
    expect(studioTier({})).toBe("legado");
    expect(studioTier(undefined)).toBe("legado");
  });
});

describe("visibleTabsFor", () => {
  it("platform definition: every content tab for the platform admin", () => {
    const tabs = ids({ definition_scope: "plataforma", kind: "runtime" }, true, true);
    for (const t of ["prompt", "textos", "ferramentas", "decisoes", "qualificacao", "biblioteca", "especificacoes", "conformidade", "conversas", "versoes", "compilado"]) {
      expect(tabs).toContain(t);
    }
    expect(tabs).not.toContain("especificacoes-org");
  });

  it("org instance, org admin: specs form, controls, conversations — and NO prompt/ferramentas/qualificação/textos/decisões", () => {
    const tabs = ids({ definition_scope: "instancia", kind: "runtime" }, true, false);
    expect(tabs).toEqual(["visao-geral", "especificacoes-org", "controles", "conversas"]);
    for (const t of ["prompt", "ferramentas", "qualificacao", "textos", "decisoes", "compilado", "biblioteca", "conformidade"]) {
      expect(tabs).not.toContain(t);
    }
  });

  it("org instance, org member: none of the Studio content tabs", () => {
    expect(ids({ definition_scope: "instancia" }, false, false)).toEqual([]);
  });

  it("a platform admin acting inside an org instance may ask for the per-org compiled view", () => {
    expect(ids({ definition_scope: "instancia" }, true, true)).toContain("compilado");
  });

  it("legacy / org-scope agents keep the pre-v2 set and never see Julia tabs", () => {
    const tabs = ids({ definition_scope: "org", kind: "runtime" }, true, true);
    expect(tabs).toContain("clientes");
    for (const t of ["textos", "ferramentas", "decisoes", "qualificacao", "biblioteca", "especificacoes", "especificacoes-org", "controles", "conversas", "conformidade"]) {
      expect(tabs).not.toContain(t);
    }
  });
});
