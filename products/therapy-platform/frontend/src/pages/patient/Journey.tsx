import { useState } from 'react';
import { Loader2, ChevronDown, Sparkles } from 'lucide-react';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Separator } from '@noctusai/seed/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@noctusai/seed/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { usePatientLongitudinal, usePatientLongitudinalVersions } from '@/hooks/useLongitudinal';
import type { PatientLongitudinal } from '@/types/session';

const MIN_SESSIONS = 3;

export default function Journey() {
  const { data: latest, isPending } = usePatientLongitudinal();
  const { data: versions } = usePatientLongitudinalVersions();

  if (isPending && !latest) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!latest) {
    return (
      <div className="space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Minha Jornada</h1>
          <p className="mt-1 text-sm text-gray-500">Sua analise longitudinal de progresso terapeutico</p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Sparkles className="h-10 w-10 text-gray-300" />
            <h3 className="mt-3 text-base font-medium text-gray-700">Sua jornada esta comecando</h3>
            <p className="mt-1 max-w-md text-center text-sm text-gray-500">
              Sua jornada terapeutica comecara a ser gerada apos {MIN_SESSIONS} sessoes.
              Continue comparecendo as suas sessoes e em breve voce tera acesso a uma analise
              personalizada do seu progresso.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const generatedDate = new Date(latest.created_at).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Minha Jornada</h1>
        <p className="mt-1 text-sm text-gray-500">
          Versao {latest.version_number} — gerado em {generatedDate} — baseado em{' '}
          {latest.session_count_at_generation} sessoes
        </p>
      </div>

      <Separator />

      {/* Narrative Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Resumo Narrativo</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">{latest.narrative_summary}</p>
        </CardContent>
      </Card>

      {/* Recurring Themes */}
      {latest.recurring_themes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Temas Recorrentes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {latest.recurring_themes.map((theme, i) => (
                <Badge key={i} variant="secondary" className="text-sm">
                  {theme}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progress Reflection */}
      {latest.progress_reflection.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Reflexao de Progresso</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-2 text-sm text-gray-700">
              {latest.progress_reflection.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Ongoing Topics */}
      {latest.ongoing_topics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Topicos em Andamento</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-2 text-sm text-gray-700">
              {latest.ongoing_topics.map((topic, i) => (
                <li key={i}>{topic}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Version History */}
      {versions && versions.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Versoes Anteriores</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {versions
              .filter((v) => v.version_number !== latest.version_number)
              .map((version) => (
                <VersionItem key={version.id} version={version} />
              ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function VersionItem({ version }: { version: PatientLongitudinal }) {
  const [open, setOpen] = useState(false);
  const date = new Date(version.created_at).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  });

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md border p-3 hover:bg-gray-50">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">Versao {version.version_number}</span>
          <span className="text-xs text-gray-500">{date}</span>
          <span className="text-xs text-gray-400">
            ({version.session_count_at_generation} sessoes)
          </span>
        </div>
        <ChevronDown className={cn('h-4 w-4 text-gray-400 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 px-3 pb-3 pt-2">
        <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">{version.narrative_summary}</p>
        {version.recurring_themes.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {version.recurring_themes.map((t, i) => (
              <Badge key={i} variant="outline" className="text-xs">{t}</Badge>
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
