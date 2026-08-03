/**
 * Chat organ — provider-agnostic 2-pane chat window.
 *
 * Usage:
 *   import { ChatWindow } from "@noctusai/lib/design-system";
 *   import type { ChatWindowAdapter, ChatThread, ChatMessage } from "@noctusai/lib/design-system";
 */
export { ChatWindow } from "./ChatWindow";
export type {
  ChatWindowProps,
  ChatWindowAdapter,
  ChatThread,
  ChatMessage,
  ChatSendResult,
  ChatAutoReplyResult,
  ChatReadStateResult,
  ChatLoadMoreResult,
} from "./ChatWindow";
