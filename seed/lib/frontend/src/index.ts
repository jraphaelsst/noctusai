// Utilities
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from './utils';

// API client
export { createApiClient, extractErrorMessage } from './api';
export type { ApiClient, CreateApiClientOptions } from './api';

// Auth
export { useSupabaseAuthInit } from './auth';

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

// Query client
export { createQueryClient } from './query-client';

// Environment
export { env, validateEnv, generateEnvExample, ENV_VARS } from './env';
export type { ProductEnv } from './env';

// Supabase
export { createProductSupabase } from './supabase';

// Components
export { ErrorBoundary, withErrorBoundary, SSOCallback, createAuthProvider, FakeModeBadge } from './components/index';
export type { SSOCallbackProps, FakeModeBadgeProps, FakeModeBadgeVariant } from './components/index';

// Env-mode hook (drives FakeModeBadge; exposed for products that want to
// branch on backend-adapter mode without rendering the badge directly).
export { useEnvMode } from './hooks/useEnvMode';
export type { EnvMode, EnvModeResult, VendorMode } from './hooks/useEnvMode';
