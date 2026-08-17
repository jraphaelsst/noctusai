import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

if (!url || !key) {
  throw new Error("VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY não configuradas no .env");
}

/**
 * Cliente Supabase usado **somente para autenticação**. Diferente do
 * protótipo, nenhuma tela consulta tabelas por aqui: os dados vêm do backend
 * FastAPI, que é quem carrega o org_id e as regras de negócio.
 */
export const supabase = createClient(url, key);
