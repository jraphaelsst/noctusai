/**
 * Modules — browse the catalog by module, drill into lessons.
 *
 * Left: module list (GET /api/catalog). Selecting a module loads its
 * lessons (GET /api/catalog/modules/{module}). Clicking a lesson routes
 * to /lessons/:module/:lesson (the viewer).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  FileText,
  Layers,
  MinusCircle,
  ScrollText,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { useCatalog, useModule } from "@/hooks/useCatalog";

export default function Modules() {
  const navigate = useNavigate();
  const { data: catalog, loading: catalogLoading, error: catalogError } =
    useCatalog();
  const [selected, setSelected] = useState<string | null>(null);
  const { data: moduleDetail, loading: moduleLoading, error: moduleError } =
    useModule(selected);

  // Auto-select the first module once the catalog loads.
  useEffect(() => {
    if (!selected && catalog.modules.length > 0) {
      setSelected(catalog.modules[0].name);
    }
  }, [catalog.modules, selected]);

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <div className="flex items-center gap-3">
        <Layers className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Módulos</h1>
          <p className="text-sm text-muted-foreground">
            Navegue pelo catálogo de conhecimento por módulo e aula.
          </p>
        </div>
      </div>

      {catalogError && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            {catalogError.message}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Module list */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Módulos</CardTitle>
            <CardDescription>
              {catalogLoading
                ? "Carregando…"
                : `${catalog.modules.length} módulo${catalog.modules.length !== 1 ? "s" : ""}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {catalogLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 rounded" />
                ))}
              </div>
            ) : catalog.modules.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Nenhum módulo no catálogo. Inicie um processamento.
              </p>
            ) : (
              catalog.modules.map((m) => (
                <button
                  key={m.name}
                  onClick={() => setSelected(m.name)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                    selected === m.name
                      ? "bg-primary/10 text-primary"
                      : "text-foreground hover:bg-muted",
                  )}
                >
                  <span className="truncate">{m.name}</span>
                  <Badge variant="outline" className="shrink-0 tabular-nums">
                    {m.lessons}
                  </Badge>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        {/* Lesson list for the selected module */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BookOpen className="h-4 w-4" />
              {selected ?? "Selecione um módulo"}
            </CardTitle>
            <CardDescription>
              {selected
                ? "Clique numa aula para abrir transcrição e resumo."
                : "Escolha um módulo à esquerda."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Nenhum módulo selecionado.
              </p>
            ) : moduleLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 rounded" />
                ))}
              </div>
            ) : moduleError ? (
              <p className="py-8 text-center text-sm text-destructive">
                {moduleError.message}
              </p>
            ) : !moduleDetail || moduleDetail.lessons.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Nenhuma aula neste módulo.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {moduleDetail.lessons.map((l) => (
                  <button
                    key={l.lesson}
                    onClick={() =>
                      navigate(
                        `/lessons/${encodeURIComponent(selected)}/${encodeURIComponent(l.lesson)}`,
                      )
                    }
                    className="flex w-full items-center justify-between gap-4 py-3 text-left transition-colors hover:bg-muted/50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-foreground">
                        {l.lesson}
                      </div>
                      <div className="flex flex-wrap items-center gap-3 pt-1 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          {l.has_transcript ? (
                            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                          ) : (
                            <MinusCircle className="h-3 w-3" />
                          )}
                          <FileText className="h-3 w-3" /> Transcrição
                          {l.has_transcript
                            ? ` (${l.transcript_chars.toLocaleString("pt-BR")} car.)`
                            : ""}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          {l.has_summary ? (
                            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                          ) : (
                            <MinusCircle className="h-3 w-3" />
                          )}
                          <ScrollText className="h-3 w-3" /> Resumo
                          {l.has_summary
                            ? ` (${l.summary_chars.toLocaleString("pt-BR")} car.)`
                            : ""}
                        </span>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
