/**
 * Shared primitives for the Vista CRM showcase tabs.
 *
 * Extracted from `pages/VistaShowcase.tsx` when the Clientes tab was wired
 * (2026-08-22), acting on the note that page had carried since Phase 1:
 * "~620 lines, 7 inline tab components — next time someone meaningfully edits
 * this page, split each tab into components/vista/<TabName>Tab.tsx".
 *
 * Nothing here is Vista-specific beyond the status vocabulary; the formatters
 * and panels are shared by every tab.
 */
import { AlertTriangle } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';

export const formatBRL = (value: number | null | undefined) =>
  value == null
    ? '—'
    : value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

export const formatArea = (value: number | null | undefined) =>
  value == null ? '—' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} m²`;

export const STATUS_PILL: Record<string, { label: string; tone: string }> = {
  live: { label: 'Conectado', tone: 'bg-emerald-100 text-emerald-800' },
  permission_denied: { label: '401 — Permissão pendente', tone: 'bg-amber-100 text-amber-800' },
  // Vista ALLOWS this one — the block is on our side (LGPD intake + wiring).
  // Distinct from permission_denied so the UI stops sending users to chase a
  // vendor grant that already landed (2026-08-21). See vista.md § 4.2.
  // Clientes has since moved on to `live`; the status stays because the
  // distinction is real and the next gated-then-granted family will need it.
  pending_intake: { label: 'Liberado — pendente LGPD', tone: 'bg-sky-100 text-sky-800' },
  // Label carries no HTTP code on purpose: this status covers a genuine 404
  // AND /imoveis/fotos, which is really a 405 (exists, write-only). The tab
  // copy states the precise reason; the pill just says "unavailable".
  not_found: { label: 'Indisponível', tone: 'bg-slate-200 text-slate-700' },
  not_configured: { label: 'Sem credenciais', tone: 'bg-rose-100 text-rose-800' },
  doc_only: { label: 'Apenas documentação', tone: 'bg-slate-100 text-slate-600' },
};

export function StatusPill({ status }: { status: string }) {
  const meta = STATUS_PILL[status] ?? { label: status, tone: 'bg-slate-100 text-slate-700' };
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${meta.tone}`}>
      {meta.label}
    </span>
  );
}

export function FilterInput({
  label, value, onChange, onEnter,
}: { label: string; value?: string; onChange: (v: string) => void; onEnter?: () => void }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-600">{label}</label>
      <Input
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        onKeyDown={onEnter ? (e) => { if (e.key === 'Enter') onEnter(); } : undefined}
        placeholder={`Filtrar por ${label.toLowerCase()}`}
      />
    </div>
  );
}

export function PaginationBar({
  page, pageSize, total, paginas, fetchedAt, noun, onPrev, onNext, disabled,
}: {
  page: number; pageSize: number; total: number | null; paginas: number | null;
  fetchedAt: string; noun: string; onPrev: () => void; onNext: () => void; disabled: boolean;
}) {
  const lastPage = paginas ?? Infinity;
  return (
    <div className="flex items-center justify-between gap-3 text-xs text-slate-600 px-1">
      <div>
        Página <strong>{page}</strong>{paginas ? ` / ${paginas}` : ''} ·
        {' '}
        {pageSize} de {total?.toLocaleString('pt-BR') ?? '?'} {noun} ·
        <span className="text-slate-400 ml-1">atualizado {new Date(fetchedAt).toLocaleTimeString('pt-BR')}</span>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onPrev} disabled={disabled || page <= 1}>‹ Anterior</Button>
        <Button variant="outline" size="sm" onClick={onNext} disabled={disabled || page >= lastPage}>Próxima ›</Button>
      </div>
    </div>
  );
}

export function ErrorPanel({ error }: { error: Error }) {
  return (
    <Card className="border-rose-200 bg-rose-50">
      <CardContent className="p-4 text-sm text-rose-800 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5" />
        <span>{error?.message || 'Erro desconhecido.'}</span>
      </CardContent>
    </Card>
  );
}

export function EmptyPanel({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="p-8 text-center text-sm text-slate-500">{message}</CardContent>
    </Card>
  );
}
