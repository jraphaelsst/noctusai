// @consumes-organ NotificationBell@1.0 +seam=hooks-binding
// Thin shim over the canonical organ: binds ERP's product-local notification
// hooks (api + auth from @noctusai/seed/infra) and nav. NOT a re-implementation.
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
