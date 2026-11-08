/**
 * Marketing copy for the product CHAPTER PAGES (`/produtos/<slug>`) — nothing else.
 *
 * Which products the site lists, their names, icons, public descriptions and status
 * (Disponível / Em breve / Lista de espera) are NOT here: they come from the dynamic catalog
 * (`GET /api/website/catalog`, core `website_catalog_service`, fed by `public.products`) —
 * see `lib/catalog.tsx`. This file only adds pt-BR/EN long-form copy for the few slugs that
 * have a dedicated page; a catalog product without an entry here simply has no chapter page
 * (its card shows no "Conhecer", and a waitlist product still offers "Avise-me").
 *
 * Adding a page for another product = a new entry here + its slug in `PRODUCT_ORDER`.
 * `content/defaults.ts` lists the same slugs as the chapter pages' visibility switches
 * (`WebsiteSettings.products[]`, edited in the admin).
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
