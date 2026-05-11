import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { Anamnese, TreatmentPlan, EvolutionNote } from '@/types';

const KEYS = {
  anamnese: (patientId: string) => ['anamnese', patientId] as const,
  treatmentPlans: (patientId: string) => ['treatment-plans', patientId] as const,
  evolutionNotes: (patientId: string) => ['evolution-notes', patientId] as const,
};

// ── Anamnese ──────────────────────────────────────────────

export function useAnamnese(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<Anamnese>({
    queryKey: KEYS.anamnese(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/anamnese/${patientId}`);
      return res.data ?? res;
    },
    enabled: !!user && !!patientId,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateAnamnese() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      patient_id: string;
      queixa_principal: string;
      historia_pregressa?: string;
      historico_familiar?: string;
      medicacoes?: string;
      observacoes?: string;
    }) => {
      return api.post('/api/anamnese', data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.anamnese(variables.patient_id) });
      toast.success('Anamnese criada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao criar anamnese');
    },
  });
}

export function useUpdateAnamnese() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, patient_id, ...data }: {
      id: string;
      patient_id: string;
      queixa_principal?: string;
      historia_pregressa?: string;
      historico_familiar?: string;
      medicacoes?: string;
      observacoes?: string;
    }) => {
      return api.patch(`/api/anamnese/${id}`, data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.anamnese(variables.patient_id) });
      toast.success('Anamnese atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar anamnese');
    },
  });
}

// ── Treatment Plans ──────────────────────────────────────────────

export function useTreatmentPlans(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<{ data: TreatmentPlan[]; total: number }>({
    queryKey: KEYS.treatmentPlans(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/treatment-plans?patient_id=${patientId}`);
      return res;
    },
    enabled: !!user && !!patientId,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateTreatmentPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      patient_id: string;
      titulo: string;
      descricao?: string;
      data_inicio: string;
      data_revisao?: string;
    }) => {
      return api.post('/api/treatment-plans', data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.treatmentPlans(variables.patient_id) });
      toast.success('Plano de tratamento criado');
    },
    onError: () => {
      toast.error('Erro ao criar plano de tratamento');
    },
  });
}

// ── Evolution Notes ──────────────────────────────────────────────

export function useEvolutionNotes(patientId?: string) {
  const { user } = useAuthStore();
  return useQuery<{ data: EvolutionNote[]; total: number }>({
    queryKey: KEYS.evolutionNotes(patientId!),
    queryFn: async () => {
      const res = await api.get(`/api/evolution-notes?patient_id=${patientId}`);
      return res;
    },
    enabled: !!user && !!patientId,
    staleTime: 30 * 1000,
  });
}

export function useCreateEvolutionNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      patient_id: string;
      appointment_id?: string;
      formato: 'soap' | 'livre';
      subjetivo?: string;
      objetivo?: string;
      avaliacao?: string;
      plano?: string;
      conteudo_livre?: string;
    }) => {
      return api.post('/api/evolution-notes', data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: KEYS.evolutionNotes(variables.patient_id) });
      toast.success('Nota de evolucao criada');
    },
    onError: () => {
      toast.error('Erro ao criar nota de evolucao');
    },
  });
}
