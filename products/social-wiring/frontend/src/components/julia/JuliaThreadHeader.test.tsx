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

const CONEXAO = { connection_id: "c1", label: "x", agente_leads_ativo: true, agente_leads_key: null,
  authorized_numbers_count: 1, agente_leads_ativado_em: null, agente_handoff_notificar_user_id: null };

function setup(pausado: boolean, ativo = true) {
  api.get.mockResolvedValue({ data: { conexoes: [{ ...CONEXAO, agente_leads_ativo: ativo }], token_configurado: true, status_agente: null, erro: null } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <JuliaThreadHeader scopeId="c1" thread={{ id: "5511@c.us", title: "Ana", meta: { agente_pausado: pausado } }} />
    </QueryClientProvider>,
  );
}

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); h.admin = true; });
afterEach(cleanup);

describe("JuliaThreadHeader", () => {
  it("chip says 'Julia atendendo' when not paused", async () => {
    setup(false);
    expect((await screen.findByTestId("julia-chip")).textContent).toBe("Julia atendendo");
  });

  it("chip says 'Atendimento humano' when paused", async () => {
    setup(true);
    expect((await screen.findByTestId("julia-chip")).textContent).toBe("Atendimento humano");
  });

  it("hides the chip when Julia is off on this connection", async () => {
    setup(false, false);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByTestId("julia-chip")).toBeNull();
  });

  it("admin toggle PATCHes the pause flag", async () => {
    api.patch.mockResolvedValue({ chat_id: "5511@c.us", agente_pausado: true });
    setup(false);
    fireEvent.click(await screen.findByTestId("julia-toggle"));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/api/whatsapp/connections/c1/chats/5511%40c.us/agente", { pausado: true }),
    );
  });

  it("LGPD delete asks for confirmation, then POSTs", async () => {
    api.post.mockResolvedValue({ data: { sw_mensagens: 3, sw_contatos: 1, agents_ok: true, agents_apagou: true } });
    setup(false);
    fireEvent.click(await screen.findByTestId("julia-apagar-dados"));
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("julia-confirmar-apagar"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/julia/agente/conexoes/c1/chats/5511%40c.us/apagar-dados", {}),
    );
  });

  it("non-admin sees the chip but no actions", async () => {
    h.admin = false;
    setup(false);
    await screen.findByTestId("julia-chip");
    expect(screen.queryByTestId("julia-toggle")).toBeNull();
    expect(screen.queryByTestId("julia-apagar-dados")).toBeNull();
  });
});
