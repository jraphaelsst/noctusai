import { useTrackEvent } from "../hooks/useTrackEvent";

export interface CtaAction {
  label: string;
  href: string;
  primary?: boolean;
  external?: boolean;
  eventName?: string;
  eventProps?: Record<string, unknown>;
}

/**
 * Primary + secondary CTA pair (P8: header carries exactly one filled
 * button; this component renders the REST of the CTA surfaces — hero,
 * chapters, closing band — each of which may combine WhatsApp + a
 * secondary action).
 */
export function CtaPair({ actions }: { actions: CtaAction[] }) {
  const track = useTrackEvent();
  return (
    <div className="nx-cta-pair">
      {actions.map((a) => (
        <a
          key={a.label}
          href={a.href}
          className={`nx-btn ${a.primary ? "nx-btn-primary" : ""}`}
          target={a.external ? "_blank" : undefined}
          rel={a.external ? "noopener noreferrer" : undefined}
          onClick={() => {
            if (a.eventName) track(a.eventName, a.eventProps);
          }}
        >
          {a.label}
        </a>
      ))}
    </div>
  );
}
