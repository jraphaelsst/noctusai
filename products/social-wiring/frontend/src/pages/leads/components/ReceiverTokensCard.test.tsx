/**
 * ReceiverTokensCard — the states, and the three things that lose leads.
 *
 * 1. The minted URL is shown once and never again, so the reveal must
 *    survive a re-render and must not be a toast.
 * 2. A URL that has never received anything is a wrong paste into Canal
 *    Pro wearing the costume of a quiet week — it has to be called out.
 * 3. Revoking before the replacement is live drops every lead in the
 *    gap, and Grupo OLX does not resend, so revoke is two-step and says
 *    the order out loud.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const {
  useReceiverTokensMock,
  useMintReceiverTokenMock,
  useRevokeReceiverTokenMock,
  mintMutateAsync,
  revokeMutateAsync,
} = vi.hoisted(() => ({
  useReceiverTokensMock: vi.fn(),
  useMintReceiverTokenMock: vi.fn(),
  useRevokeReceiverTokenMock: vi.fn(),
  mintMutateAsync: vi.fn(),
  revokeMutateAsync: vi.fn(),
}));

vi.mock("@/hooks/useReceiverTokens", () => ({
  useReceiverTokens: useReceiverTokensMock,
  useMintReceiverToken: useMintReceiverTokenMock,
  useRevokeReceiverToken: useRevokeReceiverTokenMock,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ReceiverTokensCard from "./ReceiverTokensCard";

function token(over: Record<string, unknown> = {}) {
  return {
    id: "tok-1",
    provider: "olx",
    label: "One Consultoria",
    token_prefix: "rcv_ab12",
    created_at: "2026-08-19T10:00:00Z",
    last_seen_at: "2026-08-19T12:00:00Z",
    revoked_at: null,
    ...over,
  };
}

function state(over: Record<string, unknown> = {}) {
  const tokens = (over.active as unknown[]) ?? [];
  useReceiverTokensMock.mockReturnValue({
    tokens,
    active: tokens,
    revoked: [],
    neverUsed: [],
    loading: false,
    isEmpty: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mintMutateAsync.mockResolvedValue({
    id: "tok-2",
    provider: "olx",
    label: "Nova",
    token_prefix: "rcv_zz99",
    url: "https://social-wiring.noctusai.com/api/portals/olx/leads/rcv_zz99secret",
  });
  revokeMutateAsync.mockResolvedValue({ status: "revoked", id: "tok-1" });
  useMintReceiverTokenMock.mockReturnValue({
    mutateAsync: mintMutateAsync,
    isPending: false,
  });
  useRevokeReceiverTokenMock.mockReturnValue({
    mutateAsync: revokeMutateAsync,
    isPending: false,
  });
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("states", () => {
  it("shows a skeleton while loading", () => {
    state({ loading: true });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-loading")).toBeTruthy();
  });

  it("does not claim 'no URLs' while a refetch is in flight", () => {
    // The lying-loading-state trap: `isEmpty` must never win over a
    // background refetch, or an operator mints a duplicate URL for a
    // client who already has one.
    state({ loading: true, isEmpty: false });
    render(<ReceiverTokensCard />);

    expect(screen.queryByTestId("receiver-tokens-empty")).toBeNull();
  });

  it("explains the empty state as expected, not broken", () => {
    state({ isEmpty: true });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-empty").textContent).toMatch(/Canal Pro/i);
  });

  it("surfaces a load error", () => {
    state({ isError: true, error: new Error("boom") });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-error").textContent).toContain("boom");
  });

  it("lists active URLs with when they last received", () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-token-tok-1").textContent).toContain("One Consultoria");
    expect(screen.getByTestId("receiver-token-tok-1").textContent).toContain("rcv_ab12");
  });
});

describe("the URL that never received anything", () => {
  it("is called out rather than left to be noticed", () => {
    const unused = token({ id: "tok-3", last_seen_at: null });
    state({ active: [unused], neverUsed: [unused] });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-unused-banner").textContent).toMatch(/colada errada/i);
  });

  it("reads as healthy when every URL has received", () => {
    state({ active: [token()], neverUsed: [] });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-healthy")).toBeTruthy();
  });
});

describe("minting", () => {
  it("refuses an empty label instead of creating an unidentifiable URL", async () => {
    state({ isEmpty: true });
    render(<ReceiverTokensCard />);

    fireEvent.click(screen.getByTestId("receiver-token-mint"));

    await waitFor(() => expect(mintMutateAsync).not.toHaveBeenCalled());
  });

  it("reveals the URL once and says it will not be shown again", async () => {
    state({ isEmpty: true });
    render(<ReceiverTokensCard />);

    fireEvent.change(screen.getByTestId("receiver-token-label-input"), {
      target: { value: "Nova Imobiliária" },
    });
    fireEvent.click(screen.getByTestId("receiver-token-mint"));

    const reveal = await screen.findByTestId("receiver-token-reveal");
    expect(reveal.textContent).toMatch(/não será mostrada de novo/i);
    expect(screen.getByTestId("receiver-token-url").textContent).toContain("rcv_zz99secret");
  });

  it("keeps the reveal until it is dismissed", async () => {
    state({ isEmpty: true });
    render(<ReceiverTokensCard />);

    fireEvent.change(screen.getByTestId("receiver-token-label-input"), {
      target: { value: "Nova" },
    });
    fireEvent.click(screen.getByTestId("receiver-token-mint"));
    await screen.findByTestId("receiver-token-reveal");

    fireEvent.click(screen.getByTestId("receiver-token-dismiss"));

    await waitFor(() =>
      expect(screen.queryByTestId("receiver-token-reveal")).toBeNull());
  });

  it("copies the full URL, not the prefix", async () => {
    state({ isEmpty: true });
    render(<ReceiverTokensCard />);

    fireEvent.change(screen.getByTestId("receiver-token-label-input"), {
      target: { value: "Nova" },
    });
    fireEvent.click(screen.getByTestId("receiver-token-mint"));
    await screen.findByTestId("receiver-token-reveal");

    fireEvent.click(screen.getByTestId("receiver-token-copy"));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://social-wiring.noctusai.com/api/portals/olx/leads/rcv_zz99secret"));
  });
});

describe("revoking", () => {
  it("does not revoke on the first click", () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    fireEvent.click(screen.getByTestId("receiver-token-revoke-tok-1"));

    expect(revokeMutateAsync).not.toHaveBeenCalled();
  });

  it("asks whether the replacement is already in Canal Pro", () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    fireEvent.click(screen.getByTestId("receiver-token-revoke-tok-1"));

    expect(screen.getByTestId("receiver-token-revoke-confirm-tok-1")).toBeTruthy();
    expect(screen.getByTestId("receiver-token-tok-1").textContent).toMatch(/Já colou a nova URL/i);
  });

  it("revokes only after confirmation", async () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    fireEvent.click(screen.getByTestId("receiver-token-revoke-tok-1"));
    fireEvent.click(screen.getByTestId("receiver-token-revoke-confirm-tok-1"));

    await waitFor(() => expect(revokeMutateAsync).toHaveBeenCalledWith("tok-1"));
  });

  it("can be backed out of", () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    fireEvent.click(screen.getByTestId("receiver-token-revoke-tok-1"));
    fireEvent.click(screen.getByTestId("receiver-token-revoke-cancel-tok-1"));

    expect(revokeMutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByTestId("receiver-token-revoke-confirm-tok-1")).toBeNull();
  });

  it("states the safe rotation order", () => {
    state({ active: [token()] });
    render(<ReceiverTokensCard />);

    expect(screen.getByTestId("receiver-tokens-success").textContent).toMatch(/não reenvia/i);
  });
});
