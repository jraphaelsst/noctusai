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
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

export function useCreateAgendaEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: AgendaEventCreateData) => {
      const result = await api.post('/api/agenda/events', data);
      return result as AgendaEvent;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-events'] });
      toast.success('Evento criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar evento', { description: error.message });
    },
  });
}

export function useUpdateAgendaEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string } & AgendaEventUpdateData) => {
      const result = await api.patch(`/api/agenda/events/${id}`, data);
      return result as AgendaEvent;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-events'] });
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-event', data.id] });
      toast.success('Evento atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar evento', { description: error.message });
    },
  });
}

export function useDeleteAgendaEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/agenda/events/${id}`);
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-events'] });
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
 * NOC-REMEDIATE[orbity-agenda-gcal]: real adapter requires credential wiring.
 */
export function useSyncGcal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (eventId: string) => {
      const result = await api.post(`/api/agenda/events/${eventId}/sync-gcal`, {});
      return result as AgendaEvent;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-events'] });
      queryClient.invalidateQueries({ queryKey: ['orbity-agenda-event', data.id] });
      toast.success('Evento sincronizado com Google Calendar!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao sincronizar com Google Calendar', { description: error.message });
    },
  });
}
