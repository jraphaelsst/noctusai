import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

const useVisitadas = vi.fn();
const mutate = vi.fn();
vi.mock("@/hooks/useRoteirosFeedback", () => ({ useVisitadas: (...a: unknown[]) => useVisitadas(...a) }));
vi.mock("@/hooks/useGerarProposta", () => ({
  useGerarProposta: () => ({ mutate, isPending: false, variables: undefined }),
}));
vi.mock("@/lib/erroServidor", () => ({ toastServerError: vi.fn() }));

import { VisitadasLista } from "./VisitadasLista";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const ok = (data: unknown) => ({ data, isPending: false, isFetching: false, isError: false });

describe("VisitadasLista", () => {
  it("skeletons only while there is no data", () => {
    useVisitadas.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const { getByTestId } = render(<VisitadasLista clienteId="c1" roteiroId="r1" />);
    expect(getByTestId("visitadas-loading")).toBeTruthy();
  });

  it("keeps the list mounted while refetching", () => {
    useVisitadas.mockReturnValue({
      data: [{ visita_id: "v1", imovel_codigo: "ONE9001", titulo: "Apto", realizada_em: null, proposta: null }],
      isPending: false,
      isFetching: true,
      isError: false,
    });
    const { getByTestId, queryByTestId } = render(<VisitadasLista clienteId="c1" roteiroId="r1" />);
    expect(getByTestId("gerar-proposta-v1")).toBeTruthy();
    expect(queryByTestId("visitadas-loading")).toBeNull();
  });

  it("'Gerar proposta' posts the visita; disabled 'Proposta já criada' when one exists", () => {
    useVisitadas.mockReturnValue(
      ok([
        { visita_id: "v1", imovel_codigo: "ONE9001", titulo: "Apto 1", realizada_em: null, proposta: null },
        { visita_id: "v2", imovel_codigo: "ONE9002", titulo: "Apto 2", realizada_em: null, proposta: { id: "p1", status: "enviada" } },
      ]),
    );
    const { getByTestId } = render(<VisitadasLista clienteId="c1" roteiroId="r1" />);

    fireEvent.click(getByTestId("gerar-proposta-v1"));
    expect(mutate).toHaveBeenCalledWith("v1", expect.any(Object));

    const feito = getByTestId("gerar-proposta-v2") as HTMLButtonElement;
    expect(feito.disabled).toBe(true);
    expect(feito.textContent).toBe("Proposta já criada");
  });

  it("says so when nothing was visited", () => {
    useVisitadas.mockReturnValue(ok([]));
    const { getByTestId } = render(<VisitadasLista clienteId="c1" roteiroId="r1" />);
    expect(getByTestId("visitadas-vazio")).toBeTruthy();
  });
});
