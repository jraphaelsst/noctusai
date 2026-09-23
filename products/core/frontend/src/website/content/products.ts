/**
 * Marketing copy for the curated products shown on the public website.
 *
 * Source of truth for WHICH products exist and their catalog slug/state is
 * `public.products` (core DB) — see `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`
 * and `deploy/fleet/build-scope.txt`. This file adds pt-BR/EN marketing
 * copy on top; it never invents a product that isn't real.
 *
 * Curation decision (2026-09-23, frontend-engineer slice `website-site`):
 * of the active catalog (`academia-de-reciclagem`, `agents`, `community`,
 * `core`, `igig`, `orbity`, `p-studio`, `social-wiring`), only THREE are
 * general-purpose, multi-tenant offers a visitor could plausibly sign up
 * for. The rest are single-client builds (academia-de-reciclagem, agents,
 * p-studio) or too early to market (community — "domain modules planned,
 * not built" per 02-LANDSCAPE.md) and are deliberately left OUT of the
 * public site rather than misrepresented as products anyone can buy:
 *
 *   - `social-wiring` — LIVE in prod (`deploy_scope='live'`) → `disponivel`
 *   - `orbity`        — built, `deploy_scope='dev'` (not yet promoted) → `lista_de_espera`
 *   - `igig`          — built, `deploy_scope='dev'` (not yet promoted) → `lista_de_espera`
 *
 * `content/defaults.ts` mirrors these states in `WebsiteSettings.products[]`.
 * The admin can change order/visibility/state later without a code change;
 * changing WHICH slugs exist requires shipping new copy here (D3/D4-style
 * seam — copy is content, not runtime-editable prose, for v1).
 */
import type { L10n } from "./types";

export interface ProductCopy {
  slug: string;
  name: string;
  icon: string; // lucide-react icon name, matches public.products.icone
  tagline: L10n;
  capabilities: L10n[]; // 3-5 short bullets
  panel: {
    /** One-line label for the faux-UI panel header. */
    heading: L10n;
    /** 3-4 short rows the faux-UI panel renders as fake list items. */
    rows: L10n[];
  };
  /** Real capability metric, ONLY when true — never invented (P7). */
  metric?: L10n;
}

export const PRODUCTS: Record<string, ProductCopy> = {
  "social-wiring": {
    slug: "social-wiring",
    name: "Social Wiring",
    icon: "Share2",
    tagline: {
      pt: "WhatsApp, e-mail, Google e Meta conversando em um só lugar.",
      en: "WhatsApp, email, Google and Meta, wired into one place.",
    },
    capabilities: [
      { pt: "IA conversacional no WhatsApp, com agendamento automático", en: "Conversational AI on WhatsApp, with automatic scheduling" },
      { pt: "E-mail marketing com templates e disparo segmentado", en: "Email marketing with templates and segmented sending" },
      { pt: "Integrações com Google (Calendar, Maps, Drive) e Meta (Facebook, Instagram)", en: "Google (Calendar, Maps, Drive) and Meta (Facebook, Instagram) integrations" },
      { pt: "Canal YouTube conectado ao mesmo painel", en: "YouTube channel wired into the same panel" },
    ],
    panel: {
      heading: { pt: "Central de canais", en: "Channel hub" },
      rows: [
        { pt: "WhatsApp — 1 conversa ativa", en: "WhatsApp — 1 active conversation" },
        { pt: "E-mail — próximo disparo agendado", en: "Email — next send scheduled" },
        { pt: "Google Calendar — sincronizado", en: "Google Calendar — synced" },
      ],
    },
  },
  orbity: {
    slug: "orbity",
    name: "Orbity",
    icon: "Box",
    tagline: {
      pt: "O sistema operacional da sua agência: CRM, financeiro e automação em um lugar.",
      en: "Your agency's operating system: CRM, finance and automation in one place.",
    },
    capabilities: [
      { pt: "CRM e funil de vendas para agências", en: "CRM and sales funnel for agencies" },
      { pt: "Contratos, financeiro e agenda integrados", en: "Contracts, finance and agenda, integrated" },
      { pt: "Automação de WhatsApp e tráfego Meta Ads", en: "WhatsApp automation and Meta Ads traffic" },
      { pt: "Relatórios prontos para enviar ao cliente", en: "Client-ready reports" },
    ],
    panel: {
      heading: { pt: "Funil comercial", en: "Sales funnel" },
      rows: [
        { pt: "Novo lead — Instagram Ads", en: "New lead — Instagram Ads" },
        { pt: "Proposta enviada — aguardando retorno", en: "Proposal sent — awaiting reply" },
        { pt: "Contrato assinado", en: "Contract signed" },
      ],
    },
  },
  igig: {
    slug: "igig",
    name: "IgIg",
    icon: "Palette",
    tagline: {
      pt: "ERP para agências de comunicação: da criação ao financeiro.",
      en: "ERP for communication agencies: from creative to finance.",
    },
    capabilities: [
      { pt: "Central da marca e cofre de ativos do cliente", en: "Brand hub and client asset vault" },
      { pt: "Esteira de produção criativa com portal de aprovação", en: "Creative production pipeline with an approval portal" },
      { pt: "Planejamento editorial e distribuição", en: "Editorial planning and distribution" },
      { pt: "Financeiro, retainers e DRE por cliente", en: "Finance, retainers and P&L per client" },
    ],
    panel: {
      heading: { pt: "Esteira de produção", en: "Production pipeline" },
      rows: [
        { pt: "Peça em revisão — cliente A", en: "Piece in review — client A" },
        { pt: "Aprovado — pronto para publicar", en: "Approved — ready to publish" },
        { pt: "DRE do mês — atualizado", en: "This month's P&L — updated" },
      ],
    },
  },
};

export const PRODUCT_ORDER = ["social-wiring", "orbity", "igig"] as const;
