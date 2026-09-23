import { useLocale, useT } from "../lib/i18n";
import { ArchitectureDiagram } from "../components/ArchitectureDiagram";
import { LeadForm } from "../components/LeadForm";
import { FaqAccordion } from "../components/FaqAccordion";
import { useWebsiteSettings } from "../lib/settings";

/** Soluções / IA sob medida (07 §Subpage templates — Home §4 expanded). */
export default function Solutions() {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();

  return (
    <div>
      <section className="nx-section nx-band-inverse">
        <div className="nx-container">
          <span className="nx-eyebrow">{locale === "en" ? "CUSTOM AI" : "IA SOB MEDIDA"}</span>
          <h1>{locale === "en" ? "A project built for your business" : "Um projeto construído para o seu negócio"}</h1>
          <p>
            {locale === "en"
              ? "From diagnosis to production, we build AI systems on the same seed-first foundation every NoctusAI product runs on."
              : "Do diagnóstico à produção, construímos sistemas de IA sobre a mesma base seed-first que roda todos os produtos NoctusAI."}
          </p>
        </div>
      </section>

      <section className="nx-section">
        <div className="nx-container">
          <ol className="nx-mono">
            <li>01 {locale === "en" ? "Diagnosis" : "Diagnóstico"}</li>
            <li>02 {locale === "en" ? "Prototype" : "Protótipo"}</li>
            <li>03 {locale === "en" ? "Production" : "Produção"}</li>
            <li>04 {locale === "en" ? "Evolution" : "Evolução"}</li>
          </ol>
          <ArchitectureDiagram locale={locale} />
        </div>
      </section>

      <section className="nx-section" id="brief">
        <div className="nx-container">
          <h2>{locale === "en" ? "Tell us about your project" : "Conte sobre o seu projeto"}</h2>
          <LeadForm variant="brief" />
        </div>
      </section>

      {settings.sections.faq && settings.faq.length > 0 && (
        <section className="nx-section">
          <div className="nx-container">
            <h2>{t("faq.title")}</h2>
            <FaqAccordion items={settings.faq} />
          </div>
        </section>
      )}
    </div>
  );
}
