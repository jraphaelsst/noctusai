/** Shared test helpers for the leads organ (not exported from the barrel). */
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ConfirmProvider } from '../components/confirm/ConfirmProvider';
import { makeRoutedApi } from '../organ-kit/testing';
import type { LeadsApi } from './hooks';
import type { Lead, LeadColumn, LeadsConfigData } from './types';

export const CONFIG: LeadsConfigData = {
  stages: [
    { slug: 'lead', label: 'Lead', color: 'destructive', tag: 'Lead' },
    { slug: 'atendimento', label: 'Atendimento', color: 'warning', tag: 'Em atendimento' },
    { slug: 'fechado', label: 'Fechado', color: 'success', tag: null },
  ],
  origins: [
    { slug: 'whatsapp', label: 'WhatsApp' },
    { slug: 'instagram', label: 'Instagram' },
    { slug: 'outro', label: 'Outro' },
  ],
  whatsapp_origin: 'whatsapp',
  default_origin: 'outro',
};

export function lead(over: Partial<Lead> = {}): Lead {
  return {
    id: 'l1',
    name: 'Ana Souza',
    phone: '+5511994573387',
    email: null,
    origin: 'whatsapp',
    stage: 'lead',
    position: 0,
    notes: null,
    tags: [],
    whatsapp_connection_id: 'c1',
    whatsapp_chat_id: '5511994573387@c.us',
    first_contact_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
    last_message_at: null,
    last_message_preview: 'Oi, queria marcar uma conversa',
    ...over,
  };
}

export function board(...byStage: Lead[][]): LeadColumn[] {
  return CONFIG.stages.map((s, i) => ({
    etapa: s.slug,
    stage: s,
    total: (byStage[i] ?? []).length,
    exibidos: (byStage[i] ?? []).length,
    cards: byStage[i] ?? [],
  }));
}

export const env = <T,>(data: T) => ({ data });

export function makeApi(routes: Record<string, unknown> = {}) {
  return makeRoutedApi<LeadsApi>({ 'GET /api/leads/config': env(CONFIG), ...routes });
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function wrapperFor(client: QueryClient = makeClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>
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
