import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockTokens = vi.fn();
const mint = { mutateAsync: vi.fn(), isPending: false };
const revoke = { mutateAsync: vi.fn(), isPending: false };

vi.mock("@/hooks/useChannel", () => ({
  useChannelTokens: () => mockTokens(),
  useMintChannelToken: () => mint,
  useRevokeChannelToken: () => revoke,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ChannelTokenCard } from "../ChannelTokenCard";

const view = (over: object) => ({
  data: [],
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockTokens.mockReturnValue(view({}));
});
afterEach(cleanup);

describe("ChannelTokenCard", () => {
  it("renders skeleton, error and empty states", () => {
    mockTokens.mockReturnValue(view({ data: undefined, showSkeleton: true }));
    const { rerender } = render(<ChannelTokenCard agentKey="julia" isAdmin />);
    expect(screen.getByTestId("channel-tokens-skeleton")).toBeTruthy();
    mockTokens.mockReturnValue(view({ data: undefined, isError: true, error: new Error("falhou") }));
    rerender(<ChannelTokenCard agentKey="julia" isAdmin />);
    expect(screen.getByTestId("studio-error")).toBeTruthy();
    mockTokens.mockReturnValue(view({}));
    rerender(<ChannelTokenCard agentKey="julia" isAdmin />);
    expect(screen.getByText(/Nenhum token de canal ativo/)).toBeTruthy();
  });

  it("mints, reveals the token once, and discards it on close", async () => {
    mint.mutateAsync.mockResolvedValue({
      id: "t1", token: "pk_secret_value", prefix: "pk_secr", expires_at: "2026-11-01T00:00:00Z", scopes: [],
    });
    render(<ChannelTokenCard agentKey="julia" isAdmin />);
    fireEvent.click(screen.getByTestId("channel-token-new"));
    fireEvent.click(screen.getByTestId("channel-token-mint"));
    await waitFor(() => expect(screen.getByTestId("channel-token-value").textContent).toBe("pk_secret_value"));
    expect(screen.getByText(/não será mostrado de novo/)).toBeTruthy();
    expect(screen.getByText(/Social Wiring › Lais › Agente/)).toBeTruthy();
    expect(mint.mutateAsync).toHaveBeenCalledWith({ label: "producao" });
    fireEvent.click(screen.getByTestId("channel-token-close"));
    expect(screen.queryByText("pk_secret_value")).toBeNull();
  });

  it("lists active tokens and revokes with confirmation; hides actions for non-admins", async () => {
    mockTokens.mockReturnValue(
      view({ data: [{ id: "t1", label: "canal social-wiring · julia: x", prefix: "pk_ab", scopes: [], created_at: "2026-10-01T10:00:00Z", last_used_at: null, revoked_at: null }] }),
    );
    revoke.mutateAsync.mockResolvedValue(undefined);
    const { rerender } = render(<ChannelTokenCard agentKey="julia" isAdmin />);
    fireEvent.click(screen.getByTestId("channel-token-revoke-t1"));
    fireEvent.click(screen.getByTestId("channel-token-revoke-confirm"));
    await waitFor(() => expect(revoke.mutateAsync).toHaveBeenCalledWith("t1"));
    rerender(<ChannelTokenCard agentKey="julia" isAdmin={false} />);
    expect(screen.queryByTestId("channel-token-new")).toBeNull();
    expect(screen.queryByTestId("channel-token-revoke-t1")).toBeNull();
  });
});
