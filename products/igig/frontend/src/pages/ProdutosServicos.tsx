/**
 * Produtos e Serviços — the orçamento catalog, CRUD grouped by seção
 * (roadmap R6; wave-2 contract Slice C over Slice A's endpoints).
 *
 * Declared deviation from the seed `ResourceManager` organ (the canonical
 * page-scoped CRUD): it renders ONE flat table from ONE `apiPath` with local
 * state. This page needs (a) grouping by seção, (b) a card layout at 390px
 * (R0 — a 6-column table does not fit a phone), and (c) the TanStack cache
 * the OrcamentoModal's catalog picker reads, so an edit here is visible there
 * without a reload. Reported as a `scoped-improvement` (ResourceManager
 * `groupBy` + mobile card mode + react-query variant) rather than forked.
 *
 * DELETE of a product an orçamento references is a SOFT delete server-side
 * (`ativo=false`, 200) — the toast says which one happened.
 */
import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Badge, Button, EmptyState, Field, FormError, Input, Select, Skeleton, Switch, Textarea } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { useProdutoServicoMutations, useProdutosServicos } from "@/hooks/useProdutosServicos";
import { describeError } from "@/lib/errors";
import { brl } from "@/lib/format";
import { SECAO_LABEL, SECOES, type ProdutoServico, type ProdutoServicoInput, type Secao } from "@/types/crm";

const UNIDADES = ["unidade", "mês", "hora", "post", "vídeo"];

function vazio(secao: Secao, ordem: number): ProdutoServicoInput {
  return {
    secao,
    nome: "",
    descricao: null,
    preco_base: 0,
    unidade: secao === "gestao_conta" ? "mês" : "unidade",
    horas_estimadas: 0,
    ativo: true,
    ordem,
  };
}

export default function ProdutosServicos() {
  const [mostrarInativos, setMostrarInativos] = useState(false);
  const { produtos, showSkeleton, isRefreshing, isError, error } = useProdutosServicos(
    mostrarInativos ? {} : { ativo: true },
  );
  const { remover, atualizar } = useProdutoServicoMutations();
  const [editando, setEditando] = useState<{ id: string | null; valores: ProdutoServicoInput } | null>(null);

  function excluir(p: ProdutoServico) {
    if (!window.confirm(`Excluir "${p.nome}"?`)) return;
    remover.mutate(p.id, {
      onSuccess: (r) =>
        toast.success(
          r && r.ativo === false
            ? `"${p.nome}" está em orçamentos — foi desativado em vez de excluído.`
            : `"${p.nome}" excluído.`,
        ),
      onError: (e) => toast.error(describeError(e, "Não foi possível excluir.")),
    });
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 overflow-x-hidden p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-foreground">Produtos e Serviços</h1>
          <p className="text-sm text-muted-foreground">O catálogo de onde saem os itens dos orçamentos.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={mostrarInativos} onCheckedChange={(v: boolean) => setMostrarInativos(v)} aria-label="Mostrar inativos" />
          Mostrar inativos
        </label>
      </header>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="produtos-loading">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : isError ? (
        <p role="alert" className="py-8 text-center text-sm text-destructive">
          {describeError(error, "Não foi possível carregar o catálogo.")}
        </p>
      ) : (
        SECOES.map((secao) => {
          const itens = produtos.filter((p) => p.secao === secao).sort((a, b) => a.ordem - b.ordem || a.nome.localeCompare(b.nome));
          return (
            <section key={secao} aria-label={SECAO_LABEL[secao]} className={cn("space-y-2", isRefreshing && "opacity-80")}>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-base font-semibold text-foreground">{SECAO_LABEL[secao]}</h2>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditando({ id: null, valores: vazio(secao, itens.length) })}
                >
                  <Plus className="mr-1 h-4 w-4" /> Adicionar
                </Button>
              </div>
              {itens.length === 0 ? (
                <EmptyState message="Nenhum item nesta seção." />
              ) : (
                <ul className="divide-y divide-border rounded-xl border border-border bg-card">
                  {itens.map((p) => (
                    <li key={p.id} className="flex items-start gap-3 p-3" data-testid="produto-item">
                      <div className="min-w-0 flex-1">
                        <p className={cn("truncate font-medium", p.ativo ? "text-foreground" : "text-muted-foreground line-through")}>
                          {p.nome}
                        </p>
                        {p.descricao ? <p className="line-clamp-2 text-xs text-muted-foreground">{p.descricao}</p> : null}
                        <p className="mt-1 text-xs text-muted-foreground">
                          <span className="font-medium tabular-nums text-foreground">{brl(p.preco_base)}</span> / {p.unidade}
                          {p.horas_estimadas ? ` · ${p.horas_estimadas.toLocaleString("pt-BR")} h` : ""}
                        </p>
                      </div>
                      {!p.ativo ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            atualizar.mutate(
                              { id: p.id, payload: { ativo: true } },
                              { onError: (e) => toast.error(describeError(e, "Não foi possível reativar.")) },
                            )
                          }
                        >
                          Reativar
                        </Button>
                      ) : (
                        <Badge variant="muted" className="hidden sm:inline-flex">Ativo</Badge>
                      )}
                      <button
                        type="button"
                        aria-label={`Editar ${p.nome}`}
                        onClick={() => {
                          const { id, ...valores } = p;
                          setEditando({ id, valores });
                        }}
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Excluir ${p.nome}`}
                        onClick={() => excluir(p)}
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })
      )}

      <ProdutoForm estado={editando} onClose={() => setEditando(null)} />
    </div>
  );
}

function ProdutoForm({
  estado,
  onClose,
}: {
  estado: { id: string | null; valores: ProdutoServicoInput } | null;
  onClose: () => void;
}) {
  const { criar, atualizar } = useProdutoServicoMutations();
  const [v, setV] = useState<ProdutoServicoInput | null>(null);
  const [chave, setChave] = useState<unknown>(null);
  if (estado !== chave) {
    setChave(estado);
    setV(estado ? { ...estado.valores } : null);
  }
  const mut = estado?.id ? atualizar : criar;

  function salvar() {
    if (!estado || !v) return;
    const payload: ProdutoServicoInput = {
      ...v,
      nome: v.nome.trim(),
      descricao: v.descricao?.trim() ? v.descricao.trim() : null,
    };
    const onSuccess = () => {
      toast.success(estado.id ? "Item atualizado." : "Item criado.");
      onClose();
    };
    if (estado.id) atualizar.mutate({ id: estado.id, payload }, { onSuccess });
    else criar.mutate(payload, { onSuccess });
  }

  return (
    <SheetDialog
      open={!!estado}
      onClose={onClose}
      title={estado?.id ? "Editar item" : "Novo item"}
      widthClassName="sm:max-w-md"
      testId="produto-form"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={!v?.nome.trim() || mut.isPending} onClick={salvar}>
            {mut.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      }
    >
      {v ? (
        <div className="space-y-3">
          <Field label="Seção" required>
            <Select value={v.secao} onChange={(e) => setV({ ...v, secao: e.target.value as Secao })}>
              {SECOES.map((s) => (
                <option key={s} value={s}>
                  {SECAO_LABEL[s]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Nome" required>
            <Input value={v.nome} onChange={(e) => setV({ ...v, nome: e.target.value })} placeholder="Ex.: Reels" />
          </Field>
          <Field label="Descrição">
            <Textarea rows={2} value={v.descricao ?? ""} onChange={(e) => setV({ ...v, descricao: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Preço base (R$)" required>
              <Input
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={v.preco_base}
                onChange={(e) => setV({ ...v, preco_base: Math.max(0, Number(e.target.value) || 0) })}
              />
            </Field>
            <Field label="Unidade">
              <Select value={v.unidade} onChange={(e) => setV({ ...v, unidade: e.target.value })}>
                {Array.from(new Set([...UNIDADES, v.unidade])).map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Horas estimadas">
              <Input
                type="number"
                inputMode="decimal"
                min={0}
                step="0.25"
                value={v.horas_estimadas}
                onChange={(e) => setV({ ...v, horas_estimadas: Math.max(0, Number(e.target.value) || 0) })}
              />
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm text-foreground">
              <Switch checked={v.ativo} onCheckedChange={(x: boolean) => setV({ ...v, ativo: x })} aria-label="Ativo" />
              Ativo
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            As horas alimentam o custo estimado e a margem do orçamento (custo/hora médio da equipe).
          </p>
          <FormError message={mut.isError ? describeError(mut.error, "Não foi possível salvar.") : null} />
        </div>
      ) : null}
    </SheetDialog>
  );
}
