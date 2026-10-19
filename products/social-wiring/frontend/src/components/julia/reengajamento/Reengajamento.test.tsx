import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const h = vi.hoisted(() => ({ admin: true, confirm: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("@noctusai/lib/components", async (orig) => ({ ...(await orig<object>()), useConfirm: () => async () => h.confirm }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ReengajamentoPadraoTab } from "./ReengajamentoPadraoTab";
import { TentativasCard } from "./TentativasCard";
import { ReguaRegrasCard } from "./ReguaRegrasCard";

const CFG = { minutos_ativo: true, minutos_intervalo: 15, horas_ativo: false, horas_intervalo: 2 };
const T = (n: number) => ({ id: `t${n}`, ordem: n, espera_valor: n, espera_unidade: "dias" as const, texto: `msg ${n}`, template_id: null, ativa: true });
const REGUA = (n: number) => ({ id: "r1", nome: "Régua 1", ativa: false, compra: true, aluguel: true, tentativas: Array.from({ length: n }, (_, i) => T(i + 1)) });

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const erro409 = (code: string) => ({ body: { error: { code, message: "x" } } });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  h.admin = true;
  h.confirm = true;
});
afterEach(cleanup);

describe("Reengajamento padrão", () => {
  it("renders cards with Ativo chip and saves minutes via the drawer", async () => {
    api.get.mockResolvedValue({ data: CFG });
    api.put.mockResolvedValue({ data: { ...CFG, minutos_intervalo: 20 } });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    const card = await screen.findByTestId("card-minutos");
    expect(card.textContent).toContain("Ativo");
    expect(screen.getByTestId("card-horas").textContent).toContain("Inativo");
    fireEvent.click(card.querySelector("button")!);
    const sel = (await screen.findByLabelText("Intervalo")) as HTMLSelectElement;
    expect(Array.from(sel.options).map((o) => o.text)).toEqual([
      "5 minutos", "10 minutos", "15 minutos", "20 minutos", "25 minutos", "30 minutos",
      "35 minutos", "40 minutos", "45 minutos", "50 minutos", "55 minutos", "1 hora",
    ]);
    expect(screen.getByText("Funciona em qualquer horário")).toBeTruthy();
    fireEvent.change(sel, { target: { value: "20" } });
    fireEvent.click(screen.getByText("Salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/lais/reengajamento/config", { ...CFG, minutos_intervalo: 20 }));
  });

  it("hours drawer offers 1..11 horas", async () => {
    api.get.mockResolvedValue({ data: CFG });
    wrap(<ReengajamentoPadraoTab isAdmin />);
    fireEvent.click((await screen.findByTestId("card-horas")).querySelector("button")!);
    const sel = (await screen.findByLabelText("Intervalo")) as HTMLSelectElement;
    expect(sel.options.length).toBe(11);
    expect(sel.options[0].text).toBe("1 hora");
    expect(sel.options[10].text).toBe("11 horas");
    expect(screen.getByText("Funciona das 8h às 20h")).toBeTruthy();
  });

  it("shows the error state with retry", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    wrap(<ReengajamentoPadraoTab isAdmin />);
    expect(await screen.findByTestId("reeng-erro")).toBeTruthy();
  });
});

describe("TentativasCard", () => {
  it("empty state + counter 0/3", () => {
    wrap(<TentativasCard regua={REGUA(0)} isAdmin />);
    expect(screen.getByText("Tentativas de contato 0/3")).toBeTruthy();
    expect(screen.getByTestId("tentativas-vazio")).toBeTruthy();
  });

  it("disables 'Nova tentativa' at the 3 limit", () => {
    wrap(<TentativasCard regua={REGUA(3)} isAdmin />);
    expect((screen.getByText("Nova tentativa de contato").closest("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("modelo is disabled with the official-API tooltip; text capped at 1024", () => {
    wrap(<TentativasCard regua={REGUA(0)} isAdmin />);
    fireEvent.click(screen.getByText("Nova tentativa de contato"));
    const modelo = screen.getByLabelText("Modelo") as HTMLButtonElement;
    expect(modelo.disabled).toBe(true);
    expect(modelo.parentElement?.getAttribute("title")).toBe("disponível com a API oficial");
    expect((screen.getByLabelText("Texto da mensagem") as HTMLTextAreaElement).maxLength).toBe(1024);
  });

  it("surfaces 409 limite_tentativas on create", async () => {
    api.post.mockRejectedValue(erro409("limite_tentativas"));
    wrap(<TentativasCard regua={REGUA(1)} isAdmin />);
    fireEvent.click(screen.getByText("Nova tentativa de contato"));
    fireEvent.change(screen.getByLabelText("Texto da mensagem"), { target: { value: "oi" } });
    fireEvent.click(screen.getByText("Salvar"));
    expect((await screen.findByRole("alert")).textContent).toContain("no máximo 3");
  });

  it("delete confirms then calls DELETE; 409 ultima_tentativa_ativa is shown", async () => {
    api.delete.mockRejectedValue(erro409("ultima_tentativa_ativa"));
    wrap(<TentativasCard regua={REGUA(1)} isAdmin />);
    fireEvent.click(screen.getByLabelText("Excluir tentativa 1"));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/lais/reengajamento/reguas/r1/tentativas/t1"));
    expect((await screen.findByRole("alert")).textContent).toContain("ao menos uma tentativa ativa");
  });

  it("does not delete when the confirm is declined", async () => {
    h.confirm = false;
    wrap(<TentativasCard regua={REGUA(1)} isAdmin />);
    fireEvent.click(screen.getByLabelText("Excluir tentativa 1"));
    await new Promise((r) => setTimeout(r, 10));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("non-admin gets no write controls", () => {
    wrap(<TentativasCard regua={REGUA(1)} isAdmin={false} />);
    expect(screen.queryByText("Nova tentativa de contato")).toBeNull();
    expect(screen.queryByLabelText("Excluir tentativa 1")).toBeNull();
  });
});

describe("ReguaRegrasCard", () => {
  it("activation 409 regua_sem_tentativa is shown in the drawer", async () => {
    api.patch.mockResolvedValue({ data: REGUA(0) });
    api.post.mockRejectedValue(erro409("regua_sem_tentativa"));
    wrap(<ReguaRegrasCard regua={REGUA(0)} isAdmin />);
    fireEvent.click(screen.getByText("Editar"));
    fireEvent.click(await screen.findByLabelText("Ativar régua de reengajamento"));
    fireEvent.click(screen.getByText("Salvar"));
    expect((await screen.findByRole("alert")).textContent).toContain("tentativa de contato ativa");
    expect(api.post).toHaveBeenCalledWith("/api/lais/reengajamento/reguas/r1/ativar", {});
  });

  it("Excluir régua asks for confirmation then DELETEs", async () => {
    api.delete.mockResolvedValue({});
    wrap(<ReguaRegrasCard regua={REGUA(0)} isAdmin />);
    fireEvent.click(screen.getByText("Editar"));
    fireEvent.click(await screen.findByText("Excluir régua"));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/lais/reengajamento/reguas/r1"));
  });
});
