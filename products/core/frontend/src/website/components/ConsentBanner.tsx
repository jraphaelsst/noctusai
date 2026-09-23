import { useEffect, useState } from "react";
import { useConsent } from "../lib/consent";
import { useT } from "../lib/i18n";
import { postEvent } from "../lib/api";

/**
 * Bottom-bar cookie consent (P12: a bar, never a modal). Equal-weight
 * Rejeitar/Aceitar plus Personalizar (per-category). Also opens when the
 * footer's "Preferências de cookies" link is clicked, even after an initial
 * decision was made.
 */
export function ConsentBanner() {
  const { bannerOpen, accept, reject, save } = useConsent();
  const t = useT();
  const [customizing, setCustomizing] = useState(false);
  const [measurement, setMeasurement] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [forceOpen, setForceOpen] = useState(false);

  useEffect(() => {
    function onOpenPreferences(e: Event) {
      const target = e.target as HTMLElement;
      if (target.closest("[data-nx-open-consent-preferences]")) {
        e.preventDefault();
        setForceOpen(true);
        setCustomizing(true);
      }
    }
    document.addEventListener("click", onOpenPreferences);
    return () => document.removeEventListener("click", onOpenPreferences);
  }, []);

  const open = bannerOpen || forceOpen;
  if (!open) return null;

  function commit(fn: () => void, eventName: string) {
    fn();
    postEvent("consent", { analytics: measurement, marketing });
    postEvent(eventName);
    setForceOpen(false);
    setCustomizing(false);
  }

  return (
    <div className="nx-bottom-bar" role="dialog" aria-label={t("consent.message")}>
      <div className="nx-consent-bar">
        <p style={{ margin: 0, flex: "1 1 320px" }}>{t("consent.message")}</p>
        <div className="nx-consent-actions">
          <button type="button" className="nx-btn" onClick={() => commit(reject, "consent")}>
            {t("consent.reject")}
          </button>
          <button type="button" className="nx-btn" onClick={() => setCustomizing((v) => !v)}>
            {t("consent.customize")}
          </button>
          <button type="button" className="nx-btn nx-btn-primary" onClick={() => commit(accept, "consent")}>
            {t("consent.accept")}
          </button>
        </div>
      </div>
      {customizing && (
        <div className="nx-consent-categories">
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked disabled />
            <span>
              <strong>{t("consent.necessary")}</strong> — {t("consent.necessaryDesc")}
            </span>
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={measurement} onChange={(e) => setMeasurement(e.target.checked)} />
            <span>
              <strong>{t("consent.measurement")}</strong> — {t("consent.measurementDesc")}
            </span>
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
            <span>
              <strong>{t("consent.marketing")}</strong> — {t("consent.marketingDesc")}
            </span>
          </label>
          <button
            type="button"
            className="nx-btn nx-btn-primary"
            style={{ justifySelf: "start" }}
            onClick={() => commit(() => save({ measurement, marketing }), "consent")}
          >
            {t("consent.save")}
          </button>
        </div>
      )}
    </div>
  );
}
