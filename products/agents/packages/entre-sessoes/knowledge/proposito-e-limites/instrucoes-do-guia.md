---
titulo: "Instruções do guia para quem desenvolve"
tipo: fonte
resumo: "Nunca, sempre e como falar com Mônica."
proveniencia:
  origem: "projects/app/entre-sessoes/guia-diario-entre-sessoes/08-instrucoes-para-o-agente/01-instrucoes.md (guia v1.0, 31/10/2026)"
  notas: "Cópia integral."
---
# Instruções para o agente

Você vai manter e evoluir o Diário entre sessões. Leia este arquivo inteiro antes de qualquer alteração.

## Seu papel

Desenvolver com cuidado clínico e técnico um app que guarda material íntimo de mulheres em análise. Em caso de dúvida entre velocidade e preservação dos dados da analisanda, escolha preservar.

## Antes de começar qualquer tarefa

1. Leia `README.md`, `00-proposito/`, `05-regras-de-negocio/01-regras.md` e o arquivo da área que vai mexer.
2. Monte o app atual (`fonte/build.py`) e rode as capturas para conhecer o estado de partida.
3. Escreva um plano curto: o que muda, quais regras (RN) afeta, como vai testar, impacto em dados existentes.
4. Se o plano toca qualquer item de "Depende de aprovação" (`01-produto/02-escopo.md`), pare e pergunte a Mônica.

## Nunca

- Enviar, sincronizar ou registrar conteúdo da analisanda fora do aparelho sem gesto dela e sem fase 2 aprovada.
- Adicionar analytics, pixels, anúncios, chat de terceiros ou fontes e scripts externos novos.
- Interpretar, resumir ou classificar o que a analisanda escreveu (com IA ou sem).
- Alterar textos oficiais, perguntas, emoções, despertares ou o texto de segurança sem aprovação.
- Reordenar ou apagar itens de catálogo (quebra registros antigos).
- Usar vocabulário de TCC, "paciente", "terapia" em rótulos, masculino genérico ou emojis.
- Criar cores fora da paleta, ou novas superfícies escuras sem pedido.
- Publicar versão que não passou nos critérios de `07-qualidade/02-criterios-de-aceite.md`.
- Mudar formato de dados sem migração testada e sem preservar os dados existentes.
- Usar `innerHTML` com texto digitado pela analisanda.

## Sempre

- Manter o texto de segurança em todas as abas.
- Tratar falhas de armazenamento com `try/catch` e mensagem clara.
- Testar em 320 px e com teclado.
- Citar a regra (RN) e a decisão (ADR) nas mensagens de commit.
- Atualizar este guia quando uma regra, um schema ou uma decisão mudar.
- Publicar primeiro como versão de teste, separada da versão que as analisandas usam, e só substituir depois da aprovação de Mônica.

## Como falar com Mônica

Ela é psicanalista e autora, não desenvolvedora. Ao pedir decisão:

- Explique em linguagem comum, com o efeito prático para a analisanda.
- Traga de duas a quatro opções e diga qual recomenda e por quê.
- Mostre capturas de tela.
- Respeite as regras de escrita dela: sem travessão, sem "não é X, é Y", sem frases motivacionais, sem emojis, sem elogio de abertura, prosa direta. Ela quer análise crítica: aponte riscos e erros, inclusive dela.

## Fluxo de entrega

1. Branch por tarefa.
2. Implementar, testar, gerar capturas.
3. Publicar como teste.
4. Relatório curto a Mônica: o que mudou, o que ela deve conferir, riscos.
5. Após aprovação, publicar na versão oficial mantendo o mesmo endereço.
