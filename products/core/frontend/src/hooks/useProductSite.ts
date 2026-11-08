/**
 * useProductSite — the ONE mechanism behind the public-site controls of a
 * catalog product (`exibir_no_site`, `destaque_no_site`, `descricao_publica`)
 * on `/admin/products`.
 *
 * Cache-write contract (skill noc-cache-writes): every PATCH answer is the
 * server's row, and it is written straight into the page's list (`mergeRow`),
 * so the screen agrees with the server after each step without a re-fetch.
 * When a multi-step change (swap / compact) fails midway, `settle()` re-reads
 * the list so the screen shows what the server actually holds.
 *
 * A refusal is never silent: the server's pt-BR `detail` (6 featured max,
 * hidden product, empty public description, 409 race) lands in `error`,
 * rendered inline by the page next to the control that caused it.
 *
 * Featured positions are kept contiguous (1..n): removing one moves the rest
 * up, adding appends at n+1. Positions are unique server-side and nothing is
 * ever swapped automatically — a 7th is refused.
 */
import { useCallback, useState } from 'react';
import { api } from '../lib/api';

export const MAX_DESTAQUES = 6;
export const REFUSAL_FULL = 'Já há 6 destaques. Remova um antes de adicionar outro.';

export interface SiteProduct {
  id: string;
  nome: string;
  exibir_no_site?: boolean | null;
  destaque_no_site?: number | null;
  descricao_publica?: string | null;
}

export interface SiteError {
  /** product the message belongs to (null = panel-level) */
  id: string | null;
  message: string;
}

/** Featured products in display order. */
export function featuredOf<T extends SiteProduct>(products: T[]): T[] {
  return products
    .filter(p => p.destaque_no_site != null)
    .sort((a, b) => (a.destaque_no_site as number) - (b.destaque_no_site as number));
}

export function useProductSite<T extends SiteProduct>(
  products: T[],
  setProducts: (updater: (prev: T[]) => T[]) => void,
  refetch: () => Promise<void>,
) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<SiteError | null>(null);
  const [status, setStatus] = useState('');

  const mergeRow = useCallback(
    (row: Partial<T> & { id: string }) =>
      setProducts(prev => prev.map(p => (p.id === row.id ? { ...p, ...row } : p))),
    [setProducts],
  );

  async function patch(id: string, body: Record<string, unknown>): Promise<T> {
    const res = await api.patch(`/api/products/${id}`, body);
    mergeRow(res.data);
    return res.data as T;
  }

  /** Run a (possibly multi-step) change; on failure show the server's detail and re-sync. */
  async function run(id: string, okMessage: string, steps: () => Promise<void>): Promise<boolean> {
    setBusyId(id);
    setError(null);
    try {
      await steps();
      setStatus(okMessage);
      return true;
    } catch (err: any) {
      setError({ id, message: err?.message || 'Não foi possível salvar. Nada mudou no site. Tente de novo.' });
      await refetch();
      return false;
    } finally {
      setBusyId(null);
    }
  }

  /** Re-number the remaining featured products 1..n after `skipId` left the set. */
  async function compact(skipId: string) {
    const rest = featuredOf(products.filter(p => p.id !== skipId));
    for (let i = 0; i < rest.length; i++) {
      if (rest[i].destaque_no_site !== i + 1) await patch(rest[i].id, { destaque_no_site: i + 1 });
    }
  }

  async function feature(p: T) {
    const n = featuredOf([...products]).length;
    if (n >= MAX_DESTAQUES) {
      setError({ id: p.id, message: REFUSAL_FULL });
      setStatus(REFUSAL_FULL);
      return false;
    }
    return run(p.id, `${p.nome} agora é o destaque nº ${n + 1}.`, async () => {
      await patch(p.id, { destaque_no_site: n + 1 });
    });
  }

  async function unfeature(p: T) {
    const total = featuredOf([...products]).length;
    return run(p.id, `${p.nome} saiu dos destaques. ${total - 1} de ${MAX_DESTAQUES}.`, async () => {
      await patch(p.id, { destaque_no_site: null });
      await compact(p.id);
    });
  }

  /** Move one step up (-1) or down (+1). Positions are unique, so a swap goes through null. */
  async function move(p: T, dir: -1 | 1) {
    const list = featuredOf([...products]);
    const i = list.findIndex(x => x.id === p.id);
    const other = list[i + dir];
    if (i < 0 || !other) return false;
    const a = p.destaque_no_site as number;
    const b = other.destaque_no_site as number;
    return run(p.id, `${p.nome} agora é o destaque nº ${b}.`, async () => {
      await patch(p.id, { destaque_no_site: null });
      await patch(other.id, { destaque_no_site: a });
      await patch(p.id, { destaque_no_site: b });
    });
  }

  /** Show/hide on the site. Hiding a featured product also un-features it (caller confirms first). */
  async function setExibir(p: T, on: boolean) {
    return run(
      p.id,
      on ? `${p.nome} agora aparece no site.` : `${p.nome} não aparece mais no site.`,
      async () => {
        if (!on && p.destaque_no_site != null) {
          await patch(p.id, { destaque_no_site: null });
          await compact(p.id);
        }
        await patch(p.id, { exibir_no_site: on });
      },
    );
  }

  return { busyId, error, status, setError, feature, unfeature, move, setExibir };
}
