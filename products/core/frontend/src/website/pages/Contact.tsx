import { PageHeading } from "../components/PageHeading";
import { useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { whatsappUrl } from "../lib/whatsapp";
import { SiteLeadForm } from "../components/SiteLeadForm";

/** Contato — WhatsApp primary, short form, no booking (07 §Subpage templates). */
export default function Contact() {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const wa = whatsappUrl(settings, locale);
  const en = locale === "en";

  return (
    <>
      <PageHeading>{en ? "Contact" : "Contato"}</PageHeading>
      <SiteLeadForm
        source="contact"
        id="contato"
        eyebrow={en ? "Contact" : "Contato"}
        title={en ? "Talk to us" : "Fale com a gente"}
        description={en ? "Send us a message and we'll get back to you." : "Envie uma mensagem e retornaremos em breve."}
        heading={en ? "Send a message" : "Envie uma mensagem"}
      />
      {wa && (
        <p className="mx-auto w-full max-w-6xl px-4 pb-12 sm:px-6">
          <a href={wa} target="_blank" rel="noopener noreferrer" className="nx-btn nx-btn-primary">
            {t("cta.whatsapp")}
          </a>
        </p>
      )}
    </>
  );
}
