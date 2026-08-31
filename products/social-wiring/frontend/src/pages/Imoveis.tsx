/**
 * Imóveis — the catalog page.
 *
 * Reads the local mirror of the Vista catalog (`social_wiring.imoveis`).
 * "Sincronizar" triggers the full pull; everything else is local.
 *
 * States: loading / error / empty-because-never-synced / empty-because-filtered
 * / success. The two empty states are deliberately different — "you have no
 * imóveis" and "your filters match nothing" need opposite calls to action, and
 * collapsing them is how a user concludes the sync is broken.
 *
 * Route: /imoveis. Nav entry lives in BOTH NAV_GROUPS and NAV_FALLBACK in
 * App.tsx, and needs its `status_pagina` row (migration 040) or the seed's
 * filterNavByPageStatus gate hides the link with no error anywhere.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle,
  Bath,
  BedDouble,
  Building2,
  Car,
  Loader2,
  MapPin,
  RefreshCw,
  Ruler,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import {
  caracteristicaLabel,
  formatArea,
  formatCount,
  formatValor,
  useCaracteristicas,
  useImoveis,
  useImovelFiltros,
  useSyncImoveis,
  type Imovel,
  type ImovelFilters,
} from "@/hooks/useImoveis";

const PAGE_SIZE = 24;
/** How many amenity chips to offer before "ver todas". */
const TOP_CARACTERISTICAS = 12;

const ALL = "__all__";

export default function Imoveis() {
  const [filters, setFilters] = useState<ImovelFilters>({
    page: 1,
    page_size: PAGE_SIZE,
  });
  const [searchDraft, setSearchDraft] = useState("");

  const imoveis = useImoveis(filters);
  const filtros = useImovelFiltros();
  const caracteristicas = useCaracteristicas();
  const sync = useSyncImoveis();

  // First load only — `isPending && !data`, never `isLoading` (TanStack v5's
  // `isLoading` is false mid-refetch, so an isEmpty branch keyed on it renders
  // "nenhum imóvel" over data that exists) and never a bare `|| isFetching`
  // either (that gate replaced the whole 8-card grid with skeletons on every
  // filter/sync refetch — the query has `placeholderData`, so the real data
  // is present the entire time and was being thrown away by this render
  // gate).
  const loading = imoveis.isPending && !imoveis.data;
  const page = imoveis.data;
  const hasFilters = Boolean(
    filters.status ||
      filters.categoria ||
      filters.cidade ||
      filters.bairro ||
      filters.search ||
      (filters.caracteristicas?.length ?? 0) > 0,
  );
  const isEmpty = !loading && (page?.items.length ?? 0) === 0;

  const topCaracteristicas = useMemo(() => {
    const entries = Object.entries(caracteristicas.data ?? {});
    // Server already orders by usage and omits zeroes; this only truncates.
    return entries.slice(0, TOP_CARACTERISTICAS);
  }, [caracteristicas.data]);

  function patch(next: Partial<ImovelFilters>) {
    setFilters((f) => ({ ...f, ...next, page: 1 }));
  }

  function toggleCaracteristica(slug: string) {
    setFilters((f) => {
      const current = f.caracteristicas ?? [];
      const next = current.includes(slug)
        ? current.filter((s) => s !== slug)
        : [...current, slug];
      return { ...f, caracteristicas: next, page: 1 };
    });
  }

  function clearFilters() {
    setSearchDraft("");
    setFilters({ page: 1, page_size: PAGE_SIZE });
  }

  async function handleSync() {
    try {
      const result = await sync.mutateAsync(true);
      if (result.complete) {
        toast.success(
          `${result.upserted} imóveis sincronizados em ${Math.round(result.duration_seconds)}s.`,
        );
      } else {
        // Never report a partial sync as success. The imóveis whose detalhes
        // failed have no características and will silently miss every amenity
        // filter — the user needs to know that before trusting the results.
        toast.warning(
          `${result.upserted} sincronizados, mas ${result.detalhes_failed_count} sem detalhes` +
            `${result.page_failures.length ? ` e ${result.page_failures.length} página(s) com falha` : ""}. ` +
            `Esses imóveis ficam sem características. Tente sincronizar novamente.`,
          { duration: 10000 },
        );
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao sincronizar com o Vista.",
      );
    }
  }

  return (
    <div className="space-y-6 p-6">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Imóveis</h1>
          <p className="text-sm text-muted-foreground">
            {page ? `${page.total.toLocaleString("pt-BR")} imóveis` : "Carregando…"}
            {page?.items[0]?.sincronizado_em
              ? ` · atualizado ${new Date(page.items[0].sincronizado_em).toLocaleDateString("pt-BR")}`
              : ""}
          </p>
        </div>
        <Button onClick={handleSync} disabled={sync.isPending} variant="outline">
          {sync.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Sincronizando… (pode levar alguns minutos)
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              Sincronizar
            </>
          )}
        </Button>
      </div>

      {/* ── Filters ── */}
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap gap-3">
            <div className="relative min-w-[220px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Código, título ou bairro…"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") patch({ search: searchDraft || undefined });
                }}
              />
            </div>

            <FilterSelect
              label="Status"
              value={filters.status}
              options={filtros.data?.status ?? []}
              onChange={(v) => patch({ status: v })}
            />
            <FilterSelect
              label="Categoria"
              value={filters.categoria}
              options={filtros.data?.categoria ?? []}
              onChange={(v) => patch({ categoria: v })}
            />
            <FilterSelect
              label="Cidade"
              value={filters.cidade}
              options={filtros.data?.cidade ?? []}
              onChange={(v) => patch({ cidade: v })}
            />

            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="mr-1 h-4 w-4" />
                Limpar
              </Button>
            )}
          </div>

          {topCaracteristicas.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {topCaracteristicas.map(([slug, count]) => {
                const active = filters.caracteristicas?.includes(slug);
                return (
                  <button
                    key={slug}
                    type="button"
                    onClick={() => toggleCaracteristica(slug)}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border hover:bg-muted"
                    }`}
                  >
                    {caracteristicaLabel(slug)}
                    <span className="ml-1 opacity-60">{count}</span>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Body ── */}
      {imoveis.isError ? (
        <ErrorState onRetry={() => imoveis.refetch()} />
      ) : loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-72 w-full rounded-lg" />
          ))}
        </div>
      ) : isEmpty ? (
        hasFilters ? (
          <EmptyFiltered onClear={clearFilters} />
        ) : (
          <EmptyNeverSynced onSync={handleSync} syncing={sync.isPending} />
        )
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {page!.items.map((imovel) => (
              <ImovelCard key={imovel.codigo} imovel={imovel} />
            ))}
          </div>

          {page!.pages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page!.page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {page!.page} de {page!.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page!.page >= page!.pages}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Pieces ───────────────────────────────────────────────────────────────

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value?: string;
  options: string[];
  onChange: (v: string | undefined) => void;
}) {
  return (
    <Select
      value={value ?? ALL}
      onValueChange={(v) => onChange(v === ALL ? undefined : v)}
    >
      <SelectTrigger className="w-[170px]">
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}: todos</SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ImovelCard({ imovel }: { imovel: Imovel }) {
  const preco =
    imovel.valor_venda !== null
      ? formatValor(imovel.valor_venda)
      : imovel.valor_locacao !== null
        ? `${formatValor(imovel.valor_locacao)}/mês`
        : "Sob consulta";

  return (
    <Link to={`/imoveis/${imovel.codigo}`} className="group">
      <Card className="h-full overflow-hidden transition-shadow hover:shadow-md">
        <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted">
          {imovel.foto_destaque ? (
            <img
              src={imovel.foto_destaque}
              alt={imovel.titulo ?? imovel.codigo}
              loading="lazy"
              className="h-full w-full object-cover transition-transform group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Building2 className="h-10 w-10" />
            </div>
          )}
          <Badge className="absolute left-2 top-2" variant="secondary">
            {imovel.codigo}
          </Badge>
          {imovel.status && (
            <Badge className="absolute right-2 top-2">{imovel.status}</Badge>
          )}
        </div>

        <CardContent className="space-y-2 p-4">
          <p className="line-clamp-2 text-sm font-medium leading-snug">
            {imovel.titulo ?? imovel.categoria ?? imovel.codigo}
          </p>
          <p className="text-lg font-semibold">{preco}</p>

          {(imovel.bairro || imovel.cidade) && (
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3 w-3 shrink-0" />
              <span className="truncate">
                {[imovel.bairro, imovel.cidade].filter(Boolean).join(" · ")}
              </span>
            </p>
          )}

          {/* formatCount, not `|| "—"`: 0 dormitórios on a terreno is data. */}
          <div className="flex flex-wrap gap-3 pt-1 text-xs text-muted-foreground">
            <Metric icon={<BedDouble className="h-3.5 w-3.5" />} value={formatCount(imovel.dormitorios)} />
            <Metric icon={<Car className="h-3.5 w-3.5" />} value={formatCount(imovel.vagas)} />
            {imovel.banheiro_social !== null && (
              <Metric
                icon={<Bath className="h-3.5 w-3.5" />}
                value={imovel.banheiro_social ? "Sim" : "Não"}
              />
            )}
            {imovel.area_total !== null && (
              <Metric icon={<Ruler className="h-3.5 w-3.5" />} value={formatArea(imovel.area_total)} />
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function Metric({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="flex items-center gap-1">
      {icon}
      {value}
    </span>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os imóveis.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyNeverSynced({
  onSync,
  syncing,
}: {
  onSync: () => void;
  syncing: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Building2 className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Nenhum imóvel sincronizado ainda.</p>
          <p className="text-sm text-muted-foreground">
            Importe o catálogo do Vista para começar.
          </p>
        </div>
        <Button onClick={onSync} disabled={syncing}>
          {syncing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Sincronizando…
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              Sincronizar com o Vista
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyFiltered({ onClear }: { onClear: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Search className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Nenhum imóvel corresponde aos filtros.</p>
          <p className="text-sm text-muted-foreground">
            Seu catálogo não está vazio — só esta combinação de filtros.
          </p>
        </div>
        <Button variant="outline" onClick={onClear}>
          Limpar filtros
        </Button>
      </CardContent>
    </Card>
  );
}
