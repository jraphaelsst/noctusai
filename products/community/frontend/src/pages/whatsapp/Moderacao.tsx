/**
 * Moderação — `/whatsapp/moderacao` (community-m3-contract.md §3 endpoint 20).
 *
 * Human review queue for AI-flagged WhatsApp messages. An LLM flags; a person
 * decides every action: each flag is resolved ("Resolver") or dismissed
 * ("Descartar") individually, with an optional note. There is deliberately no
 * bulk approve. The API carries no message text and no author/phone (LGPD §6 —
 * only the AI's categorized justification and the group id), so none is shown.
 * Both `admin` and `moderador` can read and resolve ("moderation IS the
 * moderador's job"), so there is no admin gate here.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { EmptyState, ErrorState, Select, Textarea } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useGruposWhatsApp, useWhatsAppIndisponivel } from "@/hooks/useGruposWhatsApp";
import {
  useFlagsWhatsApp,
  useResolverFlag,
  type FlagEstado,
  type FlagSeveridade,
  type MensagemFlag,
} from "@/hooks/useFlagsWhatsApp";

const ESTADO_LABELS: Record<FlagEstado, string> = {
  aberta: "Pendente",
  resolvida: "Resolvida",
  descartada: "Descartada",
};

const SEVERIDADE_LABELS: Record<FlagSeveridade, string> = {
  baixa: "Baixa",
  media: "Média",
  alta: "Alta",
};

const NOTA_MAX = 1000;

function severidadeVariant(s: FlagSeveridade): BadgeVariant {
  return s === "alta" ? "destructive" : s === "media" ? "default" : "outline";
}

function formatDateBR(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("pt-BR");
}

export default function Moderacao() {
  const [estadoFiltro, setEstadoFiltro] = useState<FlagEstado | "">("aberta");
  const [severidadeFiltro, setSeveridadeFiltro] = useState<FlagSeveridade | "">("");
  const [notas, setNotas] = useState<Record<string, string>>({});

  const params = useMemo(
    () => ({ estado: estadoFiltro || undefined, severidade: severidadeFiltro || undefined, page: 1, page_size: 50 }),
    [estadoFiltro, severidadeFiltro],
  );
  const { data, isPending, isFetching, error } = useFlagsWhatsApp(params);
  const { data: grupos } = useGruposWhatsApp();
  const resolver = useResolverFlag();
  const indisponivel = useWhatsAppIndisponivel();

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  const grupoNome = useMemo(() => {
    const m = new Map<string, string>();
    for (const g of grupos?.items ?? []) m.set(g.id, g.nome);
    return m;
  }, [grupos]);

  async function decidir(flag: MensagemFlag, estado: "resolvida" | "descartada") {
    const nota = (notas[flag.id] ?? "").trim();
    try {
      await resolver.mutateAsync({ id: flag.id, estado, ...(nota ? { nota } : {}) });
      setNotas((prev) => {
        const next = { ...prev };
        delete next[flag.id];
        return next;
      });
      toast.success(estado === "resolvida" ? "Sinalização resolvida." : "Sinalização descartada.");
    } catch (err) {
      toast.error("Erro ao registrar decisão", { description: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Moderação</h1>
        <p className="text-sm text-muted-foreground">
          Mensagens sinalizadas pela IA. Cada decisão é de uma pessoa — nada é aprovado automaticamente.
          {isRefreshing ? " Atualizando…" : ""}
        </p>
      </div>

      {indisponivel && (
        <div
          className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-foreground"
          role="status"
          data-testid="moderacao-whatsapp-indisponivel"
        >
          {indisponivel} Novas sinalizações só chegam com o WhatsApp conectado.
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <Select
          className="w-56"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value as FlagEstado | "")}
          aria-label="Filtrar por estado"
        >
          <option value="">Todos os estados</option>
          {(Object.keys(ESTADO_LABELS) as FlagEstado[]).map((e) => (
            <option key={e} value={e}>
              {ESTADO_LABELS[e]}
            </option>
          ))}
        </Select>
        <Select
          className="w-56"
          value={severidadeFiltro}
          onChange={(e) => setSeveridadeFiltro(e.target.value as FlagSeveridade | "")}
          aria-label="Filtrar por severidade"
        >
          <option value="">Todas as severidades</option>
          {(Object.keys(SEVERIDADE_LABELS) as FlagSeveridade[]).map((s) => (
            <option key={s} value={s}>
              {SEVERIDADE_LABELS[s]}
            </option>
          ))}
        </Select>
      </div>

      {showSkeleton ? (
        <div className="h-40 animate-pulse rounded-lg bg-muted" data-testid="moderacao-skeleton" />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma mensagem sinalizada" />
      ) : (
        <ul className="space-y-3">
          {data.items.map((f) => {
            const aberta = f.estado === "aberta";
            return (
              <li
                key={f.id}
                className="space-y-3 rounded-lg border border-border bg-card p-4 shadow-sm"
                data-testid={`flag-${f.id}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={severidadeVariant(f.severidade)}>{SEVERIDADE_LABELS[f.severidade]}</Badge>
                  <Badge variant="outline">{f.categoria ?? "Sem categoria"}</Badge>
                  <Badge variant={aberta ? "default" : "outline"}>{ESTADO_LABELS[f.estado]}</Badge>
                  <span className="ml-auto text-xs text-muted-foreground">{formatDateBR(f.created_at)}</span>
                </div>
                <p className="text-sm text-foreground">{f.justificativa ?? "Sem justificativa registrada."}</p>
                <p className="text-xs text-muted-foreground">
                  Grupo: {f.grupo_id ? (grupoNome.get(f.grupo_id) ?? "Grupo desconhecido") : "—"}
                  {f.modelo ? ` · Modelo: ${f.modelo}` : ""}
                </p>
                {aberta ? (
                  <div className="space-y-2">
                    <Textarea
                      value={notas[f.id] ?? ""}
                      maxLength={NOTA_MAX}
                      rows={2}
                      placeholder="Nota (opcional)"
                      aria-label="Nota da decisão"
                      onChange={(e) => setNotas((prev) => ({ ...prev, [f.id]: e.target.value }))}
                      data-testid={`flag-nota-${f.id}`}
                    />
                    <div className="flex gap-2">
                      <Button
                        variant="primary"
                        disabled={resolver.isPending}
                        onClick={() => void decidir(f, "resolvida")}
                        data-testid={`flag-resolver-${f.id}`}
                      >
                        Resolver
                      </Button>
                      <button
                        type="button"
                        className="text-sm bg-muted rounded-md px-3 py-1.5 hover:bg-accent transition-colors disabled:opacity-50"
                        disabled={resolver.isPending}
                        onClick={() => void decidir(f, "descartada")}
                        data-testid={`flag-descartar-${f.id}`}
                      >
                        Descartar
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Decidida em {formatDateBR(f.resolvido_em)}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
