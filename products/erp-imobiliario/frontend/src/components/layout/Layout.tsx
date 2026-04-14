/**
 * ERP Imobiliário — Unified Layout
 *
 * Follows THE NoctusAI product layout pattern:
 * - Single Layout.tsx per product
 * - Nav data defined as static constants (filtered by status_pagina for feature flags)
 * - SharedHeader + SharedSidebar via AppShell from design system
 * - useTheme + useActivityRefresh from shared hooks
 * - Products use logoutBehavior="redirect" (SSO — redirects to Core)
 *
 * ERP-specific: nav items are filtered via status_pagina DB table + role-based admin panel.
 * Profile data comes from erp.profiles table (richer than auth.users metadata).
 */
import { useCallback } from "react";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AppShell,
  Sidebar as SharedSidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
  InactivityWarning,
} from "@noctusai/shared/design-system";
import type { NavGroup, NavItem } from "@noctusai/shared/design-system";
import { NotificationBell } from "@/components/NotificationBell";
import { resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining } from "@noctusai/shared";
import { useUserRoles } from "@/hooks/useUserRoles";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useIsAdmin } from "@/hooks/useUserRole";
import { useUpdateProfile } from "@/hooks/useProfiles";
import { toast } from "sonner";
import {
  Home, Target, Users, Building2, Shield,
  LayoutDashboard, UserCircle, HomeIcon, ArrowLeftRight,
  FileText, FileSignature, ShieldCheck, Receipt, Landmark,
  Mail, BarChart3, Sparkles, Settings, DollarSign, Percent, CalendarDays,
  FileBox, MapPin, Key, Globe, Trophy, GitBranch, Store, MessageSquare,
  Megaphone, ClipboardList, CreditCard, Building, Search, BellRing, Instagram,
  Briefcase, ScrollText, Hammer, ChevronLeft, CheckCircle2,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

// ── Role labels ──────────────────────────────────────────────

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

// ── Nav item with route key for status_pagina filtering ──────

interface ERPNavItem extends NavItem { route: string }
interface ERPNavGroup extends NavGroup { items: ERPNavItem[] }

const ALL_NAV_GROUPS: ERPNavGroup[] = [
  {
    key: "principal", label: "Principal", icon: Home, defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: Home, route: "dashboard" },
      { name: "Funil de Vendas", href: "/funil", icon: LayoutDashboard, route: "funil" },
      { name: "Clientes", href: "/clientes", icon: UserCircle, route: "clientes" },
      { name: "Metas", href: "/metas", icon: Target, route: "metas" },
    ],
  },
  {
    key: "comercial", label: "Comercial", icon: Briefcase, defaultOpen: true,
    items: [
      { name: "Imoveis", href: "/imoveis", icon: HomeIcon, route: "imoveis" },
      { name: "Condominios", href: "/condominios", icon: Building2, route: "condominios" },
      { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
      { name: "Negociacoes", href: "/negociacoes", icon: FileText, route: "negociacoes" },
      { name: "Propostas", href: "/propostas", icon: ScrollText, route: "propostas" },
      { name: "Contratos", href: "/contratos", icon: FileText, route: "contratos" },
      { name: "Locacoes", href: "/locacoes", icon: Building, route: "locacoes" },
      { name: "Comissoes", href: "/comissoes", icon: Percent, route: "comissoes" },
    ],
  },
  {
    key: "financeiro", label: "Financeiro", icon: DollarSign,
    items: [
      { name: "Financeiro", href: "/financeiro", icon: DollarSign, route: "financeiro" },
      { name: "Impostos", href: "/impostos", icon: Receipt, route: "impostos" },
      { name: "Banco", href: "/banco", icon: Landmark, route: "banco" },
      { name: "Analise de Credito", href: "/analise-credito", icon: CreditCard, route: "analise-credito" },
    ],
  },
  {
    key: "operacional", label: "Operacional", icon: ClipboardList,
    items: [
      { name: "Agenda", href: "/agenda", icon: CalendarDays, route: "agenda" },
      { name: "Vistorias", href: "/vistorias", icon: Search, route: "vistorias" },
      { name: "Manutencao", href: "/manutencao", icon: Hammer, route: "manutencao" },
      { name: "Chaves", href: "/chaves", icon: Key, route: "chaves" },
      { name: "Campo", href: "/campo", icon: MapPin, route: "campo" },
      { name: "Seguros", href: "/seguros", icon: ShieldCheck, route: "seguros" },
    ],
  },
  {
    key: "marketing", label: "Marketing & Comunicacao", icon: Megaphone,
    items: [
      { name: "Marketing", href: "/marketing", icon: Megaphone, route: "marketing" },
      { name: "Emails", href: "/emails", icon: Mail, route: "emails" },
      { name: "WhatsApp", href: "/whatsapp", icon: MessageSquare, route: "whatsapp" },
      { name: "Meta Ads", href: "/meta-ads", icon: Instagram, route: "meta-ads" },
      { name: "Notificacoes", href: "/notificacoes", icon: BellRing, route: "notificacoes" },
    ],
  },
  {
    key: "documentos", label: "Documentos", icon: FileBox,
    items: [
      { name: "Documentos", href: "/documentos", icon: FileBox, route: "documentos" },
      { name: "Certidoes", href: "/certidoes", icon: ShieldCheck, route: "certidoes" },
      { name: "Matriculas", href: "/matriculas", icon: FileText, route: "matriculas" },
      { name: "Assinaturas", href: "/assinaturas", icon: FileSignature, route: "assinaturas" },
      { name: "DIMOB", href: "/dimob", icon: FileText, route: "dimob" },
      { name: "Relatorios", href: "/relatorios", icon: ClipboardList, route: "relatorios" },
    ],
  },
  {
    key: "portais", label: "Portais & Site", icon: Globe,
    items: [
      { name: "Portal Cliente", href: "/portal-cliente", icon: Users, route: "portal-cliente" },
      { name: "Portal Externo", href: "/portal", icon: Globe, route: "portal" },
      { name: "Site Imoveis", href: "/site", icon: Store, route: "site" },
    ],
  },
  {
    key: "analytics", label: "Analytics & IA", icon: BarChart3,
    items: [
      { name: "BI", href: "/bi", icon: BarChart3, route: "bi" },
      { name: "Matching IA", href: "/matching", icon: Sparkles, route: "matching" },
      { name: "Gamificacao", href: "/gamificacao", icon: Trophy, route: "gamificacao" },
    ],
  },
];

const ALL_STANDALONE: ERPNavItem[] = [
  { name: "Distribuicao", href: "/distribuicao", icon: GitBranch, route: "distribuicao" },
  { name: "Filiais", href: "/filiais", icon: Building, route: "filiais" },
  { name: "Configuracoes", href: "/configuracoes", icon: Settings, route: "configuracoes" },
];

const PAINEL_GROUP: ERPNavGroup = {
  key: "painel", label: "Painel de Controle", icon: Shield, defaultOpen: true,
  items: [
    { name: "Usuarios", href: "/usuarios", icon: Users, route: "usuarios" },
    { name: "Admin", href: "/admin", icon: Shield, route: "admin" },
    { name: "Log de Acoes", href: "/log-acoes", icon: CheckCircle2, route: "log-acoes" },
  ],
};

// ── Nav filtering (status_pagina feature flags) ──────────────

function toNavItem(item: ERPNavItem, statusPaginas: any[], isAdminOrDev: boolean): NavItem {
  const base: NavItem = { name: item.name, href: item.href, icon: item.icon };
  if (isAdminOrDev) {
    const status = statusPaginas.find((p: any) => p.nome_pagina === item.route);
    if (status?.status === "desenvolvimento") base.badge = "DEV";
    else if (status?.status === "producao") base.badge = "OK";
  }
  return base;
}

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

// ── Layout ───────────────────────────────────────────────────

export function Layout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const { data: profile, isLoading: isLoadingProfile } = useUserProfile();
  const { data: roles = [], isLoading: isLoadingRoles } = useUserRoles();
  const { isAdmin } = useIsAdmin();
  const updateProfile = useUpdateProfile();

  const { theme, toggleTheme } = useTheme({
    initialTheme: profile?.tema as "light" | "dark" | undefined,
    onPersist: (newTheme) => {
      if (profile?.id) updateProfile.mutate({ id: profile.id, tema: newTheme });
    },
  });

  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
  });

  // SSO context: role, plan, license, org info
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isSSOAdmin = ssoCtx.isProductAdmin;
  const isAdminOrDev = isSSOAdmin || roles.includes("admin") || roles.includes("dev");
  const trialDays = isTrial(ssoCtx) ? subscriptionDaysRemaining(ssoCtx) : null;
  const licenseDays = licenseDaysRemaining(ssoCtx);

  // Feature flag filtering via status_pagina
  const { data: statusPaginas = [] } = useQuery({
    queryKey: ["status-paginas"],
    queryFn: async () => {
      const { data } = await supabase.from("status_pagina").select("*");
      return data || [];
    },
  });

  const isPageVisible = (route: string) =>
    statusPaginas.some((p: any) => p.nome_pagina === route);

  const filteredGroups: NavGroup[] = ALL_NAV_GROUPS
    .map((group) => ({
      key: group.key, label: group.label, icon: group.icon, defaultOpen: group.defaultOpen,
      items: group.items
        .filter((item) => isPageVisible(item.route))
        .map((item) => toNavItem(item, statusPaginas, isAdminOrDev)),
    }))
    .filter((group) => group.items.length > 0);

  // Admin panel group
  const painelItems = PAINEL_GROUP.items
    .filter((item) => isPageVisible(item.route))
    .map((item) => toNavItem(item, statusPaginas, isAdminOrDev));
  if (painelItems.length > 0) {
    filteredGroups.push({
      key: PAINEL_GROUP.key, label: PAINEL_GROUP.label,
      icon: PAINEL_GROUP.icon, defaultOpen: PAINEL_GROUP.defaultOpen,
      items: painelItems,
    });
  }

  const filteredStandalone: NavItem[] = ALL_STANDALONE
    .filter((item) => isPageVisible(item.route))
    .map((item) => toNavItem(item, statusPaginas, isAdminOrDev));

  // Auth handlers — SSO users go back to Core; direct users sign out locally
  const handleLogout = async () => {
    await supabase.auth.signOut();
    if (ssoCtx.isSSO) {
      window.location.href = CORE_URL;
    } else {
      window.location.href = "/login";
    }
  };

  const handleUpdateProfile = async (data: { name: string; email: string; phone: string }) => {
    if (!profile?.id) return;
    await updateProfile.mutateAsync({
      id: profile.id, nome: data.name,
      ...(isAdmin && { email: data.email }),
      telefone: data.phone,
    });
    queryClient.invalidateQueries({ queryKey: ["user-profile"] });
    toast.success("Perfil atualizado com sucesso!");
  };

  const handleUpdatePassword = async (newPassword: string) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    toast.success("Senha atualizada com sucesso!");
  };

  const isLoading = isLoadingProfile || isLoadingRoles;

  if (isLoading || !profile) {
    return (
      <header className="h-14 sm:h-16 bg-card border-b border-border px-4 sm:px-6 flex items-center justify-end">
        <p className="text-sm font-medium text-muted-foreground">Carregando...</p>
      </header>
    );
  }

  return (
    <AppShell
      sidebar={
        <SharedSidebar
          brandIcon={Building2}
          brandTitle="ONE"
          brandSubtitle={ssoCtx.org.name || "Consultoria Imobiliaria"}
          navGroups={filteredGroups}
          standaloneItems={filteredStandalone}
          footerContent={ssoCtx.isSSO ? BackToCore : undefined}
        />
      }
      header={({ onMenuToggle }) => (
        <SharedHeader
          user={{
            id: profile.id,
            name: profile.nome,
            email: profile.email,
            phone: profile.telefone,
            avatar: profile.avatar,
            role: isSSOAdmin && roles.length === 0 ? "Administrador" : getRolesLabel(roles),
          }}
          onMenuToggle={onMenuToggle}
          logoutBehavior="redirect"
          platformUrl={CORE_URL}
          onLogout={handleLogout}
          theme={theme}
          onThemeToggle={toggleTheme}
          actions={<NotificationBell />}
          canEditEmail={isAdmin}
          onUpdateProfile={handleUpdateProfile}
          onUpdatePassword={handleUpdatePassword}
        />
      )}
    >
      <div className="p-4 sm:p-6 lg:p-8">
        {trialDays !== null && trialDays <= 7 && (
          <div className="mb-4 rounded-lg border border-warning bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
            {trialDays > 0
              ? `Periodo de teste expira em ${trialDays} dia${trialDays !== 1 ? "s" : ""}.`
              : "Periodo de teste expirado."}
          </div>
        )}
        {licenseDays !== null && licenseDays <= 7 && (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {licenseDays > 0
              ? `Licenca expira em ${licenseDays} dia${licenseDays !== 1 ? "s" : ""}.`
              : "Licenca expirada."}
          </div>
        )}
        {children}
      </div>
      <InactivityWarning
        onExtend={async () => { await supabase.auth.refreshSession(); }}
        onExpired={() => { supabase.auth.signOut(); }}
      />
    </AppShell>
  );
}
