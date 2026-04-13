import { createNotificationHooks } from "@noctusai/shared/notifications";
import { api } from "@/lib/api-client";

const { NotificationBell: Bell } = createNotificationHooks(api);

export function NotificationBell() {
  return <Bell />;
}
