/**
 * Julia › platform connection card — every status has its badge + pt-BR "what to do", the token is masked and
 * read-only, and "Testar conexão" writes the server's answer into the agente cache (no refetch needed).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ConexaoPlataformaBody, ConexaoPlataformaDoAgente } from "./ConexaoPlataforma";
import { JULIA_AGENTE_KEY, type ConexaoPlataforma, type JuliaAgente } from "@/hooks/useJuliaAgente";

const BASE: ConexaoPlataforma = {
  status: "ativa",
  conectada: true,
  motivo: null,
  token_prefix: "noc_ab12",
  token_mascarado: "noc_…9f3a",
  conectada_em: "2026-11-04T17:50:00Z",
  agent_key: "julia",
  verificada_em: "2026-11-04T18:00:00Z",
  ultima_falha_em: null,
  expires_at: null,
};
const AGENTE = (c: ConexaoPlataforma): JuliaAgente => ({ conexoes: [], conexao_plataforma: c, status_agente: null, erro: null });

function setup(c: ConexaoPlataforma, canTest = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(JULIA_AGENTE_KEY, AGENTE(c));
  render(
    <QueryClientProvider client={qc}>
      <ConexaoPlataformaBody conexao={c} canTest={canTest} />
    </QueryClientProvider>,
  );
  return qc;
}

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

const CASOS: [string, Partial<ConexaoPlataforma>, string, string][] = [
  ["nao_configurada", { status: "nao_configurada", conectada: false, token_mascarado: null, token_prefix: null, conectada_em: null, verificada_em: null }, "Não configurada", "Peça ao suporte NoctusAI para conectá-la"],
  ["ativa", {}, "Conectada", "o WhatsApp consegue falar com a Julia"],
  ["com_falha / token_rejeitado", { status: "com_falha", conectada: false, motivo: "token_rejeitado", ultima_falha_em: "2026-11-04T18:05:00Z" }, "Com falha", "Peça ao suporte NoctusAI para reconectar"],
  ["com_falha / agents_indisponivel", { status: "com_falha", conectada: false, motivo: "agents_indisponivel", ultima_falha_em: "2026-11-04T18:05:00Z" }, "Com falha", "Testar conexão” em alguns minutos"],
  ["revogada", { status: "revogada", conectada: false }, "Revogada", "Peça ao suporte NoctusAI para reconectar"],
  ["expirada", { status: "expirada", conectada: false, expires_at: "2026-11-01T00:00:00Z" }, "Expirada", "Peça ao suporte NoctusAI para renová-la"],
];

describe("ConexaoPlataformaBody — one state per status", () => {
  it.each(CASOS)("%s", (_nome, over, badge, ajuda) => {
    setup({ ...BASE, ...over });
    expect(screen.getByTestId("conexao-status").textContent).toContain(badge);
    expect(screen.getByTestId("conexao-ajuda").textContent).toContain(ajuda);
    // Never sends the user anywhere, never names the agents app.
    expect(document.body.textContent!.toLowerCase()).not.toContain("app de agentes");
    expect(document.querySelector("a")).toBeNull();
  });

  it("failure statuses are announced as alerts; ativa is not", () => {
    setup({ ...BASE, status: "revogada", conectada: false });
    expect(screen.getByTestId("conexao-ajuda").getAttribute("role")).toBe("alert");
    cleanup();
    setup(BASE);
    expect(screen.getByTestId("conexao-ajuda").getAttribute("role")).toBeNull();
  });
});

describe("the token is display-only", () => {
  it("shows the masked value, never an input, never the prefix as a full secret", () => {
    setup(BASE);
    expect(screen.getByTestId("conexao-token").textContent).toBe("noc_…9f3a");
    expect(document.querySelector("input, textarea")).toBeNull();
  });

  it("not configured shows 'Sem token'", () => {
    setup({ ...BASE, status: "nao_configurada", conectada: false, token_mascarado: null });
    expect(screen.getByTestId("conexao-token").textContent).toBe("Sem token");
  });

  it("shows the verification and failure times", () => {
    setup({ ...BASE, status: "com_falha", conectada: false, motivo: "token_rejeitado", ultima_falha_em: "2026-11-04T18:05:00Z" });
    expect(screen.getByTestId("conexao-verificada-em").textContent).not.toBe("—");
    expect(screen.getByTestId("conexao-falha-em").textContent).not.toBe("—");
    expect(screen.getByTestId("conexao-expira").textContent).toBe("Não expira");
  });
});

describe("Testar conexão", () => {
  it("POSTs the probe and writes the answer into the agente cache", async () => {
    const nova = { ...BASE, status: "com_falha" as const, conectada: false, motivo: "token_rejeitado" as const, ultima_falha_em: "2026-11-04T18:10:00Z" };
    api.post.mockResolvedValue({ data: nova });
    const qc = setup(BASE);
    fireEvent.click(screen.getByTestId("conexao-testar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/agente/conexao-plataforma/verificar", {}));
    await waitFor(() => expect((qc.getQueryData(JULIA_AGENTE_KEY) as JuliaAgente).conexao_plataforma.status).toBe("com_falha"));
    expect(api.get).not.toHaveBeenCalled();
  });

  it("a refused probe shows an inline pt-BR error", async () => {
    api.post.mockRejectedValue(Object.assign(new Error("[502] x"), { status: 502, body: { error: { code: "agents_indisponivel", message: "m" } } }));
    setup(BASE);
    fireEvent.click(screen.getByTestId("conexao-testar"));
    expect((await screen.findByTestId("conexao-erro")).textContent).toContain("Tente novamente em instantes");
  });

  it("a non-admin gets a status view without the button", () => {
    setup(BASE, false);
    expect(screen.queryByTestId("conexao-testar")).toBeNull();
    expect(screen.getByText(/Somente owner ou admin/)).toBeTruthy();
  });
});

describe("ConexaoPlataformaDoAgente (Configurações) — own query states", () => {
  function render2() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><ConexaoPlataformaDoAgente canTest /></QueryClientProvider>);
  }
  it("skeleton, then the card", async () => {
    api.get.mockResolvedValue({ data: AGENTE(BASE) });
    render2();
    expect(screen.getByTestId("conexao-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("conexao-plataforma")).toBeTruthy();
  });
  it("a refused read says so and offers a retry", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    render2();
    expect(await screen.findByTestId("conexao-leitura-erro")).toBeTruthy();
    expect(screen.getByText("Tentar de novo")).toBeTruthy();
  });
});
