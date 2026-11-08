import { Faq } from "@noctusai/lib/marketing";
import { safeJsonLd } from "@noctusai/lib/json-ld";
import { useL10n } from "../lib/i18n";
import type { WebsiteFaqItem } from "../content/types";

/**
 * The seed `Faq` organ plus the `FAQPage` JSON-LD, both generated from the SAME items
 * (09 §Per-page SEO contract). The organ is native <details>, so every answer is in the DOM
 * without JS (P11).
 */
export function SiteFaq({ items, title, id = "faq" }: { items: WebsiteFaqItem[]; title: string; id?: string }) {
  const l10n = useL10n();
  const faq = items.map((i) => ({ question: l10n(i.q), answer: l10n(i.a) }));
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faq.map((f) => ({
      "@type": "Question",
      name: f.question,
      acceptedAnswer: { "@type": "Answer", text: f.answer },
    })),
  };
  return (
    <>
      <Faq id={id} title={title} items={faq} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }} />
    </>
  );
}
