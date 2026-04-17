import { NotificationBell as SharedNotificationBell } from "@noctusai/lib/design-system";
import { createNotificationHooks } from "@noctusai/lib/notifications";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { useNavigate } from "react-router-dom";

const hooks = createNotificationHooks(api, useAuthStore);

export function NotificationBell() {
  const navigate = useNavigate();

  return (
    <SharedNotificationBell
      hooks={hooks}
      onViewAll={() => navigate("/notificacoes")}
    />
  );
}
