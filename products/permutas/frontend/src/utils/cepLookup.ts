export type CepData = {
  cep: string
  logradouro: string
  complemento: string
  bairro: string
  localidade: string
  uf: string
  erro?: boolean
}

export const fetchCepData = async (cep: string): Promise<CepData | null> => {
  const cleanCep = cep.replace(/\D/g, '')
  
  if (cleanCep.length !== 8) {
    return null
  }

  try {
    const response = await fetch(`https://viacep.com.br/ws/${cleanCep}/json/`)
    const data: CepData = await response.json()
    
    if (data.erro) {
      return null
    }
    
    return data
  } catch (error) {
    console.error('Erro ao buscar CEP:', error)
    return null
  }
}

export const formatCep = (value: string): string => {
  const cleanValue = value.replace(/\D/g, '')
  if (cleanValue.length <= 5) {
    return cleanValue
  }
  return `${cleanValue.slice(0, 5)}-${cleanValue.slice(5, 8)}`
}
