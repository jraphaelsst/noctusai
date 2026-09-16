/**
 * Configurações do agente — `/api/admin/agent-settings` (platform admin only).
 * Each value comes back with its env `default` and `source` (db | env);
 * sending `null` for a key resets it to the env default.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const AGENT_SETTINGS_KEY = ["agents", "admin", "agent-settings"] as const;

export interface AgentSetting {
  key: string;
  value: number | string;
  default: number | string;
  source: "db" | "env";
  editable: boolean;
  min: number | null;
  max: number | null;
}

interface AgentSettingsResponse {
  items: AgentSetting[];
}

export type AgentSettingsPatch = Partial<{
  approval_timeout_seconds: number | null;
  max_turns: number | null;
  messages_rate_limit: string | null;
}>;

export function useAgentSettings() {
  const query = useQuery<AgentSettingsResponse>({
    queryKey: AGENT_SETTINGS_KEY,
    queryFn: () => api.get<AgentSettingsResponse>("/api/admin/agent-settings"),
    retry: false,
  });

  return {
    data: query.data?.items,
    error: query.error,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}

export function useUpdateAgentSettings() {
  const qc = useQueryClient();
  return useMutation<AgentSettingsResponse, unknown, AgentSettingsPatch>({
    mutationFn: (patch) => api.put<AgentSettingsResponse>("/api/admin/agent-settings", patch),
    onSuccess: (data) => qc.setQueryData(AGENT_SETTINGS_KEY, data),
  });
}
