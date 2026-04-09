import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { FileText, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { useSessionDetail, usePatientNotes, useCreatePatientNote, useUpdatePatientNote } from '@/hooks/useJournal';

export default function PatientSessionDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: session, isLoading } = useSessionDetail(id);
  const { data: notes } = usePatientNotes(id);
  const createNote = useCreatePatientNote();
  const updateNote = useUpdatePatientNote();

  const [noteText, setNoteText] = useState('');
  const [noteLoaded, setNoteLoaded] = useState(false);

  const baseSummary = session?.latest_base;
  const existingNote = notes?.[0];

  // Load existing note text
  if (existingNote && !noteLoaded) {
    setNoteText(existingNote.note_text);
    setNoteLoaded(true);
  }

  const sessionDate = session?.created_at
    ? new Date(session.created_at).toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '';

  function handleSaveNote() {
    if (!id || !noteText.trim()) return;

    if (existingNote) {
      updateNote.mutate(
        { id: existingNote.id, note_text: noteText.trim(), session_record_id: id },
        { onSuccess: () => toast.success('Anotacao atualizada') },
      );
    } else {
      createNote.mutate(
        { session_record_id: id, note_text: noteText.trim() },
        { onSuccess: () => toast.success('Anotacao salva') },
      );
    }
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

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Sessao de {sessionDate}</h1>
        {baseSummary?.created_at && (
          <p className="mt-1 text-xs text-gray-500">
            Resumo atualizado em {new Date(baseSummary.created_at).toLocaleDateString('pt-BR')}
          </p>
        )}
      </div>

      {baseSummary?.tags && baseSummary.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {baseSummary.tags.map((tag) => (
            <Badge key={tag} variant="secondary">{tag}</Badge>
          ))}
        </div>
      )}

      <Separator />

      <Tabs defaultValue="resumo" className="space-y-4">
        <TabsList>
          <TabsTrigger value="resumo">Resumo</TabsTrigger>
          <TabsTrigger value="anotacoes">Minhas Anotacoes</TabsTrigger>
        </TabsList>

        {/* Resumo (Track 1) */}
        <TabsContent value="resumo">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileText className="h-5 w-5 text-gray-400" />
                Resumo da Sessao
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                {baseSummary?.summary ?? 'Resumo ainda nao disponivel. Por favor, aguarde o processamento.'}
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
            </CardContent>
          </Card>
        </TabsContent>

        {/* Minhas Anotacoes */}
        <TabsContent value="anotacoes">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Minhas Anotacoes</CardTitle>
              <p className="text-xs text-gray-500">
                Somente voce pode ver estas anotacoes. Elas nao sao compartilhadas com seu terapeuta.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                className="min-h-[160px] w-full rounded-md border p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Escreva suas reflexoes sobre esta sessao..."
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
              />
              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={handleSaveNote}
                  disabled={createNote.isPending || updateNote.isPending || !noteText.trim()}
                >
                  {(createNote.isPending || updateNote.isPending) && (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  )}
                  Salvar
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
