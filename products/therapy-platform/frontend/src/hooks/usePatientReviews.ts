import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatientReview {
  id: string;
  nota: number;
  comentario?: string;
  entity_name: string;
  entity_type: 'therapist' | 'clinic';
  created_at: string;
  updated_at: string;
}

export interface PendingReview {
  appointment_id: string;
  therapist_name: string;
  session_date: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function usePatientReviews() {
  const { user } = useAuthStore();

  return useQuery<{ data: PatientReview[]; pending: PendingReview[] }>({
    queryKey: ['patient', 'reviews', user?.id],
    queryFn: async () => api.get(`/api/reviews/patient/${user!.id}`),
    enabled: !!user?.id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useDeleteReview() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => api.delete(`/api/reviews/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', 'reviews'] });
      toast.success('Avaliacao removida');
    },
    onError: () => toast.error('Erro ao remover avaliacao'),
  });
}

export function useUpdateReview(onSuccess?: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, nota, comentario }: { id: string; nota: number; comentario: string }) =>
      // Backend column names are `star_rating`/`review_text`; the page collects
      // them under `nota`/`comentario`, so we adapt at the call site.
      api.patch(`/api/reviews/${id}`, { star_rating: nota, review_text: comentario }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', 'reviews'] });
      toast.success('Avaliacao atualizada');
      onSuccess?.();
    },
    onError: () => toast.error('Erro ao atualizar avaliacao'),
  });
}
