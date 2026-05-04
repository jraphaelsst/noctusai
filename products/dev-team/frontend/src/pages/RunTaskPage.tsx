/**
 * Run Task page — textarea + project + config + submit.
 *
 * Fires `POST /api/run`; the engine returns one of three discriminated
 * envelopes: ok / switch-not-flipped / dry-run. We render all three.
 */
import { useState, FormEvent } from "react";
import { Send, Loader2, AlertCircle, CheckCircle, AlertTriangle } from "lucide-react";
import { runTask } from "@/lib/api";
import type { RunTaskResponse } from "@/lib/types";

export default function RunTaskPage() {
  const [task, setTask] = useState("");
  const [project, setProject] = useState("");
  const [config, setConfig] = useState("default");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunTaskResponse | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (!task.trim()) {
      setError("Task is required.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await runTask({
        task: task.trim(),
        project: project.trim() || undefined,
        config: config.trim() || "default",
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Run task</h1>
        <p className="text-sm text-muted-foreground">
          Fire the team. The engine returns the team summary or a switch-not-flipped envelope.
        </p>
      </div>

      <form onSubmit={handleSubmit} data-testid="run-form" className="space-y-4">
        <label className="block text-sm">
          <span className="text-foreground">Task</span>
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={6}
            placeholder="Describe the task for the team..."
            data-testid="run-task-input"
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono"
          />
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="text-foreground">Project (optional)</span>
            <input
              type="text"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              placeholder="some-project-slug"
              className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-foreground">Config</span>
            <input
              type="text"
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              placeholder="default"
              className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
          </label>
        </div>

        <button
          type="submit"
          disabled={submitting}
          data-testid="run-submit"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Run
        </button>
      </form>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
          <AlertCircle className="h-5 w-5" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <section
          data-testid="run-result"
          className="rounded-lg border border-border bg-card p-5 space-y-3"
        >
          <header className="flex items-center gap-2">
            {result.status === "ok" && <CheckCircle className="h-5 w-5 text-green-600" />}
            {result.status === "switch-not-flipped" && (
              <AlertTriangle className="h-5 w-5 text-amber-500" />
            )}
            {result.status === "dry-run" && <CheckCircle className="h-5 w-5 text-blue-500" />}
            <h2 className="font-semibold text-foreground">{result.status}</h2>
          </header>
          <p className="text-sm text-foreground whitespace-pre-wrap" data-testid="run-summary">
            {result.summary}
          </p>
          {result.members && result.members.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Team members:</p>
              <ul className="text-xs text-foreground list-disc pl-4">
                {result.members.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
