/**
 * "Perfis" tab of the Biblioteca: the platform-wide library of monitored creators (contract §4.2/§11.3),
 * searchable and paged (`{items,total}`). Every profile links to its page (its Estruturas + videos).
 * Admin: "Adicionar perfil" (a library write). Members browse only.
 */
import { QueryErrorState } from "@noctusai/lib/components";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { compactoPtBr } from "@/components/pesquisa/format";
import { PERFIS_POR_PAGINA, usePerfisBiblioteca } from "@/hooks/geracao/useBiblioteca";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/utils";
import type { PerfilBiblioteca } from "@/types/bibliotecaPlataforma";
import { ROTULO_PERFIL_STATUS } from "./estruturas/rotulos";
import { SolicitarPerfil } from "./SolicitarPerfil";

export const rotaPerfil = (id: string) => `/media-creation/biblioteca/perfis/${encodeURIComponent(id)}`;

export function PerfisTab({ marcaId, isAdmin }: { marcaId: string | null; isAdmin: boolean }) {
  const [texto, setTexto] = useState("");
  const [pagina, setPagina] = useState(1);
  const [adicionando, setAdicionando] = useState(false);
  const q = useDebouncedValue(texto, 350);
  const perfisQ = usePerfisBiblioteca({ marcaId, q, limit: PERFIS_POR_PAGINA, offset: (pagina - 1) * PERFIS_POR_PAGINA });
  const total = perfisQ.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / PERFIS_POR_PAGINA));

  return (
    <section aria-label="Perfis" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-60 flex-1 flex-col gap-1.5">
          <Label htmlFor="perfis-busca">Buscar perfis</Label>
          <Input
            id="perfis-busca"
            type="search"
            placeholder="@handle ou nome"
            value={texto}
            maxLength={100}
            onChange={(e) => {
              setTexto(e.target.value);
              setPagina(1);
            }}
          />
        </div>
        {isAdmin && (
          <Button type="button" onClick={() => setAdicionando(true)}>
            Adicionar perfil
          </Button>
        )}
      </div>

      <h2 className="text-lg font-semibold">Perfis{perfisQ.data ? ` (${total.toLocaleString("pt-BR")})` : ""}</h2>

      {perfisQ.showSkeleton ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label="Carregando perfis">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : perfisQ.isError && !perfisQ.data ? (
        <QueryErrorState query={perfisQ} title="Não foi possível carregar os perfis." />
      ) : total === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center text-sm">
          <p className="font-medium">Nenhum perfil encontrado</p>
          <p className="mt-1 text-muted-foreground">
            {q.trim()
              ? "Nenhum perfil corresponde à busca. Tente outro nome ou @handle."
              : isAdmin
                ? 'A biblioteca ainda não tem perfis. Use "Adicionar perfil" ou importe estruturas.'
                : "A biblioteca ainda não tem perfis. Volte em breve."}
          </p>
        </div>
      ) : (
        <>
          <ul className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-3", perfisQ.isRefreshing && "opacity-70")} aria-busy={perfisQ.isRefreshing}>
            {perfisQ.data?.items.map((p) => (
              <li key={p.id}>
                <PerfilCard perfil={p} />
              </li>
            ))}
          </ul>
          {paginas > 1 && (
            <nav aria-label="Paginação dos perfis" className="flex items-center justify-center gap-3 text-sm">
              <Button size="sm" variant="outline" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </Button>
              <span>
                Página {pagina} de {paginas}
              </span>
              <Button size="sm" variant="outline" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)}>
                Próxima
              </Button>
            </nav>
          )}
        </>
      )}

      {isAdmin && (
        <Dialog open={adicionando} onOpenChange={setAdicionando}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Adicionar perfil à biblioteca</DialogTitle>
              <DialogDescription>Perfis da biblioteca são da plataforma; as organizações escolhem quais usar.</DialogDescription>
            </DialogHeader>
            <SolicitarPerfil marcaId={marcaId ?? undefined} />
          </DialogContent>
        </Dialog>
      )}
    </section>
  );
}

function PerfilCard({ perfil: p }: { perfil: PerfilBiblioteca }) {
  return (
    <article
      className="relative flex items-center gap-3 rounded-lg border bg-card p-4 shadow-xs focus-within:ring-2 focus-within:ring-ring hover:border-primary/50"
      data-testid={`perfil-card-${p.id}`}
    >
      {p.foto_url ? (
        <img src={p.foto_url} alt="" loading="lazy" className="h-12 w-12 shrink-0 rounded-full object-cover" />
      ) : (
        <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold uppercase text-primary-foreground">
          {p.handle.slice(0, 2)}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-medium">
          <Link to={rotaPerfil(p.id)} className="after:absolute after:inset-0 focus-visible:outline-hidden">
            @{p.handle}
          </Link>
        </h3>
        {p.nome && <p className="truncate text-xs text-muted-foreground">{p.nome}</p>}
        <p className="mt-1 text-xs text-muted-foreground">
          {compactoPtBr(p.seguidores)} seguidores
          {p.estruturas_total != null ? ` · ${p.estruturas_total === 1 ? "1 estrutura" : `${p.estruturas_total} estruturas`}` : ""}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1">
        {p.monitorar === false ? <Badge variant="outline">Somente biblioteca</Badge> : <Badge variant="secondary">{ROTULO_PERFIL_STATUS[p.status] ?? p.status}</Badge>}
        {p.selecionado_pela_marca && <Badge variant="outline">Na sua biblioteca</Badge>}
      </div>
    </article>
  );
}
