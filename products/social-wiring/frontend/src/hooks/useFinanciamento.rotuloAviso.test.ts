import { describe, expect, it } from "vitest";
import { AVISO_LABEL, rotuloAviso } from "./useFinanciamento";

describe("rotuloAviso", () => {
  it("labels a single code", () => {
    expect(rotuloAviso("quadro_resumo_soma_divergente")).toBe(
      AVISO_LABEL.quadro_resumo_soma_divergente,
    );
  });

  it("labels every code of a seed ',' list joined with the backend's '; '", () => {
    const texto = rotuloAviso(
      "quadro_resumo_soma_divergente,vendedores_cpf_digito_invalido; agente_financeiro_nao_cadastrado",
    );
    expect(texto).toContain(AVISO_LABEL.quadro_resumo_soma_divergente);
    expect(texto).toContain(AVISO_LABEL.vendedores_cpf_digito_invalido);
    expect(texto).toContain(AVISO_LABEL.agente_financeiro_nao_cadastrado);
    expect(texto).not.toMatch(/[a-z]+_[a-z_]+/);
  });

  it("keeps an unknown code raw rather than blank", () => {
    expect(rotuloAviso("codigo_novo")).toBe("codigo_novo");
  });

  it("is empty for no aviso", () => {
    expect(rotuloAviso(null)).toBe("");
    expect(rotuloAviso("")).toBe("");
  });
});

describe("rotuloErro", () => {
  it("labels a known extraction error code in pt-BR", async () => {
    const { rotuloErro } = await import("./useFinanciamento");
    expect(rotuloErro("documento_sensivel_dps")).toMatch(/Declaração Pessoal de Saúde/);
  });
  it("falls back to the raw code, and a generic message when empty", async () => {
    const { rotuloErro } = await import("./useFinanciamento");
    expect(rotuloErro("codigo_desconhecido")).toBe("codigo_desconhecido");
    expect(rotuloErro(null)).toBe("Não foi possível ler o documento.");
  });
  it("labels the derived ITBI transaction-value aviso", async () => {
    const { rotuloAviso } = await import("./useFinanciamento");
    expect(rotuloAviso("valor_transacao_derivado")).toMatch(/valor à vista \+ valor financiado/);
  });
});
