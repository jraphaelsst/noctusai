import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DimobTransacao {
  id: string;
  tipo: 'venda' | 'locacao';
  valor: number;
  data: string;
  imovel_endereco: string;
  cpf_cnpj_comprador: string;
  nome_comprador: string;
  cpf_cnpj_vendedor?: string;
  nome_vendedor?: string;
  comissao?: number;
}

export interface DimobValidacao {
  campo: string;
  mensagem: string;
  nivel: 'erro' | 'aviso';
  transacao_id?: string;
}

export interface DimobPreview {
  ano: number;
  transacoes: DimobTransacao[];
  validacoes: DimobValidacao[];
  totais: {
    total_vendas: number;
    total_locacoes: number;
    valor_total_vendas: number;
    valor_total_locacoes: number;
    total_comissoes: number;
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useDimobPreview(ano: number, enabled: boolean) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['dimob', 'preview', ano],
    queryFn: async () => {
      const result = await api.get('/api/dimob/preview', { ano });
      return result.data as DimobPreview;
    },
    enabled: !!user && enabled,
    staleTime: 5 * 60 * 1000,
  });
}
