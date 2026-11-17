/**
 * Filterable, paged list of Estruturas — the "Estruturas" tab of the Biblioteca and the Estruturas section
 * of a profile page (`perfilId` pins the profile). Controlled by `filtros` (URL state in the tab, local state
 * on the profile page). Admin-only filters ("Pendentes de revisão", "Rascunhos", status) render only for admins.
 *
 * Loading: `showSkeleton` / `isRefreshing` off `data`; an error with no data is a retryable block; empty says
 * WHY (no filters ⇒ nothing in the library yet; filters ⇒ nothing matches) and what to do next.
 */
import { QueryErrorState } from "@noctusai/lib/components";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useEstruturas, ESTRUTURAS_POR_PAGINA } from "@/hooks/geracao/useEstruturas";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/utils";
import { EstruturaCard } from "./EstruturaCard";
import { contarFiltros, FILTROS_ESTRUTURAS_VAZIOS, type FiltroStatus, type FiltrosEstruturas } from "./filtros";
import { FORMATOS, OBJETIVOS, ROTULO_FORMATO, ROTULO_OBJETIVO } from "./rotulos";

interface Props {
  filtros: FiltrosEstruturas;
  onFiltros: (f: FiltrosEstruturas) => void;
  isAdmin: boolean;
  marcaId?: string | null;
  /** Pin the list to one profile (the profile page). */
  perfilId?: string;
}

const STATUS_OPCOES: { valor: FiltroStatus; rotulo: string }[] = [
  { valor: "ativa", rotulo: "Ativas" },
  { valor: "rascunho", rotulo: "Rascunhos" },
  { valor: "arquivada", rotulo: "Arquivadas" },
  { valor: "todas", rotulo: "Todas" },
];

function alternar<T>(lista: T[], item: T): T[] {
  return lista.includes(item) ? lista.filter((x) => x !== item) : [...lista, item];
}

export function EstruturasLista({ filtros, onFiltros, isAdmin, marcaId, perfilId }: Props) {
  const [texto, setTexto] = useState(filtros.busca);
  const busca = useDebouncedValue(texto, 350);

  // The URL → input direction (back button, "Limpar filtros"): follow the filter when it changes elsewhere.
  useEffect(() => setTexto(filtros.busca), [filtros.busca]);
  // The input → URL direction, debounced; a new search always starts on page 1.
  useEffect(() => {
    if (busca.trim() !== filtros.busca.trim()) onFiltros({ ...filtros, busca: busca.trim(), pagina: 1 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the debounced text drives this
  }, [busca]);

  const q = useEstruturas({
    marcaId,
    perfilId,
    q: filtros.busca,
    formatos: filtros.formatos,
    objetivos: filtros.objetivos,
    // Members never send admin filters (the server ignores them anyway).
    status: isAdmin ? filtros.status : undefined,
    somentePendentesRevisao: isAdmin && filtros.pendentes,
    revisaoPorDesuso: isAdmin && filtros.desuso,
    limit: ESTRUTURAS_POR_PAGINA,
    offset: (filtros.pagina - 1) * ESTRUTURAS_POR_PAGINA,
  });

  const total = q.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / ESTRUTURAS_POR_PAGINA));
  const ativos = contarFiltros(filtros);
  const mudar = (m: Partial<FiltrosEstruturas>) => onFiltros({ ...filtros, ...m, pagina: 1 });

  return (
    <section aria-label="Estruturas" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-60 flex-1 flex-col gap-1.5">
          <Label htmlFor="estruturas-busca">Buscar estruturas</Label>
          <Input
            id="estruturas-busca"
            type="search"
            placeholder="Fórmula ou nome de bloco"
            value={texto}
            maxLength={200}
            onChange={(e) => setTexto(e.target.value)}
          />
        </div>
        {isAdmin && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="estruturas-status">Situação</Label>
            <select
              id="estruturas-status"
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              value={filtros.status}
              onChange={(e) => mudar({ status: e.target.value as FiltroStatus })}
            >
              {STATUS_OPCOES.map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.rotulo}
                </option>
              ))}
            </select>
          </div>
        )}
        {isAdmin && (
          <Button
            type="button"
            variant={filtros.pendentes ? "default" : "outline"}
            aria-pressed={filtros.pendentes}
            onClick={() => mudar({ pendentes: !filtros.pendentes })}
          >
            Pendentes de revisão
          </Button>
        )}
        {isAdmin && (
          <Button
            type="button"
            variant={filtros.desuso ? "default" : "outline"}
            aria-pressed={filtros.desuso}
            onClick={() => mudar({ desuso: !filtros.desuso })}
          >
            Sem uso há 24 meses
          </Button>
        )}
        {ativos > 0 && (
          <Button type="button" variant="ghost" onClick={() => onFiltros({ ...FILTROS_ESTRUTURAS_VAZIOS })}>
            Limpar filtros
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2" role="group" aria-label="Filtros de classificação">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Formato">
          <span className="text-sm text-muted-foreground">Formato:</span>
          {FORMATOS.map((f) => (
            <Button
              key={f}
              type="button"
              size="sm"
              variant={filtros.formatos.includes(f) ? "default" : "outline"}
              aria-pressed={filtros.formatos.includes(f)}
              onClick={() => mudar({ formatos: alternar(filtros.formatos, f) })}
            >
              {ROTULO_FORMATO[f]}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Objetivo">
          <span className="text-sm text-muted-foreground">Objetivo:</span>
          {OBJETIVOS.map((o) => (
            <Button
              key={o}
              type="button"
              size="sm"
              variant={filtros.objetivos.includes(o) ? "default" : "outline"}
              aria-pressed={filtros.objetivos.includes(o)}
              onClick={() => mudar({ objetivos: alternar(filtros.objetivos, o) })}
            >
              {ROTULO_OBJETIVO[o]}
            </Button>
          ))}
        </div>
      </div>

      <h2 className="text-lg font-semibold">Estruturas{q.data ? ` (${total.toLocaleString("pt-BR")})` : ""}</h2>

      {q.showSkeleton ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label="Carregando estruturas">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <QueryErrorState query={q} title="Não foi possível carregar as estruturas." />
      ) : total === 0 ? (
        <EstadoVazio filtrado={ativos > 0} isAdmin={isAdmin} doPerfil={!!perfilId} />
      ) : (
        <>
          <ul className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-3", q.isRefreshing && "opacity-70")} aria-busy={q.isRefreshing}>
            {q.data?.items.map((e) => (
              <li key={e.id}>
                <EstruturaCard estrutura={e} />
              </li>
            ))}
          </ul>
          {paginas > 1 && (
            <nav aria-label="Paginação das estruturas" className="flex items-center justify-center gap-3 text-sm">
              <Button size="sm" variant="outline" disabled={filtros.pagina <= 1} onClick={() => onFiltros({ ...filtros, pagina: filtros.pagina - 1 })}>
                Anterior
              </Button>
              <span>
                Página {filtros.pagina} de {paginas}
              </span>
              <Button size="sm" variant="outline" disabled={filtros.pagina >= paginas} onClick={() => onFiltros({ ...filtros, pagina: filtros.pagina + 1 })}>
                Próxima
              </Button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

function EstadoVazio({ filtrado, isAdmin, doPerfil }: { filtrado: boolean; isAdmin: boolean; doPerfil: boolean }) {
  return (
    <div className="rounded-md border border-dashed p-8 text-center text-sm">
      <p className="font-medium">Nenhuma estrutura encontrada</p>
      {filtrado ? (
        <p className="mt-1 text-muted-foreground">Nenhuma estrutura corresponde aos filtros atuais. Limpe os filtros para ver todas.</p>
      ) : doPerfil ? (
        <p className="mt-1 text-muted-foreground">
          Este perfil ainda não tem estruturas.{isAdmin ? " Quando um vídeo dele for analisado, um rascunho aparece aqui." : ""}
        </p>
      ) : (
        <p className="mt-1 text-muted-foreground">
          A biblioteca ainda não tem estruturas publicadas.{isAdmin ? " Elas chegam pela importação ou por rascunhos criados a partir dos vídeos analisados." : " Volte em breve."}
        </p>
      )}
    </div>
  );
}
