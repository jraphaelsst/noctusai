import { useState } from "react";
import {
  LayoutDashboard, Users, UserCircle, CalendarDays,
  DollarSign, Settings, MessageSquare, Star, Building2,
} from "lucide-react";
import { Sidebar, type NavGroup } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "@/lib/utils";

const navGroups: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/clinic", icon: LayoutDashboard },
      { name: "Terapeutas", href: "/clinic/terapeutas", icon: Users },
      { name: "Pacientes", href: "/clinic/pacientes", icon: UserCircle },
      { name: "Agendamentos", href: "/clinic/agendamentos", icon: CalendarDays },
    ],
  },
  {
    key: "gestao",
    label: "Gestao",
    icon: DollarSign,
    defaultOpen: true,
    items: [
      { name: "Financeiro", href: "/clinic/financeiro", icon: DollarSign },
      { name: "Mensagens", href: "/clinic/mensagens", icon: MessageSquare },
      { name: "Avaliacoes", href: "/clinic/avaliacoes", icon: Star },
    ],
  },
];

const standaloneItems = [
  { name: "Configuracoes", href: "/clinic/configuracoes", icon: Settings },
];

interface ClinicLayoutProps {
  children: React.ReactNode;
}

export function ClinicLayout({ children }: ClinicLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 transition-transform duration-300 md:static md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <Sidebar
          brandIcon={Building2}
          brandTitle="Clinica"
          brandSubtitle="Gestao de Clinica"
          navGroups={navGroups}
          standaloneItems={standaloneItems}
          onNavigate={() => setSidebarOpen(false)}
        />
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuToggle={() => setSidebarOpen(!sidebarOpen)} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
