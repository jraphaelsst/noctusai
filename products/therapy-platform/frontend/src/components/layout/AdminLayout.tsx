import { useState } from "react";
import {
  LayoutDashboard, Users, Building2, UserCircle, CalendarDays,
  DollarSign, ReceiptText, Settings, HeadphonesIcon, ShieldCheck,
  Brain, Star, AlertTriangle,
} from "lucide-react";
import { Sidebar, type NavGroup, type NavItem } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "@/lib/utils";

const navGroups: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/admin", icon: LayoutDashboard },
      { name: "Terapeutas", href: "/admin/terapeutas", icon: Users },
      { name: "Clinicas", href: "/admin/clinicas", icon: Building2 },
      { name: "Pacientes", href: "/admin/pacientes", icon: UserCircle },
    ],
  },
  {
    key: "operacional",
    label: "Operacional",
    icon: CalendarDays,
    defaultOpen: true,
    items: [
      { name: "Agendamentos", href: "/admin/agendamentos", icon: CalendarDays },
      { name: "Financeiro", href: "/admin/financeiro", icon: DollarSign },
      { name: "Reembolsos", href: "/admin/reembolsos", icon: ReceiptText },
    ],
  },
  {
    key: "sistema",
    label: "Sistema",
    icon: Settings,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/admin/configuracoes", icon: Settings },
      { name: "Prompts IA", href: "/admin/prompts-ia", icon: Brain },
      { name: "Suporte", href: "/admin/suporte", icon: HeadphonesIcon },
      { name: "Moderacao", href: "/admin/moderacao", icon: ShieldCheck },
      { name: "Alertas de Crise", href: "/admin/alertas-crise", icon: AlertTriangle },
      { name: "Avaliacoes", href: "/admin/avaliacoes", icon: Star },
    ],
  },
];

interface AdminLayoutProps {
  children: React.ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 transition-transform duration-300 md:static md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <Sidebar
          brandIcon={ShieldCheck}
          brandTitle="NoctusAI"
          brandSubtitle="Painel Administrativo"
          navGroups={navGroups}
          onNavigate={() => setSidebarOpen(false)}
        />
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuToggle={() => setSidebarOpen(!sidebarOpen)} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
