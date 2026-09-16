/**
 * Membros — `/membros` (community-m1-contract.md §Frontend).
 *
 * Status tabs (counts from `resumo`, which the backend computes with every
 * filter EXCEPT `status` — so switching tabs never moves the badges),
 * search + plan filter, a table, and row-click → `<EntityDetailDialog/>`
 * (`@noctusai/lib/components`) carrying the Editar / Alterar status /
 * Cancelar actions — the same shape social-wiring's `LeadDetailModal`
 * uses: chrome from the organ, content from a per-entity descriptor this
 * page owns. Create/edit is a page-local form dialog (like social-wiring's
 * `LeadFormDialog`) rather than `<ResourceManager/>`, because this list
 * needs server-side status/search/plan filtering + a `resumo` alongside
 * `items`/`total` that ResourceManager's self-contained, unparameterized
 * `api.get(apiPath)` fetch has no seam for.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Input,
  TableSkeleton,
  Dialog,
  DialogHeader,
  DialogBody,
  DialogFooter,
} from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { EntityDetailDialog } from "@noctusai/lib/components";
import type { DetailSection } from "@noctusai/lib/components";
import { EmptyState, ErrorState, Field, FormError, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import {
  useMembros,
  useCreateMembro,
  useUpdateMembro,
  useChangeMembroStatus,
  useCancelMembro,
  type Membro,
  type MembroCreateInput,
  type MembroStatus,
} from "@/hooks/useMembros";
import { usePlanos, type Plano } from "@/hooks/usePlanos";

const STATUS_LABELS: Record<MembroStatus, string> = {
  pendente: "Pendente",
  ativo: "Ativo",
  atrasado: "Atrasado",
  pausado: "Pausado",
  cancelado: "Cancelado",
};

const ORIGEM_LABELS: Record<Membro["origem"], string> = {
  checkout: "Checkout",
  aplicacao: "Aplicação",
  convite: "Convite",
};

function statusBadgeVariant(status: MembroStatus): BadgeVariant {
  switch (status) {
    case "ativo":
      return "default";
    case "atrasado":
    case "cancelado":
      return "destructive";
    default:
      return "outline";
  }
}

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

const TABS: Array<{ key: "todos" | MembroStatus; label: string }> = [
  { key: "todos", label: "Todos" },
  { key: "pendente", label: "Pendentes" },
  { key: "ativo", label: "Ativos" },
  { key: "atrasado", label: "Atrasados" },
  { key: "pausado", label: "Pausados" },
  { key: "cancelado", label: "Cancelados" },
];

function membroDetailSections(m: Membro): DetailSection[] {
  return [
    {
      fields: [
        { label: "Nome", value: m.nome },
        { label: "E-mail", value: m.email },
        { label: "Telefone", value: m.telefone ?? undefined },
        { label: "Plano", value: m.plano_nome ?? undefined },
        { label: "Origem", value: ORIGEM_LABELS[m.origem] },
        { label: "Tags", value: m.tags.length ? m.tags.join(", ") : undefined },
        { label: "Entrou em", value: formatDateBR(m.entrou_em) },
        { label: "Observações", value: m.observacoes ?? undefined, wide: true },
      ],
    },
  ];
}

export default function Membros() {
  const [tab, setTab] = useState<"todos" | MembroStatus>("todos");
  const [buscaInput, setBuscaInput] = useState("");
  const [busca, setBusca] = useState("");
  const [planoId, setPlanoId] = useState("");
  const [selected, setSelected] = useState<Membro | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Membro | null>(null);
  const [statusChangeFor, setStatusChangeFor] = useState<Membro | null>(null);

  // Small debounce so every keystroke doesn't fire a request.
  useEffect(() => {
    const t = setTimeout(() => setBusca(buscaInput.trim()), 300);
    return () => clearTimeout(t);
  }, [buscaInput]);

  const params = useMemo(
    () => ({
      status: tab === "todos" ? undefined : tab,
      plano_id: planoId || undefined,
      busca: busca || undefined,
      page: 1,
      page_size: 50,
    }),
    [tab, planoId, busca],
  );

  const { data, isPending, isFetching, error } = useMembros(params);
  const { data: planosData } = usePlanos({ ativo: true, page_size: 100 });
  const cancelMembro = useCancelMembro();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  async function handleCancel(m: Membro) {
    if (!window.confirm(`Cancelar o membro "${m.nome}"? Isso remove o acesso dele.`)) return;
    try {
      await cancelMembro.mutateAsync(m.id);
      toast.success("Membro cancelado.");
      setSelected(null);
    } catch (err) {
      toast.error("Erro ao cancelar membro", { description: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Membros</h1>
          <p className="text-sm text-muted-foreground">
            Registros de membros da comunidade.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          + Novo Membro
        </Button>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Status do membro">
        {TABS.map((t) => (
          <Button
            key={t.key}
            variant={tab === t.key ? "primary" : "outline"}
            size="sm"
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {t.key !== "todos" ? ` (${data?.resumo?.[t.key] ?? 0})` : ""}
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Buscar por nome ou e-mail"
            value={buscaInput}
            onChange={(e) => setBuscaInput(e.target.value)}
            aria-label="Buscar membros"
          />
        </div>
        <Select
          className="w-56"
          value={planoId}
          onChange={(e) => setPlanoId(e.target.value)}
          aria-label="Filtrar por plano"
        >
          <option value="">Todos os planos</option>
          {(planosData?.items ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </Select>
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={5} />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhum membro encontrado." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Nome</th>
                <th className="px-4 py-3 font-medium">E-mail</th>
                <th className="px-4 py-3 font-medium">Plano</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Entrou em</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((m) => (
                <tr
                  key={m.id}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50"
                  onClick={() => setSelected(m)}
                  data-testid={`membro-row-${m.id}`}
                >
                  <td className="px-4 py-3 text-foreground">{m.nome}</td>
                  <td className="px-4 py-3 text-foreground">{m.email}</td>
                  <td className="px-4 py-3 text-foreground">{m.plano_nome ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={statusBadgeVariant(m.status)}>{STATUS_LABELS[m.status]}</Badge>
                  </td>
                  <td className="px-4 py-3 text-foreground">{formatDateBR(m.entrou_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <EntityDetailDialog
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.nome ?? ""}
        subtitle={selected?.email}
        badges={selected ? [{ label: STATUS_LABELS[selected.status], variant: statusBadgeVariant(selected.status) }] : []}
        sections={selected ? membroDetailSections(selected) : []}
        actions={
          selected
            ? [
                {
                  label: "Cancelar membro",
                  variant: "destructive",
                  align: "start",
                  onClick: () => void handleCancel(selected),
                  testId: "membro-cancelar",
                },
                {
                  label: "Alterar status",
                  variant: "outline",
                  onClick: () => setStatusChangeFor(selected),
                  testId: "membro-alterar-status",
                },
                {
                  label: "Editar",
                  variant: "primary",
                  onClick: () => {
                    setEditing(selected);
                    setFormOpen(true);
                  },
                  testId: "membro-editar",
                },
              ]
            : []
        }
        testId="membro-detail-dialog"
      />

      {formOpen && (
        <MembroFormDialog
          membro={editing}
          planos={planosData?.items ?? []}
          onClose={() => setFormOpen(false)}
        />
      )}
      {statusChangeFor && (
        <StatusChangeDialog membro={statusChangeFor} onClose={() => setStatusChangeFor(null)} />
      )}
    </div>
  );
}

function emptyMembroForm(): MembroCreateInput {
  return { nome: "", email: "", telefone: "", origem: "convite", plano_id: "", tags: [], observacoes: "" };
}

function fromMembro(m: Membro): MembroCreateInput & { plano_id: string } {
  return {
    nome: m.nome,
    email: m.email,
    telefone: m.telefone ?? "",
    origem: m.origem,
    plano_id: m.plano_id ?? "",
    tags: m.tags,
    observacoes: m.observacoes ?? "",
  };
}

interface MembroFormDialogProps {
  membro: Membro | null;
  planos: Plano[];
  onClose: () => void;
}

function MembroFormDialog({ membro, planos, onClose }: MembroFormDialogProps) {
  const [form, setForm] = useState(() => (membro ? fromMembro(membro) : emptyMembroForm()));
  const [tagsInput, setTagsInput] = useState(() => (membro ? membro.tags.join(", ") : ""));
  const [formError, setFormError] = useState<string | null>(null);
  const createMembro = useCreateMembro();
  const updateMembro = useUpdateMembro();
  const isPending = createMembro.isPending || updateMembro.isPending;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const payload: MembroCreateInput = {
      nome: form.nome,
      email: form.email,
      telefone: form.telefone || null,
      origem: form.origem,
      plano_id: form.plano_id || null,
      tags,
      observacoes: form.observacoes || null,
    };
    const onSettled = {
      onSuccess: () => {
        toast.success(membro ? "Membro atualizado." : "Membro criado.");
        onClose();
      },
      onError: (err: unknown) => setFormError(errorMessage(err)),
    };
    if (membro) {
      updateMembro.mutate({ id: membro.id, ...payload }, onSettled);
    } else {
      createMembro.mutate(payload, onSettled);
    }
  }

  return (
    <Dialog open onClose={onClose} title={membro ? "Editar Membro" : "Novo Membro"} className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">{membro ? "Editar Membro" : "Novo Membro"}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Nome" required>
            <Input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} required />
          </Field>
          <Field label="E-mail" required>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </Field>
          <Field label="Telefone" help="Formato internacional, ex: +5511999999999">
            <Input
              value={form.telefone ?? ""}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
              placeholder="+5511999999999"
            />
          </Field>
          <Field label="Origem" required>
            <Select
              value={form.origem}
              onChange={(e) => setForm({ ...form, origem: e.target.value as Membro["origem"] })}
              required
            >
              <option value="checkout">Checkout</option>
              <option value="aplicacao">Aplicação</option>
              <option value="convite">Convite</option>
            </Select>
          </Field>
          <Field label="Plano">
            <Select value={form.plano_id ?? ""} onChange={(e) => setForm({ ...form, plano_id: e.target.value })}>
              <option value="">Sem plano</option>
              {planos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Tags" help="Separe por vírgula">
            <Input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} placeholder="fundadora, vip" />
          </Field>
          <Field label="Observações">
            <textarea
              className="w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm"
              rows={3}
              value={form.observacoes ?? ""}
              onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
            />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={isPending}>
            {isPending ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function StatusChangeDialog({ membro, onClose }: { membro: Membro; onClose: () => void }) {
  const [status, setStatus] = useState<MembroStatus>(membro.status);
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const changeStatus = useChangeMembroStatus();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    changeStatus.mutate(
      { id: membro.id, status, motivo: motivo || undefined },
      {
        onSuccess: () => {
          toast.success("Status atualizado.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Alterar status" className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Alterar status de {membro.nome}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Novo status" required>
            <Select value={status} onChange={(e) => setStatus(e.target.value as MembroStatus)} required>
              {(Object.keys(STATUS_LABELS) as MembroStatus[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Motivo (opcional)">
            <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ex: pagamento manual" />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={changeStatus.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={changeStatus.isPending}>
            {changeStatus.isPending ? "Salvando..." : "Confirmar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
