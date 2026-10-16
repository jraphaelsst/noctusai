/** Per-charge status banner: queued / generating / retrying / generated / failed (+ last error) / skipped (+ why). */
import { chargeBanner, gatewayCancelNote, type BannerTone } from "@/lib/charges";
import type { Charge } from "@/hooks/useFinancial";

const TONE: Record<BannerTone, string> = {
  neutral: "border-border bg-muted/40 text-muted-foreground",
  progress: "border-blue-200 bg-blue-50 text-blue-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  success: "border-green-200 bg-green-50 text-green-800",
  danger: "border-red-200 bg-red-50 text-red-800",
};

export function ChargeStatusBanner({ charge, onRequeue, requeuing }: { charge: Charge; onRequeue?: (entryId: string) => void; requeuing?: boolean }) {
  const banner = chargeBanner(charge);
  const cancelNote = gatewayCancelNote(charge);
  return (
    <div className="space-y-1" data-testid={`charge-banner-${charge.entry_id}`} data-status={banner.status}>
      <div className={`rounded-md border px-2 py-1 text-xs ${TONE[banner.tone]}`} role="status">
        <p className="font-medium">{banner.title}</p>
        {banner.detail ? <p className="mt-0.5 break-words opacity-90">{banner.detail}</p> : null}
        {banner.status === "generated" && charge.invoice_url ? (
          <p className="mt-0.5">
            <a className="underline" href={charge.invoice_url} target="_blank" rel="noreferrer">Abrir fatura</a>
            {charge.pix_payload ? (
              <button type="button" className="ml-3 underline" onClick={() => void navigator.clipboard?.writeText(charge.pix_payload ?? "")}>
                Copiar PIX
              </button>
            ) : null}
          </p>
        ) : null}
        {banner.canRequeue && onRequeue ? (
          <button type="button" disabled={requeuing} className="mt-1 underline disabled:opacity-50" onClick={() => onRequeue(charge.entry_id)}>
            {banner.status === "failed" ? "Tentar novamente" : "Gerar no gateway"}
          </button>
        ) : null}
      </div>
      {charge.preserved_after_deactivation ? (
        <p className="text-[11px] text-muted-foreground">Mantida após a inativação do cliente</p>
      ) : null}
      {cancelNote ? <p className="text-[11px] text-red-700">{cancelNote}</p> : null}
    </div>
  );
}
