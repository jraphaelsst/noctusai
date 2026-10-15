/** Pure KPI derivations for the Dashboard (unit-tested; no React). */
import { addDays, format, isBefore, startOfDay } from "date-fns";
import type { FunilStage } from "@/hooks/useCrm";
import type { Task } from "@/hooks/useTasks";
import type { AgendaEvent } from "@/hooks/useAgenda";

export function pipelineSummary(funil: FunilStage[]): { openLeads: number; pipelineValue: number } {
  let openLeads = 0;
  let pipelineValue = 0;
  for (const col of funil) {
    for (const lead of col.leads) {
      if (lead.won_at) continue;
      openLeads += 1;
      pipelineValue += lead.value ?? 0;
    }
  }
  return { openLeads, pipelineValue };
}

/** `due_date` is a calendar day (YYYY-MM-DD); overdue = before today, still open. */
export function taskSummary(tasks: Task[], now: Date = new Date()) {
  const today = format(now, "yyyy-MM-dd");
  let todo = 0;
  let doing = 0;
  let overdue = 0;
  for (const t of tasks) {
    if (t.status === "todo") todo += 1;
    else if (t.status === "doing") doing += 1;
    else continue;
    if (t.due_date && t.due_date.slice(0, 10) < today) overdue += 1;
  }
  return { todo, doing, overdue };
}

/** Events starting from the start of today through the next 7 days (local time). */
export function upcomingCount(events: AgendaEvent[], now: Date = new Date()): number {
  const start = startOfDay(now);
  const end = addDays(start, 8);
  return events.filter((e) => {
    const s = new Date(e.starts_at);
    return !isBefore(s, start) && isBefore(s, end);
  }).length;
}

export function agendaWindow(now: Date = new Date()): { from: string; to: string } {
  const start = startOfDay(now);
  return { from: start.toISOString(), to: addDays(start, 8).toISOString() };
}
