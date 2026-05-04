/**
 * useAuthorizedUsers — TanStack Query CRUD hooks for media_scheduling.authorized_users.
 *
 * These are the WhatsApp-authorized phone numbers + names (NOT platform SSO users —
 * separate concept per PROJECT.md §5).
 *
 * TODO Phase 3 — confirm endpoint path (`/api/authorized-users`).
 * Until backend is wired the queries will surface real API errors via toast in pages.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";

export interface AuthorizedUser {
  id: string;
  phone_number: string;
  name: string;
  is_active: boolean;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

const BASE = "/api/authorized-users"; // TODO Phase 3 — confirm endpoint path

export function useAuthorizedUsers() {
  const { user } = useAuthStore();
  return useQuery<{ data: AuthorizedUser[] }>({
    queryKey: ["authorized-users"],
    queryFn: () => api.get(BASE),
    enabled: !!user,
  });
}

export function useAuthorizedUser(id: string) {
  const { user } = useAuthStore();
  return useQuery<AuthorizedUser>({
    queryKey: ["authorized-user", id],
    queryFn: () => api.get(`${BASE}/${id}`),
    enabled: !!user && !!id,
  });
}

export function useCreateAuthorizedUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<AuthorizedUser>) => api.post(BASE, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["authorized-users"] }),
  });
}

export function useUpdateAuthorizedUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<AuthorizedUser>) =>
      api.patch(`${BASE}/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["authorized-users"] }),
  });
}

export function useDeleteAuthorizedUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["authorized-users"] }),
  });
}
