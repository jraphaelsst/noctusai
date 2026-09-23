import type { ReactNode } from "react";
import { LocaleProvider } from "../lib/i18n";
import { localeOfPath } from "../lib/routes";
import { SiteHeader } from "./SiteHeader";
import { Footer } from "./Footer";
import { ConsentBanner } from "./ConsentBanner";
import { LocaleBar } from "./LocaleBar";
import { WhatsAppFloat } from "./WhatsAppFloat";
import { TrackingLoader } from "./TrackingLoader";

/**
 * Shared page chrome. `data-surface="site"` / `data-theme` live on `<html>`
 * itself (baked in by the prerender assembly + `entry-client`'s static
 * host document) — NOT rendered here — so this component only needs to
 * emit the header/main/footer/overlay tree; the CSS `[data-surface="site"]`
 * selectors still match because `<html>` is an ancestor of everything React
 * mounts (06 §Scope isolation).
 */
export function SiteLayout({ path, children }: { path: string; children: ReactNode }) {
  const locale = localeOfPath(path);
  return (
    <LocaleProvider locale={locale}>
      <SiteHeader currentPath={path} />
      <main id="nx-main">{children}</main>
      <Footer />
      <ConsentBanner />
      <LocaleBar currentPath={path} />
      <WhatsAppFloat />
      <TrackingLoader />
    </LocaleProvider>
  );
}
