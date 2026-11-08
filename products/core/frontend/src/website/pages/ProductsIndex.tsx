import { ProductCatalogGrid } from "@noctusai/lib/marketing";
import { PageHeading } from "../components/PageHeading";
import { useLocale, useT } from "../lib/i18n";
import { useCatalog } from "../lib/catalog";
import { toOrganProducts } from "../lib/catalogView";
import { pathFor } from "../lib/routes";

/** Product index (07 §Subpage templates): the live catalog; a waitlist click opens the waitlist page with that product. */
export default function ProductsIndex() {
  const t = useT();
  const locale = useLocale();
  const en = locale === "en";
  const { products, isLoading, isError, refetch } = useCatalog();
  const rows = products ?? [];

  return (
    <>
      <PageHeading>{en ? "Products" : "Produtos"}</PageHeading>
      <ProductCatalogGrid
        id="produtos"
        eyebrow={en ? "Products" : "Produtos"}
        title={en ? "NoctusAI products" : "Produtos NoctusAI"}
        products={toOrganProducts(rows, locale)}
        isLoading={isLoading}
        isError={isError}
        onRetry={refetch}
        onWaitlist={(slug) => {
          window.location.assign(`${pathFor("waitlist", locale)}?produto=${encodeURIComponent(slug)}`);
        }}
        emptyAction={{ label: t("nav.contact"), href: pathFor("contact", locale) }}
      />
      <p className="mx-auto w-full max-w-6xl px-4 pb-12 text-sm text-muted-foreground sm:px-6">
        {en ? "Didn't find what you need?" : "Não encontrou o que precisa?"}{" "}
        <a className="underline" href={pathFor("solutions", locale)}>{t("nav.solutions")} →</a>
      </p>
    </>
  );
}
