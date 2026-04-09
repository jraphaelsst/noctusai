import { useMemo } from 'react';
import { type Appointment } from '@/types/scheduling';
import { AppointmentCard } from './AppointmentCard';

interface AgendaViewProps {
  appointments: Appointment[];
  viewerRole: 'terapeuta' | 'paciente';
  onCancel?: (id: string) => void;
  onViewDetail?: (appointment: Appointment) => void;
  onJoinSession?: (meetingLink: string) => void;
}

function formatDateHeader(date: Date): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);

  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  const dayName = d.toLocaleDateString('pt-BR', { weekday: 'long' });
  const formatted = d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });

  if (diff === 0) return `Hoje - ${formatted}`;
  if (diff === 1) return `Amanha - ${formatted}`;
  if (diff === -1) return `Ontem - ${formatted}`;
  return `${dayName.charAt(0).toUpperCase() + dayName.slice(1)} - ${formatted}`;
}

export function AgendaView({
  appointments,
  viewerRole,
  onCancel,
  onViewDetail,
  onJoinSession,
}: AgendaViewProps) {
  // Group by date, sorted ascending
  const grouped = useMemo(() => {
    const sorted = [...appointments].sort(
      (a, b) => new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime()
    );

    const groups: { date: Date; items: Appointment[] }[] = [];
    for (const apt of sorted) {
      const aptDate = new Date(apt.scheduled_start);
      aptDate.setHours(0, 0, 0, 0);

      const lastGroup = groups[groups.length - 1];
      if (lastGroup && lastGroup.date.getTime() === aptDate.getTime()) {
        lastGroup.items.push(apt);
      } else {
        groups.push({ date: aptDate, items: [apt] });
      }
    }
    return groups;
  }, [appointments]);

  if (appointments.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-lg">Nenhum agendamento encontrado</p>
        <p className="text-sm mt-1">Seus agendamentos aparecerao aqui</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {grouped.map((group) => (
        <div key={group.date.toISOString()}>
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            {formatDateHeader(group.date)}
          </h3>
          <div className="space-y-2">
            {group.items.map((apt) => (
              <AppointmentCard
                key={apt.id}
                appointment={apt}
                participantName={
                  viewerRole === 'terapeuta'
                    ? apt.patient_name ?? 'Paciente'
                    : apt.therapist_name ?? 'Terapeuta'
                }
                viewerRole={viewerRole}
                onCancel={onCancel}
                onViewDetail={onViewDetail}
                onJoinSession={onJoinSession}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
