/** Julia › Envio (julia-v2 Q6) — the rule is a MINIMUM COMPUTED STAGE fed by agents; no criteria builder, no `grupos`. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfirmProvider } from "@noctusai/lib";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import JuliaEnvio from "./Envio";

const ESTAGIOS = [
  { chave: "quente", rotulo: "Lead quente", ordem: 3, conclusivo: true },
  { chave: "frio", rotulo: "Lead frio", ordem: 1, conclusivo: false },
  { chave: "morno", rotulo: "Lead morno", ordem: 2, conclusivo: false },
];
const REGRAS = { diferenciar: false, regras: [{ operacao: "ambas", estagio_minimo: "morno", versao: 2 }] };
const POL = { frios: { ativo: false, modo: "intervalo", minutos: 60 }, captacoes: "notificar", whatsapp_invalido: false, pesquisa: false };

function setup(regras: unknown = REGRAS, estagios: unknown = ESTAGIOS) {
  api.get.mockImplementation((url: string) => {
    if (url === "/api/julia/qualificacao/estagios")
      return estagios instanceof Error ? Promise.reject(estagios) : Promise.resolve({ data: estagios });
    return Promise.resolve({ data: url.endsWith("/regras") ? regras : POL });
  });
  api.put.mockResolvedValue({});
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ConfirmProvider><JuliaEnvio /></ConfirmProvider></QueryClientProvider>);
}
async function abrir() {
  fireEvent.click(await screen.findByTestId("envio-editar"));
  return screen.findByTestId("envio-wizard");
}

beforeEach(() => { h.admin = true; Object.values(api).forEach((f) => f.mockReset()); });
afterEach(cleanup);

describe("Envio rule — minimum computed stage", () => {
  it("shows a skeleton first, then the rule summary with the stage LABEL and the policy cards", async () => {
    setup();
    expect(screen.getByTestId("envio-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("envio-regras-resumo")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("resumo-ambas").textContent).toContain('"Lead morno"'));
    expect(screen.getByTestId("card-frios")).toBeTruthy();
  });

  it("empty rule: says nothing is sent automatically", async () => {
    setup({ diferenciar: false, regras: [] });
    expect((await screen.findByTestId("resumo-ambas")).textContent).toContain("nenhum lead é enviado");
  });

  it("the dropdown lists the stages in order (from agents) and preselects the saved one", async () => {
    setup();
    const w = await abrir();
    const sel = (await within(w).findByLabelText("Etapa mínima")) as HTMLSelectElement;
    expect([...sel.options].map((o) => o.text)).toEqual(["Selecionar etapa", "1. Lead frio", "2. Lead morno", "3. Lead quente"]);
    expect(sel.value).toBe("morno");
    expect(api.get).toHaveBeenCalledWith("/api/julia/qualificacao/estagios");
  });

  it("saves estagio_minimo and NEVER sends `grupos`", async () => {
    setup();
    const w = await abrir();
    fireEvent.change(await within(w).findByLabelText("Etapa mínima"), { target: { value: "quente" } });
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put).toHaveBeenCalledWith("/api/julia/envio/regras", {
      diferenciar: false,
      regras: [{ operacao: "ambas", estagio_minimo: "quente" }],
    });
    expect(JSON.stringify(api.put.mock.calls[0][1])).not.toContain("grupos");
  });

  it("splits compra/aluguel: one dropdown each, both sent", async () => {
    setup();
    const w = await abrir();
    fireEvent.click(within(w).getByLabelText("Configurações diferentes para compra e aluguel"));
    fireEvent.change(await within(w).findByLabelText("Etapa mínima — Aluguel"), { target: { value: "quente" } });
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put.mock.calls[0][1]).toEqual({
      diferenciar: true,
      regras: [
        { operacao: "compra", estagio_minimo: "morno" },
        { operacao: "aluguel", estagio_minimo: "quente" },
      ],
    });
  });

  it("blocks saving without a stage and without changes (no request)", async () => {
    setup({ diferenciar: false, regras: [] });
    const w = await abrir();
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    expect(within(w).getByTestId("wizard-erro").textContent).toContain("Nenhuma alteração");
    fireEvent.click(within(w).getByLabelText("Configurações diferentes para compra e aluguel"));
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    expect(within(w).getByTestId("wizard-erro").textContent).toContain("escolha a etapa");
    expect(api.put).not.toHaveBeenCalled();
  });

  it.each([
    ["estagio_invalido", "Escolha a etapa"],
    ["operacoes_invalidas", "uma regra para compra"],
  ])("server 422 %s -> pt-BR message", async (code, texto) => {
    api.put.mockReset();
    setup();
    api.put.mockRejectedValue(Object.assign(new Error("[422]"), { status: 422, body: { error: { code, message: "x" } } }));
    const w = await abrir();
    fireEvent.change(await within(w).findByLabelText("Etapa mínima"), { target: { value: "quente" } });
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    expect((await within(w).findByTestId("wizard-erro")).textContent).toContain(texto);
  });

  it("a 422 refusing `grupos` (generic validation error) surfaces the server message, never a silent nothing", async () => {
    setup();
    api.put.mockRejectedValue(Object.assign(new Error("[422]"), { status: 422, body: { error: { code: "validation_error", message: "Campo não permitido: grupos" } } }));
    const w = await abrir();
    fireEvent.change(await within(w).findByLabelText("Etapa mínima"), { target: { value: "frio" } });
    fireEvent.click(within(w).getByTestId("wizard-salvar"));
    expect((await within(w).findByTestId("wizard-erro")).textContent).toContain("grupos");
  });

  it("stages failing to load: error with retry, Save disabled", async () => {
    setup(REGRAS, new Error("404"));
    const w = await abrir();
    expect(await within(w).findByTestId("estagios-erro")).toBeTruthy();
    expect((within(w).getByTestId("wizard-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("no stages published: says so", async () => {
    setup(REGRAS, []);
    const w = await abrir();
    expect(await within(w).findByTestId("estagios-vazio")).toBeTruthy();
  });

  it("a saved stage that no longer exists stays visible (not silently dropped)", async () => {
    setup({ diferenciar: false, regras: [{ operacao: "ambas", estagio_minimo: "antigo" }] });
    const w = await abrir();
    const sel = (await within(w).findByLabelText("Etapa mínima")) as HTMLSelectElement;
    expect([...sel.options].some((o) => o.text.includes("antigo"))).toBe(true);
  });

  it("asks 'Sair da edição?' only when dirty", async () => {
    setup();
    let w = await abrir();
    fireEvent.click(within(w).getAllByLabelText("Fechar")[0]);
    await waitFor(() => expect(screen.queryByTestId("envio-wizard")).toBeNull());

    w = await abrir();
    fireEvent.change(await within(w).findByLabelText("Etapa mínima"), { target: { value: "quente" } });
    fireEvent.click(within(w).getAllByLabelText("Fechar")[0]);
    expect(await screen.findByText(/Sair da edição\?/)).toBeTruthy();
  });

  it("is read-only for non-admins", async () => {
    h.admin = false;
    setup();
    const w = await abrir();
    expect(within(w).getByTestId("envio-readonly")).toBeTruthy();
    expect((await within(w).findByLabelText("Etapa mínima") as HTMLSelectElement).disabled).toBe(true);
    expect(within(w).queryByTestId("wizard-salvar")).toBeNull();
  });
});

describe("Envio policies", () => {
  it("saves the whole policy object on each change", async () => {
    setup();
    const card = await screen.findByTestId("card-captacoes");
    fireEvent.click(within(card).getByLabelText("Enviar ao SW"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/envio/politicas", { ...POL, captacoes: "enviar" }));

    fireEvent.click(within(screen.getByTestId("card-invalido")).getByLabelText("Enviar ao SW"));
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith("/api/julia/envio/politicas", { ...POL, whatsapp_invalido: true }));
  });

  it("frios: enabling unlocks the interval (30 min … 10 h) and 'manhã seguinte'", async () => {
    setup();
    const card = await screen.findByTestId("card-frios");
    const sel = within(card).getByLabelText("Intervalo") as HTMLSelectElement;
    expect(sel.disabled).toBe(true);
    expect([...sel.options].map((o) => o.text)[0]).toBe("30 min");
    expect([...sel.options].map((o) => o.text).at(-1)).toBe("10 horas");
    fireEvent.click(within(card).getByRole("switch"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/envio/politicas", { ...POL, frios: { ...POL.frios, ativo: true } }));
  });

  it("pesquisa notes the official API requirement", async () => {
    setup();
    expect((await screen.findByTestId("card-pesquisa")).textContent).toContain("requer a API oficial");
  });
});
