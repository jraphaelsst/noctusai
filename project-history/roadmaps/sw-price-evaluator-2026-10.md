# sw-price-evaluator-2026-10 — "Sugestão de preço" no grupo Imóveis do social-wiring

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: dono pediu (2026-10-14) um avaliador técnico de preço para a One Consultoria (Granja Viana), ligado aos imóveis cadastrados, com botão "Sugestão de preço" na página de detalhe.
> Decision: **hoje — capturar dados (histórico de preço pedido + motivo de perda) e fixar o mecanismo; adiar motores até haver dados.**

## Origin

O dono quer analisar imóvel + região + histórico de negócios bem e mal sucedidos e devolver uma avaliação técnica do preço. A sondagem de 2026-10-14 mostrou que a API Vista não entrega venda, data de venda nem histórico de preço, e que o sync diário sobrescrevia o preço pedido — o histórico estava sendo perdido. Pesquisa e decisões em `products/social-wiring/projects/price-evaluator/` (`RESEARCH-valuation-methods.md`, `RESEARCH-valorization-drivers.md`, `DECISIONS.md`).

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | Histórico estruturado mínimo | ≥ 30 fechamentos próprios com preço pedido + preço fechado + data, num segmento (consulta em `atendimento_negociacao` + backfill) | Mede o fator oferta local e valida o Motor A |
| T2 | Lista mestre de condomínios | Tabela canônica de condomínios com ≥ 80% dos imóveis do catálogo vinculados | Localização vira variável confiável (efeito fixo) |
| T3 | Corredor CNAI identificado | Dono confirma corredor inscrito no CNAI | Libera minuta de PTAM exportável |
| T4 | Dados para hazard | ≥ 6 meses de `imovel_preco_historico` + motivos de perda registrados | Tempo de mercado / anúncio acima do mercado deixam de "mentir" |
| T5 | Dados para regressão | n ≥ 4(k+1) observações num segmento, com variáveis passando nos limites de significância | Piso do Grau II para regressão |
| T6 | Dados para ML | ~1.000+ fechamentos rotulados ou feed externo licenciado | Abaixo disso ML não generaliza nem é defensável |
| T7 | Cenário validado | Backtest interno do bloco (iii) aceito pelo dono | Debate sobre mostrar o cenário ao cliente |

**Today's status**: nenhum disparado. T1/T2 são o caminho crítico.

> **Every slice carries TWO recipes, not one.** Test-recipe (CI) ≠ verify-recipe (estado vivo).

## Phase 0 — captura de dados (EM ANDAMENTO)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P0.1 | Histórico de preço pedido (triggers + baseline) + `atendimentos.motivo_perda` | `products/social-wiring/backend/migrations/262_imovel_preco_historico.sql`, `app/modules/pipeline/routers/boards.py`, `configs.py` | **dev `21edd44f5`** — prod pendente CI | Após aplicar 262 em prod: `select count(*) from social_wiring.imovel_preco_historico where fonte='baseline'` ≈ nº de imóveis com preço; no dia seguinte ao sync, linhas `evento='alteracao'` só para imóveis cujo preço mudou |
| P0.2 | Botão "Marcar como perdida" + lista fixa de motivos + observação | SW FE card do atendimento + BE pipeline | **em construção** (`sw-atendimento-perder-ui`) | Marcar um atendimento de teste como perdido na UI de prod → linha com `status='perdida'`, categoria e observação gravadas |
| P0.3 | Extração do histórico de vendidos/retirados pela tela do Vista (read-only, navegador) | estudo em `products/social-wiring/projects/price-evaluator/` | **bloqueado: login do dono** | Relatório do que a UI expõe (relatórios, filtros, exportação) — sem baixar nada sem permissão |
| P0.4 | Formulário "registrar negócio passado" (backfill de planilhas/Drive/memória) | SW FE+BE (a desenhar, contract-first) | planejado | Corretor registra um negócio antigo; aparece no conjunto de fechamentos do avaliador |
| P0.5 | Lista mestre de condomínios (+ atributos: segurança, lazer, acesso, geocódigo) | SW BE+FE (a desenhar) | planejado | ≥ 80% do catálogo vinculado (T2) |

## Phase 1 — Motor A: comparáveis + fatores (DEFERRED — fires when T1 ∧ T2)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P1.1 | Seleção de comparáveis sem preço como entrada (variante do `similares_service`), kNN ponderado: condomínio → vizinhos → área/padrão/idade, decaimento por recência; exclui deslistados do pool ativo | `app/modules/imovel_hub/` | T1, T2 | Na página de um imóvel real, lista de comparáveis com distância e fatores |
| P1.2 | Fator oferta medido por segmento (mediana fechamento ÷ último pedido, IC) com fallback 0,90 explícito | serviço novo | T1 | Valor exibido + n + IC; fallback sinalizado quando n pequeno |
| P1.3 | Fatores (área, padrão, idade/conservação; testada/profundidade/declive em terreno), cada um limitado a 0,80–1,20 | serviço novo | T1 | Comparáveis fora da faixa descartados e listados |
| P1.4 | Saída: faixa baixo/central/alto, amplitude IC 80%, selo de grau (n ≥ 6 → II, ≥ 12 → III), ressalvas; botão "Sugestão de preço" + card no `ImovelDetalhes` | SW FE+BE, `ai_outputs` | T1 | Botão em prod devolve faixa com comparáveis reais |
| P1.5 | Backtest mensal: MdAPE e acerto ±5/±10% exibidos ao lado da sugestão | job | T1 | Métricas na UI batem com recálculo manual |

## Phase 2 — vetores de valorização, blocos (ii) e (iii) (DEFERRED — fires when P1 shipped)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P2.1 | Tabelas `vetor` + `evidencia` (estágio enum, anéis de efeito, fontes, `revisar_em`), seed com o catálogo V1–V11 | migração + admin UI | P1 | Catálogo visível; vetor vencido aparece "desatualizado" |
| P2.2 | Bloco (ii) fatores de vizinhança (+/−) e bloco (iii) cenário — **somente interno** | SW FE | P1 | Usuário interno vê; nenhum export/relatório ao cliente contém o bloco (iii) |
| P2.3 | Rotina de monitoramento (DO Cotia semanal, ARTESP/Metrô/Sabesp mensal, macro mensal) | job ou MCP tool | P2.1 | Alerta quando fonte monitorada muda |

## Phase 3 — tempo de mercado + anúncio acima do mercado (DEFERRED — fires when T4; adiado por decisão do dono)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | Modelo de hazard em tempo discreto (censura de ativos/retirados) → P(venda 90/180 d) por preço pedido ÷ valor Motor A | serviço | T4 | Preço de anúncio recomendado + dias esperados na UI |
| P3.2 | Sinalização de anúncios acima do mercado | SW FE | T4 + aceite do dono | Lista de candidatos revisada pelo dono antes de ativar |

## Phase 4 — Motor B: regressão hedônica por segmento (DEFERRED — fires when T5)

| P4.1 | Regressão log-linear por segmento; recusa explícita "dados insuficientes" abaixo de 4(k+1) ou com variáveis reprovadas; coeficientes em linguagem simples | serviço | T5 | Resultado só aparece quando os testes passam |

## Phase 5 — ML (DEFERRED — fires when T6)

| P5.1 | Gradient boosting com MdAPE, P(±10%) em holdout temporal, SHAP; nunca motor único | serviço | T6 | Métricas publicadas; comparação com Motor A |

## Phase PTAM — minuta exportável (DEFERRED — fires when T3)

| PT.1 | Export "minuta de PTAM" com campos do Art. 5 da Res. COFECI 1.066/2007 para corretor CNAI revisar e assinar | SW FE+BE | T3 + P1 | Minuta gerada para um imóvel real, revisada pelo corretor |

## Anti-goals (explicit non-goals)

- ❌ Ajustar o valor de mercado por vetores de valorização futura. Conta duas vezes e vira "valor especial" pela NBR.
- ❌ Mostrar o cenário de valorização ao cliente antes de validado (decisão do dono 2026-10-14).
- ❌ Detectar anúncio acima do mercado antes de T4 (mentiria com poucos dados).
- ❌ Raspar portais (Zap/VivaReal/OLX) sem parecer jurídico.
- ❌ Fallback silencioso: sem dados → "dados insuficientes", nunca um número inventado.
- ❌ Chamar a saída de "laudo NBR 14653" (território de engenharia); é sugestão ou minuta de PTAM.
- ❌ Usar Planta Genérica de Valores/IPTU como piso de valor.

## Open questions (to revisit at trigger time)

- **Q1**: Lista exata de motivos de perda — a v1 é proposta da engenharia; dono pode ajustar.
- **Q2**: Licenciar feed externo (DataZap) ou inserir comparáveis manualmente?
- **Q3**: Pedido LAI de dados de ITBI a Cotia e Carapicuíba?
- **Q4**: Política do fator oferta (janela, frequência de re-medição).
- **Q5**: Apresentação da faixa: IC 80%, arbítrio ±15%, ou ambos; preço "para vender em X dias"?
- **Q6**: Registrar preço/data de compra do vendedor (sinal Genesove-Mayer) com consentimento LGPD?
- **Q7**: Horizonte do cenário (3/5/10 anos) e taxa de desconto.
- **Q8**: Como comunicar vetores negativos (pedágio, obras, verticalização) ao vendedor.
- **Q9**: Padrão construtivo não existe como coluna — capturar na captação? Com que escala?
- **Q10**: Comprar NBR 14653-1/-2 e norma IBAPE-SP para confirmar limiares [NV].

## Decision log

- **2026-10-14**: usos = preço de captação, argumento com proprietário, minuta PTAM; anúncio acima do mercado adiado.
- **2026-10-14**: segmentos casa em condomínio / terreno / apartamento primeiro; só venda.
- **2026-10-14**: registrar histórico de preço pedido agora (P0.1, migração 262, `21edd44f5`).
- **2026-10-14**: API Vista sem histórico (sondagem); exploração da tela do Vista pelo navegador com o "vai" do dono — aguardando login.
- **2026-10-14**: valorização futura separada do valor de mercado (3 blocos); cenário só interno até validado.
- **2026-10-14**: botão "Marcar como perdida" com lista fixa de motivos aprovado (P0.2).

## Retrospective (filled at first trigger fire)

*A preencher quando T1/T2 dispararem.*

## Composes with

- `project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md` — modelo de dados do espelho Vista.
- `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` — superfície da API Vista e perguntas Tier-2.
- `KB § PATTERNS/frontend/product-internal-wiring.md` — o botão precisa mostrar dado real.
- `products/erp-imobiliario/backend/app/services/ai_service.py` (`suggest_price`) — template adormecido.

## File trail

- `products/social-wiring/projects/price-evaluator/README.md`
- `products/social-wiring/projects/price-evaluator/DECISIONS.md`
- `products/social-wiring/projects/price-evaluator/RESEARCH-valuation-methods.md`
- `products/social-wiring/projects/price-evaluator/RESEARCH-valorization-drivers.md`
- `products/social-wiring/backend/migrations/262_imovel_preco_historico.sql`
- This doc.
