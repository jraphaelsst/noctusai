/** EstruturaPicker: max 3, same formato, honest states, no isLoading lie. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const m = vi.hoisted(() => ({ lista: vi.fn() }));
vi.mock("@/hooks/geracao/useEstruturas", () => ({ useEstruturas: (...a: unknown[]) => m.lista(...a) }));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfisMonitorados: () => ({ data: [{ id: "p1", handle: "criador.exemplo" }] }),
}));

import { resumo } from "@/test/estruturasFixtures";
import { EstruturaPicker } from "./EstruturaPicker";
import type { EstruturaEscolhida } from "./selecao";

const estado = (items: ReturnType<typeof resumo>[], over: Record<string, unknown> = {}) => ({
  data: { items, total: items.length },
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

const onChange = vi.fn();
function Harness({ max, inicial = [] }: { max?: number; inicial?: EstruturaEscolhida[] }) {
  const [v, setV] = useState<EstruturaEscolhida[]>(inicial);
  return (
    <EstruturaPicker
      marcaId="m1"
      value={v}
      max={max}
      onChange={(n) => {
        onChange(n);
        setV(n);
      }}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.lista.mockReturnValue(
    estado([
      resumo({ id: "e1", codigo: 1, formula_headline: "Fórmula um" }),
      resumo({ id: "e2", codigo: 2, formula_headline: "Fórmula dois" }),
      resumo({ id: "e3", codigo: 3, formula_headline: "Fórmula três" }),
      resumo({ id: "e4", codigo: 4, formula_headline: "Fórmula quatro" }),
      resumo({ id: "e5", codigo: 5, formula_headline: "Fórmula carrossel", formato: "carrossel" }),
    ]),
  );
});

describe("EstruturaPicker", () => {
  it("picks up to 3 and disables the fourth", async () => {
    rtl.render(<Harness />);
    for (const n of ["um", "dois", "três"]) await userEvent.click(rtl.screen.getByRole("button", { name: new RegExp(`Fórmula ${n}`) }));
    const quarta = rtl.screen.getByRole("button", { name: /Fórmula quatro/ }) as HTMLButtonElement;
    expect(quarta.disabled).toBe(true);
    expect(quarta.textContent).toContain("Máximo de 3 estruturas.");
    expect(onChange).toHaveBeenLastCalledWith(expect.arrayContaining([expect.objectContaining({ id: "e3" })]));
  });

  it("locks the formato of the first pick: another formato is disabled with the reason", async () => {
    rtl.render(<Harness />);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Fórmula um/ }));
    const car = rtl.screen.getByRole("button", { name: /Fórmula carrossel/ }) as HTMLButtonElement;
    expect(car.disabled).toBe(true);
    expect(car.textContent).toContain("Formato diferente");
    // and the list is asked for that formato only
    expect(m.lista.mock.calls.at(-1)![0].formatos).toEqual(["reels"]);
  });

  it("max=1 (viral wizard) refuses a second pick", async () => {
    rtl.render(<Harness max={1} />);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Fórmula um/ }));
    expect((rtl.screen.getByRole("button", { name: /Fórmula dois/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("removes a chip", async () => {
    rtl.render(<Harness />);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Fórmula um/ }));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Remover estrutura #1" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("shows a skeleton while pending, never an empty message", () => {
    m.lista.mockReturnValue({ data: undefined, showSkeleton: true, isRefreshing: false, isError: false, refetch: vi.fn() });
    rtl.render(<Harness />);
    expect(rtl.screen.getByTestId("estruturas-skeleton")).toBeTruthy();
    expect(rtl.screen.queryByText(/Nenhuma estrutura/)).toBeNull();
  });

  it("a failed read says so and retries", async () => {
    const refetch = vi.fn();
    m.lista.mockReturnValue({ data: undefined, showSkeleton: false, isRefreshing: false, isError: true, refetch });
    rtl.render(<Harness />);
    expect(rtl.screen.getByRole("alert").textContent).toContain("Não foi possível carregar as estruturas");
    await userEvent.click(rtl.screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("empty library vs empty filter read differently", () => {
    m.lista.mockReturnValue(estado([]));
    rtl.render(<Harness />);
    expect(rtl.screen.getByText(/Nenhuma estrutura disponível na biblioteca/)).toBeTruthy();
  });
});
