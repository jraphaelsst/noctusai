import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { User, Calendar, FileText, Eye, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { useSessionJournal } from '@/hooks/useJournal';
import { useClinicalLongitudinal, useClinicalLongitudinalVersions } from '@/hooks/useLongitudinal';
import type { ClinicalLongitudinal } from '@/types/session';

export default function PatientProfile() {
  const { id: patientId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // Journal sessions for this patient — filtered server-side ideally, but we fetch all for now
  const { data: journalData, isLoading: loadingJournal } = useSessionJournal(1, 50);
  const { data: longitudinal, isLoading: loadingLong } = useClinicalLongitudinal(patientId);
  const { data: longVersions } = useClinicalLongitudinalVersions(patientId);

  const sessions = journalData?.data ?? [];

  const isLoading = loadingJournal || loadingLong;

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  const longDate = longitudinal?.created_at
    ? new Date(longitudinal.created_at).toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '';

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-100">
            <User className="h-7 w-7 text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Paciente</h1>
            <div className="mt-1 flex items-center gap-2 text-sm text-gray-500">
              <span>{sessions.length} sessoes</span>
            </div>
          </div>
        </div>
      </div>

      <Separator />

      <Tabs defaultValue="diario" className="space-y-4">
        <TabsList className="flex-wrap">
          <TabsTrigger value="perfil">Perfil</TabsTrigger>
          <TabsTrigger value="diario">Diario de Sessoes</TabsTrigger>
          <TabsTrigger value="longitudinal">Analise Longitudinal</TabsTrigger>
          <TabsTrigger value="agendamentos">Agendamentos</TabsTrigger>
          <TabsTrigger value="precos">Precos</TabsTrigger>
          <TabsTrigger value="visao-paciente">Visao do Paciente</TabsTrigger>
        </TabsList>

        {/* Perfil */}
        <TabsContent value="perfil">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Informacoes do Paciente</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-500">Dados do perfil serao exibidos aqui.</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Diario de Sessoes */}
        <TabsContent value="diario">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Diario de Sessoes</CardTitle>
            </CardHeader>
            <CardContent>
              {sessions.length === 0 ? (
                <p className="text-sm text-gray-500">Nenhuma sessao registrada com este paciente.</p>
              ) : (
                <div className="space-y-3">
                  {sessions.map((session) => {
                    const date = new Date(session.created_at).toLocaleDateString('pt-BR', {
                      day: '2-digit',
                      month: 'long',
                      year: 'numeric',
                    });

                    return (
                      <div
                        key={session.id}
                        className="flex cursor-pointer items-center justify-between rounded-md border p-3 transition-colors hover:bg-gray-50"
                        onClick={() => navigate(`/therapist/sessoes/${session.id}`)}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Calendar className="h-4 w-4 text-gray-400" />
                            <span className="text-sm font-medium">{date}</span>
                            {session.ai_generated_at && (
                              <Badge variant="secondary" className="text-[10px]">IA</Badge>
                            )}
                          </div>
                          {session.combined_transcript_text && (
                            <p className="mt-1 truncate text-sm text-gray-500">
                              {session.combined_transcript_text.slice(0, 120)}...
                            </p>
                          )}
                        </div>
                        <ChevronRight className="h-4 w-4 shrink-0 text-gray-300" />
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Analise Longitudinal */}
        <TabsContent value="longitudinal">
          {!longitudinal ? (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-sm text-gray-500">
                  Analise longitudinal ainda nao disponivel. Necessario um minimo de sessoes.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-gray-500">
                Versao {longitudinal.version_number} — gerado em {longDate} — baseado em{' '}
                {longitudinal.session_count_at_generation} sessoes
              </div>

              {/* Narrative */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Narrativa Clinica</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                    {longitudinal.narrative_summary}
                  </p>
                </CardContent>
              </Card>

              {/* Recurring Themes */}
              {longitudinal.recurring_themes.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Temas Recorrentes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {longitudinal.recurring_themes.map((theme, i) => (
                        <Badge key={i} variant="secondary">{theme}</Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Progress Timeline */}
              {longitudinal.progress_timeline.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Linha do Tempo de Progresso</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="list-inside list-disc space-y-2 text-sm text-gray-700">
                      {longitudinal.progress_timeline.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {/* Unresolved Topics */}
              {longitudinal.unresolved_topics.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Topicos Nao Resolvidos</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="list-inside list-disc space-y-2 text-sm text-gray-700">
                      {longitudinal.unresolved_topics.map((topic, i) => (
                        <li key={i}>{topic}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {/* Observation Insights */}
              {longitudinal.observation_insights && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Insights de Observacoes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                      {longitudinal.observation_insights}
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Version History */}
              {longVersions && longVersions.length > 1 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Versoes Anteriores</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {longVersions
                      .filter((v) => v.version_number !== longitudinal.version_number)
                      .map((version) => (
                        <LongVersionItem key={version.id} version={version} />
                      ))}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        {/* Agendamentos */}
        <TabsContent value="agendamentos">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Agendamentos</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-500">Proximos agendamentos e historico.</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Precos */}
        <TabsContent value="precos">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Precos Personalizados</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-500">Configuracao de precos para este paciente.</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Visao do Paciente */}
        <TabsContent value="visao-paciente">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Eye className="h-5 w-5 text-gray-400" />
                <CardTitle className="text-lg">Visao do Paciente (Track 1)</CardTitle>
              </div>
              <p className="text-xs text-gray-500">
                Resumos base que o paciente visualiza. Notas pessoais e jornada do paciente nao sao exibidas aqui.
              </p>
            </CardHeader>
            <CardContent>
              {sessions.length === 0 ? (
                <p className="text-sm text-gray-500">Nenhuma sessao disponivel.</p>
              ) : (
                <div className="space-y-4">
                  {sessions.slice(0, 5).map((session) => {
                    const date = new Date(session.created_at).toLocaleDateString('pt-BR', {
                      day: '2-digit',
                      month: 'long',
                      year: 'numeric',
                    });
                    return (
                      <div key={session.id} className="rounded-md border p-4">
                        <div className="mb-2 text-sm font-medium text-gray-900">{date}</div>
                        <p className="text-sm text-gray-600">
                          {session.combined_transcript_text
                            ? session.combined_transcript_text.slice(0, 200) + '...'
                            : 'Resumo base nao disponivel.'}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function LongVersionItem({ version }: { version: ClinicalLongitudinal }) {
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
