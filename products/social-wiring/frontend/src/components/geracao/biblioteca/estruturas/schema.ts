/**
 * The admin editor's validation — a zod mirror of the contract's column rules (§3.1, §6.2) so a bad draft
 * is refused inline, in pt-BR, before the round trip (the server stays the authority).
 */
import { z } from "zod";

import type { EstruturaRascunho } from "./rotulos";

const OBJETIVOS = ["alcance", "autoridade", "conexao", "venda"] as const;
const FORMATOS = ["reels", "carrossel", "stories", "post"] as const;

export const blocoSchema = z.object({
  nome: z.string().trim().min(1, "Informe o nome do bloco.").max(120, "Use até 120 caracteres."),
  tipo_id: z.string().min(1, "Escolha o tipo do bloco."),
  tempo: z.string().trim().max(40, "Use até 40 caracteres."),
  instrucao: z.string().trim().max(2000, "Use até 2000 caracteres."),
  nota: z.string().trim().max(600, "Use até 600 caracteres."),
  repeticoes: z
    .number({ error: "Informe um número de 1 a 20." })
    .int("Informe um número inteiro.")
    .min(1, "Mínimo 1.")
    .max(20, "Máximo 20."),
});

export const rascunhoSchema = z.object({
  formula_headline: z.string().trim().min(1, "Informe a fórmula da headline.").max(1000, "Use até 1000 caracteres."),
  formato: z.enum(FORMATOS, { error: "Escolha o formato." }),
  objetivos: z
    .array(z.enum(OBJETIVOS))
    .min(1, "Escolha ao menos um objetivo.")
    .max(4)
    .refine((o) => new Set(o).size === o.length, "Objetivos repetidos."),
  blocos: z.array(blocoSchema).min(1, "Adicione ao menos um bloco.").max(60, "No máximo 60 blocos."),
});

export type ErrosRascunho = Record<string, string>;

/** `formula_headline`, `formato`, `objetivos`, `blocos`, or `bloco.<chave>.<campo>` → first message. */
export function errosDoRascunho(r: EstruturaRascunho): ErrosRascunho {
  const res = rascunhoSchema.safeParse({
    ...r,
    formato: r.formato === "" ? undefined : r.formato,
  });
  if (res.success) return {};
  const out: ErrosRascunho = {};
  for (const issue of res.error.issues) {
    const [raiz, indice, campo] = issue.path;
    let chave: string;
    if (raiz === "blocos" && typeof indice === "number" && typeof campo === "string") {
      chave = `bloco.${r.blocos[indice]?.chave ?? indice}.${campo}`;
    } else {
      chave = String(raiz);
    }
    out[chave] ??= issue.message;
  }
  return out;
}
