/** The operator-facing opt-out warning (never blocking) and the header actions. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { OptOutAcoes, OptOutAviso } from "./OptOutConversa";

const URL_ESTADO = "/api/julia/opt-outs/conversas/c1/5511%40c.us/estado";
const estado = (over: Record<string, unknown> = {}) => ({
  lead_ref: "lead1", verificado: true, opt_out_ativo: false, opt_out_em: null, motivo: null, origem: null, evento_id: null, ...over,
});
function setup(res: unknown | Error, ui = <OptOutAviso connectionId="c1" chatId="5511@c.us" />) {
  api.get.mockImplementation((u: string) =>
    u === URL_ESTADO ? (res instanceof Error ? Promise.reject(res) : Promise.resolve({ data: res })) : Promise.reject(new Error(u)));
  api.post.mockResolvedValue({ data: {} });
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
}
beforeEach(() => { vi.clearAllMocks(); h.admin = true; });
afterEach(cleanup);

describe("OptOutAviso", () => {
  it("warns with the date and the reason of an active opt-out, without blocking anything", async () => {
    setup(estado({ opt_out_ativo: true, opt_out_em: "2026-10-21T12:00:00Z", motivo: "pediu por telefone" }));
    const aviso = await screen.findByTestId("optout-aviso");
    expect(aviso.textContent).toContain("Este lead pediu para não ser contatado em");
    expect(aviso.textContent).toContain("pediu por telefone");
    expect(aviso.textContent).toContain("enviar mesmo assim");
  });

  it("shows nothing for a clean lead and nothing while loading", async () => {
    setup(estado());
    expect(screen.queryByTestId("optout-aviso")).toBeNull();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByTestId("optout-aviso")).toBeNull();
    expect(screen.queryByTestId("optout-aviso-nao-verificado")).toBeNull();
  });

  it("says it could not verify (never 'no opt-out') when the read fails, and still allows the send", async () => {
    setup(new Error("agents down"));
    const aviso = await screen.findByTestId("optout-aviso-nao-verificado");
    expect(aviso.textContent).toContain("Não foi possível verificar");
    expect(aviso.textContent).toContain("ainda pode enviar");
  });

  it("also says it when agents answers unverified", async () => {
    setup(estado({ verificado: false }));
    expect(await screen.findByTestId("optout-aviso-nao-verificado")).toBeTruthy();
  });
});

describe("OptOutAcoes", () => {
  const ui = <OptOutAcoes connectionId="c1" chatId="5511@c.us" contatoId="lead1" />;

  it("an admin marks a lead 'não contatar' with a required reason", async () => {
    setup(estado(), ui);
    fireEvent.click(await screen.findByTestId("optout-marcar"));
    const ok = await screen.findByTestId("motivo-dialog-confirmar");
    expect((ok as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("motivo-dialog-texto"), { target: { value: "ligou pedindo" } });
    fireEvent.click(ok);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/opt-outs/leads/lead1/nao-contatar", { motivo: "ligou pedindo" }));
  });

  it("an active opt-out shows the badge and offers 'Reativar atendimento'", async () => {
    setup(estado({ opt_out_ativo: true, opt_out_em: "2026-10-21T12:00:00Z" }), ui);
    expect(await screen.findByTestId("optout-badge")).toBeTruthy();
    fireEvent.click(screen.getByTestId("optout-reativar-conversa"));
    fireEvent.change(await screen.findByTestId("motivo-dialog-texto"), { target: { value: "voltou" } });
    fireEvent.click(screen.getByTestId("motivo-dialog-confirmar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/opt-outs/leads/lead1/reativar", { motivo: "voltou" }));
  });

  it("a non-admin sees the badge but no action; an unverified state offers no action", async () => {
    h.admin = false;
    setup(estado({ opt_out_ativo: true }), ui);
    await screen.findByTestId("optout-badge");
    expect(screen.queryByTestId("optout-reativar-conversa")).toBeNull();
    cleanup();
    h.admin = true;
    setup(estado({ verificado: false }), ui);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByTestId("optout-marcar")).toBeNull();
  });
});
