import { Steps } from "@noctusai/lib/marketing";
import { PageHeading } from "../components/PageHeading";
import { useLocale, useT } from "../lib/i18n";
import { SiteLeadForm } from "../components/SiteLeadForm";
import { SiteFaq } from "../components/SiteFaq";
import { useWebsiteSettings } from "../lib/settings";
import { customBuildSteps } from "../content/customBuild";

/** Soluções / IA sob medida (07 §Subpage templates — Home §4 expanded). */
export default function Solutions() {
  const t = useT();
  const locale = useLocale();
  const en = locale === "en";
  const settings = useWebsiteSettings();

  return (
    <>
      <PageHeading>{en ? "Custom AI" : "IA sob medida"}</PageHeading>
      <Steps
        id="sob-medida"
        eyebrow={en ? "Custom AI" : "IA sob medida"}
        title={en ? "A project built for your business" : "Um projeto construído para o seu negócio"}
        description={
          en
            ? "From diagnosis to production, we build AI systems on the same seed-first foundation every NoctusAI product runs on."
            : "Do diagnóstico à produção, construímos sistemas de IA sobre a mesma base seed-first que roda todos os produtos NoctusAI."
        }
        steps={customBuildSteps(en)}
      />
      <SiteLeadForm
        source="brief"
        id="brief"
        eyebrow={en ? "Talk to us" : "Fale com a gente"}
        title={en ? "Tell us about your project" : "Conte sobre o seu projeto"}
        heading={en ? "Tell us about your project" : "Conte sobre o seu projeto"}
      />
      {settings.sections.faq && settings.faq.length > 0 && <SiteFaq title={t("faq.title")} items={settings.faq} />}
    </>
  );
}
