/**
 * Methodology — renders the synthesized methodology document if available.
 *
 * GET /api/methodology → { available, markdown, modules }. Markdown is
 * rendered simply via `whitespace-pre-wrap` (no markdown lib dependency).
 */
import { BookMarked, Layers, Loader2, RefreshCw } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

import { useMethodology } from "@/hooks/useMethodology";

export default function Methodology() {
  const { data, loading, error, reload } = useMethodology();

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <BookMarked className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Metodologia</h1>
            <p className="text-sm text-muted-foreground">
              Documento de metodologia sintetizado a partir do conteúdo.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={reload}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            {error.message}
          </CardContent>
        </Card>
      )}

      {/* Modules covered */}
      {data.modules.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Layers className="h-3.5 w-3.5" /> Módulos cobertos:
          </span>
          {data.modules.map((m) => (
            <Badge key={m} variant="outline">
              {m}
            </Badge>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Metodologia</CardTitle>
          <CardDescription>
            Gerada a partir dos resumos das aulas processadas.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Carregando metodologia…
            </div>
          ) : !data.available || !data.markdown ? (
            <div className="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
              <BookMarked className="h-8 w-8" />
              <p className="max-w-md">
                Nenhuma metodologia disponível ainda. Ela é gerada após o
                processamento das aulas. Inicie um processamento na página de
                Processamentos.
              </p>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">
              {data.markdown}
            </pre>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
