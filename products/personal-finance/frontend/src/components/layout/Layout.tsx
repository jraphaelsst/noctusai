import { useCallback } from "react";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
  InactivityWarning,
} from "@noctusai/shared/design-system";
import type { NavGroup } from "@noctusai/shared/design-system";
import { NotificationBell } from "@/components/NotificationBell";
import { toast } from "sonner";
import {
  LayoutDashboard, Wallet, ArrowLeftRight, Tags, PiggyBank, Target,
  TrendingUp, Eye, CalendarClock, Landmark, FileBarChart, ArrowUpDown,
  ChevronLeft, DollarSign, Home, BarChart3, LineChart,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

const NAV_GROUPS: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Contas", href: "/contas", icon: Wallet },
      { name: "Transacoes", href: "/transacoes", icon: ArrowLeftRight },
      { name: "Categorias", href: "/categorias", icon: Tags },
    ],
  },
  {
    key: "planejamento",
    label: "Planejamento",
    icon: BarChart3,
    defaultOpen: true,
    items: [
      { name: "Orcamentos", href: "/orcamentos", icon: PiggyBank },
      { name: "Metas", href: "/metas", icon: Target },
      { name: "Recorrentes", href: "/recorrentes", icon: CalendarClock },
    ],
  },
  {
    key: "investimentos",
    label: "Investimentos",
    icon: LineChart,
    defaultOpen: true,
    items: [
      { name: "Investimentos", href: "/carteira", icon: TrendingUp },
      { name: "Watchlist", href: "/watchlist", icon: Eye },
      { name: "Operacoes", href: "/operacoes", icon: ArrowUpDown },
    ],
  },
  {
    key: "relatorios",
    label: "Relatorios",
    icon: FileBarChart,
    defaultOpen: true,
    items: [
      { name: "Patrimonio", href: "/patrimonio", icon: Landmark },
      { name: "Relatorios", href: "/relatorios", icon: FileBarChart },
    ],
  },
];

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

export function Layout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
  });

  const handleLogout = () => {
    // Fallback — only called if logoutBehavior="signout"
    supabase.auth.signOut();
  };

  const handleUpdateProfile = async (data: { name: string; email: string; phone: string }) => {
    const { error } = await supabase.auth.updateUser({
      data: { full_name: data.name, phone: data.phone },
    });
    if (error) throw error;
    toast.success("Perfil atualizado com sucesso!");
  };

  const handleUpdatePassword = async (newPassword: string) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    toast.success("Senha atualizada com sucesso!");
  };

  const userName = user?.user_metadata?.full_name
    || user?.user_metadata?.name
    || user?.email?.split("@")[0]
    || "Usuario";

  return (
    <AppShell
      sidebar={
        <Sidebar
          brandIcon={DollarSign}
          brandTitle="Financas Pessoais"
          brandSubtitle="NoctusAI"
          navGroups={NAV_GROUPS}
          footerContent={BackToCore}
        />
      }
      header={({ onMenuToggle }) => (
        <SharedHeader
          user={{
            name: userName,
            email: user?.email || "",
            phone: user?.user_metadata?.phone || user?.phone || "",
            role: "Financas Pessoais",
          }}
          onMenuToggle={onMenuToggle}
          logoutBehavior="redirect"
          platformUrl={CORE_URL}
          onLogout={handleLogout}
          theme={theme}
          onThemeToggle={toggleTheme}
          actions={<NotificationBell />}
          onUpdateProfile={handleUpdateProfile}
          onUpdatePassword={handleUpdatePassword}
        />
      )}
    >
      <div className="p-4 sm:p-6">
        {children}
      </div>
      <InactivityWarning
        onExtend={async () => { await supabase.auth.refreshSession(); }}
        onExpired={() => { window.location.href = CORE_URL; }}
      />
    </AppShell>
  );
}
