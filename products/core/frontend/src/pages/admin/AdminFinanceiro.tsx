/**
 * AdminFinanceiro -- NOC's own books: the seed finance organ (`@noctusai/lib` FinanceRoutedPage) mounted at
 * `/admin/financeiro/*`, on the `/api/finance` API (platform admins only; `CoreLayout` already gates `/admin/*`).
 * `isAdmin` is a UX gate only -- the server enforces every write. Platform IP (access tier platform-admin): a non-admin
 * sees the "sem permissão" card instead of the books (UX only; the API refuses them anyway).
 * Opt-ins of the organ used here: competence cards (revenue by category + result, tax never estimated), the "Origem"
 * column, a first-use empty state and the core-only "Ligações com o financeiro" card (seam `overviewFooter`).
 * NOC-REMEDIATE[core-finance-billing-bridge]: nothing feeds the books yet (billing/licensing -> fin entries) -- 2026-10-14.
 */
import { FinanceRoutedPage } from '@noctusai/lib';
import { Link } from 'react-router-dom';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { FinanceiroLigacoes } from './FinanceiroLigacoes';

const EMPTY_STATE = {
  title: 'O financeiro da NoctusAI ainda está vazio',
  description:
    'Nenhuma conta bancária cadastrada e nenhum lançamento. Comece cadastrando a conta PJ e o Stripe; depois os lançamentos e o saldo aparecem aqui.',
  hint: 'A cobrança das assinaturas (Stripe) ainda não vira lançamento sozinha. Veja “Ligações com o financeiro”.',
};

export function AdminFinanceiro() {
  const { isAdmin } = useAuth();
  if (!isAdmin) {
    return (
      <div className="mx-auto grid max-w-xl justify-items-center gap-2 rounded-lg border p-10 text-center" role="alert">
        <h1 className="text-base font-semibold">Esta área é só para administradores da plataforma</h1>
        <p className="text-sm text-muted-foreground">O financeiro da NoctusAI mostra dados da empresa. Peça acesso a um administrador se precisar.</p>
        <Link to="/" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">Voltar ao início</Link>
      </div>
    );
  }
  return (
    <FinanceRoutedPage
      basePath="/admin/financeiro"
      api={api}
      isAdmin={isAdmin}
      title="Financeiro da plataforma"
      className="space-y-4"
      competenceCards
      showEntryOrigin
      overviewEmptyState={EMPTY_STATE}
      overviewFooter={<FinanceiroLigacoes />}
    />
  );
}
