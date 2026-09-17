/**
 * WhatsApp connections — multi-line WAHA connection management.
 *
 * Usage:
 *   import { createWhatsAppConnectionsHooks, WhatsAppConnectionsPage } from "@noctusai/lib/components";
 */
export {
  createWhatsAppConnectionsHooks,
} from '../../whatsapp';
export type {
  CreateWhatsAppConnectionsHooksOptions,
  WhatsAppConnectionsHooks,
  WhatsAppConnectionLine,
  CreateWhatsAppConnectionBody,
  UpdateWhatsAppConnectionBody,
  WhatsAppConnectionStatus,
  WhatsAppConnectionQr,
  WhatsAppConnectionRecoverResult,
  ConfigureWhatsAppConnectionWebhookBody,
  WhatsAppConnectionWebhookResult,
} from '../../whatsapp';

export { WhatsAppConnectionsPage } from './WhatsAppConnectionsPage';
export type { WhatsAppConnectionsPageProps } from './WhatsAppConnectionsPage';

export { CreateConnectionDialog } from './CreateConnectionDialog';
export type { CreateConnectionDialogProps } from './CreateConnectionDialog';

export { ConnectionDetailDialog } from './ConnectionDetailDialog';
export type { ConnectionDetailDialogProps } from './ConnectionDetailDialog';
