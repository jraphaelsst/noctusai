/**
 * WhatsApp inbox - read + reply on top of the seed connections organ.
 *
 * Usage:
 *   import { createWhatsAppInboxHooks, WhatsAppInbox } from "@noctusai/lib/components";
 *   const hooks = createWhatsAppInboxHooks(api, { getAuthToken });
 *   <WhatsAppInbox hooks={hooks} connectionId={id} initialChatId={chatFromQuery} />
 */
export { createWhatsAppInboxHooks, inboxCacheOps } from '../../whatsapp-inbox';
export type {
  CreateWhatsAppInboxHooksOptions,
  WhatsAppInboxHooks,
  InboxChat,
  InboxMessage,
  InboxChatsPage,
  InboxMessagesPage,
} from '../../whatsapp-inbox';

export { WhatsAppInbox } from './WhatsAppInbox';
export type { WhatsAppInboxProps } from './WhatsAppInbox';
