/**
 * NoctusAI Global Design System
 *
 * Export all shared design system components, hooks, and types.
 *
 * Usage:
 *   import { AppShell, Sidebar, Header, useTheme } from "@noctusai/lib/design-system";
 *   import type { NavGroup, NavItem, HeaderProps, HeaderUser } from "@noctusai/lib/design-system";
 */

export { AppShell, useSidebarRail } from "./components/AppShell";
export type { AppShellProps, SidebarRailMode, SidebarRailState } from "./components/AppShell";

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

// UI primitives — generic, token-aligned building blocks.
// Badge / Button / Dialog / Input are consumed by integration organs and
// available to all products that import from `@noctusai/lib/design-system`.
export { Badge } from "./ui/Badge";
export type { BadgeProps, BadgeVariant } from "./ui/Badge";

export { Button } from "./ui/Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./ui/Button";

export { Dialog, DialogHeader, DialogBody, DialogFooter } from "./ui/Dialog";
export type {
  DialogProps,
  DialogHeaderProps,
  DialogBodyProps,
  DialogFooterProps,
} from "./ui/Dialog";

export { Input } from "./ui/Input";
export type { InputProps } from "./ui/Input";

export { HoverCard, HoverCardTrigger, HoverCardContent } from "./ui/hover-card";

// Skeleton / TableSkeleton — canonical loading-placeholder primitives (seed-skeleton-organs
// slice). Formalizes the animate-pulse bg-muted block hand-rolled across ChartCard,
// PageSkeleton, KanbanBoard, IntegrationCard, ClientCredentialPanel, ChatWindow (N>=5).
export { Skeleton } from "./ui/Skeleton";
export type { SkeletonProps, SkeletonRounded } from "./ui/Skeleton";
export { TableSkeleton } from "./ui/TableSkeleton";
export type { TableSkeletonProps } from "./ui/TableSkeleton";

// Form/layout primitives — Card / Textarea / Select / Field / FormError /
// EmptyState / ErrorState. Promoted from two near-verbatim product-local
// copies (academia-de-reciclagem + agents studio, DRY N=2 triage).
export { Card, Textarea, Select, Field, FormError, EmptyState, ErrorState } from "./ui/FormControls";
export type { CardProps, TextareaProps, SelectProps } from "./ui/FormControls";

// Card-hub primitives — Radix-backed, SW shadcn-copy parity (markup/classes/
// data-attributes kept byte-for-byte so `social-wiring`'s card hub can swap
// onto these imports with zero visual change at desktop). See
// `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` Slice B.
// `Textarea`/`Select` already exist above (native HTML shapes, different
// API) — the Radix-shape siblings here are re-exported under the
// `CardHub*` prefix to avoid the name collision.
export { Popover, PopoverTrigger, PopoverAnchor, PopoverContent } from "./ui/popover";

export { Checkbox } from "./ui/checkbox";

export { Switch } from "./ui/switch";

export { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";

export { ScrollArea, ScrollBar } from "./ui/scroll-area";

export { Progress } from "./ui/progress";

export { Textarea as CardHubTextarea } from "./ui/textarea";

export {
  Select as CardHubSelect,
  SelectGroup as CardHubSelectGroup,
  SelectValue as CardHubSelectValue,
  SelectTrigger as CardHubSelectTrigger,
  SelectContent as CardHubSelectContent,
  SelectLabel as CardHubSelectLabel,
  SelectItem as CardHubSelectItem,
  SelectSeparator as CardHubSelectSeparator,
  SelectScrollUpButton as CardHubSelectScrollUpButton,
  SelectScrollDownButton as CardHubSelectScrollDownButton,
} from "./ui/select";

// Card-hub Slice C additions — same SW-parity rationale as the block above.
export { CardHubButton, cardHubButtonVariants } from "./ui/card-hub-button";
export type { CardHubButtonProps, CardHubButtonVariant, CardHubButtonSize } from "./ui/card-hub-button";

export { CardHubInput } from "./ui/card-hub-input";

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "./ui/tooltip";

export {
  Dialog as CardHubDialogRoot,
  DialogPortal as CardHubDialogPortal,
  DialogOverlay as CardHubDialogOverlay,
  DialogClose as CardHubDialogClose,
  DialogTrigger as CardHubDialogTrigger,
  DialogContent as CardHubDialogContent,
  DialogHeader as CardHubDialogHeader,
  DialogFooter as CardHubDialogFooter,
  DialogTitle as CardHubDialogTitle,
  DialogDescription as CardHubDialogDescription,
} from "./ui/radix-dialog";

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
// ClientCredentialPanel composes IntegrationCard with a per-client tab selector
// and CRUD affordances — the reusable per-client credential management organ.
export {
  IntegrationCard,
  IntegrationCardModal,
  ClientCredentialPanel,
  resolveStatusBadge,
  PROVIDER_CARD_CONFIG,
  getProviderConfig,
} from "./integrations";
export type {
  IntegrationCardProps,
  IntegrationCardModalProps,
  ClientCredentialPanelProps,
  ClientRef,
  IntegrationAccount,
  IntegrationAccountPatch,
  IntegrationStatus,
  SecondaryField,
  ModalSection,
  ProviderCardConfig,
  EditableField,
} from "./integrations";

// Social dashboard shell organ — the shared container/header/network-toggle/
// Radix-Tabs spine every social-account dashboard page (YouTube, Meta, ...)
// otherwise hand-rolls. See KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend/frontend.md.
export { SocialDashboardShell } from "./dashboard/SocialDashboardShell";
export type {
  SocialDashboardShellProps,
  SocialDashboardNetwork,
  SocialDashboardSubtab,
} from "./dashboard/SocialDashboardShell";

// Chat organ — provider-agnostic 2-pane chat window (thread list + thread
// panel + composer), driven by an `adapter` hooks bag (WhatsApp + Instagram
// DMs are the first two consumers; see `KB § PATTERNS/frontend/frontend.md`).
export { ChatWindow } from "./chat";
export type {
  ChatWindowProps,
  ChatWindowAdapter,
  ChatThread,
  ChatMessage,
  ChatBlock,
  ChatSendResult,
  ChatAutoReplyResult,
  ChatReadStateResult,
  ChatLoadMoreResult,
  ChatApprovalActionResult,
  ChatRenameThreadResult,
} from "./chat";

// Chart / KPI / filter organs — seed-canonical (N=3 recurrence rule, see
// leads-module-PROJECT.md §7/§8). Leads is the first consumer; migrating the
// 3 pre-existing hand-rolled sets (social-wiring/personal-finance/erp-imobiliario)
// is a separate, pilot-products-first slice — not part of this build.
export {
  ChartCard,
  LineChart,
  AreaChart,
  BarChart,
  DonutChart,
  Heatmap,
  StatTile,
  StatTileRow,
  FilterBar,
  useChartTheme,
  CHART_PALETTE_SIZE,
  CHART_COLOR_VAR_NAMES,
  CHART_PALETTE_FALLBACK,
  resolveSeriesColor,
  heatmapStep,
  buildSequentialScale,
  formatCompactNumber,
  formatPercent,
  formatPercentDelta,
  PT_BR_MONTH_LABELS_SHORT,
} from "./charts";
export type {
  ChartCardProps,
  ChartTheme,
  ChartDatum,
  ChartSeries,
  CartesianChartProps,
  LineChartProps,
  AreaChartProps,
  BarChartProps,
  DonutChartProps,
  HeatmapProps,
  StatTileTrend,
  StatTileProps,
  StatTileRowProps,
  FilterChip,
  FilterBarProps,
} from "./charts";
