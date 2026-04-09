import { createNotificationHooks } from '@noctusai/shared/notifications';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export type { Notificacao, ContagemNaoLidas } from '@noctusai/shared/notifications';

export const {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
} = createNotificationHooks(api, useAuthStore);
