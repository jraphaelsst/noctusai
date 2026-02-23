import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

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

/**
 * Formata uma data/timestamp para o formato brasileiro DD/MM/YYYY
 * Opcionalmente inclui horário no formato DD/MM/YYYY às HH:mm
 * 
 * IMPORTANTE: Assume que as datas do banco já estão em America/Sao_Paulo
 * conforme configurado nos triggers e timezone do PostgreSQL.
 * 
 * Para datas no formato DATE (YYYY-MM-DD), interpreta como data local
 * sem conversão de timezone, evitando problemas com UTC.
 * 
 * @param dateString - String de data (ISO, YYYY-MM-DD, ou timestamp)
 * @param includeTime - Se true, inclui horário no formato "às HH:mm"
 * @returns Data formatada no padrão brasileiro
 * 
 * @example
 * formatDate("2025-10-25T14:30:00Z")           // "25/10/2025"
 * formatDate("2025-10-25T14:30:00Z", true)     // "25/10/2025 às 14:30"
 * formatDate("2025-10-25")                     // "25/10/2025"
 */
export function formatDate(dateString: string, includeTime: boolean = false): string {
  if (!dateString) return '-';
  
  let date: Date;
  
  // Detecta se é uma string de data simples (YYYY-MM-DD)
  // Regex para formato DATE: YYYY-MM-DD sem hora
  const dateOnlyRegex = /^\d{4}-\d{2}-\d{2}$/;
  
  if (dateOnlyRegex.test(dateString)) {
    // Para formato DATE puro (sem hora), interpreta como data local
    // Evita problemas de timezone ao criar Date diretamente dos componentes
    const [year, month, day] = dateString.split('-').map(Number);
    date = new Date(year, month - 1, day);
  } else {
    // Para timestamps completos, usa o construtor padrão
    date = new Date(dateString);
  }
  
  // Verifica se a data é válida
  if (isNaN(date.getTime())) return '-';
  
  // Formata para DD/MM/YYYY
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  
  const formattedDate = `${day}/${month}/${year}`;
  
  if (includeTime) {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${formattedDate} às ${hours}:${minutes}`;
  }
  
  return formattedDate;
}

/**
 * Retorna a data atual sem horário (meia-noite) no timezone local do navegador.
 * 
 * IMPORTANTE: Use esta função nos filtros para garantir consistência.
 * As comparações devem ser feitas apenas com a parte de data (YYYY-MM-DD),
 * ignorando horários, já que data_prazo no banco é armazenado como DATE.
 * 
 * @returns Date object com horário 00:00:00
 * 
 * @example
 * const hoje = getTodayAtMidnight();
 * // retorna: Date(2025-10-25T00:00:00)
 */
export function getTodayAtMidnight(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/**
 * Remove a parte de horário de um Date, retornando apenas a data à meia-noite.
 * 
 * @param date - Data a ser normalizada
 * @returns Nova data com horário 00:00:00
 * 
 * @example
 * const data = stripTime(new Date('2025-10-25T14:30:00'));
 * // retorna: Date(2025-10-25T00:00:00)
 */
export function stripTime(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}
