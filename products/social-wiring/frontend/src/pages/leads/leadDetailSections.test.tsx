/**
 * The shared detail descriptor + the card→origin resolution.
 *
 * These are the two things that make "one modal, three surfaces" true, and
 * both are pure functions — which is the point of the split. The organ
 * itself is tested in the seed's own vitest (a product suite renders a
 * SECOND React against the seed's copy and fails on hooks — memory
 * `feedback_product_vitest_cannot_render_seed_organ`), so what is worth
 * asserting HERE is the part the product owns: which fields exist, how
 * they are formatted, and which record a given card is about.
 */
import { describe, expect, it } from "vitest";

import {
  campanhaDetailSections,
  explainNeedsReview,
  leadDetailSections,
} from "./leadDetailSections";
import type { Lead, LeadSource } from "./types";
import {
  nomeDoProcesso,
  origemDoAtendimento,
  origemDoProcesso,
  type AtendimentoCampanha,
  type Atendimento,
  type ProcessoVenda,
} from "@/types/pipeline";

const LEAD: Lead = {
  id: "l1",
  org_id: "o1",
  data_entrada: "2026-07-01",
  ano: 2026,
  mes: 7,
  codigo_raw: null,
  codigo_imovel: "ONE10137",
  empreendimento: "Granja Viana",
  regiao: "Oeste",
  origem_id: "s1",
  origem_raw: "Meta",
  origem: { id: "s1", slug: "meta", label: "Meta Ads", cor: "#1877F2" },
  tipo_lead: "novo",
  cliente_nome: "Maria Silva",
  // As it arrived off the import sheet — deliberately NOT canonical, so the
  // descriptor has something to normalize.
  contato: "11 99457.3387",
  contato_tipo: "telefone",
  corretor_id: null,
  corretor_raw: "João",
  corretor: null,
  anuncio_tier: "destaque",
  status: "Em atendimento",
  observacoes: "Prefere contato à tarde",
  follow_up_data: "2026-07-05",
  follow_up_nota: "Ligar",
  needs_review: false,
  source_sheet: "2026",
  source_row: 42,
  created_at: "2026-07-01T10:00:00Z",
  updated_at: null,
};

const CAMPANHA: AtendimentoCampanha = {
  id: "m1",
  full_name: "Leonora Lira",
  email: "leonora@example.com",
  phone: "+5511964540451",
  campaign_id: "c1",
  campaign_name: "Granja Viana - Julho",
  form_id: "f1",
  form_name: "Formulário Granja",
  ad_id: null,
  adset_id: null,
  platform: "fb",
  is_organic: false,
  created_time: "2026-07-02T09:00:00Z",
  answers: { "Nome completo": "Leonora Lira", Telefone: "+5511964540451" },
};

function fieldsOf(sections: ReturnType<typeof leadDetailSections>) {
  return sections.flatMap((s) => s.fields);
}

function valueOf(sections: ReturnType<typeof leadDetailSections>, label: string) {
  return fieldsOf(sections).find((f) => f.label === label)?.value;
}

describe("leadDetailSections", () => {
  it("renders the contact through the platform phone seam, not raw", () => {
    // THE reason this file exists: the same number must read identically
    // whether it arrived from a sheet or from a Meta campaign.
    expect(valueOf(leadDetailSections(LEAD), "Contato")).toBe("+5511994573387");
  });

  it("shows a malformed number instead of blanking it", () => {
    // `normalizePhone` refuses to invent the ninth digit of a legacy mobile.
    // Hiding the result would remove the only signal that it needs a human.
    const sections = leadDetailSections({ ...LEAD, contato: "11 9999-9999" });
    expect(valueOf(sections, "Contato")).toBe("11 9999-9999");
  });

  it("lowercases an e-mail contact rather than phone-formatting it", () => {
    const sections = leadDetailSections({
      ...LEAD,
      contato: "Maria@Example.COM",
      contato_tipo: "email",
    });
    expect(valueOf(sections, "Contato")).toBe("maria@example.com");
  });

  it("falls back to the raw origem/corretor when the join is absent", () => {
    const sections = leadDetailSections({ ...LEAD, origem: null });
    expect(valueOf(sections, "Origem")).toBe("Meta");
    expect(valueOf(sections, "Corretor")).toBe("João");
  });

  it("covers every field the Leads drawer used to show", () => {
    // Regression guard for the drawer→organ migration: this modal replaced a
    // hand-written field list, and quietly dropping one of its fields is the
    // exact way a consolidation loses information.
    const labels = fieldsOf(leadDetailSections(LEAD)).map((f) => f.label);
    for (const expected of [
      "Data de entrada",
      "Tipo",
      "Contato",
      "Origem",
      "Corretor",
      "Tier do anúncio",
      "Empreendimento",
      "Região",
      "Código do imóvel",
      "Status",
      "Data",
      "Nota",
      "Observações",
      "Planilha de origem",
      "Criado em",
    ]) {
      expect(labels).toContain(expected);
    }
  });
});

describe("campanhaDetailSections", () => {
  it("formats the campaign phone through the same seam", () => {
    expect(valueOf(campanhaDetailSections(CAMPANHA), "Telefone")).toBe("+5511964540451");
  });

  it("surfaces the form answers — visible nowhere in the UI before this modal", () => {
    const sections = campanhaDetailSections(CAMPANHA);
    const respostas = sections.find((s) => s.title === "Respostas do formulário");
    expect(respostas?.fields.map((f) => f.label)).toContain("Telefone");
  });

  it("joins a multi-select answer instead of rendering [object Object]", () => {
    const sections = campanhaDetailSections({
      ...CAMPANHA,
      answers: { Interesses: ["Apartamento", "Casa"] },
    });
    const respostas = sections.find((s) => s.title === "Respostas do formulário");
    expect(respostas?.fields[0]?.value).toBe("Apartamento, Casa");
  });

  it("leaves the answers section empty when the form had none, so the organ drops it", () => {
    const sections = campanhaDetailSections({ ...CAMPANHA, answers: null });
    const respostas = sections.find((s) => s.title === "Respostas do formulário");
    expect(respostas?.fields).toHaveLength(0);
  });

  it("hides ad/adset ids that are absent rather than showing empty rows", () => {
    const campanha = sections0(CAMPANHA);
    expect(campanha.find((f) => f.label === "Anúncio")?.hidden).toBe(true);
    const comAd = sections0({ ...CAMPANHA, ad_id: "a1" });
    expect(comAd.find((f) => f.label === "Anúncio")?.hidden).toBe(false);
  });
});

function sections0(c: AtendimentoCampanha) {
  return campanhaDetailSections(c).flatMap((s) => s.fields);
}

describe("explainNeedsReview — a flag the user cannot interpret is one she cannot fix", () => {
  it("names the unrecognized origem string", () => {
    expect(explainNeedsReview({ ...LEAD, origem_id: null }, [])).toBe(
      'Origem não reconhecida: "Meta"',
    );
  });

  it("says so when the row carried no origem at all", () => {
    expect(explainNeedsReview({ ...LEAD, origem_id: null, origem_raw: null }, [])).toBe(
      "Sem origem informada nesta linha",
    );
  });

  it("points at Configuração when the origem only matched the generic bucket", () => {
    const sources = [
      { id: "s1", label: "Outro", categoria: "outro" } as unknown as LeadSource,
    ];
    expect(explainNeedsReview(LEAD, sources)).toContain("revise a categoria em Configuração");
  });
});

describe("card → origin resolution", () => {
  const negLead = {
    id: "n1",
    lead_id: "l1",
    meta_ads_lead_id: null,
    campanha: null,
  } as unknown as Atendimento;

  const negCampanha = {
    id: "n2",
    lead_id: null,
    meta_ads_lead_id: "m1",
    campanha: CAMPANHA,
  } as unknown as Atendimento;

  it("a lead-origin card is opened by id (fetched whole)", () => {
    expect(origemDoAtendimento(negLead)).toEqual({ leadId: "l1", campanha: null });
  });

  it("a campaign-origin card is opened from its own projection — there is no leads row", () => {
    expect(origemDoAtendimento(negCampanha)).toEqual({ leadId: null, campanha: CAMPANHA });
  });

  it("a processo resolves to the SAME origin as the negociação it came from", () => {
    // This is what makes both boards open one modal: the processo reaches
    // its lead one hop further out, through the deal.
    const processo = {
      id: "p1",
      atendimento: { id: "n1", lead_id: "l1", campanha: null },
    } as unknown as ProcessoVenda;
    expect(origemDoProcesso(processo)).toEqual(origemDoAtendimento(negLead));
  });

  it("a processo whose negociação did not load resolves to nothing, not a crash", () => {
    const orphan = { id: "p2" } as unknown as ProcessoVenda;
    expect(origemDoProcesso(orphan)).toEqual({ leadId: null, campanha: null });
  });

  // ── migration 054: one card per person ───────────────────────────────────
  // A survivor spawned from a CAMPAIGN has `lead_id === null` while carrying a
  // `lead` merged from the row collapsed into it. Reading the FK alone returns
  // `leadId: null` and the lead detail never opens — on exactly the cards the
  // collapse exists to create. The object wins over the FK.

  const negColapsadaComLeadMesclado = {
    id: "n3",
    lead_id: null,
    meta_ads_lead_id: "m1",
    campanha: CAMPANHA,
    lead: { id: "l9", cliente_nome: "Ana Silva", contato: "11999998888" },
  } as unknown as Atendimento;

  it("a collapsed card opens the lead merged from its sibling, despite a null FK", () => {
    expect(origemDoAtendimento(negColapsadaComLeadMesclado)).toEqual({
      leadId: "l9",
      campanha: CAMPANHA,
    });
  });

  it("a collapsed card still carries BOTH origins — that is the whole point", () => {
    const origem = origemDoAtendimento(negColapsadaComLeadMesclado);
    expect(origem.leadId).not.toBeNull();
    expect(origem.campanha).not.toBeNull();
  });

  it("a processo behind a collapsed negociação reaches the merged lead too", () => {
    const processo = {
      id: "p3",
      atendimento: {
        id: "n3",
        lead_id: null,
        campanha: CAMPANHA,
        lead: { id: "l9", cliente_nome: "Ana Silva" },
      },
    } as unknown as ProcessoVenda;
    expect(origemDoProcesso(processo).leadId).toBe("l9");
  });
});

describe("nomeDoProcesso", () => {
  it("prefers the deal title", () => {
    const p = { atendimento: { titulo: "Apto 42" } } as unknown as ProcessoVenda;
    expect(nomeDoProcesso(p)).toBe("Apto 42");
  });

  it("falls back through the origin before giving up", () => {
    const p = {
      atendimento: { titulo: null, lead: { cliente_nome: "Maria Silva" } },
    } as unknown as ProcessoVenda;
    expect(nomeDoProcesso(p)).toBe("Maria Silva");
  });

  it("never renders empty", () => {
    expect(nomeDoProcesso({} as unknown as ProcessoVenda)).toBe("Processo");
  });
});
