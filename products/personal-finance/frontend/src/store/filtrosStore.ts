import { create } from "zustand";
import { persist } from "zustand/middleware";

interface FiltrosState {
  periodo: string;
  dataInicio: string | undefined;
  dataFim: string | undefined;
  contaId: string | undefined;
  categoriaId: string | undefined;
  tipo: string | undefined;
  setPeriodo: (periodo: string) => void;
  setDataInicio: (data: string | undefined) => void;
  setDataFim: (data: string | undefined) => void;
  setContaId: (id: string | undefined) => void;
  setCategoriaId: (id: string | undefined) => void;
  setTipo: (tipo: string | undefined) => void;
  limparFiltros: () => void;
}

export const useFiltrosStore = create<FiltrosState>()(
  persist(
    (set) => ({
      periodo: "mensal",
      dataInicio: undefined,
      dataFim: undefined,
      contaId: undefined,
      categoriaId: undefined,
      tipo: undefined,
      setPeriodo: (periodo) => set({ periodo }),
      setDataInicio: (dataInicio) => set({ dataInicio }),
      setDataFim: (dataFim) => set({ dataFim }),
      setContaId: (contaId) => set({ contaId }),
      setCategoriaId: (categoriaId) => set({ categoriaId }),
      setTipo: (tipo) => set({ tipo }),
      limparFiltros: () =>
        set({
          periodo: "mensal",
          dataInicio: undefined,
          dataFim: undefined,
          contaId: undefined,
          categoriaId: undefined,
          tipo: undefined,
        }),
    }),
    { name: "pf-filtros-storage" }
  )
);
