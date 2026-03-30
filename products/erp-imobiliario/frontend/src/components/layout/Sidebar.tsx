import {
  Home, Target, Users, Building2, Shield, ChevronDown, ChevronRight,
  LayoutDashboard, UserCircle, Wrench, CheckCircle2, HomeIcon, ArrowLeftRight,
  FileText, FileSignature, UserCheck, HardHat, ShieldCheck, Receipt, Landmark,
  Mail, BarChart3, Sparkles, Settings, DollarSign, Percent, CalendarDays,
  FileBox, MapPin, Key, Globe, Trophy, GitBranch, Store, MessageSquare,
  Megaphone, ClipboardList, CreditCard, Building, Search, BellRing, Instagram,
  Briefcase, ScrollText, Car, Hammer,
} from "lucide-react";
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

interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
  route: string;
}

interface NavGroup {
  label: string;
  icon: React.ElementType;
  defaultOpen?: boolean;
  items: NavItem[];
}

export function Sidebar() {
  const { data: roles = [] } = useUserRoles();
  const isAdminOrDev = roles.includes("admin") || roles.includes("dev");

  // Track open state for each group
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    principal: true,
    comercial: true,
    financeiro: false,
    operacional: false,
    marketing: false,
    documentos: false,
    portais: false,
    analytics: false,
    painel: true,
  });

  const toggleGroup = (key: string) => {
    setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Buscar status das páginas (RLS já filtra automaticamente)
  const { data: statusPaginas = [] } = useQuery({
    queryKey: ["status-paginas"],
    queryFn: async () => {
      const { data } = await supabase.from("status_pagina").select("*");
      return data || [];
    },
  });

  // ── Grouped navigation ──────────────────────────────────────
  const navGroups: (NavGroup & { key: string })[] = [
    {
      key: "principal",
      label: "Principal",
      icon: Home,
      defaultOpen: true,
      items: [
        { name: "Dashboard", href: "/", icon: Home, route: "dashboard" },
        { name: "Funil de Vendas", href: "/funil", icon: LayoutDashboard, route: "funil" },
        { name: "Clientes", href: "/clientes", icon: UserCircle, route: "clientes" },
        { name: "Metas", href: "/metas", icon: Target, route: "metas" },
      ],
    },
    {
      key: "comercial",
      label: "Comercial",
      icon: Briefcase,
      defaultOpen: true,
      items: [
        { name: "Imóveis", href: "/imoveis", icon: HomeIcon, route: "imoveis" },
        { name: "Condomínios", href: "/condominios", icon: Building2, route: "condominios" },
        { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
        { name: "Negociações", href: "/negociacoes", icon: FileText, route: "negociacoes" },
        { name: "Propostas", href: "/propostas", icon: ScrollText, route: "propostas" },
        { name: "Contratos", href: "/contratos", icon: FileText, route: "contratos" },
        { name: "Locações", href: "/locacoes", icon: Building, route: "locacoes" },
        { name: "Comissões", href: "/comissoes", icon: Percent, route: "comissoes" },
      ],
    },
    {
      key: "financeiro",
      label: "Financeiro",
      icon: DollarSign,
      items: [
        { name: "Financeiro", href: "/financeiro", icon: DollarSign, route: "financeiro" },
        { name: "Impostos", href: "/impostos", icon: Receipt, route: "impostos" },
        { name: "Banco", href: "/banco", icon: Landmark, route: "banco" },
        { name: "Análise de Crédito", href: "/analise-credito", icon: CreditCard, route: "analise-credito" },
      ],
    },
    {
      key: "operacional",
      label: "Operacional",
      icon: ClipboardList,
      items: [
        { name: "Agenda", href: "/agenda", icon: CalendarDays, route: "agenda" },
        { name: "Vistorias", href: "/vistorias", icon: Search, route: "vistorias" },
        { name: "Manutenção", href: "/manutencao", icon: Hammer, route: "manutencao" },
        { name: "Chaves", href: "/chaves", icon: Key, route: "chaves" },
        { name: "Campo", href: "/campo", icon: MapPin, route: "campo" },
        { name: "Seguros", href: "/seguros", icon: ShieldCheck, route: "seguros" },
      ],
    },
    {
      key: "marketing",
      label: "Marketing & Comunicação",
      icon: Megaphone,
      items: [
        { name: "Marketing", href: "/marketing", icon: Megaphone, route: "marketing" },
        { name: "Emails", href: "/emails", icon: Mail, route: "emails" },
        { name: "WhatsApp", href: "/whatsapp", icon: MessageSquare, route: "whatsapp" },
        { name: "Meta Ads", href: "/meta-ads", icon: Instagram, route: "meta-ads" },
        { name: "Notificações", href: "/notificacoes", icon: BellRing, route: "notificacoes" },
      ],
    },
    {
      key: "documentos",
      label: "Documentos",
      icon: FileBox,
      items: [
        { name: "Documentos", href: "/documentos", icon: FileBox, route: "documentos" },
        { name: "Certidões", href: "/certidoes", icon: ShieldCheck, route: "certidoes" },
        { name: "Matrículas", href: "/matriculas", icon: FileText, route: "matriculas" },
        { name: "Assinaturas", href: "/assinaturas", icon: FileSignature, route: "assinaturas" },
        { name: "DIMOB", href: "/dimob", icon: FileText, route: "dimob" },
        { name: "Relatórios", href: "/relatorios", icon: ClipboardList, route: "relatorios" },
      ],
    },
    {
      key: "portais",
      label: "Portais & Site",
      icon: Globe,
      items: [
        { name: "Portal Cliente", href: "/portal-cliente", icon: UserCheck, route: "portal-cliente" },
        { name: "Portal Externo", href: "/portal", icon: Globe, route: "portal" },
        { name: "Site Imóveis", href: "/site", icon: Store, route: "site" },
      ],
    },
    {
      key: "analytics",
      label: "Analytics & IA",
      icon: BarChart3,
      items: [
        { name: "BI", href: "/bi", icon: BarChart3, route: "bi" },
        { name: "Matching IA", href: "/matching", icon: Sparkles, route: "matching" },
        { name: "Gamificação", href: "/gamificacao", icon: Trophy, route: "gamificacao" },
      ],
    },
  ];

  // Standalone items (always visible, not grouped)
  const standaloneItems: NavItem[] = [
    { name: "Distribuição", href: "/distribuicao", icon: GitBranch, route: "distribuicao" },
    { name: "Filiais", href: "/filiais", icon: Building, route: "filiais" },
    { name: "Configurações", href: "/configuracoes", icon: Settings, route: "configuracoes" },
  ];

  const painelNavigation: NavItem[] = [
    { name: "Usuários", href: "/usuarios", icon: Users, route: "usuarios" },
    { name: "Admin", href: "/admin", icon: Shield, route: "admin" },
    { name: "Log de Ações", href: "/log-acoes", icon: CheckCircle2, route: "log-acoes" },
  ];

  // Filter nav items based on RLS page status
  const isPageVisible = (route: string) => {
    return statusPaginas.some((p: any) => p.nome_pagina === route);
  };

  const getStatusPagina = (route: string) => {
    return statusPaginas.find((p: any) => p.nome_pagina === route);
  };

  const renderStatusBadge = (route: string) => {
    if (!isAdminOrDev) return null;
    const statusPagina = getStatusPagina(route);
    if (!statusPagina) return null;
    if (statusPagina.status === "desenvolvimento") {
      return <Wrench className="h-3 w-3 text-amber-500" />;
    }
    if (statusPagina.status === "producao") {
      return <CheckCircle2 className="h-3 w-3 text-green-500" />;
    }
    return null;
  };

  const renderNavLink = (item: NavItem) => (
    <NavLink
      key={item.name}
      to={item.href}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-accent"
        )
      }
    >
      <item.icon className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate">{item.name}</span>
      {renderStatusBadge(item.route)}
    </NavLink>
  );

  const filteredPainelNavigation = painelNavigation.filter((item) =>
    isPageVisible(item.route)
  );

  return (
    <div className="w-full md:w-64 min-h-screen bg-card border-r border-border flex flex-col">
      <div className="p-4 sm:p-5">
        {/* Logo */}
        <div className="flex items-center gap-2 mb-5">
          <Building2 className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-xl font-bold text-primary">ONE</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Consultoria Imobiliária
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="space-y-1">
          {navGroups.map((group) => {
            const visibleItems = group.items.filter((item) =>
              isPageVisible(item.route)
            );
            if (visibleItems.length === 0) return null;

            const isOpen = openGroups[group.key] ?? group.defaultOpen ?? false;

            return (
              <Collapsible
                key={group.key}
                open={isOpen}
                onOpenChange={() => toggleGroup(group.key)}
              >
                <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-accent/50">
                  <div className="flex items-center gap-2">
                    <group.icon className="h-3.5 w-3.5" />
                    <span>{group.label}</span>
                  </div>
                  <ChevronRight
                    className={cn(
                      "h-3.5 w-3.5 transition-transform duration-200",
                      isOpen && "rotate-90"
                    )}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-0.5 mt-0.5 ml-2 border-l border-border/50 pl-2">
                  {visibleItems.map(renderNavLink)}
                </CollapsibleContent>
              </Collapsible>
            );
          })}

          {/* Standalone items */}
          {standaloneItems.filter((item) => isPageVisible(item.route)).length > 0 && (
            <div className="pt-2 border-t border-border/50 space-y-0.5">
              {standaloneItems
                .filter((item) => isPageVisible(item.route))
                .map(renderNavLink)}
            </div>
          )}

          {/* Painel de Controle - admin only */}
          {filteredPainelNavigation.length > 0 && (
            <Collapsible
              open={openGroups.painel ?? true}
              onOpenChange={() => toggleGroup("painel")}
            >
              <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2 mt-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-accent/50 border-t border-border/50 pt-3">
                <div className="flex items-center gap-2">
                  <Shield className="h-3.5 w-3.5" />
                  <span>Painel de Controle</span>
                </div>
                <ChevronRight
                  className={cn(
                    "h-3.5 w-3.5 transition-transform duration-200",
                    (openGroups.painel ?? true) && "rotate-90"
                  )}
                />
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-0.5 mt-0.5 ml-2 border-l border-border/50 pl-2">
                {filteredPainelNavigation.map(renderNavLink)}
              </CollapsibleContent>
            </Collapsible>
          )}
        </nav>
      </div>
    </div>
  );
}
