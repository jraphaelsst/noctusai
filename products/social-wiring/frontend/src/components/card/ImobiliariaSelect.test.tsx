/**
 * ImobiliariaSelect — the REQUIRED "Imobiliária que assina" select and its
 * `origem` states: selecionada, unica, null (required-choice), plus a removed
 * company (`excluida`) and a chosen company with a non-empty `faltando`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// Same Radix `Select` stand-in `TestemunhasSelect.test.tsx` uses.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-disabled": disabled, "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children, disabled }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", disabled, onClick: () => !disabled && ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

import { ImobiliariaSelect } from "./ImobiliariaSelect";
import type { ContratoImobiliaria } from "@/hooks/useContratoImobiliaria";
import type { Imobiliaria } from "@/hooks/useImobiliarias";

function imob(over: Partial<Imobiliaria> = {}): Imobiliaria {
  return {
    id: "i1",
    razao_social: "TANGERINO LTDA",
    nome_fantasia: null,
    cnpj: "06.057.235/0001-04",
    creci_pj: null,
    creci_pj_regiao: null,
    responsavel_nome: null,
    responsavel_creci: null,
    responsavel_creci_regiao: null,
    telefone: null,
    email: null,
    endereco_cep: null,
    endereco_logradouro: null,
    endereco_numero: null,
    endereco_complemento: null,
    endereco_bairro: null,
    endereco_cidade: null,
    endereco_uf: null,
    faltando: [],
    contratos_em_uso: 0,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

function resolvida(over: Record<string, unknown> = {}) {
  return {
    id: "i1",
    razao_social: "TANGERINO LTDA",
    nome_fantasia: null,
    cnpj: "06.057.235/0001-04",
    excluida: false,
    faltando: [],
    ...over,
  } as NonNullable<ContratoImobiliaria["imobiliaria"]>;
}

async function render(atual: ContratoImobiliaria, registro: Imobiliaria[] = [imob(), imob({ id: "i2", razao_social: "OUTRA LTDA" })]) {
  const { render: rtlRender } = await import("@testing-library/react");
  const onChange = vi.fn();
  const utils = rtlRender(<ImobiliariaSelect atual={atual} registro={registro} onChange={onChange} />);
  return { ...utils, onChange };
}

describe("origem", () => {
  it("selecionada: mostra a escolhida, sem dica de única nem aviso de obrigatoriedade", async () => {
    const { container, queryByTestId } = await render({ imobiliaria: resolvida(), origem: "selecionada" });
    expect(container.querySelector("[data-value='i1']")).toBeTruthy();
    expect(queryByTestId("imobiliaria-unica")).toBeNull();
    expect(queryByTestId("imobiliaria-obrigatoria")).toBeNull();
  });

  it("unica: mostra como escolhida com a dica 'única cadastrada'", async () => {
    const { container, getByTestId, queryByTestId } = await render(
      { imobiliaria: resolvida(), origem: "unica" },
      [imob()],
    );
    expect(container.querySelector("[data-value='i1']")).toBeTruthy();
    expect(getByTestId("imobiliaria-unica").textContent).toBe("única cadastrada");
    expect(queryByTestId("imobiliaria-obrigatoria")).toBeNull();
  });

  it("null: estado de escolha obrigatória visível, e escolher dispara onChange", async () => {
    const { container, getByTestId, getByText, onChange } = await render({ imobiliaria: null, origem: null });
    expect(container.querySelector("[data-value='']")).toBeTruthy();
    expect(getByTestId("imobiliaria-obrigatoria").textContent).toMatch(/Escolha qual imobiliária assina/);
    (await import("@testing-library/react")).fireEvent.click(getByText("OUTRA LTDA"));
    expect(onChange).toHaveBeenCalledWith("i2");
  });

  it("null com registro vazio: aponta para o cadastro", async () => {
    const { getByTestId } = await render({ imobiliaria: null, origem: null }, []);
    const el = getByTestId("imobiliaria-obrigatoria");
    expect(el.textContent).toMatch(/Nenhuma imobiliária cadastrada/);
    expect(el.querySelector("a")?.getAttribute("href")).toBe("/imobiliarias");
  });
});

describe("excluida e faltando", () => {
  it("removida do cadastro: continua como valor atual, sinalizada, e não é escolhível", async () => {
    const { container, getByTestId, getByText } = await render(
      { imobiliaria: resolvida({ id: "i9", razao_social: "ANTIGA LTDA", excluida: true }), origem: "selecionada" },
      [imob()],
    );
    expect(container.querySelector("[data-value='i9']")).toBeTruthy();
    expect(getByTestId("imobiliaria-excluida")).toBeTruthy();
    expect(getByText(/ANTIGA LTDA — removida do cadastro/)).toBeTruthy();
  });

  it("faltando não vazio: lista o que falta e linka para Imobiliárias", async () => {
    const { getByTestId } = await render({
      imobiliaria: resolvida({ faltando: ["responsavel_creci", "endereco_cidade"] }),
      origem: "selecionada",
    });
    const el = getByTestId("imobiliaria-faltando");
    expect(el.textContent).toContain("CRECI do responsável, cidade");
    expect(el.querySelector("a")?.getAttribute("href")).toBe("/imobiliarias");
  });
});
