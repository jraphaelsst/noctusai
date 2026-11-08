import { LandingFooter } from "@noctusai/lib/marketing";
import { useLocale, useT } from "../lib/i18n";
import { useCatalog } from "../lib/catalog";
import { productHref } from "../lib/catalogView";
import { pathFor, EXTERNAL } from "../lib/routes";
import { legalEntity } from "../content/legal";
import { openConsentPreferences } from "./ConsentBanner";

/** Sitemap + legal anchor (P14) on the seed `LandingFooter`. Product links = the catalog's disponível rows. */
export function SiteFooter() {
  const t = useT();
  const locale = useLocale();
  const { products } = useCatalog();
  const available = (products ?? []).filter((p) => p.status === "disponivel");
  const year = new Date().getFullYear();

  const legalLines = [legalEntity.razaoSocial, legalEntity.cnpj && `CNPJ ${legalEntity.cnpj}`, legalEntity.address].filter(Boolean);

  return (
    <LandingFooter
      brand={<strong className="text-foreground">NoctusAI</strong>}
      columns={[
        {
          heading: t("footer.products"),
          links: [
            ...available.map((p) => ({ label: p.nome, href: productHref(p.slug, locale) ?? `${pathFor("products-index", locale)}#produtos` })),
            { label: t("nav.seeAll"), href: pathFor("products-index", locale) },
          ],
        },
        { heading: t("footer.solutions"), links: [{ label: t("nav.solutions"), href: pathFor("solutions", locale) }] },
        {
          heading: t("footer.company"),
          links: [
            { label: t("footer.about"), href: pathFor("about", locale) },
            { label: t("footer.contact"), href: pathFor("contact", locale) },
            { label: t("footer.waitlist"), href: pathFor("waitlist", locale) },
          ],
        },
        {
          heading: t("footer.legal"),
          links: [
            { label: t("footer.privacy"), href: EXTERNAL.privacyPolicy },
            { label: t("footer.terms"), href: EXTERNAL.termsOfUse },
            { label: t("footer.cookiePreferences"), onClick: openConsentPreferences },
          ],
        },
      ]}
      copyright={[...legalLines, `© ${year} NoctusAI. ${t("footer.rights")}`].join(" · ")}
    />
  );
}
