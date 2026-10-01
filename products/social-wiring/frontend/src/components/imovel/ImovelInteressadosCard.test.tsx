import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ useInteressados: vi.fn() }));
vi.mock("@/hooks/useImovelRelacionamentos", () => ({
  useImovelInteressados: m.useInteressados,
  useImovelSimilares: vi.fn(),
}));

import { cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ImovelInteressadosCard } from "./ImovelInteressadosCard";
import type { InteressadoRow } from "@/types/interesses";

afterEach(() => {
  cleanup();
  m.useInteressados.mockReset();
});

const row = (n: number, over: Partial<InteressadoRow> = {}): InteressadoRow => ({
  interesse_id: `i${n}`,
  cliente_id: `c${n}`,
  nome: `Pessoa ${n}`,
  telefone: "+5548999990000",
  email: `p${n}@x.com`,
  origem: "lead",
  interesse_created_at: "2026-09-01T10:00:00Z",
  lead_created_at: "2026-08-20T10:00:00Z",
  ultima_interacao_em: null,
  tem_atendimento_aberto: false,
  atendimento_aberto_id: null,
  ...over,
});

const ok = (items: InteressadoRow[], total = items.length) => ({
  data: { items, total },
  isPending: false,
  isFetching: false,
  isError: false,
});

const doRender = () =>
  render(
    <MemoryRouter>
      <ImovelInteressadosCard codigo="ONE9001" />
    </MemoryRouter>,
  );

describe("ImovelInteressadosCard", () => {
  it("lists name (linked to the person page), WhatsApp, email, origem, badge, último contato", () => {
    m.useInteressados.mockReturnValue(
      ok([row(1, { tem_atendimento_aberto: true, atendimento_aberto_id: "a1" }), row(2)]),
    );
    const { getByTestId, queryByTestId } = doRender();
    const r1 = getByTestId("interessado-i1");
    expect(r1.querySelector("a[href='/clientes/c1']")?.textContent).toBe("Pessoa 1");
    expect(r1.querySelector("[data-testid='interessado-whatsapp']")?.getAttribute("href")).toBe(
      "https://wa.me/5548999990000",
    );
    expect(r1.querySelector("a[href='mailto:p1@x.com']")).toBeTruthy();
    expect(r1.textContent).toContain("Lead");
    expect(r1.querySelector("[data-testid='interessado-atendimento-aberto']")).toBeTruthy();
    expect(r1.querySelector("[data-testid='interessado-ultimo-contato']")?.textContent).toContain("—");
    expect(
      getByTestId("interessado-i2").querySelector("[data-testid='interessado-atendimento-aberto']"),
    ).toBeNull();
    expect(queryByTestId("interessados-anterior")).toBeNull(); // single page
  });

  it("paginates with limit/offset", () => {
    m.useInteressados.mockReturnValue(ok([row(1)], 45));
    const { getByTestId } = doRender();
    expect(m.useInteressados).toHaveBeenLastCalledWith("ONE9001", { limit: 20, offset: 0 });
    expect((getByTestId("interessados-anterior") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(getByTestId("interessados-proxima"));
    expect(m.useInteressados).toHaveBeenLastCalledWith("ONE9001", { limit: 20, offset: 20 });
  });

  it("empty / error / first-load states", () => {
    m.useInteressados.mockReturnValue(ok([]));
    expect(doRender().queryByTestId("interessados-vazio")).toBeTruthy();
    cleanup();
    m.useInteressados.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    expect(doRender().queryByTestId("interessados-erro")).toBeTruthy();
    cleanup();
    m.useInteressados.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    expect(doRender().queryByTestId("interessados-loading")).toBeTruthy();
  });
});
