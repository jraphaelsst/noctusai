import { NotificationBell as SharedNotificationBell } from "@noctusai/shared/design-system";
import {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
} from "@/hooks/useNotificacoes";

const hooks = { useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas };

export function NotificationBell() {
  return <SharedNotificationBell hooks={hooks} />;
}
