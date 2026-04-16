// Re-export shared utilities so existing `import { cn } from '@/lib/utils'` keeps working
export { cn, formatCurrency, formatDate, getTodayAtMidnight, stripTime } from '@noctusai/lib/utils';

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
