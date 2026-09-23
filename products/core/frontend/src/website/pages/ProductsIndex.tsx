import { useL10n, useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { pathFor } from "../lib/routes";
import { PRODUCTS } from "../content/products";

/** Product index (07 §Subpage templates). */
export default function ProductsIndex() {
  const t = useT();
  const l10n = useL10n();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const visible = settings.products.filter((p) => p.visible && PRODUCTS[p.slug]).sort((a, b) => a.order - b.order);

  return (
    <div className="nx-container nx-section">
      <span className="nx-eyebrow">{locale === "en" ? "PRODUCTS" : "PRODUTOS"}</span>
      <h1>{locale === "en" ? "Products" : "Produtos"}</h1>
      <div className="nx-audience-grid">
        {visible.map((p) => {
          const copy = PRODUCTS[p.slug];
          if (!copy) return null;
          return (
            <div key={p.slug} className="nx-audience-card">
              <span className={`nx-badge ${p.state === "disponivel" ? "nx-badge-disponivel" : ""}`}>{t(`productStates.${p.state}`)}</span>
              <h3>{copy.name}</h3>
              <p>{l10n(copy.tagline)}</p>
              <a href={pathFor(`product-${p.slug}`, locale)} className="nx-btn nx-btn-ghost">
                {t("cta.seeProduct")}
              </a>
            </div>
          );
        })}
      </div>
      <p style={{ marginTop: 40 }}>
        {locale === "en" ? "Didn't find what you need?" : "Não encontrou o que precisa?"}{" "}
        <a href={pathFor("solutions", locale)}>{t("nav.solutions")} →</a>
      </p>
    </div>
  );
}
