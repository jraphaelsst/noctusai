import { useL10n, useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { whatsappUrl } from "../lib/whatsapp";
import { pathFor } from "../lib/routes";
import { PRODUCTS } from "../content/products";
import { CtaPair, type CtaAction } from "../components/CtaPair";
import { AudienceCard } from "../components/AudienceCard";
import { ProductChapter } from "../components/ProductChapter";
import { ArchitectureDiagram } from "../components/ArchitectureDiagram";
import { FaqAccordion } from "../components/FaqAccordion";
import { PricingSection } from "../components/PricingSection";
import { LeadForm } from "../components/LeadForm";
import { HeroScene, type HeroModule } from "../hero3d/HeroScene";
import { MarkedSection } from "../lib/markers";

/** Home (07 §Home — 11 switchable sections + hero/header/footer/closing). */
export default function Home() {
  const t = useT();
  const l10n = useL10n();
  const locale = useLocale();
  const settings = useWebsiteSettings();

  const visibleProducts = settings.products
    .filter((p) => p.visible && PRODUCTS[p.slug])
    .sort((a, b) => a.order - b.order);

  const heroModules: HeroModule[] = visibleProducts.map((p) => ({
    slug: p.slug,
    label: PRODUCTS[p.slug]?.name ?? p.slug,
    href: pathFor(`product-${p.slug}`, locale),
  }));

  const wa = whatsappUrl(settings, locale);
  const heroActions: CtaAction[] = [];
  if (wa) heroActions.push({ label: t("cta.whatsapp"), href: wa, primary: true, external: true, eventName: "whatsapp_click", eventProps: { section: "hero" } });
  heroActions.push(
    settings.signup_enabled
      ? { label: t("cta.signup"), href: "https://core.noctusai.com/login?mode=signup", primary: !wa, eventName: "signup_start" }
      : { label: t("cta.waitlist"), href: pathFor("waitlist", locale), primary: !wa },
  );

  const closingWa = wa;

  return (
    <>
      <section className="nx-hero nx-band-inverse">
        <HeroScene modules={heroModules} />
        <div className="nx-container nx-hero-content">
          <span className="nx-eyebrow" style={{ color: "var(--nx-cyan-6, #22d3ee)" }}>NOCTUSAI</span>
          <h1 className="nx-display">
            {locale === "en" ? (
              <>
                AI that works for your <span className="nx-accent-word">business</span> — ready-made or custom built.
              </>
            ) : (
              <>
                IA que trabalha pela sua <span className="nx-accent-word">empresa</span> — com produtos prontos ou sob medida.
              </>
            )}
          </h1>
          <p className="nx-subhead">
            {locale === "en"
              ? "AI systems for real estate, clinics and finance — and AI projects built for your business."
              : "Sistemas com IA para imobiliárias, clínicas e finanças — e projetos de IA construídos para o seu negócio."}
          </p>
          <CtaPair actions={heroActions} />
          {heroModules.length > 0 && (
            <ul className="nx-hero-modules">
              {heroModules.map((m) => (
                <li key={m.slug}>
                  <a href={m.href}>{m.label}</a>
                </li>
              ))}
            </ul>
          )}
        </div>
        {settings.sections.hero_update_card && (
          <div className="nx-hero-update-card">
            {locale === "en" ? "Latest update" : "Última novidade"}
          </div>
        )}
      </section>

      {settings.sections.audiences && (
        <MarkedSection sectionKey="audiences">
          <section className="nx-section" id="audiencias">
            <div className="nx-container">
              <span className="nx-eyebrow">{locale === "en" ? "WHO IT'S FOR" : "PARA QUEM É"}</span>
              <div className="nx-audience-grid">
                <AudienceCard
                  title={locale === "en" ? "Small businesses" : "Pequenas empresas"}
                  benefit={locale === "en" ? "Ready-made AI products for your day to day." : "Produtos prontos com IA para o seu dia a dia."}
                  ctaLabel={t("cta.seeProduct")}
                  ctaHref={pathFor("products-index", locale)}
                />
                <AudienceCard
                  title={locale === "en" ? "Enterprises" : "Empresas"}
                  benefit={locale === "en" ? "A custom AI project, built for your architecture." : "Um projeto de IA sob medida para a sua operação."}
                  ctaLabel={t("nav.solutions")}
                  ctaHref={pathFor("solutions", locale)}
                />
                <AudienceCard
                  title={locale === "en" ? "Developers" : "Desenvolvedores"}
                  benefit={locale === "en" ? "APIs and integrations built the seed-first way." : "APIs e integrações construídas seed-first."}
                  ctaLabel={t("cta.signup")}
                  ctaHref="https://core.noctusai.com/login?mode=signup"
                />
                <AudienceCard
                  title={locale === "en" ? "Freelancers & solo founders" : "Autônomos & solo founders"}
                  benefit={locale === "en" ? "Start free, grow when you need to." : "Comece grátis, cresça quando precisar."}
                  ctaLabel={t("cta.seePricing")}
                  ctaHref={pathFor("pricing", locale)}
                />
              </div>
            </div>
          </section>
        </MarkedSection>
      )}

      {settings.sections.products && visibleProducts.length > 0 && (
        <MarkedSection sectionKey="products">
          <section className="nx-section" id="produtos">
            <div className="nx-container">
              <span className="nx-eyebrow">{locale === "en" ? "PRODUCTS" : "PRODUTOS"}</span>
              <h2>{locale === "en" ? "Live products, in DOM." : "Produtos ao vivo, em DOM."}</h2>
              {visibleProducts.map((p) => {
                const copy = PRODUCTS[p.slug];
                if (!copy) return null;
                return (
                  <ProductChapter
                    key={p.slug}
                    copy={copy}
                    state={p.state}
                    productHref={pathFor(`product-${p.slug}`, locale)}
                    whatsappHref={whatsappUrl(settings, locale, locale === "en" ? `Hi! I'd like to know more about ${copy.name}.` : `Olá! Quero saber mais sobre o ${copy.name}.`)}
                    tagline={p.tagline}
                  />
                );
              })}
            </div>
          </section>
        </MarkedSection>
      )}

      {settings.sections.custom_builds && (
        <MarkedSection sectionKey="custom_builds">
          <section className="nx-section nx-band-inverse" id="sob-medida">
            <div className="nx-container">
              <span className="nx-eyebrow">{locale === "en" ? "CUSTOM AI" : "IA SOB MEDIDA"}</span>
              <h2>{locale === "en" ? "A project built for your business." : "Um projeto construído para o seu negócio."}</h2>
              <ol className="nx-mono">
                <li>01 {locale === "en" ? "Diagnosis" : "Diagnóstico"}</li>
                <li>02 {locale === "en" ? "Prototype" : "Protótipo"}</li>
                <li>03 {locale === "en" ? "Production" : "Produção"}</li>
                <li>04 {locale === "en" ? "Evolution" : "Evolução"}</li>
              </ol>
              <ArchitectureDiagram locale={locale} />
              <h3 style={{ marginTop: 40 }}>{locale === "en" ? "Tell us about your project" : "Conte sobre o seu projeto"}</h3>
              <LeadForm variant="brief" />
            </div>
          </section>
        </MarkedSection>
      )}

      {settings.sections.trust && (
        <MarkedSection sectionKey="trust">
          <section className="nx-section" id="confianca">
            <div className="nx-container">
              <span className="nx-eyebrow">{locale === "en" ? "WHY NOCTUSAI" : "POR QUE A NOCTUSAI"}</span>
              <div className="nx-trust-grid">
                {settings.trust_items
                  .filter((item) => item.verified_at)
                  .map((item) => (
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
              <span className="nx-eyebrow">{locale === "en" ? "TRUSTED BY" : "QUEM CONFIA"}</span>
              <div className="nx-trust-grid">
                {settings.social_proof_items.map((item, i) => (
                  <div key={i}>
                    {item.text ? l10n(item.text) : item.name}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </MarkedSection>
      )}

      <PricingSection />

      {settings.sections.faq && settings.faq.length > 0 && (
        <MarkedSection sectionKey="faq">
          <section className="nx-section" id="faq">
            <div className="nx-container">
              <h2>{t("faq.title")}</h2>
              <FaqAccordion items={settings.faq} />
            </div>
          </section>
        </MarkedSection>
      )}

      <section className="nx-section nx-band-inverse" id="cta-final">
        <div className="nx-container">
          <h2 className="nx-display" style={{ fontSize: "clamp(32px, 5vw, 64px)" }}>
            {locale === "en" ? "Ready to work with AI?" : "Pronto para trabalhar com IA?"}
          </h2>
          <CtaPair
            actions={
              closingWa
                ? [
                    { label: t("cta.whatsapp"), href: closingWa, primary: true, external: true, eventName: "whatsapp_click", eventProps: { section: "closing" } },
                    settings.signup_enabled
                      ? { label: t("cta.signup"), href: "https://core.noctusai.com/login?mode=signup" }
                      : { label: t("cta.waitlist"), href: pathFor("waitlist", locale) },
                  ]
                : [
                    settings.signup_enabled
                      ? { label: t("cta.signup"), href: "https://core.noctusai.com/login?mode=signup", primary: true }
                      : { label: t("cta.waitlist"), href: pathFor("waitlist", locale), primary: true },
                  ]
            }
          />
        </div>
      </section>
    </>
  );
}
