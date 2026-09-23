import { useLocale, useT } from "../lib/i18n";
import { PricingSection } from "../components/PricingSection";
import { FaqAccordion } from "../components/FaqAccordion";
import { useWebsiteSettings } from "../lib/settings";

/** `/precos` (07 §Subpage templates). */
export default function Pricing() {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();

  return (
    <div>
      <section className="nx-section">
        <div className="nx-container">
          <span className="nx-eyebrow">{locale === "en" ? "PRICING" : "PREÇOS"}</span>
          <h1>{locale === "en" ? "Simple, transparent pricing" : "Preços simples e transparentes"}</h1>
        </div>
      </section>
      <PricingSection full />
      {settings.sections.faq && settings.faq.length > 0 && (
        <section className="nx-section">
          <div className="nx-container">
            <h2>{t("faq.title")}</h2>
            <FaqAccordion items={settings.faq} sectionId="pricing-faq" />
          </div>
        </section>
      )}
    </div>
  );
}
