import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const v = (over: object) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over });
const mockConvs = vi.fn();
const mockMsgs = vi.fn();
const mockKeys = vi.fn();
const mockGrants = vi.fn();

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
vi.mock("@/hooks/useGrants", async (orig) => ({
  ...(await orig<typeof import("@/hooks/useGrants")>()),
  useGrants: () => mockGrants(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import ChannelsTab from "../ChannelsTab";
import { ApiError } from "@/lib/errors";

const renderTab = () => render(<MemoryRouter><ChannelsTab agentKey="julia" /></MemoryRouter>);

beforeEach(() => {
  mockKeys.mockReturnValue(v({ data: { items: [{ key: "openai_api_key", configured: false }], total: 1 } }));
  mockMsgs.mockReturnValue(v({}));
  mockGrants.mockReturnValue(v({ data: { items: [], total: 0 } }));
});
afterEach(cleanup);

describe("ChannelsTab", () => {
  it("flags a missing provider key and shows the empty conversation state", () => {
    mockConvs.mockReturnValue(v({ data: [] }));
    renderTab();
    expect(screen.getByText("Não configurada")).toBeTruthy();
    expect(screen.getByText("Nenhuma conversa de canal ainda.")).toBeTruthy();
    expect(screen.getByTestId("channel-grants").querySelector("a")?.getAttribute("href")).toBe("/conexoes-plataforma");
    expect(screen.getByTestId("channel-grants-empty")).toBeTruthy();
    expect(screen.queryByTestId("channel-token-card")).toBeNull();
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
  it("lists this agent's live connections as product · org, without the agent name", () => {
    mockConvs.mockReturnValue(v({ data: [] }));
    const g = { id: "g1", org_id: "o1", org_nome: "One Consultoria", agent_id: "a", agent_key: "julia", product: "social-wiring",
      status: "ativo", channel_token_id: "t", token_prefix: "noc_6be7", product_token_id: "p", expires_at: null,
      created_at: null, revoked_at: null, last_delivered_at: "2026-11-05T17:08:17Z", last_error: null };
    mockGrants.mockReturnValue(v({ data: { items: [g, { ...g, id: "g2", agent_key: "bia" }, { ...g, id: "g3", status: "revogado" }], total: 3 } }));
    renderTab();
    const rows = screen.getAllByTestId("channel-grant-row");
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain("social-wiring");
    expect(rows[0].textContent).toContain("One Consultoria");
    expect(rows[0].textContent).toContain("noc_6be7…");
    expect(rows[0].textContent).toContain("Ativo");
    expect(rows[0].textContent).not.toContain("julia");
  });

  it("a non platform admin (403) sees only the hint, never an error", () => {
    mockConvs.mockReturnValue(v({ data: [] }));
    mockGrants.mockReturnValue(v({ isError: true, error: new ApiError(403, "Erro HTTP 403", { code: "forbidden" }) }));
    renderTab();
    expect(screen.getByTestId("channel-grants-hint")).toBeTruthy();
    expect(screen.queryByTestId("channel-grants-list")).toBeNull();
  });
});
