/** Lais privacy notice — public read + the admin editor (contract 11.2). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

// ─── Admin editor (GET/PUT /api/lais/agente/aviso) ───────────────────────────

export interface LaisAvisoAdmin extends LaisAvisoPublico {
  slug: string;
  mensagem_inicial: string;
  /** True while the notice still shows "a definir" placeholders. */
  incompleto: boolean;
}

export interface LaisAvisoInput {
  titulo: string;
  empresa_nome: string;
  contato_email: string | null;
  contato_whatsapp: string | null;
  secoes: LaisAvisoSecao[];
  mensagem_inicial: string;
}

const AVISO_KEY = ["sw", "lais", "aviso"] as const;

export function useLaisAviso() {
  return useQuery({
    queryKey: AVISO_KEY,
    queryFn: async () => (await api.get<{ data: LaisAvisoAdmin }>("/api/lais/agente/aviso")).data,
  });
}

export function useSalvarLaisAviso() {
  const qc = useQueryClient();
  return useMutation<LaisAvisoAdmin, unknown, LaisAvisoInput>({
    mutationFn: async (body) => (await api.put<{ data: LaisAvisoAdmin }>("/api/lais/agente/aviso", body)).data,
    onSuccess: (row) => {
      qc.setQueryData(AVISO_KEY, row);
      // The Agente page's "aviso_incompleto" gate reads the notice server-side.
      qc.invalidateQueries({ queryKey: ["sw", "lais", "agente"] });
    },
  });
}
