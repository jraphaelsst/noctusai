/**
 * Grupoterapia (staff) — `/grupoterapia` (CONTRACT.md ninho-vazio
 * §Grupoterapia + §Frontend FE-A).
 *
 * Sessions CRUD + status changes + each session's reservations. Writes are
 * admin-only (the server 403s a `moderador`; the controls are not rendered
 * for one). A session with reservations cannot be deleted (409) — it is
 * cancelled instead, which the backend records on each seated member's
 * timeline. The CVV care line (`LinhaDeCuidado`, owned by FE-B) is on every
 * grupoterapia screen by contract.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
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
import { EmptyState, ErrorState, Field, FormError, Select, Textarea } from "@/components/FormControls";
import { LinhaDeCuidado } from "@/components/LinhaDeCuidado";
import { errorMessage } from "@/lib/errors";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import {
  useCreateSessao,
  useDeleteSessao,
  useGrupoterapiaSessoes,
  useSessaoReservas,
  useUpdateSessao,
  type Sessao,
  type SessaoInput,
  type SessaoStatus,
} from "@/hooks/useGrupoterapiaSessoes";

const STATUS_LABELS: Record<SessaoStatus, string> = {
  agendada: "Agendada",
  realizada: "Realizada",
  cancelada: "Cancelada",
};

function statusVariant(s: SessaoStatus): BadgeVariant {
  if (s === "agendada") return "default";
  if (s === "cancelada") return "destructive";
  return "muted";
}

function formatDataHora(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** ISO-8601 → the local `YYYY-MM-DDTHH:mm` a datetime-local input expects. */
export function isoParaInputLocal(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function Grupoterapia() {
  const isAdmin = useIsAdmin();
  const [status, setStatus] = useState<SessaoStatus | "">("");
  const [formFor, setFormFor] = useState<Sessao | "nova" | null>(null);
  const [reservasFor, setReservasFor] = useState<Sessao | null>(null);

  const { data, isPending, isFetching, error } = useGrupoterapiaSessoes(status ? { status } : undefined);
  const updateSessao = useUpdateSessao();
  const deleteSessao = useDeleteSessao();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  async function mudarStatus(s: Sessao, novo: SessaoStatus) {
    const confirmacao =
      novo === "cancelada"
        ? `Cancelar a sessão "${s.titulo}"?${s.reservas ? ` As ${s.reservas} reservas confirmadas serão registradas no histórico de cada membro.` : ""}`
        : `Marcar a sessão "${s.titulo}" como realizada?`;
    if (!window.confirm(confirmacao)) return;
    try {
      await updateSessao.mutateAsync({ id: s.id, status: novo });
      toast.success(novo === "cancelada" ? "Sessão cancelada." : "Sessão marcada como realizada.");
    } catch (err) {
      toast.error("Erro ao alterar a sessão", { description: errorMessage(err) });
    }
  }

  async function excluir(s: Sessao) {
    if (!window.confirm(`Excluir a sessão "${s.titulo}"? Esta ação não pode ser desfeita.`)) return;
    try {
      await deleteSessao.mutateAsync(s.id);
      toast.success("Sessão excluída.");
    } catch (err) {
      toast.error("Erro ao excluir a sessão", { description: errorMessage(err) });
    }
  }

  const items = [...(data?.items ?? [])].sort((a, b) => b.inicio.localeCompare(a.inicio));

  return (
    <div className="space-y-6" data-testid="grupoterapia-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Grupoterapia</h1>
          <p className="text-sm text-muted-foreground">
            Sessões, vagas de fala e reservas.
            {/* lying-loading-ok: text-only suffix, the table stays mounted */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        {isAdmin && (
          <Button variant="primary" onClick={() => setFormFor("nova")}>
            + Nova sessão
          </Button>
        )}
      </div>

      <LinhaDeCuidado />

      <Select
        className="w-56"
        value={status}
        onChange={(e) => setStatus(e.target.value as SessaoStatus | "")}
        aria-label="Filtrar por status da sessão"
      >
        <option value="">Todos os status</option>
        {(Object.keys(STATUS_LABELS) as SessaoStatus[]).map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </Select>

      {showSkeleton ? (
        <TableSkeleton rows={5} columns={6} />
      ) : error && !data ? (
        <ErrorState message={errorMessage(error)} />
      ) : items.length === 0 ? (
        <EmptyState
          message={status ? "Nenhuma sessão com este status." : "Nenhuma sessão ainda. Agende a primeira."}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Sessão</th>
                <th className="px-4 py-3 font-medium">Início</th>
                <th className="px-4 py-3 font-medium">Duração</th>
                <th className="px-4 py-3 font-medium">Vagas de fala</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0" data-testid={`sessao-row-${s.id}`}>
                  <td className="px-4 py-3 text-foreground">
                    <div className="font-medium">{s.titulo}</div>
                    {s.link_sala ? (
                      <a href={s.link_sala} target="_blank" rel="noreferrer" className="text-xs text-primary underline">
                        Link da sala
                      </a>
                    ) : (
                      <span className="text-xs text-muted-foreground">Sem link da sala</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground">{formatDataHora(s.inicio)}</td>
                  <td className="px-4 py-3 text-foreground">{s.duracao_minutos} min</td>
                  <td className="px-4 py-3 text-foreground tabular-nums">
                    {s.reservas} / {s.vagas_fala}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={statusVariant(s.status)}>{STATUS_LABELS[s.status] ?? s.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => setReservasFor(s)} data-testid={`sessao-reservas-${s.id}`}>
                        Reservas
                      </Button>
                      {isAdmin && s.status === "agendada" && (
                        <>
                          <Button variant="outline" size="sm" onClick={() => setFormFor(s)}>
                            Editar
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => void mudarStatus(s, "realizada")}>
                            Realizada
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => void mudarStatus(s, "cancelada")}
                            data-testid={`sessao-cancelar-${s.id}`}
                          >
                            Cancelar
                          </Button>
                        </>
                      )}
                      {isAdmin && s.reservas === 0 && (
                        <Button variant="destructive" size="sm" onClick={() => void excluir(s)} data-testid={`sessao-excluir-${s.id}`}>
                          Excluir
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formFor && <SessaoFormDialog sessao={formFor === "nova" ? null : formFor} onClose={() => setFormFor(null)} />}
      {reservasFor && <ReservasDialog sessao={reservasFor} onClose={() => setReservasFor(null)} />}
    </div>
  );
}

function SessaoFormDialog({ sessao, onClose }: { sessao: Sessao | null; onClose: () => void }) {
  const [form, setForm] = useState(() => ({
    titulo: sessao?.titulo ?? "",
    descricao: sessao?.descricao ?? "",
    inicio: sessao ? isoParaInputLocal(sessao.inicio) : "",
    duracao_minutos: String(sessao?.duracao_minutos ?? 90),
    link_sala: sessao?.link_sala ?? "",
    vagas_fala: String(sessao?.vagas_fala ?? 8),
  }));
  const [formError, setFormError] = useState<string | null>(null);
  const create = useCreateSessao();
  const update = useUpdateSessao();
  const saving = create.isPending || update.isPending;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const inicio = new Date(form.inicio);
    if (Number.isNaN(inicio.getTime())) {
      setFormError("Informe a data e a hora de início.");
      return;
    }
    const payload: SessaoInput = {
      titulo: form.titulo.trim(),
      descricao: form.descricao.trim() || null,
      inicio: inicio.toISOString(),
      duracao_minutos: Number(form.duracao_minutos),
      link_sala: form.link_sala.trim() || null,
      vagas_fala: Number(form.vagas_fala),
    };
    const handlers = {
      onSuccess: () => {
        toast.success(sessao ? "Sessão atualizada." : "Sessão criada.");
        onClose();
      },
      onError: (err: unknown) => setFormError(errorMessage(err)),
    };
    if (sessao) update.mutate({ id: sessao.id, ...payload }, handlers);
    else create.mutate(payload, handlers);
  }

  const titulo = sessao ? "Editar sessão" : "Nova sessão";

  return (
    <Dialog open onClose={onClose} title={titulo} className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">{titulo}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Título" required>
            <Input
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              maxLength={120}
              required
            />
          </Field>
          <Field label="Descrição">
            <Textarea
              rows={3}
              maxLength={2000}
              value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
            />
          </Field>
          <Field label="Início" required>
            <Input
              type="datetime-local"
              value={form.inicio}
              onChange={(e) => setForm({ ...form, inicio: e.target.value })}
              required
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Duração (minutos)" required>
              <Input
                type="number"
                min={15}
                max={480}
                value={form.duracao_minutos}
                onChange={(e) => setForm({ ...form, duracao_minutos: e.target.value })}
                required
              />
            </Field>
            <Field label="Vagas de fala" required>
              <Input
                type="number"
                min={0}
                max={100}
                value={form.vagas_fala}
                onChange={(e) => setForm({ ...form, vagas_fala: e.target.value })}
                required
              />
            </Field>
          </div>
          <Field label="Link da sala" help="Só é mostrado para quem o plano permite assistir.">
            <Input
              type="url"
              maxLength={500}
              value={form.link_sala}
              onChange={(e) => setForm({ ...form, link_sala: e.target.value })}
              placeholder="https://"
            />
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

function ReservasDialog({ sessao, onClose }: { sessao: Sessao; onClose: () => void }) {
  const { data, isPending, isFetching, error } = useSessaoReservas(sessao.id);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <Dialog open onClose={onClose} title="Reservas" className="max-w-md">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Reservas — {sessao.titulo}</h2>
        <p className="text-xs text-muted-foreground">
          {formatDataHora(sessao.inicio)} · {sessao.reservas} de {sessao.vagas_fala} vagas de fala
          {/* lying-loading-ok: text-only suffix */}
          {isRefreshing ? " · Atualizando…" : ""}
        </p>
      </DialogHeader>
      <DialogBody data-testid="reservas-dialog">
        {showSkeleton ? (
          <TableSkeleton rows={3} columns={2} />
        ) : error && !data ? (
          <ErrorState message={errorMessage(error)} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="Nenhuma reserva de vaga de fala nesta sessão." />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-foreground">{r.membro_nome}</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {formatDataHora(r.created_at)}
                  <Badge variant={r.status === "confirmada" ? "default" : "muted"}>
                    {r.status === "confirmada" ? "Confirmada" : "Cancelada"}
                  </Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
