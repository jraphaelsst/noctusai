import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Button } from "@noctusai/seed/components/ui/button";
import { Badge } from "@noctusai/seed/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@noctusai/seed/components/ui/tabs";
import { Switch } from "@noctusai/seed/components/ui/switch";
import { Label } from "@noctusai/seed/components/ui/label";
import { ScrollArea } from "@noctusai/seed/components/ui/scroll-area";
import {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
  useNotificacaoPreferencias,
  useAtualizarPreferencia,
} from "@/hooks/useNotificacoes";
import {
  Bell, BellRing, Check, CheckCheck, Settings, Mail, MessageSquare,
  Monitor, Clock,
} from "lucide-react";
import { CardListSkeleton } from "@/components/ui/page-skeleton";
import { SummaryValue } from "@/components/ui/summary-value";

function timeAgo(dateStr: string) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

export default function Notificacoes() {
  const [tab, setTab] = useState("todas");
  const apenasNaoLidas = tab === "nao-lidas";

  const notificacoesQuery = useNotificacoes(1, 100, apenasNaoLidas);
  const { data: notificacoesResp } = notificacoesQuery;
  const showNotificacoesSkeleton = notificacoesQuery.isPending && !notificacoesQuery.data;
  const contagemQuery = useContagemNaoLidas();
  const { data: contagem } = contagemQuery;
  const contagemNotArrived = contagemQuery.isPending && !contagemQuery.data;
  const marcarLida = useMarcarComoLida();
  const marcarTodas = useMarcarTodasComoLidas();
  const { data: prefsResp } = useNotificacaoPreferencias();
  const atualizarPref = useAtualizarPreferencia();

  const notificacoes = notificacoesResp?.data || [];
  const naoLidas = contagem?.data?.nao_lidas || 0;
  const preferencias = prefsResp?.data || [];

  const CANAIS = [
    { key: "app", label: "App", icon: Monitor },
    { key: "email", label: "Email", icon: Mail },
    { key: "whatsapp", label: "WhatsApp", icon: MessageSquare },
  ];

  const TIPOS_EVENTO = [
    { key: "novo_lead", label: "Novo Lead" },
    { key: "proposta_aceita", label: "Proposta Aceita" },
    { key: "proposta_recusada", label: "Proposta Recusada" },
    { key: "contrato_assinado", label: "Contrato Assinado" },
    { key: "pagamento_recebido", label: "Pagamento Recebido" },
    { key: "pagamento_atrasado", label: "Pagamento Atrasado" },
    { key: "vistoria_agendada", label: "Vistoria Agendada" },
    { key: "mensagem_recebida", label: "Mensagem Recebida" },
  ];

  const getPrefAtivo = (canal: string, tipo: string) => {
    const pref = preferencias.find(
      (p: any) => p.canal === canal && p.tipo_evento === tipo
    );
    return pref ? pref.ativo : true;
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BellRing className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Notificações</h1>
            <p className="text-sm text-muted-foreground">
              <SummaryValue notArrived={contagemNotArrived} className="h-4 w-24">
                {naoLidas > 0 ? `${naoLidas} não lida${naoLidas > 1 ? "s" : ""}` : "Tudo em dia"}
              </SummaryValue>
            </p>
          </div>
        </div>
        {naoLidas > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => marcarTodas.mutate()}
            disabled={marcarTodas.isPending}
          >
            <CheckCheck className="h-4 w-4 mr-1" />
            Marcar todas como lidas
          </Button>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="todas">
            Todas
          </TabsTrigger>
          <TabsTrigger value="nao-lidas">
            Não lidas
            {naoLidas > 0 && (
              <Badge className="ml-1.5 bg-primary text-primary-foreground text-[10px] h-5 min-w-[20px] flex items-center justify-center">
                {naoLidas}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="preferencias">
            <Settings className="h-4 w-4 mr-1" />
            Preferências
          </TabsTrigger>
        </TabsList>

        <TabsContent value="todas" className="mt-4">
          <NotificacaoList
            notificacoes={notificacoes}
            showSkeleton={showNotificacoesSkeleton}
            onMarcarLida={(id: string) => marcarLida.mutate(id)}
          />
        </TabsContent>

        <TabsContent value="nao-lidas" className="mt-4">
          <NotificacaoList
            notificacoes={notificacoes}
            showSkeleton={showNotificacoesSkeleton}
            onMarcarLida={(id: string) => marcarLida.mutate(id)}
          />
        </TabsContent>

        <TabsContent value="preferencias" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Preferências de Notificação</CardTitle>
              <p className="text-sm text-muted-foreground">
                Escolha quais notificações receber e por qual canal.
              </p>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 pr-4 font-medium">Evento</th>
                      {CANAIS.map((canal) => (
                        <th key={canal.key} className="text-center py-2 px-3 font-medium">
                          <div className="flex items-center justify-center gap-1">
                            <canal.icon className="h-4 w-4" />
                            {canal.label}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {TIPOS_EVENTO.map((tipo) => (
                      <tr key={tipo.key} className="border-b last:border-0">
                        <td className="py-3 pr-4">{tipo.label}</td>
                        {CANAIS.map((canal) => (
                          <td key={canal.key} className="text-center py-3 px-3">
                            <Switch
                              checked={getPrefAtivo(canal.key, tipo.key)}
                              onCheckedChange={(ativo) =>
                                atualizarPref.mutate({
                                  canal: canal.key as "app" | "email" | "whatsapp",
                                  tipo_evento: tipo.key,
                                  ativo,
                                })
                              }
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function NotificacaoList({
  notificacoes,
  showSkeleton,
  onMarcarLida,
}: {
  notificacoes: any[];
  showSkeleton: boolean;
  onMarcarLida: (id: string) => void;
}) {
  if (showSkeleton) {
    return <CardListSkeleton count={4} />;
  }

  if (notificacoes.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Bell className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-muted-foreground">Nenhuma notificação</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <ScrollArea className="max-h-[600px]">
        <div className="divide-y">
          {notificacoes.map((n: any) => (
            <div
              key={n.id}
              className={`flex items-start gap-3 p-4 transition-colors ${
                !n.is_read ? "bg-primary/5" : ""
              }`}
            >
              <div className={`mt-1 h-2 w-2 rounded-full shrink-0 ${
                n.is_read ? "bg-transparent" : "bg-primary"
              }`} />
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${!n.is_read ? "font-medium" : ""}`}>
                  {n.titulo}
                </p>
                {n.mensagem && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {n.mensagem}
                  </p>
                )}
                <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {timeAgo(n.created_at)}
                  {n.tipo && (
                    <Badge variant="outline" className="ml-2 text-[10px] py-0">
                      {n.tipo}
                    </Badge>
                  )}
                </p>
              </div>
              {!n.is_read && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0"
                  onClick={() => onMarcarLida(n.id)}
                >
                  <Check className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>
    </Card>
  );
}
