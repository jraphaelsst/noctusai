import { useState } from "react";
import {
  LayoutDashboard, Search, Building2, CalendarDays, ClipboardList,
  TrendingUp, Wallet, MessageSquare, Settings, Heart, Star,
  Smile, BookOpen, CheckSquare, Receipt,
} from "lucide-react";
import { Sidebar, type NavGroup } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "@/lib/utils";

const navGroups: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Heart,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/patient", icon: LayoutDashboard },
      { name: "Encontrar Terapeuta", href: "/therapists", icon: Search },
      { name: "Explorar Clinicas", href: "/clinics", icon: Building2 },
    ],
  },
  {
    key: "minha-terapia",
    label: "Minha Terapia",
    icon: ClipboardList,
    defaultOpen: true,
    items: [
      { name: "Minha Agenda", href: "/patient/agenda", icon: CalendarDays },
      { name: "Minhas Sessoes", href: "/patient/sessoes", icon: ClipboardList },
      { name: "Minha Jornada", href: "/patient/jornada", icon: TrendingUp },
      { name: "Humor", href: "/patient/humor", icon: Smile },
      { name: "Diario", href: "/patient/diario", icon: BookOpen },
      { name: "Tarefas", href: "/patient/tarefas", icon: CheckSquare },
    ],
  },
  {
    key: "conta",
    label: "Conta",
    icon: Wallet,
    defaultOpen: false,
    items: [
      { name: "Minha Carteira", href: "/patient/carteira", icon: Wallet },
      { name: "Recibos", href: "/patient/recibos", icon: Receipt },
      { name: "Avaliacoes", href: "/patient/avaliacoes", icon: Star },
      { name: "Mensagens", href: "/patient/mensagens", icon: MessageSquare },
    ],
  },
];

const standaloneItems = [
  { name: "Configuracoes", href: "/patient/configuracoes", icon: Settings },
];

interface PatientLayoutProps {
  children: React.ReactNode;
}

export function PatientLayout({ children }: PatientLayoutProps) {
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
          brandIcon={Heart}
          brandTitle="NoctusAI"
          brandSubtitle="Plataforma de Terapia"
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
