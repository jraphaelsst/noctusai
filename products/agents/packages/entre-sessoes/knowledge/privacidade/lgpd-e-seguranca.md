---
titulo: "Privacidade e segurança (LGPD)"
tipo: fonte
resumo: "Dados só no aparelho; não substitui parecer jurídico."
proveniencia:
  origem: "projects/app/entre-sessoes/guia-diario-entre-sessoes/06-privacidade-e-seguranca/01-lgpd-e-seguranca.md (guia v1.0, 31/10/2026)"
  notas: "Cópia integral."
---
# Privacidade e segurança

Aviso: este documento orienta o desenvolvimento e não substitui parecer jurídico.

## Natureza dos dados

O conteúdo do diário (fatos, lembranças, emoções, respostas) envolve informação sobre a vida psíquica e a saúde da analisanda. A LGPD (Lei 13.709/2018) classifica dado referente à saúde como **dado pessoal sensível** (art. 5º, II), com hipóteses de tratamento restritas (art. 11). O titular tem direitos de acesso, correção, eliminação e portabilidade (art. 18). O agente de tratamento deve adotar medidas de segurança técnicas e administrativas (art. 46).

## Fases 0 e 1 (dados só no aparelho)

- O app não transmite registros a nenhum servidor. Não há conta, cookie de rastreamento ou analytics.
- O envio ao WhatsApp é ato da analisanda. A partir do momento em que Mônica recebe a mensagem, ela trata esses dados como parte do acompanhamento e responde por sua guarda (recomenda-se orientação jurídica sobre a guarda das conversas).
- **Fontes do Google** transmitem o endereço IP da analisanda ao Google a cada carregamento. Um tribunal alemão (LG München I, processo 3 O 17493/20, 20/01/2022) considerou ilícita essa transmissão sem consentimento sob o RGPD. A fase 1 elimina o problema servindo as fontes pelo próprio app.
- A hospedagem não pode incluir scripts de terceiros (anúncios, pixels, chat).

## Fase 2 (servidor)

Antes de qualquer linha de código:

1. Parecer jurídico sobre base legal (consentimento específico e destacado, art. 11, I), papel de controladora de Mônica e operador de infraestrutura.
2. Termo de consentimento e política de privacidade aprovados, com versão registrada (`termo`, `consentimento`).
3. Relatório de impacto à proteção de dados (art. 38) recomendado.
4. Criptografia de ponta a ponta para o conteúdo (ver `03-dados/03-banco-servidor.md`).
5. Hospedagem com dados no Brasil ou com cláusulas de transferência internacional adequadas.
6. Processo de exclusão de conta e de exportação dos dados (portabilidade).

## Segurança do código

- Nunca inserir texto da analisanda com `innerHTML`. Usar `textContent` (o helper `el()` já faz isso). `innerHTML` só para os SVG fixos de `ICONS`.
- Content Security Policy na hospedagem própria: `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'` (ajustar se houver fase 2).
- Links externos com `rel="noopener noreferrer"`.
- Sem `console.log` de conteúdo de registros.
- Dependências: mínimas e fixadas por versão.

## Retenção

- Fases 0 e 1: a analisanda controla tudo; apagar é definitivo.
- Fase 2: registros apagados são purgados em 30 dias; eventos de auditoria sem conteúdo guardados conforme parecer jurídico.
