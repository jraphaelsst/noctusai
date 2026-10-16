import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("@noctusai/lib", async (orig) => ({ ...(await orig<object>()), useConfirm: () => async () => true }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import LaisAvaliacoes from "@/pages/lais/Avaliacoes";
import LaisCredito from "@/pages/lais/Credito";
import { ClienteColumn } from "@/components/lais/conversas/ClienteColumn";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}
const AV = {
  pedidos_enviados: 7, novas_avaliacoes: 3, distribuicao: { "1": 0, "2": 1, "3": 0, "4": 1, "5": 2 }, media: 4.25, total: 4,
  ultimas: [{ autor: "Ana", nota: 5, texto: "Ótimo", data: "2026-10-01T10:00:00Z", link: "https://g.co/x" }],
  configurado: { review_url: true, gbp: true },
};
const mockAv = (d: object, cfg = { google_review_url: "https://a", gbp_location_id: null, capi_ativo: false, capi_pixel_id: null }) =>
  api.get.mockImplementation(async (u: string) => (u.includes("/config") ? { data: cfg } : { data: d }));

beforeEach(() => { h.admin = true; Object.values(api).forEach((f) => f.mockReset()); });
afterEach(cleanup);

describe("Avaliações", () => {
  it("renders KPIs, distribution and reviews", async () => {
    mockAv(AV);
    wrap(<LaisAvaliacoes />);
    expect((await screen.findByTestId("kpi-pedidos")).textContent).toBe("7");
    expect(screen.getByTestId("kpi-novas").textContent).toBe("3");
    expect(screen.getByTestId("avaliacoes-media").textContent).toBe("4.3");
    expect(screen.getByTestId("dist-5").textContent).toContain("2");
    expect(screen.getByText(/Ana · 5★/)).toBeTruthy();
    expect(screen.getByLabelText("Abrir avaliação no Google").getAttribute("href")).toBe("https://g.co/x");
  });
  it("shows not-configured states", async () => {
    mockAv({ ...AV, configurado: { review_url: false, gbp: false } });
    wrap(<LaisAvaliacoes />);
    expect(await screen.findByTestId("avaliacoes-sem-link")).toBeTruthy();
    expect(screen.getByTestId("avaliacoes-sem-gbp").textContent).toContain("Conecte o Google Business Profile");
  });
  it("saves config", async () => {
    mockAv(AV);
    api.put.mockResolvedValue({ data: {} });
    wrap(<LaisAvaliacoes />);
    fireEvent.click(await screen.findByText("Configurar"));
    const input = await screen.findByLabelText("Link de avaliação do Google");
    fireEvent.change(input, { target: { value: "https://novo" } });
    fireEvent.click(screen.getByLabelText("Enviar sinais de qualificação para a Meta (CAPI)"));
    fireEvent.change(screen.getByLabelText("ID do pixel da Meta"), { target: { value: " 123456 " } });
    fireEvent.click(screen.getByText("Salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/lais/avaliacoes/config",
      { google_review_url: "https://novo", capi_ativo: true, capi_pixel_id: "123456" }));
  });
  it("hides configure for non-admin", async () => {
    h.admin = false;
    mockAv(AV);
    wrap(<LaisAvaliacoes />);
    await screen.findByTestId("kpi-pedidos");
    expect(screen.queryByText("Configurar")).toBeNull();
  });
});

// Real 13b-BE item shape (`lais_credito_service._serializar`).
const C = (id: string, status: string) => ({
  id: `a${id}`, contato_id: id, provider: "credaluga", status, resumo: "r", created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-02T10:00:00Z",
  contato: { id, nome: `Lead ${id}`, telefone_e164: null, canal: "whatsapp" },
});
const mockCr = (provider: string | null) =>
  api.get.mockImplementation(async (u: string) =>
    u.includes("/config") ? { data: { ativo: true, provider, apenas_aluguel: true } } : { data: { items: [C("1", "aprovado"), C("2", "erro")], total: 2 } });

describe("Crédito", () => {
  it("lists with chips, filters and shows the consent copy", async () => {
    mockCr("credaluga");
    wrap(<LaisCredito />);
    expect((await screen.findAllByTestId("credito-item")).length).toBe(2);
    expect(screen.getByTestId("credito-consentimento").textContent).toContain("consentimento do lead");
    expect(screen.queryByTestId("credito-sem-provedor")).toBeNull();
    fireEvent.change(screen.getByLabelText("Filtrar por status"), { target: { value: "erro" } });
    await waitFor(() => expect(api.get.mock.calls.some((c) => String(c[0]).includes("status=erro"))).toBe(true));
    // BE accepts page_size 5|10|15|20 and defaults to 10 — the FE's pagination math assumes 20, so it must send it.
    expect(api.get.mock.calls.every((c) => !String(c[0]).startsWith("/api/lais/credito?") || String(c[0]).includes("page_size=20"))).toBe(true);
  });
  it("banners when provider is null", async () => {
    mockCr(null);
    wrap(<LaisCredito />);
    expect((await screen.findByTestId("credito-sem-provedor")).textContent).toContain("ainda não configurado");
  });
  it("reprocesses after confirm (admin)", async () => {
    mockCr("x");
    api.post.mockResolvedValue({});
    wrap(<LaisCredito />);
    fireEvent.click(await screen.findByLabelText("Reprocessar Lead 1"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/lais/credito/1/reprocessar", {}));
  });
  it("shows empty and error states", async () => {
    api.get.mockImplementation(async (u: string) => (u.includes("/config") ? { data: { ativo: true, provider: "x", apenas_aluguel: true } } : { data: { items: [], total: 0 } }));
    wrap(<LaisCredito />);
    expect(await screen.findByTestId("credito-vazio")).toBeTruthy();
    cleanup();
    api.get.mockRejectedValue(new Error("boom"));
    wrap(<LaisCredito />);
    expect(await screen.findByTestId("credito-erro")).toBeTruthy();
  });
});

describe("Conversas › credit chip", () => {
  it("shows the conversa's credit status in the Cliente column (13b `credito` on list items)", async () => {
    api.get.mockResolvedValue({ data: [] });
    wrap(<ClienteColumn contatoId="c1" nome="Lead" etiquetas={[]} credito={{ status: "aprovado", atualizado_at: null }} />);
    expect(await screen.findByText("Crédito")).toBeTruthy();
  });
  it("omits the row when the contato has no analysis", async () => {
    api.get.mockResolvedValue({ data: [] });
    wrap(<ClienteColumn contatoId="c1" nome="Lead" etiquetas={[]} />);
    await screen.findByText("Nome");
    expect(screen.queryByText("Crédito")).toBeNull();
  });
});
