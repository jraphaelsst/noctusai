/**
 * Runs — start a new extraction run + watch the runs list.
 *
 * Form: Drive URL input + "modo teste" (fake) checkbox → POST /api/runs.
 * Below: the runs list (GET /api/runs), live-polled so a running job's
 * status flips automatically.
 */
import { useState } from "react";
import { FolderInput, Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";

import { useRuns, startRun } from "@/hooks/useRuns";
import { RunStatusBadge } from "@/components/RunStatusBadge";

export default function Runs() {
  const { data: runs, loading, reload } = useRuns(4000);

  const [driveUrl, setDriveUrl] = useState("");
  const [fake, setFake] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fake && !driveUrl.trim()) {
      toast.error("Informe uma URL do Drive ou ative o modo teste.");
      return;
    }
    setSubmitting(true);
    try {
      const resp = await startRun({
        drive_url: driveUrl.trim() || null,
        fake,
      });
      toast.success(`Processamento iniciado (${resp.mode})`, {
        description: resp.run_id,
      });
      setDriveUrl("");
      setFake(false);
      reload();
    } catch (err: any) {
      toast.error("Falha ao iniciar processamento", {
        description: err?.message ?? "Tente novamente",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <div className="flex items-center gap-3">
        <Play className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Processamentos</h1>
          <p className="text-sm text-muted-foreground">
            Inicie a extração de uma pasta do Drive e acompanhe os jobs.
          </p>
        </div>
      </div>

      {/* New run form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderInput className="h-4 w-4" />
            Novo processamento
          </CardTitle>
          <CardDescription>
            Cole a URL de uma pasta do Google Drive — ou use o modo teste
            para gerar dados de exemplo sem acessar o Drive.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="drive-url">URL do Drive</Label>
              <Input
                id="drive-url"
                placeholder="https://drive.google.com/drive/folders/…"
                value={driveUrl}
                onChange={(e) => setDriveUrl(e.target.value)}
                disabled={fake}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="fake-mode"
                checked={fake}
                onCheckedChange={setFake}
              />
              <Label htmlFor="fake-mode" className="text-sm">
                Modo teste (fake) — não acessa o Drive
              </Label>
            </div>
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Iniciando…
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Iniciar processamento
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Runs list */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Histórico</CardTitle>
              <CardDescription>
                Atualiza automaticamente a cada 4s.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={reload}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Atualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14 rounded" announce={i === 0} />
              ))}
            </div>
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
              <Play className="h-8 w-8" />
              Nenhum processamento ainda. Inicie um acima.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {runs.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-sm text-foreground">
                      {run.run_id}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {run.mode} · iniciado{" "}
                      {new Date(run.started_at).toLocaleString("pt-BR")}
                      {run.finished_at
                        ? ` · concluído ${new Date(run.finished_at).toLocaleString("pt-BR")}`
                        : ""}
                    </div>
                    {run.detail && (
                      <div className="truncate text-xs text-muted-foreground">
                        {run.detail}
                      </div>
                    )}
                  </div>
                  <RunStatusBadge status={run.status} />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
