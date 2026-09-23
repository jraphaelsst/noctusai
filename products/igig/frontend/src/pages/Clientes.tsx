/**
 * Clientes — Módulo 1 (CRM), wave-2 contract Slice F (roadmap R9).
 *
 * The listing (cards below `md`, a table above — R0 mobile-first, no
 * sideways page scroll) opens the cliente CARD: the seed `CardHubDialog`, the
 * same organ as the negócio card, with Geral · Dados · Marcas · Orçamentos &
 * Contratos · Calendário · Esteira · Financeiro. The Central da Marca moved
 * into the card (a cliente carries N marcas); `/marca` redirects here.
 *
 * `?id=<cliente>` deep-links the card (links from notifications, the
 * Comercial "ganho" toast…). The orçamento modal is owned HERE, not by the
 * card, so opening an orçamento from the card's tab keeps the card underneath.
 *
 * Loading: `loading` is `isPending && !data` (never `isLoading`), and the
 * list hook keeps the previous rows on screen while a new `busca` loads.
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Field, FormError, Input, Select, TableSkeleton } from "@noctusai/lib/design-system";
import { ChevronRight, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { ClienteCardDialog } from "@/components/clientes/ClienteCardDialog";
import { STATUS_CLIENTE, STATUS_CLIENTE_LABEL, STATUS_CLIENTE_VARIANT } from "@/components/clientes/status";
import { SheetDialog } from "@/components/common/SheetDialog";
import { OrcamentoModal } from "@/components/orcamento/OrcamentoModal";
import { useClientes, useCriarCliente, type Cliente, type StatusCliente } from "@/hooks/useClientes";
import { describeError } from "@/lib/errors";
import { dataBR } from "@/lib/format";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

export default function Clientes() {
  const [params, setParams] = useSearchParams();
  const abertoId = params.get("id");
  const [busca, setBusca] = useState("");
  const buscaDebounced = useDebouncedValue(busca.trim(), 300);
  const [status, setStatus] = useState<StatusCliente | "">("");
  const [novo, setNovo] = useState(false);
  const [orcamentoId, setOrcamentoId] = useState<string | null>(null);

  const { clientes, total, loading, isError, error, isRefreshing } = useClientes({
    busca: buscaDebounced || undefined,
    status: status || undefined,
  });

  /** Functional update — never clobbers a param another handler just set. */
  function abrir(id: string | null) {
    setParams(
      (atual) => {
        const prox = new URLSearchParams(atual);
        if (id) prox.set("id", id);
        else prox.delete("id");
        return prox;
      },
      { replace: !id },
    );
  }

  const aberto = abertoId ? clientes.find((c) => c.id === abertoId) ?? null : null;
  const filtrando = !!(buscaDebounced || status);

  return (
    <div className="mx-auto w-full min-w-0 max-w-full space-y-4 overflow-x-hidden p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Clientes</h1>
          <p className="text-sm text-muted-foreground">
            {loading ? "Carregando…" : `${total} ${total === 1 ? "cliente" : "clientes"}`}
            {isRefreshing && <span> · atualizando…</span>}
          </p>
        </div>
        <Button variant="primary" className="max-sm:h-10" onClick={() => setNovo(true)} data-testid="clientes-novo">
          <Plus className="mr-1 h-4 w-4" /> Novo cliente
        </Button>
      </header>

      {/* ── Filtros ─────────────────────────────────────────────── */}
      <div className="grid gap-2 sm:flex sm:items-center">
        <div className="relative min-w-0 sm:flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Buscar por nome"
            className="h-10 pl-9"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome…"
          />
        </div>
        <Select
          aria-label="Filtrar por status"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusCliente | "")}
          className="h-10 sm:w-48"
        >
          <option value="">Todos os status</option>
          {STATUS_CLIENTE.map((s) => (
            <option key={s} value={s}>
              {STATUS_CLIENTE_LABEL[s]}
            </option>
          ))}
        </Select>
      </div>

      {/* ── Lista ───────────────────────────────────────────────── */}
      {isError && clientes.length === 0 ? (
        <p role="alert" className="rounded-lg border border-border bg-card p-6 text-sm text-destructive">
          {describeError(error, "Não foi possível carregar os clientes.")}
        </p>
      ) : loading ? (
        <TableSkeleton rows={5} />
      ) : clientes.length === 0 ? (
        /* Reached only when NOT loading — an empty state shown during a
           background refetch would be lying about the data. */
        <div className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          {filtrando ? (
            "Nenhum cliente corresponde aos filtros."
          ) : (
            <>
              Nenhum cliente ainda. Clientes nascem quando um negócio é fechado no Comercial — ou adicione um agora.
              <div className="mt-3">
                <Button className="max-sm:h-10" onClick={() => setNovo(true)}>
                  <Plus className="mr-1 h-4 w-4" /> Novo cliente
                </Button>
              </div>
            </>
          )}
        </div>
      ) : (
        <>
          {/* Mobile: one tappable card per cliente. */}
          <ul className="space-y-2 md:hidden" data-testid="clientes-cards">
            {clientes.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => abrir(c.id)}
                  className="flex min-h-14 w-full items-center gap-3 rounded-lg border border-border bg-card p-3 text-left"
                  aria-label={`Abrir ${c.nome}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-foreground">{c.nome}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[c.nicho, c.email || c.telefone].filter(Boolean).join(" · ") || "Sem nicho definido"}
                    </span>
                  </span>
                  <Badge variant={STATUS_CLIENTE_VARIANT[c.status]}>{STATUS_CLIENTE_LABEL[c.status]}</Badge>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>

          {/* Desktop: a table. */}
          <div className="hidden overflow-hidden rounded-lg border border-border bg-card md:block">
            <table className="w-full table-fixed text-sm" data-testid="clientes-tabela">
              <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Cliente</th>
                  <th className="px-4 py-2 font-medium">Nicho</th>
                  <th className="px-4 py-2 font-medium">Contato</th>
                  <th className="w-36 px-4 py-2 font-medium">Status</th>
                  <th className="w-32 px-4 py-2 font-medium">Desde</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {clientes.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => abrir(c.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        abrir(c.id);
                      }
                    }}
                    aria-label={`Abrir ${c.nome}`}
                  >
                    <td className="truncate px-4 py-3 font-medium text-foreground">{c.nome}</td>
                    <td className="truncate px-4 py-3 text-muted-foreground">{c.nicho || "—"}</td>
                    <td className="truncate px-4 py-3 text-muted-foreground">{c.email || c.telefone || "—"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_CLIENTE_VARIANT[c.status]}>{STATUS_CLIENTE_LABEL[c.status]}</Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{dataBR(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <NovoClienteSheet
        open={novo}
        onClose={() => setNovo(false)}
        onCriado={(c) => {
          setNovo(false);
          abrir(c.id);
        }}
      />

      <ClienteCardDialog
        clienteId={abertoId}
        clienteDaLista={aberto}
        onClose={() => abrir(null)}
        onAbrirOrcamento={setOrcamentoId}
      />

      <OrcamentoModal open={!!orcamentoId} onClose={() => setOrcamentoId(null)} orcamentoId={orcamentoId} />
    </div>
  );
}

function NovoClienteSheet({
  open,
  onClose,
  onCriado,
}: {
  open: boolean;
  onClose: () => void;
  onCriado: (c: Cliente) => void;
}) {
  const criar = useCriarCliente();
  const [f, setF] = useState({ nome: "", nicho: "", email: "", telefone: "" });
  const opt = (v: string) => v.trim() || undefined;

  function fechar() {
    setF({ nome: "", nicho: "", email: "", telefone: "" });
    criar.reset();
    onClose();
  }

  return (
    <SheetDialog
      open={open}
      onClose={fechar}
      title="Novo cliente"
      widthClassName="sm:max-w-md"
      testId="novo-cliente-sheet"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="max-sm:h-10 max-sm:flex-1" onClick={fechar}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="novo-cliente-form"
            className="max-sm:h-10 max-sm:flex-1"
            disabled={!f.nome.trim() || criar.isPending}
          >
            {criar.isPending ? "Salvando…" : "Adicionar"}
          </Button>
        </div>
      }
    >
      <form
        id="novo-cliente-form"
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!f.nome.trim()) return;
          criar.mutate(
            { nome: f.nome.trim(), nicho: opt(f.nicho), email: opt(f.email), telefone: opt(f.telefone) },
            {
              onSuccess: (c) => {
                toast.success("Cliente criado.");
                setF({ nome: "", nicho: "", email: "", telefone: "" });
                onCriado(c);
              },
            },
          );
        }}
      >
        <Field label="Nome" required>
          <Input
            className="max-sm:h-10"
            aria-label="Nome"
            value={f.nome}
            onChange={(e) => setF({ ...f, nome: e.target.value })}
            placeholder="Padaria Sol"
          />
        </Field>
        <Field label="Nicho">
          <Input
            className="max-sm:h-10"
            aria-label="Nicho"
            value={f.nicho}
            onChange={(e) => setF({ ...f, nicho: e.target.value })}
            placeholder="Alimentação"
          />
        </Field>
        <Field label="E-mail">
          <Input
            className="max-sm:h-10"
            type="email"
            inputMode="email"
            value={f.email}
            onChange={(e) => setF({ ...f, email: e.target.value })}
          />
        </Field>
        <Field label="Telefone">
          <Input
            className="max-sm:h-10"
            type="tel"
            inputMode="tel"
            value={f.telefone}
            onChange={(e) => setF({ ...f, telefone: e.target.value })}
          />
        </Field>
        <FormError message={criar.isError ? describeError(criar.error, "Não foi possível criar o cliente.") : null} />
      </form>
    </SheetDialog>
  );
}
