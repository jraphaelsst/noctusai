/**
 * Julia › Agente card "Conhecimento": what the agency knows about selling, renting and its policies, edited as three texts
 * that Julia reads (agents org specs). Replaces the old structured knowledge form. For each text: the saved value, an
 * "alterações não salvas" mark on a draft, a character counter against the server limit, and — when the text is empty and
 * the old form held something — an explicit "preencher a partir do formulário antigo" that only fills the draft.
 *
 * Writing is NoctusAI-only for now (owner 2026-11-04): the server refuses an org admin with a typed 403 and the card says
 * so in pt-BR (never silent). States: skeleton (no data + pending, never `isLoading`), error with retry, empty, draft.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  mensagemErroConhecimento,
  useJuliaConhecimentoEditor,
  useSalvarConhecimento,
  type ChaveConhecimento,
} from "@/hooks/useJuliaConhecimentoEditor";

export function ConhecimentoEditorCard({ isAdmin = false }: { isAdmin?: boolean }) {
  const q = useJuliaConhecimentoEditor();
  const salvar = useSalvarConhecimento();
  const [rascunho, setRascunho] = useState<Partial<Record<ChaveConhecimento, string>>>({});
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const max = q.data?.max_chars ?? 4000;

  const sujos = (q.data?.itens ?? []).filter((i) => i.chave in rascunho && rascunho[i.chave] !== i.valor);
  const excede = sujos.some((i) => (rascunho[i.chave] ?? "").length > max);

  const onSalvar = () => {
    const valores: Partial<Record<ChaveConhecimento, string>> = {};
    for (const i of sujos) valores[i.chave] = rascunho[i.chave] ?? "";
    salvar.mutate(valores, { onSuccess: () => setRascunho({}) });
  };

  return (
    <Card id="conhecimento" data-testid="conhecimento-editor-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Conhecimento da imobiliária</CardTitle>
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="conhecimento-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
        </div>
        <CardDescription>
          Textos que a Julia usa para responder sobre vendas, locação e as políticas da imobiliária. Escreva em linguagem
          direta, como explicaria a um corretor novo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {q.data ? (
          <>
            {q.data.itens.map((i) => {
              const valor = i.chave in rascunho ? (rascunho[i.chave] ?? "") : i.valor;
              const suja = i.chave in rascunho && rascunho[i.chave] !== i.valor;
              return (
                <div key={i.chave} className="space-y-1" data-testid={`conhecimento-${i.chave}`}>
                  <label htmlFor={`conh-${i.chave}`} className="text-sm font-medium">{i.rotulo}</label>
                  <Textarea
                    id={`conh-${i.chave}`}
                    rows={6}
                    value={valor}
                    readOnly={!isAdmin}
                    placeholder="Ainda não preenchido."
                    onChange={(e) => setRascunho({ ...rascunho, [i.chave]: e.target.value })}
                  />
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span className={valor.length > max ? "text-destructive" : undefined} data-testid={`conhecimento-contador-${i.chave}`}>
                      {valor.length}/{max}
                    </span>
                    {suja && <span data-testid={`conhecimento-nao-salvo-${i.chave}`}>Alterações não salvas.</span>}
                    {!i.declarada && <span data-testid={`conhecimento-nao-declarada-${i.chave}`}>Ainda não disponível para a sua Julia.</span>}
                    {i.updated_by_nome && <span>Alterado por {i.updated_by_nome}</span>}
                    {isAdmin && !valor.trim() && i.sugestao && (
                      <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs"
                        data-testid={`conhecimento-sugestao-${i.chave}`}
                        onClick={() => setRascunho({ ...rascunho, [i.chave]: i.sugestao ?? "" })}>
                        Preencher a partir do formulário antigo
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
            {isAdmin ? (
              <div className="flex items-center gap-2">
                <Button type="button" size="sm" onClick={onSalvar} disabled={sujos.length === 0 || excede || salvar.isPending}>
                  {salvar.isPending ? "Salvando…" : "Salvar conhecimento"}
                </Button>
                {excede && <span role="alert" className="text-xs text-destructive">Um dos textos passa do limite de {max} caracteres.</span>}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Somente administradores da organização veem este conteúdo para edição.</p>
            )}
            {salvar.isError && (
              <p role="alert" className="text-sm text-destructive" data-testid="conhecimento-erro-salvar">
                {mensagemErroConhecimento(salvar.error, "Não foi possível salvar o conhecimento.")}
              </p>
            )}
          </>
        ) : showSkeleton ? (
          <div className="h-48 animate-pulse rounded-md bg-muted" data-testid="conhecimento-skeleton" />
        ) : (
          <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="conhecimento-erro">
            <p>{mensagemErroConhecimento(q.error, "Não foi possível carregar o conhecimento.")}</p>
            <Button variant="outline" size="sm" onClick={() => void q.refetch()}>Tentar de novo</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
