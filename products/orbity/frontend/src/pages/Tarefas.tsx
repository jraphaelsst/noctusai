/**
 * Tarefas page — Kanban-style task board (todo / doing / done columns).
 *
 * Full four states: loading, empty, error, success.
 * CRUD: create, edit (via modal), delete, and quick status-toggle between columns.
 * Filters: priority, status override for list view.
 *
 * status_pagina key: "tarefas"  ← tech-lead must seed this row.
 */
import { useState } from 'react';
import {
  useTasks,
  useCreateTask,
  useUpdateTask,
  useUpdateTaskStatus,
  useDeleteTask,
  type Task,
  type TaskStatus,
  type TaskPriority,
  type TaskCreateData,
} from '@/hooks/useTasks';
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
  ClipboardList,
  Plus,
  Loader2,
  AlertCircle,
  Trash2,
  Pencil,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Circle,
  Clock,
  XCircle,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_COLUMNS: { key: TaskStatus; label: string; icon: React.ElementType; color: string }[] = [
  { key: 'todo', label: 'A Fazer', icon: Circle, color: 'bg-slate-100 border-slate-200' },
  { key: 'doing', label: 'Em Andamento', icon: Clock, color: 'bg-blue-50 border-blue-200' },
  { key: 'done', label: 'Concluído', icon: CheckCircle2, color: 'bg-green-50 border-green-200' },
];

const PRIORITY_BADGE: Record<TaskPriority, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  low: { label: 'Baixa', variant: 'secondary' },
  med: { label: 'Média', variant: 'default' },
  high: { label: 'Alta', variant: 'destructive' },
};

// ---------------------------------------------------------------------------
// Task card component
// ---------------------------------------------------------------------------

interface TaskCardProps {
  task: Task;
  onEdit: (task: Task) => void;
  onDelete: (id: string) => void;
  onStatusChange: (id: string, status: TaskStatus) => void;
}

function TaskCard({ task, onEdit, onDelete, onStatusChange }: TaskCardProps) {
  const priorityCfg = PRIORITY_BADGE[task.priority as TaskPriority] ?? PRIORITY_BADGE.med;
  const currentIdx = STATUS_COLUMNS.findIndex((c) => c.key === task.status);
  const canMoveBack = currentIdx > 0;
  const canMoveForward = currentIdx < STATUS_COLUMNS.length - 1;

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-foreground leading-snug flex-1">{task.title}</p>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => onEdit(task)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
            aria-label="Editar tarefa"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(task.id)}
            className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
            aria-label="Excluir tarefa"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {task.description && (
        <p className="text-xs text-muted-foreground line-clamp-2">{task.description}</p>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant={priorityCfg.variant} className="text-xs">
          {priorityCfg.label}
        </Badge>
        {task.due_date && (
          <span className="text-xs text-muted-foreground">
            Prazo: {new Date(task.due_date).toLocaleDateString('pt-BR')}
          </span>
        )}
      </div>

      <div className="flex gap-1 pt-1">
        {canMoveBack && (
          <button
            onClick={() => onStatusChange(task.id, STATUS_COLUMNS[currentIdx - 1].key)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Mover para coluna anterior"
          >
            <ArrowLeft className="h-3 w-3" />
            {STATUS_COLUMNS[currentIdx - 1].label}
          </button>
        )}
        {canMoveBack && canMoveForward && <span className="text-muted-foreground text-xs">·</span>}
        {canMoveForward && (
          <button
            onClick={() => onStatusChange(task.id, STATUS_COLUMNS[currentIdx + 1].key)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Mover para próxima coluna"
          >
            {STATUS_COLUMNS[currentIdx + 1].label}
            <ArrowRight className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task form dialog
// ---------------------------------------------------------------------------

interface TaskFormDialogProps {
  open: boolean;
  onClose: () => void;
  task?: Task | null;
}

function TaskFormDialog({ open, onClose, task }: TaskFormDialogProps) {
  const isEdit = !!task;
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();

  const [title, setTitle] = useState(task?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? '');
  const [priority, setPriority] = useState<TaskPriority>(task?.priority as TaskPriority ?? 'med');
  const [dueDate, setDueDate] = useState(task?.due_date ?? '');

  // Reset form fields when dialog opens for a new task or different task
  const handleOpenChange = (v: boolean) => {
    if (!v) onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const data: TaskCreateData = {
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      due_date: dueDate || undefined,
    };

    if (isEdit && task) {
      await updateTask.mutateAsync({ id: task.id, ...data });
    } else {
      await createTask.mutateAsync(data);
    }
    onClose();
  };

  const isPending = createTask.isPending || updateTask.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar Tarefa' : 'Nova Tarefa'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Título *</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Título da tarefa"
              required
              maxLength={500}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Descrição</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detalhes opcionais..."
              rows={3}
              maxLength={5000}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Prioridade</label>
              <Select value={priority} onValueChange={(v) => setPriority(v as TaskPriority)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Baixa</SelectItem>
                  <SelectItem value="med">Média</SelectItem>
                  <SelectItem value="high">Alta</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Prazo</label>
              <Input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending || !title.trim()}>
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

export default function Tarefas() {
  const [filterPriority, setFilterPriority] = useState<TaskPriority | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);

  const { data, isPending, isError, error } = useTasks(
    filterPriority ? { priority: filterPriority } : undefined
  );
  const updateStatus = useUpdateTaskStatus();
  const deleteTask = useDeleteTask();

  const tasks = data?.items ?? [];

  const handleEdit = (task: Task) => {
    setEditingTask(task);
    setDialogOpen(true);
  };

  const handleNewTask = () => {
    setEditingTask(null);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setEditingTask(null);
  };

  const handleDelete = (id: string) => {
    if (confirm('Excluir esta tarefa?')) {
      deleteTask.mutate(id);
    }
  };

  const handleStatusChange = (id: string, status: TaskStatus) => {
    updateStatus.mutate({ id, status });
  };

  // ── Loading state ──
  if (isPending && !data) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        <span>Carregando tarefas...</span>
      </div>
    );
  }

  // ── Error state ──
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-destructive">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm font-medium">Erro ao carregar tarefas</p>
        <p className="text-xs text-muted-foreground">{(error as Error)?.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ClipboardList className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Tarefas</h1>
            <p className="text-sm text-muted-foreground">
              {tasks.length} tarefa{tasks.length !== 1 ? 's' : ''} no total
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={filterPriority || 'all'}
            onValueChange={(v) => setFilterPriority(v === 'all' ? '' : v as TaskPriority)}
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="Prioridade" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              <SelectItem value="low">Baixa</SelectItem>
              <SelectItem value="med">Média</SelectItem>
              <SelectItem value="high">Alta</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleNewTask}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Tarefa
          </Button>
        </div>
      </div>

      {/* Kanban board */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {STATUS_COLUMNS.map(({ key, label, icon: Icon, color }) => {
          const columnTasks = tasks.filter((t) => t.status === key);

          return (
            <div key={key} className={`rounded-xl border ${color} p-4 space-y-3 min-h-[200px]`}>
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold text-foreground">{label}</h2>
                <span className="ml-auto text-xs text-muted-foreground bg-background/60 rounded-full px-2 py-0.5 border">
                  {columnTasks.length}
                </span>
              </div>

              {/* Empty column state */}
              {columnTasks.length === 0 && (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <p className="text-xs">Sem tarefas</p>
                </div>
              )}

              {/* Task cards */}
              {columnTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                  onStatusChange={handleStatusChange}
                />
              ))}
            </div>
          );
        })}
      </div>

      {/* Canceled tasks (collapsed section) */}
      {tasks.filter((t) => t.status === 'canceled').length > 0 && (
        <details className="group">
          <summary className="flex items-center gap-2 cursor-pointer text-sm text-muted-foreground hover:text-foreground transition-colors list-none">
            <XCircle className="h-4 w-4" />
            <span>
              {tasks.filter((t) => t.status === 'canceled').length} tarefa(s) cancelada(s)
            </span>
          </summary>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {tasks
              .filter((t) => t.status === 'canceled')
              .map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                  onStatusChange={handleStatusChange}
                />
              ))}
          </div>
        </details>
      )}

      {/* Create/Edit dialog */}
      {dialogOpen && (
        <TaskFormDialog
          open={dialogOpen}
          onClose={handleDialogClose}
          task={editingTask}
        />
      )}
    </div>
  );
}
