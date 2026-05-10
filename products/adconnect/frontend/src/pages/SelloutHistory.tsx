/**
 * SelloutHistory — Phase 7 SKELETON.
 *
 * Sellout history list. Shows month, mode, status, and review state.
 */
import { useNavigate } from "react-router-dom";
import { FileText, Plus } from "lucide-react";
import { useSelloutHistory } from "@/hooks/useSellout";
import type { SelloutStatus, SelloutSubmissionMode } from "@/types";

const statusLabel: Record<SelloutStatus, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  recusado: "Recusado",
};

const statusClass: Record<SelloutStatus, string> = {
  pendente: "bg-warning/10 text-warning",
  aprovado: "bg-success/10 text-success",
  recusado: "bg-destructive/10 text-destructive",
};

const modeLabel: Record<SelloutSubmissionMode, string> = {
  structured: "Formulário",
  nfe_xml: "NF-e XML",
  freeform: "Anexo livre",
};

export default function SelloutHistory() {
  const navigate = useNavigate();
  const { data: reports, isLoading, error } = useSelloutHistory();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <FileText className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Histórico de sellout
            </h1>
            <p className="text-sm text-muted-foreground">
              Relatórios enviados e status de revisão
            </p>
          </div>
        </div>
        <button
          onClick={() => navigate("/sellout/submit")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" /> Novo relatório
        </button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Carregando…</p>}
      {error && <p className="text-sm text-destructive">Erro: {error.message}</p>}

      {!isLoading && reports.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed bg-muted/30 p-12 text-center space-y-3">
          <FileText className="h-10 w-10 text-muted-foreground/40 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Nenhum relatório enviado ainda.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Mês</th>
                <th className="text-left px-4 py-3 font-medium">Modo</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Enviado em</th>
                <th className="text-left px-4 py-3 font-medium">Revisado em</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{r.period_month}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {modeLabel[r.submission_mode]}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${statusClass[r.status]}`}>
                      {statusLabel[r.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(r.submitted_at).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {r.reviewed_at
                      ? new Date(r.reviewed_at).toLocaleDateString("pt-BR")
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
