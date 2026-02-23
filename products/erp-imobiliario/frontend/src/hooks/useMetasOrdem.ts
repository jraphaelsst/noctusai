import { useState, useEffect } from 'react';
import { Meta, TipoMeta } from '@/types';

// Armazenar ordem das metas por tipo no localStorage
const STORAGE_KEY = 'metas-ordem';

interface MetasOrdem {
  [tipo: string]: string[]; // tipo -> array de IDs na ordem
}

export function useMetasOrdem() {
  const [ordem, setOrdem] = useState<MetasOrdem>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  });

  // Salvar no localStorage sempre que mudar
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ordem));
  }, [ordem]);

  const reordenarMetas = (tipo: TipoMeta, metasIds: string[]) => {
    setOrdem(prev => ({
      ...prev,
      [tipo]: metasIds
    }));
  };

  const getMetasOrdenadas = (metas: Meta[], tipo: TipoMeta): Meta[] => {
    const ordemTipo = ordem[tipo];
    if (!ordemTipo || ordemTipo.length === 0) {
      return metas;
    }

    // Criar mapa de metas por ID
    const metasMap = new Map(metas.map(m => [m.id, m]));
    
    // Ordenar baseado na ordem salva
    const ordenadas: Meta[] = [];
    const naoOrdenadas: Meta[] = [];

    ordemTipo.forEach(id => {
      const meta = metasMap.get(id);
      if (meta) {
        ordenadas.push(meta);
        metasMap.delete(id);
      }
    });

    // Adicionar metas que não estão na ordem salva (novas metas)
    metasMap.forEach(meta => {
      naoOrdenadas.push(meta);
    });

    return [...ordenadas, ...naoOrdenadas];
  };

  return {
    reordenarMetas,
    getMetasOrdenadas,
  };
}
