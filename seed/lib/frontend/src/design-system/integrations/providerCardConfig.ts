/**
 * Provider card config registry.
 *
 * Each provider config describes HOW to display an IntegrationAccount:
 *   - `primary(account)` — the headline text (e.g. channel title for YouTube)
 *   - `secondary(account)` — array of {label, value} secondary fields
 *   - `editableFields` — which fields appear in the inline-edit form
 *   - `modalSections(account)` — richer sections for the detail modal
 *
 * Adding a new provider: add a new entry to PROVIDER_CARD_CONFIG.
 * The card component reads the registry; zero card-code changes needed.
 */
import * as React from "react";
import { Youtube, Facebook, Instagram } from "lucide-react";
import { WhatsAppIcon } from "./WhatsAppIcon";
import type { IntegrationAccount, SecondaryField, ModalSection } from "./types";

export interface EditableField {
  /** The key in `account` (or `channel_info` / `metadata`) to edit. */
  key: string;
  /** Human-readable label shown next to the input. */
  label: string;
  /** Input type (default: "text"). */
  inputType?: "text" | "password" | "url";
  /** Which bag this key lives in — top-level fields vs nested bags. */
  bag: "root" | "channel_info" | "metadata";
  placeholder?: string;
}

export interface ProviderCardConfig {
  /** Matches `IntegrationAccount.provider`. */
  provider: string;
  /** Human-readable provider name shown in the card header. */
  displayName: string;
  /**
   * Icon component rendered in the card's circular badge.
   * Accepts any React component that takes SVG props (className, etc.) —
   * compatible with both Lucide icons and custom brand SVG components
   * such as WhatsAppIcon.
   */
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  /**
   * Optional accent CSS class applied to the provider icon wrapper
   * (e.g. "text-red-500" for YouTube brand red).
   */
  accent?: string;
  /**
   * Returns the primary/headline text for the account.
   * Typically channel title, session name, or fallback to account_label.
   */
  primary(account: IntegrationAccount): string;
  /**
   * Returns the list of secondary fields displayed on the card face.
   * Keep to ≤4 items — the card layout compresses beyond that.
   */
  secondary(account: IntegrationAccount): SecondaryField[];
  /**
   * Fields that appear as inputs in the inline-edit form.
   * Always include account_label; add provider-specific credentials here.
   */
  editableFields: EditableField[];
  /**
   * Returns sections for the detail modal.
   * May include all channel_info + metadata — the modal has more space.
   */
  modalSections(account: IntegrationAccount): ModalSection[];
  /**
   * The provider's own dashboard route (e.g. "/youtube") — where a click on
   * the card body deep-links the user, with the account pre-selected via
   * `useActiveAccountStore`. Providers without a dedicated dashboard page
   * (e.g. gmail, google_drive, n8n) omit this field; the card falls back to
   * opening the detail modal on body click instead.
   */
  dashboardRoute?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function str(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

function fmtCount(n: unknown): string {
  if (n === null || n === undefined) return "—";
  const num = typeof n === "number" ? n : parseInt(String(n), 10);
  if (isNaN(num)) return "—";
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return String(num);
}

// ── YouTube ────────────────────────────────────────────────────────────────

const youtubeConfig: ProviderCardConfig = {
  provider: "youtube",
  displayName: "YouTube",
  icon: Youtube,
  accent: "text-red-500",
  dashboardRoute: "/youtube",

  primary(account) {
    const title = account.channel_info["title"];
    return typeof title === "string" && title.trim()
      ? title
      : account.account_label;
  },

  secondary(account) {
    const ci = account.channel_info;
    return [
      {
        label: "Inscritos",
        value: fmtCount(ci["subscriber_count"]),
      },
      {
        label: "Vídeos",
        value: fmtCount(ci["video_count"]),
      },
      {
        label: "Visualizações",
        value: fmtCount(ci["view_count"]),
      },
    ];
  },

  editableFields: [
    {
      key: "account_label",
      label: "Rótulo da conta",
      bag: "root",
      placeholder: "Ex: Canal principal",
    },
  ],

  modalSections(account) {
    const ci = account.channel_info;
    return [
      {
        title: "Canal",
        fields: [
          { label: "ID do canal", value: str(ci["channel_id"]) },
          { label: "Título", value: str(ci["title"]) },
          { label: "Inscritos", value: fmtCount(ci["subscriber_count"]) },
          { label: "Vídeos", value: fmtCount(ci["video_count"]) },
          { label: "Visualizações", value: fmtCount(ci["view_count"]) },
        ],
      },
      {
        title: "Conta",
        fields: [
          { label: "Rótulo", value: account.account_label },
          { label: "Client ID", value: str(account.client_id) },
          {
            label: "Padrão",
            value: account.is_default ? "Sim" : "Não",
          },
          {
            label: "Último sincronismo",
            value: account.last_synced_at
              ? new Date(account.last_synced_at).toLocaleString("pt-BR")
              : "—",
          },
        ],
      },
    ];
  },
};

// ── Meta (Facebook Pages / Instagram) ───────────────────────────────────────
// Per-client OAuth account; channel_info carries whatever the connect flow
// probed (page or IG business account) — kept conservative since the shape
// is provider-probed, not a fixed schema like YouTube's channel stats.

const metaConfig: ProviderCardConfig = {
  provider: "meta",
  displayName: "Meta",
  icon: Facebook,
  accent: "text-blue-600",
  dashboardRoute: "/meta",

  primary(account) {
    const title = account.channel_info["title"];
    return typeof title === "string" && title.trim()
      ? title
      : account.account_label;
  },

  secondary(account) {
    const ci = account.channel_info;
    const fields: SecondaryField[] = [];
    if (typeof ci["channel_id"] === "string" && ci["channel_id"]) {
      fields.push({ label: "ID da conta", value: str(ci["channel_id"]) });
    }
    return fields;
  },

  editableFields: [
    {
      key: "account_label",
      label: "Rótulo da conta",
      bag: "root",
      placeholder: "Ex: Página principal",
    },
  ],

  modalSections(account) {
    const ci = account.channel_info;
    return [
      {
        title: "Conta Meta",
        fields: [
          { label: "ID da conta", value: str(ci["channel_id"]) },
          { label: "Nome", value: str(ci["title"]) },
        ],
      },
      {
        title: "Conta",
        fields: [
          { label: "Rótulo", value: account.account_label },
          { label: "Client ID", value: str(account.client_id) },
          {
            label: "Padrão",
            value: account.is_default ? "Sim" : "Não",
          },
          {
            label: "Último sincronismo",
            value: account.last_synced_at
              ? new Date(account.last_synced_at).toLocaleString("pt-BR")
              : "—",
          },
        ],
      },
    ];
  },
};

// ── Instagram (Instagram-Login model) ──────────────────────────────────────
// 🔴 A DISTINCT provider from `meta`, not a sub-case of it. `meta` is the
// Facebook-Login model (Page token, graph.facebook.com, needs a linked FB
// Page); this is Instagram Business Login — its own Instagram App ID/Secret,
// token chain through api.instagram.com → graph.instagram.com, and NO Facebook
// Page anywhere. Crossing the two credential sets is the documented live
// failure (memory `reference_meta_ig_dm_facebook_login_model`), so they get
// separate cards with separate labels.
//
// `channel_info` carries `{channel_id, title}` written by the OAuth callback
// from `/me` (`id`, `username`), plus `metadata.model = "instagram_login"`.

const instagramConfig: ProviderCardConfig = {
  provider: "instagram",
  displayName: "Instagram",
  icon: Instagram,
  accent: "text-pink-600",
  dashboardRoute: "/meta",

  primary(account) {
    const title = account.channel_info["title"];
    return typeof title === "string" && title.trim()
      ? title
      : account.account_label;
  },

  secondary(account) {
    const ci = account.channel_info;
    const fields: SecondaryField[] = [];
    if (typeof ci["channel_id"] === "string" && ci["channel_id"]) {
      // The IG-scoped user id — the same identity the DM read path compares
      // against a message's sender to derive inbound/outbound.
      fields.push({ label: "ID da conta", value: str(ci["channel_id"]) });
    }
    return fields;
  },

  editableFields: [
    {
      key: "account_label",
      label: "Rótulo da conta",
      bag: "root",
      placeholder: "Ex: @cliente_principal",
    },
  ],

  modalSections(account) {
    const ci = account.channel_info;
    return [
      {
        title: "Conta do Instagram",
        fields: [
          { label: "Usuário", value: str(ci["title"]) },
          { label: "ID da conta", value: str(ci["channel_id"]) },
          {
            label: "Modelo",
            // Stated explicitly so an operator can tell at a glance which
            // credential family this row belongs to.
            value: "Instagram Login (sem página do Facebook)",
          },
        ],
      },
      {
        title: "Conta",
        fields: [
          { label: "Rótulo", value: account.account_label },
          { label: "Client ID", value: str(account.client_id) },
          { label: "Padrão", value: account.is_default ? "Sim" : "Não" },
          {
            label: "Último sincronismo",
            value: account.last_synced_at
              ? new Date(account.last_synced_at).toLocaleString("pt-BR")
              : "—",
          },
        ],
      },
    ];
  },
};

// ── WhatsApp (WAHA) ────────────────────────────────────────────────────────
// Structural config: compiles and renders WAHA fields.
// Live session/QR data is wired by the social-wiring app slice on top.

const whatsappConfig: ProviderCardConfig = {
  provider: "whatsapp",
  displayName: "WhatsApp",
  icon: WhatsAppIcon,
  accent: "text-green-500",
  // /whatsapp-chat is the unlisted-but-live chat page (App.tsx) — the Chat
  // tab inside ClienteModal is the primary UX, but the standalone page
  // remains the deep-link target for a card-body click outside the modal.
  dashboardRoute: "/whatsapp-chat",

  primary(account) {
    const session = account.channel_info["session"];
    if (typeof session === "string" && session.trim()) return session;
    const phone = account.channel_info["phone"];
    if (typeof phone === "string" && phone.trim()) return phone;
    return account.account_label;
  },

  secondary(account) {
    const ci = account.channel_info;
    const fields: SecondaryField[] = [];
    if (ci["session"]) {
      fields.push({ label: "Sessão", value: str(ci["session"]) });
    }
    if (ci["phone"]) {
      fields.push({ label: "Telefone", value: str(ci["phone"]) });
    }
    // webhook_url is intentionally omitted from the card face (long URL clutters
    // the compact card). It remains accessible in the detail modal via modalSections().
    return fields;
  },

  editableFields: [
    {
      key: "account_label",
      label: "Rótulo da conta",
      bag: "root",
      placeholder: "Ex: Atendimento",
    },
    {
      key: "webhook_url",
      label: "URL do Webhook",
      bag: "channel_info",
      inputType: "url",
      placeholder: "https://...",
    },
  ],

  modalSections(account) {
    const ci = account.channel_info;
    return [
      {
        title: "Conexão",
        fields: [
          { label: "Sessão", value: str(ci["session"]) },
          { label: "Telefone", value: str(ci["phone"]) },
          { label: "Webhook", value: str(ci["webhook_url"]) },
        ],
      },
      {
        title: "Conta",
        fields: [
          { label: "Rótulo", value: account.account_label },
          {
            label: "Padrão",
            value: account.is_default ? "Sim" : "Não",
          },
          {
            label: "Último sincronismo",
            value: account.last_synced_at
              ? new Date(account.last_synced_at).toLocaleString("pt-BR")
              : "—",
          },
        ],
      },
    ];
  },
};

// ── Registry ───────────────────────────────────────────────────────────────

export const PROVIDER_CARD_CONFIG: Record<string, ProviderCardConfig> = {
  youtube: youtubeConfig,
  whatsapp: whatsappConfig,
  meta: metaConfig,
  instagram: instagramConfig,
};

/**
 * Look up a provider config by provider string.
 * Returns `undefined` when the provider is not in the registry
 * (the card will render a generic fallback).
 */
export function getProviderConfig(
  provider: string,
): ProviderCardConfig | undefined {
  return PROVIDER_CARD_CONFIG[provider.toLowerCase()];
}
