/** Version history with rollback (activating an archived version). */
import { Badge, Button } from '@noctusai/lib/design-system';
import type { BrandIdentitySummary, BrandStatus } from '../../lib/brand-contract';

const LABEL: Record<BrandStatus, string> = { draft: 'Rascunho', active: 'Ativa', archived: 'Arquivada', failed: 'Falhou' };
const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString('pt-BR') : '—');

export function BrandHistory({
  rows, selectedId, onOpen,
}: { rows: BrandIdentitySummary[]; selectedId: string | null; onOpen: (id: string) => void }) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">Nenhuma versão ainda. Envie o material da marca para criar a primeira.</p>;
  return (
    <ul className="divide-y divide-border rounded-md border border-border" data-testid="brand-history">
      {[...rows].sort((a, b) => b.version - a.version).map((r) => (
        <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
          <span className="text-foreground">Versão {r.version}</span>
          <Badge>{LABEL[r.status]}</Badge>
          <span className="flex-1 text-xs text-muted-foreground">{r.activated_at ? `ativada em ${fmt(r.activated_at)}` : `criada em ${fmt(r.created_at)}`}</span>
          <Button variant={selectedId === r.id ? 'primary' : 'outline'} onClick={() => onOpen(r.id)}>
            {r.status === 'archived' ? 'Ver / restaurar' : r.status === 'draft' ? 'Editar' : 'Ver'}
          </Button>
        </li>
      ))}
    </ul>
  );
}
