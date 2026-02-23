import { Home, Target, Users, Building2, Shield, ChevronDown, LayoutDashboard, UserCircle, Wrench, CheckCircle2, HomeIcon, ArrowLeftRight, FileText } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useUserRoles } from "@/hooks/useUserRoles";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useState } from "react";

export function Sidebar() {
  const { data: roles = [] } = useUserRoles();
  const isAdminOrDev = roles.includes('admin') || roles.includes('dev');
  const [painelOpen, setPainelOpen] = useState(true);
  const [geralOpen, setGeralOpen] = useState(true);

  // Buscar status das páginas (RLS já filtra automaticamente)
  const { data: statusPaginas = [] } = useQuery({
    queryKey: ["status-paginas"],
    queryFn: async () => {
      const { data } = await supabase
        .from("status_pagina")
        .select("*");
      return data || [];
    },
  });

  const allGeralNavigation = [
    { name: "Dashboard", href: "/", icon: Home, route: "dashboard" },
    { name: "Funil", href: "/funil", icon: LayoutDashboard, route: "funil" },
    { name: "Clientes", href: "/clientes", icon: UserCircle, route: "clientes" },
    { name: "Metas", href: "/metas", icon: Target, route: "metas" },
    { name: "Imóveis", href: "/imoveis", icon: HomeIcon, route: "imoveis" },
    { name: "Condomínios", href: "/condominios", icon: Building2, route: "condominios" },
    { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
    { name: "Negociações", href: "/negociacoes", icon: FileText, route: "negociacoes" },
  ];

  // Filtrar navegação baseado nas páginas retornadas pelas políticas RLS
  // RLS já garante que:
  // - Usuários comuns só veem páginas gerais em produção
  // - Devs veem páginas gerais (produção + desenvolvimento)
  // - Admins veem todas as páginas
  const geralNavigation = allGeralNavigation.filter((item) => {
    const statusPagina = statusPaginas.find((p) => p.nome_pagina === item.route);
    // Se a página não está na lista retornada pela RLS, não mostrar
    return !!statusPagina;
  });

  const painelNavigation = [
    { name: "Usuários", href: "/usuarios", icon: Users, route: "usuarios" },
    { name: "Admin", href: "/admin", icon: Shield, route: "admin" },
    { name: "Log de Ações", href: "/log-acoes", icon: CheckCircle2, route: "log-acoes" },
  ];

  // Filtrar navegação do painel baseado nas políticas RLS
  // Apenas admins verão páginas administrativas
  const filteredPainelNavigation = painelNavigation.filter((item) => {
    const statusPagina = statusPaginas.find((p) => p.nome_pagina === item.route);
    return !!statusPagina;
  });

  // Helper para obter o status de uma página
  const getStatusPagina = (route: string) => {
    return statusPaginas.find((p) => p.nome_pagina === route);
  };

  // Helper para renderizar badge de status (apenas para devs/admins)
  const renderStatusBadge = (route: string) => {
    if (!isAdminOrDev) return null;
    
    const statusPagina = getStatusPagina(route);
    if (!statusPagina) return null;

    if (statusPagina.status === 'desenvolvimento') {
      return <Wrench className="h-3 w-3 text-amber-500" />;
    }
    
    if (statusPagina.status === 'producao') {
      return <CheckCircle2 className="h-3 w-3 text-green-500" />;
    }
    
    return null;
  };

  return (
    <div className="w-full md:w-64 min-h-screen bg-card border-r border-border">
      <div className="p-4 sm:p-6">
        <div className="flex items-center gap-2 mb-6 sm:mb-8">
          <Building2 className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-xl font-bold text-primary">ONE</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Consultoria Imobiliária</p>
          </div>
        </div>
        
        <nav className="space-y-4">
          {/* Seção Geral - sempre visível para admins/devs */}
          {isAdminOrDev ? (
            <Collapsible open={geralOpen} onOpenChange={setGeralOpen}>
              <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors">
                <span>Geral</span>
                <ChevronDown className={cn(
                  "h-4 w-4 transition-transform duration-200",
                  geralOpen && "transform rotate-180"
                )} />
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-1 mt-2">
                {geralNavigation.map((item) => (
                  <NavLink
                    key={item.name}
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span className="flex-1">{item.name}</span>
                    {renderStatusBadge(item.route)}
                  </NavLink>
                ))}
              </CollapsibleContent>
            </Collapsible>
          ) : (
            /* Seção Geral - sem heading para não-admins/devs */
            <div className="space-y-1">
              {geralNavigation.map((item) => (
                <NavLink
                  key={item.name}
                  to={item.href}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent"
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  <span className="flex-1">{item.name}</span>
                  {renderStatusBadge(item.route)}
                </NavLink>
              ))}
            </div>
          )}

          {/* Seção Painel de Controle - mostrar apenas se houver páginas visíveis */}
          {filteredPainelNavigation.length > 0 && (
            <Collapsible open={painelOpen} onOpenChange={setPainelOpen}>
              <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors">
                <span>Painel de Controle</span>
                <ChevronDown className={cn(
                  "h-4 w-4 transition-transform duration-200",
                  painelOpen && "transform rotate-180"
                )} />
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-1 mt-2">
                {filteredPainelNavigation.map((item) => (
                  <NavLink
                    key={item.name}
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span className="flex-1">{item.name}</span>
                    {renderStatusBadge(item.route)}
                  </NavLink>
                ))}
              </CollapsibleContent>
            </Collapsible>
          )}
        </nav>
      </div>
    </div>
  );
}