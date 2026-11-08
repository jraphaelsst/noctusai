/**
 * Catalog rows -> what the landing organs take. Pure, so every page derives its nav / chips /
 * grid from the SAME rows (nothing hand-kept, `KB § PATTERNS/frontend/product-internal-wiring.md`).
 *
 * "Conhecer" goes to the product's chapter page when one exists (a slug with copy in
 * `content/products.ts`); a product without a page has NO "Conhecer" — the public catalog
 * deliberately never carries `url_base`, and inventing a URL would be a lie.
 */
import type { CatalogProduct, HeroChip, NavProduct } from "@noctusai/lib/marketing";
import type { CatalogRow } from "./api";
import type { Locale } from "../content/types";
import { PRODUCTS } from "../content/products";
import { pathFor } from "./routes";

export function productHref(slug: string, locale: Locale): string | undefined {
  return PRODUCTS[slug] ? pathFor(`product-${slug}`, locale) : undefined;
}

export function toOrganProducts(rows: CatalogRow[], locale: Locale): CatalogProduct[] {
  return rows.map((r) => ({
    slug: r.slug,
    nome: r.nome,
    descricao_publica: r.descricao_publica,
    icone: r.icone ?? "",
    destaque_no_site: r.destaque_no_site,
    status: r.status,
    url: productHref(r.slug, locale),
  }));
}

const available = (rows: CatalogRow[]) => rows.filter((r) => r.status === "disponivel");

export function toNavProducts(rows: CatalogRow[], locale: Locale): NavProduct[] {
  return available(rows).map((r) => ({
    nome: r.nome,
    href: productHref(r.slug, locale) ?? `${pathFor("products-index", locale)}#produtos`,
    descricao: r.descricao_publica,
    icone: r.icone,
  }));
}

export function toHeroChips(rows: CatalogRow[], locale: Locale): HeroChip[] {
  return available(rows).map((r) => ({
    label: r.nome,
    href: productHref(r.slug, locale) ?? `${pathFor("products-index", locale)}#produtos`,
    icone: r.icone,
  }));
}
