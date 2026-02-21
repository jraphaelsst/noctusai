import { EtapaFunil } from '@/types/clientes';

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
