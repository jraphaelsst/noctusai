import type { ClienteDeleteOut } from "@/hooks/useClientes";

/** Result toast for a successful delete — says the person won't come back
 *  from their leads (the backfill is blocked by the tombstones). */
export function mensagemClienteExcluido(result: ClienteDeleteOut): string {
  const n = result.origens_bloqueadas ?? 0;
  return n > 0
    ? `Cliente excluído. Ele não voltará a partir dos ${n} lead(s) de origem.`
    : "Cliente excluído.";
}
