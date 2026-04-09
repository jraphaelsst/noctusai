import { useState } from "react";
import {
  LayoutDashboard, CalendarDays, Users, ClipboardList,
  DollarSign, Star, Settings, MessageSquare, Brain,
  CheckSquare, BarChart3, AlertTriangle,
} from "lucide-react";
import { Sidebar, type NavGroup } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "@/lib/utils";

const navGroups: NavGroup[] = [
  {
    key: "consultorio",
    label: "Consultorio",
    icon: Brain,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/therapist", icon: LayoutDashboard },
      { name: "Agenda", href: "/therapist/agenda", icon: CalendarDays },
      { name: "Pacientes", href: "/therapist/pacientes", icon: Users },
      { name: "Sessoes", href: "/therapist/sessoes", icon: ClipboardList },
      { name: "Prontuario", href: "/therapist/prontuario", icon: ClipboardList },
    ],
  },
  {
    key: "gestao",
    label: "Gestao",
    icon: DollarSign,
    defaultOpen: true,
    items: [
      { name: "Financeiro", href: "/therapist/financeiro", icon: DollarSign },
      { name: "Tarefas", href: "/therapist/tarefas-terapeuticas", icon: CheckSquare },
      { name: "Dashboard", href: "/therapist/bi", icon: BarChart3 },
      { name: "Alertas", href: "/therapist/alertas-crise", icon: AlertTriangle },
      { name: "Avaliacoes", href: "/therapist/avaliacoes", icon: Star },
      { name: "Mensagens", href: "/therapist/mensagens", icon: MessageSquare },
    ],
  },
];

const standaloneItems = [
  { name: "Configuracoes", href: "/therapist/configuracoes", icon: Settings },
];

interface TherapistLayoutProps {
  children: React.ReactNode;
}

export function TherapistLayout({ children }: TherapistLayoutProps) {
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
          brandIcon={Brain}
          brandTitle="Terapeuta"
          brandSubtitle="Meu Consultorio"
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
