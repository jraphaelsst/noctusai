/**
 * Relationship timeline inside the Membros detail dialog (CONTRACT.md
 * ninho-vazio §Identity, `GET|POST /api/membros/{id}/eventos`).
 *
 * The backend writes most eventos itself (status, plano, pagamento,
 * assinatura, acesso, grupoterapia, sistema); staff add `nota` / `contato`
 * here — moderadores included, per the contract. Newest first, as served.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { FormError, Select, Textarea } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import {
  useCreateMembroEvento,
  useMembroEventos,
  type EventoCreateInput,
  type EventoTipo,
} from "@/hooks/useMembroEventos";

const TIPO_LABELS: Record<EventoTipo, string> = {
  status: "Status",
  plano: "Plano",
  pagamento: "Pagamento",
  assinatura: "Assinatura",
  nota: "Nota",
  contato: "Contato",
  acesso: "Acesso",
  grupoterapia: "Grupoterapia",
  sistema: "Sistema",
};

function tipoVariant(tipo: EventoTipo): BadgeVariant {
  if (tipo === "nota" || tipo === "contato") return "default";
  if (tipo === "sistema") return "destructive";
  return "outline";
}

const PAGE_STEP = 50;
const PAGE_MAX = 200;

function formatDataHora(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function MembroTimeline({ membroId }: { membroId: string }) {
  const [pageSize, setPageSize] = useState(PAGE_STEP);
  const { data, isPending, isFetching, error } = useMembroEventos(membroId, 1, pageSize);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const items = data?.items ?? [];

  return (
    <section className="mt-4 border-t border-border pt-4" data-testid="membro-timeline">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Linha do tempo
        {/* lying-loading-ok: text-only suffix, the list stays mounted */}
        {isRefreshing ? <span className="ml-2 font-normal normal-case">Atualizando…</span> : null}
      </h3>

      <NovoEventoForm membroId={membroId} />

      {showSkeleton ? (
        <div className="mt-3 space-y-2" data-testid="membro-timeline-skeleton">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : error && !data ? (
        <p role="alert" className="mt-3 text-sm text-destructive" data-testid="membro-timeline-erro">
          {errorMessage(error)}
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground" data-testid="membro-timeline-vazio">
          Nenhum registro ainda. Anote o primeiro contato acima.
        </p>
      ) : (
        <ol className="mt-3 space-y-3">
          {items.map((ev) => (
            <li key={ev.id} className="border-l-2 border-border pl-3" data-testid={`evento-${ev.id}`}>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant={tipoVariant(ev.tipo)}>{TIPO_LABELS[ev.tipo] ?? ev.tipo}</Badge>
                <span>{formatDataHora(ev.created_at)}</span>
                <span>· {ev.autor_nome ?? (ev.autor_id ? "Equipe" : "Sistema")}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{ev.descricao}</p>
            </li>
          ))}
        </ol>
      )}

      {data && data.total > items.length && pageSize < PAGE_MAX && (
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => setPageSize((n) => Math.min(n + PAGE_STEP, PAGE_MAX))}
        >
          Ver mais ({data.total - items.length} restantes)
        </Button>
      )}
    </section>
  );
}

function NovoEventoForm({ membroId }: { membroId: string }) {
  const [tipo, setTipo] = useState<EventoCreateInput["tipo"]>("nota");
  const [descricao, setDescricao] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const criar = useCreateMembroEvento(membroId);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const texto = descricao.trim();
    if (!texto) return;
    criar.mutate(
      { tipo, descricao: texto },
      {
        onSuccess: () => {
          setDescricao("");
          toast.success(tipo === "nota" ? "Nota registrada." : "Contato registrado.");
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2" data-testid="membro-timeline-form">
      <FormError message={formError} />
      <div className="flex gap-2">
        <Select
          className="w-32"
          value={tipo}
          onChange={(e) => setTipo(e.target.value as EventoCreateInput["tipo"])}
          aria-label="Tipo de registro"
        >
          <option value="nota">Nota</option>
          <option value="contato">Contato</option>
        </Select>
        <Button type="submit" size="sm" variant="primary" disabled={criar.isPending || !descricao.trim()}>
          {criar.isPending ? "Salvando..." : "Registrar"}
        </Button>
      </div>
      <Textarea
        rows={2}
        maxLength={2000}
        value={descricao}
        onChange={(e) => setDescricao(e.target.value)}
        placeholder={tipo === "nota" ? "O que a equipe precisa lembrar sobre ela?" : "Como foi o contato?"}
        aria-label="Descrição do registro"
      />
    </form>
  );
}
