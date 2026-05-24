/**
 * API surface for Knowledge Extractor.
 *
 * Re-exports the shared `api` client from the seed boundary so product
 * code imports from `@/lib/api` instead of reaching into
 * `@noctusai/seed/infra` directly. Two reasons this layer exists:
 *
 *   1. Test seam — `vi.mock("@/lib/api", ...)` is shorter and more
 *      stable than mocking the seed boundary in every hook test.
 *   2. Domain-call wrappers (below) keep URL strings + payload shapes
 *      in one place — the hooks call the wrapper, not `api.get(url)`.
 *
 * The single-container model means same-origin: `/api/*` already routes
 * to the co-located backend, so the wrappers use bare relative paths.
 *
 * Types mirror the FROZEN backend contract (app/schemas/*). Keep them
 * in lockstep with the backend Pydantic models.
 */
import { api } from "@noctusai/seed/infra";

export { api };

// ─── Catalog ────────────────────────────────────────────────────────────
export interface CatalogModule {
  name: string;
  lessons: number;
  transcripts: number;
  summaries: number;
}

export interface CatalogTotals {
  modules: number;
  lessons: number;
  transcripts: number;
  summaries: number;
}

export interface Catalog {
  modules: CatalogModule[];
  totals: CatalogTotals;
}

export interface ModuleLesson {
  lesson: string;
  has_transcript: boolean;
  has_summary: boolean;
  transcript_chars: number;
  summary_chars: number;
}

export interface ModuleDetail {
  module: string;
  lessons: ModuleLesson[];
}

export interface LessonDetail {
  module: string;
  lesson: string;
  transcript: string | null;
  summary: string | null;
}

// ─── Methodology ──────────────────────────────────────────────────────────
export interface Methodology {
  available: boolean;
  markdown: string | null;
  modules: string[];
}

// ─── KB search ────────────────────────────────────────────────────────────
export interface SearchResult {
  document_id: string;
  module: string | null;
  text: string;
  score: number;
}

export interface SearchResponse {
  query: string;
  configured: boolean;
  results: SearchResult[];
}

// ─── Runs ─────────────────────────────────────────────────────────────────
export type RunStatus = "running" | "done" | "error";
export type RunMode = "drive" | "fake";

export interface Run {
  run_id: string;
  status: RunStatus;
  mode: string;
  started_at: string;
  finished_at: string | null;
  detail: string | null;
}

export interface RunsResponse {
  runs: Run[];
}

export interface CreateRunPayload {
  drive_url?: string | null;
  fake?: boolean;
}

export interface CreateRunResponse {
  accepted: true;
  run_id: string;
  mode: RunMode;
}

// ─── Typed wrappers ───────────────────────────────────────────────────────
// Every wrapper returns the response value; callers never touch raw URLs.

export function getCatalog(): Promise<Catalog> {
  return api.get<Catalog>("/api/catalog");
}

export function getModule(module: string): Promise<ModuleDetail> {
  return api.get<ModuleDetail>(`/api/catalog/modules/${encodeURIComponent(module)}`);
}

export function getLesson(module: string, lesson: string): Promise<LessonDetail> {
  return api.get<LessonDetail>(
    `/api/catalog/lessons/${encodeURIComponent(module)}/${encodeURIComponent(lesson)}`,
  );
}

export function getMethodology(): Promise<Methodology> {
  return api.get<Methodology>("/api/methodology");
}

export function searchKb(q: string, k = 8): Promise<SearchResponse> {
  return api.get<SearchResponse>("/api/kb/search", { q, k });
}

export function listRuns(): Promise<RunsResponse> {
  return api.get<RunsResponse>("/api/runs");
}

export function createRun(payload: CreateRunPayload): Promise<CreateRunResponse> {
  return api.post<CreateRunResponse>("/api/runs", payload);
}
