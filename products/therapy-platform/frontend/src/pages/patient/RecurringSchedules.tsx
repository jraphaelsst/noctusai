import { useState } from 'react';
import {
  Repeat,
  Calendar,
  Clock,
  Square,
  SkipForward,
  MessageSquare,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@noctusai/seed/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  useRecurringSchedules,
  useEndRecurring,
  useSkipOccurrence,
  useModifyRecurring,
} from '@/hooks/useRecurring';
import {
  RECURRING_FREQUENCY_LABELS,
  RECURRING_STATUS_LABELS,
  DAY_OF_WEEK_LABELS,
  type RecurringSchedule,
  type RecurringFrequency,
} from '@/types/scheduling';

export default function PatientRecurringSchedules() {
  const [statusFilter, setStatusFilter] = useState<'active' | 'paused' | 'ended' | undefined>(undefined);
  const [changeDialog, setChangeDialog] = useState<RecurringSchedule | null>(null);

  const { data: schedulesData, isPending } = useRecurringSchedules(
    statusFilter ? { status: statusFilter } : undefined
  );
  const showSkeleton = isPending && !schedulesData;

  const endRecurring = useEndRecurring();
  const skipOccurrence = useSkipOccurrence();
  const modifyRecurring = useModifyRecurring();

  const schedules = schedulesData?.data ?? [];

  function handleSkipNext(schedule: RecurringSchedule) {
    const next = schedule.upcoming_appointments?.[0];
    if (!next) {
      toast.error('Nenhuma sessao proxima para pular');
      return;
    }
    const date = new Date(next.scheduled_start).toISOString().split('T')[0];
    skipOccurrence.mutate({ id: schedule.id, date });
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Repeat className="h-6 w-6" />
          Meus Agendamentos Recorrentes
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Gerencie suas sessoes recorrentes
        </p>
      </div>

      {/* Filter tabs */}
      <Tabs
        value={statusFilter ?? 'all'}
        onValueChange={(v) => setStatusFilter(v === 'all' ? undefined : (v as 'active' | 'paused' | 'ended'))}
      >
        <TabsList>
          <TabsTrigger value="all">Todos</TabsTrigger>
          <TabsTrigger value="active">Ativos</TabsTrigger>
          <TabsTrigger value="paused">Pausados</TabsTrigger>
          <TabsTrigger value="ended">Encerrados</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Schedules list */}
      {showSkeleton ? (
        <div className="text-center py-12 text-muted-foreground">Carregando...</div>
      ) : schedules.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Repeat className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">Nenhum agendamento recorrente</p>
          <p className="text-sm mt-1">
            Ao agendar uma sessao, marque a opcao &quot;Tornar recorrente&quot;
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {schedules.map((schedule) => (
            <PatientScheduleCard
              key={schedule.id}
              schedule={schedule}
              onSkipNext={() => handleSkipNext(schedule)}
              onEnd={(id) => endRecurring.mutate({ id })}
              onRequestChange={() => setChangeDialog(schedule)}
            />
          ))}
        </div>
      )}

      {/* Change request dialog */}
      {changeDialog && (
        <ChangeRequestDialog
          schedule={changeDialog}
          onClose={() => setChangeDialog(null)}
          onSubmit={(data) => {
            modifyRecurring.mutate(
              { id: changeDialog.id, ...data },
              { onSuccess: () => setChangeDialog(null) }
            );
          }}
          isSubmitting={modifyRecurring.isPending}
        />
      )}
    </div>
  );
}

// ── Patient schedule card ──────────────────────────────────────

interface PatientScheduleCardProps {
  schedule: RecurringSchedule;
  onSkipNext: () => void;
  onEnd: (id: string) => void;
  onRequestChange: () => void;
}

function PatientScheduleCard({
  schedule,
  onSkipNext,
  onEnd,
  onRequestChange,
}: PatientScheduleCardProps) {
  const statusConfig = RECURRING_STATUS_LABELS[schedule.status];
  const frequencyLabel = RECURRING_FREQUENCY_LABELS[schedule.frequency];
  const dayLabel = DAY_OF_WEEK_LABELS[schedule.day_of_week];
  const nextSession = schedule.upcoming_appointments?.[0];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-medium truncate">
                {schedule.therapist_name ?? 'Terapeuta'}
              </h4>
              <Badge variant="secondary" className={cn(statusConfig.color)}>
                {statusConfig.label}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Repeat className="h-3.5 w-3.5" />
                {frequencyLabel}
              </div>
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Calendar className="h-3.5 w-3.5" />
                {dayLabel}
              </div>
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                {schedule.start_time} ({schedule.duration_minutes} min)
              </div>
              <div className="text-muted-foreground">
                {schedule.total_completed} realizadas
              </div>
            </div>

            {nextSession && (
              <p className="text-xs text-muted-foreground">
                Proxima:{' '}
                {new Date(nextSession.scheduled_start).toLocaleDateString('pt-BR', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                })}
              </p>
            )}
          </div>

          {schedule.status !== 'ended' && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {schedule.status === 'active' && (
                  <DropdownMenuItem onClick={onSkipNext}>
                    <SkipForward className="h-4 w-4 mr-2" />
                    Pular proxima
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={onRequestChange}>
                  <MessageSquare className="h-4 w-4 mr-2" />
                  Solicitar alteracao
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onEnd(schedule.id)}
                  className="text-red-600"
                >
                  <Square className="h-4 w-4 mr-2" />
                  Encerrar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Change request dialog ──────────────────────────────────────

function ChangeRequestDialog({
  schedule,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  schedule: RecurringSchedule;
  onClose: () => void;
  onSubmit: (data: Partial<RecurringSchedule>) => void;
  isSubmitting: boolean;
}) {
  const [dayOfWeek, setDayOfWeek] = useState(String(schedule.day_of_week));
  const [startTime, setStartTime] = useState(schedule.start_time);
  const [frequency, setFrequency] = useState<RecurringFrequency>(schedule.frequency);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Solicitar Alteracao</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-sm">Dia da semana</Label>
            <Select value={dayOfWeek} onValueChange={setDayOfWeek}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAY_OF_WEEK_LABELS.map((label, i) => (
                  <SelectItem key={i} value={String(i)}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-sm">Horario</Label>
            <Input
              type="time"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-sm">Frequencia</Label>
            <Select value={frequency} onValueChange={(v) => setFrequency(v as RecurringFrequency)}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(RECURRING_FREQUENCY_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            onClick={() =>
              onSubmit({
                day_of_week: Number(dayOfWeek),
                start_time: startTime,
                frequency,
              })
            }
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Enviando...' : 'Enviar solicitacao'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
