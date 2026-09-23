import { useT } from "../lib/i18n";
import { planFeatureList, type PlanRow } from "../lib/api";
import { useTrackEvent } from "../hooks/useTrackEvent";

/** Real plan limits from the `plans` row (`-1` = unlimited, per core migration 001). */
function limitLines(plan: PlanRow, t: ReturnType<typeof useT>): string[] {
  const lines: string[] = [];
  if (typeof plan.max_users === "number") {
    lines.push(plan.max_users < 0 ? t("pricing.usersUnlimited") : t("pricing.users", { n: plan.max_users }));
  }
  if (typeof plan.max_products === "number") {
    lines.push(plan.max_products < 0 ? t("pricing.productsUnlimited") : t("pricing.products", { n: plan.max_products }));
  }
  return lines;
}

function formatBRL(value: number, locale: "pt-BR" | "en"): string {
  return new Intl.NumberFormat(locale === "en" ? "en-US" : "pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export function PricingCard({
  plan,
  cycle,
  featured,
  locale,
  signupEnabled,
}: {
  plan: PlanRow;
  cycle: "monthly" | "yearly";
  featured?: boolean;
  locale: "pt-BR" | "en";
  signupEnabled: boolean;
}) {
  const t = useT();
  const track = useTrackEvent();
  const price = cycle === "monthly" ? plan.price_monthly : plan.price_yearly;
  const ctaLabel = plan.is_custom
    ? t("cta.whatsapp")
    : signupEnabled
      ? t("cta.signup")
      : t("cta.waitlistShort");
  const ctaHref = plan.is_custom ? "/solucoes" : signupEnabled ? "https://core.noctusai.com/login?mode=signup" : "/lista-de-espera";

  return (
    <div className={`nx-price-card ${featured ? "nx-price-featured" : ""}`}>
      {featured && <span className="nx-price-anchor">{t("pricing.mostChosen")}</span>}
      <h3>{plan.nome}</h3>
      {plan.descricao && <p>{plan.descricao}</p>}
      <div className="nx-price-amount">{plan.is_custom ? "—" : formatBRL(price, locale)}</div>
      <ul>
        {limitLines(plan, t).concat(planFeatureList(plan.features)).slice(0, 6).map((f, i) => (
          <li key={i}>{f}</li>
        ))}
      </ul>
      <a
        href={ctaHref}
        className="nx-btn nx-btn-primary"
        onClick={() => track("cta_click", { cta: ctaLabel, section: "pricing" })}
        target={plan.is_custom ? "_blank" : undefined}
        rel={plan.is_custom ? "noopener noreferrer" : undefined}
      >
        {ctaLabel}
      </a>
    </div>
  );
}
