import { useState } from "react";
import { useConsent } from "../lib/consent";
import { useLocale, useT } from "../lib/i18n";
import { twinPath } from "../lib/routes";

/**
 * Dismissible locale-suggestion bar (05 §URL & language scheme). Appears
 * ONLY after the consent bar is dismissed (P12: one overlay at a time).
 */
export function LocaleBar({ currentPath }: { currentPath: string }) {
  const { decision } = useConsent();
  const locale = useLocale();
  const t = useT();
  const [dismissed, setDismissed] = useState(false);

  const twin = twinPath(currentPath);
  // Requires an actual consent DECISION (not merely "banner currently
  // closed") — otherwise the locale bar would render during SSR/first
  // paint, before the consent bar has even had a chance to show, which is
  // the exact P12 stacking-order violation this gate exists to prevent.
  if (decision === null || dismissed || !twin) return null;

  return (
    <div className="nx-bottom-bar nx-locale-bar" role="status">
      <div style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <span>{t("locale.suggestion")}</span>
        <div style={{ display: "flex", gap: 8 }}>
          <a href={twin} className="nx-btn nx-btn-primary">
            {t("locale.switch")}
          </a>
          <button type="button" className="nx-btn nx-btn-ghost" onClick={() => setDismissed(true)}>
            ×
          </button>
        </div>
      </div>
    </div>
  );
}
