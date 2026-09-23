/**
 * Conditional third-party script loader. Contract D8: "GA4/Meta Pixel/
 * Plausible load only if an id is configured AND consent is granted. IDs
 * start empty ⇒ nothing third-party loads at launch." Renders nothing;
 * pure side-effect component, mounted once near the app root.
 *
 * Mapping: Plausible + GA4 → Medição consent (they measure usage). Meta
 * Pixel → Marketing consent (it's an ads/retargeting pixel). Necessary
 * cookies never gate a third-party script — there are none that qualify.
 */
import { useEffect } from "react";
import { useWebsiteSettings } from "../lib/settings";
import { useConsent } from "../lib/consent";

function injectScript(id: string, src: string, attrs: Record<string, string> = {}): void {
  if (typeof document === "undefined" || document.getElementById(id)) return;
  const script = document.createElement("script");
  script.id = id;
  script.src = src;
  script.async = true;
  Object.entries(attrs).forEach(([k, v]) => script.setAttribute(k, v));
  document.head.appendChild(script);
}

export function TrackingLoader() {
  const { tracking } = useWebsiteSettings();
  const { decision } = useConsent();

  useEffect(() => {
    if (!decision) return;

    if (tracking.plausible_domain && decision.measurement) {
      injectScript("nx-plausible", "https://plausible.io/js/script.js", {
        "data-domain": tracking.plausible_domain,
      });
    }

    if (tracking.ga4_id && decision.measurement) {
      injectScript("nx-ga4", `https://www.googletagmanager.com/gtag/js?id=${tracking.ga4_id}`);
      const w = window as unknown as { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void };
      w.dataLayer = w.dataLayer || [];
      w.gtag = w.gtag || function gtag(...args: unknown[]) { w.dataLayer!.push(args); };
      w.gtag("js", new Date());
      w.gtag("config", tracking.ga4_id);
    }

    if (tracking.meta_pixel_id && decision.marketing) {
      const w = window as unknown as { fbq?: (...args: unknown[]) => void };
      if (!w.fbq) {
        injectScript("nx-meta-pixel", "https://connect.facebook.net/en_US/fbevents.js");
      }
    }
  }, [tracking, decision]);

  return null;
}
