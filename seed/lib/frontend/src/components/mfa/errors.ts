import { ApiError } from '../../api';

/** Calm pt-BR copy for the MFA endpoints' refusals. */
export function mfaErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'mfa_invalid_code') return 'Código incorreto ou expirado. Confira o app e tente de novo.';
    if (err.code === 'mfa_factor_not_found') return 'Este dispositivo não foi encontrado. Atualize a página e tente de novo.';
    if (err.code === 'mfa_factor_limit') return 'Você já tem 2 dispositivos cadastrados. Remova um antes de adicionar outro.';
    if (err.status === 429) {
      const wait = err.retryAfterSeconds;
      return wait
        ? `Muitas tentativas. Aguarde ${wait} segundos e tente de novo.`
        : 'Muitas tentativas. Aguarde um instante e tente de novo.';
    }
    if (err.status === null) return 'Não foi possível falar com o servidor. Verifique a conexão.';
  }
  return 'Algo deu errado. Tente de novo em instantes.';
}

export const isSixDigits = (v: string) => /^\d{6}$/.test(v);
