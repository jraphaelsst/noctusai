/**
 * CPF / CNPJ helpers for the party-registration lookup (contract §2.5).
 *
 * The backend is the authority (it validates with `integrations.documents`);
 * this only decides WHEN to fire the lookup — a half-typed or check-digit-invalid
 * documento must not cost a round trip nor flash a server 400.
 */

export function apenasDigitos(valor: string): string {
  return valor.replace(/\D/g, "");
}

function digitoVerificador(base: string, pesoInicial: number): number {
  let soma = 0;
  for (let i = 0; i < base.length; i += 1) soma += Number(base[i]) * (pesoInicial - i);
  const resto = (soma * 10) % 11;
  return resto === 10 ? 0 : resto;
}

export function cpfValido(valor: string): boolean {
  const d = apenasDigitos(valor);
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  return (
    digitoVerificador(d.slice(0, 9), 10) === Number(d[9]) &&
    digitoVerificador(d.slice(0, 10), 11) === Number(d[10])
  );
}

function dvCnpj(base: string): number {
  const pesos = base.length === 12
    ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const soma = base.split("").reduce((acc, ch, i) => acc + Number(ch) * pesos[i], 0);
  const resto = soma % 11;
  return resto < 2 ? 0 : 11 - resto;
}

export function cnpjValido(valor: string): boolean {
  const d = apenasDigitos(valor);
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
  return dvCnpj(d.slice(0, 12)) === Number(d[12]) && dvCnpj(d.slice(0, 13)) === Number(d[13]);
}

/** The digits to look up, or `null` while the documento is incomplete/invalid
 *  for the chosen kind of person. */
export function documentoParaLookup(valor: string, tipo: "PF" | "PJ"): string | null {
  const d = apenasDigitos(valor);
  if (tipo === "PF") return cpfValido(d) ? d : null;
  return cnpjValido(d) ? d : null;
}
