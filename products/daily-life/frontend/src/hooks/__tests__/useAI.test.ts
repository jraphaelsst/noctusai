/**
 * useAI hook tests — Daily Life AI features (ai-expansion Phase 11 D6 / Phase 13 D1 / Phase 16 D4).
 *
 * Mirrors the canonical pattern from products/erp-imobiliario/frontend/src/hooks/__tests__/useAI.test.ts.
 * Stubs `api.get` and `api.post`, asserts URLs + payloads + parsed shapes.
 *
 * Closes the G2 backlog deferred during ai-expansion Tier 1.5 for Daily Life.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('@noctusai/seed/infra', () => ({
  api: { get: mockGet, post: mockPost },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));


function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}


describe('Daily Life useAI hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useDailyBrief gets /api/ai/daily-brief and returns brief shape', async () => {
    mockGet.mockResolvedValue({
      data: {
        chip: '3 tarefas hoje',
        summary: 'Você tem 3 tarefas pendentes para hoje. Bom trabalho ontem!',
        tasks_today: 3,
        events_today: 1,
        habits_pending: 2,
        yesterday_completed: 5,
        prompt_version: 'dl-daily-brief@v1',
      },
    });

    const { useDailyBrief } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useDailyBrief(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGet).toHaveBeenCalledWith('/api/ai/daily-brief');
    expect(result.current.data?.chip).toBe('3 tarefas hoje');
    expect(result.current.data?.tasks_today).toBe(3);
  });

  it('useDailyBrief skips fetch when enabled is false', async () => {
    const { useDailyBrief } = await import('@/hooks/useAI');
    renderHook(() => useDailyBrief({ enabled: false }), { wrapper: withQueryClient() });

    // Allow react-query to settle without firing the queryFn.
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(mockGet).not.toHaveBeenCalled();
  });

  it('useWeeklyReview gets /api/ai/weekly-review with periodDays and returns response', async () => {
    mockGet.mockResolvedValue({
      data: {
        subject: 'Revisão semanal',
        html: '<p>Resumo</p>',
        text: 'Resumo',
        summary: {
          tasks_completed: 12,
          tasks_pending: 3,
          tasks_cancelled: 1,
          habit_streaks: [['exercícios', 5]],
          notas_count: 4,
          focus_minutes: 180,
          narrative: 'Boa semana.',
          period_label: '21–27 abr',
        },
      },
    });

    const { useWeeklyReview } = await import('@/hooks/useAI');
    const { result } = renderHook(() => useWeeklyReview(7), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGet).toHaveBeenCalledWith('/api/ai/weekly-review?period_days=7');
    expect(result.current.data?.summary.tasks_completed).toBe(12);
    expect(result.current.data?.summary.habit_streaks).toEqual([['exercícios', 5]]);
  });

  it('useExtractTasksFromNote posts to /api/notes/{id}/extract-tasks and returns task list', async () => {
    mockPost.mockResolvedValue({
      data: {
        tasks: [
          { title: 'Comprar leite', due_hint: 'hoje' },
          { title: 'Ligar para João' },
        ],
      },
    });

    const { useExtractTasksFromNote } = await import('@/hooks/useNotas');
    const { result } = renderHook(() => useExtractTasksFromNote(), { wrapper: withQueryClient() });

    result.current.mutate({ note_id: 'note-42' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockPost).toHaveBeenCalledWith('/api/notes/note-42/extract-tasks');
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].title).toBe('Comprar leite');
  });

  it('useExtractTasksFromNote returns [] when response has no tasks', async () => {
    mockPost.mockResolvedValue({ data: {} });

    const { useExtractTasksFromNote } = await import('@/hooks/useNotas');
    const { result } = renderHook(() => useExtractTasksFromNote(), { wrapper: withQueryClient() });

    result.current.mutate({ note_id: 'note-1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
  });
});
