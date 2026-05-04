/**
 * Type definitions matching the backend response shapes from
 * `products/dev-team/backend/app/api/`. Updated 2026-05-04 to match the
 * actual rollup shape from `dev_team/telemetry/rollups.py` (engineer C/G).
 *
 * Every endpoint wraps its payload with `success_response(data)` →
 * `{ data: <payload> }` per `noctusai_lib.primitives.responses`.
 */

/** GET /api/agents row — one card in the agents grid. */
export interface AgentSnapshot {
  name: string;
  model: string;
  last_24h_events: number;
  last_24h_cost: number;
  /** 0..1 success ratio (backend may return null for empty scopes; we coerce to 0). */
  success_rate: number;
}

/**
 * GET /api/agents/{name}/metrics — per-agent rollup.
 *
 * NOTE on `recent_events`: the brief listed it but the engine's rollup
 * (`dev_team/telemetry/rollups.py::get_agent_metrics`) does NOT currently
 * return a `recent_events` array. Frontend treats it as optional and falls
 * back to an empty list. Logged in findings.md as a gap to track.
 */
export interface AgentMetrics {
  agent: string;
  scope: string | null;
  events: number;
  total_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number | null;
  success_rate: number | null;
  tool_call_distribution: Record<string, number>;
  /** Optional — not yet populated by the engine; see types.ts header. */
  recent_events?: RecentEvent[];
}

/** One row in the recent-events table. */
export interface RecentEvent {
  ts: string;
  agent_name: string;
  outcome: "ok" | "error" | string;
  latency_ms: number | null;
  total_cost_usd: number | null;
  task: string | null;
}

/** GET /api/metrics global rollup. */
export interface GlobalMetrics {
  scope: string | null;
  total_events: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  agents: Record<string, {
    events: number;
    cost: number;
    input_tokens: number;
    output_tokens: number;
    avg_latency_ms: number | null;
    success_rate: number | null;
  }>;
}

/** POST /api/run request body. */
export interface RunTaskRequest {
  task: string;
  project?: string;
  config?: string;
}

/** POST /api/run response envelope (3 discriminated shapes). */
export interface RunTaskResponse {
  status: "ok" | "switch-not-flipped" | "dry-run" | string;
  summary: string;
  task?: string;
  project?: string;
  config?: string;
  members?: string[];
  [key: string]: unknown;
}

/** GET /api/configs row. */
export interface ConfigSummary {
  name: string;
  agent_count: number;
  error?: string;
}

/** GET /api/configs/{name} — full config dict. Loose because YAML is open-shape. */
export interface FullConfig {
  agents?: Record<string, { model?: string; provider?: string; [k: string]: unknown }>;
  [k: string]: unknown;
}

/** PATCH /api/configs/{name} request body. */
export interface ConfigPatch {
  agent_name: string;
  model?: string;
  provider?: string;
}

/** Standard response envelope from `success_response(data)`. */
export interface ApiEnvelope<T> {
  data: T;
  total?: number;
}

/** Time-series point for the per-agent metrics chart. */
export interface MetricPoint {
  date: string;
  cost: number;
  latency: number;
  events: number;
  successRate: number;
}
