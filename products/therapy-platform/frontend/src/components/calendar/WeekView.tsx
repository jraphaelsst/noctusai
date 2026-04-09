import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { APPOINTMENT_STATUS_CONFIG, type Appointment, type AvailabilitySlot } from '@/types/scheduling';
import { RecurringBadge } from './RecurringBadge';

const HOUR_START = 8;
const HOUR_END = 21;
const HOURS = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);
const CELL_HEIGHT = 60; // px per hour

interface WeekViewProps {
  appointments: Appointment[];
  availabilitySlots?: AvailabilitySlot[];
  currentDate: Date;
  onDateChange: (date: Date) => void;
  onAppointmentClick?: (appointment: Appointment) => void;
  /** Field to display as the main label on each block */
  participantField?: 'patient_name' | 'therapist_name';
}

function getWeekDays(date: Date): Date[] {
  const d = new Date(date);
  const day = d.getDay();
  // Start week on Monday (day=1)
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((day + 6) % 7));
  monday.setHours(0, 0, 0, 0);

  return Array.from({ length: 7 }, (_, i) => {
    const dd = new Date(monday);
    dd.setDate(monday.getDate() + i);
    return dd;
  });
}

function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function getTopAndHeight(start: Date, end: Date) {
  const startMinutes = start.getHours() * 60 + start.getMinutes();
  const endMinutes = end.getHours() * 60 + end.getMinutes();
  const top = ((startMinutes - HOUR_START * 60) / 60) * CELL_HEIGHT;
  const height = Math.max(((endMinutes - startMinutes) / 60) * CELL_HEIGHT, 20);
  return { top, height };
}

const STATUS_BG: Record<string, string> = {
  waiting: 'bg-blue-200 border-blue-400 text-blue-900',
  in_progress: 'bg-green-200 border-green-400 text-green-900',
  paused: 'bg-yellow-200 border-yellow-400 text-yellow-900',
  completed: 'bg-gray-200 border-gray-400 text-gray-700',
  cancelled: 'bg-red-200 border-red-400 text-red-900',
  late_cancelled: 'bg-red-300 border-red-500 text-red-950',
  no_show: 'bg-red-400 border-red-600 text-white',
  payment_pending: 'bg-orange-200 border-orange-400 text-orange-900',
  payment_failed: 'bg-orange-300 border-orange-500 text-orange-950',
};

const DAY_LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];

export function WeekView({
  appointments,
  availabilitySlots = [],
  currentDate,
  onAppointmentClick,
  participantField = 'patient_name',
}: WeekViewProps) {
  const weekDays = useMemo(() => getWeekDays(currentDate), [currentDate]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Group appointments by day index
  const appointmentsByDay = useMemo(() => {
    const map: Record<number, Appointment[]> = {};
    for (let i = 0; i < 7; i++) map[i] = [];
    for (const apt of appointments) {
      const start = new Date(apt.scheduled_start);
      for (let i = 0; i < 7; i++) {
        if (isSameDay(start, weekDays[i])) {
          map[i].push(apt);
          break;
        }
      }
    }
    return map;
  }, [appointments, weekDays]);

  // Group availability by day index
  const availabilityByDay = useMemo(() => {
    const map: Record<number, AvailabilitySlot[]> = {};
    for (let i = 0; i < 7; i++) map[i] = [];
    for (const slot of availabilitySlots) {
      if (slot.is_blocked) continue;
      if (slot.is_recurring) {
        // Map day_of_week (0=Sun) to our columns (0=Mon)
        const colIndex = (slot.day_of_week + 6) % 7;
        if (colIndex >= 0 && colIndex < 7) map[colIndex].push(slot);
      } else if (slot.specific_date) {
        const slotDate = new Date(slot.specific_date);
        for (let i = 0; i < 7; i++) {
          if (isSameDay(slotDate, weekDays[i])) {
            map[i].push(slot);
            break;
          }
        }
      }
    }
    return map;
  }, [availabilitySlots, weekDays]);

  return (
    <div className="overflow-auto border rounded-lg bg-white">
      {/* Header row */}
      <div className="grid grid-cols-[60px_repeat(7,1fr)] border-b sticky top-0 bg-white z-10">
        <div className="p-2 text-xs text-muted-foreground border-r" />
        {weekDays.map((day, i) => {
          const isToday = isSameDay(day, today);
          return (
            <div
              key={i}
              className={cn(
                'p-2 text-center border-r last:border-r-0',
                isToday && 'bg-primary/5'
              )}
            >
              <div className="text-xs text-muted-foreground">{DAY_LABELS[i]}</div>
              <div
                className={cn(
                  'text-sm font-medium mt-0.5',
                  isToday && 'bg-primary text-primary-foreground rounded-full w-7 h-7 flex items-center justify-center mx-auto'
                )}
              >
                {day.getDate()}
              </div>
            </div>
          );
        })}
      </div>

      {/* Time grid */}
      <div className="grid grid-cols-[60px_repeat(7,1fr)]">
        {/* Hour labels */}
        <div className="relative">
          {HOURS.map((hour) => (
            <div
              key={hour}
              className="border-b border-r text-xs text-muted-foreground text-right pr-2 pt-1"
              style={{ height: CELL_HEIGHT }}
            >
              {String(hour).padStart(2, '0')}:00
            </div>
          ))}
        </div>

        {/* Day columns */}
        {weekDays.map((day, dayIndex) => {
          const isToday = isSameDay(day, today);
          const dayAppts = appointmentsByDay[dayIndex];
          const daySlots = availabilityByDay[dayIndex];

          return (
            <div
              key={dayIndex}
              className={cn('relative border-r last:border-r-0', isToday && 'bg-primary/[0.02]')}
            >
              {/* Hour grid lines */}
              {HOURS.map((hour) => (
                <div key={hour} className="border-b" style={{ height: CELL_HEIGHT }} />
              ))}

              {/* Availability background blocks */}
              {daySlots.map((slot) => {
                const [sh, sm] = slot.start_time.split(':').map(Number);
                const [eh, em] = slot.end_time.split(':').map(Number);
                const startDate = new Date(2000, 0, 1, sh, sm);
                const endDate = new Date(2000, 0, 1, eh, em);
                const { top, height } = getTopAndHeight(startDate, endDate);
                return (
                  <div
                    key={slot.id}
                    className="absolute inset-x-0 bg-green-50 border-l-2 border-green-300 opacity-50 pointer-events-none"
                    style={{ top, height }}
                  />
                );
              })}

              {/* Appointment blocks */}
              {dayAppts.map((apt) => {
                const start = new Date(apt.scheduled_start);
                const end = new Date(apt.scheduled_end);
                const { top, height } = getTopAndHeight(start, end);
                const statusClass = STATUS_BG[apt.status] ?? STATUS_BG.waiting;
                const name = apt[participantField] ?? 'Sessao';

                return (
                  <div
                    key={apt.id}
                    className={cn(
                      'absolute inset-x-1 rounded border-l-3 px-1.5 py-0.5 text-xs overflow-hidden cursor-pointer hover:opacity-90 transition-opacity',
                      statusClass
                    )}
                    style={{ top, height }}
                    onClick={() => onAppointmentClick?.(apt)}
                  >
                    <div className="font-medium truncate">{name}</div>
                    <div className="opacity-75">
                      {start.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    {apt.recurring_schedule_id && height > 35 && (
                      <RecurringBadge className="mt-0.5 text-[10px] px-1 py-0" />
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
