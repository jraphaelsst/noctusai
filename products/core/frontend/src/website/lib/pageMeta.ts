/**
 * Per-route `<head>` metadata (09 §Per-page SEO contract). Pure data, no
 * React — computed identically by `entry-server.tsx` (per-request during
 * the build-time prerender) and directly by `scripts/prerender-site.mjs`.
 *
 * JSON-LD scope, honestly stated: `Offer` nodes are NOT emitted anywhere
 * (home pricing section, `/precos`, product pages) because pricing numbers
 * only exist via the client-fetched `GET /api/website/plans` call — there is
 * no live DB access at build time, so a build-time JSON-LD `Offer` would
 * have to either omit `price` (invalid per schema.org) or fabricate one
 * (P7 violation). `NOC-REMEDIATE[content]`: add `Offer` JSON-LD once plans
 * can be resolved at build time (e.g. a build-time snapshot endpoint).
 * `FAQPage` is emitted by `FaqAccordion` itself (inline, in the body — valid
 * per schema.org, doesn't need to live in `<head>`).
 */
import { PRODUCTS, PRODUCT_ORDER } from "../content/products";
import { pathFor } from "./routes";
import type { Locale } from "../content/types";

export interface PageMeta {
  title: string;
  description: string;
  jsonLd: Record<string, unknown>[];
}

const SITE_NAME = "NoctusAI";
const ORIGIN = "https://noctusai.com";

function breadcrumb(items: Array<{ name: string; path: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: `${ORIGIN}${item.path}`,
    })),
  };
}

const COPY: Record<Locale, Record<string, { title: string; description: string }>> = {
  "pt-BR": {
    home: {
      title: "NoctusAI — IA que trabalha pela sua empresa",
      description: "Automação de WhatsApp, e-mail e redes com IA, o sistema operacional da sua agência, ou um projeto de IA sob medida para o seu negócio.",
    },
    "products-index": {
      title: "Produtos | NoctusAI",
      description: "Conheça os produtos NoctusAI: sistemas com IA prontos para usar, organizados por segmento.",
    },
    solutions: {
      title: "IA sob medida | NoctusAI",
      description: "Diagnóstico, protótipo, produção e evolução — projetos de IA construídos para o seu negócio.",
    },
    pricing: {
      title: "Preços | NoctusAI",
      description: "Planos e preços dos produtos NoctusAI, mensais ou anuais.",
    },
    contact: {
      title: "Contato | NoctusAI",
      description: "Fale com a NoctusAI pelo WhatsApp ou pelo formulário de contato.",
    },
    waitlist: {
      title: "Lista de espera | NoctusAI",
      description: "Entre na lista de espera para ser avisado quando o cadastro abrir.",
    },
    about: {
      title: "Sobre | NoctusAI",
      description: "Conheça a missão da NoctusAI e como construímos produtos com IA.",
    },
    "not-found": {
      title: "Página não encontrada | NoctusAI",
      description: "A página que você procura não existe ou foi movida.",
    },
  },
  en: {
    home: {
      title: "NoctusAI — AI that works for your business",
      description: "AI-driven WhatsApp, email and social automation, your agency's operating system, or a custom AI project for your business.",
    },
    "products-index": {
      title: "Products | NoctusAI",
      description: "Explore NoctusAI's products: ready-to-use AI systems, organized by industry.",
    },
    solutions: {
      title: "Custom AI builds | NoctusAI",
      description: "Diagnosis, prototype, production and evolution — AI projects built for your business.",
    },
    pricing: {
      title: "Pricing | NoctusAI",
      description: "Plans and pricing for NoctusAI products, monthly or yearly.",
    },
    contact: {
      title: "Contact | NoctusAI",
      description: "Talk to NoctusAI on WhatsApp or through the contact form.",
    },
    waitlist: {
      title: "Waitlist | NoctusAI",
      description: "Join the waitlist to be notified when sign-up opens.",
    },
    about: {
      title: "About | NoctusAI",
      description: "NoctusAI's mission and how we build AI products.",
    },
    "not-found": {
      title: "Page not found | NoctusAI",
      description: "The page you're looking for doesn't exist or has moved.",
    },
  },
};

export function getPageMeta(routeId: string, locale: Locale, product?: string): PageMeta {
  if (routeId.startsWith("product-") && product && PRODUCTS[product]) {
    const p = PRODUCTS[product];
    const tagline = locale === "en" ? p.tagline.en : p.tagline.pt;
    const title = `${p.name} | NoctusAI`;
    return {
      title,
      description: tagline,
      jsonLd: [
        {
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          name: p.name,
          applicationCategory: "BusinessApplication",
          operatingSystem: "Web",
          description: tagline,
          url: `${ORIGIN}${pathFor(`product-${p.slug}`, locale)}`,
        },
        breadcrumb([
          { name: SITE_NAME, path: pathFor("home", locale) },
          { name: locale === "en" ? "Products" : "Produtos", path: pathFor("products-index", locale) },
          { name: p.name, path: pathFor(`product-${p.slug}`, locale) },
        ]),
      ],
    };
  }

  const dict = COPY[locale][routeId] ?? COPY[locale]["not-found"];

  if (routeId === "home") {
    return {
      ...dict,
      jsonLd: [
        {
          "@context": "https://schema.org",
          "@type": "Organization",
          name: SITE_NAME,
          url: ORIGIN,
          sameAs: [],
        },
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: SITE_NAME,
          url: ORIGIN,
        },
      ],
    };
  }

  if (routeId === "products-index") {
    return {
      ...dict,
      jsonLd: [
        breadcrumb([
          { name: SITE_NAME, path: pathFor("home", locale) },
          { name: locale === "en" ? "Products" : "Produtos", path: pathFor("products-index", locale) },
        ]),
      ],
    };
  }

  if (["solutions", "pricing", "contact", "waitlist", "about"].includes(routeId)) {
    return {
      ...dict,
      jsonLd: [
        breadcrumb([
          { name: SITE_NAME, path: pathFor("home", locale) },
          { name: dict.title.split("|")[0].trim(), path: pathFor(routeId, locale) },
        ]),
      ],
    };
  }

  return { ...dict, jsonLd: [] };
}

export const CURATED_PRODUCT_SLUGS = PRODUCT_ORDER;
