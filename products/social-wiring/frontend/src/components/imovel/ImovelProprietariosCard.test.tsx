import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ useProprietarios: vi.fn() }));
vi.mock("@/hooks/useImovelRelacionamentos", () => ({
  useImovelProprietarios: m.useProprietarios,
}));

import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ImovelProprietariosCard } from "./ImovelProprietariosCard";
import type { ProprietarioDoImovel } from "@/types/interesses";

afterEach(() => {
  cleanup();
  m.useProprietarios.mockReset();
});

const dono = (id: string, over: Partial<ProprietarioDoImovel> = {}): ProprietarioDoImovel => ({
  id,
  tipo_pessoa: "PF",
  cliente_id: `c-${id}`,
  empresa_id: null,
  nome: `Dono ${id}`,
  documento: "52998224725",
  celular: "+5511999990000",
  email: `${id}@x.com`,
  origem: "matricula",
  created_at: "2026-09-01T10:00:00Z",
  ...over,
});

const ok = (items: ProprietarioDoImovel[]) => ({
  data: { items, total: items.length },
  isPending: false,
  isFetching: false,
  isError: false,
});

const doRender = () =>
  render(
    <MemoryRouter>
      <ImovelProprietariosCard codigo="ONE9001" />
    </MemoryRouter>,
  );

describe("ImovelProprietariosCard", () => {
  it("links a person owner to /vendedores/:id and shows a company by name only", () => {
    m.useProprietarios.mockReturnValue(
      ok([dono("1"), dono("2", { tipo_pessoa: "PJ", cliente_id: null, empresa_id: "e-2", nome: "Construtora X" })]),
    );
    const { getByTestId, queryByTestId, getByText } = doRender();
    expect(getByTestId("proprietario-link-1").getAttribute("href")).toBe("/vendedores/c-1");
    expect(queryByTestId("proprietario-link-2")).toBeNull();
    expect(getByText("Construtora X")).toBeTruthy();
    expect(getByTestId("proprietario-1").textContent).toContain("Matrícula");
  });

  it("says so when the imóvel has no registered owner", () => {
    m.useProprietarios.mockReturnValue(ok([]));
    expect(doRender().getByTestId("proprietarios-vazio")).toBeTruthy();
  });

  it("shows a skeleton only while there is nothing to show, and an error when it fails empty", () => {
    m.useProprietarios.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    expect(doRender().getByTestId("proprietarios-loading")).toBeTruthy();
    cleanup();
    m.useProprietarios.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    expect(doRender().getByTestId("proprietarios-erro")).toBeTruthy();
  });

  it("labels an owner that comes from the linked cadastro, not one of this código", () => {
    m.useProprietarios.mockReturnValue(
      ok([dono("1", { fonte_codigo: "SW-0001" }), dono("2", { fonte_codigo: "ONE9001" })]),
    );
    const { getByTestId, queryByTestId } = doRender();
    expect(getByTestId("proprietario-fonte-1").textContent).toBe("do cadastro SW-0001");
    expect(queryByTestId("proprietario-fonte-2")).toBeNull();
  });
});
