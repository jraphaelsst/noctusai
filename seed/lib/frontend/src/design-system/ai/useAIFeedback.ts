/**
 * Hooks for the X3 AI feedback widget — ai-expansion Phase 17 (2026-04-25).
 *
 * Backed by the `ai_feedback` standard router (`/api/ai/feedback`) and
 * the per-product `<schema>.ai_feedback` table. Products opt in via
 * `create_product_app(standard_routers=[..., "ai_feedback"])`.
 *
 *   const { data: existing } = useAIFeedback("ai_output:abc");
 *   const submit = useSubmitAIFeedback();
 *   await submit.mutateAsync({ output_ref: "ai_output:abc", rating: 1 });
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';

export type AIFeedbackRating = 1 | -1;

export interface AIFeedbackRow {
  id?: string;
  user_id?: string;
  output_ref: string;
  rating: AIFeedbackRating;
  notes?: string | null;
  prompt_version?: string | null;
  created_at?: string;
}

interface FeedbackResponse {
  data: AIFeedbackRow | null;
}

export function useAIFeedback(
  outputRef: string | null | undefined,
  options: { enabled?: boolean } = {},
) {
  const { enabled = true } = options;
  return useQuery<AIFeedbackRow | null, Error>({
    queryKey: ['ai_feedback', outputRef],
    queryFn: async () => {
      const qs = new URLSearchParams({ output_ref: outputRef! });
      const result = (await api.get(`/api/ai/feedback?${qs}`)) as FeedbackResponse;
      return result?.data ?? null;
    },
    enabled: enabled && !!outputRef,
    staleTime: 60_000,
    retry: false,
  });
}

export interface SubmitFeedbackInput {
  output_ref: string;
  rating: AIFeedbackRating;
  notes?: string;
  prompt_version?: string;
}

export function useSubmitAIFeedback() {
  const qc = useQueryClient();
  return useMutation<AIFeedbackRow, Error, SubmitFeedbackInput>({
    mutationFn: async (input) => {
      const result = (await api.post('/api/ai/feedback', input)) as FeedbackResponse;
      return (result?.data as AIFeedbackRow) ?? { ...input };
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['ai_feedback', vars.output_ref] });
    },
  });
}
