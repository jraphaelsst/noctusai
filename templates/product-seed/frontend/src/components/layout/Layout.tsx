import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
} from "@noctusai/shared/design-system";
import type { NavGroup } from "@noctusai/shared/design-system";
import { NotificationBell } from "@/components/NotificationBell";
import { toast } from "sonner";
import { LayoutDashboard, ChevronLeft, {{PRODUCT_ICON}} } from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

const NAV_GROUPS: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      // Add your product nav items here
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

  const handleLogout = () => {
    // Products redirect to NoctusAI dashboard — SSO stays active
    window.location.href = CORE_URL;
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
          brandIcon={{{PRODUCT_ICON}}}
          brandTitle="{{PRODUCT_NAME}}"
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
            role: "{{PRODUCT_NAME}}",
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
      <div className="p-4 sm:p-6 lg:p-8">
        {children}
      </div>
    </AppShell>
  );
}
