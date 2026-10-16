/**
 * Lais — the chatbot module's nav group (owner decision 2026-10-13).
 *
 * Modelled on the Lais product; the WhatsApp (WAHA) surface lives here (it
 * left "Conexões" entirely). The module WILL be renamed — that is why the
 * label lives in exactly ONE constant (`LAIS_LABEL`) that the sidebar group,
 * the page headers and the tests all read. Rename = edit that one string.
 *
 * Adding a Lais page = add ONE entry to `LAIS_PAGES` (+ its status_pagina
 * row in a migration, + its route in App.tsx). The nav group is derived from
 * `LAIS_PAGES`, so no second list to keep in sync.
 */
import type { LucideIcon } from "lucide-react";
import { BarChart3, Bell, BookOpen, Bot, Building2, CalendarClock, CreditCard, FileText, HelpCircle, Home, LayoutDashboard, MessagesSquare, RefreshCw, Send, Settings2, Sparkles, Star, Users } from "lucide-react";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/lib";

/** The module's display name — the ONLY place it is spelled. */
export const LAIS_LABEL = "Lais";

/** Stable nav-group key (not user-visible; survives a label rename). */
export const LAIS_NAV_KEY = "lais";

export const LAIS_ICON: LucideIcon = Bot;

interface LaisPage extends NavItemWithRoute {
  icon: LucideIcon;
  /** status_pagina key gating the nav item (migrations 252 / 259). */
  route: string;
}

/** Every Lais page, in nav order. */
export const LAIS_PAGES = {
  painel: {
    name: "Painel",
    href: "/lais/painel",
    icon: LayoutDashboard,
    route: "lais_painel",
  },
  conversas: {
    name: "Conversas",
    href: "/lais/conversas",
    icon: MessagesSquare,
    route: "lais_conversas",
  },
  configuracoes: {
    name: "Configurações",
    href: "/lais/configuracoes",
    icon: Settings2,
    route: "lais_configuracoes",
  },
  agente: {
    name: "Agente",
    href: "/lais/agente",
    icon: Sparkles,
    route: "lais_agente",
  },
  conhecimento: {
    name: "Conhecimento",
    href: "/lais/conhecimento",
    icon: BookOpen,
    route: "lais_conhecimento",
  },
  perguntas: {
    name: "Perguntas",
    href: "/lais/perguntas",
    icon: HelpCircle,
    route: "lais_perguntas",
  },
  visitas: {
    name: "Visitas",
    href: "/lais/visitas",
    icon: CalendarClock,
    route: "lais_visitas",
  },
  reengajamento: {
    name: "Reengajamento",
    href: "/lais/reengajamento",
    icon: RefreshCw,
    route: "lais_reengajamento",
  },
  notificacoes: {
    name: "Notificações",
    href: "/lais/notificacoes",
    icon: Bell,
    route: "lais_notificacoes",
  },
  modelos: {
    name: "Modelos",
    href: "/lais/modelos",
    icon: FileText,
    route: "lais_modelos",
  },
  disparos: {
    name: "Disparos",
    href: "/lais/disparos",
    icon: Send,
    route: "lais_disparos",
  },
  proprietarios: {
    name: "Atualização de imóveis",
    href: "/lais/proprietarios",
    icon: Home,
    route: "lais_proprietarios",
  },
  envio: {
    name: "Envio",
    href: "/lais/envio",
    icon: Send,
    route: "lais_envio",
  },
  leads: {
    name: "Leads",
    href: "/lais/leads",
    icon: Users,
    route: "lais_leads",
  },
  relatorios: {
    name: "Relatórios",
    href: "/lais/relatorios",
    icon: BarChart3,
    route: "lais_relatorios",
  },
  captacao: {
    name: "Captação",
    href: "/lais/captacao",
    icon: Building2,
    route: "lais_captacao",
  },
  equipes: {
    name: "Equipes",
    href: "/lais/equipes",
    icon: Users,
    route: "lais_equipes",
  },
  avaliacoes: {
    name: "Avaliações no Google",
    href: "/lais/avaliacoes",
    icon: Star,
    route: "lais_avaliacoes",
  },
  credito: {
    name: "Análise de crédito",
    href: "/lais/credito",
    icon: CreditCard,
    route: "lais_credito",
  },
} as const satisfies Record<string, LaisPage>;

export type LaisPageKey = keyof typeof LAIS_PAGES;

export const LAIS_NAV_GROUP: NavGroupWithRoute = {
  key: LAIS_NAV_KEY,
  label: LAIS_LABEL,
  icon: LAIS_ICON,
  items: Object.values(LAIS_PAGES).map((p) => ({ ...p })),
};
