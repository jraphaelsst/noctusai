import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Clock,
  Plus,
  Trash2,
  CalendarOff,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import {
  useAvailabilitySlots,
  useCreateSlot,
  useDeleteSlot,
  useBlockDates,
} from '@/hooks/useAvailability';
import { DAY_OF_WEEK_LABELS, type AvailabilitySlot } from '@/types/scheduling';

export default function AvailabilitySettings() {
  const navigate = useNavigate();
  const { data: slots = [], isLoading } = useAvailabilitySlots();
  const createSlot = useCreateSlot();
  const deleteSlot = useDeleteSlot();
  const blockDates = useBlockDates();

  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newDayOfWeek, setNewDayOfWeek] = useState('1');
  const [newStartTime, setNewStartTime] = useState('08:00');
  const [newEndTime, setNewEndTime] = useState('09:00');

  const [blockStartDate, setBlockStartDate] = useState('');
  const [blockEndDate, setBlockEndDate] = useState('');

  // Group recurring slots by day
  const recurringByDay: Record<number, AvailabilitySlot[]> = {};
  const blockedSlots: AvailabilitySlot[] = [];

  for (const slot of slots) {
    if (slot.is_blocked) {
      blockedSlots.push(slot);
    } else if (slot.is_recurring) {
      if (!recurringByDay[slot.day_of_week]) recurringByDay[slot.day_of_week] = [];
      recurringByDay[slot.day_of_week].push(slot);
    }
  }

  function handleAddSlot() {
    createSlot.mutate(
      {
        day_of_week: Number(newDayOfWeek),
        start_time: newStartTime,
        end_time: newEndTime,
        is_recurring: true,
        is_blocked: false,
      },
      {
        onSuccess: () => {
          setShowAddDialog(false);
          setNewStartTime('08:00');
          setNewEndTime('09:00');
        },
      }
    );
  }

  function handleDeleteSlot(id: string) {
    deleteSlot.mutate(id);
  }

  function handleBlockDates() {
    if (!blockStartDate || !blockEndDate) return;
    blockDates.mutate(
      { start_date: blockStartDate, end_date: blockEndDate },
      {
        onSuccess: () => {
          setBlockStartDate('');
          setBlockEndDate('');
        },
      }
    );
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/therapist/agenda')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Clock className="h-6 w-6" />
            Configurar Disponibilidade
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Defina seus horarios de atendimento e bloqueie datas
          </p>
        </div>
      </div>

      {/* Recurring availability */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Horarios Recorrentes</CardTitle>
          <Button size="sm" onClick={() => setShowAddDialog(true)}>
            <Plus className="h-4 w-4 mr-1" />
            Adicionar
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Carregando...</p>
          ) : Object.keys(recurringByDay).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum horario configurado. Adicione seus horarios de atendimento.
            </p>
          ) : (
            <div className="space-y-4">
              {[0, 1, 2, 3, 4, 5, 6].map((dow) => {
                const daySlots = recurringByDay[dow];
                if (!daySlots?.length) return null;

                return (
                  <div key={dow}>
                    <h4 className="text-sm font-medium mb-2">{DAY_OF_WEEK_LABELS[dow]}</h4>
                    <div className="space-y-1.5">
                      {daySlots
                        .sort((a, b) => a.start_time.localeCompare(b.start_time))
                        .map((slot) => (
                          <div
                            key={slot.id}
                            className="flex items-center justify-between rounded-md border px-3 py-2"
                          >
                            <span className="text-sm flex items-center gap-2">
                              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                              {slot.start_time} - {slot.end_time}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-red-600 hover:text-red-700 hover:bg-red-50"
                              onClick={() => handleDeleteSlot(slot.id)}
                              disabled={deleteSlot.isPending}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Block dates */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <CalendarOff className="h-5 w-5" />
            Bloquear Datas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Bloqueie periodos em que voce nao estara disponivel (ferias, feriados, etc.)
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Label className="text-xs text-muted-foreground">Data inicio</Label>
              <Input
                type="date"
                value={blockStartDate}
                onChange={(e) => setBlockStartDate(e.target.value)}
                className="mt-1"
              />
            </div>
            <div className="flex-1">
              <Label className="text-xs text-muted-foreground">Data fim</Label>
              <Input
                type="date"
                value={blockEndDate}
                onChange={(e) => setBlockEndDate(e.target.value)}
                className="mt-1"
              />
            </div>
            <div className="flex items-end">
              <Button
                onClick={handleBlockDates}
                disabled={!blockStartDate || !blockEndDate || blockDates.isPending}
              >
                {blockDates.isPending ? 'Bloqueando...' : 'Bloquear'}
              </Button>
            </div>
          </div>

          {blockedSlots.length > 0 && (
            <>
              <Separator />
              <div className="space-y-1.5">
                <h4 className="text-sm font-medium">Periodos bloqueados</h4>
                {blockedSlots.map((slot) => (
                  <div
                    key={slot.id}
                    className="flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2"
                  >
                    <span className="text-sm text-red-800">
                      {slot.specific_date
                        ? new Date(slot.specific_date + 'T12:00:00').toLocaleDateString('pt-BR')
                        : `${slot.start_time} - ${slot.end_time}`}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-red-600 hover:text-red-700 hover:bg-red-100"
                      onClick={() => handleDeleteSlot(slot.id)}
                      disabled={deleteSlot.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Add slot dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar Horario</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Dia da semana</Label>
              <Select value={newDayOfWeek} onValueChange={setNewDayOfWeek}>
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
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm">Inicio</Label>
                <Input
                  type="time"
                  value={newStartTime}
                  onChange={(e) => setNewStartTime(e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-sm">Fim</Label>
                <Input
                  type="time"
                  value={newEndTime}
                  onChange={(e) => setNewEndTime(e.target.value)}
                  className="mt-1"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleAddSlot} disabled={createSlot.isPending}>
              {createSlot.isPending ? 'Adicionando...' : 'Adicionar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
