/**
 * Clientes — Módulo 1 (CRM).
 *
 * The first IgIg page wired to real data, so it is the reference for the
 * rest: all data access lives in `@/hooks/useClientes`, design tokens come
 * from the shared system (`bg-card`, `text-foreground`, `border-border`),
 * and the empty state is gated on `!loading` so it can never render over
 * data that is merely refetching.
 */
import { useState } from "react";
import {
  Badge,
  Button,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  Input,
  TableSkeleton,
} from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Pencil, Plus, Search, Trash2, UserCheck } from "lucide-react";

import {
  useAtivarCliente,
  useAtualizarCliente,
  useClientes,
  useCriarCliente,
  useRemoverCliente,
  type Cliente,
  type StatusCliente,
} from "@/hooks/useClientes";

/** Badge tone per funnel status. Inadimplente is destructive because it
 *  gates the Módulo 4 approval portal — it needs to read as a problem. */
const STATUS_VARIANT: Record<StatusCliente, BadgeVariant> = {
  prospect: "muted",
  ativo: "default",
  inativo: "outline",
  // Inadimplente gates the Módulo 4 approval portal — it must read as a problem.
  inadimplente: "destructive",
};

const STATUS_LABEL: Record<StatusCliente, string> = {
  prospect: "Prospect",
  ativo: "Ativo",
  inativo: "Inativo",
  inadimplente: "Inadimplente",
};

export default function Clientes() {
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState<StatusCliente | "">("");
  const [novoNome, setNovoNome] = useState("");
  const [novoNicho, setNovoNicho] = useState("");

  const { clientes, total, loading, error } = useClientes({
    busca: busca || undefined,
    status: status || undefined,
  });
  const criar = useCriarCliente();
  const ativar = useAtivarCliente();
  const atualizar = useAtualizarCliente();
  const remover = useRemoverCliente();

  /** The client open in the edit dialog, or null. */
  const [emEdicao, setEmEdicao] = useState<Cliente | null>(null);
  /** Deletion cascades to marca/contrato/pauta/tarefa, so it asks first. */
  const [aRemover, setARemover] = useState<Cliente | null>(null);

  function handleCriar(event: React.FormEvent) {
    event.preventDefault();
    const nome = novoNome.trim();
    if (!nome) return;
    criar.mutate(
      { nome, nicho: novoNicho.trim() || undefined },
      {
        onSuccess: () => {
          setNovoNome("");
          setNovoNicho("");
        },
      },
    );
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Clientes</h1>
          <p className="text-sm text-muted-foreground">
            {loading ? "Carregando…" : `${total} ${total === 1 ? "cliente" : "clientes"}`}
          </p>
        </div>
      </header>

      {/* ── Novo cliente ─────────────────────────────────────────── */}
      <form
        onSubmit={handleCriar}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-4"
      >
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="nome" className="mb-1 block text-xs text-muted-foreground">
            Nome
          </label>
          <Input
            id="nome"
            value={novoNome}
            onChange={(e) => setNovoNome(e.target.value)}
            placeholder="Padaria Sol"
          />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label htmlFor="nicho" className="mb-1 block text-xs text-muted-foreground">
            Nicho
          </label>
          <Input
            id="nicho"
            value={novoNicho}
            onChange={(e) => setNovoNicho(e.target.value)}
            placeholder="Alimentação"
          />
        </div>
        <Button type="submit" disabled={!novoNome.trim() || criar.isPending}>
          <Plus className="mr-2 h-4 w-4" />
          {criar.isPending ? "Salvando…" : "Adicionar"}
        </Button>
      </form>

      {criar.isError && (
        <p className="text-sm text-destructive">
          Não foi possível criar o cliente. Verifique os dados e tente novamente.
        </p>
      )}

      {/* ── Filtros ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Buscar por nome"
            className="pl-9"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome…"
          />
        </div>
        <select
          aria-label="Filtrar por status"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusCliente | "")}
          className="h-10 rounded-md border border-border bg-card px-3 text-sm text-foreground"
        >
          <option value="">Todos os status</option>
          {(Object.keys(STATUS_LABEL) as StatusCliente[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>

      {/* ── Lista ────────────────────────────────────────────────── */}
      {error ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-destructive">
          Não foi possível carregar os clientes.
        </p>
      ) : loading ? (
        <TableSkeleton rows={5} />
      ) : clientes.length === 0 ? (
        /* Reached only when NOT loading — an empty state shown during a
           background refetch would be lying about the data. */
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          {busca || status
            ? "Nenhum cliente corresponde aos filtros."
            : "Nenhum cliente ainda. Adicione o primeiro acima."}
        </p>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
          {clientes.map((cliente) => (
            <li key={cliente.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-foreground">{cliente.nome}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {cliente.nicho || "Sem nicho definido"}
                </p>
              </div>

              <Badge variant={STATUS_VARIANT[cliente.status]}>
                {STATUS_LABEL[cliente.status]}
              </Badge>

              {cliente.status === "prospect" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => ativar.mutate(cliente.id)}
                  disabled={ativar.isPending}
                  aria-label={`Ativar ${cliente.nome}`}
                >
                  <UserCheck className="mr-2 h-4 w-4" />
                  Ativar
                </Button>
              )}

              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEmEdicao(cliente)}
                aria-label={`Editar ${cliente.nome}`}
              >
                <Pencil className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => setARemover(cliente)}
                disabled={remover.isPending}
                aria-label={`Remover ${cliente.nome}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {emEdicao && (
        <DialogoEdicao
          cliente={emEdicao}
          salvando={atualizar.isPending}
          erro={atualizar.isError}
          onFechar={() => setEmEdicao(null)}
          onSalvar={(patch) =>
            atualizar.mutate(
              { id: emEdicao.id, ...patch },
              { onSuccess: () => setEmEdicao(null) },
            )
          }
        />
      )}

      {/* Hard delete cascades to marca / contrato / pauta / tarefa /
          apontamento — naming that in the prompt, because "are you sure?"
          alone does not tell anyone what they are about to lose. */}
      <Dialog open={!!aRemover} onClose={() => setARemover(null)} title="Remover cliente">
        <DialogHeader>Remover cliente</DialogHeader>
        <DialogBody>
          <p className="text-sm text-foreground">
            Remover <strong>{aRemover?.nome}</strong>?
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Isso apaga também a marca, os contratos, as pautas, as tarefas e os
            apontamentos de horas deste cliente. A ação não pode ser desfeita.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => setARemover(null)}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            disabled={remover.isPending}
            onClick={() => {
              if (!aRemover) return;
              remover.mutate(aRemover.id, { onSuccess: () => setARemover(null) });
            }}
          >
            {remover.isPending ? "Removendo…" : "Remover"}
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  );
}

/** Edit dialog — every field the API accepts, including the status the
 *  `ativar` shortcut cannot reach (inativo / inadimplente). */
function DialogoEdicao({
  cliente,
  salvando,
  erro,
  onFechar,
  onSalvar,
}: {
  cliente: Cliente;
  salvando: boolean;
  erro: boolean;
  onFechar: () => void;
  onSalvar: (patch: Record<string, string>) => void;
}) {
  const [form, setForm] = useState({
    nome: cliente.nome ?? "",
    nicho: cliente.nicho ?? "",
    email: cliente.email ?? "",
    telefone: cliente.telefone ?? "",
    origem: cliente.origem ?? "",
    observacoes: cliente.observacoes ?? "",
    status: cliente.status,
  });

  function campo(chave: keyof typeof form) {
    return {
      value: form[chave] as string,
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm({ ...form, [chave]: e.target.value }),
    };
  }

  return (
    <Dialog open onClose={onFechar} title={`Editar ${cliente.nome}`}>
      <DialogHeader>Editar cliente</DialogHeader>
      <DialogBody>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-muted-foreground">
            Nome
            <Input className="mt-1" {...campo("nome")} />
          </label>
          <label className="text-xs text-muted-foreground">
            Nicho
            <Input className="mt-1" {...campo("nicho")} />
          </label>
          <label className="text-xs text-muted-foreground">
            E-mail
            <Input className="mt-1" type="email" {...campo("email")} />
          </label>
          <label className="text-xs text-muted-foreground">
            Telefone
            <Input className="mt-1" {...campo("telefone")} />
          </label>
          <label className="text-xs text-muted-foreground">
            Origem
            <Input className="mt-1" {...campo("origem")} />
          </label>
          <label className="text-xs text-muted-foreground">
            Status
            <select
              className="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
              value={form.status}
              onChange={(e) =>
                setForm({ ...form, status: e.target.value as StatusCliente })
              }
            >
              {(Object.keys(STATUS_LABEL) as StatusCliente[]).map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="mt-3 block text-xs text-muted-foreground">
          Observações
          <textarea
            className="mt-1 min-h-[80px] w-full rounded-md border border-border bg-background p-2 text-sm text-foreground"
            value={form.observacoes}
            onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
          />
        </label>
        {erro && (
          <p className="mt-2 text-sm text-destructive">
            Não foi possível salvar as alterações.
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={onFechar}>Cancelar</Button>
        <Button
          disabled={!form.nome.trim() || salvando}
          onClick={() => onSalvar(form)}
        >
          {salvando ? "Salvando…" : "Salvar"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
