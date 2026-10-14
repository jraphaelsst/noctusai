# Avaliador de preço — log de decisões do dono

> Append-only. Cada linha: data · decisão · origem. Decisões aqui NÃO se reabrem sem o dono.
> Contexto: entrevista de 2026-10-14 (sessão de construção do contexto do "Sugestão de preço" no grupo Imóveis do SW).

## 2026-10-14 — rodada 1 (propósito e escopo)

- **Usos da sugestão:** (a) corretor define o preço de captação/anúncio; (b) argumento com o proprietário; (c) PTAM formal (minuta).
- **Detecção de anúncio acima do mercado: ADIADA.** Palavras do dono: sem contexto e dados suficientes ela "mentiria no primeiro momento"; só depois que o avaliador prever preços com base em dados.
- **Segmentos primeiro:** casa em condomínio, terreno, apartamento. Outros (comercial/rural) depois.
- **Só venda.** Locação fica para depois (método e mercado diferentes).
- **Histórico de negócios:** está no Vista + planilhas/Drive + "na cabeça das pessoas" — "muito desorganizado, precisamos estruturar".
- **Vista:** pesquisar a API e dizer se dá para acessar o histórico; navegador (browser MCP) **só com o "vai" do dono**.

## 2026-10-14 — rodada 2 (dados e mecanismo)

- **Registro de histórico de preço pedido: APROVADO e implementado.** Migração SW 262 `imovel_preco_historico` (triggers em `imoveis` e `imovel_captacao`, baseline), + `atendimentos.motivo_perda`; integrado em `dev` em `21edd44f5`. Liberação para prod pelo fluxo normal após CI verde (migração 262 antes/junto da imagem SW).
- **Achado API Vista (sondagem 2026-10-14):** sem histórico, sem negociações/propostas/vendas, sem campos de venda → ver `RESEARCH-valuation-methods.md` Anexo A.
- **Caminho Vista escolhido: navegador na tela do Vista** (somente leitura). Bloqueado aguardando o dono fazer login em `https://crmx.novovista.com.br/` (Vista agora é "Loft/CRM"); nenhuma exportação/download sem permissão explícita.
- **Corretor inscrito no CNAI para assinar PTAM:** dono **não sabe** → pendência do dono (consultar cofeci.gov.br/cnai ou perguntar aos corretores). Até lá o PTAM é só minuta.
- **Vetores de preço na visão do dono:** qual condomínio; área construída e terreno; padrão e conservação; acesso/distâncias; **+ valorização futura** por projetos externos, políticas públicas, tendências e ganhos financeiros → pesquisado em `RESEARCH-valorization-drivers.md`. A ordem de peso será testada contra os dados.

## 2026-10-14 — rodada 3 (valorização e perdas)

- **Valorização futura SEPARADA do valor de mercado.** Saída em 3 blocos: (i) valor de mercado NBR (só comparáveis, nunca ajustado por vetores); (ii) fatores de vizinhança em curso (+/−, com estágio e fonte); (iii) cenário de valorização como nota separada.
- **Botão "Marcar como perdida" no card do atendimento: APROVADO**, com **lista fixa de motivos** + observação livre (base para usar negócios perdidos como sinal). Em construção (slice `sw-atendimento-perder-ui`).
- **Cenário de valorização (bloco iii): SÓ INTERNO até ser validado; depois debatemos mostrar ao cliente.**

## Pendências do dono

- Fazer login no Vista/Loft CRM para a exploração read-only do histórico.
- Verificar se algum corretor da One está no CNAI.
- (Futuro) Comprar NBR 14653-1/-2 e a norma IBAPE-SP para confirmar limiares [NV].
