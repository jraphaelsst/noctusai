/**
 * AI design-system primitives — Tier 2 Phase 3 (P1 pattern) + Phase 17 (X3 feedback) + Wave 4 (X6 consent UI).
 */
export { AIIndicator } from './AIIndicator';
export type { AIIndicatorProps } from './AIIndicator';
export { useAIOutputFor } from './useAIOutputFor';
export type { UseAIOutputForOptions } from './useAIOutputFor';
export type { AIOutput, AIOutputKind } from './types';
export { AIFeedbackButtons } from './AIFeedbackButtons';
export type { AIFeedbackButtonsProps } from './AIFeedbackButtons';
export {
  useAIFeedback,
  useSubmitAIFeedback,
} from './useAIFeedback';
export type {
  AIFeedbackRating,
  AIFeedbackRow,
  SubmitFeedbackInput,
} from './useAIFeedback';

// X6 — per-feature AI consent (LGPD). Wave 4 of ai-expansion-followups-rollout.
export { useConsents, CONSENTS_QUERY_KEY } from './useConsents';
export type { ConsentItem, ConsentCatalogResponse } from './useConsents';
export { useUpdateConsent } from './useUpdateConsent';
export type { UpdateConsentInput } from './useUpdateConsent';
export { AIConsentToggles } from './AIConsentToggles';
export type { AIConsentTogglesProps } from './AIConsentToggles';
export { PendingConsentBadge } from './PendingConsentBadge';
export type { PendingConsentBadgeProps } from './PendingConsentBadge';

// X4 — LLM spend badge. Wave 5 of ai-expansion-followups-rollout.
export { useLLMSpend, LLM_SPEND_REFETCH_INTERVAL_MS } from './useLLMSpend';
export type { SpendStatus, LLMSpendResponse } from './useLLMSpend';
export { LLMSpendBadge } from './LLMSpendBadge';
export type { LLMSpendBadgeProps } from './LLMSpendBadge';
export { AIBadgeStack } from './AIBadgeStack';
export type { AIBadgeStackProps } from './AIBadgeStack';
export { SpendDetailModal } from './SpendDetailModal';
export type { SpendDetailModalProps } from './SpendDetailModal';

// Digest container — uniform card shape for AI-generated digest narratives.
// Used by PF monthly narrative, Daily Life weekly review, Mailing campaign
// debrief, Core admin audit digest. Each consumer wraps with its own data
// hook + placement; the card just renders the standard shape.
export { DigestCard, splitProseIntoParagraphs } from './DigestCard';
export type { DigestCardProps } from './DigestCard';
