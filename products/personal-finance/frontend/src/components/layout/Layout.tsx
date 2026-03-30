import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import {
  LayoutDashboard, Wallet, ArrowLeftRight, Tags, PiggyBank, Target,
  TrendingUp, Eye, CalendarClock, Landmark, FileBarChart, ArrowUpDown,
  LogOut, Menu, X, ChevronLeft,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/contas", label: "Contas", icon: Wallet },
  { path: "/transacoes", label: "Transacoes", icon: ArrowLeftRight },
  { path: "/categorias", label: "Categorias", icon: Tags },
  { path: "/orcamentos", label: "Orcamentos", icon: PiggyBank },
  { path: "/metas", label: "Metas", icon: Target },
  { path: "/carteira", label: "Investimentos", icon: TrendingUp },
  { path: "/watchlist", label: "Watchlist", icon: Eye },
  { path: "/operacoes", label: "Operacoes", icon: ArrowUpDown },
  { path: "/recorrentes", label: "Recorrentes", icon: CalendarClock },
  { path: "/patrimonio", label: "Patrimonio", icon: Landmark },
  { path: "/relatorios", label: "Relatorios", icon: FileBarChart },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    window.location.href = CORE_URL;
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="flex flex-col md:flex-row">
        {/* Mobile header */}
        <div className="md:hidden flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <span className="text-xl">💰</span>
            <h1 className="font-bold text-lg">Financas</h1>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2">
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Sidebar */}
        <aside className={`${sidebarOpen ? "block" : "hidden"} md:block w-full md:w-64 border-r bg-card min-h-screen`}>
          <div className="p-4 border-b hidden md:flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-2xl">💰</span>
              <div>
                <h1 className="font-bold">Financas Pessoais</h1>
                <p className="text-xs text-muted-foreground">NoctusAI</p>
              </div>
            </div>
            <NotificationBell />
          </div>

          <nav className="p-2 space-y-1">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname === item.path || (item.path !== "/" && location.pathname.startsWith(item.path));
              const Icon = item.icon;
              return (
                <button
                  key={item.path}
                  onClick={() => { navigate(item.path); setSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <div className="p-2 mt-auto border-t">
            <a
              href={CORE_URL}
              className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              Voltar ao NoctusAI
            </a>
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Sair
            </button>
            {user && (
              <div className="px-3 py-2 text-xs text-muted-foreground truncate">
                {user.email}
              </div>
            )}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0 p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
