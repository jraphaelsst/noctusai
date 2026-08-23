/**
 * Vista showcase — the "this tab cannot show data" placeholder.
 * Moved out of `pages/VistaShowcase.tsx` (2026-08-22 split).
 *
 * Clientes left this component when its grant landed and the wiring shipped;
 * what remains are the two genuinely blocked tabs. The copy stays specific
 * about WHO is blocking, because "pending" without an owner is what sent
 * people to re-file a Vista ticket that had already been granted.
 */
import { Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { StatusPill } from './shared';

const MESSAGES: Record<string, { title: string; body: string; closing: string; status: string }> = {
  corretores: {
    title: 'Corretores — permissão pendente',
    body: 'O endpoint /corretores/listar existe mas retorna 401 nesta chave. Foi solicitado no mesmo chamado que Clientes (liberado em 21/08/2026) e não foi liberado junto — ou seja, é decisão por método, não propagação pendente.',
    closing: 'Enquanto isso, o roster de corretores já está disponível via /usuarios/listar (Setor: Corretores), no tab Usuários.',
    status: 'permission_denied',
  },
  fotos: {
    title: 'Fotos — não disponível neste tenant',
    body: 'O endpoint /imoveis/fotos retorna 405 (existe, mas é somente-escrita nesta assinatura) — não há leitura de galeria por aqui. Como mitigação, as fotos primárias dos imóveis já vêm em /imoveis/listar e aparecem no tab Imóveis.',
    closing: 'Se uma assinatura mais ampla for adquirida, este tab passa a operar sem alterações de código.',
    status: 'not_found',
  },
};

export function PermissionPlaceholderTab({ tab }: { tab: 'corretores' | 'fotos' }) {
  const m = MESSAGES[tab];
  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-800">
          <Lock className="h-5 w-5" />
          {m.title}
          <StatusPill status={m.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-amber-900 space-y-2">
        <p>{m.body}</p>
        <p className="text-xs text-amber-800/70">{m.closing}</p>
      </CardContent>
    </Card>
  );
}
