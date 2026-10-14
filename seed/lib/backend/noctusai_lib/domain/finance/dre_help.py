"""Plain-language pt-BR help for every DRE line (D47) -- shipped BY THE API, not only as UI copy.

Each entry: `what` (o que é, in plain words), `example`, `source` (citation, with its evidence tier from
`KB § PATTERNS/finance/dre-structure.md`). The sources are the KB document's; nothing here is invented -- a line
whose placement is an open question says so.
"""
from __future__ import annotations

from .types import DreLine

KB_DOC = "KB § PATTERNS/finance/dre-structure.md"

LINE_HELP: dict[str, dict[str, str]] = {
    DreLine.GROSS_REVENUE.value: {
        "label": "Receita bruta",
        "what": "Tudo o que a loja vendeu no período, antes de qualquer desconto ou imposto. Inclui os juros de parcelamento cobrados do comprador.",
        "example": "Vendas de produtos e serviços; juros de parcelamento pagos pelo cliente no cartão.",
        "source": "NBC TG 1002 §5.1(a) [norma]; juros de parcelamento compõem a receita bruta: Solução de Consulta Cosit 94/2025 [órgão oficial].",
    },
    DreLine.DEDUCTIONS.value: {
        "label": "(-) Deduções da receita",
        "what": "O que sai da receita bruta antes de virar receita líquida: estornos, cancelamentos, devoluções, descontos incondicionais e os impostos sobre a venda (o DAS inteiro, no Simples Nacional).",
        "example": "Reembolso de um pedido; DAS do Simples; ISS e ICMS.",
        "source": "NBC TG 1002 §23.2 e §29.3; ITG 1000 Anexo 3 (nota do Simples Nacional) [norma]. Chargeback aqui é escolha provisória (sem fonte brasileira encontrada).",
    },
    DreLine.COST_OF_SALES.value: {
        "label": "(-) Custo das vendas",
        "what": "O custo direto do que foi vendido: mercadoria revendida, insumos e terceiros que entregam o produto. Sem controle de estoque, usamos as compras do mês como aproximação.",
        "example": "Compra de mercadoria para revenda; freelancer que produz o item vendido.",
        "source": "NBC TG 1002 §5.1(d) [norma]; a aproximação por compras do mês está em aberto — confirme com seu contador.",
    },
    DreLine.SELLING_EXPENSES.value: {
        "label": "(-) Despesas com vendas",
        "what": "O que você gasta para vender: anúncios, frete de envio, comissões e as taxas do cartão/gateway cobradas a cada venda.",
        "example": "Taxa do gateway (MDR), marketing, frete de envio, comissão de marketplace.",
        "source": "Prática contábil [publicação profissional]. Taxa de gateway aqui é escolha provisória: parte da prática a classifica como despesa financeira.",
    },
    DreLine.ADMINISTRATIVE_EXPENSES.value: {
        "label": "(-) Despesas administrativas",
        "what": "O custo de manter a loja funcionando, venda você ou não: aluguel, salários, assinaturas, contabilidade. O DAS-MEI também entra aqui (valor fixo mensal).",
        "example": "Aluguel, software e assinaturas, contador, DAS-MEI.",
        "source": "Prática contábil [publicação profissional]; DAS-MEI como custo fixo: Sebrae-PR, 'Como administrar um pequeno negócio – MEI' [Sebrae].",
    },
    DreLine.OTHER_OPERATING.value: {
        "label": "(+/-) Outras receitas e despesas operacionais",
        "what": "O que é do negócio mas não se encaixa nas linhas acima, para mais ou para menos.",
        "example": "Outras receitas; outras despesas.",
        "source": "NBC TG 1002 §5.1 [norma]. Perda por fraude/chargeback aqui é alternativa (em aberto).",
    },
    DreLine.FINANCIAL_REVENUE.value: {
        "label": "(+) Receitas financeiras",
        "what": "Dinheiro que o dinheiro rendeu: rendimentos de aplicação e juros de mora recebidos de clientes em atraso.",
        "example": "Rendimento da conta remunerada; juros de mora recebidos.",
        "source": "NBC TG 1002 §5.1 [norma]; juros de mora ficam fora da receita bruta [órgão oficial].",
    },
    DreLine.FINANCIAL_EXPENSES.value: {
        "label": "(-) Despesas financeiras",
        "what": "O custo do dinheiro: tarifas bancárias, antecipação de recebíveis, juros e multas pagos.",
        "example": "Tarifa bancária; taxa para antecipar o recebimento do cartão.",
        "source": "Prática contábil [publicação profissional]; antecipação como despesa financeira é consenso.",
    },
    DreLine.INCOME_TAXES.value: {
        "label": "(-) IRPJ e CSLL",
        "what": "Imposto sobre o lucro. Lucro Presumido/Real sempre; no Simples só quando você divide o DAS informando o percentual de repartição do seu anexo.",
        "example": "IRPJ/CSLL do Lucro Presumido; parcela de IRPJ/CSLL do DAS dividido.",
        "source": "NBC TG 1002 §29 e NBC TG 1001 §29.2/29.4 [norma].",
    },
    DreLine.UNCLASSIFIED.value: {
        "label": "Sem classificação",
        "what": "Valores cuja categoria ainda não tem uma linha da DRE. Eles NÃO entram no resultado até você classificar a categoria — nada é descartado em silêncio.",
        "example": "Uma categoria nova que você criou e ainda não mapeou.",
        "source": "Regra do produto (D47): aparece à parte e gera aviso.",
    },
}

SUBTOTAL_HELP: dict[str, dict[str, str]] = {
    "net_revenue": {"label": "= Receita líquida", "what": "Receita bruta menos as deduções.", "source": "NBC TG 1002 §5.1(c) [norma]."},
    "gross_result": {"label": "= Lucro bruto", "what": "Receita líquida menos o custo das vendas: quanto sobra de cada venda antes de manter a loja.", "source": "NBC TG 1002 §5.1(e) [norma]."},
    "result_before_financial": {"label": "= Resultado antes do financeiro", "what": "Lucro bruto menos despesas com vendas e administrativas, mais/menos outras operacionais.", "source": "NBC TG 1002 §5.1(i) [norma]."},
    "result_before_income_taxes": {"label": "= Resultado antes dos tributos sobre o lucro", "what": "Resultado operacional mais receitas financeiras menos despesas financeiras.", "source": "NBC TG 1002 §5.1(l) [norma]."},
    "net_result": {"label": "= Resultado líquido", "what": "O que sobrou depois de tudo, inclusive IRPJ/CSLL: o lucro (ou prejuízo) do período.", "source": "NBC TG 1002 §5.1(n) [norma]."},
}

#: Statement order: ("line", DreLine value) or ("subtotal", key).
STATEMENT_ORDER: tuple[tuple[str, str], ...] = (
    ("line", DreLine.GROSS_REVENUE.value),
    ("line", DreLine.DEDUCTIONS.value),
    ("subtotal", "net_revenue"),
    ("line", DreLine.COST_OF_SALES.value),
    ("subtotal", "gross_result"),
    ("line", DreLine.SELLING_EXPENSES.value),
    ("line", DreLine.ADMINISTRATIVE_EXPENSES.value),
    ("line", DreLine.OTHER_OPERATING.value),
    ("subtotal", "result_before_financial"),
    ("line", DreLine.FINANCIAL_REVENUE.value),
    ("line", DreLine.FINANCIAL_EXPENSES.value),
    ("subtotal", "result_before_income_taxes"),
    ("line", DreLine.INCOME_TAXES.value),
    ("subtotal", "net_result"),
)

TITLE_MEI = "DRE gerencial (MEI não é obrigado a ter DRE)"
TITLE_DEFAULT = "Demonstração do Resultado do Exercício (DRE)"

__all__ = ["KB_DOC", "LINE_HELP", "STATEMENT_ORDER", "SUBTOTAL_HELP", "TITLE_DEFAULT", "TITLE_MEI"]
