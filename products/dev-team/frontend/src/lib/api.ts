/**
 * dev-team API wrappers.
 *
 * Goes through the seed `api` client from `@noctusai/seed/infra` so
 * authentication (Bearer token from supabase session) + 401-retry +
 * envelope handling come for free.
 *
 * All endpoints return `{data: ...}` envelopes — we unwrap here so callers
 * always work with the inner payload.
 */
import { api } from "@noctusai/seed/infra";
import type {
  AgentSnapshot,
  AgentMetrics,
  GlobalMetrics,
  RunTaskRequest,
  RunTaskResponse,
  ConfigSummary,
  FullConfig,
  ConfigPatch,
  ApiEnvelope,
} from "./types";

function unwrap<T>(envelope: ApiEnvelope<T>): T {
  return envelope.data;
}

// ── Agents ─────────────────────────────────────────────────────

export async function listAgents(): Promise<AgentSnapshot[]> {
  const env = await api.get<ApiEnvelope<AgentSnapshot[]>>("/api/agents");
  return unwrap(env);
}

export async function getAgentMetrics(
  name: string,
  scope?: string,
): Promise<AgentMetrics> {
  const env = await api.get<ApiEnvelope<AgentMetrics>>(
    `/api/agents/${encodeURIComponent(name)}/metrics`,
    scope ? { scope } : undefined,
  );
  return unwrap(env);
}

// ── Metrics ────────────────────────────────────────────────────

export async function getGlobalMetrics(scope?: string): Promise<GlobalMetrics> {
  const env = await api.get<ApiEnvelope<GlobalMetrics>>(
    "/api/metrics",
    scope ? { scope } : undefined,
  );
  return unwrap(env);
}

// ── Run ────────────────────────────────────────────────────────

export async function runTask(body: RunTaskRequest): Promise<RunTaskResponse> {
  const env = await api.post<ApiEnvelope<RunTaskResponse>>("/api/run", body);
  return unwrap(env);
}

// ── Configs ────────────────────────────────────────────────────

export async function listConfigs(): Promise<ConfigSummary[]> {
  const env = await api.get<ApiEnvelope<ConfigSummary[]>>("/api/configs");
  return unwrap(env);
}

export async function getConfig(name: string): Promise<FullConfig> {
  const env = await api.get<ApiEnvelope<FullConfig>>(
    `/api/configs/${encodeURIComponent(name)}`,
  );
  return unwrap(env);
}

export async function patchConfig(
  name: string,
  body: ConfigPatch,
): Promise<FullConfig> {
  const env = await api.patch<ApiEnvelope<FullConfig>>(
    `/api/configs/${encodeURIComponent(name)}`,
    body,
  );
  return unwrap(env);
}
