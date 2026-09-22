/**
 * SettingsTab.tsx — the model selector (§B1 `agent_versions.model`).
 * Stubs `useVersions`/`useStudioAgents`/`useIsAdmin` so this test asserts
 * ONLY the "Modelo" select's options, mirroring `JuliaPersona.test.tsx`'s
 * equivalent coverage for the persona page's own selector.
 */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseAgentVersionRefs = vi.fn();
const mockUseVersion = vi.fn();
const mockUseUpdateDraft = vi.fn();
const mockUseUpdateStudioAgent = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => mockUseAgentVersionRefs(),
  useVersion: () => mockUseVersion(),
  useUpdateDraft: () => mockUseUpdateDraft(),
}));
vi.mock("@/hooks/studio/useStudioAgents", () => ({
  useUpdateStudioAgent: () => mockUseUpdateStudioAgent(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const DRAFT_REF = {
  id: "v2",
  versao: 2,
  status: "rascunho" as const,
  notas: null,
  model: "claude-opus-5" as const,
  created_at: "2026-09-20T10:00:00Z",
  published_at: null,
  compiled_hash: null,
  eval_score: null,
};

const VERSION_DETAIL = {
  ...DRAFT_REF,
  effort: "high" as const,
  max_turns: 40,
  idioma: "pt-BR",
  tool_policy: { web_search: true, knowledge: true },
  based_on_version_id: null,
  published_by: null,
  publish_override_reason: null,
  eval_run_id: null,
  secoes: [],
  skills: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(true);
  mockUseAgentVersionRefs.mockReturnValue({
    data: { publicacao_limiar: 0.8 },
    draft: DRAFT_REF,
    ativa: null,
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isPlaceholderData: false,
  });
  mockUseVersion.mockReturnValue({
    data: VERSION_DETAIL,
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isPlaceholderData: false,
  });
  mockUseUpdateDraft.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateStudioAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

afterEach(() => cleanup());

async function renderTab() {
  const SettingsTab = (await import("@/pages/studio/tabs/SettingsTab")).default;
  render(React.createElement(SettingsTab, { agentKey: "isaia" }));
}

describe("SettingsTab — model selector", () => {
  it("offers all three allowed models, Haiku labelled as the cheapest/fastest option", async () => {
    await renderTab();

    const select = screen.getByLabelText("Modelo") as HTMLSelectElement;
    const options = Array.from(select.options);
    expect(options.map((o) => o.value)).toEqual(["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]);
    const haiku = options.find((o) => o.value === "claude-haiku-4-5")!;
    expect(haiku.textContent).toMatch(/haiku/i);
    expect(haiku.textContent).toMatch(/rápido|barato/i);
  });
});
