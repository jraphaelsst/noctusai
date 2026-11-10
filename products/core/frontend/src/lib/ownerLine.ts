/**
 * Core Notificações — "Quem recebe os avisos": typed client + react-query hooks for the owner-line recipients
 * (`/api/admin/notifications/recipients`) and the line status (`/api/admin/notifications/owner-line`).
 *
 * The HTTP client arrives through `OwnerLineApiContext` (default: the app's `api`) so tests render the page with a
 * fake client. Every write is a cache write: add appends, PATCH replaces the row, DELETE removes it.
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCacheWriteMutation, listOps } from '@noctusai/lib/cache-writes';
import { isValidPhone } from '@noctusai/lib';
import { api } from './api';

export interface OwnerRecipient {
  id: string;
  numero: string;
  nome: string | null;
  ativo: boolean;
  created_at: string;
}

export interface OwnerRecipientList {
  items: OwnerRecipient[];
}

export interface OwnerLineStatus {
  configurada: boolean;
  instancia: string | null;
}

export interface OwnerLineHttp {
  get<T = any>(path: string): Promise<T>;
  post<T = any>(path: string, body?: unknown): Promise<T>;
  patch<T = any>(path: string, body?: unknown): Promise<T>;
  delete<T = any>(path: string): Promise<T>;
}

const BASE = '/api/admin/notifications';

export function createOwnerLineApi(http: OwnerLineHttp) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  return {
    recipients: () => unwrap<OwnerRecipientList>(http.get(`${BASE}/recipients`)),
    line: () => unwrap<OwnerLineStatus>(http.get(`${BASE}/owner-line`)),
    add: (body: { numero: string; nome?: string }) => unwrap<OwnerRecipient>(http.post(`${BASE}/recipients`, body)),
    patch: (id: string, body: { ativo?: boolean; nome?: string }) =>
      unwrap<OwnerRecipient>(http.patch(`${BASE}/recipients/${encodeURIComponent(id)}`, body)),
    remove: async (id: string) => {
      await http.delete(`${BASE}/recipients/${encodeURIComponent(id)}`);
    },
  };
}

export type OwnerLineApi = ReturnType<typeof createOwnerLineApi>;

const OwnerLineApiContext = createContext<OwnerLineApi>(createOwnerLineApi(api as unknown as OwnerLineHttp));

export function OwnerLineApiProvider({ value, children }: { value: OwnerLineApi; children: ReactNode }) {
  return createElement(OwnerLineApiContext.Provider, { value }, children);
}

export const ownerLineKeys = {
  recipients: ['admin', 'notifications', 'recipients'] as const,
  line: ['admin', 'notifications', 'owner-line'] as const,
};

export function useOwnerRecipients() {
  const a = useContext(OwnerLineApiContext);
  return useQuery({
    queryKey: ownerLineKeys.recipients,
    queryFn: a.recipients,
    placeholderData: (prev) => prev,
  });
}

export function useOwnerLineStatus() {
  const a = useContext(OwnerLineApiContext);
  return useQuery({ queryKey: ownerLineKeys.line, queryFn: a.line, placeholderData: (prev) => prev });
}

/** Server order is created_at ascending; a new row lands last. */
const inEnvelope = (fn: (l: OwnerRecipient[]) => OwnerRecipient[] | undefined) => (old: OwnerRecipientList | undefined) =>
  listOps.within(old, 'items', fn as never) as OwnerRecipientList | undefined;

export function useAddOwnerRecipient() {
  const a = useContext(OwnerLineApiContext);
  return useCacheWriteMutation<OwnerRecipient, { numero: string; nome?: string }>({
    mutationFn: (v) => a.add(v),
    targets: () => [
      {
        queryKey: ownerLineKeys.recipients,
        commit: (old: OwnerRecipientList | undefined, saved: OwnerRecipient) =>
          inEnvelope((l) => listOps.append(l, saved))(old),
      },
    ],
  });
}

export function usePatchOwnerRecipient() {
  const a = useContext(OwnerLineApiContext);
  return useCacheWriteMutation<OwnerRecipient, { id: string; ativo?: boolean; nome?: string }>({
    mutationFn: ({ id, ...body }) => a.patch(id, body),
    targets: (v) => [
      {
        queryKey: ownerLineKeys.recipients,
        optimistic: (old: OwnerRecipientList | undefined) => {
          const { id, ...changes } = v;
          return inEnvelope((l) => listOps.patch(l, id, changes))(old);
        },
        commit: (old: OwnerRecipientList | undefined, saved: OwnerRecipient) =>
          inEnvelope((l) => listOps.replace(l, v.id, saved))(old),
      },
    ],
  });
}

export function useRemoveOwnerRecipient() {
  const a = useContext(OwnerLineApiContext);
  return useCacheWriteMutation<void, { id: string }>({
    mutationFn: (v) => a.remove(v.id),
    targets: (v) => [
      {
        queryKey: ownerLineKeys.recipients,
        optimistic: inEnvelope((l) => listOps.remove(l, v.id)),
        commit: inEnvelope((l) => listOps.remove(l, v.id)),
      },
    ],
  });
}

// ---- validation (client mirror of the contract; the server stays the authority) -------------------------------

export type AddFormErrors = { numero?: string; nome?: string };

export function validateAddRecipient(numero: string, nome: string): AddFormErrors {
  const errors: AddFormErrors = {};
  if (!numero.trim()) errors.numero = 'Informe o número com DDD, por exemplo (11) 99999-9999.';
  else if (!isValidPhone(numero)) errors.numero = 'Número inválido. Use DDD + número, por exemplo (11) 99999-9999.';
  if (nome.trim().length > 80) errors.nome = 'O nome pode ter no máximo 80 caracteres.';
  return errors;
}

/** Map a server refusal to a field error (pt-BR); null = not a field problem (shown as a general alert). */
export function serverAddError(err: unknown): AddFormErrors | null {
  const e = err as { status?: number | null; code?: string | null; message?: string } | null;
  const code = e?.code ?? '';
  if (e?.status === 409 || code === 'numero_duplicado')
    return { numero: 'Este número já está na lista de destinatários.' };
  if (e?.status === 422 || code === 'numero_invalido')
    return { numero: 'Número inválido. Use DDD + número, por exemplo (11) 99999-9999.' };
  return null;
}
