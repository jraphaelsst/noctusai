import { useL10n, useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { whatsappUrl } from "../lib/whatsapp";
import { pathFor } from "../lib/routes";
import { PRODUCTS } from "../content/products";
import { CtaPair, type CtaAction } from "../components/CtaPair";
import { FaqAccordion } from "../components/FaqAccordion";
import { MarkedProduct } from "../lib/markers";
import NotFound from "./NotFound";

/**
 * Product page (07 §Subpage templates). A product whose slug is not
 * `visible` in the live settings 404s (contract §5 step 3) — mirrored here
 * client-side so a hydrated visitor sees the same outcome a fresh request
 * would get from the BE.
 */
export default function ProductPage({ slug }: { slug: string }) {
  const t = useT();
  const l10n = useL10n();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const copy = PRODUCTS[slug];
  const entry = settings.products.find((p) => p.slug === slug);

  if (!copy || !entry || !entry.visible) {
    return <NotFound />;
  }

  const wa = whatsappUrl(settings, locale, locale === "en" ? `Hi! I'd like to know more about ${copy.name}.` : `Olá! Quero saber mais sobre o ${copy.name}.`);
  const actions: CtaAction[] = [];
  if (entry.state === "disponivel") {
    actions.push({ label: t("cta.signup"), href: "https://core.noctusai.com/login?mode=signup", primary: true, eventName: "signup_start" });
    if (wa) actions.push({ label: t("cta.whatsapp"), href: wa, external: true, eventName: "whatsapp_click", eventProps: { product: slug } });
  } else if (entry.state === "lista_de_espera") {
    actions.push({ label: t("cta.waitlistShort"), href: `${pathFor("waitlist", locale)}?produto=${slug}`, primary: true });
  }

  return (
    <MarkedProduct slug={slug}>
      <div>
        <section className="nx-hero nx-band-inverse" style={{ minHeight: "50vh" }}>
          <div className="nx-container nx-hero-content">
            <span className="nx-eyebrow">{copy.name.toUpperCase()}</span>
            <h1>{entry.tagline ? l10n(entry.tagline) : l10n(copy.tagline)}</h1>
            <CtaPair actions={actions} />
          </div>
        </section>

        <section className="nx-section">
          <div className="nx-container">
            <div className="nx-chapter">
              <div>
                <h2>{locale === "en" ? "Capabilities" : "Recursos"}</h2>
                <ul>
                  {copy.capabilities.map((c, i) => (
                    <li key={i}>{l10n(c)}</li>
                  ))}
                </ul>
              </div>
              <div className="nx-panel" aria-hidden="true">
                <div className="nx-panel-header">
                  <span className="nx-panel-dot" />
                  <span>{l10n(copy.panel.heading)}</span>
                </div>
                {copy.panel.rows.map((row, i) => (
                  <div className="nx-panel-row" key={i}>
                    <span>{l10n(row)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {settings.sections.faq && settings.faq.length > 0 && (
          <section className="nx-section" id="faq">
            <div className="nx-container">
              <h2>{t("faq.title")}</h2>
              <FaqAccordion items={settings.faq} />
            </div>
          </section>
        )}

        <section className="nx-section nx-band-inverse">
          <div className="nx-container">
            <h2>{locale === "en" ? `Ready for ${copy.name}?` : `Pronto para usar o ${copy.name}?`}</h2>
            <CtaPair actions={actions} />
          </div>
        </section>
      </div>
    </MarkedProduct>
  );
}
