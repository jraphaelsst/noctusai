/**
 * useTasks + useRoutines hook smoke tests.
 *
 * Pattern mirrors products/erp-imobiliario/frontend/src/hooks/__tests__/useCorretorHooks.test.ts.
 *
 * Goal: verify each hook calls the correct backend path with the expected
 * params and surfaces the parsed response.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
const mockAuth = { user: { id: 'u1', email: 'u@test.com' } };

vi.mock('@noctusai/seed/infra', () => ({
  api: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
  useAuthStore: () => mockAuth,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useTasks hook smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useTasks fetches /api/tasks with default params', async () => {
    const mockResponse = {
      items: [
        {
          id: 't1',
          org_id: 'org1',
          title: 'Tarefa teste',
          description: null,
          assignee_user_id: null,
          client_id: null,
          status: 'todo',
          priority: 'med',
          due_date: null,
          completed_at: null,
          created_at: '2026-06-01T00:00:00Z',
          updated_at: '2026-06-01T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 200,
    };
    mockGet.mockResolvedValue(mockResponse);

    const { useTasks } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useTasks(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/tasks', { page: 1, page_size: 200 });
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].title).toBe('Tarefa teste');
  });

  it('useTasks passes priority filter', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useTasks } = await import('@/hooks/useTasks');
    renderHook(() => useTasks({ priority: 'high' }), { wrapper: withQueryClient() });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/tasks', {
      page: 1,
      page_size: 200,
      priority: 'high',
    });
  });

  it('useTasks passes status filter', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useTasks } = await import('@/hooks/useTasks');
    renderHook(() => useTasks({ status: 'doing' }), { wrapper: withQueryClient() });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/tasks', {
      page: 1,
      page_size: 200,
      status: 'doing',
    });
  });

  it('useCreateTask POSTs to /api/tasks', async () => {
    const created = {
      id: 't2',
      org_id: 'org1',
      title: 'Nova Tarefa',
      description: null,
      assignee_user_id: null,
      client_id: null,
      status: 'todo',
      priority: 'med',
      due_date: null,
      completed_at: null,
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-01T00:00:00Z',
    };
    mockPost.mockResolvedValue(created);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useCreateTask } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useCreateTask(), { wrapper: withQueryClient() });

    result.current.mutate({ title: 'Nova Tarefa', priority: 'med' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/api/tasks', {
      title: 'Nova Tarefa',
      priority: 'med',
    });
  });

  it('useUpdateTaskStatus PATCHes /api/tasks/{id}/status', async () => {
    const updated = {
      id: 't1',
      org_id: 'org1',
      title: 'T',
      description: null,
      assignee_user_id: null,
      client_id: null,
      status: 'done',
      priority: 'med',
      due_date: null,
      completed_at: '2026-06-01T12:00:00Z',
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-01T12:00:00Z',
    };
    mockPatch.mockResolvedValue(updated);
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useUpdateTaskStatus } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useUpdateTaskStatus(), { wrapper: withQueryClient() });

    result.current.mutate({ id: 't1', status: 'done' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPatch).toHaveBeenCalledWith('/api/tasks/t1/status', { status: 'done' });
  });

  it('useDeleteTask DELETEs /api/tasks/{id}', async () => {
    mockDelete.mockResolvedValue({ ok: true });
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200 });

    const { useDeleteTask } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useDeleteTask(), { wrapper: withQueryClient() });

    result.current.mutate('t1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith('/api/tasks/t1');
  });
});

describe('useRoutines hook smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useRoutines fetches /api/routines with active_only=false by default', async () => {
    const routines = [
      {
        id: 'r1',
        org_id: 'org1',
        title: 'Daily standup',
        description: null,
        cadence: 'daily',
        next_run: '2026-06-03',
        active: true,
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-01T00:00:00Z',
      },
    ];
    mockGet.mockResolvedValue(routines);

    const { useRoutines } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useRoutines(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/api/routines', { active_only: false });
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].title).toBe('Daily standup');
  });

  it('useRoutines passes active_only=true when requested', async () => {
    mockGet.mockResolvedValue([]);

    const { useRoutines } = await import('@/hooks/useTasks');
    renderHook(() => useRoutines(true), { wrapper: withQueryClient() });

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(mockGet).toHaveBeenCalledWith('/api/routines', { active_only: true });
  });

  it('useCreateRoutine POSTs to /api/routines', async () => {
    const created = {
      id: 'r2',
      org_id: 'org1',
      title: 'Weekly review',
      description: null,
      cadence: 'weekly',
      next_run: '2026-06-09',
      active: true,
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-01T00:00:00Z',
    };
    mockPost.mockResolvedValue(created);
    mockGet.mockResolvedValue([]);

    const { useCreateRoutine } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useCreateRoutine(), { wrapper: withQueryClient() });

    result.current.mutate({
      title: 'Weekly review',
      cadence: 'weekly',
      next_run: '2026-06-09',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/api/routines', {
      title: 'Weekly review',
      cadence: 'weekly',
      next_run: '2026-06-09',
    });
  });

  it('useRunDueRoutines POSTs to /api/routines/run-due', async () => {
    mockPost.mockResolvedValue({ spawned: 2, tasks: [] });
    mockGet.mockResolvedValue([]);

    const { useRunDueRoutines } = await import('@/hooks/useTasks');
    const { result } = renderHook(() => useRunDueRoutines(), { wrapper: withQueryClient() });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/api/routines/run-due', {});
  });
});
