/**
 * The ONE mechanism behind the product working-guide toggles (Status +
 * Deploy scope) — consumed by BOTH surfaces that render them (`/admin/products`
 * and the core dashboard cards). Before this hook existed the two pages each
 * hand-rolled their own busy-state + mutate + error-handling, and they had
 * already drifted (dashboard used a sonner toast on failure, admin used a
 * blocking `alert()`). One hook, one behaviour, two consumers.
 *
 * The server stays the authority: this hook never guesses the resulting
 * state locally. On success it hands the id back to the caller's own
 * `onChanged`, which re-reads from the server (admin re-reads the row +
 * table, the dashboard re-reads `/api/auth/me`) — a deactivation also
 * demotes the scope server-side, so an optimistic local echo would show a
 * combination the backend never actually persisted.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { api } from '../lib/api';
import type { DeployScope } from '../components/ProductStateControls';

/** Minimal shape the hook needs — both pages' richer Product types satisfy
 *  this structurally. */
export interface ProductStateActionsTarget {
  id: string;
}

export function useProductStateActions(onChanged: (id: string) => void | Promise<void>) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function run(id: string, call: () => Promise<unknown>): Promise<boolean> {
    setBusyId(id);
    try {
      await call();
      await onChanged(id);
      return true;
    } catch (err: any) {
      // Sonner, never a blocking native alert() — a failed toggle must not
      // stall the rest of the page.
      toast.error(err?.message || 'Falha ao atualizar o produto');
      return false;
    } finally {
      setBusyId(null);
    }
  }

  async function setActivation(product: ProductStateActionsTarget, ativo: boolean) {
    const ok = await run(product.id, () =>
      api.post(`/api/products/${product.id}/activation`, { ativo }),
    );
    if (ok) {
      // Gate scope (CI/checks) is driven off the same catalog row via a
      // periodic sync (`deploy/fleet/active-scope.txt`), not this request —
      // say so, so nobody expects the gates to move instantly.
      toast.success(
        ativo
          ? 'Produto ativado — volta aos gates em ~1 min'
          : 'Produto desativado — sai dos gates em ~1 min',
      );
    }
  }

  async function setDeployScope(product: ProductStateActionsTarget, deploy_scope: DeployScope) {
    const ok = await run(product.id, () =>
      api.post(`/api/products/${product.id}/deploy-scope`, { deploy_scope }),
    );
    if (ok) toast.success('Escopo de trabalho salvo');
  }

  return { busyId, setActivation, setDeployScope };
}
