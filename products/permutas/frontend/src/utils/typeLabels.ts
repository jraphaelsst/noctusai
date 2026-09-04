export const TIPO_IMOVEL_LABELS: Record<string, string> = {
  'a': 'Apartamento',
  'c': 'Casa',
  't': 'Terreno',
  'ch': 'Chácara',
  'co': 'Comercial'
}

export const TIPO_AUTOMOVEL_LABELS: Record<string, string> = {
  'c': 'Carro',
  'm': 'Moto',
  'cm': 'Caminhão'
}

export const ZONA_LABELS: Record<string, string> = {
  'n': 'Norte',
  's': 'Sul',
  'l': 'Leste',
  'o': 'Oeste'
}

export const MOTOR_LABELS: Record<string, string> = {
  'a': 'Álcool',
  'e': 'Elétrico',
  'f': 'Flex',
  'g': 'Gasolina',
  'h': 'Híbrido'
}

export const getTipoImovel = (tipo: string): string => {
  return TIPO_IMOVEL_LABELS[tipo] || tipo || '-'
}

export const getTipoAutomovel = (tipo: string): string => {
  return TIPO_AUTOMOVEL_LABELS[tipo] || tipo || '-'
}

export const getZona = (zona: string): string => {
  return ZONA_LABELS[zona] || zona || '-'
}

export const getMotor = (motor: string): string => {
  return MOTOR_LABELS[motor] || motor || '-'
}
