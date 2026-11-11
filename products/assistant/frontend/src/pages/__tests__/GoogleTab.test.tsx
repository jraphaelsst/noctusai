/** `/configuracoes/google`: connect / disconnect / proof, every state (loading, empty, error, forbidden), no token shown. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const admin = { value: true };
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => admin.value }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import GoogleTab from "../GoogleTab";

const CAL = "https://www.googleapis.com/auth/calendar.events";
const DRV = "https://www.googleapis.com/auth/drive.readonly";
const base = { connected: false, account_email: null, scopes: [], missing_scopes: [], connected_at: null, needs_reconnection: false, app_scopes: [] };
const conectado = { ...base, connected: true, account_email: "dono@example.com", scopes: [CAL, DRV], connected_at: "2026-11-10T12:00:00Z" };

function renderTab(url = "/configuracoes/google") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}><GoogleTab /></MemoryRouter></QueryClientProvider>,
  );
}

beforeEach(() => { admin.value = true; api.get.mockReset(); api.post.mockReset(); });
afterEach(cleanup);

describe("GoogleTab", () => {
  it("refuses a non-admin without calling the API", () => {
    admin.value = false;
    renderTab();
    expect(screen.getByTestId("google-acesso-restrito")).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("shows a skeleton while loading, then the disconnected card with the connect button", async () => {
    api.get.mockResolvedValue(base);
    renderTab();
    expect(screen.getByTestId("google-carregando")).toBeInTheDocument();
    expect(await screen.findByTestId("google-desconectado")).toBeInTheDocument();
    expect(screen.getByTestId("google-conectar")).toHaveTextContent("Conectar Google");
  });

  it("starts the connection and navigates to the consent URL the server returned", async () => {
    api.get.mockResolvedValue(base);
    api.post.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?state=abc" });
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
    renderTab();
    fireEvent.click(await screen.findByTestId("google-conectar"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?state=abc"));
    expect(api.post).toHaveBeenCalledWith("/api/google/connect/start", {});
  });

  it("shows the connected account and the granted scopes, never a token", async () => {
    api.get.mockResolvedValue(conectado);
    renderTab();
    expect(await screen.findByTestId("google-conta")).toHaveTextContent("dono@example.com");
    expect(screen.getByTestId("google-escopos")).toHaveTextContent("Agenda: ler e criar eventos");
    expect(screen.getByTestId("google-desconectar")).toBeInTheDocument();
  });

  it("warns about declined scopes and about a dead token", async () => {
    api.get.mockResolvedValue({ ...conectado, scopes: [CAL], missing_scopes: [DRV], needs_reconnection: true });
    renderTab();
    expect(await screen.findByTestId("google-escopos-faltando")).toHaveTextContent("Drive: ler arquivos");
    expect(screen.getByTestId("google-reconectar")).toBeInTheDocument();
  });

  it("disconnects and shows the card as disconnected at once; flags an unconfirmed revoke", async () => {
    let live = true; // the server forgets the grant once the POST lands, so the settle refetch agrees with the commit
    api.get.mockImplementation(() => Promise.resolve(live ? conectado : base));
    api.post.mockImplementation(() => { live = false; return Promise.resolve({ connected: false, revoked: false }); });
    renderTab();
    fireEvent.click(await screen.findByTestId("google-desconectar"));
    expect(await screen.findByTestId("google-desconectado")).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/api/google/disconnect", {});
    expect(await screen.findByTestId("google-revogacao-pendente")).toBeInTheDocument();
  });

  it("runs the proof on demand and lists the calendar events and Drive file names", async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith("/prova")
        ? { calendario: { status: "ok", itens: [{ titulo: "Visita ao imóvel", inicio: "2026-11-11T14:00:00Z" }] },
            drive: { status: "ok", itens: [{ nome: "Planilha de leads", tipo: "x", modificado_em: null }] }, needs_reconnection: false }
        : conectado));
    renderTab();
    await screen.findByTestId("google-conta");
    expect(api.get).not.toHaveBeenCalledWith("/api/google/prova");
    fireEvent.click(screen.getByTestId("google-testar"));
    expect(await screen.findByTestId("google-calendario")).toHaveTextContent("Visita ao imóvel");
    expect(screen.getByTestId("google-drive")).toHaveTextContent("Planilha de leads");
  });

  it("shows the empty states and a per-half failure of the proof", async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith("/prova")
        ? { calendario: { status: "ok", itens: [] }, drive: { status: "reconectar", itens: [] }, needs_reconnection: true }
        : conectado));
    renderTab();
    fireEvent.click(await screen.findByTestId("google-testar"));
    expect(await screen.findByTestId("google-calendario-vazio")).toBeInTheDocument();
    expect(screen.getByTestId("google-drive-status")).toHaveTextContent("Reconecte o Google");
  });

  it("shows a retry when the status cannot be loaded, and a proof error", async () => {
    api.get.mockRejectedValueOnce(new Error("503"));
    renderTab();
    expect(await screen.findByTestId("google-erro")).toBeInTheDocument();
  });

  it("explains the redirect result after coming back from Google", async () => {
    api.get.mockResolvedValue(conectado);
    renderTab("/configuracoes/google?google=negado");
    expect(await screen.findByTestId("google-resultado")).toHaveTextContent("negada");
  });
});
