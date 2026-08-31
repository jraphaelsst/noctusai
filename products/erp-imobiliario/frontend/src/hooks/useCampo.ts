import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface Checkin {
  id: string;
  org_id: string;
  corretor_id: string;
  imovel_id?: string | null;
  latitude: number;
  longitude: number;
  tipo: 'visita' | 'vistoria' | 'captacao' | 'reuniao';
  observacoes?: string | null;
  fotos: string[];
  created_at: string;
}

export interface ImovelProximo {
  id: string;
  natureza: string;
  tipo_imovel?: string;
  titulo_anuncio?: string;
  valor?: number;
  cidade?: string;
  bairro?: string;
  logradouro?: string;
  numero?: string;
  estado?: string;
  latitude: number;
  longitude: number;
  quartos?: number;
  area_privativa?: number;
  fotos?: string[];
  status: string;
  finalidade?: string;
  distancia_km: number;
}

export function useCheckins(filters?: {
  corretor_id?: string;
  tipo?: string;
  data_inicio?: string;
  data_fim?: string;
}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['checkins', filters],
    queryFn: async () => {
      const result = await api.get('/api/campo/checkins', filters);
      return (result.data || []) as Checkin[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useCreateCheckin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      latitude: number;
      longitude: number;
      tipo: 'visita' | 'vistoria' | 'captacao' | 'reuniao';
      imovel_id?: string;
      observacoes?: string;
      fotos?: string[];
    }) => {
      const result = await api.post('/api/campo/checkin', data);
      return result.data as Checkin;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checkins'] });
      toast.success('Check-in registrado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar check-in', { description: error.message });
    },
  });
}

export function useVistoriaRapida() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      imovel_id: string;
      latitude: number;
      longitude: number;
      estado_geral: 'bom' | 'regular' | 'ruim' | 'critico';
      itens_checklist?: Record<string, boolean>;
      observacoes?: string;
      fotos?: string[];
    }) => {
      const result = await api.post('/api/campo/vistoria-rapida', data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checkins'] });
      queryClient.invalidateQueries({ queryKey: ['vistorias'] });
      toast.success('Vistoria rápida registrada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar vistoria', { description: error.message });
    },
  });
}

export function useImoveisProximos(latitude?: number, longitude?: number, raio_km?: number) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['imoveis-proximos', latitude, longitude, raio_km],
    queryFn: async () => {
      if (latitude === undefined || longitude === undefined) return [];
      const result = await api.get('/api/campo/proximos', {
        latitude,
        longitude,
        raio_km: raio_km || 5,
      });
      return (result.data || []) as ImovelProximo[];
    },
    enabled: !!user && latitude !== undefined && longitude !== undefined,
  });
}

export function useSyncCampo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { checkins?: any[]; vistorias?: any[] }) => {
      const result = await api.post('/api/campo/sync', data);
      return result.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['campo-offline-data'] });
      queryClient.invalidateQueries({ queryKey: ['checkins'] });
      toast.success(`Sincronizado: ${data?.checkins_criados || 0} checkins, ${data?.vistorias_criadas || 0} vistorias`);
    },
    onError: (error: Error) => {
      toast.error('Erro ao sincronizar', { description: error.message });
    },
  });
}

export function useOfflineData() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['campo-offline-data'],
    queryFn: async () => {
      const result = await api.get('/api/campo/offline-data');
      return result.data;
    },
    enabled: !!user,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}
