import type { EditorialAction, EditorialState } from './types';

export const STATE_META: Record<EditorialState, { label: string; badgeClass: string }> = {
  rascunho: {
    label: 'Rascunho',
    badgeClass: 'border-slate-400/40 bg-slate-400/10 text-slate-600 dark:text-slate-400',
  },
  revisao_editorial: {
    label: 'Revisão editorial',
    badgeClass: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  },
  revisao_seguranca: {
    label: 'Revisão de segurança',
    badgeClass: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400',
  },
  publicado: {
    label: 'Publicado',
    badgeClass: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400',
  },
  arquivado: {
    label: 'Arquivado',
    badgeClass: 'border-border bg-muted text-muted-foreground',
  },
};

export const ACTION_LABEL: Record<EditorialAction, string> = {
  create: 'criou o rascunho',
  edit: 'editou',
  submit: 'enviou para revisão',
  approve_editorial: 'aprovou na revisão editorial',
  approve_security: 'aprovou na revisão de segurança',
  publish: 'publicou',
  send_back: 'devolveu para rascunho',
  archive: 'arquivou',
};

export function stateLabel(s: string | null | undefined): string {
  return s && s in STATE_META ? STATE_META[s as EditorialState].label : (s ?? '—');
}

export function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}
