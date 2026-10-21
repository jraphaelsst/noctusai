import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockTokens = vi.fn();
const mint = { mutateAsync: vi.fn(), isPending: false };
const revoke = { mutateAsync: vi.fn(), isPending: false };

vi.mock("@/hooks/studio/useContentToken", () => ({
  useContentTokens: () => mockTokens(),
  useMintContentToken: () => mint,
  useRevokeContentToken: () => revoke,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ContentTokenCard } from "../ContentTokenCard";

const row = (over: object = {}) => ({
  id: "t1", label: "notebook", prefix: "pk_abcd123", scopes: ["studio:content-write"],
  created_at: "2026-10-01T10:00:00Z", created_by: "11111111-2222-3333-4444-555555555555",
  expires_at: null, last_used_at: null, revoked_at: null, status: "ativo", ...over,
});
const view = (over: object) => ({
  data: { itens: [] }, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockTokens.mockReturnValue(view({}));
});
afterEach(cleanup);

describe("ContentTokenCard", () => {
  it("renders skeleton, error and empty states", () => {
    mockTokens.mockReturnValue(view({ data: undefined, showSkeleton: true }));
    const { rerender } = render(<ContentTokenCard />);
    expect(screen.getByTestId("content-tokens-skeleton")).toBeTruthy();
    mockTokens.mockReturnValue(view({ data: undefined, isError: true, error: new Error("falhou") }));
    rerender(<ContentTokenCard />);
    expect(screen.getByTestId("studio-error")).toBeTruthy();
    mockTokens.mockReturnValue(view({}));
    rerender(<ContentTokenCard />);
    expect(screen.getByText(/Nenhum token de conteúdo emitido/)).toBeTruthy();
  });

  it("says plainly what the token does", () => {
    render(<ContentTokenCard />);
    expect(screen.getByText(/rascunhos/)).toBeTruthy();
    expect(screen.getByText(/nunca publica uma versão e nunca conversa com leads/)).toBeTruthy();
  });

  it("lists tokens with Nunca for a null expiry, and never shows a secret", () => {
    mockTokens.mockReturnValue(view({ data: { itens: [row(), row({ id: "t2", status: "revogado", revoked_at: "2026-10-02T00:00:00Z" })] } }));
    render(<ContentTokenCard />);
    expect(screen.getByTestId("content-token-expira-t1").textContent).toBe("Nunca");
    expect(screen.getByTestId("content-token-status-t2").textContent).toBe("Revogado");
    expect(screen.queryByTestId("content-token-revoke-t2")).toBeNull();
    expect(screen.getByTestId("content-token-revoke-t1")).toBeTruthy();
  });

  it("mints with 30 days by default, reveals once, shows where to put it, and discards on close", async () => {
    mint.mutateAsync.mockResolvedValue({ id: "t1", token: "pk_secret_value", prefix: "pk_secre", expires_at: "2026-11-20T00:00:00Z", scopes: [] });
    render(<ContentTokenCard />);
    fireEvent.click(screen.getByTestId("content-token-new"));
    expect((screen.getByTestId("content-token-mint") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("content-token-label"), { target: { value: "meu notebook" } });
    fireEvent.click(screen.getByTestId("content-token-mint"));
    await waitFor(() => expect(screen.getByTestId("content-token-value").textContent).toBe("pk_secret_value"));
    expect(mint.mutateAsync).toHaveBeenCalledWith({ label: "meu notebook", expira_em_dias: 30 });
    expect(screen.getByText(/não será mostrado de novo/)).toBeTruthy();
    expect(screen.getByText(/NOCTUS_AGENTS_CONTENT_TOKEN=/)).toBeTruthy();
    expect(screen.getByText(/agents\.env/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("content-token-close"));
    expect(screen.queryByText("pk_secret_value")).toBeNull();
  });

  it("sends the chosen number of days and validates the range", () => {
    render(<ContentTokenCard />);
    fireEvent.click(screen.getByTestId("content-token-new"));
    fireEvent.change(screen.getByTestId("content-token-label"), { target: { value: "x" } });
    fireEvent.change(screen.getByTestId("content-token-dias"), { target: { value: "400" } });
    expect(screen.getByTestId("content-token-dias-erro")).toBeTruthy();
    expect((screen.getByTestId("content-token-mint") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("content-token-dias"), { target: { value: "7" } });
    expect((screen.getByTestId("content-token-mint") as HTMLButtonElement).disabled).toBe(false);
  });

  it("never-expires warns clearly and sends expira_em_dias null", async () => {
    mint.mutateAsync.mockResolvedValue({ id: "t1", token: "pk_x", prefix: "pk_x", expires_at: null, scopes: [] });
    render(<ContentTokenCard />);
    fireEvent.click(screen.getByTestId("content-token-new"));
    fireEvent.change(screen.getByTestId("content-token-label"), { target: { value: "perm" } });
    fireEvent.click(screen.getByTestId("content-token-modo-nunca"));
    expect(screen.getByTestId("content-token-nunca-aviso").textContent).toMatch(/continua válido até ser revogado/);
    fireEvent.click(screen.getByTestId("content-token-mint"));
    await waitFor(() => expect(mint.mutateAsync).toHaveBeenCalledWith({ label: "perm", expira_em_dias: null }));
    await waitFor(() => expect(screen.getByText(/vale até ser revogado/)).toBeTruthy());
  });

  it("revokes only after the confirm modal", async () => {
    mockTokens.mockReturnValue(view({ data: { itens: [row()] } }));
    revoke.mutateAsync.mockResolvedValue({});
    render(<ContentTokenCard />);
    fireEvent.click(screen.getByTestId("content-token-revoke-t1"));
    expect(revoke.mutateAsync).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("content-token-revoke-confirm"));
    await waitFor(() => expect(revoke.mutateAsync).toHaveBeenCalledWith("t1"));
  });
});
