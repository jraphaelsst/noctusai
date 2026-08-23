/**
 * Vista showcase — Diagnóstico tab. Tenant probe + per-endpoint status.
 * Moved out of `pages/VistaShowcase.tsx` unchanged (2026-08-22 split).
 */
import { RefreshCcw } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useVistaDiagnostico } from '@/hooks/useVistaShowcase';
import { ErrorPanel, StatusPill } from './shared';

export function DiagnosticoTab() {
  const { data, isLoading, isError, error, refetch, isFetching } = useVistaDiagnostico(true);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Tenant Vista</span>
            <Button onClick={() => refetch()} variant="outline" size="sm" disabled={isFetching}>
              <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Re-probar
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          {isLoading && <Skeleton className="h-12 w-full" />}
          {isError && <ErrorPanel error={error as Error} />}
          {data && (
            <>
              <div>
                <span className="text-slate-500">Base URL:</span>{' '}
                <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{data.tenant_base_url || '(não configurada)'}</code>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Status:</span>
                {data.configured
                  ? <StatusPill status="live" />
                  : <StatusPill status="not_configured" />}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {data && data.probes.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Probes por endpoint</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>HTTP</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Latência</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.probes.map(p => (
                  <TableRow key={p.endpoint}>
                    <TableCell><code className="text-xs">{p.endpoint}</code></TableCell>
                    <TableCell>{p.http_status ?? '—'}</TableCell>
                    <TableCell><StatusPill status={probeStatusToPill(p.status)} /></TableCell>
                    <TableCell>{p.latency_ms != null ? `${p.latency_ms} ms` : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Probe statuses are a different vocabulary from tab statuses — this maps
 *  the overlap and lets everything else fall through to `doc_only`. There is
 *  deliberately no `pending_intake` case: that is a TAB status (our side is
 *  blocked), and a probe can never report it. */
function probeStatusToPill(status: string): string {
  if (status === 'ok') return 'live';
  if (status === 'permission_denied') return 'permission_denied';
  if (status === 'not_found') return 'not_found';
  if (status === 'not_configured') return 'not_configured';
  return 'doc_only';
}
