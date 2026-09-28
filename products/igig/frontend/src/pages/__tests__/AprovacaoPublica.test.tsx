/**
 * AprovacaoPublica — the white-label portal a CLIENT (no noc account) opens.
 *
 * achado 8: every load failure used to render the SAME "Link inválido ou
 * expirado", and "Sua agência já foi notificada" was shown unconditionally.
 * These tests pin the fix: 429 / network-or-5xx / genuinely-invalid render
 * DIFFERENT copy, and the notified claim only appears when the backend's
 * own `notificado` flag says so.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@noctusai/lib";

const mockUseAprovacaoPublica = vi.fn();
const mockDecidir = { mutate: vi.fn(), isPending: false, isSuccess: false, data: undefined as unknown };

vi.mock("@/hooks/useEsteira", () => ({
  useAprovacaoPublica: () => mockUseAprovacaoPublica(),
  useDecidirAprovacao: () => mockDecidir,
}));

import AprovacaoPublica from "../AprovacaoPublica";

function renderPortal() {
  return render(
    <MemoryRouter initialEntries={["/aprovar/org.abc123"]}>
      <Routes>
        <Route path="/aprovar/:token" element={<AprovacaoPublica />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDecidir.isSuccess = false;
  mockDecidir.data = undefined;
});

describe("AprovacaoPublica — error state honesty (achado 8)", () => {
  it("shows a rate-limit message for a 429, not the generic invalid-link copy", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: null, loading: false, error: new ApiError(429, "Muitas tentativas"),
    });
    renderPortal();
    expect(screen.getByText("Muitas tentativas")).toBeInTheDocument();
    expect(screen.queryByText("Link inválido ou expirado")).not.toBeInTheDocument();
  });

  it("shows an unreachable message for a network failure (status null)", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: null, loading: false, error: new ApiError(null, "Failed to fetch"),
    });
    renderPortal();
    expect(screen.getByText("Não foi possível carregar")).toBeInTheDocument();
  });

  it("shows an unreachable message for a 5xx", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: null, loading: false, error: new ApiError(503, "Service Unavailable"),
    });
    renderPortal();
    expect(screen.getByText("Não foi possível carregar")).toBeInTheDocument();
  });

  it("shows the portal-blocked message for a 423 portal_bloqueado, not the invalid-link copy", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: null, loading: false,
      error: new ApiError(423, "Portal temporariamente indisponível, contate a agência.", {
        code: "portal_bloqueado",
      }),
    });
    renderPortal();
    expect(screen.getByText("Portal temporariamente indisponível")).toBeInTheDocument();
    expect(screen.getByText("Contate a agência.")).toBeInTheDocument();
    expect(screen.queryByText("Link inválido ou expirado")).not.toBeInTheDocument();
  });

  it("keeps the single opaque message for a genuine 404 (unknown/expired/decided)", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: null, loading: false, error: new ApiError(404, "Link inválido ou expirado"),
    });
    renderPortal();
    expect(screen.getByText("Link inválido ou expirado")).toBeInTheDocument();
  });
});

describe("AprovacaoPublica — 'agência notificada' only when it actually happened", () => {
  it("claims notification when this session's own decision reports notificado=true", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: { ja_decidida: false, aguardando_aprovacao: true, pecas: [], titulo: "Post" },
      loading: false, error: null,
    });
    mockDecidir.isSuccess = true;
    mockDecidir.data = { ok: true, decisao: "aprovado", notificado: true };
    renderPortal();
    expect(screen.getByText("Obrigado! Sua agência já foi notificada.")).toBeInTheDocument();
  });

  it("does NOT claim notification when notificado=false", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: { ja_decidida: false, aguardando_aprovacao: true, pecas: [], titulo: "Post" },
      loading: false, error: null,
    });
    mockDecidir.isSuccess = true;
    mockDecidir.data = { ok: true, decisao: "aprovado", notificado: false };
    renderPortal();
    expect(screen.getByText("Obrigado pela resposta.")).toBeInTheDocument();
    expect(screen.queryByText(/já foi notificada/)).not.toBeInTheDocument();
  });

  it("a link opened ALREADY decided (no decision made this session) never claims notification", () => {
    mockUseAprovacaoPublica.mockReturnValue({
      aprovacao: { ja_decidida: true, aguardando_aprovacao: false, pecas: [], titulo: "Post" },
      loading: false, error: null,
    });
    renderPortal();
    expect(screen.getByText("Obrigado pela resposta.")).toBeInTheDocument();
  });
});
