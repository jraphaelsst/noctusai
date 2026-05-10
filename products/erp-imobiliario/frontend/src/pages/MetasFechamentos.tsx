/**
 * /metas/fechamentos — period closings + "fechar período" action + CSV export.
 */
import { useState } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { Archive, CheckCircle2, AlertTriangle, Download, Lock } from 'lucide-react';
import {
  useFecharPeriodo, useFechamentos, usePeriodos,
} from '@/hooks/useMetasDomain';

function brl(n: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(n || 0);
}

function toCsv(rows: any[]): string {
  if (!rows.length) return '';
  const header = Object.keys(rows[0]).join(',');
  const body = rows.map((r) =>
    Object.values(r).map((v) => {
      const s = v == null ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(',')
  ).join('\n');
  return `${header}\n${body}`;
}

export default function MetasFechamentos() {
  const { data: periodos = [] } = usePeriodos();
  const [periodoId, setPeriodoId] = useState<string | null>(null);
  const { data: fechamentos = [], isLoading } = useFechamentos(periodoId ?? undefined);
  const fechar = useFecharPeriodo();
  const [confirmOpen, setConfirmOpen] = useState<string | null>(null);

  const periodoSelecionado = periodos.find((p: any) => p.id === periodoId);

  function handleFechar(id: string) {
    fechar.mutate(id, { onSuccess: () => setConfirmOpen(null) });
  }

  function exportCsv() {
    const rows = fechamentos.map((f: any) => ({
      corretor_id: f.corretor_id,
      corretor_nome: f.corretor_nome ?? '',
      pontos_total: f.pontos_total ?? 0,
      vgv_total: f.vgv_total ?? 0,
      score_unificado: f.score_unificado ?? 0,
      rank: f.rank ?? '',
      fechado_em: f.fechado_em ?? '',
    }));
    const csv = toCsv(rows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fechamentos${periodoSelecionado ? `-${periodoSelecionado.tipo}-${periodoSelecionado.data_inicio}` : ''}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <div className="mb-6 flex items-center gap-2">
        <Archive className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Fechamentos de Período</h1>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">
        Cada período encerrado gera um snapshot imutável dos pontos, VGV e
        ranking por agente. Fechar é idempotente — re-executar reutiliza o
        snapshot existente.
      </p>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Período</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <select
            value={periodoId ?? ''}
            onChange={(e) => setPeriodoId(e.target.value || null)}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">Todos os períodos</option>
            {periodos.map((p: any) => (
              <option key={p.id} value={p.id}>
                {p.tipo} — {p.data_inicio} a {p.data_fim} ({p.status})
              </option>
            ))}
          </select>

          {periodoSelecionado && periodoSelecionado.status !== 'fechado' && (
            <div className="flex items-start gap-3 rounded border border-amber-500/40 bg-amber-500/10 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div className="flex-1">
                <p className="text-sm font-medium">
                  Este período está "{periodoSelecionado.status}" — pode ser fechado.
                </p>
                <p className="text-xs text-muted-foreground">
                  Ao fechar: pontos/VGV são agregados por agente, score unificado calculado,
                  ranking snapshot gravado. O status do período vira "fechado" e não pode mais
                  receber eventos. Operação é idempotente.
                </p>
              </div>
              <Button
                size="sm"
                onClick={() => setConfirmOpen(periodoSelecionado.id)}
                className="shrink-0 gap-1"
              >
                <Lock className="h-3.5 w-3.5" /> Fechar período
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Snapshots ({fechamentos.length})
            </CardTitle>
            <CardDescription>
              {isLoading ? 'Carregando…' : 'Cada linha é um fechamento por agente.'}
            </CardDescription>
          </div>
          {fechamentos.length > 0 && (
            <Button variant="outline" size="sm" className="gap-1" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {!fechamentos.length ? (
            <p className="text-sm text-muted-foreground">
              Nenhum fechamento encontrado para o filtro atual.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 text-left">Agente</th>
                    <th className="py-2 text-right">Pontos</th>
                    <th className="py-2 text-right">VGV</th>
                    <th className="py-2 text-right">Score</th>
                    <th className="py-2 text-right">Rank</th>
                    <th className="py-2 text-right">Fechado em</th>
                  </tr>
                </thead>
                <tbody>
                  {fechamentos.map((f: any) => (
                    <tr key={f.id} className="border-b last:border-0">
                      <td className="py-2">{f.corretor_nome || f.corretor_id}</td>
                      <td className="py-2 text-right">{f.pontos_total ?? 0}</td>
                      <td className="py-2 text-right">{brl(Number(f.vgv_total ?? 0))}</td>
                      <td className="py-2 text-right">
                        {f.score_unificado?.toFixed?.(1) ?? '—'}
                      </td>
                      <td className="py-2 text-right">
                        {f.rank ? <Badge variant="outline">#{f.rank}</Badge> : '—'}
                      </td>
                      <td className="py-2 text-right text-muted-foreground">
                        {f.fechado_em ? new Date(f.fechado_em).toLocaleDateString('pt-BR') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {confirmOpen && (
        <Dialog open onOpenChange={(v) => !v && setConfirmOpen(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Fechar período?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Esta ação vai agregar todos os eventos do período e congelar o ranking.
              Após fechar, o período não aceita mais eventos. A operação é idempotente —
              rodar de novo não duplica snapshots.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(null)}>Cancelar</Button>
              <Button
                onClick={() => handleFechar(confirmOpen!)}
                disabled={fechar.isPending}
              >
                {fechar.isPending ? 'Fechando…' : 'Confirmar fechamento'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
