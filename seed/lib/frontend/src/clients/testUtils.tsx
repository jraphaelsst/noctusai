/** Shared test helpers for the clients organ (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ConfirmProvider } from '../components/confirm/ConfirmProvider';
import { makeRoutedApi } from '../organ-kit/testing';
import type { ClientsApi } from './hooks';
import type { Client, ClientFinance, ClientsConfigData, Schedule, Session } from './types';

export const CONFIG: ClientsConfigData = {
  noun_singular: 'Paciente',
  noun_plural: 'Pacientes',
  statuses: [
    { slug: 'ativo', label: 'Ativo', color: 'success' },
    { slug: 'pausado', label: 'Pausado', color: 'warning' },
    { slug: 'encerrado', label: 'Encerrado', color: 'muted' },
  ],
  session_statuses: [
    { slug: 'agendada', label: 'Agendada', color: 'primary', billable: false },
    { slug: 'realizada', label: 'Realizada', color: 'success', billable: true },
    { slug: 'falta', label: 'Falta', color: 'destructive', billable: true },
    { slug: 'cancelada', label: 'Cancelada', color: 'muted', billable: false },
  ],
  default_session_status: 'agendada',
  default_duration_min: 50,
  default_price_cents: null,
  payment_methods: [
    { slug: 'pix', label: 'Pix' },
    { slug: 'dinheiro', label: 'Dinheiro' },
  ],
  timezone: 'America/Sao_Paulo',
  finance_enabled: true,
};

export function client(over: Partial<Client> = {}): Client {
  return {
    id: 'c1',
    name: 'Ana Souza',
    phone: '+5511994573387',
    email: null,
    doc: null,
    birth_date: null,
    status: 'ativo',
    tags: [],
    notes: null,
    lead_id: null,
    whatsapp_chat_id: null,
    default_price_cents: 20000,
    session_duration_min: 50,
    started_at: '2026-10-01',
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
    summary: { next_session_at: null, last_session_at: null, sessions_done: 0, open_cents: 0, overdue_cents: 0, paid_cents: 0 },
    ...over,
  };
}

export function session(over: Partial<Session> = {}): Session {
  return {
    id: 's1',
    client_id: 'c1',
    client_name: 'Ana Souza',
    schedule_id: null,
    starts_at: '2026-11-03T14:00:00-03:00',
    duration_min: 50,
    status: 'agendada',
    price_cents: null,
    waive_charge: false,
    notes: null,
    entry_id: null,
    payment_status: 'none',
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
    ...over,
  };
}

export function schedule(over: Partial<Schedule> = {}): Schedule {
  return {
    id: 'h1',
    client_id: 'c1',
    weekday: 1,
    time: '14:00',
    duration_min: 50,
    price_cents: null,
    starts_on: '2026-10-01',
    ends_on: null,
    active: true,
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
    ...over,
  };
}

export function finance(over: Partial<ClientFinance> = {}): ClientFinance {
  return { open_cents: 0, overdue_cents: 0, paid_cents: 0, entries: [], ...over };
}

export const env = <T,>(data: T) => ({ data });

export function makeApi(routes: Record<string, unknown> = {}) {
  return makeRoutedApi<ClientsApi>({ 'GET /api/clients/config': env(CONFIG), 'GET /api/clients/tags': env([]), ...routes });
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(qc: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <ConfirmProvider>{children}</ConfirmProvider>
      </QueryClientProvider>
    );
  };
}

export function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
