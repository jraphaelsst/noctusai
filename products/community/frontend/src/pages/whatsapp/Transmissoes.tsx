/**
 * Transmissões — `/whatsapp/transmissoes` (community-m3-contract.md §4).
 *
 * List plus composer (tipo, título, corpo with a character counter,
 * destination multi-select, "enviar agora" / "agendar") and a per-destino
 * delivery table on the detail dialog. Broadcasts go through the `jobs`
 * worker server-side (contract §5.6) — `POST .../enviar` returns 202, so the
 * FE never assumes delivery is instant: it shows `estado: "enviando"` and
 * re-fetches for the real per-destino outcome, exactly like `aplicado_parcial`
 * on the sync side never gets treated as a synchronous success/fail signal.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Input, Dialog, DialogHeader, DialogBody, DialogFooter } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Checkbox, EmptyState, ErrorState, Field, FormError, Select, Textarea } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useGruposWhatsApp } from "@/hooks/useGruposWhatsApp";
import {
  useTransmissoes,
  useCreateTransmissao,
  useUpdateTransmissao,
  useEnviarTransmissao,
  useDeleteTransmissao,
  type Transmissao,
  type TransmissaoEstado,
  type TransmissaoTipo,
} from "@/hooks/useTransmissoes";

const CORPO_MAX = 2000;

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

const TIPO_LABELS: Record<TransmissaoTipo, string> = {
  anuncio: "Anúncio",
  lembrete_evento: "Lembrete de evento",
  conteudo: "Conteúdo",
};

const ESTADO_LABELS: Record<TransmissaoEstado, string> = {
  rascunho: "Rascunho",
  agendada: "Agendada",
  enviando: "Enviando",
  enviada: "Enviada",
  falhou: "Falhou",
};

function estadoBadgeVariant(estado: TransmissaoEstado): BadgeVariant {
  switch (estado) {
    case "enviada":
      return "default";
    case "falhou":
      return "destructive";
    default:
      return "outline";
  }
}

function editable(t: Transmissao): boolean {
  return t.estado === "rascunho" || t.estado === "agendada";
}

export default function Transmissoes() {
  const [estadoFiltro, setEstadoFiltro] = useState<TransmissaoEstado | "">("");
  const [composerOpen, setComposerOpen] = useState(false);
  const [editing, setEditing] = useState<Transmissao | null>(null);
  const [detail, setDetail] = useState<Transmissao | null>(null);

  const params = useMemo(() => ({ estado: estadoFiltro || undefined, page: 1, page_size: 50 }), [estadoFiltro]);
  const { data, isPending, isFetching, error } = useTransmissoes(params);
  const enviar = useEnviarTransmissao();
  const excluir = useDeleteTransmissao();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  async function handleEnviar(t: Transmissao) {
    if (!window.confirm(`Enviar "${t.titulo}" agora?`)) return;
    try {
      const res = await enviar.mutateAsync(t.id);
      toast.success(`Envio iniciado para ${res.destinos} grupo(s).`);
    } catch (err) {
      toast.error("Erro ao enviar transmissão", { description: errorMessage(err) });
    }
  }

  async function handleExcluir(t: Transmissao) {
    if (!window.confirm(`Excluir "${t.titulo}"?`)) return;
    try {
      await excluir.mutateAsync(t.id);
      toast.success("Transmissão excluída.");
      setDetail(null);
    } catch (err) {
      toast.error("Erro ao excluir transmissão", { description: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Transmissões</h1>
          <p className="text-sm text-muted-foreground">
            Anúncios e lembretes enviados aos grupos do WhatsApp.
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setComposerOpen(true);
          }}
          data-testid="transmissoes-nova"
        >
          + Nova transmissão
        </Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select
          className="w-56"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value as TransmissaoEstado | "")}
          aria-label="Filtrar por estado"
        >
          <option value="">Todos os estados</option>
          {(Object.keys(ESTADO_LABELS) as TransmissaoEstado[]).map((e) => (
            <option key={e} value={e}>
              {ESTADO_LABELS[e]}
            </option>
          ))}
        </Select>
      </div>

      {showSkeleton ? (
        <div className="h-40 animate-pulse rounded-lg bg-muted" data-testid="transmissoes-skeleton" />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma transmissão ainda." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">Título</th>
                <th className="px-4 py-3 font-medium">Tipo</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium">Agendada/Enviada em</th>
                <th className="px-4 py-3 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((t) => (
                <tr
                  key={t.id}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50"
                  onClick={() => setDetail(t)}
                  data-testid={`transmissao-row-${t.id}`}
                >
                  <td className="px-4 py-3 text-foreground">{t.titulo}</td>
                  <td className="px-4 py-3 text-foreground">{TIPO_LABELS[t.tipo]}</td>
                  <td className="px-4 py-3">
                    <Badge variant={estadoBadgeVariant(t.estado)}>{ESTADO_LABELS[t.estado]}</Badge>
                  </td>
                  <td className="px-4 py-3 text-foreground">{formatDateBR(t.enviada_em ?? t.agendada_para)}</td>
                  <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-2">
                      {editable(t) && (
                        <button
                          type="button"
                          className="text-sm bg-muted rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                          onClick={() => {
                            setEditing(t);
                            setComposerOpen(true);
                          }}
                          data-testid={`transmissao-editar-${t.id}`}
                        >
                          Editar
                        </button>
                      )}
                      {editable(t) && (
                        <button
                          type="button"
                          className="text-sm bg-primary/10 text-primary rounded-md px-3 py-1.5 hover:bg-primary/20 transition-colors"
                          onClick={() => void handleEnviar(t)}
                          data-testid={`transmissao-enviar-${t.id}`}
                        >
                          Enviar
                        </button>
                      )}
                      {editable(t) && (
                        <button
                          type="button"
                          className="text-sm bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                          onClick={() => void handleExcluir(t)}
                          data-testid={`transmissao-excluir-${t.id}`}
                        >
                          Excluir
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {composerOpen && (
        <ComposerDialog
          transmissao={editing}
          onClose={() => {
            setComposerOpen(false);
            setEditing(null);
          }}
        />
      )}
      {detail && <DetailDialog transmissao={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function ComposerDialog({ transmissao, onClose }: { transmissao: Transmissao | null; onClose: () => void }) {
  const [tipo, setTipo] = useState<TransmissaoTipo>(transmissao?.tipo ?? "anuncio");
  const [titulo, setTitulo] = useState(transmissao?.titulo ?? "");
  const [corpo, setCorpo] = useState(transmissao?.corpo ?? "");
  const [grupoIds, setGrupoIds] = useState<string[]>(
    transmissao?.destinos?.map((d) => d.grupo_id) ?? [],
  );
  const [agendarPara, setAgendarPara] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const { data: gruposData } = useGruposWhatsApp({ ativo: true, page_size: 100 });
  const criar = useCreateTransmissao();
  const atualizar = useUpdateTransmissao();
  const isPending = criar.isPending || atualizar.isPending;

  function toggleGrupo(id: string) {
    setGrupoIds((prev) => (prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]));
  }

  function handleSubmit(e: FormEvent, agendar: boolean) {
    e.preventDefault();
    setFormError(null);
    if (grupoIds.length === 0) {
      setFormError("Selecione ao menos um grupo de destino.");
      return;
    }
    const payload = {
      titulo,
      corpo,
      tipo,
      grupo_ids: grupoIds,
      ...(agendar && agendarPara ? { agendada_para: new Date(agendarPara).toISOString() } : {}),
    };
    const onSettled = {
      onSuccess: () => {
        toast.success(transmissao ? "Transmissão atualizada." : "Transmissão salva.");
        onClose();
      },
      onError: (err: unknown) => setFormError(errorMessage(err)),
    };
    if (transmissao) {
      atualizar.mutate({ id: transmissao.id, ...payload }, onSettled);
    } else {
      criar.mutate(payload, onSettled);
    }
  }

  return (
    <Dialog open onClose={onClose} title={transmissao ? "Editar transmissão" : "Nova transmissão"} className="max-w-lg">
      <form onSubmit={(e) => handleSubmit(e, !!agendarPara)}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">
            {transmissao ? "Editar transmissão" : "Nova transmissão"}
          </h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Tipo" required>
            <Select value={tipo} onChange={(e) => setTipo(e.target.value as TransmissaoTipo)} required>
              {(Object.keys(TIPO_LABELS) as TransmissaoTipo[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_LABELS[t]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Título" required>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
          </Field>
          <Field label="Corpo" required help={`${corpo.length}/${CORPO_MAX} caracteres`}>
            <Textarea
              value={corpo}
              onChange={(e) => setCorpo(e.target.value.slice(0, CORPO_MAX))}
              rows={5}
              required
            />
          </Field>
          <Field label="Grupos de destino" required>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {(gruposData?.items ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">Nenhum grupo ativo cadastrado.</p>
              ) : (
                (gruposData?.items ?? []).map((g) => (
                  <Checkbox
                    key={g.id}
                    id={`destino-${g.id}`}
                    label={g.nome}
                    checked={grupoIds.includes(g.id)}
                    onChange={() => toggleGrupo(g.id)}
                    data-testid={`transmissao-destino-${g.id}`}
                  />
                ))
              )}
            </div>
          </Field>
          <Field label="Agendar para (opcional)" help="Deixe em branco para salvar como rascunho">
            <input
              type="datetime-local"
              className="w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm"
              value={agendarPara}
              onChange={(e) => setAgendarPara(e.target.value)}
            />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={isPending}>
            {isPending ? "Salvando..." : agendarPara ? "Agendar" : "Salvar como rascunho"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function DetailDialog({ transmissao, onClose }: { transmissao: Transmissao; onClose: () => void }) {
  const destinos = transmissao.destinos ?? [];
  return (
    <Dialog open onClose={onClose} title={transmissao.titulo} className="max-w-xl">
      <DialogHeader>
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-foreground">{transmissao.titulo}</h2>
          <Badge variant={estadoBadgeVariant(transmissao.estado)}>{ESTADO_LABELS[transmissao.estado]}</Badge>
        </div>
      </DialogHeader>
      <DialogBody className="space-y-4">
        <p className="whitespace-pre-wrap text-sm text-foreground">{transmissao.corpo}</p>
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Entrega por grupo
          </h3>
          {destinos.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="transmissao-destinos-vazio">
              Nenhum destino registrado ainda.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm" data-testid="transmissao-destinos-tabela">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Grupo</th>
                    <th className="px-3 py-2 font-medium">Estado</th>
                    <th className="px-3 py-2 font-medium">Enviado em</th>
                    <th className="px-3 py-2 font-medium">Erro</th>
                  </tr>
                </thead>
                <tbody>
                  {destinos.map((d) => (
                    <tr key={d.id} className="border-b border-border last:border-0" data-testid={`destino-row-${d.id}`}>
                      <td className="px-3 py-2 text-foreground">{d.grupo_nome ?? d.grupo_id}</td>
                      <td className="px-3 py-2">
                        <Badge variant={d.estado === "enviado" ? "default" : d.estado === "falhou" ? "destructive" : "outline"}>
                          {d.estado}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-foreground">{formatDateBR(d.enviado_em)}</td>
                      <td className="px-3 py-2 text-foreground">{d.erro ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
