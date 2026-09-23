import { useLocale } from "../lib/i18n";
import { legalEntity } from "../content/legal";

/** Sobre (07 §Subpage templates). */
export default function About() {
  const locale = useLocale();
  return (
    <div className="nx-container nx-section">
      <span className="nx-eyebrow">{locale === "en" ? "ABOUT" : "SOBRE"}</span>
      <h1>NoctusAI</h1>
      <p>
        {locale === "en"
          ? "Noctus comes from nocturnal: the hours when work keeps happening. We build AI products that work while you sleep — calm, precise, always on."
          : "Noctus vem de noturno: as horas em que o trabalho continua acontecendo. Construímos produtos com IA que trabalham enquanto você dorme — calmos, precisos, sempre ativos."}
      </p>
      <h2>{locale === "en" ? "How we work" : "Como trabalhamos"}</h2>
      <ul>
        <li>{locale === "en" ? "Seed-first: every product shares one foundation." : "Seed-first: todo produto compartilha a mesma base."}</li>
        <li>{locale === "en" ? "No fabricated proof — only what's verifiably true." : "Sem prova fabricada — só o que é verificavelmente verdadeiro."}</li>
        <li>{locale === "en" ? "Data hosted in Brazil, LGPD-compliant by construction." : "Dados hospedados no Brasil, em conformidade com a LGPD por construção."}</li>
      </ul>
      {legalEntity.razaoSocial && <p>{legalEntity.razaoSocial}</p>}
    </div>
  );
}
