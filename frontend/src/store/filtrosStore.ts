import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface FiltrosState {
  periodo: string;
  dataInicio: Date | undefined;
  dataFim: Date | undefined;
  filtroCorretor: string;
  filtroStatus: string;
  filtroTipo: string;
  filtroReferencia: string;
  filtroConclusaoPrazo: string;
  setPeriodo: (periodo: string) => void;
  setDataInicio: (data: Date | undefined) => void;
  setDataFim: (data: Date | undefined) => void;
  setFiltroCorretor: (corretor: string) => void;
  setFiltroStatus: (status: string) => void;
  setFiltroTipo: (tipo: string) => void;
  setFiltroReferencia: (referencia: string) => void;
  setFiltroConclusaoPrazo: (conclusaoPrazo: string) => void;
  limparFiltros: () => void;
}

export const useFiltrosStore = create<FiltrosState>()(
  persist(
    (set) => ({
      periodo: "global",
      dataInicio: undefined,
      dataFim: undefined,
      filtroCorretor: "todos",
      filtroStatus: "todos",
      filtroTipo: "todos",
      filtroReferencia: "todos",
      filtroConclusaoPrazo: "todos",
      setPeriodo: (periodo) => set({ periodo }),
      setDataInicio: (data) => set({ dataInicio: data }),
      setDataFim: (data) => set({ dataFim: data }),
      setFiltroCorretor: (corretor) => set({ filtroCorretor: corretor }),
      setFiltroStatus: (status) => set({ filtroStatus: status }),
      setFiltroTipo: (tipo) => set({ filtroTipo: tipo }),
      setFiltroReferencia: (referencia) => set({ filtroReferencia: referencia }),
      setFiltroConclusaoPrazo: (conclusaoPrazo) => set({ filtroConclusaoPrazo: conclusaoPrazo }),
      limparFiltros: () => set({ 
        periodo: "global",
        dataInicio: undefined, 
        dataFim: undefined, 
        filtroCorretor: "todos", 
        filtroStatus: "todos",
        filtroTipo: "todos",
        filtroReferencia: "todos",
        filtroConclusaoPrazo: "todos"
      }),
    }),
    {
      name: 'filtros-storage',
    }
  )
);
