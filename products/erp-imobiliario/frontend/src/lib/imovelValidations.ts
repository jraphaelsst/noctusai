import { z } from 'zod';

export const imovelSchema = z.object({
  finalidade: z.enum(['venda', 'aluguel'], {
    required_error: 'Finalidade é obrigatória',
  }),
  preco_pedido: z.coerce
    .number()
    .min(0, 'Preço não pode ser negativo')
    .positive('Preço deve ser maior que zero'),
  aceita_permutas: z.boolean().default(false),
  observacoes_negociacao: z.string().max(1000, 'Observações muito longas').optional(),
  
  cep: z.string()
    .trim()
    .min(8, 'CEP é obrigatório')
    .regex(/^\d{5}-?\d{3}$/, 'CEP inválido'),
  logradouro: z.string().trim().max(200).optional(),
  numero: z.string().trim().max(20).optional(),
  complemento: z.string().trim().max(100).optional(),
  bairro: z.string().trim().max(100).optional(),
  cidade: z.string().trim().max(100).optional(),
  estado: z.string().trim().length(2, 'Estado deve ter 2 caracteres').optional(),
  
  tipo: z.enum(['casa', 'apartamento', 'terreno', 'comercial', 'rural', 'outro'], {
    required_error: 'Tipo é obrigatório',
  }),
  area_privativa: z.coerce.number().min(0).optional(),
  area_total: z.coerce.number().min(0).optional(),
  quartos: z.coerce.number().int().min(0).optional(),
  suites: z.coerce.number().int().min(0).optional(),
  banheiros: z.coerce.number().int().min(0).optional(),
  vagas: z.coerce.number().int().min(0).optional(),
  andar: z.coerce.number().int().optional(),
  condominio: z.coerce.number().min(0).optional(),
  iptu: z.coerce.number().min(0).optional(),
  condominio_nome: z.string().max(200).optional(),
  ano_construcao: z.coerce.number().int().min(1900).max(new Date().getFullYear() + 2).optional(),
  
  titulo_anuncio: z.string().max(200).optional(),
  descricao_seo: z.string().max(2000).optional(),
  palavras_chave: z.array(z.string()).max(4, 'Máximo 4 palavras-chave').optional(),
  pontos_de_interesse: z.array(z.string()).optional(),
});

export const perfilPermutaSchema = z.object({
  categoria: z.enum(['imovel', 'movel'], {
    required_error: 'Categoria é obrigatória',
  }),
  
  // Imóvel
  tipo_imovel: z.enum(['casa', 'apartamento', 'terreno', 'comercial', 'rural', 'outro']).optional(),
  faixa_preco_min: z.coerce.number().min(0).optional(),
  faixa_preco_max: z.coerce.number().min(0).optional(),
  regiao_preferida: z.array(z.string()).optional(),
  metragem_min: z.coerce.number().min(0).optional(),
  metragem_max: z.coerce.number().min(0).optional(),
  quartos_min: z.coerce.number().int().min(0).optional(),
  vagas_min: z.coerce.number().int().min(0).optional(),
  
  // Móvel
  tipo_movel: z.enum(['carro', 'moto']).optional(),
  marca: z.string().max(100).optional(),
  modelo: z.string().max(100).optional(),
  ano_min: z.coerce.number().int().min(1900).optional(),
  ano_max: z.coerce.number().int().max(new Date().getFullYear() + 1).optional(),
  quilometragem_max: z.coerce.number().int().min(0).optional(),
  
  // Flexibilidade
  aceita_completar_diferenca: z.boolean().default(false),
  limite_complemento: z.coerce.number().min(0).optional(),
  observacoes: z.string().max(1000).optional(),
  valor_estimado: z.coerce.number().min(0).optional(),
}).refine(
  (data) => {
    if (data.faixa_preco_min && data.faixa_preco_max) {
      return data.faixa_preco_min <= data.faixa_preco_max;
    }
    return true;
  },
  {
    message: 'Preço mínimo deve ser menor que o máximo',
    path: ['faixa_preco_max'],
  }
).refine(
  (data) => {
    if (data.metragem_min && data.metragem_max) {
      return data.metragem_min <= data.metragem_max;
    }
    return true;
  },
  {
    message: 'Metragem mínima deve ser menor que a máxima',
    path: ['metragem_max'],
  }
);

export type ImovelFormData = z.infer<typeof imovelSchema>;
export type PerfilPermutaFormData = z.infer<typeof perfilPermutaSchema>;

// Helper para calcular score de qualidade do anúncio
export function calcularQualidadeAnuncio(imovel: Partial<ImovelFormData> & { fotos?: string[] }): {
  score: number;
  alertas: string[];
} {
  const alertas: string[] = [];
  let score = 0;

  // CEP (obrigatório)
  if (!imovel.cep) {
    alertas.push('⚠️ CEP é obrigatório');
  } else {
    score += 20;
  }

  // Fotos (importante)
  const numFotos = imovel.fotos?.length || 0;
  if (numFotos === 0) {
    alertas.push('📷 Adicione fotos do imóvel (mínimo 4, recomendado 8+)');
  } else if (numFotos < 4) {
    alertas.push(`📷 Adicione mais fotos (${numFotos}/4 mínimo)`);
    score += 10;
  } else if (numFotos < 8) {
    score += 20;
    alertas.push(`📷 Bom! Adicione mais fotos para melhorar (${numFotos}/8 recomendado)`);
  } else {
    score += 30;
  }

  // Título e descrição
  if (!imovel.titulo_anuncio || imovel.titulo_anuncio.length < 20) {
    alertas.push('📝 Adicione um título descritivo (mín. 20 caracteres)');
  } else {
    score += 15;
  }

  if (!imovel.descricao_seo || imovel.descricao_seo.length < 50) {
    alertas.push('📝 Adicione uma descrição completa (mín. 50 caracteres)');
  } else {
    score += 15;
  }

  // Palavras-chave
  const numPalavras = imovel.palavras_chave?.length || 0;
  if (numPalavras === 0) {
    alertas.push('🔑 Adicione palavras-chave para SEO (até 4)');
  } else if (numPalavras < 3) {
    score += 5;
    alertas.push(`🔑 Adicione mais palavras-chave (${numPalavras}/4)`);
  } else {
    score += 10;
  }

  // Pontos de interesse
  if (!imovel.pontos_de_interesse || imovel.pontos_de_interesse.length === 0) {
    alertas.push('📍 Adicione pontos de interesse próximos');
  } else {
    score += 10;
  }

  return { score, alertas };
}
