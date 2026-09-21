/**
 * Agent Studio — the compiled master prompt (CONTRACT §C, §D1):
 *   GET /api/studio/agents/{key}/versions/{vid}/compiled?client_id=
 *   GET /api/studio/prompts/{hash}
 *
 * §A4: the UI NEVER re-implements composition — it renders the server's
 * `texto` and slices it with the server's `manifest` offsets.
 *
 * Compiling a DRAFT refreshes `agent_versions.compiled_hash` server-side, so a
 * successful compile of a draft whose hash differs from the cached
 * `VersionSummary.compiled_hash` invalidates the agent detail (the publish
 * gate reads that hash).
 */
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AgentDetail, CompiledOut, StoredPrompt } from "@/api/studio/types";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export function useCompiled(key: string, vid: string | null | undefined, clientId: string | null = null) {
  const qc = useQueryClient();
  const q = useQuery<CompiledOut>({
    queryKey: studioKeys.compiled(key, vid ?? "", clientId),
    queryFn: () =>
      api.get<CompiledOut>(`/api/studio/agents/${seg(key)}/versions/${seg(vid as string)}/compiled`, {
        client_id: clientId ?? undefined,
      }),
    enabled: !!key && !!vid,
    placeholderData: keepWithinAgent<CompiledOut>(key),
  });

  const compiled = q.isPlaceholderData ? undefined : q.data;
  useEffect(() => {
    if (!compiled || compiled.client_id) return;
    const detail = qc.getQueryData<AgentDetail>(studioKeys.detail(key));
    const summary = detail?.versoes.find((v) => v.id === compiled.version_id);
    if (summary && summary.status === "rascunho" && summary.compiled_hash !== compiled.hash) {
      void qc.invalidateQueries({ queryKey: studioKeys.detail(key) });
    }
  }, [compiled, key, qc]);

  return toView(q);
}

export function usePromptByHash(hash: string | undefined) {
  const q = useQuery<StoredPrompt>({
    queryKey: studioKeys.prompt(hash ?? ""),
    queryFn: () => api.get<StoredPrompt>(`/api/studio/prompts/${seg(hash as string)}`),
    enabled: !!hash,
    // `prompt_not_found` is final; the stored text is write-once (§A7), so
    // it never goes stale either.
    retry: false,
    staleTime: Infinity,
  });
  return toView(q);
}
