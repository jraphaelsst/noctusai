import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { EtapaFunil } from '@/types/clientes';

interface FunilFiltrosStore {
  busca: string;
  responsavelId: 'todos' | string;
  origem: 'todas' | string;
  etapa: 'todas' | EtapaFunil;
  incluirArquivados: boolean;
  dataInicio?: Date;
  dataFim?: Date;
  
  setBusca: (busca: string) => void;
  setResponsavelId: (id: 'todos' | string) => void;
  setOrigem: (origem: 'todas' | string) => void;
  setEtapa: (etapa: 'todas' | EtapaFunil) => void;
  setIncluirArquivados: (incluir: boolean) => void;
  setDataInicio: (data?: Date) => void;
  setDataFim: (data?: Date) => void;
  limparFiltros: () => void;
}

export const useFunilFiltrosStore = create<FunilFiltrosStore>()(
  persist(
    (set) => ({
      busca: '',
      responsavelId: 'todos',
      origem: 'todas',
      etapa: 'todas',
      incluirArquivados: false,
      dataInicio: undefined,
      dataFim: undefined,

      setBusca: (busca) => set({ busca }),
      setResponsavelId: (id) => set({ responsavelId: id }),
      setOrigem: (origem) => set({ origem }),
      setEtapa: (etapa) => set({ etapa }),
      setIncluirArquivados: (incluir) => set({ incluirArquivados: incluir }),
      setDataInicio: (data) => set({ dataInicio: data }),
      setDataFim: (data) => set({ dataFim: data }),
      limparFiltros: () =>
        set({
          busca: '',
          responsavelId: 'todos',
          origem: 'todas',
          etapa: 'todas',
          incluirArquivados: false,
          dataInicio: undefined,
          dataFim: undefined,
        }),
    }),
    {
      name: 'funil-filtros-storage',
    }
  )
);
