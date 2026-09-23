/**
 * SkillsTab.tsx tests — Agent Studio CONTRACT.md §G "Skills". Stubs every
 * `useVersions.ts` hook this tab (and its nested `SkillFilesUploadDialog`)
 * touches + `useIsAdmin`. Focused on the ▲▼ reorder control (item 5 of the
 * "build IsaIA entirely through the UI" audit) — everything else about this
 * tab (editor fields, file add/edit/delete) is exercised implicitly by the
 * existing `studioHooks.test.ts` wire-shape tests.
 */
import React from "react";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseAgentVersionRefs = vi.fn();
const mockUseVersion = vi.fn();
const mockUseCreateSkill = vi.fn();
const mockUseUpdateSkill = vi.fn();
const mockUseDeleteSkill = vi.fn();
const mockUseSkillFile = vi.fn();
const mockUseUpsertSkillFile = vi.fn();
const mockUseDeleteSkillFile = vi.fn();
const mockUseBatchUpsertSkillFiles = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/studio/useVersions", () => ({
  useAgentVersionRefs: () => mockUseAgentVersionRefs(),
  useVersion: () => mockUseVersion(),
  useCreateSkill: () => mockUseCreateSkill(),
  useUpdateSkill: () => mockUseUpdateSkill(),
  useDeleteSkill: () => mockUseDeleteSkill(),
  useSkillFile: () => mockUseSkillFile(),
  useUpsertSkillFile: () => mockUseUpsertSkillFile(),
  useDeleteSkillFile: () => mockUseDeleteSkillFile(),
  useBatchUpsertSkillFiles: () => mockUseBatchUpsertSkillFiles(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const SKILL_A = { id: "skill-a", nome: "skill-a", descricao: "Descrição A", corpo: "corpo a", ordem: 10, ativo: true, arquivos: [] };
const SKILL_B = { id: "skill-b", nome: "skill-b", descricao: "Descrição B", corpo: "corpo b", ordem: 20, ativo: true, arquivos: [] };

const DRAFT_REF = { id: "v2", versao: 2, status: "rascunho" as const, notas: null, model: "claude-sonnet-5" as const, created_at: "t", published_at: null, compiled_hash: null, eval_score: null };

const VERSION_DETAIL = {
  ...DRAFT_REF,
  effort: "medium" as const,
  max_turns: 20,
  idioma: "pt-BR",
  tool_policy: { web_search: false, knowledge: true },
  based_on_version_id: null,
  published_by: null,
  publish_override_reason: null,
  eval_run_id: null,
  secoes: [],
  skills: [SKILL_A, SKILL_B],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(true);
  mockUseAgentVersionRefs.mockReturnValue({
    draft: DRAFT_REF,
    ativa: null,
    showSkeleton: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
  mockUseVersion.mockReturnValue({
    data: VERSION_DETAIL,
    isPlaceholderData: false,
    showSkeleton: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isRefreshing: false,
  });
  mockUseCreateSkill.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateSkill.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue(SKILL_A), isPending: false });
  mockUseDeleteSkill.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseSkillFile.mockReturnValue({ data: undefined, showSkeleton: false, isError: false, isPlaceholderData: false });
  mockUseUpsertSkillFile.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDeleteSkillFile.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseBatchUpsertSkillFiles.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

afterEach(() => cleanup());

async function renderTab() {
  const SkillsTab = (await import("@/pages/studio/tabs/SkillsTab")).default;
  render(
    <MemoryRouter initialEntries={["/studio/isaia?tab=skills"]}>
      <Routes>
        <Route path="/studio/:key" element={<SkillsTab agentKey="isaia" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SkillsTab — reorder (▲▼)", () => {
  it("moving the first skill down swaps both skills' ordem (renumbered by position, 10/20)", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(SKILL_A);
    mockUseUpdateSkill.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("skill-move-down-skill-a"));

    expect(mutateAsync).toHaveBeenCalledTimes(2);
    expect(mutateAsync).toHaveBeenCalledWith({ skillId: "skill-b", patch: { ordem: 10 } });
    expect(mutateAsync).toHaveBeenCalledWith({ skillId: "skill-a", patch: { ordem: 20 } });
  });

  it("disables the ▲ button on the first skill and the ▼ button on the last skill", async () => {
    await renderTab();
    expect(screen.getByTestId("skill-move-up-skill-a").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("skill-move-down-skill-b").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("skill-move-down-skill-a").hasAttribute("disabled")).toBe(false);
    expect(screen.getByTestId("skill-move-up-skill-b").hasAttribute("disabled")).toBe(false);
  });

  it("hides the ▲▼ controls for a non-admin (read-only)", async () => {
    mockUseIsAdmin.mockReturnValue(false);
    await renderTab();
    expect(screen.queryByTestId("skill-move-down-skill-a")).toBeNull();
  });
});

describe("SkillsTab — file upload trigger", () => {
  it("shows 'Enviar arquivos' and opens the batch upload dialog for an admin with a selected skill", async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId("skill-item-skill-a"));
    fireEvent.click(await screen.findByTestId("skill-files-upload-toggle"));
    expect(await screen.findByTestId("skill-files-upload-dialog")).toBeTruthy();
  });
});
