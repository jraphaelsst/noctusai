import { createNotificationHooks } from '@noctusai/lib/notifications';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export type { Notificacao, ContagemNaoLidas } from '@noctusai/lib/notifications';

export const {
  useNotificacoes,
  useContagemNaoLidas,
  useMarcarComoLida,
  useMarcarTodasComoLidas,
} = createNotificationHooks(api, useAuthStore);
