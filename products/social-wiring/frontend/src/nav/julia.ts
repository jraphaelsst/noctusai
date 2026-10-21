/**
 * Julia — the chatbot module's nav group (owner decision 2026-10-13).
 *
 * Modelled on the Lais product; the WhatsApp (WAHA) surface lives here (it
 * left "Conexões" entirely). The module WILL be renamed — that is why the
 * label lives in exactly ONE constant (`JULIA_LABEL`) that the sidebar group,
 * the page headers and the tests all read. Rename = edit that one string.
 *
 * Adding a Julia page = add ONE entry to `JULIA_PAGES` (+ its status_pagina
 * row in a migration, + its route in App.tsx). The nav group is derived from
 * `JULIA_PAGES`, so no second list to keep in sync.
 */
import type { LucideIcon } from "lucide-react";
import { BarChart3, Bell, BookOpen, Bot, Building2, CalendarClock, CreditCard, FileText, HelpCircle, Home, LayoutDashboard, MessagesSquare, RefreshCw, Send, Settings2, ShieldOff, Sparkles, Star, Users } from "lucide-react";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/lib";

/** The module's display name — the ONLY place it is spelled. */
export const JULIA_LABEL = "Julia";

/** Stable nav-group key (not user-visible; survives a label rename). */
export const JULIA_NAV_KEY = "julia";

export const JULIA_ICON: LucideIcon = Bot;

interface JuliaPage extends NavItemWithRoute {
  icon: LucideIcon;
  /** status_pagina key gating the nav item (migrations 252 / 259). */
  route: string;
}

/** Every Julia page, in nav order. */
export const JULIA_PAGES = {
  painel: {
    name: "Painel",
    href: "/julia/painel",
    icon: LayoutDashboard,
    route: "julia_painel",
  },
  conversas: {
    name: "Conversas",
    href: "/julia/conversas",
    icon: MessagesSquare,
    route: "julia_conversas",
  },
  configuracoes: {
    name: "Configurações",
    href: "/julia/configuracoes",
    icon: Settings2,
    route: "julia_configuracoes",
  },
  agente: {
    name: "Agente",
    href: "/julia/agente",
    icon: Sparkles,
    route: "julia_agente",
  },
  conhecimento: {
    name: "Conhecimento",
    href: "/julia/conhecimento",
    icon: BookOpen,
    route: "julia_conhecimento",
  },
  perguntas: {
    name: "Perguntas",
    href: "/julia/perguntas",
    icon: HelpCircle,
    route: "julia_perguntas",
  },
  visitas: {
    name: "Visitas",
    href: "/julia/visitas",
    icon: CalendarClock,
    route: "julia_visitas",
  },
  reengajamento: {
    name: "Reengajamento",
    href: "/julia/reengajamento",
    icon: RefreshCw,
    route: "julia_reengajamento",
  },
  notificacoes: {
    name: "Notificações",
    href: "/julia/notificacoes",
    icon: Bell,
    route: "julia_notificacoes",
  },
  modelos: {
    name: "Modelos",
    href: "/julia/modelos",
    icon: FileText,
    route: "julia_modelos",
  },
  disparos: {
    name: "Disparos",
    href: "/julia/disparos",
    icon: Send,
    route: "julia_disparos",
  },
  proprietarios: {
    name: "Atualização de imóveis",
    href: "/julia/proprietarios",
    icon: Home,
    route: "julia_proprietarios",
  },
  envio: {
    name: "Envio",
    href: "/julia/envio",
    icon: Send,
    route: "julia_envio",
  },
  leads: {
    name: "Leads",
    href: "/julia/leads",
    icon: Users,
    route: "julia_leads",
  },
  relatorios: {
    name: "Relatórios",
    href: "/julia/relatorios",
    icon: BarChart3,
    route: "julia_relatorios",
  },
  captacao: {
    name: "Captação",
    href: "/julia/captacao",
    icon: Building2,
    route: "julia_captacao",
  },
  equipes: {
    name: "Equipes",
    href: "/julia/equipes",
    icon: Users,
    route: "julia_equipes",
  },
  optOuts: {
    name: "Opt-outs",
    href: "/julia/opt-outs",
    icon: ShieldOff,
    route: "julia_opt_outs",
  },
  avaliacoes: {
    name: "Avaliações no Google",
    href: "/julia/avaliacoes",
    icon: Star,
    route: "julia_avaliacoes",
  },
  credito: {
    name: "Análise de crédito",
    href: "/julia/credito",
    icon: CreditCard,
    route: "julia_credito",
  },
} as const satisfies Record<string, JuliaPage>;

export type JuliaPageKey = keyof typeof JULIA_PAGES;

export const JULIA_NAV_GROUP: NavGroupWithRoute = {
  key: JULIA_NAV_KEY,
  label: JULIA_LABEL,
  icon: JULIA_ICON,
  items: Object.values(JULIA_PAGES).map((p) => ({ ...p })),
};
