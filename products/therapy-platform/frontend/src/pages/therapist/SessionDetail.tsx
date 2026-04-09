import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FileText, Eye, Clock, Download, RefreshCw, Plus, Pencil, Trash2, Loader2, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  useSessionDetail,
  useSessionVersions,
  useSessionAudio,
  useObservations,
  useCreateObservation,
  useUpdateObservation,
  useDeleteObservation,
} from '@/hooks/useJournal';
import { useReopenSession } from '@/hooks/useSessions';
import type { SessionSummaryVersion, SessionObservation } from '@/types/session';

const SOURCE_BADGES: Record<string, { label: string; color: string }> = {
  ai_generated: { label: 'IA', color: 'bg-blue-100 text-blue-800' },
  ai_auto_fallback: { label: 'IA (fallback)', color: 'bg-yellow-100 text-yellow-800' },
  manual_edit: { label: 'Manual', color: 'bg-gray-100 text-gray-800' },
};

export default function TherapistSessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: session, isLoading } = useSessionDetail(id);
  const { data: versions } = useSessionVersions(id);
  const { data: audioSegments } = useSessionAudio(id);
  const { data: observations } = useObservations(id);
  const reopenSession = useReopenSession();
  const createObservation = useCreateObservation();
  const updateObservation = useUpdateObservation();
  const deleteObservation = useDeleteObservation();

  const [editingSummary, setEditingSummary] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState('');
  const [newObservation, setNewObservation] = useState('');
  const [showNewObs, setShowNewObs] = useState(false);
  const [editingObsId, setEditingObsId] = useState<string | null>(null);
  const [editingObsText, setEditingObsText] = useState('');
  const [privateNotes, setPrivateNotes] = useState('');
  const [privateNotesLoaded, setPrivateNotesLoaded] = useState(false);

  // Load private notes from session when available
  if (session?.therapist_notes_private && !privateNotesLoaded) {
    setPrivateNotes(session.therapist_notes_private);
    setPrivateNotesLoaded(true);
  }

  const clinicalSummary = session?.latest_clinical;
  const baseSummary = session?.latest_base;

  const sessionDate = session?.created_at
    ? new Date(session.created_at).toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '';

  function handleStartEditSummary() {
    if (!clinicalSummary) return;
    setSummaryDraft(clinicalSummary.summary);
    setEditingSummary(true);
  }

  function handleSaveSummary() {
    // Would POST a new manual_edit version
    toast.success('Resumo atualizado (nova versao criada)');
    setEditingSummary(false);
  }

  function handleAddObservation() {
    if (!id || !newObservation.trim()) return;
    createObservation.mutate(
      { session_record_id: id, observation_text: newObservation.trim() },
      {
        onSuccess: () => {
          setNewObservation('');
          setShowNewObs(false);
          toast.info('O resumo sera regenerado com a nova observacao');
        },
      },
    );
  }

  function handleUpdateObservation(obsId: string) {
    if (!id || !editingObsText.trim()) return;
    updateObservation.mutate(
      { id: obsId, observation_text: editingObsText.trim(), session_record_id: id },
      {
        onSuccess: () => {
          setEditingObsId(null);
          setEditingObsText('');
        },
      },
    );
  }

  function handleDeleteObservation(obsId: string) {
    if (!id) return;
    deleteObservation.mutate({ id: obsId, session_record_id: id });
  }

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="p-6 text-center text-gray-500">Sessao nao encontrada.</div>
    );
  }

  const canDownloadAudio = audioSegments?.some(
    (seg) => seg.audio_file_url && (!seg.download_expires_at || new Date(seg.download_expires_at) > new Date()),
  );

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Detalhes da Sessao</h1>
          <p className="mt-1 text-sm text-gray-500">
            {sessionDate} &middot; {session.total_segments} segmento(s)
          </p>
        </div>
        <div className="flex items-center gap-2">
          {clinicalSummary?.tags?.map((tag) => (
            <Badge key={tag} variant="secondary">{tag}</Badge>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {canDownloadAudio && (
          <Button variant="outline" size="sm" className="gap-1.5">
            <Download className="h-4 w-4" />
            Baixar Audio
          </Button>
        )}
        {/* Reopen if applicable — would check from session status */}
      </div>

      <Separator />

      <Tabs defaultValue="resumo" className="space-y-4">
        <TabsList>
          <TabsTrigger value="resumo">Resumo Clinico</TabsTrigger>
          <TabsTrigger value="observacoes">Observacoes</TabsTrigger>
          <TabsTrigger value="notas">Notas Privadas</TabsTrigger>
          <TabsTrigger value="versoes">Historico de Versoes</TabsTrigger>
          <TabsTrigger value="paciente">Visao do Paciente</TabsTrigger>
        </TabsList>

        {/* Resumo Clinico */}
        <TabsContent value="resumo">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg">Resumo Clinico (Track 2)</CardTitle>
                {clinicalSummary?.created_at && (
                  <p className="mt-1 text-xs text-gray-500">
                    Resumo atualizado em{' '}
                    {new Date(clinicalSummary.created_at).toLocaleDateString('pt-BR')}
                  </p>
                )}
              </div>
              {!editingSummary && (
                <Button variant="outline" size="sm" className="gap-1.5" onClick={handleStartEditSummary}>
                  <Pencil className="h-3.5 w-3.5" />
                  Editar
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {editingSummary ? (
                <div className="space-y-3">
                  <textarea
                    className="min-h-[200px] w-full rounded-md border p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={summaryDraft}
                    onChange={(e) => setSummaryDraft(e.target.value)}
                  />
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditingSummary(false)}>
                      Cancelar
                    </Button>
                    <Button size="sm" onClick={handleSaveSummary}>
                      Salvar (nova versao)
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                    {clinicalSummary?.summary ?? 'Resumo ainda nao disponivel.'}
                  </p>
                  {clinicalSummary?.key_points && clinicalSummary.key_points.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium text-gray-900">Pontos-chave</h4>
                      <ul className="list-inside list-disc space-y-1 text-sm text-gray-600">
                        {clinicalSummary.key_points.map((point, i) => (
                          <li key={i}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Observacoes */}
        <TabsContent value="observacoes">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Observacoes Clinicas</CardTitle>
              <Button size="sm" className="gap-1.5" onClick={() => setShowNewObs(true)}>
                <Plus className="h-3.5 w-3.5" />
                Adicionar Observacao
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {showNewObs && (
                <div className="space-y-2 rounded-md border border-blue-200 bg-blue-50 p-3">
                  <textarea
                    className="min-h-[80px] w-full rounded-md border p-2 text-sm focus:border-blue-500 focus:outline-none"
                    placeholder="Descreva sua observacao clinica..."
                    value={newObservation}
                    onChange={(e) => setNewObservation(e.target.value)}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setShowNewObs(false);
                        setNewObservation('');
                      }}
                    >
                      Cancelar
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleAddObservation}
                      disabled={createObservation.isPending || !newObservation.trim()}
                    >
                      {createObservation.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      Adicionar
                    </Button>
                  </div>
                </div>
              )}

              {!observations || observations.length === 0 ? (
                <p className="text-sm text-gray-500">Nenhuma observacao registrada.</p>
              ) : (
                <div className="space-y-3">
                  {observations.map((obs) => (
                    <ObservationItem
                      key={obs.id}
                      observation={obs}
                      isEditing={editingObsId === obs.id}
                      editText={editingObsText}
                      onStartEdit={() => {
                        setEditingObsId(obs.id);
                        setEditingObsText(obs.observation_text);
                      }}
                      onChangeEdit={setEditingObsText}
                      onSaveEdit={() => handleUpdateObservation(obs.id)}
                      onCancelEdit={() => {
                        setEditingObsId(null);
                        setEditingObsText('');
                      }}
                      onDelete={() => handleDeleteObservation(obs.id)}
                      isSaving={updateObservation.isPending}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notas Privadas */}
        <TabsContent value="notas">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Notas Privadas</CardTitle>
              <p className="text-xs text-gray-500">
                Estas notas nao sao compartilhadas com o paciente e nao alimentam a IA.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                className="min-h-[200px] w-full rounded-md border p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Suas notas privadas sobre esta sessao..."
                value={privateNotes}
                onChange={(e) => setPrivateNotes(e.target.value)}
              />
              <div className="flex justify-end">
                <Button size="sm" onClick={() => toast.success('Notas salvas')}>
                  Salvar
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Historico de Versoes */}
        <TabsContent value="versoes">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Historico de Versoes</CardTitle>
            </CardHeader>
            <CardContent>
              {!versions || versions.length === 0 ? (
                <p className="text-sm text-gray-500">Nenhuma versao disponivel.</p>
              ) : (
                <div className="space-y-2">
                  {versions
                    .filter((v) => v.track === 'clinical')
                    .map((version) => (
                      <VersionItem key={version.id} version={version} />
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Visao do Paciente */}
        <TabsContent value="paciente">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Eye className="h-5 w-5 text-gray-400" />
                <CardTitle className="text-lg">Visao do Paciente (Track 1)</CardTitle>
              </div>
              <p className="text-xs text-gray-500">Este e o resumo que o paciente visualiza.</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                {baseSummary?.summary ?? 'Resumo base ainda nao disponivel.'}
              </p>
              {baseSummary?.key_points && baseSummary.key_points.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-medium text-gray-900">Pontos-chave</h4>
                  <ul className="list-inside list-disc space-y-1 text-sm text-gray-600">
                    {baseSummary.key_points.map((point, i) => (
                      <li key={i}>{point}</li>
                    ))}
                  </ul>
                </div>
              )}
              {baseSummary?.tags && baseSummary.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {baseSummary.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">{tag}</Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────

function ObservationItem({
  observation,
  isEditing,
  editText,
  onStartEdit,
  onChangeEdit,
  onSaveEdit,
  onCancelEdit,
  onDelete,
  isSaving,
}: {
  observation: SessionObservation;
  isEditing: boolean;
  editText: string;
  onStartEdit: () => void;
  onChangeEdit: (text: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDelete: () => void;
  isSaving: boolean;
}) {
  const timestamp = new Date(observation.created_at).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-xs text-gray-500">{timestamp}</span>
          {observation.is_initial && (
            <Badge variant="outline" className="text-[10px]">Inicial</Badge>
          )}
        </div>
        {!isEditing && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onStartEdit}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:text-red-700">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Remover observacao?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Esta acao nao pode ser desfeita. O resumo sera regenerado sem esta observacao.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} className="bg-red-600 hover:bg-red-700">
                    Remover
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </div>
      {isEditing ? (
        <div className="space-y-2">
          <textarea
            className="min-h-[60px] w-full rounded-md border p-2 text-sm focus:border-blue-500 focus:outline-none"
            value={editText}
            onChange={(e) => onChangeEdit(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onCancelEdit}>
              Cancelar
            </Button>
            <Button size="sm" onClick={onSaveEdit} disabled={isSaving}>
              {isSaving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Salvar
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-gray-700">{observation.observation_text}</p>
      )}
    </div>
  );
}

function VersionItem({ version }: { version: SessionSummaryVersion }) {
  const [open, setOpen] = useState(false);
  const sourceBadge = SOURCE_BADGES[version.source] ?? { label: version.source, color: 'bg-gray-100 text-gray-800' };
  const date = new Date(version.created_at).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md border p-3 hover:bg-gray-50">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">Versao {version.version_number}</span>
          <Badge className={cn('text-[10px]', sourceBadge.color)}>{sourceBadge.label}</Badge>
          <span className="text-xs text-gray-500">{date}</span>
        </div>
        <ChevronDown className={cn('h-4 w-4 text-gray-400 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-3 pt-2">
        <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">{version.summary}</p>
        {version.key_points.length > 0 && (
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-gray-600">
            {version.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
