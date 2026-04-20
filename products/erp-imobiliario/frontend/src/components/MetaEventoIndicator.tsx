/**
 * Contextual Metas indicator — drop on any source entity page (imóvel,
 * evento, contrato, comissão split) to show what the Metas pipeline
 * scored for this entity.
 *
 *   <MetaEventoIndicator refType="ativo" refId={imovel.id} />
 *   <MetaEventoIndicator refType="evento" refId={evento.id} />
 *   <MetaEventoIndicator refType="comissoes_split" refId={split.id} />
 *   <MetaEventoIndicator refType="contrato" refId={contrato.id} />
 *
 * Hides itself when there's nothing to show (entity didn't generate a
 * meta_evento — e.g. an ativo with no captador_id).
 */
import { Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ScorePill } from '@noctusai/lib/design-system';
import { useMetaEventosFor, type MetaEvento } from '@/hooks/useMetasDomain';

function brl(n: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL', maximumFractionDigits: 0,
  }).format(n || 0);
}

const TIPO_LABEL: Record<string, string> = {
  captacao: 'Captação',
  visita: 'Visita',
  venda: 'Venda',
  locacao: 'Locação',
  reuniao: 'Reunião',
};

const MODALIDADE_LABEL: Record<string, string> = {
  padrao: 'Padrão',
  compartilhada: 'Compartilhada',
  exclusividade: 'Exclusividade',
};

export interface MetaEventoIndicatorProps {
  refType: 'ativo' | 'evento' | 'comissoes_split' | 'contrato';
  refId: string | null | undefined;
  className?: string;
}

export function MetaEventoIndicator({ refType, refId, className = '' }: MetaEventoIndicatorProps) {
  const { data: eventos = [], isLoading } = useMetaEventosFor(refType, refId ?? null);

  if (isLoading || !refId) return null;
  if (!eventos.length) return null;

  // Aggregate when multiple eventos share the same reference (e.g. multi-
  // participant visita). Each row is a separate scoring for a different agent.
  const totalPontos = eventos.reduce((acc, e) => acc + (Number(e.pontos) || 0), 0);
  const totalVgv = eventos.reduce((acc, e) => acc + (Number(e.valor_vgv) || 0), 0);

  return (
    <div className={`inline-flex flex-wrap items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm ${className}`}>
      <Sparkles className="h-4 w-4 text-primary" />
      <span className="text-muted-foreground">Metas:</span>
      {eventos.map((e, i) => (
        <EventoChip key={e.id} evento={e} isLast={i === eventos.length - 1} />
      ))}
      {eventos.length > 1 && (
        <>
          <span className="text-muted-foreground">·</span>
          <span className="font-medium">Total: {totalPontos.toFixed(1)} pts</span>
          {totalVgv > 0 && <span className="text-muted-foreground">· {brl(totalVgv)}</span>}
        </>
      )}
    </div>
  );
}

function EventoChip({ evento }: { evento: MetaEvento; isLast: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant="outline" className="gap-1">
        {TIPO_LABEL[evento.evento_tipo] ?? evento.evento_tipo}
        {evento.modalidade !== 'padrao' && (
          <span className="text-xs text-muted-foreground">· {MODALIDADE_LABEL[evento.modalidade] ?? evento.modalidade}</span>
        )}
      </Badge>
      <ScorePill
        value={Number(evento.pontos)}
        suffix=" pts"
        thresholds={{ good: 10, warn: 2 }}
        precision={1}
      />
      {evento.valor_vgv ? (
        <span className="text-xs text-muted-foreground">{brl(Number(evento.valor_vgv))}</span>
      ) : null}
    </span>
  );
}
