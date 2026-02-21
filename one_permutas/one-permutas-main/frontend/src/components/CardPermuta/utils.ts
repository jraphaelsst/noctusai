export const getTipoImovel = (tipo: string) => {
  if (tipo === 'a') {
    return 'Apartamento'
  }
  if (tipo === 'c') {
    return 'Casa'
  }
  if (tipo === 't') {
    return 'Terreno'
  } else {
    return 'Tipo não cadastrado'
  }
}

export const getZona = (tipo: string) => {
  if (tipo === 'l') {
    return 'Leste'
  }
  if (tipo === 'n') {
    return 'Norte'
  }
  if (tipo === 'o') {
    return 'Oeste'
  }
  if (tipo === 's') {
    return 'Sul'
  } else {
    return 'Zona não cadastrada'
  }
}

export const getTipoAutomovel = (tipo: string) => {
  if (tipo === 'c') {
    return 'Carro'
  }
  if (tipo === 'm') {
    return 'Moto'
  }
  if (tipo === 's') {
    return 'SUV'
  } else {
    return 'Tipo não cadastrado'
  }
}

export const getMotor = (tipo: string) => {
  if (tipo === 'a') {
    return 'Álcool'
  }
  if (tipo === 'e') {
    return 'Elétrico'
  }
  if (tipo === 'f') {
    return 'Flex'
  }
  if (tipo === 'g') {
    return 'Gasolina'
  }
  if (tipo === 'h') {
    return 'Híbrido'
  } else {
    return 'Tipo não cadastrado'
  }
}
