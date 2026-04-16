import { NotificationBell as SharedNotificationBell } from "@noctusai/lib/design-system";
import {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
} from "@/hooks/useNotificacoes";
import { useNavigate } from "react-router-dom";

const hooks = { useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas };

export function NotificationBell() {
  const navigate = useNavigate();

  return (
    <SharedNotificationBell
      hooks={hooks}
      onViewAll={() => navigate("/notificacoes")}
    />
  );
}
