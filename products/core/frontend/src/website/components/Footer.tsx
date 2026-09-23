import { useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { PRODUCTS } from "../content/products";
import { pathFor, EXTERNAL } from "../lib/routes";
import { legalEntity } from "../content/legal";

/** Mega-footer as sitemap + legal anchor (P14). */
export function Footer() {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const visibleProducts = settings.products.filter((p) => p.visible && PRODUCTS[p.slug]);
  const year = new Date().getFullYear();

  return (
    <footer className="nx-footer">
      <div className="nx-container">
        <div className="nx-footer-grid">
          <div>
            <h3>{t("footer.products")}</h3>
            <ul>
              {visibleProducts.map((p) => (
                <li key={p.slug}>
                  <a href={pathFor(`product-${p.slug}`, locale)}>{PRODUCTS[p.slug]?.name ?? p.slug}</a>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3>{t("footer.solutions")}</h3>
            <ul>
              <li>
                <a href={pathFor("solutions", locale)}>{t("nav.solutions")}</a>
              </li>
            </ul>
          </div>
          <div>
            <h3>{t("footer.company")}</h3>
            <ul>
              <li>
                <a href={pathFor("about", locale)}>{t("footer.about")}</a>
              </li>
              <li>
                <a href={pathFor("contact", locale)}>{t("footer.contact")}</a>
              </li>
              <li>
                <a href={pathFor("waitlist", locale)}>{t("footer.waitlist")}</a>
              </li>
            </ul>
          </div>
          <div>
            <h3>{t("footer.legal")}</h3>
            <ul>
              <li>
                <a href={EXTERNAL.privacyPolicy}>{t("footer.privacy")}</a>
              </li>
              <li>
                <a href={EXTERNAL.termsOfUse}>{t("footer.terms")}</a>
              </li>
              <li>
                <a href="#nx-consent-preferences" data-nx-open-consent-preferences="1">
                  {t("footer.cookiePreferences")}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="nx-footer-legal">
          <div>
            {legalEntity.razaoSocial && <div>{legalEntity.razaoSocial}</div>}
            {legalEntity.cnpj && <div>CNPJ {legalEntity.cnpj}</div>}
            {legalEntity.address && <div>{legalEntity.address}</div>}
            <div>
              © {year} NoctusAI. {t("footer.rights")}
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
