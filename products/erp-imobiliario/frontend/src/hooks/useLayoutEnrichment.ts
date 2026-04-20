/**
 * ERP Layout Enrichment Hook
 *
 * Provides domain-specific data to the framework's createProductLayout.
 * This is where all ERP-specific layout logic lives:
 * - Profile from erp.profiles table
 * - Roles from erp.user_roles junction table
 * - Admin panel visibility
 * - Theme persistence to DB
 * - Multi-role label display
 */
import { useUserProfile } from "@/hooks/useUserProfile";
import { useUserRoles } from "@/hooks/useUserRoles";
import { useIsAdmin } from "@/hooks/useUserRole";
import { useUpdateProfile } from "@/hooks/useProfiles";
import { useQueryClient } from "@tanstack/react-query";
import { resolveSSOContext, isDevOrOwner } from "@noctusai/lib";
import { useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { LayoutEnrichment } from "@noctusai/seed";
import type { NavGroupWithRoute } from "@noctusai/lib";
import { Users, UserPlus, Shield, CheckCircle2 } from "lucide-react";
import { usePeriodos, useRankings } from "@/hooks/useMetasDomain";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  coordenador: "Coordenador",
  dev: "Desenvolvedor",
  corretor: "Corretor",
};

const getRolesLabel = (roles: string[]) => {
  if (roles.length === 0) return "Corretor";
  return roles.map((r) => ROLE_LABELS[r] || "Corretor").join(", ");
};

const PAINEL_GROUP: NavGroupWithRoute = {
  key: "painel", label: "Painel de Controle", icon: Shield, defaultOpen: true,
  items: [
    { name: "Usuarios", href: "/usuarios", icon: Users, route: "usuarios" },
    { name: "Equipe", href: "/equipe", icon: UserPlus, route: "equipe" },
    { name: "Admin", href: "/admin", icon: Shield, route: "admin" },
    { name: "Log de Acoes", href: "/log-acoes", icon: CheckCircle2, route: "log-acoes" },
  ],
};

export function useERPLayoutEnrichment(): LayoutEnrichment {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const { data: profile, isLoading: isLoadingProfile } = useUserProfile();
  const { data: roles = [], isLoading: isLoadingRoles } = useUserRoles();
  const { isAdmin } = useIsAdmin();
  const updateProfile = useUpdateProfile();

  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isSSOAdmin = ssoCtx.isProductAdmin;
  const isAdminOrDev = isSSOAdmin || roles.includes("admin") || roles.includes("dev");

  // Inline rank badge in the role label so every page's header shows the
  // agent's current Metas rank. Subtle gamification per `KB/CONTEXT/07-GAMIFICATION.md`.
  const { data: periodos = [] } = usePeriodos();
  const openPeriod = periodos.find((p: any) => p.status === "aberto") ?? periodos[0];
  const { data: rankings } = useRankings({
    data_inicio: openPeriod?.data_inicio,
    data_fim: openPeriod?.data_fim,
  });
  const myRank = rankings?.unificado?.find((r) => r.corretor_id === user?.id)?.rank ?? null;

  const effectiveDevRole = isDevOrOwner(ssoCtx.org.role) || roles.includes("dev") || roles.includes("admin")
    ? "dev"
    : ssoCtx.org.role ?? null;

  return {
    userName: profile?.nome,
    userEmail: profile?.email,
    userPhone: profile?.telefone,
    userAvatar: profile?.avatar,
    roleLabel: (() => {
      const base = isSSOAdmin && roles.length === 0 ? "Administrador" : getRolesLabel(roles);
      return myRank ? `${base} · #${myRank}` : base;
    })(),
    extraNavGroups: isAdminOrDev ? [PAINEL_GROUP] : [],
    effectiveDevRole,
    isLoading: isLoadingProfile || isLoadingRoles || !profile,
    canEditEmail: isAdmin,
    initialTheme: profile?.tema as "light" | "dark" | undefined,
    onThemePersist: (newTheme: string) => {
      if (profile?.id) updateProfile.mutate({ id: profile.id, tema: newTheme });
    },
    onUpdateProfile: async (data: { name: string; email: string; phone: string }) => {
      if (!profile?.id) return;
      await updateProfile.mutateAsync({
        id: profile.id,
        nome: data.name,
        ...(isAdmin && { email: data.email }),
        telefone: data.phone,
      });
      queryClient.invalidateQueries({ queryKey: ["user-profile"] });
      toast.success("Perfil atualizado com sucesso!");
    },
    headerUserProps: profile?.id ? { id: profile.id } : undefined,
  };
}
