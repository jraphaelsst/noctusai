# Contrato de Compra e Venda de Imóvel — modelo genérico (produto digital)

Template sem dados reais, para venda como produto digital (pedidos recebidos no Instagram do Gilson).

| Arquivo | Variante | Cláusulas |
|---|---|---|
| `Contrato-Compra-e-Venda-Imovel-A-Vista.*` | Sinal + saldo na escritura | 14 |
| `Contrato-Compra-e-Venda-Imovel-Financiado.*` | Sinal + recursos próprios + financiamento bancário | 14 |
| `Contrato-Compra-e-Venda-Imovel-Parcelado-Direto.*` | Sinal + parcelas direto ao vendedor, com confissão de dívida | 15 |

`.docx` é editável (campos `[ASSIM]` destacados em amarelo); `.pdf` é a versão ABNT.

## Proveniência

Gerado pelo próprio gerador de contratos do social-wiring
(`products/social-wiring/backend/app/modules/card_hub/contrato_gerador/`): a redação de
`modelo_texto.TEMPLATE`, a numeração de cláusulas/parágrafos de `numeracao.py`, a face
da página de `documento.py` e o PDF ABNT do seed. Nenhum `DadosContrato` é carregado —
cada dado vira um campo `[CAMPO]`, então nenhum dado pessoal dos contratos assinados
(gitignored em `products/social-wiring/contracts/`) chega a estes arquivos. A lista de
certidões é a do escritório (`frases.CERTIDOES`), com "Estado de São Paulo" generalizado
para "Estado de [UF]".

Regenerar (a partir da raiz do repo):

```bash
PYTHONPATH=products/social-wiring/backend:seed/lib/backend \
  venv/bin/python projects/store/contrato/gerar_modelo.py projects/store/contrato
```

## Antes de vender

- Autorização do escritório/Gilson para comercializar a redação.
- Uma revisão jurídica da versão genérica.
