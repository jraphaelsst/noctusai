/**
 * WebsiteSettings — the single shape the website FE and core BE share.
 *
 * Mirrors `src/website/docs/15-api-contract.md` §2 exactly. This file is the
 * FE's copy of the contract type; the BE (FastAPI/Pydantic) owns its own
 * mirror. Any shape change goes through the tech-lead and bumps the contract
 * doc first (skill `noc-contract-first`).
 *
 * NOC-REMEDIATE[seed-promotion]: once a second product needs an admin-toggled
 * public settings document (N=2), lift the shape + fallback pattern into
 * `@noctusai/lib`.
 */

export type L10n = { pt: string; en: string };

export type ProductState = "disponivel" | "lista_de_espera" | "em_breve";

export interface WebsiteSettingsProduct {
  slug: string;
  visible: boolean;
  order: number;
  state: ProductState;
  tagline?: L10n;
}

export interface WebsiteTrustItem {
  key: string;
  icon: string;
  text: L10n;
  verified_by: string | null;
  verified_at: string | null;
}

export interface WebsiteSocialProofItem {
  kind: "logo" | "testimonial" | "metric";
  name: string;
  text?: L10n;
  image_url?: string;
  consent_ref: string;
}

export interface WebsiteFaqItem {
  q: L10n;
  a: L10n;
}

export interface WebsiteSettings {
  site_enabled: boolean;
  signup_enabled: boolean;
  whatsapp: {
    number_e164: string | null;
    default_message: L10n;
    float_enabled: boolean;
  };
  sections: {
    audiences: boolean;
    products: boolean;
    custom_builds: boolean;
    trust: boolean;
    social_proof: boolean;
    pricing: boolean;
    news: boolean;
    faq: boolean;
    hero_update_card: boolean;
  };
  products: WebsiteSettingsProduct[];
  trust_items: WebsiteTrustItem[];
  social_proof_items: WebsiteSocialProofItem[];
  faq: WebsiteFaqItem[];
  tracking: {
    plausible_domain: string | null;
    ga4_id: string | null;
    meta_pixel_id: string | null;
  };
}

/** The subset an anonymous client receives (contract §2 "Public subset"). */
export type PublicWebsiteSettings = Omit<WebsiteSettings, "trust_items" | "social_proof_items"> & {
  trust_items: Omit<WebsiteTrustItem, "verified_by">[];
  social_proof_items: Omit<WebsiteSocialProofItem, "consent_ref">[];
};

export type Locale = "pt-BR" | "en";
