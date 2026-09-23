/**
 * ImovelCartorioCard — the título aquisitivo / ônus source badges
 * (migration 109).
 *
 * Scope: ONLY the new read-only badges this change added. The form fields
 * above them (número da matrícula, captador, situação de ônus) are exercised
 * indirectly here only to the extent needed to render the card at all.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelCartorioCard from "./ImovelCartorioCard";
import type { ImovelDados } from "@/hooks/useImovelDados";

function dados(over: Partial<ImovelDados> = {}): ImovelDados {
  return {
    codigo: "ONE9001",
    numero_matricula: "12345",
    numero_matricula_origem: null,
    numero_matricula_documento_id: null,
    numero_matricula_em: null,
    numero_matricula_confirmado_por: null,
    numero_matricula_confirmado_em: null,
    numero_registro_imoveis: null,
    prefeitura_cadastro_imobiliario: null,
    captador: null,
    situacao_onus: null,
    onus_observacoes: null,
    onus_certidao_em: null,
    onus_documento_id: null,
    onus_registrado_por: null,
    onus_registrado_em: null,
    situacoes_onus: [],
    titulo_aquisitivo_fonte: null,
    onus_fonte: null,
    endereco_manual_logradouro: null,
    endereco_manual_numero: null,
    endereco_manual_cidade: null,
    endereco_manual_uf: null,
    endereco_manual_confirmado_por: null,
    endereco_manual_confirmado_em: null,
    empreendimento_manual: null,
    empreendimento_manual_confirmado_por: null,
    empreendimento_manual_confirmado_em: null,
    updated_at: null,
    ...over,
  };
}

async function render(
  dadosOverride?: Partial<ImovelDados>,
  opts?: {
    onSave?: (patch: unknown) => void;
    mirror?: {
      logradouro?: string | null;
      numero?: string | null;
      cidade?: string | null;
      uf?: string | null;
      empreendimento?: string | null;
    };
  },
) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  const view = rtl.render(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(ImovelCartorioCard, {
        dados: dados(dadosOverride),
        membros: [],
        loading: false,
        saving: false,
        error: null,
        onSave: opts?.onSave ?? vi.fn(),
        mirror: opts?.mirror,
      }),
    ),
  );
  return { ...view, ...rtl };
}

describe("ImovelCartorioCard — matrícula source badges", () => {
  it("shows 'não confirmado' for both when neither pointer is set", async () => {
    const { screen } = await render();
    expect(screen.getByTestId("imovel-titulo-aquisitivo-ausente")).toBeTruthy();
    expect(screen.getByTestId("imovel-onus-fonte-ausente")).toBeTruthy();
    expect(screen.queryByTestId("imovel-titulo-aquisitivo-badge")).toBeNull();
    expect(screen.queryByTestId("imovel-onus-fonte-badge")).toBeNull();
  });

  it("🔴 links the título aquisitivo badge to its matrícula extração", async () => {
    const { screen } = await render({
      titulo_aquisitivo_fonte: {
        extracao_id: "extracao-9",
        ato_id: "ato-1",
        char_inicio: 10,
        char_fim: 50,
        origem: "sugerido",
        confirmado_por: { id: "u1", nome: "Ana" },
        confirmado_em: "2026-02-01T00:00:00Z",
      },
    });
    const link = screen.getByTestId("imovel-titulo-aquisitivo-badge") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas?extracao=extracao-9");
    expect(screen.queryByTestId("imovel-titulo-aquisitivo-ausente")).toBeNull();
  });

  it("marks a manually-chosen ônus source distinctly from a suggested one", async () => {
    const { screen } = await render({
      onus_fonte: {
        extracao_id: "extracao-9",
        atos: [{ ato_id: "ato-2", char_inicio: 60, char_fim: 90 }],
        origem: "manual",
        confirmado_por: { id: "u1", nome: "Ana" },
        confirmado_em: "2026-02-01T00:00:00Z",
      },
    });
    const badge = screen.getByTestId("imovel-onus-fonte-badge");
    expect(badge.textContent).toContain("Ônus (1)");
    expect(badge.textContent).toContain("manual");
  });
});

describe("ImovelCartorioCard — empreendimento manual override (migration 158)", () => {
  it("renders with no mirror prop at all — the manual-layout case", async () => {
    // `ImovelManualLayout` (ImovelDetalhes.tsx) never passes `mirror` — a
    // manually registered imóvel has no Vista mirror row to show. The field
    // must still render and take the generic placeholder.
    const { screen } = await render();
    const input = screen.getByTestId("imovel-empreendimento-manual") as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.value).toBe("");
    expect(input.getAttribute("placeholder")).toBe("Ex.: Residencial Euroville");
  });

  it("shows the CRM mirror value in the label and uses it as the placeholder", async () => {
    const { screen } = await render(undefined, {
      mirror: { empreendimento: "Edifício Exemplo" },
    });
    expect(screen.getByText(/Empreendimento \/ condomínio/)).toBeTruthy();
    expect(screen.getByText(/\(CRM: Edifício Exemplo\)/)).toBeTruthy();
    const input = screen.getByTestId("imovel-empreendimento-manual") as HTMLInputElement;
    expect(input.getAttribute("placeholder")).toBe("Edifício Exemplo");
  });

  it("pre-fills the stored authored value", async () => {
    const { screen } = await render({ empreendimento_manual: "Residencial Euroville" });
    const input = screen.getByTestId("imovel-empreendimento-manual") as HTMLInputElement;
    expect(input.value).toBe("Residencial Euroville");
  });

  it("saves the typed value through the generic PATCH", async () => {
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(undefined, { onSave });
    const input = screen.getByTestId("imovel-empreendimento-manual") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Residencial Euroville" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ empreendimento_manual: "Residencial Euroville" }),
    );
  });

  it("clearing a stored value saves null, never an invented value", async () => {
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(
      { empreendimento_manual: "Residencial Euroville" },
      { onSave },
    );
    const input = screen.getByTestId("imovel-empreendimento-manual") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ empreendimento_manual: null }),
    );
  });
});

describe("ImovelCartorioCard — prefeitura_cadastro_imobiliario field label", () => {
  it("labels the field as the municipal registration NUMBER, not the city", async () => {
    // 🔴 The contract template prints "cadastrado pela Prefeitura Municipal
    // de {cidade} sob nº {inscricao_municipal}" — the city comes from
    // elsewhere, and this DB column supplies only the "nº" part. A label
    // reading "Prefeitura do cadastro imobiliário" with a city placeholder
    // led an operator to type a city here, which printed "sob nº São Paulo"
    // in a signed contract.
    const { screen } = await render();
    const input = screen.getByLabelText("Inscrição municipal (cadastro na prefeitura)");
    expect(input).toBeTruthy();
    expect(input.getAttribute("placeholder")).not.toMatch(/São Paulo/);
  });
});
