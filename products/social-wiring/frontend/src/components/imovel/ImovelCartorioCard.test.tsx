/**
 * ImovelCartorioCard — the título aquisitivo / ônus source badges
 * (migration 109).
 *
 * Scope: ONLY the new read-only badges this change added. The form fields
 * above them (número da matrícula, captador, situação de ônus) are exercised
 * indirectly here only to the extent needed to render the card at all.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

// Migration 300 — the condomínio picker's data layer, mocked at the hook seam.
const { mockBusca, mockCriar } = vi.hoisted(() => ({ mockBusca: vi.fn(), mockCriar: vi.fn() }));
vi.mock("@/hooks/useCondominios", () => ({
  useCondominioBusca: mockBusca,
  useCriarCondominio: () => ({ mutate: mockCriar, isPending: false, isError: false, error: null }),
}));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

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
    endereco_manual_complemento: null,
    endereco_manual_bairro: null,
    endereco_manual_cidade: null,
    endereco_manual_uf: null,
    endereco_manual_cep: null,
    endereco_manual_confirmado_por: null,
    endereco_manual_confirmado_em: null,
    empreendimento_manual: null,
    empreendimento_manual_confirmado_por: null,
    empreendimento_manual_confirmado_em: null,
    condominio_id: null,
    condominio: null,
    casa_de_rua: false,
    em_condominio: null,
    em_condominio_legado: null,
    padrao_construtivo: null,
    estado_conservacao: null,
    area_terreno_m2: null,
    area_construida_m2: null,
    testada_m: null,
    profundidade_m: null,
    topografia: null,
    posicao_lote: null,
    avaliacao_campos_atualizado_em: null,
    avaliacao_campos_atualizado_por: null,
    updated_at: null,
    ...over,
  };
}

async function render(
  dadosOverride?: Partial<ImovelDados>,
  opts?: {
    onSave?: (patch: unknown) => void;
    // Migration 159 — the address fields moved to `<ImovelEnderecoCard/>`;
    // this card's `mirror` prop only carries `empreendimento` now.
    mirror?: {
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
    expect(screen.getByText(/Nome do empreendimento no contrato/)).toBeTruthy();
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

const VILA = {
  id: "c-1",
  nome: "Vila Verde",
  cidade: "Cotia",
  bairro: null,
  status_validacao: "validado" as const,
};

describe("ImovelCartorioCard — condomínio (migration 300)", () => {
  function semResultados() {
    mockBusca.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: false });
  }

  it("renders the control under the readiness alvo id; unanswered saves neither", async () => {
    semResultados();
    const onSave = vi.fn();
    const { screen, fireEvent, container } = await render(undefined, { onSave });
    expect(container.querySelector("#imovel-condominio")).toBeTruthy();
    expect(screen.getByTestId("imovel-condominio-pendente")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ condominio_id: null, casa_de_rua: false }),
    );
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("em_condominio");
  });

  it("attaching from the dropdown saves the condomínio id", async () => {
    mockBusca.mockReturnValue({ data: [VILA], isPending: false, isFetching: false, isError: false });
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(undefined, { onSave });
    fireEvent.change(screen.getByTestId("imovel-condominio-busca"), { target: { value: "vila" } });
    fireEvent.click(screen.getByTestId("imovel-condominio-item-c-1"));
    expect(screen.getByTestId("imovel-condominio-chip").textContent).toContain("Vila Verde");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ condominio_id: "c-1", casa_de_rua: false }),
    );
  });

  it("F91: picking a condomínio persists the link at once (partial patch), without Salvar", async () => {
    mockBusca.mockReturnValue({ data: [VILA], isPending: false, isFetching: false, isError: false });
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(undefined, { onSave });
    fireEvent.change(screen.getByTestId("imovel-condominio-busca"), { target: { value: "vila" } });
    fireEvent.click(screen.getByTestId("imovel-condominio-item-c-1"));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({ condominio_id: "c-1", casa_de_rua: false });
  });

  it("F91: editing a text field shows the unsaved state until Salvar", async () => {
    semResultados();
    const { screen, fireEvent } = await render();
    expect(screen.queryByTestId("imovel-cartorio-nao-salvo")).toBeNull();
    fireEvent.change(document.getElementById("numero-matricula") as HTMLInputElement, {
      target: { value: "999" },
    });
    expect(screen.getByTestId("imovel-cartorio-nao-salvo")).toBeTruthy();
  });

  it("checking 'Casa de rua' detaches and saves casa_de_rua=true", async () => {
    semResultados();
    const onSave = vi.fn();
    const { screen, fireEvent } = await render(
      { condominio_id: "c-1", condominio: VILA, em_condominio: true },
      { onSave },
    );
    expect(screen.getByTestId("imovel-condominio-chip")).toBeTruthy();
    fireEvent.click(screen.getByTestId("imovel-casa-de-rua"));
    expect(screen.queryByTestId("imovel-condominio-chip")).toBeNull();
    expect(screen.queryByTestId("imovel-condominio-busca")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ condominio_id: null, casa_de_rua: true }),
    );
  });
});

describe("ImovelCartorioCard — vinculo_legal markers", () => {
  it("marks fields filled from the manual record and fields in conflict", async () => {
    const { screen } = await render({
      vinculo_legal: {
        manual_codigo: "SW-0001",
        fontes: { numero_matricula: "SW-0001", onus_fonte: "SW-0001" },
        conflitos: ["numero_registro_imoveis"],
        // pointer groups too
      },
    });
    expect(screen.getByTestId("vinculo-legal-numero_matricula").textContent).toBe("do cadastro manual");
    const c = screen.getByTestId("vinculo-legal-numero_registro_imoveis");
    expect(c.textContent).toBe("em conflito — revise");
    expect(c.getAttribute("href")).toBe("#imovel-conflitos");
    expect(screen.getByTestId("vinculo-legal-onus_fonte").textContent).toBe("do cadastro manual");
    expect(screen.queryByTestId("vinculo-legal-situacao_onus")).toBeNull();
  });

  it("no markers without a vínculo", async () => {
    const { screen } = await render();
    expect(screen.queryByTestId("vinculo-legal-numero_matricula")).toBeNull();
  });
});
