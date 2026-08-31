import { useState } from 'react';
import { Loader2, BarChart3, Users, CalendarDays, DollarSign, Star, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@noctusai/seed/components/ui/select';
import { formatCurrency } from '@/lib/utils';
import { useBiResumo, useBiSessoes, useBiReceita, useBiCancelamentos } from '@/hooks/useBi';

const PERIODOS = [
  { value: '7d', label: 'Ultimos 7 dias' },
  { value: '30d', label: 'Ultimos 30 dias' },
  { value: '90d', label: 'Ultimos 90 dias' },
];

export default function BiDashboard() {
  const [periodo, setPeriodo] = useState('30d');
  const { data: resumo, isPending: resumoPending } = useBiResumo();
  const { data: sessoes, isPending: sessoesPending } = useBiSessoes(periodo);
  const { data: receita } = useBiReceita(periodo);
  const { data: cancelamentos } = useBiCancelamentos();

  const metrics = [
    { label: 'Total Sessoes', value: resumo?.total_sessoes ?? 0, icon: CalendarDays, color: 'text-blue-500', format: (v: number) => String(v) },
    { label: 'Receita Total', value: resumo?.receita_total ?? 0, icon: DollarSign, color: 'text-green-500', format: formatCurrency },
    { label: 'Pacientes Ativos', value: resumo?.pacientes_ativos ?? 0, icon: Users, color: 'text-purple-500', format: (v: number) => String(v) },
    { label: 'Media Avaliacao', value: resumo?.media_avaliacao ?? 0, icon: Star, color: 'text-yellow-500', format: (v: number) => v.toFixed(1) },
  ];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6" /> Dashboard BI
          </h1>
          <p className="text-muted-foreground">Metricas e indicadores do seu consultorio</p>
        </div>
        <Select value={periodo} onValueChange={setPeriodo}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIODOS.map((p) => (
              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Metric Cards */}
      {resumoPending && !resumo ? (
        <div className="flex h-32 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((m) => (
            <Card key={m.label}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{m.label}</CardTitle>
                <m.icon className={`h-5 w-5 ${m.color}`} />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{m.format(m.value)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Sessions breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Sessoes por Periodo</CardTitle>
        </CardHeader>
        <CardContent>
          {sessoesPending && !sessoes ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : !sessoes || sessoes.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum dado disponivel para o periodo selecionado.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Data</th>
                    <th className="pb-2 pr-4 text-right">Total</th>
                    <th className="pb-2 pr-4 text-right">Concluidas</th>
                    <th className="pb-2 text-right">Canceladas</th>
                  </tr>
                </thead>
                <tbody>
                  {sessoes.map((s, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-4">{s.data}</td>
                      <td className="py-2 pr-4 text-right font-medium">{s.total}</td>
                      <td className="py-2 pr-4 text-right text-green-600">{s.concluidas}</td>
                      <td className="py-2 text-right text-red-600">{s.canceladas}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Revenue breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Receita por Periodo</CardTitle>
        </CardHeader>
        <CardContent>
          {!receita || receita.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum dado de receita disponivel.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Data</th>
                    <th className="pb-2 text-right">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {receita.map((r, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-4">{r.data}</td>
                      <td className="py-2 text-right font-medium text-green-600">{formatCurrency(r.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cancellation reasons */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-500" /> Motivos de Cancelamento
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!cancelamentos || cancelamentos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum cancelamento registrado.</p>
          ) : (
            <div className="space-y-2">
              {cancelamentos.map((c, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-sm">{c.motivo}</span>
                  <Badge variant="outline">{c.total}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
