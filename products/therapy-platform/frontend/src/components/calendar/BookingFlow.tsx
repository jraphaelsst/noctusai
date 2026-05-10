import { useState, useMemo } from 'react';
import { Calendar, Clock, ChevronLeft, ChevronRight, Repeat, Check } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@noctusai/seed/components/ui/select';
import { Switch } from '@noctusai/seed/components/ui/switch';
import { Label } from '@noctusai/seed/components/ui/label';
import { Input } from '@noctusai/seed/components/ui/input';
import { cn } from '@/lib/utils';
import { useBookableSlots } from '@/hooks/useAvailability';
import { useCreateAppointment } from '@/hooks/useAppointments';
import type { BookableSlot, RecurringFrequency } from '@/types/scheduling';
import { RECURRING_FREQUENCY_LABELS } from '@/types/scheduling';

interface BookingFlowProps {
  therapistId: string;
  therapistName: string;
  sessionPrice?: number;
  sessionDuration?: number;
}

type Step = 'date' | 'time' | 'confirm';

function getMonthDays(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const startDow = (first.getDay() + 6) % 7; // Mon=0
  const days: (Date | null)[] = [];
  for (let i = 0; i < startDow; i++) days.push(null);
  for (let d = 1; d <= last.getDate(); d++) days.push(new Date(year, month, d));
  return days;
}

export function BookingFlow({
  therapistId,
  therapistName,
  sessionPrice,
  sessionDuration = 50,
}: BookingFlowProps) {
  const [step, setStep] = useState<Step>('date');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<BookableSlot | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(new Date());
  const [isRecurring, setIsRecurring] = useState(false);
  const [frequency, setFrequency] = useState<RecurringFrequency>('weekly');
  const [endCondition, setEndCondition] = useState<'indefinite' | 'after_n_occurrences' | 'on_date'>('indefinite');
  const [endAfterN, setEndAfterN] = useState(10);
  const [endOnDate, setEndOnDate] = useState('');

  const createAppointment = useCreateAppointment();

  // Fetch bookable slots for the displayed month
  const monthStart = useMemo(() => {
    const d = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
    return d.toISOString().split('T')[0];
  }, [calendarMonth]);

  const monthEnd = useMemo(() => {
    const d = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 0);
    return d.toISOString().split('T')[0];
  }, [calendarMonth]);

  const { data: bookableSlots = [] } = useBookableSlots(therapistId, monthStart, monthEnd);

  // Group slots by date
  const slotsByDate = useMemo(() => {
    const map: Record<string, BookableSlot[]> = {};
    for (const slot of bookableSlots) {
      if (!map[slot.date]) map[slot.date] = [];
      map[slot.date].push(slot);
    }
    return map;
  }, [bookableSlots]);

  const days = useMemo(
    () => getMonthDays(calendarMonth.getFullYear(), calendarMonth.getMonth()),
    [calendarMonth]
  );

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const slotsForSelectedDate = selectedDate ? slotsByDate[selectedDate] ?? [] : [];

  function handleConfirm() {
    if (!selectedSlot) return;
    const startDt = `${selectedSlot.date}T${selectedSlot.start_time}:00`;
    const endDt = `${selectedSlot.date}T${selectedSlot.end_time}:00`;

    createAppointment.mutate(
      {
        therapist_id: therapistId,
        scheduled_start: startDt,
        scheduled_end: endDt,
        recurring: isRecurring
          ? {
              frequency,
              end_condition: endCondition,
              end_after_n: endCondition === 'after_n_occurrences' ? endAfterN : undefined,
              end_on_date: endCondition === 'on_date' ? endOnDate : undefined,
            }
          : undefined,
      },
      {
        onSuccess: () => {
          setStep('date');
          setSelectedDate(null);
          setSelectedSlot(null);
          setIsRecurring(false);
        },
      }
    );
  }

  function prevMonth() {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  }

  function nextMonth() {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          Agendar com {therapistName}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Step 1: Select date */}
        {step === 'date' && (
          <div className="space-y-4">
            {/* Month navigation */}
            <div className="flex items-center justify-between">
              <Button variant="ghost" size="sm" onClick={prevMonth}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-medium">
                {calendarMonth.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
              </span>
              <Button variant="ghost" size="sm" onClick={nextMonth}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            {/* Calendar grid */}
            <div className="grid grid-cols-7 gap-1">
              {['S', 'T', 'Q', 'Q', 'S', 'S', 'D'].map((d, i) => (
                <div key={i} className="text-center text-xs font-medium text-muted-foreground py-1">
                  {d}
                </div>
              ))}
              {days.map((day, i) => {
                if (!day) return <div key={`empty-${i}`} />;

                const dateStr = day.toISOString().split('T')[0];
                const hasSlots = !!slotsByDate[dateStr]?.length;
                const isPast = day < today;
                const isSelected = dateStr === selectedDate;

                return (
                  <button
                    key={dateStr}
                    disabled={isPast || !hasSlots}
                    className={cn(
                      'h-9 w-full rounded-md text-sm transition-colors',
                      isPast && 'text-muted-foreground/30 cursor-not-allowed',
                      !isPast && !hasSlots && 'text-muted-foreground cursor-not-allowed',
                      !isPast && hasSlots && 'hover:bg-primary/10 cursor-pointer font-medium',
                      isSelected && 'bg-primary text-primary-foreground hover:bg-primary/90',
                      hasSlots && !isSelected && 'text-primary'
                    )}
                    onClick={() => {
                      setSelectedDate(dateStr);
                      setSelectedSlot(null);
                      setStep('time');
                    }}
                  >
                    {day.getDate()}
                  </button>
                );
              })}
            </div>

            {sessionPrice != null && (
              <p className="text-sm text-muted-foreground">
                Valor da sessao: <span className="font-medium">R$ {sessionPrice.toFixed(2)}</span>
                {' - '}{sessionDuration} minutos
              </p>
            )}
          </div>
        )}

        {/* Step 2: Select time */}
        {step === 'time' && selectedDate && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep('date')}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-medium">
                {new Date(selectedDate + 'T12:00:00').toLocaleDateString('pt-BR', {
                  weekday: 'long',
                  day: '2-digit',
                  month: 'long',
                })}
              </span>
            </div>

            {slotsForSelectedDate.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhum horario disponivel neste dia
              </p>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {slotsForSelectedDate.map((slot) => {
                  const isSelected = selectedSlot?.start_time === slot.start_time;
                  return (
                    <button
                      key={`${slot.date}-${slot.start_time}`}
                      className={cn(
                        'flex items-center justify-center gap-1 rounded-md border px-3 py-2 text-sm transition-colors',
                        isSelected
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'hover:bg-muted border-border'
                      )}
                      onClick={() => {
                        setSelectedSlot(slot);
                        setStep('confirm');
                      }}
                    >
                      <Clock className="h-3.5 w-3.5" />
                      {slot.start_time}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 'confirm' && selectedSlot && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep('time')}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-medium">Confirmar agendamento</span>
            </div>

            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Data</span>
                <span className="font-medium">
                  {new Date(selectedSlot.date + 'T12:00:00').toLocaleDateString('pt-BR', {
                    day: '2-digit',
                    month: 'long',
                    year: 'numeric',
                  })}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Horario</span>
                <span className="font-medium">
                  {selectedSlot.start_time} - {selectedSlot.end_time}
                </span>
              </div>
              {sessionPrice != null && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Valor</span>
                  <span className="font-medium">R$ {sessionPrice.toFixed(2)}</span>
                </div>
              )}
            </div>

            {/* Recurring toggle */}
            <div className="space-y-3 rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Repeat className="h-4 w-4 text-muted-foreground" />
                  <Label htmlFor="recurring" className="text-sm font-medium">
                    Tornar recorrente
                  </Label>
                </div>
                <Switch id="recurring" checked={isRecurring} onCheckedChange={setIsRecurring} />
              </div>

              {isRecurring && (
                <div className="space-y-3 pt-2 border-t">
                  <div>
                    <Label className="text-xs text-muted-foreground">Frequencia</Label>
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

                  <div>
                    <Label className="text-xs text-muted-foreground">Encerramento</Label>
                    <Select value={endCondition} onValueChange={(v) => setEndCondition(v as typeof endCondition)}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="indefinite">Indefinido</SelectItem>
                        <SelectItem value="after_n_occurrences">Apos N sessoes</SelectItem>
                        <SelectItem value="on_date">Ate uma data</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {endCondition === 'after_n_occurrences' && (
                    <div>
                      <Label className="text-xs text-muted-foreground">Numero de sessoes</Label>
                      <Input
                        type="number"
                        min={1}
                        max={100}
                        value={endAfterN}
                        onChange={(e) => setEndAfterN(Number(e.target.value))}
                        className="mt-1"
                      />
                    </div>
                  )}

                  {endCondition === 'on_date' && (
                    <div>
                      <Label className="text-xs text-muted-foreground">Data final</Label>
                      <Input
                        type="date"
                        value={endOnDate}
                        onChange={(e) => setEndOnDate(e.target.value)}
                        className="mt-1"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            <p className="text-xs text-muted-foreground">
              Cancelamentos com menos de 24 horas de antecedencia podem ser cobrados integralmente.
            </p>

            <Button
              className="w-full"
              onClick={handleConfirm}
              disabled={createAppointment.isPending}
            >
              {createAppointment.isPending ? (
                'Agendando...'
              ) : (
                <>
                  <Check className="h-4 w-4 mr-1" />
                  Confirmar agendamento
                </>
              )}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
