import { Clock, Video, X, Eye } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { cn } from '@/lib/utils';
import { APPOINTMENT_STATUS_CONFIG, type Appointment } from '@/types/scheduling';
import { RecurringBadge } from './RecurringBadge';

interface AppointmentCardProps {
  appointment: Appointment;
  /** Name to display — therapist name for patients, patient name for therapists */
  participantName: string;
  /** Role of the current viewer */
  viewerRole: 'terapeuta' | 'paciente';
  onCancel?: (id: string) => void;
  onViewDetail?: (appointment: Appointment) => void;
  onJoinSession?: (meetingLink: string) => void;
}

export function AppointmentCard({
  appointment,
  participantName,
  viewerRole,
  onCancel,
  onViewDetail,
  onJoinSession,
}: AppointmentCardProps) {
  const start = new Date(appointment.scheduled_start);
  const end = new Date(appointment.scheduled_end);
  const statusConfig = APPOINTMENT_STATUS_CONFIG[appointment.status];

  const timeStr = `${start.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  const durationMin = Math.round((end.getTime() - start.getTime()) / 60000);

  const isCancellable = ['waiting', 'payment_pending'].includes(appointment.status);
  const isJoinable =
    ['waiting', 'in_progress'].includes(appointment.status) && !!appointment.meeting_link;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-medium text-sm truncate">{participantName}</h4>
              <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', statusConfig.color)}>
                {statusConfig.label}
              </span>
              {appointment.recurring_schedule_id && <RecurringBadge />}
            </div>

            <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {timeStr}
              </span>
              <span>{durationMin} min</span>
            </div>

            {appointment.session_price_applied != null && (
              <p className="text-xs text-muted-foreground mt-1">
                R$ {appointment.session_price_applied.toFixed(2)}
              </p>
            )}
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {isJoinable && onJoinSession && (
              <Button
                size="sm"
                variant="default"
                className="h-8"
                onClick={() => onJoinSession(appointment.meeting_link!)}
              >
                <Video className="h-3.5 w-3.5 mr-1" />
                Entrar
              </Button>
            )}
            {onViewDetail && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8"
                onClick={() => onViewDetail(appointment)}
              >
                <Eye className="h-3.5 w-3.5" />
              </Button>
            )}
            {isCancellable && onCancel && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                onClick={() => onCancel(appointment.id)}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
