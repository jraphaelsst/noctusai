/**
 * NoctusAI Global Design System
 *
 * Export all shared design system components, hooks, and types.
 *
 * Usage:
 *   import { AppShell, Sidebar, Header, useTheme } from "@noctusai/lib/design-system";
 *   import type { NavGroup, NavItem, HeaderProps, HeaderUser } from "@noctusai/lib/design-system";
 */

export { AppShell } from "./components/AppShell";
export type { AppShellProps } from "./components/AppShell";

export { Sidebar } from "./components/Sidebar";
export type { SidebarProps, NavGroup, NavItem } from "./components/Sidebar";

export { Header } from "./components/Header";
export type { HeaderProps, HeaderUser } from "./components/Header";

export { useTheme } from "./useTheme";
export { useActivityRefresh } from "./useActivityRefresh";
export { InactivityWarning } from "./InactivityWarning";

export { PageSkeleton } from "./components/PageSkeleton";

export { LoginForm } from "./components/LoginForm";
export type { LoginFormProps } from "./components/LoginForm";

export { ForgotPasswordPage } from "./components/ForgotPasswordPage";
export type { ForgotPasswordPageProps } from "./components/ForgotPasswordPage";

export { NotificationBell } from "./components/NotificationBell";
export type { NotificationBellProps, NotificationHooks } from "./components/NotificationBell";

export { PoweredByFooter } from "./components/PoweredByFooter";

export { AcceptInvitePage } from "./components/AcceptInvitePage";
export type { AcceptInvitePageProps } from "./components/AcceptInvitePage";

export { HoverCard, HoverCardTrigger, HoverCardContent } from "./ui/hover-card";

export { LLMProviderSelector } from "./components/LLMProviderSelector";
export type { LLMProviderSelectorProps } from "./components/LLMProviderSelector";

// Gamification primitives — see `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md`.
// Subtle, always tied to real business activity.
export { RankBadge } from "./gamification/RankBadge";
export type { RankBadgeProps } from "./gamification/RankBadge";
export { ScorePill } from "./gamification/ScorePill";
export type { ScorePillProps } from "./gamification/ScorePill";
export { ProgressRing } from "./gamification/ProgressRing";
export type { ProgressRingProps } from "./gamification/ProgressRing";

// AI primitives — Tier 2 Phase 3 (P1 pattern). Backed by `/api/ai/outputs`
// standard router + `<schema>.ai_outputs` per-product table.
export { AIIndicator, useAIOutputFor } from "./ai";
export type { AIIndicatorProps, UseAIOutputForOptions, AIOutput, AIOutputKind } from "./ai";

// AI feedback — ai-expansion Phase 17 (X3 cross-cutting). Backed by
// `/api/ai/feedback` standard router + `<schema>.ai_feedback` per-product table.
export { AIFeedbackButtons, useAIFeedback, useSubmitAIFeedback } from "./ai";
export type { AIFeedbackButtonsProps, AIFeedbackRating } from "./ai";

// AI consent UI — Wave 4 (X6 / LGPD). Backed by `/api/me/consents` (Core).
// Auto-mounted by the seed framework: `<AIConsentToggles/>` lives at
// `/settings/ai`; `<PendingConsentBadge/>` default-fills the layout's
// `aiBadge` slot. Products write zero consent-UI code.
export { AIConsentToggles, PendingConsentBadge, useConsents, useUpdateConsent, CONSENTS_QUERY_KEY } from "./ai";
export type {
  AIConsentTogglesProps,
  PendingConsentBadgeProps,
  ConsentItem,
  ConsentCatalogResponse,
  UpdateConsentInput,
} from "./ai";

// LLM spend badge — Wave 5 (X4 / cost guardrails). Backed by
// `GET /api/admin/llm-spend/{org_id}` (Core, admin-only). Composed with
// `<PendingConsentBadge/>` via `<AIBadgeStack/>` as the seed framework's
// default `aiBadge` fill. Admin-only render; non-admins see nothing.
export {
  AIBadgeStack,
  LLMSpendBadge,
  SpendDetailModal,
  useLLMSpend,
  LLM_SPEND_REFETCH_INTERVAL_MS,
} from "./ai";
export type {
  AIBadgeStackProps,
  LLMSpendBadgeProps,
  SpendDetailModalProps,
  LLMSpendResponse,
  SpendStatus,
} from "./ai";

// Digest container — uniform card for AI-generated digest narratives.
// Each product wraps the card with its own hook + placement; the card
// renders the standard shape (title + prose + feedback buttons).
export { DigestCard, splitProseIntoParagraphs } from "./ai";
export type { DigestCardProps } from "./ai";

// Integration card organ — config-driven card for provider integration accounts.
// Driven by PROVIDER_CARD_CONFIG (youtube + whatsapp shipped); extend the registry
// to add more providers — the card component needs no changes.
export {
  IntegrationCard,
  IntegrationCardModal,
  resolveStatusBadge,
  PROVIDER_CARD_CONFIG,
  getProviderConfig,
} from "./integrations";
export type {
  IntegrationCardProps,
  IntegrationCardModalProps,
  IntegrationAccount,
  IntegrationAccountPatch,
  IntegrationStatus,
  SecondaryField,
  ModalSection,
  ProviderCardConfig,
  EditableField,
} from "./integrations";
