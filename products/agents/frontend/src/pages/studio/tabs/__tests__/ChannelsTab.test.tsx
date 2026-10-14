import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const v = (over: object) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over });
const mockConvs = vi.fn();
const mockMsgs = vi.fn();
const mockKeys = vi.fn();

vi.mock("@/hooks/useChannel", () => ({
  useChannelConversations: () => mockConvs(),
  useChannelMessages: () => mockMsgs(),
}));
vi.mock("@/hooks/useOrgApiKeys", () => ({
  orgApiKeysHooks: { useApiKeys: () => mockKeys() },
  isProviderKeyConfigured: (s: { items: { key: string; configured: boolean }[] } | undefined, p: string) =>
    s?.items.find((k) => k.key === `${p}_api_key`)?.configured,
}));
vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => ({ showSkeleton: false, draft: { versao: 2, provider: "openai" }, ativa: null }),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));
vi.mock("@/components/studio/ChannelTokenCard", () => ({ ChannelTokenCard: () => <div data-testid="token-card-stub" /> }));

import ChannelsTab from "../ChannelsTab";

const renderTab = () => render(<MemoryRouter><ChannelsTab agentKey="lead-imob" /></MemoryRouter>);

beforeEach(() => {
  mockKeys.mockReturnValue(v({ data: { items: [{ key: "openai_api_key", configured: false }], total: 1 } }));
  mockMsgs.mockReturnValue(v({}));
});
afterEach(cleanup);

describe("ChannelsTab", () => {
  it("flags a missing provider key and shows the empty conversation state", () => {
    mockConvs.mockReturnValue(v({ data: [] }));
    renderTab();
    expect(screen.getByText("Não configurada")).toBeTruthy();
    expect(screen.getByText("Nenhuma conversa de canal ainda.")).toBeTruthy();
    expect(screen.getByTestId("token-card-stub")).toBeTruthy();
  });

  it("lists conversations and opens one read-only (no composer)", () => {
    mockConvs.mockReturnValue(v({ data: [{ id: "c1", titulo: null, status: "ativa", last_message_at: null, created_at: "2026-10-10T10:00:00Z", channel: "whatsapp", contact: { nome: "Maria" } }] }));
    mockMsgs.mockReturnValue(v({ data: [{ id: "m1", role: "user", texto: "Oi", created_at: "2026-10-10T10:00:00Z" }] }));
    renderTab();
    fireEvent.click(screen.getByTestId("channel-conversation-c1"));
    expect(screen.getByText("Oi")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("shows error with retry", () => {
    mockConvs.mockReturnValue(v({ isError: true, error: new Error("x") }));
    renderTab();
    expect(screen.getByTestId("studio-error")).toBeTruthy();
  });
});
