import { useEffect, useState } from "react";
import { useLocale } from "../lib/i18n";
import { useCatalog } from "../lib/catalog";
import { PageHeading } from "../components/PageHeading";
import { SiteLeadForm } from "../components/SiteLeadForm";

/** Lista de espera (07 §Subpage templates). `?produto=<slug>` preselects the product once the catalog knows it. */
export default function Waitlist() {
  const locale = useLocale();
  const en = locale === "en";
  const { products } = useCatalog();
  const [slug, setSlug] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);

  // The query string exists only in the browser; read it after mount (the prerender has none).
  useEffect(() => {
    setSlug(new URLSearchParams(window.location.search).get("produto"));
  }, []);

  const row = !cleared && slug ? products?.find((p) => p.slug === slug && p.status !== "disponivel") : undefined;

  return (
    <>
      <PageHeading>{en ? "Waitlist" : "Lista de espera"}</PageHeading>
      <SiteLeadForm
        source="waitlist"
        id="lista-de-espera"
        eyebrow={en ? "Waitlist" : "Lista de espera"}
        title={en ? "Join the waitlist" : "Entre na lista de espera"}
        description={
          en
            ? "We'll let you know as soon as sign-up opens for this product."
            : "Avisaremos assim que o cadastro para este produto abrir."
        }
        heading={en ? "Leave your contact" : "Deixe o seu contato"}
        interest={row ? { slug: row.slug, nome: row.nome } : null}
        onInterestClear={() => setCleared(true)}
      />
    </>
  );
}
