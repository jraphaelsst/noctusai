import { useState } from 'react';
import {
  Repeat,
  Calendar,
  Clock,
  Pause,
  Play,
  Square,
  CheckCircle2,
  XCircle,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@noctusai/seed/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@noctusai/seed/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import {
  useRecurringSchedules,
  usePauseRecurring,
  useResumeRecurring,
  useEndRecurring,
  useApproveRecurring,
  useDenyRecurring,
} from '@/hooks/useRecurring';
import {
  RECURRING_FREQUENCY_LABELS,
  RECURRING_STATUS_LABELS,
  DAY_OF_WEEK_LABELS,
  type RecurringSchedule,
} from '@/types/scheduling';

export default function TherapistRecurringSchedules() {
  const [statusFilter, setStatusFilter] = useState<'active' | 'paused' | 'ended' | undefined>(undefined);

  const { data: schedulesData, isPending } = useRecurringSchedules(
    statusFilter ? { status: statusFilter } : undefined
  );
  const showSkeleton = isPending && !schedulesData;

  const pauseRecurring = usePauseRecurring();
  const resumeRecurring = useResumeRecurring();
  const endRecurring = useEndRecurring();
  const approveRecurring = useApproveRecurring();
  const denyRecurring = useDenyRecurring();

  const schedules = schedulesData?.data ?? [];

  // Separate pending approval requests (patient-initiated that need therapist approval)
  // Convention: schedules with status 'active' and total_completed === 0 might be pending
  // In practice, the backend would have a 'pending' status — for now we show all

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Repeat className="h-6 w-6" />
          Agendamentos Recorrentes
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Gerencie as sessoes recorrentes com seus pacientes
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
          <p className="text-sm mt-1">Agendamentos recorrentes aparecerao aqui</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {schedules.map((schedule) => (
            <RecurringScheduleCard
              key={schedule.id}
              schedule={schedule}
              onPause={(id) => pauseRecurring.mutate({ id })}
              onResume={(id) => resumeRecurring.mutate({ id })}
              onEnd={(id) => endRecurring.mutate({ id })}
              onApprove={(id) => approveRecurring.mutate({ id })}
              onDeny={(id) => denyRecurring.mutate({ id })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Schedule card ──────────────────────────────────────────────

interface RecurringScheduleCardProps {
  schedule: RecurringSchedule;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onEnd: (id: string) => void;
  onApprove: (id: string) => void;
  onDeny: (id: string) => void;
}

function RecurringScheduleCard({
  schedule,
  onPause,
  onResume,
  onEnd,
  onApprove,
  onDeny,
}: RecurringScheduleCardProps) {
  const statusConfig = RECURRING_STATUS_LABELS[schedule.status];
  const frequencyLabel = RECURRING_FREQUENCY_LABELS[schedule.frequency];
  const dayLabel = DAY_OF_WEEK_LABELS[schedule.day_of_week];

  // Next session from upcoming_appointments
  const nextSession = schedule.upcoming_appointments?.[0];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-medium truncate">
                {schedule.patient_name ?? 'Paciente'}
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
                {schedule.total_absences > 0 && (
                  <span className="text-red-600 ml-1">
                    ({schedule.total_absences} faltas)
                  </span>
                )}
              </div>
            </div>

            {nextSession && (
              <p className="text-xs text-muted-foreground">
                Proxima sessao:{' '}
                {new Date(nextSession.scheduled_start).toLocaleDateString('pt-BR', {
                  day: '2-digit',
                  month: 'short',
                })}
              </p>
            )}
          </div>

          {/* Actions menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {schedule.status === 'active' && (
                <>
                  <DropdownMenuItem onClick={() => onPause(schedule.id)}>
                    <Pause className="h-4 w-4 mr-2" />
                    Pausar
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => onEnd(schedule.id)}
                    className="text-red-600"
                  >
                    <Square className="h-4 w-4 mr-2" />
                    Encerrar
                  </DropdownMenuItem>
                </>
              )}
              {schedule.status === 'paused' && (
                <>
                  <DropdownMenuItem onClick={() => onResume(schedule.id)}>
                    <Play className="h-4 w-4 mr-2" />
                    Retomar
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => onEnd(schedule.id)}
                    className="text-red-600"
                  >
                    <Square className="h-4 w-4 mr-2" />
                    Encerrar
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardContent>
    </Card>
  );
}
