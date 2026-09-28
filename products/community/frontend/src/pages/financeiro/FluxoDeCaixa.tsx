/**
 * Fluxo de caixa — the third Financeiro tab (CONTRACT.md ninho-vazio
 * §Cashflow, `/api/lancamentos*`).
 *
 * Period totals come from the list envelope's `totais` (server-computed over
 * the whole filtered period, not just the visible page). Automatic entries
 * (`origem` pagamento/estorno — booked by the billing webhooks) are shown
 * read-only; only `manual` rows get edit/delete, and only for an admin.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  Input,
  StatTile,
  StatTileRow,
  TableSkeleton,
} from "@noctusai/lib/design-system";
import { EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { centsToReais, formatBRLFromCents, reaisToCents } from "@/lib/money";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import {
  useCategoriasLancamento,
  useCreateLancamento,
  useDeleteLancamento,
  useLancamentos,
  useUpdateLancamento,
  type Lancamento,
  type LancamentoInput,
  type LancamentoOrigem,
  type LancamentoTipo,
} from "@/hooks/useLancamentos";

const PAGE_SIZE = 50;

const ORIGEM_LABELS: Record<LancamentoOrigem, string> = {
  pagamento: "Pagamento",
  estorno: "Estorno",
  manual: "Manual",
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The contract's default window: the current calendar month. */
export function mesCorrente(hoje = new Date()): { de: string; ate: string } {
  const inicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  const fim = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0);
  return { de: toISODate(inicio), ate: toISODate(fim) };
}

/** `YYYY-MM-DD` → `DD/MM/YYYY` without a timezone shift. */
function formatDia(value: string): string {
  const [a, m, d] = value.split("-");
  return a && m && d ? `${d}/${m}/${a}` : value;
}

export default function FluxoDeCaixa() {
  const isAdmin = useIsAdmin();
  const [periodo, setPeriodo] = useState(() => mesCorrente());
  const [tipo, setTipo] = useState<LancamentoTipo | "">("");
  const [categoria, setCategoria] = useState("");
  const [page, setPage] = useState(1);
  const [formFor, setFormFor] = useState<Lancamento | "novo" | null>(null);

  const params = useMemo(
    () => ({
      de: periodo.de || undefined,
      ate: periodo.ate || undefined,
      tipo: tipo || undefined,
      categoria: categoria || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    [periodo, tipo, categoria, page],
  );

  const { data, isPending, isFetching, error } = useLancamentos(params);
  const categorias = useCategoriasLancamento();
  const deleteLancamento = useDeleteLancamento();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  function resetPage<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(1);
    };
  }

  async function handleDelete(l: Lancamento) {
    if (!window.confirm(`Excluir o lançamento "${l.descricao || l.categoria}" de ${formatBRLFromCents(l.valor_centavos)}?`)) {
      return;
    }
    try {
      await deleteLancamento.mutateAsync(l.id);
      toast.success("Lançamento excluído.");
    } catch (err) {
      toast.error("Erro ao excluir lançamento", { description: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4" data-testid="fluxo-de-caixa">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="De">
          <Input
            type="date"
            value={periodo.de}
            onChange={(e) => resetPage(setPeriodo)({ ...periodo, de: e.target.value })}
            aria-label="Data inicial"
          />
        </Field>
        <Field label="Até">
          <Input
            type="date"
            value={periodo.ate}
            onChange={(e) => resetPage(setPeriodo)({ ...periodo, ate: e.target.value })}
            aria-label="Data final"
          />
        </Field>
        <Field label="Tipo">
          <Select
            className="w-40"
            value={tipo}
            onChange={(e) => resetPage(setTipo)(e.target.value as LancamentoTipo | "")}
            aria-label="Filtrar por tipo"
          >
            <option value="">Entradas e saídas</option>
            <option value="entrada">Entradas</option>
            <option value="saida">Saídas</option>
          </Select>
        </Field>
        <Field label="Categoria">
          <Select
            className="w-44"
            value={categoria}
            onChange={(e) => resetPage(setCategoria)(e.target.value)}
            aria-label="Filtrar por categoria"
          >
            <option value="">Todas</option>
            {(categorias.data?.items ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </Field>
        {isAdmin && (
          <Button variant="primary" className="ml-auto" onClick={() => setFormFor("novo")}>
            + Novo lançamento
          </Button>
        )}
      </div>

      <StatTileRow className="lg:grid-cols-3">
        <StatTile
          label="Entradas"
          loading={showSkeleton}
          value={data ? formatBRLFromCents(data.totais.entradas_centavos) : null}
        />
        <StatTile
          label="Saídas"
          loading={showSkeleton}
          value={data ? formatBRLFromCents(data.totais.saidas_centavos) : null}
        />
        <StatTile
          label="Saldo"
          loading={showSkeleton}
          value={data ? formatBRLFromCents(data.totais.saldo_centavos) : null}
          hint="No período filtrado"
        />
      </StatTileRow>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={7} />
      ) : error && !data ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhum lançamento neste período." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          {/* lying-loading-ok: caption-only refresh hint, table stays mounted */}
          {isRefreshing && <p className="px-4 py-1 text-xs text-muted-foreground">Atualizando…</p>}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Data</th>
                <th className="px-4 py-3 font-medium">Categoria</th>
                <th className="px-4 py-3 font-medium">Descrição</th>
                <th className="px-4 py-3 font-medium">Membro</th>
                <th className="px-4 py-3 font-medium">Origem</th>
                <th className="px-4 py-3 font-medium text-right">Valor</th>
                <th className="px-4 py-3 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.id} className="border-b border-border last:border-0" data-testid={`lancamento-row-${l.id}`}>
                  <td className="px-4 py-3 text-foreground">{formatDia(l.data)}</td>
                  <td className="px-4 py-3 text-foreground">{l.categoria}</td>
                  <td className="px-4 py-3 text-foreground">{l.descricao || "—"}</td>
                  <td className="px-4 py-3 text-foreground">{l.membro_nome ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={l.origem === "manual" ? "outline" : "muted"}>{ORIGEM_LABELS[l.origem] ?? l.origem}</Badge>
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums ${l.tipo === "saida" ? "text-destructive" : "text-foreground"}`}
                  >
                    {l.tipo === "saida" ? "− " : "+ "}
                    {formatBRLFromCents(l.valor_centavos)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {l.origem === "manual" && isAdmin ? (
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setFormFor(l)} data-testid={`lancamento-editar-${l.id}`}>
                          Editar
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => void handleDelete(l)}
                          data-testid={`lancamento-excluir-${l.id}`}
                        >
                          Excluir
                        </Button>
                      </div>
                    ) : l.origem !== "manual" ? (
                      <span className="text-xs text-muted-foreground">Automático</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPaginas > 1 && (
            <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-2 text-xs text-muted-foreground">
              <span>
                Página {page} de {totalPaginas} · {data.total} lançamentos
              </span>
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Anterior
              </Button>
              <Button variant="outline" size="sm" disabled={page >= totalPaginas} onClick={() => setPage((p) => p + 1)}>
                Próxima
              </Button>
            </div>
          )}
        </div>
      )}

      {formFor && (
        <LancamentoFormDialog
          lancamento={formFor === "novo" ? null : formFor}
          categorias={categorias.data?.items ?? []}
          onClose={() => setFormFor(null)}
        />
      )}
    </div>
  );
}

function LancamentoFormDialog({
  lancamento,
  categorias,
  onClose,
}: {
  lancamento: Lancamento | null;
  categorias: string[];
  onClose: () => void;
}) {
  const [form, setForm] = useState(() => ({
    tipo: (lancamento?.tipo ?? "saida") as LancamentoTipo,
    categoria: lancamento?.categoria ?? "",
    descricao: lancamento?.descricao ?? "",
    valor_reais: lancamento ? String(centsToReais(lancamento.valor_centavos)) : "",
    data: lancamento?.data ?? toISODate(new Date()),
  }));
  const [formError, setFormError] = useState<string | null>(null);
  const create = useCreateLancamento();
  const update = useUpdateLancamento();
  const saving = create.isPending || update.isPending;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const valor_centavos = reaisToCents(form.valor_reais);
    if (valor_centavos <= 0) {
      setFormError("Informe um valor maior que zero.");
      return;
    }
    const payload: LancamentoInput = {
      tipo: form.tipo,
      categoria: form.categoria.trim(),
      descricao: form.descricao.trim() || null,
      valor_centavos,
      data: form.data,
    };
    const handlers = {
      onSuccess: () => {
        toast.success(lancamento ? "Lançamento atualizado." : "Lançamento criado.");
        onClose();
      },
      onError: (err: unknown) => setFormError(errorMessage(err)),
    };
    if (lancamento) update.mutate({ id: lancamento.id, ...payload }, handlers);
    else create.mutate(payload, handlers);
  }

  const titulo = lancamento ? "Editar lançamento" : "Novo lançamento";

  return (
    <Dialog open onClose={onClose} title={titulo} className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">{titulo}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Tipo" required>
            <Select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as LancamentoTipo })}>
              <option value="entrada">Entrada</option>
              <option value="saida">Saída</option>
            </Select>
          </Field>
          <Field label="Categoria" required help="Escolha uma existente ou digite uma nova.">
            <Input
              list="categorias-lancamento"
              value={form.categoria}
              onChange={(e) => setForm({ ...form, categoria: e.target.value })}
              maxLength={60}
              required
            />
            <datalist id="categorias-lancamento">
              {categorias.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
          <Field label="Descrição">
            <Input
              value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
              maxLength={300}
            />
          </Field>
          <Field label="Valor (R$)" required>
            <Input
              type="number"
              min={0.01}
              step={0.01}
              value={form.valor_reais}
              onChange={(e) => setForm({ ...form, valor_reais: e.target.value })}
              required
            />
          </Field>
          <Field label="Data" required>
            <Input type="date" value={form.data} onChange={(e) => setForm({ ...form, data: e.target.value })} required />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
