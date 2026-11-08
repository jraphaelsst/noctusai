/**
 * NoctusAI's own sales funnel -- core's DECLARED context of the seed funnel organ (`@noctusai/lib` `defineFunnel`
 * + `createFunnelHooks`). Face, tabs, actions and data are this literal; board, card dialog, move/lose/refusal
 * flows and the cache writes are the organ's. Nothing here re-implements them.
 *
 * Wire: `/api/admin/funnel` (platform admins only; `projects/noc-funnel/CONTRACT.md`).
 * The card tabs: Contato (editable) · Origem (what the site form sent, read-only) · Oferta (what is being sold,
 * one-off + monthly kept apart) · Histórico (stage history). The card hub (notas, etiquetas, anexos) is not wired
 * yet -- NOC-REMEDIATE[core-funnel-card-hub] on the backend (`app/noc_funnel.py`).
 */
import { defineFunnel } from '@noctusai/lib/components';
import { History, Inbox, Package, Trophy, UserRound } from 'lucide-react';
import { type NocCard } from './hooks';
import { OfertaSection } from './OfertaSection';

export const nocFunnel = defineFunnel<NocCard>({
  id: 'noc',
  entityLabel: 'contato',
  face: {
    subtitle: (c) => c.subtitulo,
  },
  defaultTab: 'contato',
  tabs: [
    {
      id: 'contato',
      label: 'Contato',
      icon: UserRound,
      order: 0,
      section: {
        kind: 'form',
        fields: [
          { key: 'empresa', label: 'Empresa' },
          { key: 'email', label: 'E-mail' },
          { key: 'whatsapp', label: 'WhatsApp' },
          { key: 'proxima_acao', label: 'Próxima ação' },
          { key: 'proxima_acao_em', label: 'Quando', type: 'date' },
        ],
      },
    },
    {
      id: 'origem',
      label: 'Origem',
      icon: Inbox,
      order: 1,
      section: {
        kind: 'fields',
        fields: [
          { key: 'origem', label: 'Origem' },
          { key: 'produtos', label: 'Produtos de interesse' },
          { key: 'mensagem', label: 'Mensagem', type: 'textarea' },
          { key: 'consentimento_marketing', label: 'Aceitou receber novidades' },
        ],
      },
    },
    {
      id: 'oferta',
      label: 'Oferta',
      icon: Package,
      order: 2,
      section: { kind: 'custom', render: ({ card }) => <OfertaSection card={card} /> },
    },
    { id: 'historico', label: 'Histórico', icon: History, order: 3, section: { kind: 'timeline' } },
  ],
  actions: [
    {
      code: 'ganhar',
      label: 'Marcar como ganho',
      icon: Trophy,
      placement: 'header',
      confirm:
        'Marcar este contato como ganho? O link de assinatura do Stripe e os recebíveis do financeiro ainda não são gerados automaticamente.',
    },
  ],
});
