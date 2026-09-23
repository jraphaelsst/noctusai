import { useState } from "react";
import { useL10n } from "../lib/i18n";
import type { WebsiteFaqItem } from "../content/types";

/**
 * Accordion + `FAQPage` JSON-LD, generated from the SAME data (09 §Per-page
 * SEO contract). Content is visible in the DOM even with JS disabled — the
 * accordion only toggles a CSS class, it never removes the answer from the
 * tree, so a no-JS visitor still reads every answer (P11).
 */
export function FaqAccordion({ items, sectionId }: { items: WebsiteFaqItem[]; sectionId?: string }) {
  const l10n = useL10n();
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: l10n(item.q),
      acceptedAnswer: { "@type": "Answer", text: l10n(item.a) },
    })),
  };

  return (
    <div id={sectionId}>
      {items.map((item, i) => (
        <div className="nx-faq-item" key={i}>
          <button
            type="button"
            className="nx-faq-question"
            aria-expanded={openIndex === i}
            onClick={() => setOpenIndex(openIndex === i ? null : i)}
          >
            <span>{l10n(item.q)}</span>
            <span aria-hidden="true">{openIndex === i ? "−" : "+"}</span>
          </button>
          <div className="nx-faq-answer" hidden={openIndex !== i}>
            {l10n(item.a)}
          </div>
        </div>
      ))}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </div>
  );
}
