import { useLocale, useT } from "../lib/i18n";
import { pathFor } from "../lib/routes";

/** 404 — light on-brand, search-free (07 §Subpage templates). */
export default function NotFound() {
  const t = useT();
  const locale = useLocale();
  return (
    <div className="nx-container nx-section" style={{ textAlign: "center" }}>
      <h1>{t("notFound.title")}</h1>
      <p>{t("notFound.body")}</p>
      <a href={pathFor("home", locale)} className="nx-btn nx-btn-primary">
        {t("notFound.home")}
      </a>
    </div>
  );
}
