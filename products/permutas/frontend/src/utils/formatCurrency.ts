export const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return `R$ ${value.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

export const formatCurrencyValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '0'
  return value.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}
