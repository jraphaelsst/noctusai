/**
 * Julia › Agente card "Contatos por setor": who Julia redirects a person who is NOT a lead to (a vendor, a partner, the legal
 * desk, a property owner). The org admin edits a list of {setor, finalidade, nome, telefone}; the owner's own number is shown
 * first and READ-ONLY ("vem do perfil"): it is read from the owner's profile at every load, never typed here.
 *
 * States: skeleton while there is no data and a request is pending (never `isLoading`), error with retry, empty list, a
 * draft marked "alterações não salvas", a typed refusal shown in an alert (the save never fails silently). Phones are shown
 * through the seed `formatPhone` seam; the server normalises and is the authority on validity.
 */
import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { formatPhone, isValidPhone } from "@noctusai/lib";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ROTULO_SETOR,
  mensagemErroContatos,
  useJuliaContatosSetoriais,
  useSalvarContatosSetoriais,
  type ContatoSetorial,
} from "@/hooks/useJuliaContatosSetoriais";

const VAZIO: ContatoSetorial = { setor: "juridico", finalidade: "", nome: "", telefone: "" };

function problema(c: ContatoSetorial): string | null {
  if (c.finalidade.trim().length < 3) return "Descreva para que serve este contato.";
  if (!c.nome.trim()) return "Informe o nome.";
  if (!isValidPhone(c.telefone)) return "Telefone inválido. Use DDD + número, ex.: (11) 99999-9999.";
  return null;
}

export function ContatosSetoriaisCard({ isAdmin = false }: { isAdmin?: boolean }) {
  const q = useJuliaContatosSetoriais();
  const salvar = useSalvarContatosSetoriais();
  const [rascunho, setRascunho] = useState<ContatoSetorial[] | null>(null);
  const [tentou, setTentou] = useState(false);

  const salvos = q.data?.contatos;
  useEffect(() => {
    // Server state changed (first load or a save landed): drop a draft that now equals it.
    if (rascunho && salvos && JSON.stringify(rascunho) === JSON.stringify(salvos)) setRascunho(null);
  }, [salvos, rascunho]);

  const lista = rascunho ?? salvos ?? [];
  const alterado = rascunho !== null && JSON.stringify(rascunho) !== JSON.stringify(salvos ?? []);
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;
  const maximo = (q.data?.maximo ?? 10) - (q.data?.dono ? 1 : 0);
  const problemas = useMemo(() => lista.map(problema), [lista]);

  const editar = (i: number, parte: Partial<ContatoSetorial>) =>
    setRascunho(lista.map((c, j) => (j === i ? { ...c, ...parte } : c)));

  const onSalvar = () => {
    setTentou(true);
    if (problemas.some(Boolean)) return;
    salvar.mutate(lista, { onSuccess: () => { setRascunho(null); setTentou(false); } });
  };

  return (
    <Card id="contatos-setoriais" data-testid="contatos-setoriais-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Contatos por setor</CardTitle>
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="contatos-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
        </div>
        <CardDescription>
          Quando alguém que não é lead procura a imobiliária (fornecedor, parceiro, jurídico, proprietário de imóvel), a Julia
          encaminha a pessoa para estes contatos em vez de atender como lead.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.data ? (
          <>
            {q.data.declarada === false && (
              <p role="status" className="text-sm text-muted-foreground" data-testid="contatos-nao-declarada">
                Este recurso ainda não está disponível para a sua Julia. Você pode preparar a lista, mas não conseguirá salvar.
              </p>
            )}
            {q.data.dono ? (
              <div className="rounded-md border p-3 text-sm" data-testid="contatos-dono">
                <p className="font-medium">{q.data.dono.nome}</p>
                <p className="text-muted-foreground">{q.data.dono.finalidade}</p>
                <p>{formatPhone(q.data.dono.telefone)}</p>
                <p className="text-xs text-muted-foreground">Vem do perfil do proprietário: para mudar, atualize o telefone no perfil.</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="contatos-dono-ausente">
                O proprietário ainda não cadastrou um telefone no perfil, então ele não aparece para a Julia.
              </p>
            )}
            {q.data.legado.length > 0 && (
              <p role="status" className="text-sm text-muted-foreground" data-testid="contatos-legado">
                Há contatos antigos, sem setor: {q.data.legado.join(", ")}. Ao salvar, eles são substituídos por esta lista.
              </p>
            )}
            {lista.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="contatos-vazio">
                Nenhum contato por setor ainda.
              </p>
            ) : (
              <ul className="space-y-3" data-testid="contatos-lista">
                {lista.map((c, i) => (
                  <li key={i} className="grid gap-2 rounded-md border p-3 sm:grid-cols-2" data-testid={`contato-${i}`}>
                    <select
                      aria-label={`Setor do contato ${i + 1}`}
                      className="h-9 rounded-md border bg-background px-2 text-sm"
                      value={c.setor}
                      disabled={!isAdmin}
                      onChange={(e) => editar(i, { setor: e.target.value })}
                    >
                      {(q.data!.setores ?? Object.keys(ROTULO_SETOR)).map((s) => (
                        <option key={s} value={s}>{ROTULO_SETOR[s] ?? s}</option>
                      ))}
                    </select>
                    <Input aria-label={`Nome do contato ${i + 1}`} placeholder="Nome" value={c.nome} disabled={!isAdmin}
                      onChange={(e) => editar(i, { nome: e.target.value })} />
                    <Input aria-label={`Finalidade do contato ${i + 1}`} placeholder="Para que serve (ex.: contratos e dúvidas jurídicas)"
                      value={c.finalidade} disabled={!isAdmin} onChange={(e) => editar(i, { finalidade: e.target.value })} />
                    <div className="flex gap-2">
                      <Input aria-label={`Telefone do contato ${i + 1}`} placeholder="(11) 99999-9999" inputMode="tel" value={c.telefone}
                        disabled={!isAdmin} onChange={(e) => editar(i, { telefone: e.target.value })} />
                      {isAdmin && (
                        <Button type="button" variant="ghost" size="icon" aria-label={`Remover contato ${i + 1}`}
                          onClick={() => setRascunho(lista.filter((_, j) => j !== i))}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                    {tentou && problemas[i] && (
                      <p role="alert" className="text-xs text-destructive sm:col-span-2" data-testid={`contato-problema-${i}`}>
                        {problemas[i]}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {isAdmin ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" disabled={lista.length >= maximo}
                  onClick={() => setRascunho([...lista, { ...VAZIO }])}>
                  <Plus className="mr-1 h-4 w-4" /> Adicionar contato
                </Button>
                <Button type="button" size="sm" onClick={onSalvar} disabled={!alterado || salvar.isPending}>
                  {salvar.isPending ? "Salvando…" : "Salvar contatos"}
                </Button>
                {alterado && (
                  <span className="text-xs text-muted-foreground" data-testid="contatos-nao-salvo">Alterações não salvas.</span>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Somente administradores da organização podem alterar estes contatos.</p>
            )}
            {salvar.isError && (
              <p role="alert" className="text-sm text-destructive" data-testid="contatos-erro-salvar">
                {mensagemErroContatos(salvar.error, "Não foi possível salvar os contatos.")}
              </p>
            )}
          </>
        ) : showSkeleton ? (
          <div className="h-32 animate-pulse rounded-md bg-muted" data-testid="contatos-skeleton" />
        ) : (
          <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="contatos-erro">
            <p>{mensagemErroContatos(q.error, "Não foi possível carregar os contatos por setor.")}</p>
            <Button variant="outline" size="sm" onClick={() => void q.refetch()}>Tentar de novo</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
