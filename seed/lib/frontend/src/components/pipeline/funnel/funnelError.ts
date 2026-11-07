/**
 * Parse a funnel API refusal into one shape. CANONICAL (projects/noc-funnel/CONTRACT.md): the platform
 * envelope `{"error":{"code","message","details"}}`; `409 gate_refused` carries
 * `details.{gate, pendencias:[{codigo, mensagem}]}`. The seed ApiClient exposes the parsed body as
 * `ApiError.body`. Flat / `detail` / `detalhe` layers are still read so a transport re-shape never turns a
 * refusal back into a bare "Erro HTTP 409".
 */
import type { FunnelPendencia, FunnelRefusal } from './types';

const isObj = (x: unknown): x is Record<string, unknown> =>
  !!x && typeof x === 'object' && !Array.isArray(x);

export function parseFunnelError(error: unknown): FunnelRefusal {
  const fallback = error instanceof Error ? error.message : 'Não foi possível concluir a operação.';
  const body = isObj(error) ? (error as { body?: unknown }).body : undefined;
  const layers: Record<string, unknown>[] = [];
  const push = (x: unknown) => {
    if (isObj(x)) layers.push(x);
  };
  push(body);
  if (isObj(body)) {
    push(body.error);
    push(body.detail);
    push(body.detalhe);
    if (isObj(body.detail)) push(body.detail.detalhe);
    if (isObj(body.error)) {
      push(body.error.details);
      push(body.error.detalhe);
    }
  }
  let code: string | null = null;
  let mensagem: string | null = null;
  let gate: string | null = null;
  let pendencias: FunnelPendencia[] = [];
  for (const l of layers) {
    if (code === null && typeof l.code === 'string') code = l.code;
    if (mensagem === null && typeof l.mensagem === 'string') mensagem = l.mensagem;
    if (mensagem === null && typeof l.message === 'string') mensagem = l.message;
    if (gate === null && typeof l.gate === 'string') gate = l.gate;
    if (pendencias.length === 0 && Array.isArray(l.pendencias)) {
      pendencias = l.pendencias.filter(isObj).map((p) => ({
        codigo: String(p.codigo ?? ''),
        label: String(p.label ?? p.mensagem ?? p.codigo ?? ''),
      }));
    }
  }
  return { code, mensagem: mensagem ?? fallback, gate, pendencias };
}
