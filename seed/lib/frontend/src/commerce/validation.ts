/** CPF/CNPJ validation — delegates to the canonical `identificador.ts` check-digit algorithms. */
import { cnpjDvValido, cpfDvValido } from '../identificador';
import { onlyDigits } from './format';

export function isValidCnpj(value: string): boolean {
  const d = onlyDigits(value);
  return d.length === 14 && cnpjDvValido(d);
}

export function isValidCpf(value: string): boolean {
  const d = onlyDigits(value);
  return d.length === 11 && cpfDvValido(d);
}

export function isValidCpfOrCnpj(value: string): boolean {
  return isValidCpf(value) || isValidCnpj(value);
}

export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim());
}
