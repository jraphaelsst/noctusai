/**
 * Julia › Agente card "Especificações do negócio" (owner 2026-11-18: an org's business data is org-owned, its admins edit it).
 * Rendered generically from the declarations the active version carries (rotulo / descricao per `tipo`), with "Alterado por … em …".
 * An org ADMIN edits the keys agents marks `editavel_pela_org` that have no dedicated card (knowledge and the sector contacts have
 * their own); everything else, and every key for a non-admin, is read-only with a note. Loading = two signals off `data`
 * (never `isLoading`); a refusal is a pt-BR sentence, never silent.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { formatarDataHora } from "@/components/julia/ConexaoPlataforma";
import {
  leituraErroEspec,
  mensagemErroEspec,
  useJuliaEspecificacoes,
  useSalvarEspecificacoes,
  type Especificacoes,
} from "@/hooks/useJuliaEspecificacoes";

export const NOTA_EDICAO_NOCTUS =
  "As informações marcadas como da equipe NoctusAI só podem ser alteradas por ela. Para alterar, fale com o suporte.";
export const NOTA_SOMENTE_ADMIN = "Somente administradores da organização podem alterar estas informações.";

/** Keys with their own editor card (Conhecimento / Contatos por setor): never duplicated here. */
const CHAVES_COM_CARD_PROPRIO = new Set(["conhecimento_venda", "conhecimento_locacao", "conhecimento_politicas", "contatos_oficiais"]);

function Lista({
  data,
  isAdmin,
  rascunho,
  onEditar,
}: {
  data: Especificacoes;
  isAdmin: boolean;
  rascunho: Record<string, string>;
  onEditar: (chave: string, valor: string) => void;
}) {
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
        const editavel = isAdmin && d.editavel_pela_org === true && !CHAVES_COM_CARD_PROPRIO.has(d.chave);
        const problema = problemas.get(d.chave) ?? (faltando.has(d.chave) && !v?.valor?.trim() ? "Obrigatório: ainda não preenchido." : null);
        return (
          <div key={d.id} className="space-y-1" data-testid={`espec-campo-${d.chave}`}>
            <dt className="text-sm font-medium">{d.rotulo}</dt>
            {editavel ? (
              <dd>
                <Textarea
                  aria-label={d.rotulo}
                  rows={2}
                  value={d.chave in rascunho ? rascunho[d.chave] : (v?.valor ?? "")}
                  placeholder={d.exemplo ?? "Ainda não preenchido."}
                  data-testid={`espec-input-${d.chave}`}
                  onChange={(e) => onEditar(d.chave, e.target.value)}
                />
                {d.chave in rascunho && rascunho[d.chave] !== (v?.valor ?? "") && (
                  <span className="text-xs text-muted-foreground" data-testid={`espec-nao-salvo-${d.chave}`}>Alterações não salvas.</span>
                )}
              </dd>
            ) : (
              <dd className="whitespace-pre-wrap text-sm" data-testid={`espec-valor-${d.chave}`}>
                {v?.valor?.trim() ? v.valor : <span className="text-muted-foreground">Não preenchido</span>}
              </dd>
            )}
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

export function EspecificacoesCard({ isAdmin = false }: { isAdmin?: boolean } = {}) {
  const q = useJuliaEspecificacoes();
  const salvar = useSalvarEspecificacoes();
  const [rascunho, setRascunho] = useState<Record<string, string>>({});
  const sujos = Object.entries(rascunho).filter(([chave, valor]) => (q.data?.valores.find((x) => x.chave === chave)?.valor ?? "") !== valor);
  const onSalvar = () =>
    salvar.mutate(Object.fromEntries(sujos), { onSuccess: () => setRascunho({}) });
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
          Dados da sua empresa que a Julia usa para atender seus leads. São informações do seu negócio, que os administradores da sua organização editam; o funcionamento da Julia é mantido pela NoctusAI.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {q.data ? (
          <>
            <Lista data={q.data} isAdmin={isAdmin} rascunho={rascunho} onEditar={(c, v) => setRascunho({ ...rascunho, [c]: v })} />
            {isAdmin && q.data.declaradas.some((d) => d.editavel_pela_org && !CHAVES_COM_CARD_PROPRIO.has(d.chave)) && (
              <div className="mt-4">
                <Button type="button" size="sm" onClick={onSalvar} disabled={sujos.length === 0 || salvar.isPending} data-testid="espec-salvar">
                  {salvar.isPending ? "Salvando…" : "Salvar informações"}
                </Button>
              </div>
            )}
            {salvar.isError && (
              <p role="alert" className="mt-2 text-sm text-destructive" data-testid="espec-erro-salvar">
                {mensagemErroEspec(salvar.error) ?? "Não foi possível salvar as informações."}
              </p>
            )}
            <p className="mt-4 text-xs text-muted-foreground" data-testid="espec-nota-suporte">
              {isAdmin ? NOTA_EDICAO_NOCTUS : NOTA_SOMENTE_ADMIN}
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
