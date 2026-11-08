import { LandingNav } from "@noctusai/lib/marketing";
import { useLocale, useT } from "../lib/i18n";
import { useSiteTheme } from "../lib/theme";
import { useWebsiteSettings } from "../lib/settings";
import { useCatalog } from "../lib/catalog";
import { toNavProducts } from "../lib/catalogView";
import { pathFor, twinPath, EXTERNAL } from "../lib/routes";
import { useTrackEvent } from "../hooks/useTrackEvent";

/**
 * The site header = the seed `LandingNav` organ fed by the site: the "Produtos" menu lists the
 * catalog's DISPONÍVEL rows (derived, never hand-kept); P8 stays — exactly one filled CTA.
 */
export function SiteNav({ currentPath }: { currentPath: string }) {
  const t = useT();
  const locale = useLocale();
  const { choice, setChoice } = useSiteTheme();
  const settings = useWebsiteSettings();
  const { products } = useCatalog();
  const track = useTrackEvent();

  const otherLocalePath = twinPath(currentPath) ?? (locale === "en" ? "/" : "/en");
  const toLocale = locale === "en" ? "pt-BR" : "en";
  const primary = settings.signup_enabled
    ? { label: t("nav.signup"), href: EXTERNAL.signup }
    : { label: t("nav.waitlist"), href: pathFor("waitlist", locale) };

  return (
    <LandingNav
      brand={{ label: "NoctusAI", href: pathFor("home", locale), ariaLabel: "NoctusAI, página inicial" }}
      productsLabel={t("nav.products")}
      products={toNavProducts(products ?? [], locale)}
      allProductsHref={pathFor("products-index", locale)}
      links={[
        { label: t("nav.solutions"), href: pathFor("solutions", locale) },
        { label: t("nav.pricing"), href: pathFor("pricing", locale) },
        { label: t("nav.about"), href: pathFor("about", locale) },
        { label: t("nav.contact"), href: pathFor("contact", locale) },
      ]}
      loginAction={{ label: t("nav.login"), href: EXTERNAL.login }}
      primaryAction={primary}
      languageLink={{
        label: locale === "en" ? "PT" : "EN",
        href: otherLocalePath,
        lang: toLocale === "en" ? "en" : "pt-BR",
        ariaLabel: locale === "en" ? "Ver em Português" : "View in English",
      }}
      themeSwitch={{
        value: choice,
        onChange: (next) => {
          setChoice(next);
          track("theme_change", { theme: next });
        },
      }}
    />
  );
}
