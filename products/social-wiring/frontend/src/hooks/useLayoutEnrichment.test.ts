/**
 * useLayoutEnrichment.test.ts — the role-label-flicker fix.
 *
 * Asserts the enrichment hook shows a neutral "Carregando…" while the
 * authoritative `/api/team` list is still loading — NEVER the stale
 * JWT-cached guess — and resolves to the DB-backed `org_role` exactly
 * once, with no re-flip during a background refetch (`isFetching` alone
 * must not re-trigger the loading label — mirrors the isPending-vs-
 * isFetching rule already applied to ChartCard/StatTile in this product).
 */
import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const mockUseAuthStore = vi.fn();
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: mockUseAuthStore,
}));

const mockUseTeamMembers = vi.fn();
vi.mock("@/hooks/useTeam", () => ({
  useTeamMembers: mockUseTeamMembers,
}));

async function importHook() {
  return import("./useLayoutEnrichment");
}

describe("useSocialWiringLayoutEnrichment", () => {
  it("shows a neutral loading label while /api/team has not resolved yet", async () => {
    mockUseAuthStore.mockReturnValue({ user: { id: "u1" } });
    mockUseTeamMembers.mockReturnValue({ data: undefined, isPending: true });
    const { useSocialWiringLayoutEnrichment } = await importHook();

    const { result } = renderHook(() => useSocialWiringLayoutEnrichment());
    expect(result.current.roleLabel).toBe("Carregando…");
  });

  it("resolves to the DB-backed org_role once the team list loads", async () => {
    mockUseAuthStore.mockReturnValue({ user: { id: "u1" } });
    mockUseTeamMembers.mockReturnValue({
      data: [
        { id: "u1", nome: "Ana", email: "ana@x.com", role: "member", org_role: "admin", created_at: "" },
        { id: "u2", nome: "Beto", email: "beto@x.com", role: "member", org_role: "member", created_at: "" },
      ],
      isPending: false,
    });
    const { useSocialWiringLayoutEnrichment } = await importHook();

    const { result } = renderHook(() => useSocialWiringLayoutEnrichment());
    expect(result.current.roleLabel).toBe("Administrador");
  });

  it("does NOT re-flip to the loading label during a background refetch (isFetching only)", async () => {
    mockUseAuthStore.mockReturnValue({ user: { id: "u1" } });
    mockUseTeamMembers.mockReturnValue({
      data: [{ id: "u1", nome: "Ana", email: "ana@x.com", role: "member", org_role: "owner", created_at: "" }],
      isPending: false,
      isFetching: true,
    });
    const { useSocialWiringLayoutEnrichment } = await importHook();

    const { result } = renderHook(() => useSocialWiringLayoutEnrichment());
    expect(result.current.roleLabel).toBe("Proprietário");
  });

  it("degrades to the pre-existing guess (undefined roleLabel) when the user's own row isn't in the list", async () => {
    mockUseAuthStore.mockReturnValue({ user: { id: "u-not-in-list" } });
    mockUseTeamMembers.mockReturnValue({
      data: [{ id: "u1", nome: "Ana", email: "ana@x.com", role: "member", org_role: "admin", created_at: "" }],
      isPending: false,
    });
    const { useSocialWiringLayoutEnrichment } = await importHook();

    const { result } = renderHook(() => useSocialWiringLayoutEnrichment());
    expect(result.current.roleLabel).toBeUndefined();
  });
});
