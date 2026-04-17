import { useMutation } from '@tanstack/react-query';
import { supabase } from '@noctusai/seed/infra';
import { toast } from 'sonner';

interface RequisitarSenhaRequest {
  corretorId: string;
  corretorEmail: string;
  corretorNome: string;
  confirmationMethod: 'email' | 'sms';
  confirmationCode?: string;
  step: 'request' | 'confirm';
}

export function useRequisitarSenha() {
  return useMutation({
    mutationFn: async (data: RequisitarSenhaRequest) => {
      const { data: result, error } = await supabase.functions.invoke('requisitar-senha', {
        body: data,
      });

      if (error) throw error;
      return result;
    },
    onSuccess: (data, variables) => {
      if (variables.step === 'request') {
        toast.success('Código de confirmação enviado!', {
          description: `Verifique seu ${variables.confirmationMethod === 'email' ? 'email' : 'SMS'}`,
        });
      } else {
        toast.success('Senha gerada com sucesso!', {
          description: 'A senha temporária foi enviada para seu email',
        });
      }
    },
    onError: (error: any) => {
      toast.error('Erro ao requisitar senha', {
        description: error.message || 'Tente novamente',
      });
    },
  });
}
