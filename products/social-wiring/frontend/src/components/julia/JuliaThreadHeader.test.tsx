/**
 * Julia thread header (julia-v2): the state chip comes from agents' GET with its SOURCE flag (agents | espelho |
 * nenhuma) and honest copy; the pause/resume toggle PATCHes the SW proxy and is offered only on a live state; the stage
 * chip shows label + score only; the LGPD erase still asks for confirmation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { JuliaThreadHeader } from "./JuliaThreadHeader";

const LINHA = { connection_id: "c1", label: "x", alimenta: true, alimenta_desde: null, numeros_autorizados: 1, destino_handoff_user_id: null };
const ROT = { linhas: [LINHA], destino_handoff_padrao: { tipo: "dono_da_organizacao", user_id: null }, agents_url: null };
const ESTADO_URL = "/api/whatsapp/connections/c1/chats/5511%40c.us/agente";
const estado = (estado: string | null, fonte = "agents") => ({
  thread_id: "t1", estado, pausado: estado === "pausado", reengajamento_suprimido: null, motivo: null, fonte,
});

interface Opts { estado?: unknown | Error; linha?: object; contato?: unknown; meta?: Record<string, unknown> }
function setup({ estado: est = estado("ativo"), linha = {}, contato = { contato: null, slots: {}, interacao_atual: null }, meta = {} }: Opts = {}) {
  api.get.mockImplementation((url: string) => {
    if (url === "/api/julia/roteamento") return Promise.resolve({ data: { ...ROT, linhas: [{ ...LINHA, ...linha }] } });
    if (url === ESTADO_URL) return est instanceof Error ? Promise.reject(est) : Promise.resolve({ data: est });
    if (url.startsWith("/api/julia/contatos/")) return Promise.resolve({ data: contato });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <JuliaThreadHeader scopeId="c1" thread={{ id: "5511@c.us", title: "Ana", meta }} />
    </QueryClientProvider>,
  );
}

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); h.admin = true; });
afterEach(cleanup);

describe("state chip — from agents, with its source", () => {
  it("shows a skeleton chip, then 'Julia atendendo' for ativo", async () => {
    setup();
    expect(await screen.findByTestId("julia-chip-skeleton")).toBeTruthy();
    const chip = await screen.findByTestId("julia-chip");
    expect(chip.textContent).toBe("Julia atendendo");
    expect(chip.getAttribute("data-fonte")).toBe("agents");
  });

  it.each([
    ["pausado", "Atendimento humano (Julia pausada)"],
    ["concluido", "Julia concluiu"],
    ["transferido", "Transferido para uma pessoa"],
    ["encerrado", "Conversa encerrada"],
  ])("state %s -> %s", async (st, texto) => {
    setup({ estado: estado(st) });
    expect((await screen.findByTestId("julia-chip")).textContent).toBe(texto);
  });

  it("fonte 'nenhuma': says Julia has not served this chat and offers no toggle", async () => {
    setup({ estado: estado(null, "nenhuma") });
    expect((await screen.findByTestId("julia-chip")).textContent).toBe("Julia ainda não atendeu");
    expect(screen.getByTestId("julia-fonte-aviso").textContent).toContain("ainda não atendeu");
    expect(screen.queryByTestId("julia-toggle")).toBeNull();
  });

  it("fonte 'espelho' (agents unreachable): flags the last known state as stale and disables the toggle", async () => {
    setup({ estado: estado("ativo", "espelho") });
    const chip = await screen.findByTestId("julia-chip");
    expect(chip.textContent).toContain("último estado conhecido");
    expect(chip.getAttribute("data-fonte")).toBe("espelho");
    expect(screen.queryByTestId("julia-toggle")).toBeNull();
    expect(screen.getByTestId("julia-fonte-aviso").textContent).toContain("desatualizado");
  });

  it("the state read failing falls back to the chat-row mirror, flagged stale", async () => {
    setup({ estado: new Error("502"), meta: { agente_estado: "pausado", agente_pausado: true } });
    const chip = await screen.findByTestId("julia-chip");
    expect(chip.getAttribute("data-fonte")).toBe("espelho");
    expect(chip.textContent).toContain("Atendimento humano");
    expect(chip.textContent).toContain("último estado conhecido");
  });

  it("hides everything when the line does not feed Julia (and never reads the state)", async () => {
    setup({ linha: { alimenta: false } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/julia/roteamento"));
    expect(screen.queryByTestId("julia-chip")).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith(ESTADO_URL);
  });
});

describe("stage chip — label + score only", () => {
  it("renders the computed stage label and score", async () => {
    setup({ contato: { contato: null, slots: {}, interacao_atual: null, qualificacao: { estagio: "quente", rotulo: "Lead quente", score: 72 } } });
    expect((await screen.findByTestId("julia-estagio")).textContent).toBe("Lead quente · 72");
  });

  it("falls back to the stage key when there is no label, and is absent without a computed stage", async () => {
    setup({ contato: { contato: null, slots: {}, interacao_atual: null, qualificacao: { estagio: "morno" } } });
    expect((await screen.findByTestId("julia-estagio")).textContent).toBe("morno");
    cleanup();
    setup();
    await screen.findByTestId("julia-chip");
    expect(screen.queryByTestId("julia-estagio")).toBeNull();
  });
});

describe("pause / resume toggle — proxied to agents", () => {
  it("admin toggle PATCHes the pause and refetches the state from agents", async () => {
    api.patch.mockResolvedValue({ chat_id: "5511@c.us", agente_pausado: true, agente_estado: "pausado" });
    setup();
    fireEvent.click(await screen.findByTestId("julia-toggle"));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/api/whatsapp/connections/c1/chats/5511%40c.us/agente", { pausado: true }),
    );
    await waitFor(() => expect(api.get.mock.calls.filter((c) => c[0] === ESTADO_URL).length).toBeGreaterThan(1));
  });

  it("paused: the button offers to give the chat back to Julia and sends pausado=false", async () => {
    api.patch.mockResolvedValue({ chat_id: "5511@c.us", agente_pausado: false, agente_estado: "ativo" });
    setup({ estado: estado("pausado") });
    const btn = await screen.findByTestId("julia-toggle");
    expect(btn.textContent).toContain("Devolver à Julia");
    fireEvent.click(btn);
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(expect.any(String), { pausado: false }));
  });

  it("no toggle once the conversation is concluded or transferred", async () => {
    setup({ estado: estado("concluido") });
    await screen.findByTestId("julia-chip");
    expect(screen.queryByTestId("julia-toggle")).toBeNull();
  });
});

describe("LGPD + roles", () => {
  it("LGPD delete asks for confirmation, then POSTs", async () => {
    api.post.mockResolvedValue({ data: { sw_mensagens: 3, sw_contatos: 1, agents_ok: true, agents_apagou: true } });
    setup();
    fireEvent.click(await screen.findByTestId("julia-apagar-dados"));
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("julia-confirmar-apagar"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/julia/agente/conexoes/c1/chats/5511%40c.us/apagar-dados", {}),
    );
  });

  it("non-admin sees the chip but no actions", async () => {
    h.admin = false;
    setup();
    await screen.findByTestId("julia-chip");
    expect(screen.queryByTestId("julia-toggle")).toBeNull();
    expect(screen.queryByTestId("julia-apagar-dados")).toBeNull();
  });
});
