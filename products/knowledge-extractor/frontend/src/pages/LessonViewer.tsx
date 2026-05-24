/**
 * LessonViewer — read one lesson's transcript + summary side by side.
 *
 * Route: /lessons/:module/:lesson → GET /api/catalog/lessons/{module}/{lesson}.
 * Markdown is rendered simply via `whitespace-pre-wrap` (no markdown lib
 * dependency, per the contract). Tabs: Transcrição / Resumo.
 */
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, BookOpen, FileText, Loader2, ScrollText } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { useLesson } from "@/hooks/useCatalog";

function MarkdownBlock({ value, emptyLabel }: { value: string | null; emptyLabel: string }) {
  if (!value) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
        <FileText className="h-8 w-8" />
        {emptyLabel}
      </div>
    );
  }
  return (
    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">
      {value}
    </pre>
  );
}

export default function LessonViewer() {
  const navigate = useNavigate();
  const { module, lesson } = useParams<{ module: string; lesson: string }>();
  const { data, loading, error } = useLesson(module ?? null, lesson ?? null);

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      {/* Header */}
      <div className="space-y-3">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 gap-1"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4" /> Voltar
        </Button>
        <div className="flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-primary" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold text-foreground">
              {lesson ?? "Aula"}
            </h1>
            <p className="truncate text-sm text-muted-foreground">
              {module ?? "—"}
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando aula…
        </div>
      ) : error ? (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            {error.message}
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue="transcript" className="w-full">
          <TabsList className="grid w-full grid-cols-2 sm:max-w-sm">
            <TabsTrigger value="transcript" className="gap-1">
              <FileText className="h-4 w-4" /> Transcrição
            </TabsTrigger>
            <TabsTrigger value="summary" className="gap-1">
              <ScrollText className="h-4 w-4" /> Resumo
            </TabsTrigger>
          </TabsList>

          <TabsContent value="transcript" className="mt-4">
            <Card>
              <CardContent className="p-6">
                <MarkdownBlock
                  value={data?.transcript ?? null}
                  emptyLabel="Sem transcrição para esta aula."
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="summary" className="mt-4">
            <Card>
              <CardContent className="p-6">
                <MarkdownBlock
                  value={data?.summary ?? null}
                  emptyLabel="Sem resumo para esta aula."
                />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
