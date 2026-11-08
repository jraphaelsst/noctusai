/**
 * Admin > Comercial > Funil -- NoctusAI's own sales funnel: every contact from the site (waitlist, briefing,
 * contact form, signup intent) as a card, from "Novo" to won or lost.
 *
 * This page only DECLARES core's context of the seed funnel organ (`./funil/funnel.tsx`) and mounts the organ's
 * `FunnelBoard`; board, card dialog, gate refusals, lost-reason flow and cache writes are the organ's.
 * Platform admins only: `CoreLayout` gates `/admin/*` for the UI, the API (`/api/admin/funnel`) enforces it.
 */
import * as React from 'react';
import { parseFunnelError, FunnelBoard } from '@noctusai/lib/components';
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Input } from '@noctusai/lib/design-system';
import { useAuth } from '../../lib/auth-context';
import { nocFunnel } from './funil/funnel';
import { nocFunnelHooks } from './funil/hooks';

function NovoContatoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = nocFunnelHooks.useCreateCard();
  const [nome, setNome] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  function fechar() {
    setNome('');
    setError(null);
    onClose();
  }

  function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim()) {
      setError('Informe o nome do contato.');
      return;
    }
    setError(null);
    create.mutate(
      { titulo: nome.trim() },
      { onSuccess: fechar, onError: (err) => setError(parseFunnelError(err).mensagem) },
    );
  }

  return (
    <Dialog open={open} onClose={fechar} title="Novo contato">
      <form onSubmit={criar}>
        <DialogHeader>
          <h2 className="text-lg font-semibold">Novo contato</h2>
        </DialogHeader>
        <DialogBody>
          <label htmlFor="novo-contato-nome" className="text-sm font-medium">
            Nome
          </label>
          <Input id="novo-contato-nome" value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />
          <p className="mt-2 text-sm text-muted-foreground">
            Entra na primeira etapa. Complete o contato e a oferta no cartão.
          </p>
          {error && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={fechar}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? 'Criando…' : 'Criar contato'}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

export function AdminFunil() {
  const { isAdmin } = useAuth();
  const [busca, setBusca] = React.useState('');
  const [termo, setTermo] = React.useState('');
  const [novo, setNovo] = React.useState(false);

  // The search is server-side; wait for a pause in typing instead of querying on every keystroke.
  React.useEffect(() => {
    const t = setTimeout(() => setTermo(busca.trim()), 300);
    return () => clearTimeout(t);
  }, [busca]);

  const filtros = React.useMemo(() => (termo ? { busca: termo } : {}), [termo]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Funil</h1>
          <p className="text-sm text-muted-foreground">
            Cada contato do site, da primeira mensagem até fechar (ou registrar por que não fechou).
          </p>
        </div>
        {isAdmin && (
          <Button variant="primary" onClick={() => setNovo(true)}>
            Novo contato
          </Button>
        )}
      </header>

      <div>
        <label htmlFor="funil-busca" className="sr-only">
          Buscar contato
        </label>
        <Input
          id="funil-busca"
          type="search"
          placeholder="Buscar por nome, empresa, e-mail…"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className="max-w-md"
        />
      </div>

      <FunnelBoard
        funnel={nocFunnel}
        hooks={nocFunnelHooks}
        filtros={filtros}
        canEdit={isAdmin}
        canEditStages={isAdmin}
        emptyColumnLabel="Nenhum contato nesta etapa"
      />

      <NovoContatoDialog open={novo} onClose={() => setNovo(false)} />
    </div>
  );
}
