/**
 * Scheduling hooks — `/api/scheduling/*` (the absorbed real-estate
 * scheduling domain, Wave 2.3).
 *
 * The reference-data CRUD (condomínios / imóveis / serviços / equipe) is
 * NOT wrapped here: those four surfaces are driven by the canonical
 * `<ResourceManager/>` organ, which owns its own fetching. What lives here
 * is everything ResourceManager cannot express — the read-only agenda
 * lists, the pending-identity resolve, and the propose tool — plus the
 * lookup queries the agenda needs to render ids as names.
 *
 * Every list endpoint returns a BARE ARRAY (no envelope) — see
 * `app/modules/scheduling/router.py`, `response_model=list[...]`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

// ─── Types (mirror app/modules/scheduling/schemas.py) ────────────────────────

export type UserRole = "real_estate_agent" | "media_crew" | "admin";

export type AppointmentStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "no_show"
  | "rescheduled";

export type AppointmentRequestStatus =
  | "collecting_details"
  | "pending_confirmation"
  | "confirmed"
  | "cancelled"
  | "expired";

export type PendingChatStatus = "pending" | "resolved" | "rejected";

export interface SchedulingUser {
  id: string;
  org_id: string;
  auth_user_id: string | null;
  name: string;
  role: UserRole;
  phone_number: string;
  email: string | null;
  linked_identity: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Condominium {
  id: string;
  org_id: string;
  name: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SchedulingProperty {
  id: string;
  org_id: string;
  condominium_id: string;
  code: string;
  unit: string | null;
  address_notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SchedulingService {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  default_duration_minutes: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Appointment {
  id: string;
  org_id: string;
  appointment_request_id: string | null;
  google_calendar_event_id: string | null;
  property_id: string;
  condominium_id: string;
  media_crew_user_id: string | null;
  route_group_id: string | null;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  created_at: string;
  updated_at: string;
}

export interface AppointmentRequest {
  id: string;
  org_id: string;
  requester_user_id: string;
  property_id: string | null;
  condominium_id: string | null;
  requested_date: string | null;
  requested_time_window: string | null;
  status: AppointmentRequestStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PendingChatIdentity {
  id: string;
  org_id: string;
  chat_id: string;
  push_name: string | null;
  phone_hint: string | null;
  status: PendingChatStatus;
  captured_at: string;
  resolved_at: string | null;
  resolved_to_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposedSlot {
  start_at: string;
  end_at: string;
  duration_minutes: number;
  score: number;
}

export interface ProposeResponse {
  property_code: string;
  slots: ProposedSlot[];
}

export interface ProposeInput {
  property_code: string;
  requested_date: string;
  time_window: "morning" | "afternoon" | "any";
}

// ─── Query keys ──────────────────────────────────────────────────────────────

const BASE = "/api/scheduling";
const FAMILY = ["sw", "scheduling"] as const;

export const schedulingKeys = {
  appointments: (status?: string) =>
    [...FAMILY, "appointments", status ?? "all"] as const,
  requests: () => [...FAMILY, "appointment-requests"] as const,
  pendingIdentities: () => [...FAMILY, "pending-chat-identities"] as const,
  condominiums: () => [...FAMILY, "condominiums"] as const,
  properties: () => [...FAMILY, "properties"] as const,
  services: () => [...FAMILY, "services"] as const,
  users: () => [...FAMILY, "users"] as const,
};

// ─── Lookups (the agenda renders ids as names) ───────────────────────────────

export function useSchedulingCondominiums() {
  return useQuery({
    queryKey: schedulingKeys.condominiums(),
    queryFn: async () =>
      (await api.get<Condominium[]>(`${BASE}/condominiums`)) ?? [],
  });
}

export function useSchedulingProperties() {
  return useQuery({
    queryKey: schedulingKeys.properties(),
    queryFn: async () =>
      (await api.get<SchedulingProperty[]>(`${BASE}/properties`)) ?? [],
  });
}

export function useSchedulingServices() {
  return useQuery({
    queryKey: schedulingKeys.services(),
    queryFn: async () =>
      (await api.get<SchedulingService[]>(`${BASE}/services`)) ?? [],
  });
}

export function useSchedulingUsers() {
  return useQuery({
    queryKey: schedulingKeys.users(),
    queryFn: async () =>
      (await api.get<SchedulingUser[]>(`${BASE}/users`)) ?? [],
  });
}

// ─── Agenda (read-only) ──────────────────────────────────────────────────────

export function useAppointments(status?: AppointmentStatus | "") {
  const qs = status ? `?appointment_status=${encodeURIComponent(status)}` : "";
  return useQuery({
    queryKey: schedulingKeys.appointments(status || undefined),
    queryFn: async () =>
      (await api.get<Appointment[]>(`${BASE}/appointments${qs}`)) ?? [],
  });
}

export function useAppointmentRequests() {
  return useQuery({
    queryKey: schedulingKeys.requests(),
    queryFn: async () =>
      (await api.get<AppointmentRequest[]>(`${BASE}/appointment-requests`)) ?? [],
  });
}

// ─── Pending chat identities (read + resolve) ────────────────────────────────

export function usePendingChatIdentities() {
  return useQuery({
    queryKey: schedulingKeys.pendingIdentities(),
    queryFn: async () =>
      (await api.get<PendingChatIdentity[]>(`${BASE}/pending-chat-identities`)) ??
      [],
  });
}

export function useResolvePendingChatIdentity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      resolvedToUserId,
    }: {
      id: string;
      status: PendingChatStatus;
      resolvedToUserId?: string | null;
    }) =>
      api.patch<PendingChatIdentity>(
        `${BASE}/pending-chat-identities/${encodeURIComponent(id)}`,
        {
          status,
          resolved_to_user_id: resolvedToUserId ?? null,
        },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulingKeys.pendingIdentities() });
    },
  });
}

// ─── Propose (read-only slot generation; no DB write) ────────────────────────

export function useProposeSlots() {
  return useMutation({
    mutationFn: (body: ProposeInput) =>
      api.post<ProposeResponse>(`${BASE}/propose`, body),
  });
}
