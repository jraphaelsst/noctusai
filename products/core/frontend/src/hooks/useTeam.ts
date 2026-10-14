/**
 * Team admin data hooks (core `/team`) — multi-org S5 (roadmap multi-org-membership-2026-10,
 * § "S4b API contract").
 *
 * Every team call is scoped by `?org_id=`: the viewer manages their profile org as before, and —
 * owner D2/D3 — any org they are an ACTIVE owner/admin of (`manageable_orgs`), or ANY org when
 * they are platform staff (`manage_any_org`). The server re-checks every call; this is UX.
 *
 * Org-keyed lists deliberately carry NO `placeholderData`: they are authorization-scoped per
 * org, and keeping org A's members on screen while org B loads would label A's people as B's.
 * The page shows a skeleton for a fresh org instead (`isPending && !data`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { MeAccess, ManageableOrg } from '@noctusai/lib';

import { api } from '../lib/api';

export interface TeamMember {
  id: string;
  nome: string;
  email: string;
  org_role: string;
  created_at: string;
}

export interface TeamInvitation {
  id: string;
  email: string;
  role: string;
  status: string;
  invited_by: string;
  expires_at: string;
  created_at: string;
}

export interface TeamRole {
  id: string;
  name: string;
  slug: string;
  permissions: string[];
  is_system: boolean;
}

export interface OrgRow { id: string; nome: string }

export interface MemberProductAccess {
  product_id: string;
  slug: string;
  nome: string;
  blocked: boolean;
  blocked_at: string | null;
  blocked_by: string | null;
}

export type MoveMode = 'transfer' | 'add';

export interface MoveMemberInput {
  user_id: string;
  source_org_id: string;
  target_org_id: string;
  role: string;
  mode: MoveMode;
}

export interface MoveMemberResult {
  user_id: string;
  source_org_id: string;
  target_org_id: string;
  org_role: string;
  mode: MoveMode;
  previous_org_role: string | null;
  source_ended: boolean;
  profile_moved: boolean;
  reactivated: boolean;
  selections_ended: number;
}

/** An org the viewer may open on the team page, with THEIR role in it for the manage rules. */
export interface TeamScopeOrg {
  id: string;
  nome: string;
  /** `owner`/`admin` = may move members + manage product access there; `null` = plain team page. */
  actorRole: 'owner' | 'admin' | null;
}

export const teamKeys = {
  access: ['core', 'team', 'me-access'] as const,
  allOrgs: ['core', 'team', 'all-orgs'] as const,
  roles: ['core', 'team', 'roles'] as const,
  members: (orgId: string) => ['core', 'team', 'members', orgId] as const,
  invitations: (orgId: string) => ['core', 'team', 'invitations', orgId] as const,
  productAccess: (orgId: string, userId: string) => ['core', 'team', 'product-access', orgId, userId] as const,
};

const qs = (orgId: string) => `?org_id=${encodeURIComponent(orgId)}`;

/** `GET /api/me/access` — `manage_any_org` / `manageable_orgs` / `platform_role`. */
export function useTeamAccess() {
  return useQuery<MeAccess>({
    queryKey: teamKeys.access,
    queryFn: () => api.get<MeAccess>('/api/me/access'),
    staleTime: 60_000,
    retry: false,
  });
}

/** Every org (platform staff only — the org list a staff viewer may manage). */
export function useAllOrgs(enabled: boolean) {
  return useQuery<OrgRow[]>({
    queryKey: teamKeys.allOrgs,
    queryFn: async () => (await api.get<{ data: OrgRow[] }>('/api/organizations')).data ?? [],
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useTeamRoles() {
  return useQuery<TeamRole[]>({
    queryKey: teamKeys.roles,
    queryFn: async () => (await api.get<{ data: TeamRole[] }>('/api/roles')).data ?? [],
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useTeamMembers(orgId: string | null) {
  return useQuery<TeamMember[]>({
    queryKey: teamKeys.members(orgId ?? ''),
    queryFn: async () => (await api.get<{ data: TeamMember[] }>(`/api/team${qs(orgId!)}`)).data ?? [],
    enabled: !!orgId,
    retry: false,
  });
}

export function useTeamInvitations(orgId: string | null) {
  return useQuery<TeamInvitation[]>({
    queryKey: teamKeys.invitations(orgId ?? ''),
    queryFn: async () =>
      (await api.get<{ data: TeamInvitation[] }>(`/api/team/invitations${qs(orgId!)}`)).data ?? [],
    enabled: !!orgId,
    retry: false,
  });
}

function useInvalidateTeam() {
  const qc = useQueryClient();
  return (orgId: string) => Promise.all([
    qc.invalidateQueries({ queryKey: teamKeys.members(orgId) }),
    qc.invalidateQueries({ queryKey: teamKeys.invitations(orgId) }),
  ]);
}

export function useInviteMember(orgId: string | null) {
  const invalidate = useInvalidateTeam();
  return useMutation({
    mutationFn: (body: { email: string; role: string }) => api.post(`/api/team/invite${qs(orgId!)}`, body),
    onSuccess: () => invalidate(orgId!),
  });
}

/** `DELETE /api/team/{user_id}` → `data` (S5b): what happened to the removed person's profile. */
export interface RemoveMemberResult {
  removed: true;
  /** Org the profile now points at; `null` = this org was not their profile org (nothing moved). */
  profile_moved_to: string | null;
  /** Set only when a personal org was created for a sole-org member (D4). */
  personal_org_id: string | null;
}

export function useRemoveMember(orgId: string | null) {
  const invalidate = useInvalidateTeam();
  return useMutation({
    mutationFn: async (userId: string) =>
      (await api.delete<{ data: RemoveMemberResult }>(`/api/team/${userId}${qs(orgId!)}`)).data,
    onSuccess: () => invalidate(orgId!),
  });
}

export function useChangeMemberRole(orgId: string | null) {
  const invalidate = useInvalidateTeam();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch(`/api/team/${userId}/role${qs(orgId!)}`, { role }),
    onSuccess: () => invalidate(orgId!),
  });
}

export function useCancelInvitation(orgId: string | null) {
  const invalidate = useInvalidateTeam();
  return useMutation({
    mutationFn: (invitationId: string) => api.delete(`/api/team/invitations/${invitationId}${qs(orgId!)}`),
    onSuccess: () => invalidate(orgId!),
  });
}

/** `POST /api/team/move` (D3) — refreshes BOTH orgs' lists. */
export function useMoveMember() {
  const invalidate = useInvalidateTeam();
  return useMutation({
    mutationFn: async (body: MoveMemberInput) =>
      (await api.post<{ data: MoveMemberResult }>('/api/team/move', body)).data,
    onSuccess: (_data, body) => Promise.all([invalidate(body.source_org_id), invalidate(body.target_org_id)]),
  });
}

/** `GET /api/team/{user_id}/product-access?org_id=` (D5). */
export function useMemberProductAccess(orgId: string | null, userId: string | null) {
  return useQuery<MemberProductAccess[]>({
    queryKey: teamKeys.productAccess(orgId ?? '', userId ?? ''),
    queryFn: async () => (await api.get<{ data: { products: MemberProductAccess[] } }>(
      `/api/team/${userId}/product-access${qs(orgId!)}`,
    )).data?.products ?? [],
    enabled: !!orgId && !!userId,
    retry: false,
  });
}

/** `PUT /api/team/{user_id}/product-access/{slug}?org_id=` (D5, idempotent). */
export function useSetMemberProductAccess(orgId: string | null, userId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, blocked }: { slug: string; blocked: boolean }) =>
      api.put(`/api/team/${userId}/product-access/${encodeURIComponent(slug)}${qs(orgId!)}`, { blocked }),
    onSuccess: () => qc.invalidateQueries({ queryKey: teamKeys.productAccess(orgId ?? '', userId ?? '') }),
  });
}

/**
 * The orgs the viewer may open on the team page: their profile org first (always — the team
 * page they had before), then every org they manage. Platform staff (`manage_any_org`) manage
 * every org and count as `owner` there (D3 role cap); a member's role is their membership role.
 */
export function teamScopeOrgs(
  access: MeAccess | undefined,
  allOrgs: OrgRow[] | undefined,
  profileOrg: OrgRow | null,
): TeamScopeOrg[] {
  const sel = access?.org_selection;
  const staff = sel?.manage_any_org === true;
  const managed: TeamScopeOrg[] = staff
    ? (allOrgs ?? []).map((o) => ({ id: o.id, nome: o.nome, actorRole: 'owner' as const }))
    : (sel?.manageable_orgs ?? []).map((o: ManageableOrg) => ({
      id: o.id,
      nome: o.nome ?? 'Organização sem nome',
      actorRole: o.org_role === 'owner' ? 'owner' as const : 'admin' as const,
    }));
  const byName = (a: TeamScopeOrg, b: TeamScopeOrg) => a.nome.localeCompare(b.nome, 'pt-BR');
  if (!profileOrg) return managed.sort(byName);
  const own = managed.find((o) => o.id === profileOrg.id)
    ?? { id: profileOrg.id, nome: profileOrg.nome, actorRole: null };
  return [own, ...managed.filter((o) => o.id !== profileOrg.id).sort(byName)];
}
