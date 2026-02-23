import { useMutation } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

interface RecuperarSenhaRequest {
  email: string;
}

export function useRecuperarSenha() {
  return useMutation({
    mutationFn: async (data: RecuperarSenhaRequest) => {
      const { data: result, error } = await supabase.functions.invoke('recuperar-senha', {
        body: data,
      });

      if (error) throw error;
      return result;
    },
    onSuccess: () => {
      toast.success('Solicitação enviada!', {
        description: 'Se o email estiver cadastrado, você receberá instruções em breve.',
      });
    },
    onError: (error: any) => {
      toast.error('Erro ao recuperar senha', {
        description: error.message || 'Tente novamente',
      });
    },
  });
}
