/** Julia › Proteção — every limit visible with its default and range, validation before save, the lead document prompt, the blocklist
 *  (manual block with a REQUIRED reason, automatic ones labelled, unblock through a design-system dialog), every state, the admin gate. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import JuliaProtecao from "./Protecao";

const FAIXAS = {
  entrada_limite: [1, 500], entrada_janela_s: [10, 3600], midia_limite_chat_dia: [0, 10000], midia_limite_conexao_dia: [0, 100000],
  bloqueio_auto_limiar: [1, 100], bloqueio_auto_janela_min: [1, 1440], bloqueio_auto_duracao_min: [1, 43200],
};
const CFG = (over: Record<string, unknown> = {}) => ({
  entrada_limite: 20, entrada_janela_s: 60, midia_limite_chat_dia: 10, midia_limite_conexao_dia: 200, bloqueio_auto_ativo: true,
  bloqueio_auto_limiar: 3, bloqueio_auto_janela_min: 60, bloqueio_auto_duracao_min: 1440, prompt_documento_lead: null, padrao: true,
  atualizado_em: null, faixas: FAIXAS,
  padroes: { entrada_limite: 20, entrada_janela_s: 60, midia_limite_chat_dia: 10, midia_limite_conexao_dia: 200, bloqueio_auto_limiar: 3,
    bloqueio_auto_janela_min: 60, bloqueio_auto_duracao_min: 1440 },
  prompt_documento_padrao: "Identifique apenas o TIPO do documento…", ...over,
});
const B = (over: Record<string, unknown> = {}) => ({
  id: "b1", numero: "5511977770001", motivo: "spam de links", origem: "manual", gatilho: "manual", criado_por: "u1",
  criado_em: "2026-10-21T12:00:00Z", expira_em: null, ativo: true, desbloqueado_por: null, desbloqueado_em: null,
  notificacao_status: "nao_aplica", ...over,
});

function setup({ config = CFG() as unknown | Error, bloqueios = [B()] as unknown[] | Error } = {}) {
  api.get.mockImplementation((u: string) => {
    if (u.includes("/bloqueios"))
      return bloqueios instanceof Error ? Promise.reject(bloqueios) : Promise.resolve({ data: { items: bloqueios } });
    return config instanceof Error ? Promise.reject(config) : Promise.resolve({ data: config });
  });
  api.put.mockResolvedValue({ data: {} });
  api.post.mockResolvedValue({ data: {} });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><JuliaProtecao /></QueryClientProvider>);
}
beforeEach(() => { vi.clearAllMocks(); h.admin = true; });
afterEach(cleanup);

describe("limites", () => {
  it("shows a skeleton, then every limit with its range and default, flagged as the platform default", async () => {
    setup();
    expect(screen.getByTestId("protecao-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("limites-form")).toBeTruthy();
    expect(screen.getByTestId("limites-padrao")).toBeTruthy();
    expect((screen.getByTestId("limite-entrada_limite") as HTMLInputElement).value).toBe("20");
    expect(screen.getByTestId("faixa-midia_limite_chat_dia").textContent).toContain("de 0 a 10000 · padrão 10");
    expect((screen.getByTestId("limite-midia_limite_conexao_dia") as HTMLInputElement).value).toBe("200");
  });

  it("saves the whole set with numbers, the toggle and a null prompt when empty", async () => {
    setup();
    fireEvent.change(await screen.findByTestId("limite-entrada_limite"), { target: { value: "5" } });
    fireEvent.click(screen.getByTestId("limites-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/api/julia/protecao/config");
    expect(body).toMatchObject({ entrada_limite: 5, entrada_janela_s: 60, midia_limite_chat_dia: 10, bloqueio_auto_ativo: true, prompt_documento_lead: null });
    expect(toast.success).toHaveBeenCalled();
  });

  it("blocks saving a value outside its range or not an integer, pointing at the field", async () => {
    setup();
    const campo = await screen.findByTestId("limite-entrada_limite");
    const salvar = screen.getByTestId("limites-salvar") as HTMLButtonElement;
    fireEvent.change(campo, { target: { value: "501" } });
    expect(salvar.disabled).toBe(true);
    expect(screen.getByTestId("faixa-entrada_limite").className).toContain("text-destructive");
    fireEvent.change(campo, { target: { value: "2.5" } });
    expect(salvar.disabled).toBe(true);
    fireEvent.change(campo, { target: { value: "" } });
    expect(salvar.disabled).toBe(true);
    fireEvent.change(campo, { target: { value: "500" } });
    expect(salvar.disabled).toBe(false);
  });

  it("the operator can edit the lead document prompt; a too-short one is refused before sending", async () => {
    setup();
    const prompt = await screen.findByTestId("limite-prompt");
    fireEvent.change(prompt, { target: { value: "curto" } });
    expect(screen.getByTestId("prompt-curto")).toBeTruthy();
    expect((screen.getByTestId("limites-salvar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(prompt, { target: { value: "Devolva só o tipo do documento e um resumo curto, sem dados pessoais." } });
    fireEvent.click(screen.getByTestId("limites-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put.mock.calls[0][1].prompt_documento_lead).toContain("só o tipo do documento");
  });

  it("shows the server refusal inline", async () => {
    setup();
    api.put.mockRejectedValue({ message: "422", body: { error: { message: "entrada_limite: use um número inteiro de 1 a 500." } } });
    fireEvent.click(await screen.findByTestId("limites-salvar"));
    expect((await screen.findByTestId("limites-erro")).textContent).toContain("1 a 500");
  });

  it("shows the error with a retry when the config cannot be read", async () => {
    setup({ config: new Error("boom") });
    expect(await screen.findByTestId("protecao-erro")).toBeTruthy();
  });

  it("a non-admin sees the notice and triggers no request", async () => {
    h.admin = false;
    setup();
    expect(screen.getByTestId("protecao-sem-permissao")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("bloqueios", () => {
  it("lists reason, origin, since / until and an unblock action; automatic ones carry their trigger", async () => {
    setup({ bloqueios: [B(), B({ id: "b2", numero: "5511966660000", origem: "automatico", gatilho: "loop_detectado", expira_em: "2026-10-22T12:00:00Z", notificacao_status: "falhou", motivo: "Bloqueio automático: 3 sinais" })] });
    const itens = await screen.findAllByTestId("bloqueio-item");
    expect(itens).toHaveLength(2);
    expect(itens[0].textContent).toContain("+55 11 97777-0001");
    expect(itens[0].textContent).toContain("spam de links");
    expect(itens[0].textContent).toContain("sem prazo");
    expect(itens[1].textContent).toContain("Automático · Loop detectado");
    expect(itens[1].textContent).toContain("até");
    expect(screen.getByTestId("bloqueio-aviso-falhou")).toBeTruthy();
  });

  it("an empty list says so", async () => {
    setup({ bloqueios: [] });
    expect(await screen.findByTestId("bloqueios-vazio")).toBeTruthy();
  });

  it("requires number and reason to block, converts hours to minutes, and shows the refusal inline", async () => {
    setup({ bloqueios: [] });
    api.post.mockRejectedValueOnce({ message: "409", body: { error: { message: "Este número é da equipe." } } });
    fireEvent.click(await screen.findByTestId("bloqueio-novo"));
    const confirmar = screen.getByTestId("bloqueio-confirmar") as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("bloqueio-numero"), { target: { value: "+55 11 97777-0001" } });
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("bloqueio-motivo"), { target: { value: "spam" } });
    fireEvent.change(screen.getByTestId("bloqueio-horas"), { target: { value: "2" } });
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);
    expect((await screen.findByTestId("bloqueio-erro")).textContent).toContain("é da equipe");
    fireEvent.click(screen.getByTestId("bloqueio-confirmar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1]).toEqual(["/api/julia/protecao/bloqueios", { numero: "+55 11 97777-0001", motivo: "spam", duracao_min: 120 }]);
  });

  it("unblocks only after the design-system confirmation (no browser dialog)", async () => {
    const confirmar = vi.spyOn(window, "confirm");
    setup();
    fireEvent.click(await screen.findByTestId("bloqueio-desbloquear"));
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("desbloquear-confirmar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/protecao/bloqueios/b1/desbloquear", {}));
    expect(confirmar).not.toHaveBeenCalled();
  });

  it("the history toggle asks for the lifted ones too and marks them", async () => {
    setup({ bloqueios: [B({ ativo: false, desbloqueado_em: "2026-10-21T13:00:00Z" })] });
    fireEvent.click(await screen.findByTestId("bloqueios-historico"));
    await waitFor(() => expect(api.get.mock.calls.some((c) => String(c[0]).includes("historico=true"))).toBe(true));
    expect(await screen.findByTestId("bloqueio-desfeito")).toBeTruthy();
    expect(screen.queryByTestId("bloqueio-desbloquear")).toBeNull();
  });
});
