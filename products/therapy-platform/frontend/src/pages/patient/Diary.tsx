import { useState } from 'react';
import { Loader2, BookOpen, Plus, Trash2, Eye, EyeOff } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Switch } from '@noctusai/seed/components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { formatDate } from '@/lib/utils';
import {
  useJournalEntries, useCreateJournalEntry, useUpdateJournalEntry, useDeleteJournalEntry,
} from '@/hooks/useDiary';
import type { JournalEntry } from '@/types';

export default function Diary() {
  const [page, setPage] = useState(1);
  const { data, isPending } = useJournalEntries(page);
  const showSkeleton = isPending && !data;
  const createEntry = useCreateJournalEntry();
  const updateEntry = useUpdateJournalEntry();
  const deleteEntry = useDeleteJournalEntry();

  const [createOpen, setCreateOpen] = useState(false);
  const [editEntry, setEditEntry] = useState<JournalEntry | null>(null);
  const [form, setForm] = useState({ titulo: '', conteudo: '', is_shared_with_therapist: false });

  const entries = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 10);

  function openCreate() {
    setForm({ titulo: '', conteudo: '', is_shared_with_therapist: false });
    setCreateOpen(true);
  }

  function openEdit(entry: JournalEntry) {
    setForm({
      titulo: entry.titulo ?? '',
      conteudo: entry.conteudo,
      is_shared_with_therapist: entry.is_shared_with_therapist,
    });
    setEditEntry(entry);
  }

  function handleCreate() {
    createEntry.mutate(
      {
        titulo: form.titulo.trim() || undefined,
        conteudo: form.conteudo,
        is_shared_with_therapist: form.is_shared_with_therapist,
      },
      { onSuccess: () => setCreateOpen(false) }
    );
  }

  function handleUpdate() {
    if (!editEntry) return;
    updateEntry.mutate(
      {
        id: editEntry.id,
        titulo: form.titulo.trim() || undefined,
        conteudo: form.conteudo,
        is_shared_with_therapist: form.is_shared_with_therapist,
      },
      { onSuccess: () => setEditEntry(null) }
    );
  }

  function handleDelete(id: string) {
    deleteEntry.mutate(id);
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookOpen className="h-6 w-6" /> Meu Diario
          </h1>
          <p className="text-muted-foreground">Escreva sobre seus pensamentos e experiencias</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> Nova Entrada
        </Button>
      </div>

      {showSkeleton ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : entries.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <BookOpen className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm text-muted-foreground">Seu diario esta vazio. Comece escrevendo sua primeira entrada.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <Card key={entry.id}>
              <CardContent className="p-4">
                <div className="flex flex-col sm:flex-row sm:items-start gap-3">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      {entry.titulo && <span className="font-medium">{entry.titulo}</span>}
                      <span className="text-xs text-muted-foreground">{formatDate(entry.created_at)}</span>
                      {entry.is_shared_with_therapist ? (
                        <Badge variant="secondary" className="text-xs gap-1">
                          <Eye className="h-3 w-3" /> Compartilhado
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs gap-1">
                          <EyeOff className="h-3 w-3" /> Privado
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm whitespace-pre-wrap line-clamp-4">{entry.conteudo}</p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button size="sm" variant="outline" onClick={() => openEdit(entry)}>Editar</Button>
                    <Button size="sm" variant="ghost" onClick={() => handleDelete(entry.id)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
              <span className="text-sm text-muted-foreground flex items-center px-2">Pagina {page} de {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Proxima</Button>
            </div>
          )}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Nova Entrada do Diario</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Titulo (opcional)</Label>
              <Input value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} placeholder="Titulo da entrada..." />
            </div>
            <div>
              <Label>Conteudo *</Label>
              <Textarea
                rows={6}
                value={form.conteudo}
                onChange={(e) => setForm({ ...form, conteudo: e.target.value })}
                placeholder="Escreva seus pensamentos..."
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_shared_with_therapist}
                onCheckedChange={(checked) => setForm({ ...form, is_shared_with_therapist: checked })}
              />
              <Label>Compartilhar com meu terapeuta</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={!form.conteudo.trim() || createEntry.isPending}>
              {createEntry.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editEntry} onOpenChange={(open) => !open && setEditEntry(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Editar Entrada</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Titulo (opcional)</Label>
              <Input value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
            </div>
            <div>
              <Label>Conteudo *</Label>
              <Textarea
                rows={6}
                value={form.conteudo}
                onChange={(e) => setForm({ ...form, conteudo: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_shared_with_therapist}
                onCheckedChange={(checked) => setForm({ ...form, is_shared_with_therapist: checked })}
              />
              <Label>Compartilhar com meu terapeuta</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditEntry(null)}>Cancelar</Button>
            <Button onClick={handleUpdate} disabled={!form.conteudo.trim() || updateEntry.isPending}>
              {updateEntry.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
