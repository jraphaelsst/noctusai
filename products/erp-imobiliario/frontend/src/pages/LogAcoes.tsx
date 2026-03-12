import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Calendar as CalendarIcon, Filter, User, X } from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { useActionLogs } from "@/hooks/useActionLog";
import { formatDate } from "@/lib/utils";
import { useProfiles } from "@/hooks/useProfiles";
import { useUserRole } from "@/hooks/useUserRole";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ACAO_LABELS } from "@/lib/constants";

const entidadeLabels: Record<string, string> = {
  meta: "Meta",
  cliente: "Cliente",
  usuario: "Usuário",
  atividade: "Atividade",
  config_meta: "Configuração de Meta",
  auth: "Autenticação",
};

const acaoColors: Record<string, string> = {
  criar: "bg-success/10 text-success-foreground border-success/20",
  editar: "bg-info/10 text-info-foreground border-info/20",
  excluir: "bg-destructive/10 text-destructive-foreground border-destructive/20",
  concluir: "bg-primary/10 text-primary-foreground border-primary/20",
  arquivar: "bg-warning/10 text-warning-foreground border-warning/20",
  desarquivar: "bg-secondary/10 text-secondary-foreground border-secondary/20",
  mover: "bg-accent/10 text-accent-foreground border-accent/20",
  login: "bg-muted/10 text-muted-foreground border-muted/20",
  logout: "bg-muted/10 text-muted-foreground border-muted/20",
};

export default function LogAcoes() {
  const [filtroUsuario, setFiltroUsuario] = useState<string>("todos");
  const [dataInicio, setDataInicio] = useState<Date | undefined>(undefined);
  const [dataFim, setDataFim] = useState<Date | undefined>(undefined);

  const { data: userRole } = useUserRole();
  const { data: profiles } = useProfiles();
  const canViewAll = userRole === "admin";

  const { data: logs, isLoading } = useActionLogs(
    filtroUsuario !== "todos" ? filtroUsuario : undefined,
    dataInicio,
    dataFim
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Log de Ações</h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe todas as ações realizadas na plataforma
        </p>
      </div>

      {/* Filtros */}
      <Card className="border-0 bg-accent/30 shadow-none">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground uppercase tracking-wider">
            <Filter className="h-3.5 w-3.5" />
            Filtros
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {canViewAll && (
              <div className="flex-1 min-w-[200px] space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Usuário</Label>
                <div className="relative">
                  <Select value={filtroUsuario} onValueChange={setFiltroUsuario}>
                    <SelectTrigger className={cn("h-9 border-muted-foreground/20", filtroUsuario === "todos" && "text-muted-foreground")}>
                      <User className="mr-2 h-4 w-4" />
                      <SelectValue placeholder="Todos os usuários" />
                    </SelectTrigger>
                    <SelectContent className="bg-background">
                      <SelectItem value="todos">Todos os usuários</SelectItem>
                      {profiles?.map((profile) => (
                        <SelectItem key={profile.id} value={profile.id}>
                          {profile.nome}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {filtroUsuario !== "todos" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFiltroUsuario("todos");
                      }}
                      className="absolute right-8 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                    >
                      <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="flex-1 min-w-[200px] space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Data Início</Label>
              <div className="relative">
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        "w-full h-9 justify-start text-left font-normal border-muted-foreground/20",
                        !dataInicio && "text-muted-foreground"
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dataInicio ? format(dataInicio, "PPP", { locale: ptBR }) : <span>Selecione</span>}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={dataInicio}
                      onSelect={setDataInicio}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
                {dataInicio && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDataInicio(undefined);
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                  >
                    <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 min-w-[200px] space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Data Fim</Label>
              <div className="relative">
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        "w-full h-9 justify-start text-left font-normal border-muted-foreground/20",
                        !dataFim && "text-muted-foreground"
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dataFim ? format(dataFim, "PPP", { locale: ptBR }) : <span>Selecione</span>}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={dataFim}
                      onSelect={setDataFim}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
                {dataFim && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDataFim(undefined);
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                  >
                    <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lista de Logs */}
      <Card>
        <CardHeader>
          <CardTitle>Histórico de Ações</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          ) : !logs || logs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-lg mb-2">Nenhuma ação registrada</p>
              <p className="text-sm">
                {dataInicio || dataFim || filtroUsuario !== "todos"
                  ? "Ajuste os filtros para ver mais ações"
                  : "As ações dos usuários aparecerão aqui"}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
                >
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className={acaoColors[log.tipo_acao] || ""}>
                        {ACAO_LABELS[log.tipo_acao] || log.tipo_acao}
                      </Badge>
                      <Badge variant="secondary">
                        {entidadeLabels[log.tipo_entidade] || log.tipo_entidade}
                      </Badge>
                      {log.entidade_id && (
                        <span className="text-xs text-muted-foreground">
                          ID: {log.entidade_id}
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium">{log.descricao}</p>
                    {log.detalhes && Object.keys(log.detalhes).length > 0 && (
                      <details className="text-xs text-muted-foreground">
                        <summary className="cursor-pointer hover:text-foreground">
                          Ver detalhes
                        </summary>
                        <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto">
                          {JSON.stringify(log.detalhes, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                  <div className="flex flex-col sm:items-end gap-1 text-xs text-muted-foreground">
                    {log.usuario && (
                      <span className="font-medium text-foreground">{log.usuario.nome}</span>
                    )}
                    <span>{formatDate(log.created_at, true)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
