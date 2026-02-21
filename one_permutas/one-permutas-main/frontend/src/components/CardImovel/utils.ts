export const getTipo = (tipo: string) => {
  if (tipo === 'c') {
    return 'Casa'
  }
  if (tipo === 'a') {
    return 'Apartamento'
  }
  if (tipo === 't') {
    return 'Terreno'
  }
}
