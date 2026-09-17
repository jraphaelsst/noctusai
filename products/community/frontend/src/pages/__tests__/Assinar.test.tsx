/**
 * Assinar (public checkout) render tests — community-m2-contract.md
 * §Frontend, amendments A2/A17/P2, product decision P1.
 *
 * Mounted as a `publicRoute` — no auth, no Layout, same seam as
 * `/inscrever` (module 1). `TurnstileWidget` is mocked to a plain button
 * that fires `onVerify("test-token")` — the real Cloudflare embed is out of
 * scope for a unit test; what matters here is the FE forwards whatever
 * token the widget hands back as `turnstile_token`.
 *
 * No `AuthProvider`/session is ever wired into `renderPage` — this suite
 * proves the page (and its `usePlanosPublicos` tier fetch, A17) works with
 * NO session at all, matching how a real unauthenticated visitor hits it.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    coreApi: api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }),
    useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }),
    default: { api },
  };
});

vi.mock("@/pages/checkout/TurnstileWidget", () => ({
  TurnstileWidget: ({ onVerify }: { onVerify: (t: string) => void }) => (
    <button type="button" data-testid="turnstile-mock-verify" onClick={() => onVerify("test-token")}>
      Verificar
    </button>
  ),
}));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

/** `PlanoPublico` (amendment A17) — deliberately narrower than module 1's
 * `Plano`: no `ref_externo`, no `membros_ativos`, no timestamps. */
const PLANO = {
  id: "p-1",
  nome: "Círculo",
  descricao: null,
  preco_centavos: 9900,
  ciclo: "mensal" as const,
  beneficios: { feed: true, forum: true, chat: true, eventos: true },
  metodos_disponiveis: ["cartao", "pix", "boleto"] as const,
};

function fillCommonFields() {
  fireEvent.change(screen.getByLabelText(/^Plano/), { target: { value: "p-1" } });
  fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: "Ana" } });
  fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "ana@x.com" } });
  fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "+5511999999999" } });
}

beforeEach(() => vi.clearAllMocks());

describe("Assinar — loading / empty / error", () => {
  it("shows a skeleton on first load", async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    expect(screen.getByTestId("assinar-skeleton")).toBeInTheDocument();
  });

  it("shows the empty state when there are no active planos", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByText("Nenhum plano disponível no momento.")).toBeInTheDocument());
  });

  it("renders the backend's error detail on a failed plano fetch", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(500, "Erro interno."));
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByText("Erro interno.")).toBeInTheDocument());
  });
});

describe("Assinar — CPF field per method (P1)", () => {
  it("shows the CPF field (with the not-stored note) for pix, not for cartao", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/^Plano/), { target: { value: "p-1" } });

    expect(screen.queryByLabelText(/^CPF/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Pix"));
    expect(screen.getByLabelText(/^CPF/)).toBeInTheDocument();
    expect(screen.getByText(/não é armazenado por nós/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Cartão de crédito"));
    expect(screen.queryByLabelText(/^CPF/)).not.toBeInTheDocument();
  });

  it("blocks submit client-side when pix/boleto CPF is missing/invalid, never calling checkout", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { default: Assinar } = await import("../Assinar");
    const { container } = renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    fillCommonFields();
    fireEvent.click(screen.getByLabelText("Pix"));
    fireEvent.click(screen.getByTestId("turnstile-mock-verify"));
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() =>
      expect(screen.getByText(/Informe um CPF válido/)).toBeInTheDocument(),
    );
    expect(mockPost).not.toHaveBeenCalled();
  });
});

describe("Assinar — amendment A2 (checkout_url:null is a normal outcome)", () => {
  it("renders the friendly 'verifique seu e-mail' state, never as an error", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    mockPost.mockResolvedValue({
      checkout_url: null,
      assinatura_id: "a-1",
      membro_id: "m-1",
      pix_qr: null,
      status: "verifique_seu_email",
    });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    fillCommonFields();
    fireEvent.click(screen.getByTestId("turnstile-mock-verify"));
    fireEvent.click(screen.getByRole("button", { name: "Assinar" }));

    await waitFor(() => expect(screen.getByTestId("assinar-verifique-email")).toBeInTheDocument());
    expect(screen.getByText("Verifique seu e-mail")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Assinar — Pix shows the QR inline instead of redirecting", () => {
  it("renders the QR payload + image for a pix checkout", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    mockPost.mockResolvedValue({
      checkout_url: "https://asaas.example/checkout/abc",
      assinatura_id: "a-2",
      membro_id: "m-2",
      pix_qr: { payload: "000201PIXPAYLOAD", imagem_base64: "iVBORw0KG==", expira_em: "2026-09-17T00:00:00+00:00" },
    });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    fillCommonFields();
    fireEvent.click(screen.getByLabelText("Pix"));
    fireEvent.change(screen.getByLabelText(/^CPF/), { target: { value: "123.456.789-01" } });
    fireEvent.click(screen.getByTestId("turnstile-mock-verify"));
    fireEvent.click(screen.getByRole("button", { name: "Assinar" }));

    await waitFor(() => expect(screen.getByTestId("pix-qr-card")).toBeInTheDocument());
    expect(screen.getByText("000201PIXPAYLOAD")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/api/checkout",
      expect.objectContaining({ metodo: "pix", cpf: "12345678901" }),
    );
  });
});

describe("Assinar — amendment P2 (missing/expired Turnstile token)", () => {
  it("surfaces the backend's strict 403 detail when the token is missing", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { ApiError } = await import("@noctusai/lib");
    mockPost.mockRejectedValue(
      new ApiError(403, "Verificação de segurança falhou. Recarregue a página e tente novamente."),
    );
    const { default: Assinar } = await import("../Assinar");
    const { container } = renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    fillCommonFields();
    // Deliberately do NOT click the turnstile mock — no token obtained.
    // The Submit button is disabled without a token, so the form's submit
    // event is dispatched directly (bypassing the disabled-button UX gate)
    // to exercise the actual backend-refusal path, per the amendment's test
    // requirement ("a missing Turnstile token surfacing the 403 message").
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() =>
      expect(
        screen.getByText("Verificação de segurança falhou. Recarregue a página e tente novamente."),
      ).toBeInTheDocument(),
    );
  });
});

describe("Assinar — per-tier payment methods (amendment A17)", () => {
  const CARTAO_SOMENTE = {
    id: "p-cartao",
    nome: "Só Cartão",
    descricao: null,
    preco_centavos: 5900,
    ciclo: "mensal" as const,
    beneficios: { feed: true, forum: false, chat: false, eventos: false },
    metodos_disponiveis: ["cartao"] as const,
  };
  const INDISPONIVEL = {
    id: "p-indisponivel",
    nome: "Ainda sem gateway",
    descricao: null,
    preco_centavos: 3900,
    ciclo: "mensal" as const,
    beneficios: { feed: true, forum: false, chat: false, eventos: false },
    metodos_disponiveis: [] as const,
  };

  it("offers only cartao (not pix/boleto) for a tier whose metodos_disponiveis is ['cartao']", async () => {
    mockGet.mockResolvedValue({ items: [CARTAO_SOMENTE], total: 1 });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/^Plano/), { target: { value: "p-cartao" } });

    expect(screen.getByLabelText("Cartão de crédito")).toBeInTheDocument();
    expect(screen.queryByLabelText("Pix")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Boleto")).not.toBeInTheDocument();
  });

  it("renders a tier with metodos_disponiveis:[] as a disabled, explained option — never hidden", async () => {
    mockGet.mockResolvedValue({ items: [INDISPONIVEL], total: 1 });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);
    await waitFor(() => expect(screen.getByLabelText(/^Plano/)).toBeInTheDocument());

    const option = screen.getByRole("option", { name: /Ainda sem gateway/ });
    expect(option).toBeDisabled();
    expect(option).toHaveTextContent("indisponível no momento");

    // Even if force-selected (bypassing the disabled option), the page
    // explains unavailability rather than silently offering no methods.
    fireEvent.change(screen.getByLabelText(/^Plano/), { target: { value: "p-indisponivel" } });
    expect(screen.getByTestId("assinar-plano-indisponivel")).toBeInTheDocument();
  });

  it("loads tiers from the PUBLIC /api/planos/publicos endpoint (A17) with no session set up in the test", async () => {
    mockGet.mockResolvedValue({ items: [PLANO], total: 1 });
    const { default: Assinar } = await import("../Assinar");
    renderPage(<Assinar />);

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/api/planos/publicos"));
    expect(mockGet).not.toHaveBeenCalledWith("/api/planos", expect.anything());
  });
});
