/**
 * D1 today's brief badge — mounted via `LayoutEnrichment.aiBadge` (P4
 * pattern from ai-expansion §5a / Tier 2 Phase 5). Shipped as part of
 * ai-expansion Phase 13 (2026-04-25).
 *
 * Renders a compact chip in the framework header band; clicking the
 * chip toggles a small panel with the longer summary + per-bucket
 * counts. Auto-hides while loading and on the dry-run / unconfigured
 * path (the hook returns `error`/`undefined` and we render nothing).
 */
import { useState } from "react";
import { useDailyBrief } from "@/hooks/useAI";
import { AIFeedbackButtons } from "@noctusai/lib/design-system";
import { Sparkles } from "lucide-react";

export function DailyBriefBadge() {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError } = useDailyBrief();

  if (isLoading || isError || !data) return null;

  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={data.summary}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 10px",
          fontSize: 12,
          fontWeight: 500,
          color: "var(--foreground, #222)",
          background: "var(--muted, rgba(0,0,0,0.06))",
          border: "1px solid var(--border, rgba(0,0,0,0.1))",
          borderRadius: 999,
          cursor: "pointer",
          lineHeight: 1.2,
        }}
      >
        <Sparkles size={12} />
        <span>{data.chip}</span>
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            zIndex: 50,
            width: 280,
            padding: 12,
            background: "var(--popover, white)",
            color: "var(--popover-foreground, #222)",
            border: "1px solid var(--border, rgba(0,0,0,0.1))",
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            fontSize: 13,
            lineHeight: 1.4,
          }}
          role="dialog"
          aria-label="Resumo do dia"
        >
          <p style={{ margin: 0, marginBottom: 8 }}>{data.summary}</p>
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: "none",
              fontSize: 12,
              color: "var(--muted-foreground, #555)",
            }}
          >
            <li>Tarefas hoje: {data.tasks_today}</li>
            <li>Hábitos pendentes: {data.habits_pending}</li>
            <li>Eventos hoje: {data.events_today}</li>
            <li>Concluído ontem: {data.yesterday_completed}</li>
          </ul>
          <div
            style={{
              marginTop: 10,
              paddingTop: 8,
              borderTop: "1px solid var(--border, rgba(0,0,0,0.08))",
              display: "flex",
              justifyContent: "flex-end",
            }}
          >
            <AIFeedbackButtons
              output_ref={`digest:dl-daily-brief:${new Date()
                .toISOString()
                .slice(0, 10)}`}
              size="sm"
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default DailyBriefBadge;
