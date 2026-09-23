import { useL10n, useT } from "../lib/i18n";
import type { ProductCopy } from "../content/products";
import type { ProductState } from "../content/types";
import { CtaPair, type CtaAction } from "./CtaPair";
import { MarkedProduct } from "../lib/markers";

export interface ProductChapterProps {
  copy: ProductCopy;
  state: ProductState;
  productHref: string;
  whatsappHref: string | null;
  tagline?: { pt: string; en: string };
}

/**
 * The repeated product chapter template (P10, 07 §3). Never hides the faux-
 * UI panel on mobile (Linear's mobile gap is the anti-pattern the brief
 * calls out).
 */
export function ProductChapter({ copy, state, productHref, whatsappHref, tagline }: ProductChapterProps) {
  const l10n = useL10n();
  const t = useT();

  const actions: CtaAction[] = [];
  if (state === "disponivel") {
    actions.push({ label: t("cta.signup"), href: "https://core.noctusai.com/login?mode=signup", primary: true });
    if (whatsappHref) actions.push({ label: t("cta.whatsapp"), href: whatsappHref, external: true, eventName: "whatsapp_click", eventProps: { section: "products", product: copy.slug } });
  } else if (state === "lista_de_espera") {
    actions.push({ label: t("cta.waitlistShort"), href: `/lista-de-espera?produto=${copy.slug}`, primary: true });
  }

  return (
    <MarkedProduct slug={copy.slug}>
      <section className="nx-chapter" id={`nx-product-${copy.slug}`}>
        <div>
          <h3>
            {copy.name} — <span data-nx-tagline>{tagline ? l10n(tagline) : l10n(copy.tagline)}</span>
          </h3>
          <span className={`nx-badge ${state === "disponivel" ? "nx-badge-disponivel" : ""}`}>{t(`productStates.${state}`)}</span>
          <ul>
            {copy.capabilities.map((c, i) => (
              <li key={i}>{l10n(c)}</li>
            ))}
          </ul>
          <CtaPair actions={actions} />
          <p>
            <a href={productHref}>{t("cta.seeProduct")} →</a>
          </p>
        </div>
        <div className="nx-panel" aria-hidden="true">
          <div className="nx-panel-header">
            <span className="nx-panel-dot" />
            <span>{l10n(copy.panel.heading)}</span>
          </div>
          {copy.panel.rows.map((row, i) => (
            <div className="nx-panel-row" key={i}>
              <span>{l10n(row)}</span>
            </div>
          ))}
        </div>
      </section>
    </MarkedProduct>
  );
}
