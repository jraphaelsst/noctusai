---
titulo: "Registro de decisões ADR-01 a ADR-13"
tipo: fonte
resumo: "ADR-03, 04, 11 e 12 nasceram para a versão web."
proveniencia:
  origem: "projects/app/entre-sessoes/guia-diario-entre-sessoes/02-arquitetura/04-decisoes.md (guia v1.0, 31/10/2026)"
  notas: "Cópia integral."
---
# Registro de decisões (ADR)

| # | Decisão | Motivo | Status |
|---|---|---|---|
| ADR-01 | Dados só no aparelho, sem servidor | Privacidade de dados sensíveis; simplicidade; nenhuma obrigação de guarda por terceiro | Vigente |
| ADR-02 | Envio pelo WhatsApp ou cópia, sempre por gesto da analisanda | Canal que Mônica já usa; nada automático | Vigente |
| ADR-03 | HTML único com imagens em base64 | Publicação simples como artifact; um só arquivo | Vigente na fase 0; revisar na fase 1 |
| ADR-04 | Sem framework | Peso mínimo, manutenção simples | Vigente |
| ADR-05 | Nome cadastrado uma vez na abertura | Pedido de Mônica | Vigente |
| ADR-06 | Escolha do passo 7 (`bring`) separada da marcação atual (`levar`) | Permite mudar de ideia na aba Levar sem perder a intenção original | Vigente |
| ADR-07 | Exemplos pré-carregados com aviso para apagar | Mostrar o resultado antes do primeiro uso | Vigente |
| ADR-08 | Corpo do texto em 18 px | Pedido de Mônica ("mantenha a letra"), prevalece sobre os 16 px do design system | Vigente |
| ADR-09 | Cinco abas próprias do diário, e não as quatro do mockup | O mockup é de outro produto da marca | Vigente |
| ADR-10 | Identificadores estáveis para perguntas e despertares (p1..p5, d1..d6) | Evitar corrupção de dados ao reordenar listas | Proposta (fase 1) |
| ADR-11 | IndexedDB, PWA e backup | Evitar perda de dados (Safari, troca de aparelho) | Proposta (fase 1) |
| ADR-12 | Fontes servidas pelo app | Privacidade e funcionamento offline | Proposta (fase 1) |
| ADR-13 | Servidor com criptografia de ponta a ponta | Só se houver sincronização | Em aberto, depende de Mônica |

Para nova decisão: acrescente uma linha, com motivo e status, e cite o número no commit.
