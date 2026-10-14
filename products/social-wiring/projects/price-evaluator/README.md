# Avaliador de preço (Sugestão de preço) — social-wiring / Imóveis

Avaliador técnico de preço de venda para os imóveis da One Consultoria (Granja Viana), a ser disparado por um botão "Sugestão de preço" na página de detalhe do imóvel (`pages/ImovelDetalhes.tsx`). Ordem acordada: **mecanismo → contexto e dados → automação**.

| Arquivo | Conteúdo |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | Decisões do dono (append-only) e pendências |
| [`RESEARCH-valuation-methods.md`](RESEARCH-valuation-methods.md) | NBR 14653, fatores IBAPE-SP, AVMs, negócios perdidos como sinal, dados públicos, PTAM/CNAI, abordagem recomendada; sondagem da API Vista; mapa do código do SW |
| [`RESEARCH-valorization-drivers.md`](RESEARCH-valorization-drivers.md) | Vetores de valorização da Granja Viana (Nova Raposo, Linha 22, Linha 4, LUOS…), evidência de efeito, macro, modelo de conhecimento e monitoramento |
| `project-history/roadmaps/sw-price-evaluator-2026-10.md` | Roadmap por fases com gatilhos |

Estado (2026-10-14): fase de entrevista; captura de histórico de preço pedido em `dev` (migração 262); botão de negócio perdido em construção; exploração do Vista aguardando login do dono.
