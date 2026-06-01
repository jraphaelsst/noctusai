/**
 * RewardsLedger — Phase 7 SKELETON.
 *
 * Distributor rewards ledger: accrued cashback + verba_mkt, status, redemption.
 */
import { Award, Coins } from "lucide-react";
import { useRewards } from "@/hooks/useRewards";
import type { RewardStatus, RewardType } from "@/types";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

const typeLabel: Record<RewardType, string> = {
  cashback: "Cashback",
  verba_mkt: "Verba MKT",
};

const statusLabel: Record<RewardStatus, string> = {
  pendente: "Pendente",
  liberado: "Liberado",
  utilizado: "Utilizado",
  expirado: "Expirado",
};

const statusClass: Record<RewardStatus, string> = {
  pendente: "bg-warning/10 text-warning",
  liberado: "bg-success/10 text-success",
  utilizado: "bg-muted text-muted-foreground",
  expirado: "bg-destructive/10 text-destructive",
};

export default function RewardsLedger() {
  const { data: rewards = [], isLoading, error } = useRewards();
  // Totals are derived client-side from the rewards list (the hook returns the
  // raw Reward[] query, not pre-aggregated totals).
  const totalAccrued = rewards.reduce((sum, r) => sum + r.amount, 0);
  const totalAvailable = rewards
    .filter((r) => r.status === "liberado")
    .reduce((sum, r) => sum + r.amount, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Award className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Recompensas</h1>
          <p className="text-sm text-muted-foreground">
            Cashback e verba de marketing acumulados
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Coins className="h-4 w-4" />
            <span className="text-xs uppercase tracking-wide">Total acumulado</span>
          </div>
          <p className="text-2xl font-bold text-foreground">
            {formatBRL(totalAccrued)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2 text-success">
            <Coins className="h-4 w-4" />
            <span className="text-xs uppercase tracking-wide">Disponível para uso</span>
          </div>
          <p className="text-2xl font-bold text-success">
            {formatBRL(totalAvailable)}
          </p>
        </div>
      </div>

      {/* Ledger */}
      {isLoading && <p className="text-sm text-muted-foreground">Carregando…</p>}
      {error && <p className="text-sm text-destructive">Erro: {error.message}</p>}

      {!isLoading && rewards.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed bg-muted/30 p-12 text-center space-y-3">
          <Award className="h-10 w-10 text-muted-foreground/40 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Você ainda não tem recompensas acumuladas. Faça pedidos e envie sellout
            para começar a acumular.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Data</th>
                <th className="text-left px-4 py-3 font-medium">Tipo</th>
                <th className="text-left px-4 py-3 font-medium">Origem</th>
                <th className="text-left px-4 py-3 font-medium">Descrição</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-right px-4 py-3 font-medium">Valor</th>
              </tr>
            </thead>
            <tbody>
              {rewards.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(r.accrued_at).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3">{typeLabel[r.type]}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {r.source_pedido_id ?? r.source_relatorio_sellout_id ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {r.description ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${statusClass[r.status]}`}>
                      {statusLabel[r.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-semibold">
                    {formatBRL(r.amount)}
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
