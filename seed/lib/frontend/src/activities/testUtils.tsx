/** Shared test helpers for the activities organ (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { makeRoutedApi } from '../organ-kit/testing';
import type { ActivitiesApi } from './hooks';
import type { Activity, ActivityType } from './types';

export const ENTITY = 'entity-1';
export const OTHER_ENTITY = 'entity-2';

export const type = (over: Partial<ActivityType> = {}): ActivityType => ({
  org_id: 'o', slug: 'tarefa', label: 'Tarefa', kind: 'task', position: 0, active: true, ...over,
});

export const activity = (over: Partial<Activity> = {}): Activity => ({
  id: 'a1', org_id: 'o', entity_kind: 'lead', entity_id: ENTITY, type_slug: 'tarefa', kind: 'task', title: 'Ligar para o cliente',
  notes: null, due_at: null, assignee_id: null, org_unit_id: null, done_at: null, done_by: null, outcome: null, cancelled_at: null,
  created_by: null, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:00:00Z', overdue: false, ...over,
});

export const page = <T,>(rows: T[]) => ({ data: rows, pagination: { page: 1, page_size: 50, total: rows.length } });

export const makeApi = (routes: Record<string, unknown> = {}) => makeRoutedApi<ActivitiesApi>(routes);

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}
