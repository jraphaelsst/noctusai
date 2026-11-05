/**
 * Julia › "WhatsApp da Julia" card: the seed pairing panel for the org's single line (QR / status / reconnect),
 * the anchor, the link into Conversas, admin-only controls, and the no-line state.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { WhatsAppJuliaCard } from "./WhatsAppJuliaCard";
import type { LinhaRoteamento } from "@/hooks/useJuliaRoteamento";

const LINHA: LinhaRoteamento = { connection_id: "c1", label: "Julia", alimenta: false, alimenta_desde: null, destino_handoff_user_id: null };
const STATUS = { connection_id: "c1", status: "SCAN_QR_CODE", paired: false, me_id: null, me_name: null, session: "default", error: null };
const QR = { connection_id: "c1", scannable: true, status: "SCAN_QR_CODE", png_base64: "ZmFrZQ==" };

function setup(linha: LinhaRoteamento | undefined, isAdmin = true, status = STATUS) {
  api.get.mockImplementation(async (path: string) => (String(path).endsWith("/qr") ? QR : status));
  api.post.mockResolvedValue(status);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={qc}><WhatsAppJuliaCard linha={linha} isAdmin={isAdmin} /></QueryClientProvider>);
}

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("WhatsAppJuliaCard", () => {
  it("is the #whatsapp anchor and shows the QR for an unpaired line", async () => {
    setup(LINHA);
    expect(document.getElementById("whatsapp")).toBe(screen.getByTestId("whatsapp-julia-card"));
    expect((await screen.findByTestId("wa-qr-image")).getAttribute("src")).toBe("data:image/png;base64,ZmFrZQ==");
    expect(api.get.mock.calls.some(([p]) => String(p) === "/api/whatsapp/connections/c1/qr")).toBe(true);
    expect(screen.getByTestId("wa-pairing-actions")).toBeTruthy();
  });

  it("links to the existing Conversas chat window and offers no 'add connection'", async () => {
    setup(LINHA);
    await screen.findByTestId("wa-pairing-panel");
    expect(screen.getByTestId("whatsapp-ver-conversas").getAttribute("href")).toBe("/julia/conversas");
    expect(screen.queryByTestId("whatsapp-criar-linha")).toBeNull();
    expect(document.body.textContent!.toLowerCase()).not.toContain("nova conexão");
  });

  it("a paired line shows its status and no QR", async () => {
    setup(LINHA, true, { ...STATUS, status: "WORKING", paired: true });
    expect((await screen.findByTestId("wa-pairing-panel")).textContent).toContain("WORKING");
    expect(screen.queryByTestId("wa-qr-panel")).toBeNull();
  });

  it("Desconectar asks first and names the shared number consequence", async () => {
    setup(LINHA, true, { ...STATUS, status: "WORKING", paired: true });
    fireEvent.click(await screen.findByText("Desconectar"));
    expect((await screen.findAllByText(/envia os avisos para a equipe/)).length).toBe(2); // card copy + the confirm dialog
    expect(api.post).not.toHaveBeenCalled();
  });

  it("a non-admin sees status only: no QR, no actions", async () => {
    setup(LINHA, false);
    await screen.findByTestId("wa-pairing-panel");
    expect(screen.queryByTestId("wa-qr-panel")).toBeNull();
    expect(screen.queryByTestId("wa-pairing-actions")).toBeNull();
    expect(screen.getByText(/Somente owner ou admin/)).toBeTruthy();
  });

  it("a refused status read says so with a retry", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><WhatsAppJuliaCard linha={LINHA} isAdmin /></QueryClientProvider>);
    expect(await screen.findByTestId("wa-pairing-error")).toBeTruthy();
  });

  it("no line yet: the empty state offers 'Criar linha' to an admin, only an instruction to others", async () => {
    setup(undefined);
    expect(screen.getByTestId("wa-pairing-empty")).toBeTruthy();
    expect(screen.getByTestId("whatsapp-criar-linha")).toBeTruthy();
    expect(screen.queryByTestId("whatsapp-ver-conversas")).toBeNull();
    cleanup();
    setup(undefined, false);
    expect(screen.queryByTestId("whatsapp-criar-linha")).toBeNull();
    await waitFor(() => expect(screen.getByText(/Peça a um owner ou admin/)).toBeTruthy());
  });
});
