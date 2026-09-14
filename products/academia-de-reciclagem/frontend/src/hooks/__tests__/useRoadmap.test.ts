/**
 * useRoadmap hook tests — contract §B.4.
 *
 * Verifies phases/tasks GETs, task create, `PATCH /api/tasks/{codigo}` (the
 * mutation a kanban card move fires — `Roadmap.tsx`'s `onMove` calls
 * `useUpdateTask().mutate`), and `GET /api/session-prep`.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: mockPatch, delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const PHASE = {
  codigo: "P1",
  titulo: "Fundação",
  objetivo: "Migrar o conhecimento",
  concluida_quando: "Todas as entidades importadas",
  estado: "em-andamento" as const,
  ordem: 1,
};

const TASK = {
  codigo: "T-005",
  titulo: "Construir o parser do bundle",
  fase: "P1",
  detalhe: null,
  estado: "pendente" as const,
  bloqueada_por: null,
};

beforeEach(() => vi.clearAllMocks());

describe("usePhases", () => {
  it("queries GET /api/roadmap", async () => {
    mockGet.mockResolvedValue({ items: [PHASE], total: 1 });
    const { usePhases } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => usePhases(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/roadmap");
    expect(result.current.data?.items[0].codigo).toBe("P1");
  });
});

describe("useTasks", () => {
  it("queries GET /api/tasks with fase/estado params", async () => {
    mockGet.mockResolvedValue({ items: [TASK], total: 1 });
    const { useTasks } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useTasks({ fase: "P1", estado: "pendente" }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/tasks", { fase: "P1", estado: "pendente" });
  });
});

describe("useCreateTask", () => {
  it("posts to /api/tasks (422 surface when fase is unknown is a backend concern, not asserted here)", async () => {
    mockPost.mockResolvedValue(TASK);
    const { useCreateTask } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useCreateTask(), { wrapper: wrapper() });

    result.current.mutate({ titulo: TASK.titulo, fase: "P1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/tasks", { titulo: TASK.titulo, fase: "P1" });
  });
});

describe("useUpdateTask — the kanban-move mutation", () => {
  it("PATCHes /api/tasks/{codigo} with the new estado when a card moves column", async () => {
    mockPatch.mockResolvedValue({ ...TASK, estado: "em-andamento" });
    const { useUpdateTask } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useUpdateTask(), { wrapper: wrapper() });

    // Mirrors Roadmap.tsx's KanbanBoard onMove: (codigo, fromStage, toStage) =>
    // updateTask.mutate({ codigo, changes: { estado: toStage } })
    result.current.mutate({ codigo: "T-005", changes: { estado: "em-andamento" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith("/api/tasks/T-005", { estado: "em-andamento" });
    expect(result.current.data?.estado).toBe("em-andamento");
  });
});

describe("useSessionPrep", () => {
  it("queries GET /api/session-prep", async () => {
    mockGet.mockResolvedValue({
      fase_atual: PHASE,
      proximas: [TASK],
      bloqueadas: [],
      perguntas_abertas: 2,
      perguntas_bloqueantes: [],
    });
    const { useSessionPrep } = await import("@/hooks/useRoadmap");
    const { result } = renderHook(() => useSessionPrep(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/session-prep");
    expect(result.current.data?.perguntas_abertas).toBe(2);
    expect(result.current.data?.fase_atual?.codigo).toBe("P1");
  });
});
