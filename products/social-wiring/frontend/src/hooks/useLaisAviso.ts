/** Lais privacy notice — public read (contract 11.2). Editing hooks arrive with W2. */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface LaisAvisoSecao {
  n: string;
  title: string;
  blocks: ({ p: string } | { ul: string[] })[];
}

export interface LaisAvisoPublico {
  titulo: string | null;
  empresa_nome: string | null;
  contato_email: string | null;
  contato_whatsapp: string | null;
  secoes: LaisAvisoSecao[];
  versao: number;
  atualizado_em: string | null;
}

export function useLaisAvisoPublico(slug: string | undefined) {
  return useQuery({
    queryKey: ["sw", "lais", "aviso-publico", slug ?? "_none"],
    enabled: !!slug,
    retry: false,
    // 404 is a stable state the page renders itself ("Aviso não encontrado").
    meta: { suppressErrorToastStatuses: [404] },
    queryFn: () =>
      api.get<{ data: LaisAvisoPublico }>(`/api/public/lais/privacidade/${encodeURIComponent(slug!)}`),
  });
}
