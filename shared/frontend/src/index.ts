// Utilities
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from './utils';

// API client
export { createApiClient, extractErrorMessage } from './api';
export type { ApiClient, CreateApiClientOptions } from './api';

// Auth
export { useSupabaseAuthInit } from './auth';

// Stores
export { createAuthStore, createFiltrosStore } from './stores';
export type { AuthState, BaseFiltrosState } from './stores';

// Hooks
export { createCrudHooks } from './hooks';
export type { CrudHookOptions } from './hooks';

// Query client
export { createQueryClient } from './query-client';

// Components
export { ErrorBoundary, withErrorBoundary, SSOCallback } from './components/index';
export type { SSOCallbackProps } from './components/index';
