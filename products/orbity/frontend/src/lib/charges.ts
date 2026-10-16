/** Pure helpers for the Financeiro charges view (money in cents, pt-BR copy, one place for the status vocabulary). */
import type { Charge, GenerationStatus } from "@/hooks/useFinancial";

export function formatCents(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatReais(value: number): string {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("pt-BR");
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export type BannerTone = "neutral" | "progress" | "warning" | "success" | "danger";

export interface ChargeBanner {
  status: GenerationStatus;
  tone: BannerTone;
  title: string;
  /** The last error / the reason it stayed a plain receivable, when there is one. */
  detail: string | null;
  /** `failed` and `skipped` can be sent (again) once the cause is fixed. */
  canRequeue: boolean;
}

/** The per-charge status banner: what the worker did with this receivable and why. */
export function chargeBanner(c: Pick<Charge, "generation_status" | "last_error" | "next_attempt_at" | "generation_attempts" | "entry_status">): ChargeBanner {
  const open = c.entry_status === "open" || c.entry_status === "partial";
  switch (c.generation_status) {
    case "queued":
      return { status: "queued", tone: "neutral", title: "Na fila para gerar no gateway", detail: null, canRequeue: false };
    case "generating":
      return { status: "generating", tone: "progress", title: "Gerando a cobrança no gateway…", detail: null, canRequeue: false };
    case "retrying":
      return {
        status: "retrying",
        tone: "warning",
        title: `Nova tentativa agendada (tentativa ${c.generation_attempts})`,
        detail: [c.last_error, c.next_attempt_at ? `Próxima tentativa: ${formatDateTime(c.next_attempt_at)}` : null].filter(Boolean).join(" · ") || null,
        canRequeue: false,
      };
    case "generated":
      return { status: "generated", tone: "success", title: "Cobrança gerada no gateway", detail: null, canRequeue: false };
    case "failed":
      return { status: "failed", tone: "danger", title: "Falha ao gerar a cobrança", detail: c.last_error, canRequeue: open };
    case "skipped":
    default:
      return { status: "skipped", tone: "neutral", title: "Recebível simples (sem cobrança no gateway)", detail: c.last_error, canRequeue: open };
  }
}

/** The extra line about the gateway-side cancel of a cancelled charge, when one is queued/failed. */
export function gatewayCancelNote(c: Pick<Charge, "gateway_cancel_status" | "gateway_cancel_error">): string | null {
  if (c.gateway_cancel_status === "pending") return `Cancelamento no gateway pendente${c.gateway_cancel_error ? `: ${c.gateway_cancel_error}` : ""}`;
  if (c.gateway_cancel_status === "failed") return `Não foi possível cancelar no gateway: ${c.gateway_cancel_error ?? "erro desconhecido"}`;
  return null;
}

export const ENTRY_STATUS_LABEL: Record<Charge["entry_status"], string> = {
  open: "Em aberto",
  partial: "Pago em parte",
  paid: "Pago",
  cancelled: "Cancelado",
};

export const GENERATION_STATUS_FILTER: { value: GenerationStatus | ""; label: string }[] = [
  { value: "", label: "Todos os status do gateway" },
  { value: "queued", label: "Na fila" },
  { value: "generating", label: "Gerando" },
  { value: "retrying", label: "Tentando de novo" },
  { value: "generated", label: "Gerada" },
  { value: "failed", label: "Com falha" },
  { value: "skipped", label: "Sem gateway" },
];
