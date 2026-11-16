/**
 * Import report (`/media-creation/biblioteca/importacoes`, platform admin, contract §11.3). READ-ONLY: the
 * load itself is the `noctus.sw.estruturas_import` tool (plan → apply); this page shows each run's counts and
 * reason codes (never row text) and follows one that is `em_andamento`.
 */
import { QueryErrorState } from "@noctusai/lib/components";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { dataHoraPtBr } from "@/components/pesquisa/format";
import { cn } from "@/lib/utils";
import { useEstruturasAdmin, useImportacoes } from "@/hooks/geracao/useEstruturas";
import type { ImportacaoRelatorio } from "@/types/estruturas";

const POR_PAGINA = 20;
const VOLTAR = "/media-creation/biblioteca?aba=estruturas";

const ROTULO_FONTE: Record<ImportacaoRelatorio["fonte"], string> = {
  referencia: "Estruturas de referência",
  maquina_de_roteiros: "Máquina de Roteiros",
};
const ROTULO_STATUS_IMPORTACAO: Record<ImportacaoRelatorio["status"], string> = {
  simulada: "Simulada",
  em_andamento: "Em andamento",
  concluida: "Concluída",
  falhou: "Falhou",
};
const MOTIVOS: Record<string, string> = {
  handle_invalido: "perfil com @handle inválido",
  id_invalido: "id externo inválido",
  tipo_desconhecido: "tipo de bloco desconhecido",
};
const n = (v: number) => v.toLocaleString("pt-BR");

export default function BibliotecaImportacoes() {
  const adminQ = useEstruturasAdmin();
  const [pagina, setPagina] = useState(1);
  const isAdmin = adminQ.data === true;
  const q = useImportacoes(POR_PAGINA, (pagina - 1) * POR_PAGINA, isAdmin);
  const total = q.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  return (
    <div className="flex flex-col gap-5 p-6">
      <Link to={VOLTAR} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Voltar para a Biblioteca
      </Link>
      <header>
        <h1 className="text-2xl font-semibold">Importações de estruturas</h1>
        <p className="text-sm text-muted-foreground">
          Relatório de cada carga. A carga é feita pela ferramenta <code>noctus.sw.estruturas_import</code> (simular e depois
          aplicar); aqui você só confere os números.
        </p>
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
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Carregando importações">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <QueryErrorState query={q} title="Não foi possível carregar as importações." />
      ) : total === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center text-sm">
          <p className="font-medium">Nenhuma importação ainda</p>
          <p className="mt-1 text-muted-foreground">Rode a simulação com a ferramenta de importação; o relatório aparece aqui.</p>
        </div>
      ) : (
        <>
          <ul className={cn("flex flex-col gap-3", q.isRefreshing && "opacity-70")} aria-busy={q.isRefreshing}>
            {q.data?.items.map((i) => (
              <li key={i.id}>
                <Relatorio r={i} />
              </li>
            ))}
          </ul>
          {paginas > 1 && (
            <nav aria-label="Paginação das importações" className="flex items-center justify-center gap-3 text-sm">
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
    </div>
  );
}

function Relatorio({ r }: { r: ImportacaoRelatorio }) {
  const motivos = Object.entries(r.ignoradas_motivos);
  const contagens: [string, number][] = [
    ["Linhas", r.linhas_total],
    ["Criadas", r.estruturas_criadas],
    ["Atualizadas", r.estruturas_atualizadas],
    ["Inalteradas", r.estruturas_inalteradas],
    ["Ignoradas", r.estruturas_ignoradas],
    ["Blocos criados", r.blocos_criados],
    ["Perfis criados", r.perfis_criados],
    ["Perfis mesclados", r.perfis_mesclados],
  ];
  return (
    <article className="rounded-lg border bg-card p-4" data-testid={`importacao-${r.id}`}>
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">{ROTULO_FONTE[r.fonte]}</h2>
        <Badge variant={r.status === "falhou" ? "destructive" : r.status === "concluida" ? "secondary" : "outline"}>
          {ROTULO_STATUS_IMPORTACAO[r.status]}
        </Badge>
        {r.dry_run && <Badge variant="outline">Simulação (nada foi gravado)</Badge>}
        <span className="text-xs text-muted-foreground">
          {dataHoraPtBr(r.created_at)}
          {r.finished_at ? ` → ${dataHoraPtBr(r.finished_at)}` : ""} · arquivo {r.arquivo_sha256.slice(0, 12)}
        </span>
      </header>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        {contagens.map(([rotulo, valor]) => (
          <div key={rotulo}>
            <dt className="text-xs text-muted-foreground">{rotulo}</dt>
            <dd className="font-medium tabular-nums">{n(valor)}</dd>
          </div>
        ))}
      </dl>
      {r.erro && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          Erro: {r.erro}
        </p>
      )}
      {motivos.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="text-xs text-muted-foreground">Linhas ignoradas por motivo</p>
          <ul className="list-disc pl-5">
            {motivos.map(([motivo, qtd]) => (
              <li key={motivo}>
                {n(qtd)} — {MOTIVOS[motivo] ?? motivo}
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.campos_nao_importados.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">Campos não importados (mantidos na origem): {r.campos_nao_importados.join(", ")}</p>
      )}
    </article>
  );
}
