/**
 * VideoPicker — choose ONE library viral (contract §7.8, Roteiro Avançado).
 *
 * STABLE PUBLIC API (FE-3 builds against it; do not change required props):
 *
 *   import { VideoPicker } from "@/components/geracao/biblioteca/VideoPicker";
 *   <VideoPicker marcaId={string} value={string | null}
 *                onChange={(viralId: string | null) => void} />
 *
 * Optional props: `disabled`, `className`. Selecting a card calls
 * `onChange(viralId)`; "remover" calls `onChange(null)`.
 * Filters: text search, Formato, Perfil, Nicho, Views mínimas, Likes mínimas.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  usePerfisMonitorados,
  useViraisBiblioteca,
  useViralDetalhe,
  VIRAIS_POR_PAGINA,
} from "@/hooks/geracao/useBiblioteca";
import { useTaxonomias } from "@/hooks/geracao/useTaxonomias";
import { compactoPtBr } from "@/components/pesquisa/format";
import { cn } from "@/lib/utils";
import { FILTROS_VAZIOS, type FiltrosViral } from "./filtros";
import { ViralCard } from "./ViralCard";

export interface VideoPickerProps {
  marcaId: string;
  value: string | null;
  onChange: (viralId: string | null) => void;
  disabled?: boolean;
  className?: string;
}

const VIEWS_MIN = [100_000, 500_000, 1_000_000, 5_000_000];
const LIKES_MIN = [10_000, 50_000, 100_000, 500_000];

const FILTROS_PICKER: FiltrosViral = { ...FILTROS_VAZIOS, verTodos: true };

const selectCls = "h-9 rounded-md border border-input bg-background px-2 text-sm";

export function VideoPicker({ marcaId, value, onChange, disabled, className }: VideoPickerProps) {
  const [aberto, setAberto] = useState(false);
  const [filtros, setFiltros] = useState<FiltrosViral>(FILTROS_PICKER);
  const set = <K extends keyof FiltrosViral>(k: K, v: FiltrosViral[K]) =>
    setFiltros((f) => ({ ...f, [k]: v, page: k === "page" ? (v as number) : 1 }));

  const escolhido = useViralDetalhe(marcaId, value);
  const virais = useViraisBiblioteca(aberto ? marcaId : null, filtros);
  const tax = useTaxonomias().data;
  const perfis = usePerfisMonitorados().data ?? [];

  const total = virais.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / VIRAIS_POR_PAGINA));

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {value ? (
        <div className="flex items-center gap-3 rounded-md border p-2" data-testid="video-escolhido">
          {escolhido.data?.thumbnail_url ? (
            <img src={escolhido.data.thumbnail_url} alt="" className="h-16 w-9 rounded object-cover" />
          ) : (
            <div className="h-16 w-9 rounded bg-muted" />
          )}
          <div className="min-w-0 flex-1 text-sm">
            <div className="truncate font-medium">
              {escolhido.data ? `@${escolhido.data.perfil.handle}` : "Vídeo selecionado"}
            </div>
            {escolhido.data && (
              <div className="text-xs text-muted-foreground">
                ♥ {compactoPtBr(escolhido.data.likes)} · 💬 {compactoPtBr(escolhido.data.comments)}
              </div>
            )}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            remover
          </Button>
        </div>
      ) : null}
      <Button
        type="button"
        variant="outline"
        className="w-fit"
        disabled={disabled}
        onClick={() => setAberto(true)}
      >
        {value ? "Trocar vídeo da biblioteca" : "Abrir biblioteca e escolher vídeo"}
      </Button>

      <Dialog open={aberto} onOpenChange={setAberto}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Escolher vídeo da biblioteca</DialogTitle>
            <DialogDescription>Clique em um vídeo para usá-lo como referência.</DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-end gap-2">
            <Input
              aria-label="Buscar por texto"
              placeholder="Buscar por texto"
              className="w-56"
              value={filtros.q}
              onChange={(e) => set("q", e.target.value)}
            />
            <select
              aria-label="Formato"
              className={selectCls}
              value={filtros.formatoId ?? ""}
              onChange={(e) => set("formatoId", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Formato</option>
              {(tax?.formatos ?? []).map((f) => (
                <option key={f.id} value={f.id}>
                  {f.nome}
                </option>
              ))}
            </select>
            <select
              aria-label="Perfil"
              className={selectCls}
              value={filtros.perfilId}
              onChange={(e) => set("perfilId", e.target.value)}
            >
              <option value="">Perfil</option>
              {perfis.map((p) => (
                <option key={p.id} value={p.id}>
                  @{p.handle}
                </option>
              ))}
            </select>
            <select
              aria-label="Nicho"
              className={selectCls}
              value={filtros.nichos[0] ?? ""}
              onChange={(e) => set("nichos", e.target.value ? [Number(e.target.value)] : [])}
            >
              <option value="">Nicho</option>
              {(tax?.nichos ?? []).map((n) => (
                <option key={n.id} value={n.id}>
                  {n.nome}
                </option>
              ))}
            </select>
            <select
              aria-label="Views mínimas"
              className={selectCls}
              value={filtros.viewsMin ?? ""}
              onChange={(e) => set("viewsMin", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Views mínimas</option>
              {VIEWS_MIN.map((n) => (
                <option key={n} value={n}>
                  {compactoPtBr(n)}+
                </option>
              ))}
            </select>
            <select
              aria-label="Likes mínimas"
              className={selectCls}
              value={filtros.likesMin ?? ""}
              onChange={(e) => set("likesMin", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Likes mínimas</option>
              {LIKES_MIN.map((n) => (
                <option key={n} value={n}>
                  {compactoPtBr(n)}+
                </option>
              ))}
            </select>
          </div>

          {virais.showSkeleton ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[9/16] w-full" />
              ))}
            </div>
          ) : virais.isError ? (
            <div className="text-sm text-destructive">
              Não foi possível carregar a biblioteca.{" "}
              <Button variant="link" className="h-auto p-0" onClick={() => virais.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : (virais.data?.items.length ?? 0) === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nenhum viral encontrado. A monitoração de perfis pode ainda não estar ativa.
            </p>
          ) : (
            <div
              className={cn(
                "grid grid-cols-2 gap-3 md:grid-cols-4",
                virais.isRefreshing && "opacity-70",
              )}
            >
              {virais.data?.items.map((v) => (
                <ViralCard
                  key={v.id}
                  viral={v}
                  onAbrir={() => {
                    onChange(v.id);
                    setAberto(false);
                  }}
                />
              ))}
            </div>
          )}

          {paginas > 1 && (
            <div className="flex items-center justify-center gap-3 text-sm">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={filtros.page <= 1}
                onClick={() => set("page", filtros.page - 1)}
              >
                Anterior
              </Button>
              <span>
                Página {filtros.page} de {paginas}
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={filtros.page >= paginas}
                onClick={() => set("page", filtros.page + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default VideoPicker;
