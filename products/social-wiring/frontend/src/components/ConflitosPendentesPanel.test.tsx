/**
 * ConflitosPendentesPanel.test.tsx — the container half of the admin
 * decide surface (owner directive, 2026-09-19). Mock strategy mirrors
 * `QualificacaoCompletudePanel.test.tsx`: one `vi.mock` per hook, plus the
 * two SSO-role modules `Equipe.tsx`'s own admin-visibility check uses.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { mockUseAuthStore, mockUseConflitosPendentes, mockMutate } = vi.hoisted(() => ({
  mockUseAuthStore: vi.fn(),
  mockUseConflitosPendentes: vi.fn(),
  mockMutate: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: mockUseAuthStore,
}));

vi.mock("@noctusai/lib", () => ({
  resolveSSOContext: (metadata: any) => {
    const m = metadata || {};
    const isProductAdmin =
      m.org_role === "owner" || m.org_role === "admin" || m.noctus_role === "admin";
    return {
      isSSO: !!m.noctus_role || !!m.org_role,
      isProductAdmin,
      plan: { slug: null, maxUsers: null, maxProducts: null, features: null },
      subscription: { status: null, expiresAt: null },
      license: { expiresAt: null },
      org: { name: null, logoUrl: null, role: m.org_role ?? "member" },
    };
  },
}));

vi.mock("@/hooks/useCardHub", () => ({
  useConflitosPendentes: (...a: any[]) => mockUseConflitosPendentes(...a),
  useDecidirConflitoMutation: () => ({
    mutate: mockMutate,
    isPending: false,
    variables: undefined,
  }),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ConflitosPendentesPanel } from "./ConflitosPendentesPanel";

function setUser(orgRole: string | null) {
  mockUseAuthStore.mockReturnValue({
    user: orgRole ? { user_metadata: { org_role: orgRole } } : { user_metadata: {} },
  });
}

const PENDENTE = {
  id: "c1",
  cliente_id: "cli-1",
  campo: "estado_civil",
  valor_anterior: "Casado(a)",
  origem_anterior: "certidao_casamento",
  valor_proposto: "Solteiro(a)",
  origem_proposto: "manual",
  confianca_proposta: null,
  status: "pendente" as const,
  created_at: "2026-09-20T00:00:00Z",
};

describe("ConflitosPendentesPanel", () => {
  it("renders nothing while there is nothing pending", async () => {
    setUser("owner");
    mockUseConflitosPendentes.mockReturnValue({ data: [] });
    const { render } = await import("@testing-library/react");
    const { container } = render(<ConflitosPendentesPanel clienteId="cli-1" />);
    expect(container.firstChild).toBeNull();
  });

  it("queries scoped to THIS cliente_id, not the org-wide queue", async () => {
    setUser("owner");
    mockUseConflitosPendentes.mockReturnValue({ data: [] });
    const { render } = await import("@testing-library/react");
    render(<ConflitosPendentesPanel clienteId="cli-42" />);
    expect(mockUseConflitosPendentes).toHaveBeenCalledWith("cli-42");
  });

  it("a member sees the pending conflict but no decide buttons", async () => {
    setUser("member");
    mockUseConflitosPendentes.mockReturnValue({ data: [PENDENTE] });
    const { render, screen } = await import("@testing-library/react");
    render(<ConflitosPendentesPanel clienteId="cli-1" />);
    expect(screen.getByText("Estado civil")).toBeTruthy();
    expect(screen.queryByTestId("conflitos-pendentes-cli-1-item-c1-aprovar")).toBeNull();
  });

  it("an owner sees the decide buttons and Aprovar calls the mutation", async () => {
    setUser("owner");
    mockUseConflitosPendentes.mockReturnValue({ data: [PENDENTE] });
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ConflitosPendentesPanel clienteId="cli-1" />);
    fireEvent.click(screen.getByTestId("conflitos-pendentes-cli-1-item-c1-aprovar"));
    expect(mockMutate).toHaveBeenCalledWith(
      { conflitoId: "c1", aceitar: true },
      expect.anything(),
    );
  });

  it("a platform admin (SSO isProductAdmin) also sees the decide buttons", async () => {
    mockUseAuthStore.mockReturnValue({
      user: { user_metadata: { noctus_role: "admin" } },
    });
    mockUseConflitosPendentes.mockReturnValue({ data: [PENDENTE] });
    const { render, screen } = await import("@testing-library/react");
    render(<ConflitosPendentesPanel clienteId="cli-1" />);
    expect(screen.getByTestId("conflitos-pendentes-cli-1-item-c1-aprovar")).toBeTruthy();
  });
});
