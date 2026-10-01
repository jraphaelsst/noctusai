/**
 * Edit controls for an OPEN fatura (admin-only, server-enforced):
 *  - `EditarFaturaForm`  → `PATCH /faturas/{id}` (competência, vencimento)
 *  - `EditarItemForm`    → `PATCH /faturas/{id}/itens/{item_id}`
 * Deleting a line is a ConfirmDialog owned by the page (`useRemoverItem`).
 * The server recomputes the total and returns the fatura; the hooks
 * invalidate the whole financeiro key so every number refreshes.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button, Input } from "@noctusai/lib/design-system";

import { useEditarFatura, useEditarItem, type Fatura, type FaturaItem } from "@/hooks/useFinanceiro";
import { describeError } from "@/lib/errors";
import { parseValorBR } from "@/lib/format";

export function EditarFaturaForm({ fatura, onClose }: { fatura: Fatura; onClose: () => void }) {
  const editar = useEditarFatura();
  const [competencia, setCompetencia] = useState(fatura.competencia);
  const [vencimento, setVencimento] = useState(fatura.vencimento?.slice(0, 10) ?? "");

  function submeter(e: React.FormEvent) {
    e.preventDefault();
    if (!competencia) return;
    editar.mutate(
      { faturaId: fatura.id, competencia, ...(vencimento ? { vencimento } : {}) },
      {
        onSuccess: () => {
          toast.success("Fatura atualizada");
          onClose();
        },
        onError: (erro) => toast.error(describeError(erro, "Não foi possível editar a fatura.")),
      },
    );
  }

  return (
    <form
      onSubmit={submeter}
      aria-label="Editar fatura"
      className="mt-2 grid grid-cols-1 gap-3 rounded-md border border-border bg-background p-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end"
    >
      <label className="text-xs text-muted-foreground">
        Competência
        <Input type="month" className="mt-1 h-11" value={competencia} onChange={(e) => setCompetencia(e.target.value)} />
      </label>
      <label className="text-xs text-muted-foreground">
        Vencimento
        <Input type="date" className="mt-1 h-11" value={vencimento} onChange={(e) => setVencimento(e.target.value)} />
      </label>
      <Button type="submit" className="min-h-11" disabled={!competencia || editar.isPending}>
        {editar.isPending ? "Salvando…" : "Salvar"}
      </Button>
      <Button type="button" variant="ghost" className="min-h-11" onClick={onClose}>
        Cancelar
      </Button>
    </form>
  );
}

export function EditarItemForm({
  faturaId,
  item,
  onClose,
}: {
  faturaId: string;
  item: FaturaItem;
  onClose: () => void;
}) {
  const editar = useEditarItem();
  const [descricao, setDescricao] = useState(item.descricao);
  const [quantidade, setQuantidade] = useState(String(item.quantidade));
  const [valor, setValor] = useState(String(item.valor_unit).replace(".", ","));
  const [erroValor, setErroValor] = useState<string | null>(null);

  function submeter(e: React.FormEvent) {
    e.preventDefault();
    const d = descricao.trim();
    if (!d) return;
    const valorNumerico = parseValorBR(valor);
    if (valorNumerico === null || valorNumerico < 0) {
      setErroValor("Valor inválido. Use, por exemplo, 1500,00 ou 1.500,00.");
      return;
    }
    setErroValor(null);
    editar.mutate(
      {
        faturaId,
        itemId: item.id,
        descricao: d,
        quantidade: Math.max(1, Number(quantidade) || 1),
        valor_unit: valorNumerico,
      },
      {
        onSuccess: () => {
          toast.success("Item atualizado");
          onClose();
        },
        onError: (erro) => toast.error(describeError(erro, "Não foi possível editar o item.")),
      },
    );
  }

  return (
    <form
      onSubmit={submeter}
      aria-label={`Editar item ${item.descricao}`}
      className="grid grid-cols-2 gap-2 py-2 sm:grid-cols-[2fr_5rem_7rem_auto_auto] sm:items-end"
    >
      <label className="col-span-2 text-xs text-muted-foreground sm:col-span-1">
        Descrição
        <Input className="mt-1 h-11" value={descricao} maxLength={200} onChange={(e) => setDescricao(e.target.value)} />
      </label>
      <label className="text-xs text-muted-foreground">
        Qtd
        <Input type="number" min={1} className="mt-1 h-11" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} />
      </label>
      <label className="text-xs text-muted-foreground">
        Valor un.
        <Input inputMode="decimal" className="mt-1 h-11" value={valor} onChange={(e) => setValor(e.target.value)} />
      </label>
      <Button type="submit" className="min-h-11" disabled={!descricao.trim() || editar.isPending}>
        {editar.isPending ? "Salvando…" : "Salvar"}
      </Button>
      <Button type="button" variant="ghost" className="min-h-11" onClick={onClose}>
        Cancelar
      </Button>
      {erroValor && (
        <p role="alert" className="col-span-2 text-xs text-destructive sm:col-span-5">{erroValor}</p>
      )}
    </form>
  );
}
