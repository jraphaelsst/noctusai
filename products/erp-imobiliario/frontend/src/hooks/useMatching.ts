/**
 * @deprecated This file is deprecated. Use useMatches.ts for server-side matching.
 * 
 * The matching algorithm has been moved to the Supabase Edge Function `gerar-matches`.
 * Match results are now persisted in the `matches` table in the database.
 * 
 * Use:
 * - `useMatches()` to read persisted matches
 * - `useRecalcularMatches()` to trigger recalculation
 * - `useAtualizarStatusMatch()` to accept/reject matches
 * 
 * This file re-exports from useMatches.ts for backward compatibility.
 */

export { useRecalcularMatches as useGerarMatches } from './useMatches';
