/**
 * Automação page — WhatsApp banner states, failure reasons, step forms.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib/components";

const h = vi.hoisted(() => ({
  wa: vi.fn(),
  createStep: vi.fn(),
  idle: () => ({ mutate: () => {}, isPending: false }),
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api, supabase: {}, appConfig: {}, useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null, useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }), useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }), default: { api },
  };
});

vi.mock("@/hooks/useWhatsApp", () => ({ useWhatsAppConnectionState: () => h.wa() }));
vi.mock("@/hooks/useClients", () => ({
  useLeadOptions: () => ({ data: [] }),
  nameLookup: () => () => "Maria",
}));
vi.mock("@/components/LeadSelect", () => ({ LeadSelect: () => null }));

const flow = { id: "f1", name: "Boas-vindas", trigger_type: "manual", trigger_config: {}, active: true, schedule_window: null, stop_rules: null };
const failedExec = { id: "e1", flow_id: "f1", lead_id: "l1", status: "failed", current_step_ord: 0, next_action_at: null, error_detail: "Número de telefone inválido" };

vi.mock("@/hooks/useAutomacao", () => ({
  useFlows: () => ({ data: [flow], isPending: false, error: null, refetch: () => {} }),
  useSteps: () => ({ data: [], isPending: false, error: null, refetch: () => {} }),
  useExecutions: () => ({ data: [failedExec], isPending: false, error: null, refetch: () => {} }),
  useCreateStep: () => ({ mutate: h.createStep, isPending: false }),
  useUpdateStep: h.idle, useCreateFlow: h.idle, useUpdateFlow: h.idle, useDeleteFlow: h.idle,
  useDeleteStep: h.idle, useCancelExecution: h.idle, useRunDue: h.idle,
  useTriggerFlow: h.idle, useToggleFlow: h.idle, useStartFlow: h.idle,
  useReorderSteps: h.idle,
}));

import Automacao from "../Automacao";

function renderPage() {
  return render(
    <MemoryRouter>
      <ConfirmProvider>
        <Automacao />
      </ConfirmProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("Automacao WhatsApp banner", () => {
  it("warns + links to /whatsapp when disconnected", () => {
    h.wa.mockReturnValue({ kind: "disconnected" });
    renderPage();
    expect(screen.getByText(/WhatsApp não conectado — mensagens não serão enviadas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Conectar WhatsApp/ })).toHaveAttribute("href", "/whatsapp");
    expect(screen.queryByText(/simulado/i)).toBeNull();
  });

  it("shows the connected number and no warning when connected", () => {
    h.wa.mockReturnValue({ kind: "connected", label: "Agência", number: "5511999990000", session: "s1" });
    renderPage();
    expect(screen.getByTestId("wa-banner-connected")).toHaveTextContent("5511999990000");
    expect(screen.queryByTestId("wa-banner-disconnected")).toBeNull();
  });

  it("shows no banner while loading (no false warning)", () => {
    h.wa.mockReturnValue({ kind: "loading" });
    renderPage();
    expect(screen.queryByTestId("wa-banner-disconnected")).toBeNull();
    expect(screen.queryByTestId("wa-banner-connected")).toBeNull();
  });

  it("lists the failure reason of a failed execution", () => {
    h.wa.mockReturnValue({ kind: "loading" });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Execuções/ }));
    expect(screen.getAllByText("Número de telefone inválido").length).toBeGreaterThan(0);
  });
});
