/** Shared test helpers for the assignment organ (not exported from the barrel). */
import * as React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { AssignmentApi } from './hooks';
import type { AssignmentEvent, AssignmentRule, AssignmentSettings, AssignmentTeam, AssignmentTeamMember, AssignmentWorkloadRow } from './types';

export function makeApi() {
  return { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } as unknown as {
    [K in keyof AssignmentApi]: ReturnType<typeof vi.fn>;
  } & AssignmentApi;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

export const T1 = 't-1';
export const T2 = 't-2';
export const ANA = 'u-ana';
export const BRUNO = 'u-bruno';
export const CARLA = 'u-carla';

export const member = (over: Partial<AssignmentTeamMember> = {}): AssignmentTeamMember => ({
  user_id: ANA, name: 'Ana', in_org: true, active: true, position: 0, capacity: null, ooo_from: null, ooo_until: null, open_count: 0,
  unavailable_reason: null, ...over,
});

export const team = (over: Partial<AssignmentTeam> = {}): AssignmentTeam => ({
  id: T1, name: 'Vendas', auto: true, org_unit_id: null, members: [member(), member({ user_id: BRUNO, name: 'Bruno', position: 1 })], ...over,
});

export const settings = (over: Partial<AssignmentSettings> = {}): AssignmentSettings => ({
  strategy: 'round_robin', default_team_id: null, keep_last: true, builtin: ['round_robin', 'by_team', 'by_source', 'by_unit', 'manual'], custom: [], ...over,
});

export const rule = (over: Partial<AssignmentRule> = {}): AssignmentRule => ({
  id: 'r-1', org_id: 'o', kind: 'source', match_value: 'meta_ads', team_id: T1, created_at: '', updated_at: '', ...over,
});

export const person = (over: Partial<AssignmentWorkloadRow> = {}): AssignmentWorkloadRow => ({
  user_id: ANA, name: 'Ana', open_count: 2, teams: [T1], available: true, unavailable_reasons: [], ...over,
});

export const event = (over: Partial<AssignmentEvent> = {}): AssignmentEvent => ({
  id: 'e-1', org_id: 'o', subject_kind: 'card', subject_id: 'c-1', event: 'assigned', from_user_id: null, to_user_id: ANA, team_id: T1,
  org_unit_id: null, strategy: 'round_robin', criterion: 'round_robin', actor_id: null, note: null, created_at: '2026-11-10T12:00:00Z', ...over,
});

export const env = <T,>(data: T) => ({ data });

/** Route `api.get` by path so several hooks in one organ each get their payload. */
export function routeGet(api: ReturnType<typeof makeApi>, routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.entries(routes).find(([p]) => path.endsWith(p));
    return hit ? Promise.resolve(hit[1]) : Promise.reject(new Error(`unrouted GET ${path}`));
  });
}

export const ROUTES = {
  '/settings': env(settings()),
  '/teams': env([team()]),
  '/rules': env([rule()]),
  '/workload': env([person(), person({ user_id: BRUNO, name: 'Bruno', open_count: 0 }), person({ user_id: CARLA, name: 'Carla', open_count: 0, teams: [] })]),
  '/events': env([event()]),
};
