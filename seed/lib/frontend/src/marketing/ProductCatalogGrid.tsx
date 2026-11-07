import { useRef, useState } from "react";
import { ArrowRight, Bell, ChevronDown } from "lucide-react";
import { Badge } from "../design-system/ui/Badge";
import { Button } from "../design-system/ui/Button";
import { Card } from "../design-system/ui/FormControls";
import { Skeleton } from "../design-system/ui/Skeleton";
import { cn } from "../utils";
import { Reveal } from "./primitives";
import { LandingIcon, SectionHead, linkButtonClass, sectionClass, wrapClass } from "./shared";

export type CatalogStatus = "disponivel" | "em_breve" | "lista_de_espera";

export interface CatalogProduct {
  slug: string;
  nome: string;
  /** Public copy. `null` renders the honest "Descrição não informada.". */
  descricao_publica: string | null;
  /** Registered lucide icon name; unknown names fall back to a generic box. */
  icone: string;
  /** 1-based featured position chosen in admin; `null` = not featured. */
  destaque_no_site: number | null;
  status: CatalogStatus;
  /** Where "Conhecer" goes (disponível only). */
  url?: string;
}

const MAX_FEATURED = 6;
const STATUS_ORDER: Record<CatalogStatus, number> = { disponivel: 0, em_breve: 1, lista_de_espera: 2 };
const STATUS_LABEL: Record<CatalogStatus, string> = {
  disponivel: "Disponível",
  em_breve: "Em breve",
  lista_de_espera: "Lista de espera",
};
const FILTER_LABEL: Record<CatalogStatus, string> = {
  disponivel: "Disponíveis",
  em_breve: "Em breve",
  lista_de_espera: "Lista de espera",
};
/** Status → badge colour (tokens: ok = success, info = info, warn = warning). */
const STATUS_BADGE: Record<CatalogStatus, string> = {
  disponivel: "border-success bg-success-light text-foreground",
  em_breve: "border-info bg-info-light text-foreground",
  lista_de_espera: "border-warning bg-warning-light text-foreground",
};

const byStatusThenName = (a: CatalogProduct, b: CatalogProduct) =>
  STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.nome.localeCompare(b.nome, "pt-BR");

/** Every product, status order (disponível first) then alphabetical (pt-BR). */
export function sortCatalog(products: CatalogProduct[]): CatalogProduct[] {
  return [...products].sort(byStatusThenName);
}

/**
 * The collapsed selection: featured products ordered by `destaque_no_site`
 * (up to 6). With none featured, the first 6 by status then name.
 */
export function selectFeaturedProducts(products: CatalogProduct[], max = MAX_FEATURED): CatalogProduct[] {
  const featured = products
    .filter((p) => p.destaque_no_site != null)
    .sort((a, b) => (a.destaque_no_site as number) - (b.destaque_no_site as number) || byStatusThenName(a, b));
  return (featured.length > 0 ? featured : sortCatalog(products)).slice(0, max);
}

export interface ProductCatalogGridProps {
  /** Only the public flavour exists here; the dashboard variant lives in the product. */
  variant?: "public";
  products: CatalogProduct[];
  isLoading?: boolean;
  /** A refetch failed. With `products` present they are shown as the stale published version. */
  isError?: boolean;
  onRetry?: () => void;
  /** "Avise-me quando abrir". Without it the waitlist button is not rendered. */
  onWaitlist?: (slug: string) => void;
  id?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  /** Empty state: where to send the visitor instead (e.g. the contact form). */
  emptyAction?: { label: string; href: string };
}

type Filter = "all" | CatalogStatus;

function ProductCard({ p, onWaitlist }: { p: CatalogProduct; onWaitlist?: (slug: string) => void }) {
  const lista = p.status === "lista_de_espera";
  return (
    <li className="flex">
      <Card className={cn("flex w-full flex-col gap-3 p-5", lista && "border-dashed")}>
        <div className="flex items-start justify-between gap-2">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-muted text-foreground">
            <LandingIcon name={p.icone} className="h-5 w-5" />
          </span>
          <Badge variant="outline" className={STATUS_BADGE[p.status]}>{STATUS_LABEL[p.status]}</Badge>
        </div>
        <h3 className="text-base font-semibold text-foreground">{p.nome}</h3>
        <p className="text-sm text-muted-foreground">{p.descricao_publica || "Descrição não informada."}</p>
        <div className="mt-auto pt-2">
          {p.status === "disponivel" ? (
            p.url ? (
              <a href={p.url} className={linkButtonClass("primary", "sm")}>
                Conhecer<span className="sr-only"> o {p.nome}</span>
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            ) : null
          ) : onWaitlist ? (
            <Button size="sm" aria-label={`Avise-me quando abrir: ${p.nome}`} onClick={() => onWaitlist(p.slug)}>
              <Bell className="h-3.5 w-3.5" aria-hidden="true" />
              Avise-me quando abrir
            </Button>
          ) : null}
        </div>
      </Card>
    </li>
  );
}

/**
 * Public product catalog. Purely presentational: the caller hands in the
 * published rows (only "No site" rows, with their derived status). Collapsed it
 * shows the featured picks; "Ver todos os produtos (N)" expands the full list in
 * place and reveals the status filter.
 */
export function ProductCatalogGrid({
  products, isLoading = false, isError = false, onRetry, onWaitlist,
  id = "produtos", eyebrow, title, description, emptyAction,
}: ProductCatalogGridProps) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const sectionRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const titleId = `${id}-title`;
  const regionId = `${id}-region`;

  const all = sortCatalog(products);
  const featured = selectFeaturedProducts(products);
  const canExpand = featured.length < all.length;
  const collapsed = !expanded && canExpand;

  const counts: Record<Filter, number> = { all: all.length, disponivel: 0, em_breve: 0, lista_de_espera: 0 };
  for (const p of all) counts[p.status] += 1;
  // Derived, not synced: a filter whose bucket emptied falls back to "all".
  const activeFilter: Filter = filter !== "all" && counts[filter] === 0 ? "all" : filter;

  const shown = collapsed ? featured : all.filter((p) => activeFilter === "all" || p.status === activeFilter);

  const countText = isLoading
    ? "Carregando produtos…"
    : collapsed
      ? `${shown.length} de ${all.length} produtos`
      : `${shown.length} ${shown.length === 1 ? "produto" : "produtos"}${activeFilter === "all" ? "" : ` · filtro: ${FILTER_LABEL[activeFilter]}`}`;

  const toggle = () => {
    const wasExpanded = expanded;
    setExpanded(!wasExpanded);
    setFilter("all");
    if (wasExpanded) sectionRef.current?.scrollIntoView?.();
    // keep focus on the toggle (it re-renders with a new label)
    requestAnimationFrame(() => toggleRef.current?.focus());
  };

  return (
    <section ref={sectionRef} id={id} aria-labelledby={titleId} className={cn(sectionClass, "bg-muted/40")}>
      <div className={wrapClass}>
        <Reveal>
          <SectionHead eyebrow={eyebrow} title={title} titleId={titleId} description={description} />

          {expanded && canExpand && !isLoading ? (
            <div role="group" aria-label="Filtrar produtos" className="mb-4 inline-flex flex-wrap gap-1 rounded-md border border-input p-0.5">
              {(["all", "disponivel", "em_breve", "lista_de_espera"] as const)
                .filter((k) => k === "all" || counts[k] > 0)
                .map((k) => (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={activeFilter === k}
                    onClick={() => setFilter(k)}
                    className={cn(
                      "h-7 rounded-sm px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      activeFilter === k ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {k === "all" ? "Todos" : FILTER_LABEL[k]} <span>({counts[k]})</span>
                  </button>
                ))}
            </div>
          ) : null}

          <div id={regionId} aria-busy={isLoading || undefined}>
            {isLoading ? (
              <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
                {Array.from({ length: MAX_FEATURED }, (_, i) => (
                  <li key={i}>
                    <Card className="flex flex-col gap-3 p-5">
                      <Skeleton announce={false} width={36} height={36} />
                      <Skeleton announce={false} width="55%" height={18} />
                      <Skeleton announce={false} width="90%" height={12} />
                      <Skeleton announce={false} width="70%" height={12} />
                    </Card>
                  </li>
                ))}
              </ul>
            ) : products.length === 0 && !isError ? (
              <Card className="flex flex-col items-start gap-3 p-6">
                <h3 className="text-base font-semibold text-foreground">Nenhum produto publicado no momento</h3>
                <p className="text-sm text-muted-foreground">
                  Conte o que você precisa no formulário abaixo e respondemos pelo WhatsApp.
                </p>
                {emptyAction ? <a href={emptyAction.href} className={linkButtonClass("outline", "md")}>{emptyAction.label}</a> : null}
              </Card>
            ) : (
              <>
                {isError ? (
                  <div role="alert" className="mb-4 rounded-lg border border-destructive p-4 text-sm text-foreground">
                    <strong className="block text-destructive">Não foi possível atualizar a lista agora.</strong>
                    {products.length > 0
                      ? "Mostramos a versão publicada no site; ela pode estar desatualizada. "
                      : "Tente de novo em instantes. "}
                    {onRetry ? <Button size="sm" className="mt-2" onClick={onRetry}>Tentar de novo</Button> : null}
                  </div>
                ) : null}
                <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {shown.map((p) => <ProductCard key={p.slug} p={p} onWaitlist={onWaitlist} />)}
                </ul>
              </>
            )}
          </div>

          <p role="status" className="mt-3 text-sm text-muted-foreground">
            {products.length === 0 && !isLoading ? "" : countText}
          </p>

          {canExpand && !isLoading ? (
            <div className="mt-4">
              <Button
                ref={toggleRef}
                variant={collapsed ? "outline" : "ghost"}
                className={collapsed ? "h-10 px-5 text-base" : undefined}
                aria-controls={regionId}
                aria-expanded={!collapsed}
                onClick={toggle}
              >
                {collapsed ? (
                  <>Ver todos os produtos ({all.length}) <ChevronDown className="h-4 w-4" aria-hidden="true" /></>
                ) : (
                  "Mostrar só os destaques"
                )}
              </Button>
            </div>
          ) : null}
        </Reveal>
      </div>
    </section>
  );
}
