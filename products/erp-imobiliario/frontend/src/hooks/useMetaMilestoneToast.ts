/**
 * useMetaMilestoneToast — Phase 11 gamification polish.
 *
 * Subscribes to the shared notifications stream via `useNotificacoes` and
 * fires a celebration callback the moment a new `tipo='meta_atingida'`
 * notification arrives. Dedup by notification id in a ref-backed Set so
 * the same milestone never burst twice per session.
 *
 * The backend trigger `trg_meta_milestone` (migration 019) dispatches this
 * notification at 50% / 80% / 100% VGV milestones — highest-only, so the
 * agent sees one burst per crossing, not three.
 */
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useNotificacoes, type Notificacao } from './useNotificacoes';

type Callback = (n: Notificacao) => void;

export function useMetaMilestoneToast(onBurst?: Callback) {
  const q = useNotificacoes(1, 20, false);
  const seen = useRef<Set<string>>(new Set());
  const primed = useRef(false);

  useEffect(() => {
    const rows = q.data?.data ?? [];
    // First render: seed the set with existing notifications so we don't
    // burst for rows the user has seen in previous sessions. From the
    // second render onward, any new meta_atingida with an unseen id fires.
    if (!primed.current) {
      rows.forEach(n => seen.current.add(n.id));
      primed.current = true;
      return;
    }
    for (const n of rows) {
      if (seen.current.has(n.id)) continue;
      seen.current.add(n.id);
      if (n.tipo === 'meta_atingida') {
        toast.success(n.titulo, { description: n.mensagem ?? undefined });
        onBurst?.(n);
      }
    }
  }, [q.data, onBurst]);
}
