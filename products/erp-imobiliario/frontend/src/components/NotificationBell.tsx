import { useState } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useContagemNaoLidas, useNotificacoes, useMarcarComoLida, useMarcarTodasComoLidas } from "@/hooks/useNotificacoes";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: contagem } = useContagemNaoLidas();
  const { data: notificacoesData } = useNotificacoes(1, 10);
  const marcarComoLida = useMarcarComoLida();
  const marcarTodas = useMarcarTodasComoLidas();

  const naoLidas = contagem?.nao_lidas ?? 0;
  const notificacoes = notificacoesData?.data ?? [];

  const handleClick = (id: string, link?: string | null) => {
    marcarComoLida.mutate(id);
    if (link) {
      window.location.href = link;
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          {naoLidas > 0 && (
            <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center">
              {naoLidas > 99 ? "99+" : naoLidas}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="flex items-center justify-between p-3 border-b">
          <h4 className="font-semibold text-sm">Notificacoes</h4>
          {naoLidas > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7"
              onClick={() => marcarTodas.mutate()}
            >
              Marcar todas como lidas
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-[300px]">
          {notificacoes.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Nenhuma notificacao
            </div>
          ) : (
            notificacoes.map((n) => (
              <div
                key={n.id}
                className={`flex flex-col gap-1 p-3 border-b cursor-pointer hover:bg-muted/50 transition-colors ${
                  !n.is_read ? "bg-blue-50 dark:bg-blue-950/20" : ""
                }`}
                onClick={() => handleClick(n.id, n.link)}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium text-sm leading-tight">{n.titulo}</span>
                  {!n.is_read && (
                    <span className="h-2 w-2 rounded-full bg-blue-500 mt-1 flex-shrink-0" />
                  )}
                </div>
                {n.mensagem && (
                  <span className="text-xs text-muted-foreground line-clamp-2">
                    {n.mensagem}
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground">
                  {formatDistanceToNow(new Date(n.created_at), {
                    addSuffix: true,
                    locale: ptBR,
                  })}
                </span>
              </div>
            ))
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
