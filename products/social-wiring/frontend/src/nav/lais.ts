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
import { BookOpen, Bot, CalendarClock, HelpCircle, MessagesSquare, RefreshCw, Settings2, Sparkles } from "lucide-react";
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
} as const satisfies Record<string, LaisPage>;

export type LaisPageKey = keyof typeof LAIS_PAGES;

export const LAIS_NAV_GROUP: NavGroupWithRoute = {
  key: LAIS_NAV_KEY,
  label: LAIS_LABEL,
  icon: LAIS_ICON,
  items: Object.values(LAIS_PAGES).map((p) => ({ ...p })),
};
