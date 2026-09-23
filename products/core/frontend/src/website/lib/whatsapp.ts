/**
 * WhatsApp CTA helpers. Every WhatsApp affordance degrades gracefully to the
 * waitlist/contact form when `whatsapp.number_e164` is null (contract §2).
 */
import type { WebsiteSettings } from "../content/types";
import type { Locale } from "../content/types";

export function whatsappUrl(
  settings: WebsiteSettings,
  locale: Locale,
  overrideMessage?: string,
): string | null {
  if (!settings.whatsapp.number_e164) return null;
  const digits = settings.whatsapp.number_e164.replace(/[^0-9]/g, "");
  const message = overrideMessage ?? (locale === "en" ? settings.whatsapp.default_message.en : settings.whatsapp.default_message.pt);
  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}
