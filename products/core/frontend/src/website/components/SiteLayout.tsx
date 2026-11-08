import type { ReactNode } from "react";
import { LocaleProvider } from "../lib/i18n";
import { localeOfPath } from "../lib/routes";
import { Toaster } from "sonner";
import { MotionProvider } from "@noctusai/lib/marketing";
import { SiteNav } from "./SiteNav";
import { SiteFooter } from "./SiteFooter";
import { ConsentBanner } from "./ConsentBanner";
import { LocaleBar } from "./LocaleBar";
import { WhatsAppFloat } from "./WhatsAppFloat";
import { TrackingLoader } from "./TrackingLoader";

/**
 * Shared page chrome. `data-surface="site"` / `data-theme` live on `<html>`
 * itself (baked in by the prerender assembly + `entry-client`'s static
 * host document) — NOT rendered here — so this component only needs to
 * emit the nav/main/footer/overlay tree; the CSS `[data-surface="site"]`
 * selectors still match because `<html>` is an ancestor of everything React
 * mounts (06 §Scope isolation).
 */
export function SiteLayout({ path, children }: { path: string; children: ReactNode }) {
  const locale = localeOfPath(path);
  return (
    <LocaleProvider locale={locale}>
      <MotionProvider>
        <a
          href="#nx-main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        >
          {locale === "en" ? "Skip to content" : "Pular para o conteúdo"}
        </a>
        <SiteNav currentPath={path} />
        <main id="nx-main">{children}</main>
        <SiteFooter />
        <ConsentBanner />
        <LocaleBar currentPath={path} />
        <WhatsAppFloat />
        <TrackingLoader />
        {/* Polite live region for the organs' toasts (e.g. the waitlist "Desfazer" notice). */}
        <Toaster />
      </MotionProvider>
    </LocaleProvider>
  );
}
