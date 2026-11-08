import { describe, expect, it } from 'vitest';

import { GENERIC_TIMELINE_RENDERERS } from '../../card-hub/Timeline';
import { parseFunnelError } from './funnelError';

describe('parseFunnelError — canonical platform envelope (CONTRACT.md)', () => {
  it('reads code, message and details.pendencias from {error:{code,message,details}}', () => {
    const err = Object.assign(new Error('Erro HTTP 409'), {
      body: {
        error: {
          code: 'gate_refused',
          message: 'Falta definir o responsável para entrar em Qualificado.',
          details: {
            gate: 'responsavel_definido',
            pendencias: [{ codigo: 'responsavel', mensagem: 'Defina o responsável' }],
          },
        },
      },
    });
    expect(parseFunnelError(err)).toEqual({
      code: 'gate_refused',
      mensagem: 'Falta definir o responsável para entrar em Qualificado.',
      gate: 'responsavel_definido',
      pendencias: [{ codigo: 'responsavel', label: 'Defina o responsável' }],
    });
  });

  it('falls back to the transport message when the body has no envelope', () => {
    expect(parseFunnelError(new Error('Erro HTTP 500')).mensagem).toBe('Erro HTTP 500');
  });
});

describe('funnel outcome timeline kinds', () => {
  it('renders perdido with its motivo, reaberto and arquivado in pt-BR', () => {
    expect(GENERIC_TIMELINE_RENDERERS.perdido.summary({ motivo: 'Sem orçamento' })).toBe(
      'Marcado como perdido: Sem orçamento',
    );
    expect(GENERIC_TIMELINE_RENDERERS.perdido.summary({})).toBe('Marcado como perdido');
    expect(GENERIC_TIMELINE_RENDERERS.reaberto.summary({})).toBe('Reaberto');
    expect(GENERIC_TIMELINE_RENDERERS.arquivado.summary({})).toBe('Arquivado');
  });
});
