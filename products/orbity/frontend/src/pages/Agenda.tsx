/**
 * Agenda page — events grouped by day (list view), create/edit/delete,
 * and GCal sync action.
 *
 * Full four states: loading, empty, error, success.
 * GCal sync: calls POST /api/agenda/events/{id}/sync-gcal via useSyncGcal().
 *
 * status_pagina key: "agenda"  ← tech-lead must seed this row.
 */
import { useState } from 'react';
import {
  useAgendaEvents,
  useCreateAgendaEvent,
  useUpdateAgendaEvent,
  useDeleteAgendaEvent,
  useSyncGcal,
  type AgendaEvent,
  type EventType,
  type AgendaEventCreateData,
} from '@/hooks/useAgenda';
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
  CalendarDays,
  Plus,
  Loader2,
  AlertCircle,
  Trash2,
  Pencil,
  MapPin,
  Clock,
  RefreshCw,
  CheckCircle2,
  CalendarCheck,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EVENT_TYPE_CONFIG: Record<EventType, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  meeting: { label: 'Reunião', variant: 'default' },
  call: { label: 'Ligação', variant: 'secondary' },
  visit: { label: 'Visita', variant: 'outline' },
  other: { label: 'Outro', variant: 'secondary' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(isoStr: string): string {
  return new Date(isoStr).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDateLabel(isoStr: string): string {
  return new Date(isoStr).toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function groupByDay(events: AgendaEvent[]): Map<string, AgendaEvent[]> {
  const map = new Map<string, AgendaEvent[]>();
  const sorted = [...events].sort(
    (a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
  );
  for (const ev of sorted) {
    const dayKey = ev.starts_at.slice(0, 10); // YYYY-MM-DD
    if (!map.has(dayKey)) map.set(dayKey, []);
    map.get(dayKey)!.push(ev);
  }
  return map;
}

// ---------------------------------------------------------------------------
// Event card
// ---------------------------------------------------------------------------

interface EventCardProps {
  event: AgendaEvent;
  onEdit: (event: AgendaEvent) => void;
  onDelete: (id: string) => void;
  onSyncGcal: (id: string) => void;
  isSyncing: boolean;
}

function EventCard({ event, onEdit, onDelete, onSyncGcal, isSyncing }: EventCardProps) {
  const typeCfg = EVENT_TYPE_CONFIG[event.event_type as EventType] ?? EVENT_TYPE_CONFIG.other;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{event.title}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <Badge variant={typeCfg.variant} className="text-xs">
              {typeCfg.label}
            </Badge>
            {event.gcal_event_id && (
              <span className="flex items-center gap-1 text-xs text-green-600">
                <CheckCircle2 className="h-3 w-3" />
                GCal
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={() => onSyncGcal(event.id)}
            disabled={isSyncing}
            className="text-muted-foreground hover:text-blue-600 transition-colors p-1 rounded"
            aria-label="Sincronizar com Google Calendar"
            title="Sincronizar com Google Calendar"
          >
            {isSyncing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <CalendarCheck className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={() => onEdit(event)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
            aria-label="Editar evento"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(event.id)}
            className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
            aria-label="Excluir evento"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatTime(event.starts_at)} – {formatTime(event.ends_at)}
        </span>
        {event.location && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {event.location}
          </span>
        )}
      </div>

      {event.description && (
        <p className="text-xs text-muted-foreground line-clamp-2">{event.description}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event form dialog
// ---------------------------------------------------------------------------

interface EventFormDialogProps {
  open: boolean;
  onClose: () => void;
  event?: AgendaEvent | null;
}

function EventFormDialog({ open, onClose, event }: EventFormDialogProps) {
  const isEdit = !!event;
  const createEvent = useCreateAgendaEvent();
  const updateEvent = useUpdateAgendaEvent();

  // Derive datetime-local strings for the form inputs
  const toLocalInput = (isoStr: string | undefined) => {
    if (!isoStr) return '';
    // datetime-local expects "YYYY-MM-DDTHH:mm"
    return isoStr.slice(0, 16);
  };

  const [title, setTitle] = useState(event?.title ?? '');
  const [description, setDescription] = useState(event?.description ?? '');
  const [eventType, setEventType] = useState<EventType>(event?.event_type as EventType ?? 'other');
  const [startsAt, setStartsAt] = useState(toLocalInput(event?.starts_at));
  const [endsAt, setEndsAt] = useState(toLocalInput(event?.ends_at));
  const [location, setLocation] = useState(event?.location ?? '');

  const handleOpenChange = (v: boolean) => {
    if (!v) onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const data: AgendaEventCreateData = {
      title: title.trim(),
      description: description.trim() || undefined,
      event_type: eventType,
      starts_at: new Date(startsAt).toISOString(),
      ends_at: new Date(endsAt).toISOString(),
      location: location.trim() || undefined,
    };

    if (isEdit && event) {
      await updateEvent.mutateAsync({ id: event.id, ...data });
    } else {
      await createEvent.mutateAsync(data);
    }
    onClose();
  };

  const isPending = createEvent.isPending || updateEvent.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar Evento' : 'Novo Evento'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Título *</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Título do evento"
              required
              maxLength={500}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Tipo</label>
            <Select value={eventType} onValueChange={(v) => setEventType(v as EventType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="meeting">Reunião</SelectItem>
                <SelectItem value="call">Ligação</SelectItem>
                <SelectItem value="visit">Visita</SelectItem>
                <SelectItem value="other">Outro</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Início *</label>
              <Input
                type="datetime-local"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">Fim *</label>
              <Input
                type="datetime-local"
                value={endsAt}
                onChange={(e) => setEndsAt(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Local</label>
            <Input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Endereço ou link"
              maxLength={500}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Descrição</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Notas do evento..."
              rows={3}
              maxLength={5000}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending || !title.trim() || !startsAt || !endsAt}>
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

export default function Agenda() {
  const [filterType, setFilterType] = useState<EventType | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<AgendaEvent | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useAgendaEvents(
    filterType ? { event_type: filterType } : undefined
  );
  const deleteEvent = useDeleteAgendaEvent();
  const syncGcal = useSyncGcal();

  const events = data?.items ?? [];
  const grouped = groupByDay(events);

  const handleEdit = (event: AgendaEvent) => {
    setEditingEvent(event);
    setDialogOpen(true);
  };

  const handleNewEvent = () => {
    setEditingEvent(null);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setEditingEvent(null);
  };

  const handleDelete = (id: string) => {
    if (confirm('Excluir este evento?')) {
      deleteEvent.mutate(id);
    }
  };

  const handleSyncGcal = (id: string) => {
    setSyncingId(id);
    syncGcal.mutate(id, {
      onSettled: () => setSyncingId(null),
    });
  };

  // ── Loading state ──
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        <span>Carregando agenda...</span>
      </div>
    );
  }

  // ── Error state ──
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-destructive">
        <AlertCircle className="h-8 w-8" />
        <p className="text-sm font-medium">Erro ao carregar agenda</p>
        <p className="text-xs text-muted-foreground">{(error as Error)?.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <CalendarDays className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Agenda</h1>
            <p className="text-sm text-muted-foreground">
              {events.length} evento{events.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={filterType || 'all'}
            onValueChange={(v) => setFilterType(v === 'all' ? '' : v as EventType)}
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="Tipo" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="meeting">Reunião</SelectItem>
              <SelectItem value="call">Ligação</SelectItem>
              <SelectItem value="visit">Visita</SelectItem>
              <SelectItem value="other">Outro</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleNewEvent}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Evento
          </Button>
        </div>
      </div>

      {/* Empty state */}
      {events.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
          <CalendarDays className="h-12 w-12 opacity-40" />
          <p className="text-sm font-medium">Nenhum evento encontrado</p>
          <p className="text-xs">Crie o primeiro evento clicando em "Novo Evento"</p>
        </div>
      )}

      {/* Events grouped by day */}
      {grouped.size > 0 && (
        <div className="space-y-6">
          {Array.from(grouped.entries()).map(([day, dayEvents]) => (
            <div key={day} className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-border" />
                <h2 className="text-sm font-semibold text-foreground whitespace-nowrap capitalize">
                  {formatDateLabel(day + 'T12:00:00')}
                </h2>
                <div className="h-px flex-1 bg-border" />
              </div>
              <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
                {dayEvents.map((ev) => (
                  <EventCard
                    key={ev.id}
                    event={ev}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                    onSyncGcal={handleSyncGcal}
                    isSyncing={syncingId === ev.id}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit dialog */}
      {dialogOpen && (
        <EventFormDialog
          open={dialogOpen}
          onClose={handleDialogClose}
          event={editingEvent}
        />
      )}
    </div>
  );
}
