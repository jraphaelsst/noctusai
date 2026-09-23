import { useLocale } from "../lib/i18n";
import { LeadForm } from "../components/LeadForm";

/** Lista de espera (07 §Subpage templates). */
export default function Waitlist() {
  const locale = useLocale();
  return (
    <div className="nx-container nx-section">
      <span className="nx-eyebrow">{locale === "en" ? "WAITLIST" : "LISTA DE ESPERA"}</span>
      <h1>{locale === "en" ? "Join the waitlist" : "Entre na lista de espera"}</h1>
      <p>
        {locale === "en"
          ? "We'll let you know as soon as sign-up opens for this product."
          : "Avisaremos assim que o cadastro para este produto abrir."}
      </p>
      <LeadForm variant="waitlist" />
    </div>
  );
}
