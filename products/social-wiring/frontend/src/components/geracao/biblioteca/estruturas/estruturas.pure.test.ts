/** Pure helpers of the Estruturas library UI: vocabulary, provenance, draft mapping, validation, URL filters, link, errors. */
import { describe, expect, it } from "vitest";

import { bloco, detalheAdmin, membro } from "@/test/estruturasFixtures";
import { codigoDoErro, dadoDoErro, ehConflitoDeVersao, mensagemEstruturas } from "./erros";
import { contarFiltros, FILTROS_ESTRUTURAS_VAZIOS, filtrosDeParams, filtrosParaParams } from "./filtros";
import { normalizarLinkInstagram } from "./link";
import {
  blocoParaCorpo,
  camposPendentes,
  detalheParaRascunho,
  faltandoParaPublicar,
  placeholdersDaFormula,
  resumoBloco,
} from "./rotulos";
import { errosDoRascunho } from "./schema";

describe("camposPendentes (confirm grammar)", () => {
  it("lists every referencia / ia_sugerido field in the contract's field grammar", () => {
    expect(camposPendentes(detalheAdmin())).toEqual(["formula_headline", "bloco.b1.tipo", "bloco.b1.instrucao"]);
  });
  it("is empty for a member's response (no provenance is ever sent)", () => {
    expect(camposPendentes(membro(detalheAdmin()))).toEqual([]);
  });
});

describe("draft mapping", () => {
  it("maps the persisted detail to the draft shape (null → empty string, key = server id)", () => {
    const r = detalheParaRascunho(detalheAdmin());
    expect(r.formato).toBe("reels");
    expect(r.blocos[1]).toMatchObject({ chave: "b2", id: "b2", instrucao: "", repeticoes: 2, tipo_id: "t3" });
  });
  it("body items omit empty text and keep the id of saved blocks only", () => {
    expect(blocoParaCorpo({ chave: "novo-1", nome: " Novo ", tipo_id: "t4", tempo: "", instrucao: "", nota: "", repeticoes: 1 })).toEqual({
      nome: "Novo",
      tipo_id: "t4",
      repeticoes: 1,
    });
    expect(blocoParaCorpo(detalheParaRascunho(detalheAdmin()).blocos[0]!)).toMatchObject({ id: "b1", tempo: "0–3s" });
  });
});

describe("helpers", () => {
  it("finds [placeholders]", () => {
    expect(placeholdersDaFormula("Como [autoridade teórica] resolve [problema]")).toEqual(["autoridade teórica", "problema"]);
    expect(placeholdersDaFormula("sem colchetes")).toEqual([]);
  });
  it("mirrors the publish rule", () => {
    expect(faltandoParaPublicar({ formato: null, objetivos: [], blocos: [] })).toEqual(["formato", "objetivos", "blocos"]);
    expect(faltandoParaPublicar({ formato: "post", objetivos: ["venda"], blocos: [bloco()] })).toEqual([]);
  });
  it("summarises a block's tempo and repeats", () => {
    expect(resumoBloco({ tempo: "3–7s", repeticoes: 2 })).toBe("3–7s · ×2");
    expect(resumoBloco({ tempo: null, repeticoes: 1 })).toBe("");
  });
});

describe("errosDoRascunho (zod mirror of the column rules)", () => {
  const ok = detalheParaRascunho(detalheAdmin());
  it("accepts a valid draft", () => expect(errosDoRascunho(ok)).toEqual({}));
  it("refuses an empty formula, a missing formato, no objetivo and no block — in pt-BR", () => {
    const e = errosDoRascunho({ formula_headline: " ", formato: "", objetivos: [], blocos: [] });
    expect(e.formula_headline).toBe("Informe a fórmula da headline.");
    expect(e.formato).toBe("Escolha o formato.");
    expect(e.objetivos).toBe("Escolha ao menos um objetivo.");
    expect(e.blocos).toBe("Adicione ao menos um bloco.");
  });
  it("addresses block errors by the block's draft key", () => {
    const e = errosDoRascunho({ ...ok, blocos: [{ ...ok.blocos[0]!, nome: "", repeticoes: 21 }] });
    expect(e["bloco.b1.nome"]).toBe("Informe o nome do bloco.");
    expect(e["bloco.b1.repeticoes"]).toBe("Máximo 20.");
  });
  it("refuses NaN repeats (an emptied number input)", () => {
    expect(errosDoRascunho({ ...ok, blocos: [{ ...ok.blocos[0]!, repeticoes: Number.NaN }] })["bloco.b1.repeticoes"]).toBeTruthy();
  });
});

describe("URL filters", () => {
  it("round-trips, omitting defaults and keeping foreign params", () => {
    const f = { ...FILTROS_ESTRUTURAS_VAZIOS, busca: "autoridade", formatos: ["reels", "post"] as const, status: "rascunho" as const, pendentes: true, pagina: 3 };
    const p = filtrosParaParams({ ...f, formatos: [...f.formatos] }, new URLSearchParams({ aba: "estruturas" }));
    expect(p.toString()).toBe("aba=estruturas&busca=autoridade&formato=reels&formato=post&status=rascunho&pendentes=1&pagina=3");
    expect(filtrosDeParams(p)).toEqual({ ...f, formatos: ["reels", "post"], objetivos: [] });
    expect(filtrosParaParams(FILTROS_ESTRUTURAS_VAZIOS).toString()).toBe("");
  });
  it("drops invalid values and counts active filters", () => {
    const f = filtrosDeParams(new URLSearchParams("formato=podcast&status=x&pagina=-2"));
    expect(f).toEqual(FILTROS_ESTRUTURAS_VAZIOS);
    expect(contarFiltros({ ...f, busca: "a", pendentes: true })).toBe(2);
  });
});

describe("normalizarLinkInstagram (host allowlist)", () => {
  it.each([
    "https://www.instagram.com/reel/AbC_123-x/",
    "instagram.com/p/AbC123/?igsh=1",
    "http://instagram.com/tv/AbC123",
    "https://www.instagram.com/reels/AbC123/",
  ])("accepts %s", (u) => expect(normalizarLinkInstagram(u)).toMatchObject({ ok: true }));
  it.each([
    "",
    "https://evil.com/reel/AbC123/",
    "https://instagram.com.evil.com/p/AbC123/",
    "https://www.instagram.com/fulano/",
    "https://www.instagram.com/stories/fulano/123/",
  ])("rejects %s", (u) => expect(normalizarLinkInstagram(u)).toMatchObject({ ok: false }));
});

describe("erros", () => {
  const apiErr = (code: string, extra: Record<string, unknown> = {}, status = 409) => ({
    code,
    status,
    message: `[${status}] x`,
    field: (k: string) => extra[k],
  });
  it("maps every catalogued code to its pt-BR sentence", () => {
    expect(mensagemEstruturas(apiErr("estrutura_em_uso"), "f")).toBe("Esta estrutura já foi usada em headlines ou roteiros. Arquive-a em vez de excluir.");
    expect(mensagemEstruturas(apiErr("fonte_nao_suporta_link"), "f")).toBe("A fonte de ingestão atual não consegue buscar um post avulso.");
    expect(mensagemEstruturas(apiErr("tipo_protegido"), "f")).toContain('"Outro"');
  });
  it("falls back to 403 / 404 sentences, then the error text, then the caller's fallback", () => {
    expect(mensagemEstruturas({ status: 403 }, "f")).toBe("Somente administradores da plataforma podem fazer isso.");
    expect(mensagemEstruturas({ status: 404 }, "f")).toContain("Não encontramos");
    expect(mensagemEstruturas(new Error("falhou"), "f")).toBe("falhou");
    expect(mensagemEstruturas({}, "padrão")).toBe("padrão");
  });
  it("reads code and extra data", () => {
    const e = apiErr("rascunho_incompleto", { faltando: ["formato"] }, 422);
    expect(codigoDoErro(e)).toBe("rascunho_incompleto");
    expect(dadoDoErro(e, "faltando")).toEqual(["formato"]);
    expect(ehConflitoDeVersao(apiErr("versao_desatualizada"))).toBe(true);
    expect(ehConflitoDeVersao(null)).toBe(false);
  });
  it("reads extras from a raw FastAPI body when the error has no field()", () => {
    expect(dadoDoErro({ body: { detail: { code: "x", estruturas_total: 4 } } }, "estruturas_total")).toBe(4);
  });
});
