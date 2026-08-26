/**
 * RoteirosSection — the card's Roteiros tab.
 *
 * The load-bearing assertions are the CONTABILIZAÇÃO (three buckets, never
 * two) and the LOADING GATE (an empty state must never render over roteiros
 * that exist during a background refetch — `KB § PATTERNS/frontend/
 * lying-loading-state.md`).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { RoteirosSection, type RoteirosSectionProps } from "./RoteirosSection";
import type { ImovelVisita, Roteiro, Visita } from "@/types/cardHub";

function imovel(codigo: string, over: Partial<ImovelVisita> = {}): ImovelVisita {
  return {
    codigo,
    titulo: `Apartamento ${codigo}`,
    empreendimento: "Edifício Aurora",
    logradouro: "Rua das Palmeiras",
    numero: "320",
    complemento: null,
    bairro: "Centro",
    cidade: "Florianópolis",
    uf: "SC",
    cep: "88010-000",
    foto_destaque: null,
    captacao: null,
    corretores: [{ nome: "Ana Prado", email: null }],
    ativo_no_vista: true,
    fonte: "imoveis",
    ...over,
  };
}

function visita(id: string, codigo: string, over: Partial<Visita> = {}): Visita {
  return {
    id,
    roteiro_id: "r1",
    codigo,
    ordem: 0,
    status: "pendente",
    observacao: null,
    feedback_em: null,
    created_at: "2026-08-25T12:00:00+00:00",
    imovel: imovel(codigo),
    ...over,
  };
}

function roteiro(over: Partial<Roteiro> = {}): Roteiro {
  const visitas = over.visitas ?? [visita("v1", "ONE9001")];
  return {
    id: "r1",
    atendimento_id: "a1",
    titulo: "Terça de manhã",
    created_at: "2026-08-25T12:00:00+00:00",
    visitas,
    contagem: {
      total: visitas.length,
      realizadas: visitas.filter((v) => v.status === "realizada").length,
      nao_realizadas: visitas.filter((v) => v.status === "nao_realizada").length,
      pendentes: visitas.filter((v) => v.status === "pendente").length,
    },
    ...over,
  };
}

function baseProps(overrides: Partial<RoteirosSectionProps> = {}): RoteirosSectionProps {
  return {
    roteiros: [],
    onCriar: vi.fn(),
    onRemover: vi.fn(),
    onGerarPdf: vi.fn(),
    onPatchVisita: vi.fn(),
    ...overrides,
  };
}

async function render(props: RoteirosSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(RoteirosSection, props));
}

describe("RoteirosSection — states", () => {
  it("offers Criar Roteiro even with nothing to show", async () => {
    // You come to this tab to ADD; an empty state with no way out is a dead end.
    const { getByTestId } = await render(baseProps());
    expect(getByTestId("roteiros-empty")).toBeTruthy();
    expect(getByTestId("roteiro-criar-trigger")).toBeTruthy();
  });

  it("🔴 never renders the empty state while loading", async () => {
    // The lying-loading-state class: the caller gates on `isPending ||
    // isFetching`, so a background refetch must show the skeleton, NOT
    // "nenhum roteiro criado" over roteiros that exist.
    const { getByTestId, queryByTestId } = await render(
      baseProps({ loading: true, roteiros: [] }),
    );
    expect(getByTestId("roteiros-loading")).toBeTruthy();
    expect(queryByTestId("roteiros-empty")).toBeNull();
  });

  it("shows an error instead of an empty list", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({ error: "Não foi possível carregar os roteiros." }),
    );
    expect(getByTestId("roteiros-erro")).toBeTruthy();
    expect(queryByTestId("roteiros-empty")).toBeNull();
  });
});

describe("RoteirosSection — contabilização", () => {
  it("🔴 renders three buckets, never two", async () => {
    const { getByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE9001", { status: "realizada", feedback_em: "2026-08-26T10:00:00+00:00" }),
              visita("v2", "ONE9002", { status: "nao_realizada", feedback_em: "2026-08-26T11:00:00+00:00" }),
              visita("v3", "ONE9003"),
            ],
          }),
        ],
      }),
    );
    const texto = getByTestId("roteiro-contagem").textContent ?? "";
    expect(texto).toContain("1 realizadas");
    expect(texto).toContain("1 não realizadas");
    expect(texto).toContain("1 pendentes");
  });
});

describe("RoteirosSection — outcomes", () => {
  it("records an outcome with the visita id", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId } = await render(baseProps({ roteiros: [roteiro()], onPatchVisita }));
    const rtl = await import("@testing-library/react");

    rtl.fireEvent.click(getByTestId("visita-status-realizada-v1"));
    expect(onPatchVisita).toHaveBeenCalledWith("r1", "v1", { status: "realizada" });
  });

  it("saves the observação on blur, not on every keystroke", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId } = await render(baseProps({ roteiros: [roteiro()], onPatchVisita }));
    const rtl = await import("@testing-library/react");
    const campo = getByTestId("visita-observacao-v1");

    rtl.fireEvent.change(campo, { target: { value: "não atendeu" } });
    expect(onPatchVisita).not.toHaveBeenCalled();

    rtl.fireEvent.blur(campo);
    expect(onPatchVisita).toHaveBeenCalledWith("r1", "v1", { observacao: "não atendeu" });
  });

  it("does not PATCH an unchanged observação", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId } = await render(
      baseProps({
        roteiros: [roteiro({ visitas: [visita("v1", "ONE9001", { observacao: "já escrito" })] })],
        onPatchVisita,
      }),
    );
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.blur(getByTestId("visita-observacao-v1"));
    expect(onPatchVisita).not.toHaveBeenCalled();
  });
});

describe("RoteirosSection — Gerar Roteiro", () => {
  it("asks for the PDF by roteiro id", async () => {
    const onGerarPdf = vi.fn();
    const { getByTestId } = await render(baseProps({ roteiros: [roteiro()], onGerarPdf }));
    const rtl = await import("@testing-library/react");

    rtl.fireEvent.click(getByTestId("roteiro-pdf-r1"));
    expect(onGerarPdf).toHaveBeenCalledWith("r1");
  });

  it("is disabled on an empty roteiro", async () => {
    // The API answers 422 rather than handing back a zero-page file; disabling
    // here means the user never meets that error.
    const { getByTestId } = await render(
      baseProps({ roteiros: [roteiro({ visitas: [] })] }),
    );
    expect((getByTestId("roteiro-pdf-r1") as HTMLButtonElement).disabled).toBe(true);
  });

  it("spins only the roteiro being generated", async () => {
    const dois = [roteiro(), roteiro({ id: "r2", visitas: [visita("v9", "ONE9009", { roteiro_id: "r2" })] })];
    const { getByTestId } = await render(baseProps({ roteiros: dois, pdfPendingId: "r1" }));
    expect((getByTestId("roteiro-pdf-r1") as HTMLButtonElement).disabled).toBe(true);
    expect((getByTestId("roteiro-pdf-r2") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("RoteirosSection — a delisted imóvel", () => {
  it("says so, and still renders what the registry snapshot holds", async () => {
    // `imovel` is never null (the FK guarantees a registry row), but a sold
    // property carries no street — the badge is what explains the blanks.
    const { getByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE4770", {
                imovel: imovel("ONE4770", {
                  ativo_no_vista: false,
                  fonte: "registry",
                  empreendimento: null,
                  logradouro: null,
                  numero: null,
                  corretores: [],
                }),
              }),
            ],
          }),
        ],
      }),
    );
    expect(getByTestId("imovel-fora-do-catalogo")).toBeTruthy();
    expect(getByTestId("imovel-visita-ONE4770").textContent).toContain("Centro");
  });
});

describe("RoteirosSection — owner data (D1)", () => {
  it("renders the labels with an em-dash rather than hiding them", async () => {
    // User-ratified 2026-08-25: Vista exposes no proprietário, so the slot
    // ships empty. The LABEL still prints — a corretor must see that the field
    // exists and is unknown, not wonder whether it was dropped.
    // Destination when a source exists: `imovel_dados` (migration 075).
    const { getByTestId } = await render(baseProps({ roteiros: [roteiro()] }));
    const texto = getByTestId("imovel-proprietario").textContent ?? "";
    expect(texto).toContain("Proprietário");
    expect(texto).toContain("Celular");
    expect(texto).toContain("—");
  });
});
