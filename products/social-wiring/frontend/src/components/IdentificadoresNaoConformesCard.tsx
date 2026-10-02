/**
 * `<IdentificadoresNaoConformesCard/>` — the human hand-in for stored document
 * numbers that do not fit their type (owner rule 2026-10-01: such a value is
 * never rewritten; it is shown here, with the reason, for a person to fix).
 *
 * Presentational: rows, paging state and the two callbacks come in as props;
 * `IdentificadoresNaoConformesPanel` is the container that wires the hooks.
 * Mounted in Configurações → Pendências, next to the data-conflict queue — the
 * place owners/admins already review data corrections (a duplicate-merge queue
 * lives at /clientes/revisao, a different decision).
 *
 * Loading state follows the two-signal rule: skeleton only when pending AND no
 * data; a background refetch keeps the list and shows a subtle "Atualizando".
 */
import { useState } from "react";
import { AlertTriangle, Check, ExternalLink, Loader2, Pencil, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCorrigirIdentificador,
  useIdentificadoresNaoConformes,
  type IdentificadorNaoConforme,
  type IdentificadoresNaoConformesPage,
} from "@/hooks/useIdentificadoresNaoConformes";

const TESTID = "identificadores-nao-conformes";

function hrefDe(link: IdentificadorNaoConforme["link"]): string | null {
  if (!link) return null;
  return link.tipo === "cliente"
    ? `/clientes/${encodeURIComponent(link.id)}`
    : `/imoveis/${encodeURIComponent(link.id)}`;
}

export interface IdentificadoresNaoConformesCardProps {
  data: IdentificadoresNaoConformesPage | undefined;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
  onRetry: () => void;
  page: number;
  onPage: (page: number) => void;
  /** Resolves when the correction was accepted, rejects with the server message. */
  onSalvar: (item: IdentificadorNaoConforme, valor: string) => Promise<unknown>;
}

export function IdentificadoresNaoConformesCard({
  data, isPending, isFetching, isError, onRetry, page, onPage, onSalvar,
}: IdentificadoresNaoConformesCardProps) {
  const [editando, setEditando] = useState<string | null>(null);
  const [valor, setValor] = useState("");
  const [salvando, setSalvando] = useState<string | null>(null);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return (
      <Card data-testid={`${TESTID}-skeleton`}>
        <CardContent className="space-y-2 p-6">
          <Skeleton className="h-5 w-64" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }
  if (isError && !data) {
    return (
      <Card data-testid={`${TESTID}-erro`}>
        <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-sm text-muted-foreground">
            Não foi possível carregar os identificadores fora do padrão.
          </p>
          <Button variant="outline" size="sm" onClick={onRetry}>Tentar novamente</Button>
        </CardContent>
      </Card>
    );
  }
  if (!data || data.total === 0) {
    return (
      <Card data-testid={`${TESTID}-vazio`}>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          Nenhum número de documento fora do padrão no momento.
        </CardContent>
      </Card>
    );
  }

  const ultimaPagina = Math.max(1, Math.ceil(data.total / data.page_size));

  async function salvar(item: IdentificadorNaoConforme) {
    if (!item.edicao || !valor.trim()) return;
    setSalvando(item.chave);
    try {
      await onSalvar(item, valor.trim());
      setEditando(null);
      toast.success("Valor corrigido.");
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Não foi possível corrigir o valor.");
    } finally {
      setSalvando(null);
    }
  }

  return (
    <Card data-testid={TESTID}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <CardTitle className="text-sm">
            Números de documento fora do padrão ({data.total})
          </CardTitle>
          {isRefreshing && (
            <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground" data-testid={`${TESTID}-atualizando`}>
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Valores guardados como foram digitados ou lidos, que não se encaixam no tipo do campo.
          Nada é reescrito sozinho — corrija aqui.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.items.map((item) => {
          const href = hrefDe(item.link);
          const emEdicao = editando === item.chave;
          return (
            <div key={item.chave} className="rounded-md border p-3 text-sm" data-testid={`${TESTID}-item-${item.chave}`}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-medium">{item.rotulo_campo}</span>
                <span className="text-muted-foreground">·</span>
                {href ? (
                  <Link to={href} className="inline-flex items-center gap-1 underline-offset-2 hover:underline" data-testid={`${TESTID}-link-${item.chave}`}>
                    {item.entidade_nome}
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                ) : (
                  <span>{item.entidade_nome}</span>
                )}
              </div>
              <p className="mt-1">
                Guardado: <code className="rounded bg-muted px-1">{item.valor}</code>
              </p>
              <p className="mt-0.5 text-xs text-amber-800 dark:text-amber-300" data-testid={`${TESTID}-motivo-${item.chave}`}>
                {item.motivo}
              </p>
              <div className="mt-2">
                {emEdicao ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      className="h-8 max-w-xs"
                      value={valor}
                      onChange={(e) => setValor(e.target.value)}
                      aria-label={`Novo valor de ${item.rotulo_campo}`}
                      data-testid={`${TESTID}-input-${item.chave}`}
                      autoFocus
                    />
                    <Button size="sm" className="h-8" disabled={!valor.trim() || salvando === item.chave}
                      onClick={() => void salvar(item)} data-testid={`${TESTID}-salvar-${item.chave}`}>
                      {salvando === item.chave ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Check className="mr-1 h-3 w-3" />}
                      Salvar
                    </Button>
                    <Button size="sm" variant="ghost" className="h-8" onClick={() => setEditando(null)}>
                      <X className="mr-1 h-3 w-3" /> Cancelar
                    </Button>
                  </div>
                ) : item.edicao ? (
                  <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={() => { setEditando(item.chave); setValor(item.valor); }}
                    data-testid={`${TESTID}-editar-${item.chave}`}>
                    <Pencil className="mr-1 h-3 w-3" /> Corrigir valor
                  </Button>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Corrija no cadastro da pessoa{href ? " (link acima)" : ""} — este valor é a chave de uma consulta já emitida.
                  </p>
                )}
              </div>
            </div>
          );
        })}
        {ultimaPagina > 1 && (
          <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground">
            <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} data-testid={`${TESTID}-anterior`}>Anterior</Button>
            <span>Página {page} de {ultimaPagina}</span>
            <Button size="sm" variant="ghost" disabled={page >= ultimaPagina} onClick={() => onPage(page + 1)} data-testid={`${TESTID}-proxima`}>Próxima</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Container: wires the hooks to the presentational card. */
export function IdentificadoresNaoConformesPanel() {
  const [page, setPage] = useState(1);
  const query = useIdentificadoresNaoConformes(page);
  const corrigir = useCorrigirIdentificador();
  return (
    <IdentificadoresNaoConformesCard
      data={query.data}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => void query.refetch()}
      page={page}
      onPage={setPage}
      onSalvar={(item, valor) => corrigir.mutateAsync({ alvo: item.edicao!, valor })}
    />
  );
}
