import { useState, useMemo } from 'react';
import {
  useEventos,
  useEventosHoje,
  useCreateEvento,
  useDeleteEvento,
  type TipoEvento,
  type Evento,
} from '@/hooks/useAgenda';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { CardListSkeleton } from '@/components/ui/page-skeleton';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@noctusai/seed/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import {
  CalendarDays,
  Plus,
  Clock,
  MapPin,
  User,
  Home,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Trash2,
} from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { AGENDA_TIPO_CONFIG } from '@/lib/constants';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const tipoStyle: Record<TipoEvento, { color: string; bg: string }> = {
  visita: { color: 'text-blue-700', bg: 'bg-blue-100 border-blue-300' },
  reuniao: { color: 'text-purple-700', bg: 'bg-purple-100 border-purple-300' },
  ligacao: { color: 'text-green-700', bg: 'bg-green-100 border-green-300' },
  vistoria: { color: 'text-orange-700', bg: 'bg-orange-100 border-orange-300' },
  assinatura: { color: 'text-red-700', bg: 'bg-red-100 border-red-300' },
  outro: { color: 'text-gray-700', bg: 'bg-gray-100 border-gray-300' },
};

const getTipoConfig = (tipo: TipoEvento) => ({
  label: AGENDA_TIPO_CONFIG[tipo]?.label || tipo,
  ...tipoStyle[tipo] || tipoStyle.outro,
});

const tipoBadgeVariant: Record<TipoEvento, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  visita: 'default',
  reuniao: 'secondary',
  ligacao: 'default',
  vistoria: 'secondary',
  assinatura: 'destructive',
  outro: 'outline',
};

const formatTime = (dateStr: string) => {
  const d = new Date(dateStr);
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const formatDateFull = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
};

function getWeekDays(baseDate: Date): Date[] {
  const day = baseDate.getDay();
  const monday = new Date(baseDate);
  monday.setDate(baseDate.getDate() - ((day + 6) % 7)); // Monday-based week
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    days.push(d);
  }
  return days;
}

function getMonthDays(year: number, month: number): (Date | null)[][] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startDayOfWeek = (firstDay.getDay() + 6) % 7; // Monday = 0

  const weeks: (Date | null)[][] = [];
  let currentWeek: (Date | null)[] = [];

  // Pad beginning
  for (let i = 0; i < startDayOfWeek; i++) {
    currentWeek.push(null);
  }

  for (let day = 1; day <= lastDay.getDate(); day++) {
    currentWeek.push(new Date(year, month, day));
    if (currentWeek.length === 7) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
  }

  // Pad end
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) {
      currentWeek.push(null);
    }
    weeks.push(currentWeek);
  }

  return weeks;
}

function isSameDay(d1: Date, d2: Date): boolean {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

const WEEKDAY_LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];
const TIME_SLOTS = Array.from({ length: 13 }, (_, i) => i + 7); // 7h - 19h

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Agenda() {
  const [view, setView] = useState<'semana' | 'mes'>('semana');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [dialogOpen, setDialogOpen] = useState(false);

  // Form state for creating events
  const [formData, setFormData] = useState({
    titulo: '',
    tipo: 'visita' as TipoEvento,
    data_inicio: '',
    hora_inicio: '09:00',
    data_fim: '',
    hora_fim: '10:00',
    local: '',
    cliente_id: '',
    imovel_id: '',
  });

  // Calculate date range for query
  const weekDays = useMemo(() => getWeekDays(currentDate), [currentDate]);
  const weekStart = weekDays[0].toISOString().split('T')[0];
  const weekEnd = weekDays[6].toISOString().split('T')[0];

  const monthStart = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
    .toISOString()
    .split('T')[0];
  const monthEnd = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0)
    .toISOString()
    .split('T')[0];

  const dateRange =
    view === 'semana'
      ? { data_inicio: weekStart, data_fim: weekEnd }
      : { data_inicio: monthStart, data_fim: monthEnd };

  const { data: eventosResult, isLoading } = useEventos(dateRange);
  const { data: eventosHoje } = useEventosHoje();
  const createEvento = useCreateEvento();
  const deleteEvento = useDeleteEvento();

  const eventos = eventosResult?.data || [];
  const todayEvents = eventosHoje || [];
  const today = new Date();

  // Navigation
  const navigatePrev = () => {
    const d = new Date(currentDate);
    if (view === 'semana') {
      d.setDate(d.getDate() - 7);
    } else {
      d.setMonth(d.getMonth() - 1);
    }
    setCurrentDate(d);
  };

  const navigateNext = () => {
    const d = new Date(currentDate);
    if (view === 'semana') {
      d.setDate(d.getDate() + 7);
    } else {
      d.setMonth(d.getMonth() + 1);
    }
    setCurrentDate(d);
  };

  const navigateToday = () => {
    setCurrentDate(new Date());
  };

  // Form handlers
  const resetForm = () => {
    setFormData({
      titulo: '',
      tipo: 'visita',
      data_inicio: '',
      hora_inicio: '09:00',
      data_fim: '',
      hora_fim: '10:00',
      local: '',
      cliente_id: '',
      imovel_id: '',
    });
  };

  const handleCreateEvento = () => {
    if (!formData.titulo || !formData.data_inicio) return;

    const dataInicio = `${formData.data_inicio}T${formData.hora_inicio}:00`;
    const dataFim = formData.data_fim
      ? `${formData.data_fim}T${formData.hora_fim}:00`
      : `${formData.data_inicio}T${formData.hora_fim}:00`;

    createEvento.mutate(
      {
        titulo: formData.titulo,
        tipo: formData.tipo,
        data_inicio: dataInicio,
        data_fim: dataFim,
        local: formData.local || undefined,
        cliente_id: formData.cliente_id || undefined,
        imovel_id: formData.imovel_id || undefined,
      },
      {
        onSuccess: () => {
          setDialogOpen(false);
          resetForm();
        },
      },
    );
  };

  // Get events for a specific day
  const getEventsForDay = (date: Date): Evento[] => {
    return eventos.filter((e) => {
      const eventDate = new Date(e.data_inicio);
      return isSameDay(eventDate, date);
    });
  };

  // Get event position in time grid
  const getEventStyle = (evento: Evento) => {
    const start = new Date(evento.data_inicio);
    const end = new Date(evento.data_fim);
    const startHour = start.getHours() + start.getMinutes() / 60;
    const endHour = end.getHours() + end.getMinutes() / 60;
    const top = ((startHour - 7) / 13) * 100;
    const height = Math.max(((endHour - startHour) / 13) * 100, 3);
    return { top: `${top}%`, height: `${height}%` };
  };

  // Month view data
  const monthWeeks = useMemo(
    () => getMonthDays(currentDate.getFullYear(), currentDate.getMonth()),
    [currentDate],
  );

  const monthLabel = currentDate.toLocaleDateString('pt-BR', {
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Agenda</h1>
          <p className="text-muted-foreground">Gerencie compromissos e visitas da equipe</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Novo Evento
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Criar Evento</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Titulo</label>
                <Input
                  placeholder="Ex: Visita ao apartamento..."
                  value={formData.titulo}
                  onChange={(e) => setFormData({ ...formData, titulo: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Tipo</label>
                <Select
                  value={formData.tipo}
                  onValueChange={(v) => setFormData({ ...formData, tipo: v as TipoEvento })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(tipoStyle) as TipoEvento[]).map((tipo) => {
                      const cfg = getTipoConfig(tipo);
                      return (
                      <SelectItem key={tipo} value={tipo}>
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${cfg.bg.split(' ')[0]}`} />
                          {cfg.label}
                        </div>
                      </SelectItem>
                    );
                    })}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Data Inicio</label>
                  <Input
                    type="date"
                    value={formData.data_inicio}
                    onChange={(e) => setFormData({ ...formData, data_inicio: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Hora Inicio</label>
                  <Input
                    type="time"
                    value={formData.hora_inicio}
                    onChange={(e) => setFormData({ ...formData, hora_inicio: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Data Fim (opcional)</label>
                  <Input
                    type="date"
                    value={formData.data_fim}
                    onChange={(e) => setFormData({ ...formData, data_fim: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Hora Fim</label>
                  <Input
                    type="time"
                    value={formData.hora_fim}
                    onChange={(e) => setFormData({ ...formData, hora_fim: e.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Local</label>
                <Input
                  placeholder="Endereco ou local do evento"
                  value={formData.local}
                  onChange={(e) => setFormData({ ...formData, local: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Cliente (ID - opcional)</label>
                  <Input
                    placeholder="UUID do cliente"
                    value={formData.cliente_id}
                    onChange={(e) => setFormData({ ...formData, cliente_id: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Imovel (ID - opcional)</label>
                  <Input
                    placeholder="UUID do imovel"
                    value={formData.imovel_id}
                    onChange={(e) => setFormData({ ...formData, imovel_id: e.target.value })}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setDialogOpen(false);
                    resetForm();
                  }}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleCreateEvento}
                  disabled={!formData.titulo || !formData.data_inicio || createEvento.isPending}
                >
                  {createEvento.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4 mr-2" />
                  )}
                  Criar Evento
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-6 lg:grid-cols-4">
        {/* Main Calendar Area */}
        <div className="lg:col-span-3 space-y-4">
          {/* Navigation & View Toggle */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="outline" size="icon" onClick={navigatePrev}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={navigateToday}>
                Hoje
              </Button>
              <Button variant="outline" size="icon" onClick={navigateNext}>
                <ChevronRight className="h-4 w-4" />
              </Button>
              <h2 className="text-lg font-semibold ml-2 capitalize">{monthLabel}</h2>
            </div>

            <Tabs value={view} onValueChange={(v) => setView(v as 'semana' | 'mes')}>
              <TabsList>
                <TabsTrigger value="semana">Semana</TabsTrigger>
                <TabsTrigger value="mes">Mes</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {isLoading && <CardListSkeleton count={3} />}

          {/* Week View */}
          {view === 'semana' && !isLoading && (
            <Card>
              <CardContent className="p-0 overflow-x-auto">
                <div className="min-w-[700px]">
                  {/* Week header */}
                  <div className="grid grid-cols-8 border-b">
                    <div className="p-2 text-xs text-muted-foreground text-center border-r">
                      Hora
                    </div>
                    {weekDays.map((day, i) => {
                      const isToday = isSameDay(day, today);
                      return (
                        <div
                          key={i}
                          className={`p-2 text-center border-r last:border-r-0 ${
                            isToday ? 'bg-primary/5' : ''
                          }`}
                        >
                          <div className="text-xs text-muted-foreground">{WEEKDAY_LABELS[i]}</div>
                          <div
                            className={`text-sm font-medium ${
                              isToday
                                ? 'bg-primary text-primary-foreground rounded-full w-7 h-7 flex items-center justify-center mx-auto'
                                : ''
                            }`}
                          >
                            {day.getDate()}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Time grid */}
                  <div className="relative">
                    <div className="grid grid-cols-8">
                      {/* Time labels */}
                      <div className="border-r">
                        {TIME_SLOTS.map((hour) => (
                          <div
                            key={hour}
                            className="h-14 border-b px-2 py-1 text-xs text-muted-foreground text-right"
                          >
                            {String(hour).padStart(2, '0')}:00
                          </div>
                        ))}
                      </div>

                      {/* Day columns */}
                      {weekDays.map((day, dayIndex) => {
                        const dayEvents = getEventsForDay(day);
                        const totalHeight = TIME_SLOTS.length * 56; // 56px = h-14

                        return (
                          <div
                            key={dayIndex}
                            className={`relative border-r last:border-r-0 ${
                              isSameDay(day, today) ? 'bg-primary/[0.02]' : ''
                            }`}
                            style={{ height: `${totalHeight}px` }}
                          >
                            {/* Grid lines */}
                            {TIME_SLOTS.map((hour) => (
                              <div key={hour} className="h-14 border-b" />
                            ))}

                            {/* Events overlay */}
                            {dayEvents.map((evento) => {
                              const style = getEventStyle(evento);
                              const cfg = getTipoConfig(evento.tipo);
                              return (
                                <div
                                  key={evento.id}
                                  className={`absolute left-0.5 right-0.5 rounded border px-1.5 py-0.5 overflow-hidden cursor-pointer group ${cfg.bg}`}
                                  style={style}
                                  title={`${evento.titulo} (${formatTime(evento.data_inicio)} - ${formatTime(evento.data_fim)})`}
                                >
                                  <div className={`text-[10px] font-medium truncate ${cfg.color}`}>
                                    {evento.titulo}
                                  </div>
                                  <div className="text-[9px] text-muted-foreground truncate">
                                    {formatTime(evento.data_inicio)}
                                  </div>
                                  <button
                                    className="absolute top-0.5 right-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      deleteEvento.mutate(evento.id);
                                    }}
                                  >
                                    <Trash2 className="h-3 w-3 text-destructive" />
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Month View */}
          {view === 'mes' && !isLoading && (
            <Card>
              <CardContent className="p-4">
                {/* Month header */}
                <div className="grid grid-cols-7 gap-1 mb-2">
                  {WEEKDAY_LABELS.map((label) => (
                    <div
                      key={label}
                      className="text-xs font-medium text-muted-foreground text-center py-1"
                    >
                      {label}
                    </div>
                  ))}
                </div>

                {/* Month grid */}
                <div className="space-y-1">
                  {monthWeeks.map((week, weekIndex) => (
                    <div key={weekIndex} className="grid grid-cols-7 gap-1">
                      {week.map((day, dayIndex) => {
                        if (!day) {
                          return (
                            <div
                              key={dayIndex}
                              className="min-h-[80px] rounded-md bg-muted/30"
                            />
                          );
                        }

                        const dayEvents = getEventsForDay(day);
                        const isToday = isSameDay(day, today);

                        return (
                          <div
                            key={dayIndex}
                            className={`min-h-[80px] rounded-md border p-1 ${
                              isToday ? 'border-primary bg-primary/5' : 'border-transparent hover:border-muted-foreground/20'
                            }`}
                          >
                            <div
                              className={`text-xs font-medium mb-1 ${
                                isToday ? 'text-primary' : 'text-muted-foreground'
                              }`}
                            >
                              {day.getDate()}
                            </div>
                            <div className="space-y-0.5">
                              {dayEvents.slice(0, 3).map((evento) => {
                                const cfg = getTipoConfig(evento.tipo);
                                return (
                                  <div
                                    key={evento.id}
                                    className={`text-[10px] px-1 py-0.5 rounded truncate ${cfg.bg} ${cfg.color}`}
                                    title={evento.titulo}
                                  >
                                    {evento.titulo}
                                  </div>
                                );
                              })}
                              {dayEvents.length > 3 && (
                                <div className="text-[10px] text-muted-foreground text-center">
                                  +{dayEvents.length - 3} mais
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Today's Events Sidebar */}
        <div className="lg:col-span-1">
          <Card className="sticky top-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <CalendarDays className="h-5 w-5" />
                Hoje
              </CardTitle>
              <p className="text-xs text-muted-foreground capitalize">
                {formatDateFull(today.toISOString())}
              </p>
            </CardHeader>
            <CardContent>
              {todayEvents.length === 0 ? (
                <div className="py-6 text-center text-muted-foreground">
                  <CalendarDays className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Nenhum evento hoje</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {todayEvents.map((evento) => {
                    const cfg = getTipoConfig(evento.tipo);
                    return (
                      <div
                        key={evento.id}
                        className={`p-3 rounded-lg border ${cfg.bg}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className={`text-sm font-medium truncate ${cfg.color}`}>
                              {evento.titulo}
                            </p>
                            <Badge
                              variant={tipoBadgeVariant[evento.tipo]}
                              className="mt-1 text-[10px]"
                            >
                              {cfg.label}
                            </Badge>
                          </div>
                        </div>

                        <div className="mt-2 space-y-1">
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            {formatTime(evento.data_inicio)} - {formatTime(evento.data_fim)}
                          </div>
                          {evento.local && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <MapPin className="h-3 w-3" />
                              <span className="truncate">{evento.local}</span>
                            </div>
                          )}
                          {evento.cliente_id && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <User className="h-3 w-3" />
                              <span className="truncate">Cliente vinculado</span>
                            </div>
                          )}
                          {evento.imovel_id && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Home className="h-3 w-3" />
                              <span className="truncate">Imovel vinculado</span>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
