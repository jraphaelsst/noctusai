/**
 * Sidebar nav on the seed module manifests (W3-S1): canonical group order,
 * every pre-W3-S1 nav URL still present and in exactly ONE group, every nav
 * URL still routed in App.tsx, Julia + the derived ungated fallback.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect } from "vitest";
import { MODULE_GROUP_ORDER, MODULE_GROUP_LABELS } from "@noctusai/lib/design-system";

import { NAV_FALLBACK, NAV_GROUPS, STANDALONE_ITEMS } from "./navGroups";
import { JULIA_LABEL, JULIA_PAGES } from "./julia";

type AnyGroup = { key: string; label: string; items: any[]; groups?: AnyGroup[] };

function allItems(groups: AnyGroup[]): any[] {
  return groups.flatMap((g) => [...g.items, ...allItems(g.groups ?? [])]);
}
const allGroups = (gs: AnyGroup[]): AnyGroup[] => gs.flatMap((g) => [g, ...allGroups(g.groups ?? [])]);
const byKey = (groups: AnyGroup[], key: string) => allGroups(groups).find((g) => g.key === key);

/** Every href the sidebar listed before W3-S1 (frozen snapshot: deep links never move). */
const PRE_EXISTING_HREFS = [
  "/",
  "/agendamentos",
  "/agentes-financeiros",
  "/atendimento-blocos",
  "/campanhas",
  "/certidoes",
  "/clientes",
  "/clientes/revisao",
  "/condominios",
  "/configuracoes",
  "/contatos",
  "/custos",
  "/edicao-fotos",
  "/edicao-fotos/configuracoes",
  "/edicao-fotos/curadores",
  "/edicao-fotos/guias",
  "/edicao-fotos/modelos",
  "/edicao-fotos/novo",
  "/edicao-fotos/painel",
  "/edicao-fotos/processamento",
  "/edicao-fotos/referencias",
  "/edicao-fotos/regras",
  "/email-marketing/campanhas",
  "/email-marketing/configuracao",
  "/email-marketing/listas",
  "/email-marketing/membros",
  "/email-marketing/templates",
  "/email",
  "/email/automacoes",
  "/email/campanhas",
  "/email/contatos",
  "/email/dominios",
  "/email/listas",
  "/email/templates",
  "/equipe",
  "/favorecidos",
  "/financeiro",
  "/funil",
  "/imobiliarias",
  "/imoveis",
  "/julia/agente",
  "/julia/avaliacoes",
  "/julia/captacao",
  "/julia/configuracoes",
  "/julia/conhecimento",
  "/julia/conversas",
  "/julia/credito",
  "/julia/disparos",
  "/julia/envio",
  "/julia/equipe-whatsapp",
  "/julia/equipes",
  "/julia/leads",
  "/julia/modelos",
  "/julia/notificacoes",
  "/julia/opt-outs",
  "/julia/painel",
  "/julia/perguntas",
  "/julia/proprietarios",
  "/julia/protecao",
  "/julia/reengajamento",
  "/julia/relatorios",
  "/julia/visitas",
  "/leads",
  "/marcas",
  "/matriculas",
  "/media-creation/biblioteca",
  "/media-creation/branding",
  "/media-creation/carrosseis",
  "/media-creation/cerebro",
  "/media-creation/cerebro/extracoes",
  "/media-creation/chat",
  "/media-creation/dashboard",
  "/media-creation/esteira",
  "/media-creation/headlines/favoritas",
  "/media-creation/headlines/gerar",
  "/media-creation/headlines/sugeridas",
  "/media-creation/minha-biblioteca",
  "/media-creation/perfil",
  "/media-creation/pesquisa",
  "/media-creation/pesquisa/extrair",
  "/media-creation/roteiros",
  "/media-creation/treinamentos",
  "/meta",
  "/monitor",
  "/n8n",
  "/permutas",
  "/portal-roi",
  "/processos-venda",
  "/simec",
  "/supervisao",
  "/testemunhas",
  "/youtube",
];

const topGroupOf = (href: string) =>
  (NAV_GROUPS as AnyGroup[]).filter((g) => allItems([g]).some((i) => i.href === href)).map((g) => g.key);

describe.each([
  ["NAV_GROUPS", NAV_GROUPS as AnyGroup[]],
  ["NAV_FALLBACK", NAV_FALLBACK as AnyGroup[]],
])("%s", (_name, groups) => {
  it("top-level groups follow MODULE_GROUP_ORDER, labelled by MODULE_GROUP_LABELS", () => {
    const keys = groups.map((g) => g.key);
    const ranks = keys.map((k) => MODULE_GROUP_ORDER.indexOf(k as never));
    expect(ranks.every((r) => r >= 0)).toBe(true);
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks);
    expect(keys).toEqual(["crm", "redes-sociais", "erp", "cms", "corestudio", "emissoes", "integracoes", "configuracoes"]);
    for (const g of groups) expect(g.label).toBe(MODULE_GROUP_LABELS[g.key as keyof typeof MODULE_GROUP_LABELS]);
  });

  it("every pre-existing nav URL is still present, in exactly one group (Dashboard stands alone)", () => {
    for (const href of PRE_EXISTING_HREFS) {
      if (href === "/") continue;
      const hits = allItems(groups).filter((i) => i.href === href);
      expect(hits, href).toHaveLength(1);
    }
    expect(STANDALONE_ITEMS.map((i) => [i.name, i.href])).toEqual([["Dashboard", "/"]]);
    expect(allItems(groups).some((i) => i.href === "/")).toBe(false);
  });

  it("no orphan pages: nothing in the nav that was not already a SW page", () => {
    const hrefs = allItems(groups).map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs.filter((h) => !PRE_EXISTING_HREFS.includes(h))).toEqual([]);
  });

  it("Conexões is gone; its pages sit in Integrações / Redes Sociais / Atendimento", () => {
    expect(byKey(groups, "conexoes")).toBeUndefined();
    expect(byKey(groups, "integracoes")!.items.map((i) => i.href)).toEqual(["/marcas", "/n8n"]);
    expect(byKey(groups, "redes-sociais")!.items.map((i) => i.href)).toEqual(["/meta", "/youtube", "/simec"]);
  });

  it("Roteiros sits under CoreStudio › Headlines, and only there", () => {
    const headlines = allGroups(groups).find((g) => g.key === "media-creation-headlines")!;
    expect(headlines.items.map((i) => i.href)).toContain("/media-creation/roteiros");
    expect(allItems(groups).filter((i) => i.href === "/media-creation/roteiros")).toHaveLength(1);
  });

  it("nothing links to the retired /whatsapp-chat route", () => {
    expect(allItems(groups).some((i) => i.href === "/whatsapp-chat")).toBe(false);
  });

  it("Julia lives under CRM with its pages unchanged", () => {
    expect(topGroupOf("/julia/painel")).toEqual(["crm"]);
    const julia = allGroups(groups).find((g) => g.label === JULIA_LABEL)!;
    expect(julia.items.map((i) => [i.name, i.href])).toEqual(Object.values(JULIA_PAGES).map((p) => [p.name, p.href]));
  });

  it("E-mail (CRM) carries Mailchimp as a sub-group", () => {
    const email = allGroups(groups).find((g) => g.label === "E-mail")!;
    expect(email.items.map((i) => i.href)).toEqual([
      "/email", "/email/campanhas", "/email/contatos", "/email/listas", "/email/templates", "/email/automacoes", "/email/dominios",
    ]);
    expect(email.groups!.map((g) => g.label)).toEqual(["Mailchimp"]);
    expect(email.groups![0].items.every((i) => i.href.startsWith("/email-marketing/"))).toBe(true);
  });
});

describe("route keys (status_pagina gating)", () => {
  it("every gated item keeps a route key; the fallback has none", () => {
    expect(allItems(NAV_GROUPS as AnyGroup[]).every((i) => typeof i.route === "string" && i.route.length > 0)).toBe(true);
    expect(allItems(NAV_FALLBACK as AnyGroup[]).some((i) => "route" in i)).toBe(false);
  });

  it("every Julia item is gated by its own julia_* key", () => {
    const routes = Object.values(JULIA_PAGES).map((p) => p.route);
    const julia = allGroups(NAV_GROUPS as AnyGroup[]).find((g) => g.label === JULIA_LABEL)!;
    expect(julia.items.map((i) => i.route)).toEqual(routes);
    expect(routes.every((r) => r.startsWith("julia_"))).toBe(true);
  });

  it("the fallback is NAV_GROUPS minus route keys (derived, same hrefs in the same order)", () => {
    expect(allItems(NAV_FALLBACK as AnyGroup[]).map((i) => i.href)).toEqual(allItems(NAV_GROUPS as AnyGroup[]).map((i) => i.href));
  });

  it("module pages gate on the same status_pagina keys as before (route per href)", () => {
    const route = (href: string) => allItems(NAV_GROUPS as AnyGroup[]).find((i) => i.href === href)?.route;
    expect(route("/funil")).toBe("funil");
    expect(route("/clientes/revisao")).toBe("clientes_revisao");
    expect(route("/email/dominios")).toBe("email_dominios_noc");
    expect(route("/email-marketing/configuracao")).toBe("email_config");
    expect(route("/simec")).toBe("simec");
    expect(route("/edicao-fotos/novo")).toBe("edicao-fotos-novo-lote");
  });
});

describe("deep links", () => {
  const app = readFileSync(resolve(__dirname, "../App.tsx"), "utf8");
  const declared = new Set<string>();
  for (const m of app.matchAll(/path:\s*"([^"]+)"/g)) declared.add(m[1]);
  for (const m of app.matchAll(/path:\s*JULIA_PAGES\.(\w+)\.href/g)) declared.add((JULIA_PAGES as any)[m[1]].href);

  it("every pre-existing nav URL (and Dashboard) is still a declared route in App.tsx", () => {
    for (const href of PRE_EXISTING_HREFS) {
      const wild = href === "/financeiro" ? "/financeiro/*" : href;
      expect(declared.has(href) || declared.has(wild), href).toBe(true);
    }
  });
});
