import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Building2,
  Calendar,
  Camera,
  Clapperboard,
  KanbanSquare,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  Sun,
  Users,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/stores/auth";
import { cn } from "@/lib/utils";

/** Os nove destinos do produto, na ordem do protótipo. */
export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/crm", label: "CRM Comercial", icon: KanbanSquare },
  { to: "/agenda", label: "Agenda", icon: Calendar },
  { to: "/producao", label: "Produção", icon: Clapperboard },
  { to: "/imoveis", label: "Imóveis", icon: Building2 },
  { to: "/servicos", label: "Serviços", icon: ListChecks },
  { to: "/financeiro", label: "Financeiro", icon: Wallet },
  { to: "/equipamentos", label: "Equipamentos", icon: Camera },
  { to: "/clientes", label: "Clientes", icon: Users },
];

const CHAVE_TEMA = "p-studio:tema";

function useTema() {
  const [escuro, setEscuro] = useState(() => localStorage.getItem(CHAVE_TEMA) === "escuro");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", escuro);
    localStorage.setItem(CHAVE_TEMA, escuro ? "escuro" : "claro");
  }, [escuro]);
  return { escuro, alternar: () => setEscuro((e) => !e) };
}

export default function AppLayout() {
  const { me, signOut } = useAuth();
  const { escuro, alternar } = useTema();
  const { pathname } = useLocation();
  const [menuAberto, setMenuAberto] = useState(false);

  // Navegar fecha a gaveta no mobile.
  useEffect(() => setMenuAberto(false), [pathname]);

  const atual = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)));

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {menuAberto && (
        <div className="fixed inset-0 z-30 bg-foreground/40 md:hidden" onClick={() => setMenuAberto(false)} />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0",
          menuAberto ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center gap-2 border-b border-sidebar-border px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Camera className="h-5 w-5" />
          </div>
          <div>
            <div className="font-display text-lg leading-none">P Studio</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">Operação e Financeiro</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-sidebar-border px-4 py-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-accent-foreground">
              {(me?.nome ?? me?.email ?? "P")[0].toUpperCase()}
            </div>
            <div className="min-w-0 leading-tight">
              <div className="truncate font-medium text-foreground">{me?.nome ?? me?.email}</div>
              <div className="truncate">Estúdio</div>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur md:px-8">
          <button
            onClick={() => setMenuAberto((a) => !a)}
            className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-accent md:hidden"
            aria-label="Abrir menu"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className="font-display text-lg">{atual?.label ?? "P Studio"}</div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={alternar}
              className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-accent"
              aria-label="Alternar tema"
            >
              {escuro ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              onClick={signOut}
              className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-accent"
              aria-label="Sair"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
