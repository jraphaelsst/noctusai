import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { type Appointment } from '@/types/scheduling';

const DAY_HEADERS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];

interface MonthViewProps {
  appointments: Appointment[];
  currentDate: Date;
  onDayClick?: (date: Date) => void;
}

function getMonthGrid(date: Date): (Date | null)[][] {
  const year = date.getFullYear();
  const month = date.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);

  // Monday-based: 0=Mon, 6=Sun
  const startDow = (firstDay.getDay() + 6) % 7;
  const totalDays = lastDay.getDate();

  const weeks: (Date | null)[][] = [];
  let week: (Date | null)[] = [];

  // Leading nulls
  for (let i = 0; i < startDow; i++) week.push(null);

  for (let d = 1; d <= totalDays; d++) {
    week.push(new Date(year, month, d));
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }

  // Trailing nulls
  if (week.length > 0) {
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }

  return weeks;
}

function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

const STATUS_DOT: Record<string, string> = {
  waiting: 'bg-blue-500',
  in_progress: 'bg-green-500',
  paused: 'bg-yellow-500',
  completed: 'bg-gray-400',
  cancelled: 'bg-red-500',
  late_cancelled: 'bg-red-600',
  no_show: 'bg-red-700',
  payment_pending: 'bg-orange-500',
  payment_failed: 'bg-orange-600',
};

export function MonthView({ appointments, currentDate, onDayClick }: MonthViewProps) {
  const weeks = useMemo(() => getMonthGrid(currentDate), [currentDate]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Group appointments by date key
  const appointmentsByDate = useMemo(() => {
    const map: Record<string, Appointment[]> = {};
    for (const apt of appointments) {
      const d = new Date(apt.scheduled_start);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      if (!map[key]) map[key] = [];
      map[key].push(apt);
    }
    return map;
  }, [appointments]);

  return (
    <div className="border rounded-lg bg-white overflow-hidden">
      {/* Day headers */}
      <div className="grid grid-cols-7 border-b">
        {DAY_HEADERS.map((label) => (
          <div key={label} className="p-2 text-center text-xs font-medium text-muted-foreground border-r last:border-r-0">
            {label}
          </div>
        ))}
      </div>

      {/* Weeks */}
      {weeks.map((week, wi) => (
        <div key={wi} className="grid grid-cols-7 border-b last:border-b-0">
          {week.map((day, di) => {
            if (!day) {
              return <div key={di} className="min-h-[80px] bg-muted/30 border-r last:border-r-0" />;
            }

            const isToday = isSameDay(day, today);
            const isCurrentMonth = day.getMonth() === currentDate.getMonth();
            const dateKey = `${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`;
            const dayAppts = appointmentsByDate[dateKey] ?? [];

            return (
              <div
                key={di}
                className={cn(
                  'min-h-[80px] p-1.5 border-r last:border-r-0 cursor-pointer hover:bg-muted/40 transition-colors',
                  !isCurrentMonth && 'bg-muted/20 text-muted-foreground'
                )}
                onClick={() => onDayClick?.(day)}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={cn(
                      'text-sm',
                      isToday && 'bg-primary text-primary-foreground rounded-full w-6 h-6 flex items-center justify-center font-medium'
                    )}
                  >
                    {day.getDate()}
                  </span>
                  {dayAppts.length > 0 && (
                    <span className="text-xs text-muted-foreground bg-muted rounded-full px-1.5 py-0.5">
                      {dayAppts.length}
                    </span>
                  )}
                </div>

                {/* Status dots (max 4 visible) */}
                <div className="flex flex-wrap gap-0.5 mt-1">
                  {dayAppts.slice(0, 4).map((apt) => (
                    <div
                      key={apt.id}
                      className={cn('w-2 h-2 rounded-full', STATUS_DOT[apt.status] ?? 'bg-gray-400')}
                      title={apt.patient_name ?? apt.therapist_name ?? 'Sessao'}
                    />
                  ))}
                  {dayAppts.length > 4 && (
                    <span className="text-[10px] text-muted-foreground">+{dayAppts.length - 4}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
