/**
 * Julia › Agente card "Especificações do negócio", READ-ONLY (owner 2026-11-04: SW users do not edit Julia's content for now; only
 * NoctusAI does). It shows the business data Julia uses, rendered generically from the declarations the active version carries
 * (rotulo / descricao per `tipo`), with "Alterado por … em …" and a note pointing to support. There are NO inputs and no save: the
 * write route answers 403 `edicao_restrita_plataforma` to an org admin. Loading = two signals off `data` (never `isLoading`).
 */
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatarDataHora } from "@/components/julia/ConexaoPlataforma";
import {
  leituraErroEspec,
  mensagemErroEspec,
  useJuliaEspecificacoes,
  type Especificacoes,
} from "@/hooks/useJuliaEspecificacoes";

export const NOTA_EDICAO_NOCTUS =
  "As especificações da Julia são configuradas pela equipe NoctusAI. Para alterar, fale com o suporte.";

function Lista({ data }: { data: Especificacoes }) {
  if (data.declaradas.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="espec-vazio">
        A Julia não pede nenhuma informação do seu negócio por enquanto.
      </p>
    );
  }
  const faltando = new Set(data.faltando);
  const problemas = new Map(data.invalidas.map((i) => [i.chave, i.mensagem]));
  return (
    <dl className="space-y-4" data-testid="espec-lista">
      {data.declaradas.map((d) => {
        const v = data.valores.find((x) => x.chave === d.chave);
        const problema = problemas.get(d.chave) ?? (faltando.has(d.chave) && !v?.valor?.trim() ? "Obrigatório: ainda não preenchido." : null);
        return (
          <div key={d.id} className="space-y-1" data-testid={`espec-campo-${d.chave}`}>
            <dt className="text-sm font-medium">{d.rotulo}</dt>
            <dd className="whitespace-pre-wrap text-sm" data-testid={`espec-valor-${d.chave}`}>
              {v?.valor?.trim() ? v.valor : <span className="text-muted-foreground">Não preenchido</span>}
            </dd>
            {v?.updated_by_nome && (
              <p className="text-xs text-muted-foreground" data-testid={`espec-alterado-${d.chave}`}>
                Alterado por {v.updated_by_nome}
                {v.updated_at ? ` em ${formatarDataHora(v.updated_at)}` : ""}
              </p>
            )}
            {problema && (
              <p role="alert" className="text-xs text-destructive" data-testid={`espec-problema-${d.chave}`}>
                {problema}
              </p>
            )}
          </div>
        );
      })}
    </dl>
  );
}

// `isAdmin` is accepted so the page keeps its call shape; nobody edits here, whatever the role.
export function EspecificacoesCard(_props: { isAdmin?: boolean } = {}) {
  const q = useJuliaEspecificacoes();
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const refusa = q.error ? mensagemErroEspec(q.error) : null;
  const naoConectado = q.error ? leituraErroEspec(q.error).code === "agente_nao_conectado" : false;

  return (
    <Card id="especificacoes" data-testid="especificacoes-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Especificações do negócio</CardTitle>
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="espec-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
        </div>
        <CardDescription>
          Dados da sua empresa que a Julia usa para atender seus leads. São informações do seu negócio: o funcionamento da Julia e o conteúdo dela são mantidos pela NoctusAI.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {q.data ? (
          <>
            <Lista data={q.data} />
            <p className="mt-4 text-xs text-muted-foreground" data-testid="espec-nota-suporte">
              {NOTA_EDICAO_NOCTUS}
            </p>
          </>
        ) : showSkeleton ? (
          <div className="h-40 animate-pulse rounded-md bg-muted" data-testid="espec-skeleton" />
        ) : (
          <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="espec-erro" data-codigo={leituraErroEspec(q.error).code ?? ""}>
            <p>{refusa ?? "Não foi possível carregar as especificações."}</p>
            {naoConectado ? (
              <a href="#conexao-plataforma" className="text-primary underline" data-testid="espec-ver-conexao">
                Ver conexão com a plataforma
              </a>
            ) : (
              <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
                Tentar de novo
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
