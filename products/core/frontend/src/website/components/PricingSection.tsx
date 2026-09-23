import { useState } from "react";
import { useLocale, useT } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { usePlans } from "../hooks/usePlans";
import { PricingCard } from "./PricingCard";
import { MarkedSection } from "../lib/markers";

/**
 * Pricing section shared by Home §7 and `/precos` (07 §7, §Subpage
 * templates). Plans are client-fetched only (`GET /api/website/plans`) — no
 * live DB at build time, so the prerendered HTML shows the skeleton state
 * for the numbers; the structure/copy around them is still fully static
 * for SEO (P11).
 */
export function PricingSection({ full }: { full?: boolean }) {
  const t = useT();
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const { data, showSkeleton, isRefreshing, error } = usePlans();
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");

  if (!settings.sections.pricing) return null;

  return (
    <MarkedSection sectionKey="pricing">
      <section className="nx-section" id="precos">
        <div className="nx-container">
          <span className="nx-eyebrow">PREÇOS</span>
          <h2>
            {data && data.length > 0
              ? t("pricing.fromMonth", { price: Math.min(...data.map((p) => p.price_monthly)).toFixed(0) })
              : locale === "en"
                ? "Pricing"
                : "Preços"}
          </h2>

          <div className="nx-pricing-toggle" role="group" aria-label="Mensal ou Anual">
            <button type="button" aria-pressed={cycle === "monthly"} onClick={() => setCycle("monthly")}>
              {t("pricing.monthly")}
            </button>
            <button type="button" aria-pressed={cycle === "yearly"} onClick={() => setCycle("yearly")}>
              {t("pricing.yearly")} · {t("pricing.discount")}
            </button>
          </div>

          {showSkeleton && (
            <div className="nx-pricing-grid" aria-busy="true">
              {[0, 1, 2].map((i) => (
                <div className="nx-price-card" key={i}>
                  <span className="nx-skeleton" style={{ width: "60%", height: 20 }} />
                  <span className="nx-skeleton" style={{ width: "40%", height: 32, marginTop: 12 }} />
                </div>
              ))}
            </div>
          )}

          {!showSkeleton && error && <p className="nx-form-error">{t("pricing.error")}</p>}
          {!showSkeleton && !error && data && data.length === 0 && <p>{t("pricing.empty")}</p>}

          {!showSkeleton && !error && data && data.length > 0 && (
            <div className="nx-pricing-grid" aria-busy={isRefreshing}>
              {data.map((plan, i) => (
                <PricingCard
                  key={plan.id}
                  plan={plan}
                  cycle={cycle}
                  featured={i === Math.floor(data.length / 2)}
                  locale={locale}
                  signupEnabled={settings.signup_enabled}
                />
              ))}
            </div>
          )}

          {!full && (
            <p style={{ marginTop: 24 }}>
              <a href={locale === "en" ? "/en/pricing" : "/precos"}>{t("pricing.fullComparison")} →</a>
            </p>
          )}

          {full && !showSkeleton && !error && data && data.length > 0 && (
            <table className="nx-comparison-table">
              <thead>
                <tr>
                  <th></th>
                  {data.map((p) => (
                    <th key={p.id}>{p.nome}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{locale === "en" ? "Users" : "Usuários"}</td>
                  {data.map((p) => (
                    <td key={p.id}>{p.max_users ?? "—"}</td>
                  ))}
                </tr>
                <tr>
                  <td>{locale === "en" ? "Products" : "Produtos"}</td>
                  {data.map((p) => (
                    <td key={p.id}>{p.max_products ?? "—"}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </section>
    </MarkedSection>
  );
}
