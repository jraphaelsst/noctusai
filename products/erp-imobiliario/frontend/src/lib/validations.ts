import { z } from 'zod';

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'Email é obrigatório')
    .email('Email inválido')
    .max(255, 'Email muito longo'),
  password: z
    .string()
    .min(8, 'Senha deve ter no mínimo 8 caracteres')
    .max(100, 'Senha muito longa'),
});

export const signUpSchema = z.object({
  nome: z
    .string()
    .trim()
    .min(1, 'Nome é obrigatório')
    .max(100, 'Nome muito longo')
    .regex(/^[a-zA-ZÀ-ÿ\s]+$/, 'Nome deve conter apenas letras'),
  email: z
    .string()
    .trim()
    .min(1, 'Email é obrigatório')
    .email('Email inválido')
    .max(255, 'Email muito longo'),
  telefone: z
    .string()
    .trim()
    .min(1, 'Telefone é obrigatório')
    .regex(/^\(\d{2}\) \d{5}-\d{4}$/, 'Telefone deve estar no formato (00) 00000-0000'),
  password: z
    .string()
    .min(8, 'Senha deve ter no mínimo 8 caracteres')
    .max(100, 'Senha muito longa'),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: 'As senhas não coincidem',
  path: ['confirmPassword'],
});

export const corretorSchema = signUpSchema;

export type LoginFormData = z.infer<typeof loginSchema>;
export type SignUpFormData = z.infer<typeof signUpSchema>;
export type CorretorFormData = z.infer<typeof corretorSchema>;

export const clienteSchema = z.object({
  nome: z
    .string()
    .trim()
    .min(3, 'Nome deve ter no mínimo 3 caracteres')
    .max(100, 'Nome muito longo'),
  email: z
    .string()
    .trim()
    .email('Email inválido')
    .max(255, 'Email muito longo')
    .optional()
    .or(z.literal('')),
  telefone: z
    .string()
    .trim()
    .min(10, 'Telefone deve ter no mínimo 10 dígitos')
    .max(20, 'Telefone muito longo')
    .optional()
    .or(z.literal('')),
  origem: z.string().optional(),
  interesse: z.string().max(200, 'Interesse muito longo').optional(),
  observacoes: z.string().max(1000, 'Observações muito longas').optional(),
  probabilidade: z.coerce
    .number()
    .min(0, 'Probabilidade mínima é 0%')
    .max(100, 'Probabilidade máxima é 100%')
    .default(10),
  valor_estimado: z.coerce
    .number()
    .min(0, 'Valor não pode ser negativo')
    .default(0),
});

export const atividadeSchema = z.object({
  tipo: z.enum([
    'ligacao',
    'email',
    'reuniao',
    'whatsapp',
    'visita',
    'proposta',
    'negociacao',
    'outro',
  ]),
  descricao: z
    .string()
    .trim()
    .min(3, 'Descrição deve ter no mínimo 3 caracteres')
    .max(500, 'Descrição muito longa'),
  data_execucao: z.string().optional(),
});

export type ClienteFormData = z.infer<typeof clienteSchema>;
export type AtividadeFormData = z.infer<typeof atividadeSchema>;

export const impedimentoSchema = z.object({
  tem_impedimento: z.boolean(),
  motivo_impedimento: z.string()
    .trim()
    .min(10, 'Motivo deve ter no mínimo 10 caracteres')
    .max(500, 'Motivo muito longo')
    .optional()
    .or(z.literal('')),
}).refine(
  (data) => !data.tem_impedimento || (data.motivo_impedimento && data.motivo_impedimento.length >= 10),
  {
    message: 'Motivo do impedimento é obrigatório quando há impedimento',
    path: ['motivo_impedimento'],
  }
);

export type ImpedimentoFormData = z.infer<typeof impedimentoSchema>;
