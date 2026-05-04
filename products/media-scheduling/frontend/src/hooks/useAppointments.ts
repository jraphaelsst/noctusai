/**
 * useAppointments — TanStack Query list/filter hooks for media_scheduling.appointments.
 *
 * Read-mostly admin surface for the scheduled real-estate-media appointments.
 *
 * TODO Phase 3 — confirm endpoint path (`/api/appointments`).
 */
import { useQuery } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";

export type AppointmentStatus =
  | "pending"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "cancelled";

export interface Appointment {
  id: string;
  starts_at: string; // ISO datetime — start of window
  ends_at: string; // ISO datetime — end of window
  property_id: string;
  property_label?: string | null;
  condominium_id: string;
  condominium_label?: string | null;
  service_type_id: string;
  service_type_label?: string | null;
  crew_assignee_id?: string | null;
  crew_assignee_label?: string | null;
  status: AppointmentStatus;
  created_at: string;
  updated_at: string;
}

export interface AppointmentFilters {
  /** ISO date YYYY-MM-DD inclusive */
  startDate?: string;
  /** ISO date YYYY-MM-DD inclusive */
  endDate?: string;
  status?: AppointmentStatus | "";
  condominiumId?: string;
}

const BASE = "/api/appointments"; // TODO Phase 3 — confirm endpoint path

export function useAppointments(filters?: AppointmentFilters) {
  const { user } = useAuthStore();
  const params = new URLSearchParams();
  if (filters?.startDate) params.set("start_date", filters.startDate);
  if (filters?.endDate) params.set("end_date", filters.endDate);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.condominiumId) params.set("condominium_id", filters.condominiumId);
  const qs = params.toString();

  return useQuery<{ data: Appointment[]; total?: number }>({
    queryKey: ["appointments", filters ?? {}],
    queryFn: () => api.get(qs ? `${BASE}?${qs}` : BASE),
    enabled: !!user,
  });
}

export function useAppointment(id: string) {
  const { user } = useAuthStore();
  return useQuery<Appointment>({
    queryKey: ["appointment", id],
    queryFn: () => api.get(`${BASE}/${id}`),
    enabled: !!user && !!id,
  });
}

/**
 * Convenience: fetch the condominium dropdown options for the filter bar.
 *
 * TODO Phase 3 — confirm endpoint path (`/api/condominiums`).
 */
export interface CondominiumOption {
  id: string;
  name: string;
}

export function useCondominiumOptions() {
  const { user } = useAuthStore();
  return useQuery<{ data: CondominiumOption[] }>({
    queryKey: ["condominiums"],
    queryFn: () => api.get("/api/condominiums"),
    enabled: !!user,
  });
}
