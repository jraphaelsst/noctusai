// Re-export shared utilities so existing `import { cn } from '@/lib/utils'` keeps working
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from '@noctusai/lib/utils';

// The platform's ONE phone definition. `normalizePhone` is what a value must
// pass through before it is STORED or compared; `formatPhone` is the display
// seam. Both are re-exported here so ERP has a single entry point and nobody
// hand-rolls a fifth version.
export { formatPhone, isValidPhone, normalizePhone, phoneDigits } from '@noctusai/lib/phone';

/**
 * INPUT MASK — progressive `(11) 99999-9999` as the user types.
 *
 * Deliberately NOT replaced by the seeded `formatPhone`, and the distinction
 * matters: a mask must render a HALF-TYPED number, while `formatPhone`
 * renders a COMPLETE one. Feeding a mask through a canonicalizer means
 * nothing appears until the last digit lands, which is unusable.
 *
 * So this is presentation-only. What gets SUBMITTED must still go through
 * `normalizePhone` — see `NovoUsuarioModal`, which used to store this masked
 * string verbatim and so wrote a third phone format into the database.
 */
export function formatPhoneNumber(value: string): string {
  const cleaned = value.replace(/\D/g, '');
  const limited = cleaned.slice(0, 11);

  if (limited.length <= 2) {
    return limited;
  } else if (limited.length <= 7) {
    return `(${limited.slice(0, 2)}) ${limited.slice(2)}`;
  } else {
    return `(${limited.slice(0, 2)}) ${limited.slice(2, 7)}-${limited.slice(7)}`;
  }
}

export function cleanPhoneNumber(value: string): string {
  return value.replace(/\D/g, '');
}

export function formatCurrencyInput(value: string): string {
  // Remove tudo exceto dígitos
  const cleaned = value.replace(/\D/g, '');
  
  if (!cleaned) return '';
  
  // Converte para número e divide por 100 para considerar centavos
  const number = parseInt(cleaned) / 100;
  
  // Formata como moeda brasileira
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(number);
}

export function cleanCurrencyInput(value: string): number {
  // Remove símbolos de moeda e formata para número
  const cleaned = value.replace(/[^\d,]/g, '').replace(',', '.');
  return parseFloat(cleaned) || 0;
}

// Product-specific utilities below
