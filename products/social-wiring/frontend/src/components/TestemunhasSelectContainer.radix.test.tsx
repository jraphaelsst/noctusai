/**
 * TestemunhasSelectContainer through the REAL Radix `Select` (no
 * `@/components/ui/select` mock) and the REAL query hooks over a mocked
 * `api` — the 2026-10-03 prod bug: on a contract with NO witnesses the two
 * padded slots rendered, but slot 0's pick never stuck and nothing was ever
 * saved. The sibling `TestemunhasSelectContainer.test.tsx` inlines every
 * option through a Select mock, which is exactly what hid it: an empty slot
 * was `value={undefined}` — an UNCONTROLLED Radix Select — which the mock
 * cannot model. Synthetic data only.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const apiGet = vi.fn();
const apiPut = vi.fn();
vi.mock("@noctusai/seed/infra", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    put: (...args: unknown[]) => apiPut(...args),
  },
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TestemunhasSelectContainer } from "./TestemunhasSelectContainer";

function testemunha(id: string, nome: string) {
  return {
    id, nome, cpf: "111.222.333-44", rg: null, celular: null, email: null,
    cpf_pendente: false, contratos_em_uso: 0, excluida: false,
    created_at: null, updated_at: null,
  };
}

const ROSTER = [
  testemunha("t1", "Maria Souza"),
  testemunha("t2", "João Lima"),
  testemunha("t3", "Ana Reis"),
];

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) =>
    Promise.resolve(
      url.includes("/contratos/")
        ? { items: [], total: 0 } // the contract has NO witnesses yet
        : { items: ROSTER, total: ROSTER.length },
    ),
  );
  apiPut.mockImplementation((_url: string, body: { testemunha_ids: string[] }) =>
    Promise.resolve({
      items: body.testemunha_ids.map((id, ordem) => ({
        id: `sel-${id}`,
        ordem,
        testemunha: ROSTER.find((t) => t.id === id),
      })),
      total: body.testemunha_ids.length,
    }),
  );
});

async function renderContainer() {
  const rtl = await import("@testing-library/react");
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const utils = rtl.render(
    <TestemunhasSelectContainer clienteId="cli-1" contratoId="ct-1" aberto />,
    { wrapper },
  );
  // Editable only once the (empty) selection has seeded.
  await rtl.waitFor(() =>
    expect(
      (utils.getByTestId("testemunhas-slot-0") as HTMLButtonElement).disabled,
    ).toBe(false),
  );
  return { ...rtl, ...utils };
}

async function abrir(slot: number) {
  const { screen } = await import("@testing-library/react");
  const userEvent = (await import("@testing-library/user-event")).default;
  const user = userEvent.setup();
  await user.click(screen.getByTestId(`testemunhas-slot-${slot}`));
  return { user, opcoes: () => screen.getAllByRole("option").map((o) => o.textContent) };
}

describe("contrato sem testemunhas — Radix real", () => {
  it("🔴 cada slot vazio é um Select CONTROLADO desde o primeiro render (sem troca não-controlado→controlado)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { screen } = await renderContainer();
    const { user } = await abrir(0);
    await user.click(screen.getByRole("option", { name: "Maria Souza" }));
    const trocas = warn.mock.calls.filter((c) =>
      String(c[0]).includes("changing from uncontrolled to controlled"),
    );
    warn.mockRestore();
    expect(trocas).toEqual([]);
  });

  it("🔴 o slot 0 lista cada testemunha UMA vez", async () => {
    await renderContainer();
    const { opcoes } = await abrir(0);
    expect(opcoes()).toEqual(["Maria Souza", "João Lima", "Ana Reis"]);
  });

  it("🔴 escolher no slot 0 preenche o slot 0 — o slot 1 continua vazio e não oferece a mesma testemunha", async () => {
    const { screen, within } = await renderContainer();
    const { user, opcoes } = await abrir(0);
    await user.click(screen.getByRole("option", { name: "Maria Souza" }));

    expect(within(screen.getByTestId("testemunhas-slot-0")).getByText("Maria Souza")).toBeTruthy();
    expect(within(screen.getByTestId("testemunhas-slot-1")).queryByText("Maria Souza")).toBeNull();
    expect(apiPut).not.toHaveBeenCalled(); // slot 1 still empty

    await user.click(screen.getByTestId("testemunhas-slot-1"));
    expect(opcoes()).toEqual(["João Lima", "Ana Reis"]);
  });

  it("🔴 slot 0 e depois slot 1 salvam duas testemunhas DISTINTAS, na ordem", async () => {
    const { screen, waitFor, within } = await renderContainer();
    const { user } = await abrir(0);
    await user.click(screen.getByRole("option", { name: "Maria Souza" }));
    await user.click(screen.getByTestId("testemunhas-slot-1"));
    await user.click(screen.getByRole("option", { name: "João Lima" }));

    await waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1));
    expect(apiPut.mock.calls[0][0]).toBe("/api/clientes/cli-1/contratos/ct-1/testemunhas");
    expect(apiPut.mock.calls[0][1]).toEqual({ testemunha_ids: ["t1", "t2"] });
    expect(within(screen.getByTestId("testemunhas-slot-0")).getByText("Maria Souza")).toBeTruthy();
    expect(within(screen.getByTestId("testemunhas-slot-1")).getByText("João Lima")).toBeTruthy();
  });
});
