/**
 * Block-type catalog (`/media-creation/biblioteca/tipos-de-bloco`, platform admin, contract §11.3):
 * CRUD over `TipoBloco`. A type in use is deactivated, never deleted (409 `tipo_em_uso` is explained);
 * `Outro` is a system row (409 `tipo_protegido`, shown read-only).
 */
import { QueryErrorState, useConfirm } from "@noctusai/lib/components";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { codigoDoErro, mensagemEstruturas } from "@/components/geracao/biblioteca/estruturas/erros";
import { ehTipoDeSistema, TipoBlocoDialog } from "@/components/geracao/biblioteca/estruturas/TipoBlocoDialog";
import {
  useEstruturasAdmin,
  useExcluirTipoBloco,
  useSalvarTipoBloco,
  useTiposBloco,
  type TipoBlocoAdmin,
} from "@/hooks/geracao/useEstruturas";
import { cn } from "@/lib/utils";

const VOLTAR = "/media-creation/biblioteca?aba=estruturas";

export default function BibliotecaTiposBloco() {
  const confirmar = useConfirm();
  const adminQ = useEstruturasAdmin();
  const isAdmin = adminQ.data === true;
  const q = useTiposBloco();
  const salvar = useSalvarTipoBloco();
  const excluir = useExcluirTipoBloco();
  const [editando, setEditando] = useState<TipoBlocoAdmin | null>(null);
  const [aberto, setAberto] = useState(false);
  const tipos = (q.data ?? []) as TipoBlocoAdmin[];

  function abrir(t: TipoBlocoAdmin | null) {
    setEditando(t);
    setAberto(true);
  }

  async function alternarAtivo(t: TipoBlocoAdmin) {
    try {
      await salvar.mutateAsync({
        id: t.id,
        nome: t.nome,
        tempo_tipico: t.tempo_tipico,
        instrucao_referencia: t.instrucao_referencia,
        ativo: !t.ativo,
        expected_versao: t.versao,
      });
      toast.success(t.ativo ? "Tipo desativado." : "Tipo ativado.");
    } catch (e) {
      toast.error(mensagemEstruturas(e, "Não foi possível alterar o tipo."));
    }
  }

  async function apagar(t: TipoBlocoAdmin) {
    if (!(await confirmar({ title: `Excluir o tipo "${t.nome}"?`, description: "Só é possível se nenhum bloco o usa; senão, desative-o.", confirmLabel: "Excluir", tone: "danger" }))) return;
    try {
      await excluir.mutateAsync(t.id);
      toast.success("Tipo excluído.");
    } catch (e) {
      toast.error(
        codigoDoErro(e) === "tipo_em_uso"
          ? "Este tipo de bloco está em uso. Desative-o em vez de excluir."
          : mensagemEstruturas(e, "Não foi possível excluir o tipo."),
      );
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6">
      <Link to={VOLTAR} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Voltar para a Biblioteca
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Tipos de bloco</h1>
          <p className="text-sm text-muted-foreground">
            O catálogo canônico que classifica cada bloco de uma estrutura. A instrução de referência vale quando um bloco não tem instrução própria.
          </p>
        </div>
        {isAdmin && <Button onClick={() => abrir(null)}>Novo tipo</Button>}
      </header>

      {adminQ.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : adminQ.isError ? (
        <QueryErrorState query={adminQ} title="Não foi possível verificar seu acesso." />
      ) : !isAdmin ? (
        <p role="alert" className="rounded-md border border-dashed p-8 text-center text-sm">
          Esta página é restrita a administradores da plataforma.
        </p>
      ) : q.showSkeleton ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Carregando tipos de bloco">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <QueryErrorState query={q} title="Não foi possível carregar os tipos de bloco." />
      ) : tipos.length === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center text-sm">
          <p className="font-medium">Nenhum tipo de bloco</p>
          <p className="mt-1 text-muted-foreground">O catálogo é carregado com a migração; se está vazio, algo falhou ao aplicá-la.</p>
        </div>
      ) : (
        <ul className={cn("flex flex-col gap-2", q.isRefreshing && "opacity-70")} aria-busy={q.isRefreshing}>
          {tipos.map((t) => (
            <li key={t.id} className="flex flex-wrap items-start gap-3 rounded-lg border bg-card p-3" data-testid={`tipo-${t.id}`}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">{t.nome}</h2>
                  {t.tempo_tipico && <span className="text-xs text-muted-foreground">{t.tempo_tipico}</span>}
                  {!t.ativo && <Badge variant="outline">Inativo</Badge>}
                  {ehTipoDeSistema(t) && <Badge variant="secondary">Sistema</Badge>}
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{t.instrucao_referencia}</p>
              </div>
              {!ehTipoDeSistema(t) && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => abrir(t)} aria-label={`Editar o tipo ${t.nome}`}>
                    Editar
                  </Button>
                  <Button size="sm" variant="outline" disabled={salvar.isPending} onClick={() => void alternarAtivo(t)} aria-label={`${t.ativo ? "Desativar" : "Ativar"} o tipo ${t.nome}`}>
                    {t.ativo ? "Desativar" : "Ativar"}
                  </Button>
                  <Button size="sm" variant="outline" className="text-destructive" disabled={excluir.isPending} onClick={() => void apagar(t)} aria-label={`Excluir o tipo ${t.nome}`}>
                    Excluir
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <TipoBlocoDialog open={aberto} onOpenChange={setAberto} tipo={editando} />
    </div>
  );
}
