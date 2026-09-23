/**
 * The single source of truth for `WebsiteSettings` defaults.
 *
 * The prerender step (`scripts/prerender-site.mjs`) emits this object
 * verbatim as `dist/_site/settings.defaults.json`. The core BE reads that
 * file as "version 0" when `website_settings` has no rows yet (contract §2:
 * "the BE never hardcodes defaults"). It is ALSO what every prerendered page
 * is built against, so the static HTML and the runtime fallback always agree.
 *
 * Launch values (owner decisions, contract §0):
 *  - `whatsapp.number_e164` starts `null` — the admin sets it. Every WhatsApp
 *    CTA in this codebase must degrade to the waitlist/contact form when null.
 *  - `social_proof`, `news`, `hero_update_card` start OFF (no real proof/news
 *    yet — P7 "honest proof before social proof").
 *  - `trust_items[].verified_at` starts `null` so the section renders empty
 *    until a human verifies each claim (nothing here is claimed unverified).
 */
import { PRODUCT_ORDER } from "./products";
import type { WebsiteSettings, WebsiteSettingsProduct } from "./types";

const DEFAULT_PRODUCTS: WebsiteSettingsProduct[] = PRODUCT_ORDER.map((slug, i) => ({
  slug,
  visible: true,
  order: i,
  state: slug === "social-wiring" ? "disponivel" : "lista_de_espera",
}));

export const defaultSettings: WebsiteSettings = {
  site_enabled: true,
  signup_enabled: true,
  whatsapp: {
    number_e164: null,
    default_message: {
      pt: "Olá! Vim pelo site e quero saber mais sobre a NoctusAI.",
      en: "Hi! I came from the website and I'd like to know more about NoctusAI.",
    },
    float_enabled: true,
  },
  sections: {
    audiences: true,
    products: true,
    custom_builds: true,
    trust: true,
    social_proof: false,
    pricing: true,
    news: false,
    faq: true,
    hero_update_card: false,
  },
  products: DEFAULT_PRODUCTS,
  trust_items: [
    {
      key: "brazil-hosted",
      icon: "MapPin",
      text: { pt: "Dados hospedados no Brasil", en: "Data hosted in Brazil" },
      verified_by: null,
      verified_at: null,
    },
    {
      key: "lgpd",
      icon: "ShieldCheck",
      text: { pt: "Conforme a LGPD", en: "LGPD compliant" },
      verified_by: null,
      verified_at: null,
    },
    {
      key: "no-training",
      icon: "Lock",
      text: { pt: "Seus dados não treinam modelos de terceiros", en: "Your data never trains third-party models" },
      verified_by: null,
      verified_at: null,
    },
    {
      key: "integrations",
      icon: "Plug",
      text: { pt: "Integra com o que você já usa", en: "Integrates with what you already use" },
      verified_by: null,
      verified_at: null,
    },
  ],
  social_proof_items: [],
  faq: [
    {
      q: { pt: "Quanto custa?", en: "How much does it cost?" },
      a: {
        pt: "Cada produto tem seus próprios planos, exibidos na página de Preços. Alguns ainda estão em lista de espera.",
        en: "Each product has its own plans, shown on the Pricing page. Some are still on the waitlist.",
      },
    },
    {
      q: { pt: "Meus dados ficam seguros e onde?", en: "Are my data safe, and where do they live?" },
      a: {
        pt: "Os dados ficam hospedados no Brasil, com controle de acesso por organização e conformidade com a LGPD.",
        en: "Data is hosted in Brazil, with per-organization access control and LGPD compliance.",
      },
    },
    {
      q: { pt: "Como funciona um projeto sob medida?", en: "How does a custom project work?" },
      a: {
        pt: "Diagnóstico, protótipo, produção e evolução contínua — veja o processo completo em \"IA sob medida\".",
        en: "Diagnosis, prototype, production and continuous evolution — see the full process on \"Custom builds\".",
      },
    },
    {
      q: { pt: "Como falo com a equipe?", en: "How do I talk to the team?" },
      a: {
        pt: "Pelo WhatsApp, quando o canal estiver ativo, ou pelo formulário de contato.",
        en: "Via WhatsApp, when the channel is active, or through the contact form.",
      },
    },
    {
      q: { pt: "Posso cancelar quando quiser?", en: "Can I cancel anytime?" },
      a: {
        pt: "Sim, sem fidelidade — o cancelamento é feito diretamente nas configurações da sua conta.",
        en: "Yes, no lock-in — cancel any time from your account settings.",
      },
    },
  ],
  tracking: {
    plausible_domain: null,
    ga4_id: null,
    meta_pixel_id: null,
  },
};
