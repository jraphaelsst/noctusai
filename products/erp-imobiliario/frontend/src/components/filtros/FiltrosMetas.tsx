import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@noctusai/seed/components/ui/select";
import { Label } from "@noctusai/seed/components/ui/label";
import { Button } from "@noctusai/seed/components/ui/button";
import { X, Calendar as CalendarIcon, CheckSquare } from "lucide-react";
import { useFiltrosStore } from "@/store/filtrosStore";
import { useProfiles } from "@/hooks/useProfiles";
import { useUserRole } from "@/hooks/useUserRole";
import { Popover, PopoverContent, PopoverTrigger } from "@noctusai/seed/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import {
  format,
  startOfDay,
  endOfDay,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  startOfYear,
  endOfYear,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import { cn, getTodayAtMidnight } from "@/lib/utils";
import { NovaMetaModal } from "@/components/modals/NovaMetaModal";
import { useEffect } from "react";

interface FiltrosMetasProps {
  modoSelecao: boolean;
  setModoSelecao: (value: boolean) => void;
  hasMetas: boolean;
}

export function FiltrosMetas({ modoSelecao, setModoSelecao, hasMetas }: FiltrosMetasProps) {
  const {
    periodo,
    dataInicio,
    dataFim,
    filtroCorretor,
    filtroStatus,
    filtroTipo,
    filtroReferencia,
    filtroConclusaoPrazo,
    setPeriodo,
    setDataInicio,
    setDataFim,
    setFiltroCorretor,
    setFiltroStatus,
    setFiltroTipo,
    setFiltroReferencia,
    setFiltroConclusaoPrazo,
    limparFiltros,
  } = useFiltrosStore();

  const { data: profiles } = useProfiles();
  const { data: userRole } = useUserRole();
  const isAdmin = userRole === "admin";

  useEffect(() => {
    // Usa data sem horário para garantir comparações consistentes
    const hoje = getTodayAtMidnight();

    switch (periodo) {
      case "global":
        setDataInicio(undefined);
        setDataFim(undefined);
        break;
      case "diario":
        setDataInicio(startOfDay(hoje).toISOString());
        setDataFim(endOfDay(hoje).toISOString());
        break;
      case "semanal":
        setDataInicio(startOfWeek(hoje, { weekStartsOn: 0 }).toISOString());
        setDataFim(endOfWeek(hoje, { weekStartsOn: 0 }).toISOString());
        break;
      case "mensal":
        setDataInicio(startOfMonth(hoje).toISOString());
        setDataFim(endOfMonth(hoje).toISOString());
        break;
      case "anual":
        setDataInicio(startOfYear(hoje).toISOString());
        setDataFim(endOfYear(hoje).toISOString());
        break;
    }
  }, [periodo, setDataInicio, setDataFim]);

  return (
    <div className="flex flex-col gap-4 mb-6">
      <div className="flex flex-wrap gap-4 items-end">
        <div className="w-48">
          <Label htmlFor="periodo">Período</Label>
          <Select value={periodo} onValueChange={setPeriodo}>
            <SelectTrigger id="periodo">
              <SelectValue placeholder="Selecione o período" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="global">Global</SelectItem>
              <SelectItem value="diario">Diário</SelectItem>
              <SelectItem value="semanal">Semanal</SelectItem>
              <SelectItem value="mensal">Mensal</SelectItem>
              <SelectItem value="anual">Anual</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-48">
          <Label htmlFor="data-inicio">Data Início</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                id="data-inicio"
                variant="outline"
                className={cn("w-full justify-start text-left font-normal", !dataInicio && "text-muted-foreground")}
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {dataInicio ? format(new Date(dataInicio), "PPP", { locale: ptBR }) : <span>Selecione</span>}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={dataInicio ? new Date(dataInicio) : undefined}
                onSelect={(date) => setDataInicio(date?.toISOString())}
                initialFocus
                className={cn("p-3 pointer-events-auto")}
              />
            </PopoverContent>
          </Popover>
        </div>

        <div className="w-48">
          <Label htmlFor="data-fim">Data Fim</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                id="data-fim"
                variant="outline"
                className={cn("w-full justify-start text-left font-normal", !dataFim && "text-muted-foreground")}
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {dataFim ? format(new Date(dataFim), "PPP", { locale: ptBR }) : <span>Selecione</span>}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={dataFim ? new Date(dataFim) : undefined}
                onSelect={(date) => setDataFim(date?.toISOString())}
                initialFocus
                className={cn("p-3 pointer-events-auto")}
              />
            </PopoverContent>
          </Popover>
        </div>

        <div className="w-48">
          <Label htmlFor="referencia">Ref</Label>
          <input
            id="referencia"
            type="text"
            placeholder="MT0000"
            value={filtroReferencia === "todos" ? "" : filtroReferencia}
            onChange={(e) => {
              const value = e.target.value.toUpperCase();
              setFiltroReferencia(value || "todos");
            }}
            maxLength={6}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>

        {isAdmin && (
          <div className="w-48">
            <Label htmlFor="usuario">Usuário</Label>
            <Select value={filtroCorretor} onValueChange={setFiltroCorretor}>
              <SelectTrigger id="usuario">
                <SelectValue placeholder="Selecione o usuário" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                {profiles?.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id}>
                    {profile.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="w-48">
          <Label htmlFor="status">Status</Label>
          <Select value={filtroStatus} onValueChange={setFiltroStatus}>
            <SelectTrigger id="status">
              <SelectValue placeholder="Selecione o status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos</SelectItem>
              <SelectItem value="aberta">Aberta</SelectItem>
              <SelectItem value="concluida">Concluída</SelectItem>
              <SelectItem value="atrasada">Atrasada</SelectItem>
              <SelectItem value="no_prazo">No Prazo</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-48">
          <Label htmlFor="tipo">Periodicidade</Label>
          <Select value={filtroTipo} onValueChange={setFiltroTipo}>
            <SelectTrigger id="tipo">
              <SelectValue placeholder="Selecione a periodicidade" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos</SelectItem>
              <SelectItem value="diaria">Diária</SelectItem>
              <SelectItem value="semanal">Semanal</SelectItem>
              <SelectItem value="mensal">Mensal</SelectItem>
              <SelectItem value="anual">Anual</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="w-48">
          <Label htmlFor="conclusao-prazo">Conclusão</Label>
          <Select value={filtroConclusaoPrazo} onValueChange={setFiltroConclusaoPrazo}>
            <SelectTrigger id="conclusao-prazo">
              <SelectValue placeholder="Selecione a conclusão" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos</SelectItem>
              <SelectItem value="no_prazo">No Prazo</SelectItem>
              <SelectItem value="atrasada">Atrasada</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button variant="outline" onClick={limparFiltros}>
          <X className="w-4 h-4 mr-2" />
          Limpar Filtros
        </Button>
      </div>
    </div>
  );
}
