/** Lais › Envio — wizard (OR/AND, locked base criterion, steps, exit), policy cards. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfirmProvider } from "@noctusai/lib";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import LaisEnvio from "./Envio";

const BASE = { campo: "comportamento", operador: "=", valor: "qualificado" };
const REGRAS = { regras: [{ operacao: "ambas", grupos: [[BASE]] }] };
const POL = { frios: { ativo: false, modo: "intervalo", minutos: 60 }, captacoes: "notificar", whatsapp_invalido: false, pesquisa: false };

function setup(regras: unknown = REGRAS) {
  api.get.mockImplementation((url: string) =>
    Promise.resolve({ data: url.endsWith("/regras") ? regras : POL }));
  api.put.mockResolvedValue({});
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ConfirmProvider><LaisEnvio /></ConfirmProvider></QueryClientProvider>);
}
async function abrir() {
  fireEvent.click(await screen.findByTestId("envio-editar"));
  return screen.findByTestId("envio-wizard");
}
const pick = (el: HTMLElement, label: string, value: string) =>
  fireEvent.change(within(el).getByLabelText(label), { target: { value } });

beforeEach(() => { h.admin = true; Object.values(api).forEach((f) => f.mockReset()); });
afterEach(cleanup);

describe("Envio wizard", () => {
  it("shows a skeleton first, then the summary and policy cards", async () => {
    setup();
    expect(screen.getByTestId("envio-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("envio-regras-resumo")).toBeTruthy();
    expect(screen.getByTestId("card-frios")).toBeTruthy();
  });

  it("locks the base criterion (no remove, no selects) and builds AND / OR", async () => {
    setup();
    const w = await abrir();
    const base = within(w).getByTestId("crit-0-0");
    expect(base.textContent).toContain("Comportamento = Qualificado via inteligência da Julia");
    expect(within(base).queryByLabelText("Remover critério")).toBeNull();

    fireEvent.click(within(w).getByTestId("combinar-0")); // AND inside group 0
    expect(within(w).getAllByText("E").length).toBe(1);
    fireEvent.click(within(w).getByTestId("adicionar-grupo")); // new OR group
    expect(within(w).getByText("OU")).toBeTruthy();
    expect(within(w).getByTestId("grupo-1")).toBeTruthy();
  });

  it("blocks Próximo on an incomplete criterion, then saves AND/OR on step 2", async () => {
    setup();
    const w = await abrir();
    fireEvent.click(within(w).getByTestId("combinar-0"));
    fireEvent.click(within(w).getByTestId("wizard-proximo"));
    expect(within(w).getByTestId("wizard-erro").textContent).toContain("Selecione o critério");

    const c = within(w).getByTestId("crit-0-1");
    pick(c, "Critério", "orcamento");
    pick(c, "Condição", "entre");
    fireEvent.change(within(c).getByLabelText("De"), { target: { value: "100000" } });
    fireEvent.change(within(c).getByLabelText("Até"), { target: { value: "300000" } });
    fireEvent.click(within(w).getByTestId("adicionar-grupo"));
    pick(within(w).getByTestId("crit-1-0"), "Critério", "visita_solicitada");

    fireEvent.click(within(w).getByTestId("wizard-proximo"));
    expect(within(w).getByText(/Passo 2 de 2/)).toBeTruthy();
    expect(within(w).getByTestId("resumo-grupo-0").textContent).toContain("Comportamento — Qualificado via inteligência da Julia E Orçamento: de R$ 100.000 até R$ 300.000");
    expect(within(w).getByTestId("resumo-grupo-1").textContent).toContain("Visita");

    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put).toHaveBeenCalledWith("/api/lais/envio/regras", {
      regras: [{ operacao: "ambas", grupos: [
        [BASE, { campo: "orcamento", operador: "entre", valor: [100000, 300000] }],
        [{ campo: "visita_solicitada", operador: "=", valor: true }],
      ] }],
    });
  });

  it("splits compra/aluguel with separate tabs and sends both rules", async () => {
    setup();
    const w = await abrir();
    fireEvent.click(within(w).getByLabelText("Configurações diferentes para compra e aluguel"));
    fireEvent.click(within(w).getByRole("tab", { name: "Aluguel" }));
    fireEvent.click(within(w).getByTestId("combinar-0"));
    pick(within(w).getByTestId("crit-0-1"), "Critério", "nome");
    fireEvent.click(within(w).getByTestId("wizard-proximo"));
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const body = api.put.mock.calls[0][1] as { regras: { operacao: string; grupos: unknown[][] }[] };
    expect(body.regras.map((r) => r.operacao)).toEqual(["compra", "aluguel"]);
    expect(body.regras[0].grupos[0].length).toBe(1);
    expect(body.regras[1].grupos[0].length).toBe(2);
  });

  it("asks 'Sair da edição?' only when dirty", async () => {
    setup();
    let w = await abrir();
    fireEvent.click(within(w).getAllByLabelText("Fechar")[0]);
    await waitFor(() => expect(screen.queryByTestId("envio-wizard")).toBeNull());

    w = await abrir();
    fireEvent.click(within(w).getByTestId("combinar-0"));
    fireEvent.click(within(w).getAllByLabelText("Fechar")[0]);
    expect(await screen.findByText(/Sair da edição\?/)).toBeTruthy();
  });

  it("is read-only for non-admins", async () => {
    h.admin = false;
    setup();
    const w = await abrir();
    expect(within(w).getByTestId("envio-readonly")).toBeTruthy();
    expect((within(w).getByTestId("adicionar-grupo") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("Envio policies", () => {
  it("saves the whole policy object on each change", async () => {
    setup();
    const card = await screen.findByTestId("card-captacoes");
    fireEvent.click(within(card).getByLabelText("Enviar ao SW"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/lais/envio/politicas", { ...POL, captacoes: "enviar" }));

    fireEvent.click(within(screen.getByTestId("card-invalido")).getByLabelText("Enviar ao SW"));
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith("/api/lais/envio/politicas", { ...POL, whatsapp_invalido: true }));
  });

  it("frios: enabling unlocks the interval (30 min … 10 h) and 'manhã seguinte'", async () => {
    setup();
    const card = await screen.findByTestId("card-frios");
    const sel = within(card).getByLabelText("Intervalo") as HTMLSelectElement;
    expect(sel.disabled).toBe(true);
    expect([...sel.options].map((o) => o.text)[0]).toBe("30 min");
    expect([...sel.options].map((o) => o.text).at(-1)).toBe("10 horas");
    fireEvent.click(within(card).getByRole("switch"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/lais/envio/politicas", { ...POL, frios: { ...POL.frios, ativo: true } }));
  });

  it("pesquisa notes the official API requirement", async () => {
    setup();
    expect((await screen.findByTestId("card-pesquisa")).textContent).toContain("requer a API oficial");
  });
});
