import { useState } from "react";
import { CtaBand, FeatureGrid, Hero, ProductCatalogGrid, Steps, type LeadInterest } from "@noctusai/lib/marketing";
import { useL10n, useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { useCatalog } from "../lib/catalog";
import { toHeroChips, toOrganProducts } from "../lib/catalogView";
import { pathFor, EXTERNAL } from "../lib/routes";
import { PricingSection } from "../components/PricingSection";
import { SiteFaq } from "../components/SiteFaq";
import { SiteLeadForm } from "../components/SiteLeadForm";
import { MarkedSection } from "../lib/markers";
import { customBuildSteps } from "../content/customBuild";

/** Home (07 §Home). Sections are the seed landing organs; the products section is the live catalog. */
export default function Home() {
  const t = useT();
  const l10n = useL10n();
  const locale = useLocale();
  const en = locale === "en";
  const settings = useWebsiteSettings();
  const { products, isLoading, isRefreshing, isError, refetch } = useCatalog();
  const [interest, setInterest] = useState<LeadInterest | null>(null);

  const rows = products ?? [];
  const signup = settings.signup_enabled
    ? { label: t("cta.signup"), href: EXTERNAL.signup }
    : { label: t("cta.waitlist"), href: pathFor("waitlist", locale) };

  const verifiedTrustItems = settings.trust_items.filter((item) => item.verified_at);

  return (
    <>
      <Hero
        eyebrow="NOCTUSAI"
        title={en ? "AI that works for your business," : "IA que trabalha pela sua empresa,"}
        titleEmphasis={en ? "ready-made or custom-built." : "pronta ou sob medida."}
        lede={
          en
            ? "Ready-made products that answer WhatsApp leads and organise sales, AI agents you switch on and off, and projects built for your operation."
            : "Produtos prontos para atender leads no WhatsApp e organizar as vendas, agentes de IA que você liga e desliga quando quiser, e projetos feitos para a sua operação."
        }
        actions={[
          { label: signup.label, href: signup.href, variant: "primary" },
          { label: en ? "See the products" : "Ver os produtos", href: "#produtos", variant: "outline" },
        ]}
        chips={toHeroChips(rows, locale)}
        chipsLabel={en ? "Available products" : "Produtos disponíveis"}
      />

      {settings.sections.audiences && (
        <MarkedSection sectionKey="audiences">
          <FeatureGrid
            id="audiencias"
            eyebrow={en ? "Who it's for" : "Para quem é"}
            title={en ? "Choose where to start" : "Escolha por onde começar"}
            description={
              en
                ? "A ready-made product solves the day to day. A custom project solves what is only yours."
                : "Um produto pronto resolve o dia a dia. Um projeto sob medida resolve o que é só seu."
            }
            items={[
              {
                title: en ? "Small and mid-size businesses" : "Pequenas e médias empresas",
                description: en ? "Ready-made AI products to sell and serve better, no IT project." : "Produtos prontos com IA para vender e atender melhor, sem projeto de TI.",
                icon: "Store",
                cta: { label: en ? "See the products" : "Ver os produtos", href: "#produtos" },
              },
              {
                title: en ? "Companies with their own process" : "Empresas com processo próprio",
                description: en ? "An AI project designed for your operation and your data." : "Um projeto de IA desenhado para a sua operação e os seus dados.",
                icon: "Building2",
                cta: { label: en ? "See how it works" : "Ver como funciona", href: "#sob-medida" },
              },
              {
                title: en ? "Freelancers" : "Autônomos",
                description: en ? "Start free and change plan when the business grows." : "Comece grátis e mude de plano quando o negócio crescer.",
                icon: "User",
                cta: { label: en ? "See pricing" : "Ver os preços", href: pathFor("pricing", locale) },
              },
            ]}
          />
        </MarkedSection>
      )}

      {settings.sections.products && (
        <MarkedSection sectionKey="products">
          <ProductCatalogGrid
            id="produtos"
            eyebrow={en ? "Products" : "Produtos"}
            title={en ? "NoctusAI products" : "Produtos NoctusAI"}
            description={
              en
                ? "The available ones you use today with the same account. The others are being built or paused: join the list and we tell you when they open."
                : "Os disponíveis você usa hoje com a mesma conta. Os outros estão em construção ou em pausa: entre na lista e avisamos quando abrirem."
            }
            products={toOrganProducts(rows, locale)}
            isLoading={isLoading}
            isError={isError}
            onRetry={refetch}
            onWaitlist={(slug) => {
              const p = rows.find((r) => r.slug === slug);
              if (p) setInterest({ slug: p.slug, nome: p.nome });
            }}
            emptyAction={{ label: en ? "Talk to us" : "Falar com a gente", href: pathFor("contact", locale) }}
          />
          {isRefreshing && <p className="sr-only" role="status">{en ? "Updating the product list" : "Atualizando a lista de produtos"}</p>}
        </MarkedSection>
      )}

      {settings.sections.custom_builds && (
        <MarkedSection sectionKey="custom_builds">
          <Steps
            id="sob-medida"
            eyebrow={en ? "Custom AI" : "IA sob medida"}
            title={en ? "A project built for your business" : "Um projeto construído para o seu negócio"}
            description={
              en
                ? "You see and use a version with your data before we decide what to build."
                : "Você vê e usa uma versão com os seus dados antes de decidirmos o que construir."
            }
            steps={customBuildSteps(en)}
          />
        </MarkedSection>
      )}

      <SiteLeadForm
        source="brief"
        id="contato-form"
        eyebrow={en ? "Talk to us" : "Fale com a gente"}
        title={en ? "Tell us what you need" : "Conte o que você precisa"}
        description={
          en
            ? "Every message reaches the NoctusAI team, and a person answers on WhatsApp during business hours."
            : "Cada mensagem chega à equipe da NoctusAI, e uma pessoa responde pelo WhatsApp em horário comercial."
        }
        heading={en ? "Tell us about your project" : "Conte sobre o seu projeto"}
        interest={interest}
        onInterestClear={() => setInterest(null)}
      />

      {settings.sections.trust && verifiedTrustItems.length > 0 && (
        // Empty-state guard: a heading with nothing under it reads as unfinished, so the section
        // renders only once at least one claim is human-verified (P7: nothing unverified).
        <MarkedSection sectionKey="trust">
          <section className="nx-section" id="confianca">
            <div className="nx-container">
              <span className="nx-eyebrow">{en ? "Why NoctusAI" : "Por que a NoctusAI"}</span>
              <h2>{en ? "What's verifiably true today" : "O que é verdade hoje"}</h2>
              <div className="nx-trust-grid">
                {verifiedTrustItems.map((item) => (
                  <div className="nx-trust-item" key={item.key}>
                    <span>{l10n(item.text)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </MarkedSection>
      )}

      {settings.sections.social_proof && settings.social_proof_items.length > 0 && (
        <MarkedSection sectionKey="social_proof">
          <section className="nx-section" id="prova-social">
            <div className="nx-container">
              <span className="nx-eyebrow">{en ? "Trusted by" : "Quem confia"}</span>
              <h2>{en ? "Trusted by" : "Quem confia"}</h2>
              <div className="nx-trust-grid">
                {settings.social_proof_items.map((item, i) => (
                  <div key={i}>{item.text ? l10n(item.text) : item.name}</div>
                ))}
              </div>
            </div>
          </section>
        </MarkedSection>
      )}

      <PricingSection />

      {settings.sections.faq && settings.faq.length > 0 && (
        <MarkedSection sectionKey="faq">
          <SiteFaq title={t("faq.title")} items={settings.faq} />
        </MarkedSection>
      )}

      <CtaBand
        id="cta-final"
        title={en ? "Start with a ready-made product or tell us your case." : "Comece por um produto pronto ou conte o seu caso."}
        description={en ? "One account works for every NoctusAI product." : "A conta é a mesma para todos os produtos NoctusAI."}
        actions={[
          { label: signup.label, href: signup.href, variant: "primary" },
          { label: en ? "Tell us my case" : "Contar o meu caso", href: "#contato-form", variant: "outline" },
        ]}
      />
    </>
  );
}
