import { useState } from "react";
import { useL10n, useLocale, useT } from "../lib/i18n";
import { useSiteTheme, type ThemeChoice } from "../lib/theme";
import { useWebsiteSettings } from "../lib/settings";
import { PRODUCTS } from "../content/products";
import { pathFor, twinPath, EXTERNAL } from "../lib/routes";
import { useTrackEvent } from "../hooks/useTrackEvent";

const THEME_CHOICES: ThemeChoice[] = ["system", "light", "dark"];
const THEME_CYCLE: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
const THEME_ICON: Record<ThemeChoice, string> = { system: "\u{1F5A5}", light: "☀", dark: "\u{1F319}" };

/**
 * Header (05 §Navigation, P8: exactly one filled CTA). `currentPath` drives
 * the locale switch's twin-page lookup and is supplied by the page, not
 * read from `window` (SSR-safe).
 */
export function SiteHeader({ currentPath }: { currentPath: string }) {
  const t = useT();
  const l10n = useL10n();
  const locale = useLocale();
  const { choice, setChoice } = useSiteTheme();
  const settings = useWebsiteSettings();
  const track = useTrackEvent();
  const [menuOpen, setMenuOpen] = useState(false);
  const [productsOpen, setProductsOpen] = useState(false);

  const otherLocalePath = twinPath(currentPath) ?? (locale === "en" ? "/" : "/en");
  const otherLocaleLabel = locale === "en" ? "PT" : "EN";

  const primaryCta = settings.signup_enabled
    ? { label: t("nav.signup"), href: EXTERNAL.signup }
    : { label: t("nav.waitlist"), href: pathFor("waitlist", locale) };

  const visibleProducts = settings.products
    .filter((p) => p.visible && PRODUCTS[p.slug])
    .sort((a, b) => a.order - b.order);

  return (
    <header className="nx-header">
      <a href="#nx-main" className="nx-skip-link">
        {locale === "en" ? "Skip to content" : "Pular para o conteúdo"}
      </a>
      <div className="nx-container nx-header-inner">
        <a href={pathFor("home", locale)} className="nx-logo">
          NoctusAI
        </a>

        <nav className="nx-nav" aria-label="Primary">
          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="nx-nav-link"
              aria-expanded={productsOpen}
              onClick={() => setProductsOpen((v) => !v)}
              onMouseEnter={() => setProductsOpen(true)}
              onMouseLeave={() => setProductsOpen(false)}
            >
              {t("nav.products")}
            </button>
            {productsOpen && (
              <div className="nx-mega-menu" onMouseEnter={() => setProductsOpen(true)} onMouseLeave={() => setProductsOpen(false)}>
                <div className="nx-container nx-mega-menu-grid">
                  {visibleProducts.map((p) => (
                    <a key={p.slug} href={pathFor(`product-${p.slug}`, locale)}>
                      {PRODUCTS[p.slug]?.name ?? p.slug}
                    </a>
                  ))}
                  <a href={pathFor("products-index", locale)}>{t("nav.seeAll")}</a>
                </div>
              </div>
            )}
          </div>
          <a href={pathFor("solutions", locale)}>{t("nav.solutions")}</a>
          <a href={pathFor("pricing", locale)}>{t("nav.pricing")}</a>
          <a href={pathFor("about", locale)}>{t("nav.about")}</a>
          <a href={pathFor("contact", locale)}>{t("nav.contact")}</a>
        </nav>

        <div className="nx-nav-right">
          <a
            href={otherLocalePath}
            className="nx-locale-switch"
            onClick={() => track("locale_change", { locale: locale === "en" ? "pt-BR" : "en" })}
          >
            {otherLocaleLabel}
          </a>

          <div className="nx-theme-switch" role="group" aria-label={t("theme.label")}>
            {THEME_CHOICES.map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={choice === c}
                onClick={() => {
                  setChoice(c);
                  track("theme_change", { theme: c });
                }}
              >
                {t(`theme.${c}`)}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="nx-theme-toggle-mobile"
            aria-label={`${t("theme.label")}: ${t(`theme.${choice}`)}`}
            onClick={() => {
              const next = THEME_CYCLE[choice];
              setChoice(next);
              track("theme_change", { theme: next });
            }}
          >
            <span aria-hidden="true">{THEME_ICON[choice]}</span>
          </button>

          <a href={EXTERNAL.login} className="nx-btn nx-btn-ghost">
            {t("nav.login")}
          </a>
          <a
            href={primaryCta.href}
            className="nx-btn nx-btn-primary"
            onClick={() => track("cta_click", { cta: primaryCta.label, section: "header" })}
          >
            {primaryCta.label}
          </a>

          <button
            type="button"
            className="nx-nav-mobile-toggle"
            aria-expanded={menuOpen}
            aria-label={t("nav.menu")}
            onClick={() => setMenuOpen((v) => !v)}
          >
            ☰
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="nx-mobile-drawer nx-container">
          {visibleProducts.map((p) => (
            <a key={p.slug} href={pathFor(`product-${p.slug}`, locale)}>
              {PRODUCTS[p.slug]?.name ?? p.slug}
            </a>
          ))}
          <a href={pathFor("solutions", locale)}>{t("nav.solutions")}</a>
          <a href={pathFor("pricing", locale)}>{t("nav.pricing")}</a>
          <a href={pathFor("about", locale)}>{t("nav.about")}</a>
          <a href={pathFor("contact", locale)}>{t("nav.contact")}</a>
          <a href={EXTERNAL.login}>{t("nav.login")}</a>

          <div className="nx-drawer-utilities">
            <a
              href={otherLocalePath}
              className="nx-locale-switch"
              onClick={() => track("locale_change", { locale: locale === "en" ? "pt-BR" : "en" })}
            >
              {otherLocaleLabel}
            </a>
            <div className="nx-theme-switch" role="group" aria-label={t("theme.label")}>
              {THEME_CHOICES.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={choice === c}
                  onClick={() => {
                    setChoice(c);
                    track("theme_change", { theme: c });
                  }}
                >
                  {t(`theme.${c}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
