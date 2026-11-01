# Testes

Ferramenta: Playwright com Chromium (e WebKit para Safari quando possível). Viewports: 320x640, 390x844, 430x932, 768x1024.

## Rotina mínima a cada alteração

1. `python3 build.py && node --check check.js`
2. Rodar a suíte de ponta a ponta.
3. Capturas das telas: Abertura, Semana (cada filtro), passos 1 a 7, Levar, Resumo, Como usar. Conferir visualmente.
4. Conferir peso do arquivo final (≤ 400 KB).

## Casos de ponta a ponta

| # | Caso | Regras |
|---|---|---|
| E1 | Primeira visita: abertura aparece; sem nome mostra erro; com nome vai à Semana e saúda pelo nome | RN-01 a RN-03 |
| E2 | Segunda visita: abertura não aparece; campo nome oculto | RN-01, RN-03 |
| E3 | Exemplos existem; apagar com confirmação; recarregar não traz de volta | RN-16 |
| E4 | Registrar sem passo 1 mostra erro; sem pergunta no passo 5 mostra erro; sem escolha no 7 mostra erro | RN-05 |
| E5 | Salvar com Sim: aviso vinho, cartão com "Levar à análise", aparece marcado na aba Levar | RN-06, RN-13 |
| E6 | Desmarcar na aba Levar e recarregar: continua desmarcado; filtro Levar não mostra | RN-08 |
| E7 | Busca "frustracao" encontra registro com "Frustração" | RN-11 |
| E8 | Texto para Mônica: ordem cronológica, campos vazios omitidos, sem exemplos | RN-17, RN-19 |
| E9 | Texto longo: botão do WhatsApp desabilitado | RN-21 |
| E10 | Resumo com registros de 8 dias atrás: não contam | RN-23 |
| E11 | Aba anônima simulada (localStorage lançando erro): aviso aparece, app não quebra | |
| E12 | Navegação só por teclado em todas as abas; foco visível | |
| E13 | Zoom de texto 200%: nada cortado, botões acessíveis | |
| E14 | Migração v1→v2 (fase 1) preserva marcações e significado das perguntas | ver 03-dados |
| E15 | Backup exportado e importado em perfil limpo reproduz os registros | fase 1 |

## Testes de unidade (fase 1)

Funções puras de `dominio/` e `dados/legado.js` com casos de borda: lista vazia, registro sem `levar`, registro com `levar` false e `bring` sim, horário 23h59 e 00h00 na janela de 7 dias, emoções com empate.
