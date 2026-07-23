// Utilities
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from './utils';

// API client
export { createApiClient, extractErrorMessage, ApiError } from './api';
export type { ApiClient, CreateApiClientOptions } from './api';

// Auth
export { useSupabaseAuthInit, useAuthReady } from './auth';

// SSO
export { resolveSSORoles, resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining } from './sso';
export type { SSORoleInfo, SSOContext, SSOPlanInfo, SSOSubscriptionInfo, SSOLicenseInfo, SSOOrgInfo } from './sso';

// Roles
export { ORG_ROLES, ADMIN_ROLES, MANAGE_TEAM_ROLES, DEV_ROLES, PRODUCT_ADMIN_ROLES, ASSIGNABLE_ROLES, ORG_ROLE_LABELS, isDevOrOwner, canManageTeam, canManageBilling } from './roles';
export type { OrgRole } from './roles';

// Page Status
export { usePageStatus, isPageVisible, filterNavByPageStatus } from './page-status';
export type { StatusPagina, NavItemWithRoute, NavGroupWithRoute } from './page-status';

// Stores
export { createAuthStore, createFiltrosStore } from './stores';
export type { AuthState, BaseFiltrosState } from './stores';

// Hooks
export { createCrudHooks } from './hooks';
export type { CrudHookOptions } from './hooks';

// LLM hooks
export { createLLMHooks, createLLMCredentialsHooks } from './llm';
export type {
  LLMProviderInfo,
  LLMModelInfo,
  LLMPreferences,
  CredentialStatus,
  CredentialsState,
  SetCredentialsBody,
} from './llm';

// WhatsApp connection-admin + intake-monitor hooks
export { createWhatsAppConnectionHooks, createWhatsAppIntakeHooks } from './whatsapp';
export type {
  WhatsAppConnection,
  WhatsAppQr,
  WhatsAppWebhookResult,
  ConfigureWebhookBody,
  IntakeConversation,
  IntakeMessage,
  IntakeConversationDetail,
  IntakeCancelResult,
} from './whatsapp';

// Query client
export { createQueryClient } from './query-client';

// Environment
export { env, validateEnv, generateEnvExample, ENV_VARS } from './env';
export type { ProductEnv } from './env';

// Supabase
export { createProductSupabase, assertSupabaseBuildEnv } from './supabase';

// Components
export { ErrorBoundary, withErrorBoundary, SSOCallback, createAuthProvider, FakeModeBadge } from './components/index';
export type { SSOCallbackProps, FakeModeBadgeProps, FakeModeBadgeVariant } from './components/index';

// Page-visibility admin organ — the WRITE side of the status_pagina system
// (the READ side is `usePageStatus`). Product-agnostic; takes the product's
// own api client. Gate the `enabled` prop to owner/admin/dev.
export { StatusPaginaPanel, STATUS_PAGINAS_QUERY_KEY } from './components/index';
export type {
  StatusPaginaPanelProps,
  StatusPaginaApi,
  StatusPaginaRow,
  StatusPaginaStatus,
} from './components/index';

// Env-mode hook (drives FakeModeBadge; exposed for products that want to
// branch on backend-adapter mode without rendering the badge directly).
export { useEnvMode } from './hooks/useEnvMode';
export type { EnvMode, EnvModeResult, VendorMode } from './hooks/useEnvMode';

// Integration card organ — config-driven card for provider integration accounts.
// YouTube + WhatsApp configs shipped; extend PROVIDER_CARD_CONFIG for more.
// Consuming product wires mutations; the organ is purely presentational.
export {
  IntegrationCard,
  IntegrationCardModal,
  resolveStatusBadge,
  PROVIDER_CARD_CONFIG,
  getProviderConfig,
} from './design-system/integrations';
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
} from './design-system/integrations';
