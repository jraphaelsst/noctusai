/**
 * Static landing copy (the approved design, verbatim). Everything that varies per
 * deployment — name, price, items, guarantee, author — comes from
 * GET /api/public/settings, NOT from here.
 */
export const FEARS: { q: string; cl: string; p: string }[] = [
  { q: "E se o comprador desistir depois de pagar o sinal?", cl: "Da irretratabilidade e rescisão", p: "Quem desiste perde o sinal a título indenizatório e paga multa rescisória, mais os custos já gerados." },
  { q: "E se o vendedor não entregar as chaves no prazo?", cl: "Da posse sobre o imóvel", p: "Prazo de entrega definido e multa diária por atraso, sem prejuízo da ação de imissão na posse." },
  { q: "E se aparecer processo ou dívida no nome do vendedor?", cl: "Das certidões e documentos", p: "14 certidões e documentos listados um a um, com prazo para apresentar os pendentes e esclarecer apontamentos." },
  { q: "Quem paga ITBI, escritura e registro?", cl: "Dos tributos, taxas e contribuições", p: "Despesas da transmissão, IPTU, condomínio e contas de consumo divididas por escrito, antes e depois da posse." },
  { q: "E se o comprador parar de pagar as parcelas?", cl: "Da confissão de dívida", p: "Na versão parcelada, o saldo vira título executivo extrajudicial, com vencimento antecipado após 30 dias de atraso." },
  { q: "E se o financiamento do banco não sair?", cl: "Do preço e condições de pagamento", p: "Fica claro de quem é a responsabilidade pela obtenção do crédito e qual parcela ele quita." },
];

export const COMPARE: [string, string, string][] = [
  ["Desistência depois do sinal", "Vago ou ausente", "Perda do sinal + multa rescisória"],
  ["Atraso na entrega das chaves", "Sem prazo nem multa", "Prazo + multa diária por atraso"],
  ["Dívidas e processos do vendedor", "\"Livre e desembaraçado\" e só", "14 certidões listadas + prazo para pendências"],
  ["Parcelamento direto", "Uma promessa de pagamento", "Confissão de dívida com força executiva"],
  ["Numeração e referências", "\"Cláusula sétima\" apontando para a oitava", "Cláusulas e parágrafos conferidos"],
];

export const CLAUSES: [string, string][] = [
  ["Do objeto do contrato", "Descrição do imóvel conforme a matrícula"],
  ["Do preço e condições de pagamento", "Parcelas, favorecido e conta"],
  ["Da confissão de dívida", "Vencimento antecipado e força executiva"],
  ["Das certidões e documentos", "14 certidões + pendências com prazo"],
  ["Do ônus sobre o imóvel", "Ações reipersecutórias e evicção"],
  ["Da posse sobre o imóvel", "Prazo e multa diária"],
  ["Do pagamento dos tributos", "IPTU, condomínio, ITBI e registro"],
  ["Da irretratabilidade e rescisão", "Arts. 417 a 420 do Código Civil"],
  ["Da mora e do inadimplemento", "Multa de 2%, juros de 1% e IGPM"],
  ["Declaração das partes", "Lei 7.433/85 e Decreto 93.240/86"],
  ["Da vistoria prévia", "Estado de conservação aceito"],
  ["Autorização de registro", "No Registro de Imóveis competente"],
  ["Cláusula resolutiva expressa", "Art. 474 do Código Civil"],
  ["Da intermediação", "Corretagem e quem paga em caso de rescisão"],
  ["Da eleição do foro", "Comarca e assinaturas com 2 testemunhas"],
];

export const WHO: [string, string][] = [
  ["É corretor", "e quer entregar ao cliente um contrato completo, sem montar do zero a cada venda."],
  ["Está vendendo por conta própria", "e não quer descobrir depois do sinal que faltou uma cláusula."],
  ["Vai comprar um imóvel", "e quer saber o que exigir antes de transferir qualquer valor."],
  ["Vai parcelar direto com o vendedor", "e precisa que a dívida tenha força de cobrança de verdade."],
];

export const STEPS: [string, string][] = [
  ["Garanta o kit", "Pagamento em ambiente seguro, no PIX ou no cartão."],
  ["Receba no e-mail", "Os 3 contratos em Word e PDF chegam logo após a confirmação."],
  ["Preencha o amarelo", "Troque os campos destacados pelos dados do seu negócio e imprima."],
];

export const KIT: { badge: string; title: string; img: "aVista" | "financiado" | "parcelado"; alt: string; bullets: string[] }[] = [
  { badge: "Contrato 01 · 14 cláusulas", title: "À Vista", img: "aVista", alt: "Página do contrato à vista",
    bullets: ["Sinal e princípio de pagamento", "Saldo pago na escritura pública", "Posse vinculada ao pagamento do saldo"] },
  { badge: "Contrato 02 · 14 cláusulas", title: "Financiado", img: "financiado", alt: "Página do contrato financiado",
    bullets: ["Sinal + recursos próprios + financiamento bancário", "Comprador responsável pela obtenção do crédito", "Posse após a liberação do financiamento"] },
  { badge: "Contrato 03 · 15 cláusulas", title: "Parcelado direto com o vendedor", img: "parcelado", alt: "Página do contrato parcelado com confissão de dívida",
    bullets: ["Parcelas com juros pro rata die", "Confissão de dívida com força de título executivo", "Vencimento antecipado e encargos de mora definidos"] },
];

/** FAQ — the guarantee entry is built from settings (see `faqItems`). */
export const FAQ_STATIC_BEFORE: [string, string][] = [
  ["Serve para imóveis em qualquer estado?", "Sim. Cidade, comarca e as certidões estaduais são campos para preencher. Para negócios de valor alto ou situações fora do comum, vale uma revisão rápida por um advogado da sua região."],
  ["Em que formato eu recebo?", "Cada contrato vem em Word (.docx), editável no Word, no Google Docs ou no LibreOffice, e em PDF para conferência."],
  ["Serve quando o comprador vai financiar pelo banco?", "Sim, é para isso que existe a versão Financiado. Ela é o compromisso entre comprador e vendedor, assinado antes do contrato do banco."],
  ["E se forem dois vendedores ou um casal?", "O texto usa VENDEDOR(A) e COMPRADOR(A). Basta ajustar para o plural e repetir a qualificação de cada pessoa."],
  ["O modelo substitui um advogado?", "Não. Ele é um ponto de partida completo e redigido. Inventário, imóvel com penhora ou permuta pedem orientação jurídica específica."],
];

export function faqItems(guaranteeDays: number | null): [string, string][] {
  return guaranteeDays && guaranteeDays > 0
    ? [...FAQ_STATIC_BEFORE, ["Como funciona a garantia?", `Você tem ${guaranteeDays} ${guaranteeDays === 1 ? "dia" : "dias"} a partir da compra para pedir reembolso integral, sem precisar justificar.`]]
    : FAQ_STATIC_BEFORE;
}

export const dias = (n: number): string => `${n} ${n === 1 ? "dia" : "dias"}`;
