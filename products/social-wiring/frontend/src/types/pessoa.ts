/** `GET /api/clientes/{id}/resumo` — CONTRACT §4.5. */
export type PessoaPapel = "lead" | "comprador" | "vendedor" | "proprietario";

export interface PessoaAtendimento {
  id: string;
  titulo: string | null;
  etapa: { id: string; nome: string } | null;
  status: string | null;
  arquivado: boolean;
  titular: boolean;
  lado: string | null;
  papel: string | null;
  parte_id: string | null;
  imovel_pendente: boolean;
  imoveis: string[];
  created_at: string | null;
}

export interface PessoaResumo {
  cliente: {
    id: string;
    nome: string | null;
    nome_oficial: string | null;
    cpf: string | null;
    celular: string | null;
    email: string | null;
    estado_civil?: string | null;
    [key: string]: unknown;
  };
  papeis: PessoaPapel[];
  contatos: {
    celular: string | null;
    email: string | null;
    chave_canonica: string | null;
  };
  atendimentos: PessoaAtendimento[];
  contagens: {
    interesses: number;
    propriedades: number;
    roteiros: number;
    atendimentos: number;
  };
}
