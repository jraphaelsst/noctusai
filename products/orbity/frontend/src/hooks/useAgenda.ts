/**
 * Agenda hooks for Orbity.
 *
 * Mirrors the ERP TanStack Query hook shape (useQuery/useMutation + toast).
 * Hooks are the ONLY place useQuery/useMutation appears — never in page
 * components directly (per engineer-seed protocol).
 *
 * Backend contract: products/orbity/backend/app/schemas/agenda.py
 *   EventType: "meeting" | "call" | "visit" | "other"
 *   GCal sync: POST /api/agenda/events/{id}/sync-gcal
 */
import { useQuery } from '@tanstack/react-query';
import { pageOps, useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types — mirror backend schemas/agenda.py
// ---------------------------------------------------------------------------

export type EventType = 'meeting' | 'call' | 'visit' | 'other';

export interface AgendaEvent {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  event_type: EventType;
  client_id: string | null;
  starts_at: string;
  ends_at: string;
  location: string | null;
  gcal_event_id: string | null;
  assignee_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgendaEventListResponse {
  items: AgendaEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface AgendaFilters {
  from?: string;    // ISO 8601 date
  to?: string;      // ISO 8601 date
  event_type?: EventType;
  client_id?: string;
  assignee_user_id?: string;
  page?: number;
  page_size?: number;
}

export interface AgendaEventCreateData {
  title: string;
  description?: string;
  event_type?: EventType;
  client_id?: string;
  starts_at: string;
  ends_at: string;
  location?: string;
  assignee_user_id?: string;
}

export interface AgendaEventUpdateData {
  title?: string;
  description?: string;
  event_type?: EventType;
  client_id?: string;
  starts_at?: string;
  ends_at?: string;
  location?: string;
  assignee_user_id?: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useAgendaEvents(filters?: AgendaFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['orbity-agenda-events', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = {
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 200,
      };
      if (filters?.from) params['from'] = filters.from;
      if (filters?.to) params['to'] = filters.to;
      if (filters?.event_type) params['event_type'] = filters.event_type;
      if (filters?.client_id) params['client_id'] = filters.client_id;
      if (filters?.assignee_user_id) params['assignee_user_id'] = filters.assignee_user_id;

      const result = await api.get('/api/agenda/events', params);
      return result as AgendaEventListResponse;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useAgendaEvent(id?: string) {
  return useQuery({
    queryKey: ['orbity-agenda-event', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/agenda/events/${id}`);
      return result as AgendaEvent;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

const EVENTS_KEY = ['orbity-agenda-events'];
const eventKey = (id: string) => ['orbity-agenda-event', id];

export function useCreateAgendaEvent() {
  // Cached windows are filtered by range/type/client/assignee (all checkable here) and ordered
  // by starts_at asc: the new event is committed into each window it belongs to, at its sorted
  // place, when that window holds every match (page 1, not full). Anything else converges on the settle.
  return useCacheWriteMutation<AgendaEvent, AgendaEventCreateData>({
    mutationFn: async (data) => {
      const result = await api.post('/api/agenda/events', data);
      return result as AgendaEvent;
    },
    targets: [
      {
        queryKey: EVENTS_KEY,
        match: 'prefix',
        commit: (old: AgendaEventListResponse | undefined, saved, _vars, _ctx, queryKey) => {
          const f = (queryKey?.[1] ?? {}) as AgendaFilters;
          const at = Date.parse(saved.starts_at);
          const inWindow =
            (!f.from || at >= Date.parse(f.from)) &&
            (!f.to || at <= Date.parse(f.to)) &&
            (!f.event_type || f.event_type === saved.event_type) &&
            (!f.client_id || f.client_id === saved.client_id) &&
            (!f.assignee_user_id || f.assignee_user_id === saved.assignee_user_id);
          const holdsEveryMatch = !!old && Array.isArray(old.items) && (old.page ?? 1) === 1 && old.items.length < old.page_size;
          if (!inWindow || !holdsEveryMatch) return old;
          return pageOps.insertSorted(old, saved, (x, y) => Date.parse(x.starts_at) - Date.parse(y.starts_at));
        },
      },
    ],
    onSuccess: () => {
      toast.success('Evento criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar evento', { description: error.message });
    },
  });
}

export function useUpdateAgendaEvent() {
  return useCacheWriteMutation<AgendaEvent, { id: string } & AgendaEventUpdateData>({
    mutationFn: async ({ id, ...data }) => {
      const result = await api.patch(`/api/agenda/events/${id}`, data);
      return result as AgendaEvent;
    },
    targets: ({ id }) => [
      {
        queryKey: EVENTS_KEY,
        match: 'prefix',
        commit: (old, saved) => pageOps.replace(old, id, saved),
      },
      { queryKey: eventKey(id), commit: (_old, saved) => saved },
    ],
    onSuccess: () => {
      toast.success('Evento atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar evento', { description: error.message });
    },
  });
}

export function useDeleteAgendaEvent() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (id) => {
      await api.delete(`/api/agenda/events/${id}`);
      return id;
    },
    targets: (id) => [
      {
        queryKey: EVENTS_KEY,
        match: 'prefix',
        optimistic: (old, vars) => pageOps.remove(old, vars),
      },
      { queryKey: eventKey(id) },
    ],
    onSuccess: () => {
      toast.success('Evento excluído!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir evento', { description: error.message });
    },
  });
}

/**
 * GCal sync — calls POST /api/agenda/events/{id}/sync-gcal.
 * The backend wires through AgendaService.sync_to_gcal() which uses
 * FakeCalendarAdapter by default. Returns the updated event with gcal_event_id.
 * NOC-REMEDIATE[orbity-agenda-gcal]: real adapter requires credential wiring. — 2026-06-03
 */
export function useSyncGcal() {
  return useCacheWriteMutation<AgendaEvent, string>({
    mutationFn: async (eventId) => {
      const result = await api.post(`/api/agenda/events/${eventId}/sync-gcal`, {});
      return result as AgendaEvent;
    },
    targets: (eventId) => [
      {
        queryKey: EVENTS_KEY,
        match: 'prefix',
        commit: (old, saved) => pageOps.replace(old, eventId, saved),
      },
      { queryKey: eventKey(eventId), commit: (_old, saved) => saved },
    ],
    onSuccess: () => {
      toast.success('Sincronização simulada', {
        description: 'Google Calendar não conectado — nada foi enviado à agenda real.',
      });
    },
    onError: (error: Error) => {
      toast.error('Erro ao simular sincronização', { description: error.message });
    },
  });
}
