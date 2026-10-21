/** ImovelManualModal — create (validation, payload) and edit (prefill, PATCH diff). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";

const { criar, atualizar } = vi.hoisted(() => ({
  criar: vi.fn(),
  atualizar: vi.fn(),
}));
vi.mock("@/hooks/useImovelManual", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/useImovelManual")>();
  return {
    ...actual,
    useCriarImovelManual: () => ({ mutateAsync: criar, isPending: false }),
    useAtualizarImovelManual: () => ({
      mutateAsync: atualizar,
      isPending: false,
    }),
  };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// Migration 300 — the condomínio picker's data layer, mocked at the hook seam.
const { mockBusca } = vi.hoisted(() => ({ mockBusca: vi.fn() }));
vi.mock("@/hooks/useCondominios", () => ({
  useCondominioBusca: mockBusca,
  useCriarCondominio: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
}));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

import ImovelManualModal, { parseNumero } from "./ImovelManualModal";
import type { Imovel } from "@/hooks/useImoveis";

beforeEach(() => {
  criar.mockReset();
  atualizar.mockReset();
  mockBusca.mockReset();
  mockBusca.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: false });
});
afterEach(cleanup);

const typed = (id: string, value: string, get: (t: string) => HTMLElement) =>
  fireEvent.change(get(id), { target: { value } });

describe("ImovelManualModal — create", () => {
  it("blocks submit and shows required-field + format errors, no request sent", () => {
    const onSaved = vi.fn();
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={vi.fn()} onSaved={onSaved} />,
    );
    typed("imovel-manual-end-uf", "S", getByTestId);
    typed("imovel-manual-end-cep", "123", getByTestId);
    fireEvent.click(getByTestId("imovel-manual-salvar"));

    expect(getByTestId("imovel-manual-titulo-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-end-logradouro-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-end-numero-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-end-bairro-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-end-cidade-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-end-uf-erro").textContent).toContain(
      "2 letras",
    );
    expect(getByTestId("imovel-manual-end-cep-erro")).toBeTruthy();
    expect(criar).not.toHaveBeenCalled();
  });

  it("rejects a bad Drive URL and a non-positive valor", () => {
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={vi.fn()} />,
    );
    typed("imovel-manual-drive", "https://example.com/x", getByTestId);
    typed("imovel-manual-valor_venda", "0", getByTestId);
    typed("imovel-manual-vagas", "-1", getByTestId);
    fireEvent.click(getByTestId("imovel-manual-salvar"));
    expect(getByTestId("imovel-manual-drive-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-valor_venda-erro")).toBeTruthy();
    expect(getByTestId("imovel-manual-vagas-erro")).toBeTruthy();
  });

  it("submits the ImovelManualIn payload and reports the generated código", async () => {
    criar.mockResolvedValue({ codigo: "SW-0001" });
    const onSaved = vi.fn();
    const onOpenChange = vi.fn();
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={onOpenChange} onSaved={onSaved} />,
    );
    typed("imovel-manual-titulo", " Al. Liverpool 81 ", getByTestId);
    typed("imovel-manual-status", "Venda", getByTestId);
    typed("imovel-manual-end-logradouro", "Alameda Liverpool", getByTestId);
    typed("imovel-manual-end-numero", "81", getByTestId);
    typed("imovel-manual-end-bairro", "Reserva do Vianna", getByTestId);
    typed("imovel-manual-end-cidade", "Cotia", getByTestId);
    typed("imovel-manual-end-uf", "sp", getByTestId);
    typed("imovel-manual-end-cep", "06700-000", getByTestId);
    typed("imovel-manual-valor_venda", "1.250.000,50", getByTestId);
    typed("imovel-manual-dormitorios", "3", getByTestId);
    typed("imovel-manual-processo", "876", getByTestId);
    typed(
      "imovel-manual-drive",
      "https://drive.google.com/drive/folders/1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK",
      getByTestId,
    );
    fireEvent.click(getByTestId("imovel-manual-salvar"));

    await waitFor(() => expect(criar).toHaveBeenCalledTimes(1));
    const body = criar.mock.calls[0][0];
    expect(body).toMatchObject({
      titulo: "Al. Liverpool 81",
      status: "Venda",
      finalidades: ["venda"],
      valor_venda: 1250000.5,
      valor_locacao: null,
      dormitorios: 3,
      suites: null,
      processo_atual_numero: "876",
      // Migration 300 — an untouched control is NOT an explicit "não": the
      // old checkbox defaulted to false and saved "fora de condomínio".
      condominio_id: null,
      casa_de_rua: false,
      drive_folder_url:
        "https://drive.google.com/drive/folders/1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK",
      endereco: {
        logradouro: "Alameda Liverpool",
        numero: "81",
        complemento: null,
        bairro: "Reserva do Vianna",
        cidade: "Cotia",
        uf: "SP",
        cep: "06700-000",
      },
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("SW-0001"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows the server error message and keeps the modal open", async () => {
    criar.mockRejectedValue(new Error("endereco incompleto"));
    const onOpenChange = vi.fn();
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={onOpenChange} />,
    );
    typed("imovel-manual-titulo", "X", getByTestId);
    typed("imovel-manual-end-logradouro", "R", getByTestId);
    typed("imovel-manual-end-numero", "1", getByTestId);
    typed("imovel-manual-end-bairro", "B", getByTestId);
    typed("imovel-manual-end-cidade", "C", getByTestId);
    typed("imovel-manual-end-uf", "SP", getByTestId);
    fireEvent.click(getByTestId("imovel-manual-salvar"));
    await waitFor(() =>
      expect(getByTestId("imovel-manual-erro").textContent).toBe(
        "endereco incompleto",
      ),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe("ImovelManualModal — edit", () => {
  const imovel = {
    codigo: "SW-0001",
    titulo: "Al. Liverpool 81",
    categoria: "Casa",
    status: "Venda",
    finalidades: ["Venda"],
    logradouro: "Alameda Liverpool",
    numero: "81",
    complemento: null,
    bairro: "Reserva do Vianna",
    cidade: "Cotia",
    uf: "SP",
    cep: "06700-000",
    empreendimento: "Reserva do Vianna",
    condominio_id: "c-1",
    condominio: { id: "c-1", nome: "Reserva do Vianna", cidade: "Cotia", bairro: null, status_validacao: "validado" },
    casa_de_rua: false,
    em_condominio: true,
    valor_venda: 1250000,
    valor_locacao: null,
    dormitorios: 3,
    referencias: {
      processo_atual_numero: "876",
      drive_folder_url: null,
      drive_folder_id: null,
    },
  } as unknown as Imovel;

  it("prefills every group from the imóvel", () => {
    const { getByTestId } = render(
      <ImovelManualModal
        open
        onOpenChange={vi.fn()}
        imovel={imovel}
      />,
    );
    expect(
      (getByTestId("imovel-manual-titulo") as HTMLInputElement).value,
    ).toBe("Al. Liverpool 81");
    expect(
      (getByTestId("imovel-manual-end-bairro") as HTMLInputElement).value,
    ).toBe("Reserva do Vianna");
    expect(
      (getByTestId("imovel-manual-valor_venda") as HTMLInputElement).value,
    ).toBe("1250000");
    expect(
      (getByTestId("imovel-manual-processo") as HTMLInputElement).value,
    ).toBe("876");
    expect(getByTestId("imovel-condominio-chip").textContent).toContain("Reserva do Vianna");
  });

  it("checking 'Casa de rua' on edit PATCHes the detach + flag only", async () => {
    atualizar.mockResolvedValue({ codigo: "SW-0001" });
    const { getByTestId, queryByTestId } = render(
      <ImovelManualModal open onOpenChange={vi.fn()} imovel={imovel} />,
    );
    fireEvent.click(getByTestId("imovel-casa-de-rua"));
    expect(queryByTestId("imovel-condominio-chip")).toBeNull();
    fireEvent.click(getByTestId("imovel-manual-salvar"));
    await waitFor(() => expect(atualizar).toHaveBeenCalledTimes(1));
    expect(atualizar.mock.calls[0][0]).toEqual({ condominio_id: null, casa_de_rua: true });
  });

  it("an imóvel with no answer opens unanswered (never 'fora de condomínio')", () => {
    const semResposta = { ...imovel, condominio_id: null, condominio: null, em_condominio: null } as Imovel;
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={vi.fn()} imovel={semResposta} />,
    );
    expect(getByTestId("imovel-casa-de-rua").getAttribute("data-state")).toBe("unchecked");
    expect(getByTestId("imovel-condominio-pendente")).toBeTruthy();
  });

  it("PATCHes only the changed fields (emptied → null)", async () => {
    atualizar.mockResolvedValue({ codigo: "SW-0001" });
    const { getByTestId } = render(
      <ImovelManualModal open onOpenChange={vi.fn()} imovel={imovel} />,
    );
    typed("imovel-manual-titulo", "Al. Liverpool 81 — reformada", getByTestId);
    typed("imovel-manual-dormitorios", "", getByTestId);
    fireEvent.click(getByTestId("imovel-manual-salvar"));
    await waitFor(() => expect(atualizar).toHaveBeenCalledTimes(1));
    expect(atualizar.mock.calls[0][0]).toEqual({
      titulo: "Al. Liverpool 81 — reformada",
      dormitorios: null,
    });
    expect(criar).not.toHaveBeenCalled();
  });
});

describe("parseNumero", () => {
  it("parses pt-BR and plain decimals; blank is null; garbage is NaN", () => {
    expect(parseNumero("1.234,56")).toBe(1234.56);
    expect(parseNumero("1234.56")).toBe(1234.56);
    expect(parseNumero("  ")).toBeNull();
    expect(Number.isNaN(parseNumero("abc"))).toBe(true);
  });
});
