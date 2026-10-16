/** Expanded team body: month picker + per-member metrics table. */
import { Loader2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { formatarTpr, useMetricasEquipe } from "@/hooks/useLaisEquipes";

function fmtAcesso(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

interface Props { equipeId: string; mes: string; onMes: (m: string) => void }

export function EquipeMetricas({ equipeId, mes, onMes }: Props) {
  const q = useMetricasEquipe(equipeId, mes);
  const linhas = q.data ?? [];
  return (
    <div className="space-y-3 border-t px-4 py-3" data-testid="equipe-metricas">
      <div className="flex items-center gap-2 text-sm">
        <label htmlFor={`mes-${equipeId}`} className="text-muted-foreground">Mês</label>
        <Input id={`mes-${equipeId}`} type="month" value={mes} className="h-8 w-40"
          onChange={(e) => e.target.value && onMes(e.target.value)} />
        {q.isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
      </div>
      {q.showSkeleton && <p className="text-sm text-muted-foreground" data-testid="metricas-loading">Carregando métricas…</p>}
      {q.isError && !q.data && <p className="text-sm text-destructive" role="alert">Não foi possível carregar as métricas.</p>}
      {q.data && linhas.length === 0 && <p className="text-sm text-muted-foreground">Sem membros para exibir métricas.</p>}
      {linhas.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-muted-foreground">
              <th className="py-1">Usuário</th><th>Último acesso</th><th>TPR</th><th>Conversas</th><th>Distribuição</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((m) => (
              <tr key={m.user_id} className="border-t" data-testid="metrica-linha">
                <td className="py-1.5">{m.nome}</td>
                <td>{fmtAcesso(m.ultimo_acesso)}</td>
                <td>{formatarTpr(m.tpr_segundos)}</td>
                <td>{m.conversas}</td>
                <td>{m.distribuicao}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
