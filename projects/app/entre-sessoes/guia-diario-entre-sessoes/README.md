# Guia de desenvolvimento: Diário entre sessões

Versão do guia: 1.0, 31/10/2026
Responsável pelo produto: Mônica Tangerino, psicanalista clínica (marca Nós no Limiar)
Destinatário principal: um agente de desenvolvimento (IA ou pessoa) que vai manter e evoluir o app.

## O que é este pacote

Este pacote descreve o app **Diário entre sessões**: para que ele existe, o que ele faz hoje, como os dados nascem, circulam e são guardados, quais regras não podem ser quebradas e como evoluir o app sem perder o que já foi aprovado. O código-fonte atual está na pasta `fonte/`.

## Ordem de leitura obrigatória para o agente

1. `08-instrucoes-para-o-agente/01-instrucoes.md` (como trabalhar e o que nunca fazer)
2. `00-proposito/` (por que o app existe e seus limites clínicos e éticos)
3. `01-produto/` (glossário, escopo, telas, textos oficiais)
4. `05-regras-de-negocio/01-regras.md`
5. `03-dados/` (modelo, schemas, fluxos, armazenamento, banco)
6. `02-arquitetura/` (estado atual, alvo, integração interna, decisões)
7. `04-design/`, `06-privacidade-e-seguranca/`, `07-qualidade/`
8. `08-instrucoes-para-o-agente/02-roteiro.md` e `03-backlog.md` (o que fazer, em que ordem)

## Mapa de pastas

| Pasta | Conteúdo |
|---|---|
| `00-proposito/` | Propósito, público, limites e princípios |
| `01-produto/` | Glossário, escopo, telas e fluxos de uso, textos oficiais, citações |
| `02-arquitetura/` | Estado atual, arquitetura alvo, integração interna entre módulos, registro de decisões |
| `03-dados/` | Modelo de dados, armazenamento local, banco de dados do servidor, fluxos de dados, backup e migrações |
| `03-dados/schemas/` | JSON Schema das estruturas, esquema do IndexedDB e DDL SQL do banco |
| `04-design/` | Design system aplicado, imagens, escrita da interface |
| `05-regras-de-negocio/` | Regras numeradas (RN) que o código precisa respeitar |
| `06-privacidade-e-seguranca/` | LGPD, segurança, retenção |
| `07-qualidade/` | Testes, acessibilidade, critérios de aceite |
| `08-instrucoes-para-o-agente/` | Instruções de trabalho, roteiro por fases, backlog |
| `09-referencias/` | Design system v2.1 da marca e fontes citadas |
| `fonte/` | Código atual (template, script de montagem, imagens, app montado) |

## Situação em 31/10/2026

- Versão oficial publicada: versão 21 (arquivo `fonte/template_v21.html`). É a que as analisandas usam.
- Versão de teste: "Diário teste escuro" (arquivo `fonte/template.html`), mais próxima do mockup da marca, aguardando aprovação de Mônica.
- O app é um único arquivo HTML, sem servidor. Os registros ficam só no navegador da analisanda (localStorage).
- Nenhum dado chega a Mônica a não ser pelo texto que a analisanda decide copiar ou abrir no WhatsApp.

## Ordem de autoridade

1. Instruções expressas de Mônica Tangerino.
2. Paleta oficial e logo original.
3. Design system v2.1 (`09-referencias/design-system-v2.1.md`).
4. Mockup aprovado.
5. Este guia e decisões locais de implementação.

Quando houver conflito, o item anterior prevalece. Desvios já aprovados por Mônica estão listados em `04-design/01-design-system-aplicado.md`.
