/**
 * Vista showcase — Agência tab. Agency metadata cards.
 * Moved out of `pages/VistaShowcase.tsx` unchanged (2026-08-22 split).
 */
import { ExternalLink } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import { useVistaAgencias } from '@/hooks/useVistaShowcase';
import { EmptyPanel, ErrorPanel } from './shared';

export function AgenciaTab() {
  const { data: agencias, isLoading, isError, error } = useVistaAgencias(true);
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError) return <ErrorPanel error={error as Error} />;
  if (!agencias || agencias.length === 0) {
    return <EmptyPanel message="Nenhuma agência retornada." />;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {agencias.map(a => (
        <Card key={a.codigo}>
          <CardHeader>
            <CardTitle className="text-base">{a.nome ?? a.codigo}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <div><span className="text-slate-500">Endereço:</span> {a.endereco ?? '—'}</div>
            <div><span className="text-slate-500">Bairro:</span> {a.bairro ?? '—'}</div>
            <div><span className="text-slate-500">Cidade:</span> {a.cidade ?? '—'}</div>
            <div className="flex items-center gap-1">
              <span className="text-slate-500">Site:</span>
              {a.site
                ? <a href={a.site.startsWith('http') ? a.site : `https://${a.site}`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline flex items-center gap-1">{a.site} <ExternalLink className="h-3 w-3" /></a>
                : '—'}
            </div>
            <div className="text-[11px] text-slate-400 pt-2">Código Vista: {a.codigo}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
