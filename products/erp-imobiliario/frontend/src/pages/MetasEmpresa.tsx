/**
 * /metas/metas-empresa — owner-side VGV goal setting + per-team distribution.
 *
 * Flow:
 *   1. Pick a period (quinzenal / mensal / trimestral)
 *   2. Set company meta VGV for that period
 *   3. Distribute the total to teams — live validation against saldo_a_alocar
 *      and estouro from /api/metas/empresa/resumo
 *   4. "Distribuir igualmente" / "Distribuir por headcount" quick actions
 */
import { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Target, TrendingUp, Scale, Users, Divide, Equal } from 'lucide-react';
import {
  useCascadeResumo,
  useEquipes,
  useMetasEmpresa,
  useMetasEquipe,
  usePeriodos,
  useUpsertMetaEmpresa,
  useUpsertMetaEquipe,
} from '@/hooks/useMetasDomain';

function brl(n: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(n || 0);
}

export default function MetasEmpresa() {
  const { data: periodos = [] } = usePeriodos();
  const [periodoId, setPeriodoId] = useState<string | null>(null);

  const periodo = periodos.find((p: any) => p.id === periodoId);
  const { data: metasEmpresa = [] } = useMetasEmpresa(periodoId ?? undefined);
  const metaAtual = metasEmpresa.find((m: any) => m.categoria === 'vgv');
  const { data: cascade } = useCascadeResumo(periodoId);
  const { data: equipes = [] } = useEquipes();
  const { data: metasEquipe = [] } = useMetasEquipe(periodoId ?? undefined);
  const upsertEmpresa = useUpsertMetaEmpresa();
  const upsertEquipe = useUpsertMetaEquipe();

  // Default to the first open period when data arrives.
  useEffect(() => {
    if (!periodoId && periodos.length > 0) {
      const aberto = periodos.find((p: any) => p.status === 'aberto') ?? periodos[0];
      setPeriodoId(aberto.id);
    }
  }, [periodos, periodoId]);

  // Local edit state for company meta VGV.
  const [valorEmpresa, setValorEmpresa] = useState<string>('');
  useEffect(() => {
    setValorEmpresa(metaAtual ? String(metaAtual.valor_meta) : '');
  }, [metaAtual?.valor_meta]);

  // Local edit state for each team's allocation.
  const [allocs, setAllocs] = useState<Record<string, string>>({});
  useEffect(() => {
    const map: Record<string, string> = {};
    for (const e of equipes) {
      const q = metasEquipe.find((m: any) => m.equipe_id === e.id && m.categoria === 'vgv');
      map[e.id] = q ? String(q.valor_meta) : '';
    }
    setAllocs(map);
  }, [equipes.length, metasEquipe.length, periodoId]);

  const parsedEmpresa = Number(valorEmpresa || 0);
  const totalAllocated = useMemo(
    () => Object.values(allocs).reduce((acc, v) => acc + (Number(v) || 0), 0),
    [allocs],
  );
  const saldo = parsedEmpresa - totalAllocated;

  async function saveEmpresa() {
    if (!periodoId) return;
    await upsertEmpresa.mutateAsync({
      periodo_id: periodoId,
      valor_meta: parsedEmpresa,
      categoria: 'vgv',
    });
  }

  async function saveAllTeams() {
    if (!periodoId) return;
    const jobs = equipes.map((e: any) => {
      const valor = Number(allocs[e.id] || 0);
      return upsertEquipe.mutateAsync({
        periodo_id: periodoId,
        equipe_id: e.id,
        valor_meta: valor,
        categoria: 'vgv',
      });
    });
    await Promise.all(jobs);
  }

  function distribuirIgualmente() {
    if (!equipes.length || !parsedEmpresa) return;
    const each = Math.floor(parsedEmpresa / equipes.length);
    const map: Record<string, string> = {};
    equipes.forEach((e: any, i: number) => {
      // Last team gets the remainder so the sum is exact.
      map[e.id] = String(i === equipes.length - 1 ? parsedEmpresa - each * (equipes.length - 1) : each);
    });
    setAllocs(map);
  }

  function zerar() {
    const map: Record<string, string> = {};
    for (const e of equipes) map[e.id] = '0';
    setAllocs(map);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10">
      <div className="mb-6 flex items-center gap-2">
        <Target className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Metas da Empresa</h1>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">
        Defina o VGV alvo da empresa por período e distribua entre as equipes.
        O backend aplica cascata — a soma das metas das equipes não pode
        exceder a meta da empresa (estouro é sinalizado aqui em tempo real).
      </p>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Período
          </CardTitle>
        </CardHeader>
        <CardContent>
          <select
            value={periodoId ?? ''}
            onChange={(e) => setPeriodoId(e.target.value || null)}
            className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="" disabled>Selecione um período…</option>
            {periodos.map((p: any) => (
              <option key={p.id} value={p.id}>
                {p.tipo} — {p.data_inicio} a {p.data_fim} ({p.status})
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      {periodo && (
        <>
          <Card className="mb-4">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Scale className="h-4 w-4" />
                Meta da Empresa
              </CardTitle>
              <CardDescription>
                VGV total que a empresa deve bater neste período.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="mb-1 block text-xs text-muted-foreground">Valor (R$)</label>
                  <Input
                    type="number"
                    min={0}
                    step={1000}
                    value={valorEmpresa}
                    onChange={(e) => setValorEmpresa(e.target.value)}
                    placeholder="Ex: 10000000"
                  />
                </div>
                <Button
                  onClick={saveEmpresa}
                  disabled={upsertEmpresa.isPending || !parsedEmpresa}
                  className="whitespace-nowrap"
                >
                  {upsertEmpresa.isPending ? 'Salvando…' : 'Salvar meta'}
                </Button>
              </div>
              {metaAtual && (
                <p className="text-xs text-muted-foreground">
                  Atual: {brl(metaAtual.valor_meta)}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="h-4 w-4" />
                Distribuição por Equipe
              </CardTitle>
              <CardDescription>
                Alocado: <strong>{brl(totalAllocated)}</strong> ·{' '}
                Saldo a alocar:{' '}
                <strong className={saldo < 0 ? 'text-destructive' : saldo === 0 ? 'text-green-600 dark:text-green-400' : ''}>
                  {brl(saldo)}
                </strong>
                {cascade && cascade.estouro > 0 && (
                  <Badge variant="destructive" className="ml-2">Estouro: {brl(cascade.estouro)}</Badge>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={distribuirIgualmente}
                  disabled={!parsedEmpresa || !equipes.length}
                  className="gap-1"
                >
                  <Divide className="h-3.5 w-3.5" />
                  Distribuir igualmente
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={zerar}
                  className="gap-1"
                >
                  <Equal className="h-3.5 w-3.5" />
                  Zerar alocações
                </Button>
              </div>

              {!equipes.length ? (
                <p className="text-sm text-muted-foreground">
                  Nenhuma equipe. Crie equipes em <code>Metas & Desempenho → Equipes</code>.
                </p>
              ) : (
                <ul className="space-y-2">
                  {equipes.map((e: any) => (
                    <li key={e.id} className="flex items-center gap-3 rounded border border-border bg-card p-3">
                      <div
                        className="h-3 w-3 shrink-0 rounded-full"
                        style={{ background: e.cor || '#999' }}
                      />
                      <span className="flex-1 text-sm font-medium">{e.nome}</span>
                      <Input
                        type="number"
                        min={0}
                        step={1000}
                        value={allocs[e.id] ?? ''}
                        onChange={(ev) => setAllocs((prev) => ({ ...prev, [e.id]: ev.target.value }))}
                        className="w-40"
                        placeholder="0"
                      />
                      <span className="w-20 text-right text-xs text-muted-foreground">
                        {parsedEmpresa > 0
                          ? `${Math.round((Number(allocs[e.id] || 0) / parsedEmpresa) * 100)}%`
                          : '—'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex items-center justify-end pt-2">
                <Button
                  onClick={saveAllTeams}
                  disabled={upsertEquipe.isPending || !equipes.length}
                >
                  {upsertEquipe.isPending ? 'Salvando…' : 'Salvar distribuição'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
