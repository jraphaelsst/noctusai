import { EtapaProcesso } from '@/types/processos';

/**
 * Display config for the 8 Processos de Venda stages.
 *
 * Mirrors the shape of `ETAPAS_CONFIG` in `@/lib/etapasConfig` (the Funil's
 * equivalent) so both boards read the same way — same keys, same semantic
 * token names, no bespoke palette.
 *
 * Colour progresses along the pipeline: neutral while drafting, warning
 * through the review/signature gauntlet, primary once money and deeds move,
 * success at handover and invoice.
 */
export const ETAPAS_PROCESSO_CONFIG: Record<
  EtapaProcesso,
  {
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  elaboracao_contrato: {
    label: 'Elaboração do Contrato',
    color: 'text-secondary-foreground',
    bgColor: 'bg-secondary/10',
    borderColor: 'border-secondary',
  },
  analise_partes: {
    label: 'Análise das Partes',
    color: 'text-secondary-foreground',
    bgColor: 'bg-secondary/10',
    borderColor: 'border-secondary',
  },
  revisao_contrato: {
    label: 'Revisão do Contrato',
    color: 'text-warning-foreground',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning',
  },
  assinatura: {
    label: 'Assinatura',
    color: 'text-warning-foreground',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning',
  },
  financiamento_escritura: {
    label: 'Financiamento & Escritura',
    color: 'text-primary-foreground',
    bgColor: 'bg-primary/10',
    borderColor: 'border-primary',
  },
  finalizacao: {
    label: 'Finalização',
    color: 'text-primary-foreground',
    bgColor: 'bg-primary/10',
    borderColor: 'border-primary',
  },
  entrega_chaves: {
    label: 'Entrega das Chaves',
    color: 'text-success-foreground',
    bgColor: 'bg-success/10',
    borderColor: 'border-success',
  },
  nota_fiscal: {
    label: 'Nota Fiscal',
    color: 'text-success-foreground',
    bgColor: 'bg-success/10',
    borderColor: 'border-success',
  },
};

/**
 * Stage order, derived from the config's key order rather than re-listed.
 * A second hand-maintained list is a drift source; `Object.keys` on a
 * `Record<EtapaProcesso, …>` cannot fall out of step with the type.
 */
export const ETAPAS_PROCESSO_ORDER = Object.keys(
  ETAPAS_PROCESSO_CONFIG,
) as EtapaProcesso[];

/** Terminal stage — nothing follows issuing the invoice; cards archive here. */
export const ETAPA_PROCESSO_FINAL: EtapaProcesso = 'nota_fiscal';
