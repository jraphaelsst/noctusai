/**
 * The wizard's pure logic over the REAL model shape (fixture generated from `app.studio.modelo.construir_modelo`):
 * validation reads only the field model, the publish body is CONTRACT §6, the local draft survives a broken store.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgenteModelo } from "@/api/agentes/types";
import modeloJson from "@/api/agentes/__fixtures__/modelo-plataforma.json";
import {
  RASCUNHO_STORAGE_KEY,
  apresentacao,
  apagarRascunho,
  camposVisiveis,
  gravarRascunho,
  gruposDoPasso,
  lerRascunho,
  limiteGeracao,
  montarCorpo,
  primeiroPassoInvalido,
  validarPasso,
  valoresIniciais,
  type Valores,
} from "@/lib/assistente";

const MODELO = modeloJson as unknown as AgenteModelo;
const PASSOS = MODELO.assistente!.passos;
const passo = (id: string) => PASSOS.find((p) => p.id === id)!;

function preenchido(over: Valores = {}): Valores {
  return {
    ...valoresIniciais(PASSOS),
    "plataforma.key": "estrategista",
    "plataforma.nome": "Estrategista",
    "briefing.objetivo": "Planejar conteúdo semanal para redes sociais.",
    "briefing.publico": "Social media",
    "briefing.canal": "web",
    ...over,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("model-driven fields", () => {
  it("starts every field from the server default", () => {
    const v = valoresIniciais(PASSOS);
    expect(v["briefing.idioma"]).toBe("pt-BR");
    expect(v["plataforma.runtime"]).toBe("llm");
    expect(v["plataforma.instanciavel"]).toBe(false);
    expect(v["plataforma.limite_usd"]).toBe(5);
    expect(limiteGeracao(PASSOS)).toBe(5);
  });

  it("hides the briefing (and the generation cap) in empty mode", () => {
    expect(camposVisiveis(passo("papel"), "vazio").map((c) => c.chave)).toEqual(["padrao_qualificacao", "escopo_qualificacao"]);
    expect(camposVisiveis(passo("publicar"), "vazio").map((c) => c.chave)).toEqual(["instanciavel"]);
    expect(camposVisiveis(passo("publicar"), "gerar").map((c) => c.chave)).toEqual(["instanciavel", "limite_usd"]);
  });

  it("splits a step that mixes field groups into subtabs only when both are visible", () => {
    expect(gruposDoPasso(passo("papel"), "gerar").map((g) => g.grupo)).toEqual(["briefing", "plataforma"]);
    expect(gruposDoPasso(passo("papel"), "vazio").map((g) => g.grupo)).toEqual(["plataforma"]);
  });
});

describe("labels", () => {
  it("the server's title wins; the local table only fills a missing one", () => {
    const campo = passo("papel").campos.find((c) => c.chave === "publico")!;
    expect(campo.rotulo).toBe("Público atendido");
    expect(apresentacao({ ...campo, rotulo: "Quem é atendido" }).rotulo).toBe("Quem é atendido");
    expect(apresentacao({ ...campo, rotulo: "" }).rotulo).toBe("Público atendido");
    expect(apresentacao({ ...campo, chave: "novo_campo", rotulo: "Novo campo", modelo: "briefing" }).rotulo).toBe("Novo campo");
  });
});

describe("validation blocks what the server would 422", () => {
  it("requires a pattern-valid, new key and a name", () => {
    const vazio = validarPasso(passo("identidade"), "vazio", valoresIniciais(PASSOS));
    expect(Object.keys(vazio).sort()).toEqual(["plataforma.key", "plataforma.nome"]);
    const ruim = validarPasso(passo("identidade"), "vazio", preenchido({ "plataforma.key": "Bad Key" }));
    expect(ruim["plataforma.key"]).toMatch(/minúsculas/);
    const existe = validarPasso(passo("identidade"), "vazio", preenchido(), { chavesExistentes: new Set(["estrategista"]) });
    expect(existe["plataforma.key"]).toMatch(/Já existe/);
  });

  it("enforces min_length / options / numeric range from the model", () => {
    const e = validarPasso(passo("papel"), "gerar", preenchido({ "briefing.objetivo": "curto" }));
    expect(e["briefing.objetivo"]).toBe("Objetivo: mínimo de 10 caracteres.");
    expect(validarPasso(passo("canais"), "gerar", preenchido({ "briefing.canal": "" }))["briefing.canal"]).toMatch(/obrigatório/);
    expect(validarPasso(passo("publicar"), "gerar", preenchido({ "plataforma.limite_usd": 9 }))["plataforma.limite_usd"]).toMatch(/máximo de 5/);
    expect(validarPasso(passo("publicar"), "gerar", preenchido({ "plataforma.limite_usd": 0 }))["plataforma.limite_usd"]).toMatch(/maior que 0/);
  });

  it("does not ask for briefing fields in empty mode", () => {
    const v = preenchido({ "briefing.objetivo": "", "briefing.publico": "", "briefing.canal": "" });
    expect(primeiroPassoInvalido(PASSOS, "vazio", v)).toBeNull();
    expect(primeiroPassoInvalido(PASSOS, "gerar", v)?.passo.id).toBe("papel");
  });
});

describe("publish body (CONTRACT §6)", () => {
  it("empty mode: top-level definition fields only, empty optionals omitted", () => {
    expect(montarCorpo(PASSOS, "vazio", preenchido())).toEqual({
      key: "estrategista",
      nome: "Estrategista",
      runtime: "llm",
      instanciavel: false,
    });
  });

  it("AI mode: briefing nested, briefing.nome = the agent name, cost cap sent", () => {
    const corpo = montarCorpo(
      PASSOS,
      "gerar",
      preenchido({ "plataforma.descricao": "  Faz planos.  ", "briefing.tom_de_voz": "direto", "plataforma.instanciavel": true }),
    );
    expect(corpo).toEqual({
      key: "estrategista",
      nome: "Estrategista",
      descricao: "Faz planos.",
      runtime: "llm",
      instanciavel: true,
      limite_usd: 5,
      briefing: {
        nome: "Estrategista",
        objetivo: "Planejar conteúdo semanal para redes sociais.",
        publico: "Social media",
        tom_de_voz: "direto",
        idioma: "pt-BR",
        canal: "web",
      },
    });
  });
});

describe("local draft", () => {
  it("round-trips and clears", () => {
    expect(gravarRascunho({ modo: "gerar", valores: { "plataforma.key": "x" }, passo: "papel", chaveTocada: true, salvoEm: "t" })).toBe(true);
    expect(lerRascunho()).toMatchObject({ modo: "gerar", passo: "papel", chaveTocada: true, valores: { "plataforma.key": "x" } });
    apagarRascunho();
    expect(lerRascunho()).toBeNull();
  });

  it("treats a corrupt or foreign value as no draft", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    window.localStorage.setItem(RASCUNHO_STORAGE_KEY, "{nope");
    expect(lerRascunho()).toBeNull();
    window.localStorage.setItem(RASCUNHO_STORAGE_KEY, JSON.stringify({ modo: "outro", valores: {} }));
    expect(lerRascunho()).toBeNull();
  });

  it("reports a refused write instead of pretending it was kept", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const recusa = {
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
    } as unknown as Storage;
    vi.spyOn(window, "localStorage", "get").mockReturnValue(recusa);
    expect(gravarRascunho({ modo: "vazio", valores: {}, passo: null, chaveTocada: false, salvoEm: "t" })).toBe(false);
    expect(warn).toHaveBeenCalled();
  });
});
