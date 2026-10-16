export const brl = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);
export const pct = (n: number) => `${Math.round(n * 10) / 10}%`;
export const opLabel = (o: string) => (o === "aluguel" ? "aluguel" : "compra");
