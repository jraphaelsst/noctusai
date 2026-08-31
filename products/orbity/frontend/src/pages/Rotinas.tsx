/**
 * Rotinas page — routines list, create/edit, delete, and "advance due" action.
 *
 * Full four states: loading, empty, error, success.
 * "Advance due" = POST /api/routines/run-due — spawns tasks for all active
 * routines due today or earlier.
 *
 * status_pagina key: "rotinas"  ← tech-lead must seed this row.
 */
import { useState } from 'react';
import {
  useRoutines,
  useCreateRoutine,
  useUpdateRoutine,
  useDeleteRoutine,
  useRunDueRoutines,
  type Routine,
  type RoutineCadence,
  type RoutineCreateData,
} from '@/hooks/useRoutines';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  RefreshCw,
  Plus,
  Loader2,
  AlertCircle,
  Trash2,
  Pencil,
  Play,
  Calendar,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CADENCE_CONFIG: Record<RoutineCadence, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  daily: { label: 'Diária', variant: 'default' },
  weekly: { label: 'Semanal', variant: 'secondary' },
  monthly: { label: 'Mensal', variant: 'outline' },
};

// ---------------------------------------------------------------------------
// Routine card
// ---------------------------------------------------------------------------

interface RoutineCardProps {
  routine: Routine;
  onEdit: (routine: Routine) => void;
  onDelete: (id: string) => void;
  onToggleActive: (routine: Routine) => void;
}

function RoutineCard({ routine, onEdit, onDelete, onToggleActive }: RoutineCardProps) {
  const cadenceCfg = CADENCE_CONFIG[routine.cadence as RoutineCadence] ?? CADENCE_CONFIG.daily;
  const nextRunDate = new Date(routine.next_run + 'T00:00:00');
  const isDue = nextRunDate <= new Date();

  return (
    <div className={`rounded-lg border bg-card p-4 space-y-3 hover:shadow-sm transition-shadow ${routine.active ? 'border-border' : 'border-border/50 opacity-60'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground">{routine.title}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <Badge variant={cadenceCfg.variant} className="text-xs">
              {cadenceCfg.label}
            </Badge>
            {!routine.active && (
              <Badge variant="outline" className="text-xs text-muted-foreground">
                Inativa
              </Badge>
            )}
            {isDue && routine.active && (
              <Badge variant="destructive" className="text-xs">
                Vencida
              </Badge>
            )}
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => onToggleActive(routine)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
            aria-label={routine.active ? 'Desativar rotina' : 'Ativar rotina'}
            title={routine.active ? 'Desativar' : 'Ativar'}
          >
            {routine.active ? (
              <ToggleRight className="h-4 w-4 text-green-600" />
            ) : (
              <ToggleLeft className="h-4 w-4" />
            )}
          </button>
          <button
            onClick={() => onEdit(routine)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
            aria-label="Editar rotina"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(routine.id)}
            className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
            aria-label="Excluir rotina"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {routine.description && (
        <p className="text-xs text-muted-foreground line-clamp-2">{routine.description}</p>
      )}

      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Calendar className="h-3 w-3" />
        <span>
          Próxima execução:{' '}
          <span className={isDue && routine.active ? 'text-destructive font-medium' : ''}>
            {nextRunDate.toLocaleDateString('pt-BR')}
          </span>
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Routine form dialog
// ---------------------------------------------------------------------------

interface RoutineFormDialogProps {
  open: boolean;
  onClose: () => void;
  routine?: Routine | null;
}

function RoutineFormDialog({ open, onClose, routine }: RoutineFormDialogProps) {
  const isEdit = !!routine;
  const createRoutine = useCreateRoutine();
  const updateRoutine = useUpdateRoutine();

  const [title, setTitle] = useState(routine?.title ?? '');
  const [description, setDescription] = useState(routine?.description ?? '');
  const [cadence, setCadence] = useState<RoutineCadence>(routine?.cadence as RoutineCadence ?? 'weekly');
  const [nextRun, setNextRun] = useState(routine?.next_run ?? new Date().toISOString().slice(0, 10));
  const [active, setActive] = useState(routine?.active ?? true);

  const handleOpenChange = (v: boolean) => {
    if (!v) onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const data: RoutineCreateData = {
      title: title.trim(),
      description: description.trim() || undefined,
      cadence,
      next_run: nextRun,
      active,
    };

    if (isEdit && routine) {
      await updateRoutine.mutateAsync({ id: routine.id, ...data });
    } else {
      await createRoutine.mutateAsync(data);
    }
    onClose();
  };

  const isPending = createRoutine.isPending || updateRoutine.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar Rotina' : 'Nova Rotina'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Título *</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Nome da rotina"
              required
              maxLength={500}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Descrição</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="O que essa rotina gera..."
              rows={2}
              maxLength={5000}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Cadência</label>
              <Select value={cadence} onValueChange={(v) => setCadence(v as RoutineCadence)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Diária</SelectItem>
                  <SelectItem value="weekly">Semanal</SelectItem>
                  <SelectItem value="monthly">Mensal</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Próxima execução</label>
              <Input
                type="date"
                value={nextRun}
                onChange={(e) => setNextRun(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="active"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            <label htmlFor="active" className="text-sm font-medium text-foreground cursor-pointer">
              Rotina ativa
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending || !title.trim() || !nextRun}>
              {isPending ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Salvando...</>
              ) : (
                isEdit ? 'Salvar' : 'Criar'
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Rotinas() {
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRoutine, setEditingRoutine] = useState<Routine | null>(null);

  const { data: routines, isPending, isError, error } = useRoutines(showActiveOnly);
  const deleteRoutine = useDeleteRoutine();
  const updateRoutine = useUpdateRoutine();
  const runDue = useRunDueRoutines();

  const items = routines ?? [];
  const dueCount = items.filter((r) => {
    const nextRun = new Date(r.next_run + 'T00:00:00');
    return r.active && nextRun <= new Date();
  }).length;

  const handleEdit = (routine: Routine) => {
    setEditingRoutine(routine);
    setDialogOpen(true);
  };

  const handleNew = () => {
    setEditingRoutine(null);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setEditingRoutine(null);
  };

  const handleDelete = (id: string) => {
    if (confirm('Excluir esta rotina?')) {
      deleteRoutine.mutate(id);
    }
  };

  const handleToggleActive = (routine: Routine) => {
    updateRoutine.mutate({ id: routine.id, active: !routine.active });
  };

  const handleRunDue = () => {
    if (dueCount === 0) return;
    if (confirm(`Executar ${dueCount} rotina(s) vencida(s) e criar as tarefas?`)) {
      runDue.mutate();
    }
  };

  // ── Loading state ──
  if (isPending && !routines) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        <span>Carregando rotinas...</span>
      </div>
    );
  }

  // ── Error state ──
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-destructive">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm font-medium">Erro ao carregar rotinas</p>
        <p className="text-xs text-muted-foreground">{(error as Error)?.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <RefreshCw className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Rotinas</h1>
            <p className="text-sm text-muted-foreground">
              {items.length} rotina{items.length !== 1 ? 's' : ''}
              {dueCount > 0 && (
                <span className="ml-2 text-destructive font-medium">
                  · {dueCount} vencida{dueCount !== 1 ? 's' : ''}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Active filter toggle */}
          <button
            onClick={() => setShowActiveOnly((v) => !v)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border transition-colors ${
              showActiveOnly
                ? 'bg-primary text-primary-foreground border-primary'
                : 'border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            {showActiveOnly ? <ToggleRight className="h-3.5 w-3.5" /> : <ToggleLeft className="h-3.5 w-3.5" />}
            Só ativas
          </button>

          {/* Run-due action */}
          <Button
            variant="outline"
            onClick={handleRunDue}
            disabled={dueCount === 0 || runDue.isPending}
          >
            {runDue.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Executar vencidas
            {dueCount > 0 && (
              <span className="ml-2 rounded-full bg-destructive text-destructive-foreground text-xs px-1.5 py-0.5">
                {dueCount}
              </span>
            )}
          </Button>

          <Button onClick={handleNew}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Rotina
          </Button>
        </div>
      </div>

      {/* Empty state */}
      {items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
          <RefreshCw className="h-12 w-12 opacity-40" />
          <p className="text-sm font-medium">
            {showActiveOnly ? 'Nenhuma rotina ativa' : 'Nenhuma rotina criada'}
          </p>
          <p className="text-xs">
            {showActiveOnly
              ? 'Ative uma rotina ou desative o filtro'
              : 'Crie a primeira rotina clicando em "Nova Rotina"'}
          </p>
        </div>
      )}

      {/* Routine grid */}
      {items.length > 0 && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((routine) => (
            <RoutineCard
              key={routine.id}
              routine={routine}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onToggleActive={handleToggleActive}
            />
          ))}
        </div>
      )}

      {/* Create/Edit dialog */}
      {dialogOpen && (
        <RoutineFormDialog
          open={dialogOpen}
          onClose={handleDialogClose}
          routine={editingRoutine}
        />
      )}
    </div>
  );
}
