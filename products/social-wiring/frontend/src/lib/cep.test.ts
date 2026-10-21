import { describe, expect, it } from "vitest";
import { cepOitoDigitos, preencherEnderecoVazio } from "./cep";

const END = { logradouro: "Avenida Paulista", bairro: "Bela Vista", cidade: "São Paulo", uf: "SP" };

describe("cep helpers", () => {
  it("accepts a CEP only when it has exactly 8 digits", () => {
    expect(cepOitoDigitos("01310-100")).toBe("01310100");
    expect(cepOitoDigitos("0131010")).toBeNull();
    expect(cepOitoDigitos(null)).toBeNull();
  });

  it("fills every empty address field", () => {
    expect(preencherEnderecoVazio({}, END)).toEqual({
      endereco_logradouro: "Avenida Paulista",
      endereco_bairro: "Bela Vista",
      endereco_cidade: "São Paulo",
      endereco_uf: "SP",
    });
  });

  it("never overwrites a field the operator already typed", () => {
    const r = preencherEnderecoVazio(
      { endereco_logradouro: "Rua Minha", endereco_cidade: null, endereco_uf: "  " },
      END,
    );
    expect(r.endereco_logradouro).toBe("Rua Minha");
    expect(r.endereco_cidade).toBe("São Paulo");
    expect(r.endereco_uf).toBe("SP");
  });
});
