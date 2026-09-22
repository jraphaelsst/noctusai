/**
 * VersionsTab.tsx — publish dialog 409 `draft_changed` handling (backend
 * hardening add-on, tech-lead "item 7"): the draft's hash moved between the
 * gating eval run and the publish call, so the server refuses; the dialog
 * must say so in pt-BR and recompile (`useCompiled`'s `refetch`) so "Hash
 * atual" is current for a retry. Stubs `useVersions.ts` + `useCompiled.ts` +
 * `useIsAdmin` — each hook has its own request-shape test.
 */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/errors";

const mockUseAgentVersionRefs = vi.fn();
const mockUseCreateDraft = vi.fn();
const mockUseDiscardDraft = vi.fn();
const mockUsePublishDraft = vi.fn();
const mockUseVersionDiff = vi.fn();
const mockUseCompiled = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => mockUseAgentVersionRefs(),
  useCreateDraft: () => mockUseCreateDraft(),
  useDiscardDraft: () => mockUseDiscardDraft(),
  usePublishDraft: () => mockUsePublishDraft(),
  useVersionDiff: () => mockUseVersionDiff(),
}));
vi.mock("@/hooks/studio/useCompiled", () => ({ useCompiled: () => mockUseCompiled() }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const DRAFT = {
  id: "v2",
  versao: 2,
  status: "rascunho" as const,
  notas: null,
  model: "claude-opus-5" as const,
  created_at: "2026-09-20T10:00:00Z",
  published_at: null,
  compiled_hash: "sha256:" + "b".repeat(64),
  eval_score: 0.9,
};

const AGENT = {
  id: "a1",
  key: "isaia",
  nome: "IsaIA",
  descricao: null,
  definition_mode: "studio" as const,
  ativo: true,
  publicacao_limiar: 0.8,
  versao_ativa: null,
  tem_rascunho: true,
  versoes: [DRAFT],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(true);
  mockUseAgentVersionRefs.mockReturnValue({
    data: AGENT,
    draft: DRAFT,
    ativa: null,
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
  mockUseCreateDraft.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDiscardDraft.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseVersionDiff.mockReturnValue({ data: undefined, showSkeleton: false, isError: false, error: null, refetch: vi.fn() });
  mockUseCompiled.mockReturnValue({
    data: { hash: DRAFT.compiled_hash, avisos: [] },
    showSkeleton: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
});

afterEach(() => cleanup());

async function renderVersionsTab() {
  const VersionsTab = (await import("@/pages/studio/tabs/VersionsTab")).default;
  render(
    <MemoryRouter initialEntries={["/studio/isaia?tab=versoes&publicar=1"]}>
      <Routes>
        <Route path="/studio/:key" element={<VersionsTab agentKey="isaia" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("VersionsTab — publish dialog, 409 draft_changed", () => {
  it("shows the pt-BR recompile message and refetches the compiled view", async () => {
    const compiledRefetch = vi.fn();
    mockUseCompiled.mockReturnValue({
      data: { hash: DRAFT.compiled_hash, avisos: [] },
      showSkeleton: false,
      isError: false,
      error: null,
      refetch: compiledRefetch,
    });
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError(409, "O rascunho mudou", { detail: "O rascunho mudou", code: "draft_changed" }));
    mockUsePublishDraft.mockReturnValue({ mutateAsync, isPending: false });

    await renderVersionsTab();
    fireEvent.click(await screen.findByTestId("publish-confirm"));

    const erro = await screen.findByTestId("publish-erro");
    expect(erro.textContent).toContain("O rascunho mudou desde a última compilação — recompile e tente de novo.");
    await waitFor(() => expect(compiledRefetch).toHaveBeenCalled());
  });

  it("a plain eval_required 409 still shows the gate UI, not the draft_changed message", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(
      new ApiError(409, "Avaliação necessária", {
        detail: "Avaliação necessária",
        code: "eval_required",
        hash_atual: DRAFT.compiled_hash,
        ultima_execucao: null,
      }),
    );
    mockUsePublishDraft.mockReturnValue({ mutateAsync, isPending: false });

    await renderVersionsTab();
    fireEvent.click(await screen.findByTestId("publish-confirm"));

    const erro = await screen.findByTestId("publish-erro");
    expect(erro.textContent).not.toContain("recompile e tente de novo");
  });
});
