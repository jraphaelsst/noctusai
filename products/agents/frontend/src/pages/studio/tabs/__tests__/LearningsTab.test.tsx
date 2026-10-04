/**
 * LearningsTab.tsx tests — Agent Packages CONTRACT §D3 / §H2. Stubs the
 * `usePackages.ts` hooks + `useIsAdmin`.
 */
import React from "react";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseLearnings = vi.fn();
const mockUsePackageProjects = vi.fn();
const mockUseReviewLearning = vi.fn();
const mockUseIsAdmin = vi.fn();
const mutateAsync = vi.fn();

vi.mock("@/hooks/studio/usePackages", () => ({
  useLearnings: (...args: unknown[]) => mockUseLearnings(...args),
  usePackageProjects: () => mockUsePackageProjects(),
  useReviewLearning: () => mockUseReviewLearning(),
}));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const LEARNING = {
  id: "l1",
  project_slug: "noc",
  row_sha: "a".repeat(64),
  data: "2026-10-01",
  tipo: "pitfall",
  texto: "Nunca rode o gate sem deps.",
  evidencia: "PR #12",
  row_status: "novo",
  status: "novo" as const,
  nota: null,
  reviewed_by: null,
  reviewed_at: null,
  created_at: "2026-10-01T00:00:00Z",
};

const OK = { data: [LEARNING], showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(false);
  mockUseLearnings.mockReturnValue(OK);
  mockUsePackageProjects.mockReturnValue({ data: [{ slug: "noc" }, { slug: "outro" }] });
  mutateAsync.mockResolvedValue(undefined);
  mockUseReviewLearning.mockReturnValue({ mutateAsync, isPending: false });
});

afterEach(() => cleanup());

async function renderTab() {
  const LearningsTab = (await import("@/pages/studio/tabs/LearningsTab")).default;
  render(React.createElement(LearningsTab, { agentKey: "isaia-dev" }));
}

describe("LearningsTab — states", () => {
  it("shows a skeleton while loading", async () => {
    mockUseLearnings.mockReturnValue({ ...OK, data: undefined, showSkeleton: true });
    await renderTab();
    expect(screen.getByTestId("learnings-skeleton")).toBeTruthy();
  });

  it("shows an error with retry", async () => {
    mockUseLearnings.mockReturnValue({ ...OK, data: undefined, isError: true, error: new Error("boom") });
    await renderTab();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows an empty state", async () => {
    mockUseLearnings.mockReturnValue({ ...OK, data: [] });
    await renderTab();
    expect(screen.getByText("Nenhum aprendizado encontrado")).toBeTruthy();
  });

  it("lists rows and shows detail on click", async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId("learning-row-l1"));
    expect(screen.getByTestId("learning-detail")).toBeTruthy();
    expect(screen.getByTestId("learning-evidencia").textContent).toBe("PR #12");
  });

  it("passes the project and status filters to the hook", async () => {
    await renderTab();
    fireEvent.change(screen.getByLabelText("Filtrar por projeto"), { target: { value: "noc" } });
    fireEvent.change(screen.getByLabelText("Filtrar por status"), { target: { value: "aceito" } });
    expect(mockUseLearnings).toHaveBeenLastCalledWith("isaia-dev", "noc", "aceito");
  });
});

describe("LearningsTab — review", () => {
  it("member: no review controls", async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId("learning-row-l1"));
    expect(screen.queryByTestId("learning-review-form")).toBeNull();
  });

  it("admin: requires a note before reviewing", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderTab();
    fireEvent.click(screen.getByTestId("learning-row-l1"));
    fireEvent.click(screen.getByTestId("learning-accept"));
    expect(screen.getByText("Informe uma nota para registrar a decisão.")).toBeTruthy();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("admin: accepts with a note", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderTab();
    fireEvent.click(screen.getByTestId("learning-row-l1"));
    fireEvent.change(screen.getByTestId("learning-review-nota"), { target: { value: "ok" } });
    fireEvent.click(screen.getByTestId("learning-accept"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ id: "l1", review: { status: "aceito", nota: "ok" } }));
  });

  it("admin: shows a visible error when the review fails", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    mutateAsync.mockRejectedValueOnce(new Error("falhou"));
    await renderTab();
    fireEvent.click(screen.getByTestId("learning-row-l1"));
    fireEvent.change(screen.getByTestId("learning-review-nota"), { target: { value: "não serve" } });
    fireEvent.click(screen.getByTestId("learning-discard"));
    await waitFor(() => expect(screen.getByText(/Não foi possível salvar a revisão/)).toBeTruthy());
  });
});
