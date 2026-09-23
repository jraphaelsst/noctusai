export interface AudienceCardProps {
  title: string;
  benefit: string;
  ctaLabel: string;
  ctaHref: string;
}

/** One of the four audience-row cards (P3 · 07 §2). */
export function AudienceCard({ title, benefit, ctaLabel, ctaHref }: AudienceCardProps) {
  return (
    <div className="nx-audience-card">
      <h3>{title}</h3>
      <p>{benefit}</p>
      <a href={ctaHref} className="nx-btn nx-btn-ghost">
        {ctaLabel}
      </a>
    </div>
  );
}
