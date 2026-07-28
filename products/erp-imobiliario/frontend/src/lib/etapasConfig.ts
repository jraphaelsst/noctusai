import { EtapaFunil } from '@/types/clientes';

/**
 * LEGACY display map for `erp.clientes.etapa_atual`.
 *
 * NOT the funnel's stage vocabulary any more. Since migration 042 the Funil and
 * Processos boards read per-organization stage ROWS the user edits, and both
 * get their labels and colours from `pipeline_stages` via
 * `@noctusai/lib/components`'s `stageColorClasses`.
 *
 * This map survives for exactly one reason: `erp.clientes.etapa_atual` is a
 * retained legacy enum column (roadmap Q8's removal target) and `pages/Clientes.tsx`
 * still renders it. When Q8 lands and that column goes, this map goes with it.
 *
 * Do NOT reach for this when building anything on a board — it cannot see a
 * stage the user created, so it would silently render nothing for it.
 */

export const ETAPAS_CONFIG: Record<
  EtapaFunil,
  {
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  qualificacao: {
    label: 'Qualificação',
    color: 'text-secondary-foreground',
    bgColor: 'bg-secondary/10',
    borderColor: 'border-secondary',
  },
  visitas: {
    label: 'Visitas',
    color: 'text-warning-foreground',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning',
  },
  proposta: {
    label: 'Proposta',
    color: 'text-primary-foreground',
    bgColor: 'bg-primary/10',
    borderColor: 'border-primary',
  },
  negociacao: {
    label: 'Negociação',
    color: 'text-muted-foreground',
    bgColor: 'bg-muted/50',
    borderColor: 'border-muted',
  },
  fechado: {
    label: 'Fechado',
    color: 'text-success-foreground',
    bgColor: 'bg-success/10',
    borderColor: 'border-success',
  },
};

export const TIPOS_ATIVIDADE = [
  { value: 'ligacao', label: 'Ligação' },
  { value: 'email', label: 'E-mail' },
  { value: 'reuniao', label: 'Reunião' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'visita', label: 'Visita' },
  { value: 'proposta', label: 'Proposta' },
  { value: 'negociacao', label: 'Negociação' },
  { value: 'outro', label: 'Outro' },
];
