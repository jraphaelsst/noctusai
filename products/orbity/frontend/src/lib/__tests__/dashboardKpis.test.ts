import { describe, it, expect } from "vitest";
import { pipelineSummary, taskSummary, upcomingCount } from "../dashboardKpis";
import type { FunilStage, Lead } from "@/hooks/useCrm";
import type { Task } from "@/hooks/useTasks";
import type { AgendaEvent } from "@/hooks/useAgenda";

const lead = (id: string, value: number | null, won = false) =>
  ({ id, value, won_at: won ? "2026-01-01" : null }) as unknown as Lead;
const task = (status: string, due: string | null) => ({ status, due_date: due }) as unknown as Task;
const ev = (d: Date) => ({ starts_at: d.toISOString() }) as unknown as AgendaEvent;

describe("dashboard KPIs", () => {
  it("pipeline counts open leads and sums value, skipping won", () => {
    const funil = [
      { stage: {}, leads: [lead("1", 100), lead("2", null), lead("3", 50, true)] },
      { stage: {}, leads: [lead("4", 25)] },
    ] as unknown as FunilStage[];
    expect(pipelineSummary(funil)).toEqual({ openLeads: 3, pipelineValue: 125 });
  });
  it("tasks: todo/doing/overdue, done+canceled never overdue", () => {
    const now = new Date(2026, 5, 10, 12);
    const s = taskSummary(
      [task("todo", "2026-06-09"), task("doing", "2026-06-10"), task("doing", "2026-06-01"),
       task("done", "2026-05-01"), task("canceled", "2026-05-01"), task("todo", null)],
      now,
    );
    expect(s).toEqual({ todo: 2, doing: 2, overdue: 2 });
  });
  it("upcoming counts today..+7d in local time", () => {
    const now = new Date(2026, 5, 10, 15);
    const n = upcomingCount(
      [ev(new Date(2026, 5, 10, 8)), ev(new Date(2026, 5, 17, 23)), ev(new Date(2026, 5, 18, 9)), ev(new Date(2026, 5, 9, 23))],
      now,
    );
    expect(n).toBe(2);
  });
});
