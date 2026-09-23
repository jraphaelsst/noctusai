import { useConsent } from "../lib/consent";
import { useWebsiteSettings } from "../lib/settings";
import { useLocale } from "../lib/i18n";
import { whatsappUrl } from "../lib/whatsapp";
import { useTrackEvent } from "../hooks/useTrackEvent";

/**
 * Floating WhatsApp button (P9). Appears only AFTER the consent decision
 * (P12: one overlay at a time) and only when a number is configured; never
 * stacks with the consent bar being open.
 */
export function WhatsAppFloat() {
  const settings = useWebsiteSettings();
  const { decision, bannerOpen } = useConsent();
  const locale = useLocale();
  const track = useTrackEvent();

  if (!settings.whatsapp.float_enabled || bannerOpen || decision === null) return null;
  const href = whatsappUrl(settings, locale);
  if (!href) return null;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="nx-whatsapp-float"
      aria-label="WhatsApp"
      onClick={() => track("whatsapp_click", { section: "float" })}
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.39 1.26 4.82L2 22l5.44-1.35a9.9 9.9 0 0 0 4.6 1.14h.01c5.46 0 9.9-4.45 9.9-9.91 0-2.65-1.03-5.13-2.9-7C17.17 3.03 14.69 2 12.04 2Z" />
      </svg>
    </a>
  );
}
