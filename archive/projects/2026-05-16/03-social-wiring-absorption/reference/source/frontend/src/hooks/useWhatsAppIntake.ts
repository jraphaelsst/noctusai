/**
 * Binds the seed `createWhatsAppIntakeHooks` factory to this product's
 * authenticated API client. Same one-liner pattern as
 * useWhatsAppConnection.ts — the monitor logic lives in the seed; the
 * product only supplies its `api`.
 */
import { api } from "@noctusai/seed/infra";
import { createWhatsAppIntakeHooks } from "@noctusai/lib";

const hooks = createWhatsAppIntakeHooks(api);

export const useIntakeConversations = hooks.useIntakeConversations;
export const useIntakeConversation = hooks.useIntakeConversation;
export const useCancelConversation = hooks.useCancelConversation;

export type {
  IntakeConversation,
  IntakeMessage,
  IntakeConversationDetail,
} from "@noctusai/lib";
