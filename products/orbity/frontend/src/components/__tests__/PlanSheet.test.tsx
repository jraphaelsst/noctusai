/** PlanSheet — task selection eligibility, delete semantics copy, AI error surface. */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ConfirmProvider } from "@noctusai/lib/components";

const h = vi.hoisted(() => ({
  createTasks: vi.fn(),
  deleteItem: vi.fn(),
  generateError: { current: null as Error | null },
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return { api, useAuthStore: () => ({ user: null }), default: { api } };
});
vi.mock("@/components/ClientSelect", () => ({ ClientSelect: () => null }));

vi.mock("@/hooks/useContentPlans", async (orig) => {
  const real = await orig<typeof import("@/hooks/useContentPlans")>();
  const idle = () => ({ mutate: () => {}, isPending: false });
  return {
    ...real,
    useCreateTasksFromItems: () => ({ mutate: h.createTasks, isPending: false }),
    useDeletePlanItem: () => ({ mutate: h.deleteItem, isPending: false }),
    useUpdatePlan: idle, useReorderPlanItems: idle, usePromoteItemToPost: idle,
    useAppendPlanItems: idle, useUpdatePlanItem: idle,
    useGenerateAIItems: () => ({
      mutate: (_v: unknown, o?: { onError?: () => void }) => o?.onError?.(),
      isPending: false,
      isError: !!h.generateError.current,
      error: h.generateError.current,
    }),
  };
});

import { PlanSheet } from "@/components/content-plans/PlanSheet";
import type { ContentPlan, PlanItem } from "@/hooks/useContentPlans";

const base: PlanItem = {
  id: "i1", org_id: "o", plan_id: "p1", order_position: 0, title: "Reels A", description: null, format: null,
  platform: "instagram", post_date: "2026-11-10", due_date: null, caption: null, reference_notes: null,
  status: "planned", task_id: null, post_id: null, created_at: "", updated_at: "",
};
const plan: ContentPlan = {
  id: "p1", org_id: "o", client_id: null, campaign_id: null, title: "Novembro", month: "2026-11",
  strategy_context: {}, status: "active", creation_mode: "manual", created_at: "", updated_at: "",
  items: [
    base,
    { ...base, id: "i2", title: "Com tarefa", order_position: 1, status: "task_created", task_id: "t1" },
    { ...base, id: "i3", title: "Descartado", order_position: 2, status: "discarded" },
  ],
};

function renderSheet() {
  return render(<ConfirmProvider><PlanSheet plan={plan} onClose={() => {}} /></ConfirmProvider>);
}

beforeEach(() => {
  h.createTasks.mockReset();
  h.deleteItem.mockReset();
  h.generateError.current = null;
});

describe("PlanSheet", () => {
  it("opens in edit mode with an editable title", () => {
    renderSheet();
    expect(screen.getByLabelText("Título do planejamento")).toHaveValue("Novembro");
  });

  it("only items without task and not discarded can be selected for tasks", () => {
    renderSheet();
    expect(screen.getByLabelText("Selecionar Reels A")).toBeEnabled();
    expect(screen.getByLabelText("Selecionar Com tarefa")).toBeDisabled();
    expect(screen.getByLabelText("Selecionar Descartado")).toBeDisabled();
  });

  it("creates tasks for the selected eligible item only", () => {
    renderSheet();
    fireEvent.click(screen.getByLabelText("Selecionar Reels A"));
    fireEvent.click(screen.getByRole("button", { name: /Criar tarefas \(1\)/ }));
    expect(h.createTasks).toHaveBeenCalledWith({ planId: "p1", itemIds: ["i1"] }, expect.any(Object));
  });

  it("deleting an item with a task warns the task is kept, then deletes", async () => {
    renderSheet();
    fireEvent.click(screen.getAllByLabelText("Remover conteúdo")[1]);
    expect(await screen.findByText(/a tarefa já criada continua existindo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(h.deleteItem).toHaveBeenCalledWith({ planId: "p1", itemId: "i2" }));
  });

  it("AI not configured shows the honest message and no preview", () => {
    h.generateError.current = new Error("IA não configurada. Cadastre a chave");
    renderSheet();
    fireEvent.click(screen.getByRole("button", { name: /Gerar com IA/ }));
    fireEvent.click(screen.getByRole("button", { name: "Gerar" }));
    expect(screen.getByRole("alert")).toHaveTextContent("IA não configurada");
    expect(screen.queryByText(/conteúdos gerados/)).not.toBeInTheDocument();
  });
});
