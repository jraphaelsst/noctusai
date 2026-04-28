/**
 * Daily Life AI hooks — Phase 11 (D6 weekly review) + Phase 13 (D1 today's brief).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface DailyBriefResult {
  chip: string;
  summary: string;
  tasks_today: number;
  events_today: number;
  habits_pending: number;
  yesterday_completed: number;
  prompt_version: string;
}

/**
 * D1 — today's brief. Cached for 15 min so the LayoutEnrichment hook
 * doesn't re-fetch on every page navigation.
 */
export function useDailyBrief(opts: { enabled?: boolean } = {}) {
  return useQuery<DailyBriefResult, Error>({
    queryKey: ["ai_daily_brief"],
    queryFn: async () => {
      const result = await api.get("/api/ai/daily-brief");
      return result.data as DailyBriefResult;
    },
    staleTime: 1000 * 60 * 15,
    retry: false,
    enabled: opts.enabled ?? true,
  });
}

export interface WeeklyReviewSummary {
  tasks_completed: number;
  tasks_pending: number;
  tasks_cancelled: number;
  habit_streaks: Array<[string, number]>;
  notas_count: number;
  focus_minutes: number;
  narrative: string;
  period_label: string;
}

export interface WeeklyReviewResponse {
  subject: string;
  html: string;
  text: string;
  summary: WeeklyReviewSummary;
}

/** D6 — past-week review for the calling user. Used by an in-app dashboard widget. */
export function useWeeklyReview(periodDays = 7) {
  return useQuery<WeeklyReviewResponse, Error>({
    queryKey: ["ai_weekly_review", periodDays],
    queryFn: async () => {
      const result = await api.get(`/api/ai/weekly-review?period_days=${periodDays}`);
      return result.data as WeeklyReviewResponse;
    },
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}
