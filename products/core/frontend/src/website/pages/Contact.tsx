import { useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { whatsappUrl } from "../lib/whatsapp";
import { LeadForm } from "../components/LeadForm";

/** Contato — WhatsApp primary, short form, no booking (07 §Subpage templates). */
export default function Contact() {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const wa = whatsappUrl(settings, locale);

  return (
    <div className="nx-container nx-section">
      <span className="nx-eyebrow">{locale === "en" ? "CONTACT" : "CONTATO"}</span>
      <h1>{locale === "en" ? "Talk to us" : "Fale com a gente"}</h1>
      {wa ? (
        <p>
          <a href={wa} target="_blank" rel="noopener noreferrer" className="nx-btn nx-btn-primary">
            {t("cta.whatsapp")}
          </a>
        </p>
      ) : (
        <p>{locale === "en" ? "Send us a message and we'll get back to you." : "Envie uma mensagem e retornaremos em breve."}</p>
      )}
      <LeadForm variant="contact" />
    </div>
  );
}
