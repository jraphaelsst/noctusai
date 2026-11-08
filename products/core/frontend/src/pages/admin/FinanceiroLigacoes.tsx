/**
 * "Ligações com o financeiro" -- core-only card (declared seam `overviewFooter` of the seed finance organ): how the
 * NoctusAI books are (not) fed today. It states the TRUTH of the code, it does not build the bridges: owner decision
 * pending (NOC-REMEDIATE[core-finance-billing-bridge], see AdminFinanceiro.tsx).
 */
type Estado = 'Não ligada' | 'Não existe ainda' | 'Já existe';

const LIGACOES: { titulo: string; estado: Estado; descricao: string }[] = [
  {
    titulo: 'Faturamento (Stripe) → Contas a receber',
    estado: 'Não ligada',
    descricao: 'As assinaturas são cobradas, mas nada é lançado aqui. Pendência registrada no código: NOC-REMEDIATE[core-finance-billing-bridge].',
  },
  {
    titulo: 'Funil (card ganho) → Contas a receber',
    estado: 'Não existe ainda',
    descricao: 'Projeto sob medida ganho cria as parcelas a receber. Plano ganho não cria nada aqui: ele vira assinatura e entra pela linha de cima.',
  },
  {
    titulo: 'Uso & Custos (IA, servidores) → Contas a pagar',
    estado: 'Não existe ainda',
    descricao: 'O custo mensal medido em Uso & Custos vira conta a pagar por fornecedor (OpenAI, Anthropic, Hetzner…).',
  },
  {
    titulo: 'Extrato do banco → Conciliação',
    estado: 'Já existe',
    descricao: 'Importação de OFX ou CSV na seção Conciliação.',
  },
];

export function FinanceiroLigacoes() {
  return (
    <section aria-labelledby="financeiro-ligacoes" className="rounded-lg border p-4">
      <h3 id="financeiro-ligacoes" className="mb-3 text-sm font-semibold">Ligações com o financeiro</h3>
      <ul className="space-y-3">
        {LIGACOES.map((l) => (
          <li key={l.titulo} className="grid gap-0.5 border-b pb-3 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">
              <span>{l.titulo}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${l.estado === 'Já existe' ? 'border' : 'bg-amber-500/15'}`}>{l.estado}</span>
            </div>
            <span className="text-sm text-muted-foreground">{l.descricao}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
