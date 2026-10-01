# Relatório de Desempenho (QuintoAndar → imobiliária) — anatomy

Observed 2026-10-01 from a downloaded HTML file `OneConsultoriaImobiliaria.html`
(`<title>Relatório de Desempenho</title>`, header "Relatório de Desempenho -
OneConsultoriaImobiliaria - 2026-10-01"). It is a self-contained static page (inline CSS/JS,
no network calls); everything below is `[observado]` from that file. How the file reaches the
agency (e-mail? portal download?) was not observed — open question.

## Layout

Three tabs (`.tab-content`): **Oportunidades em Venda** (`#tab-sale`) · **Oportunidades em
Locação** (`#tab-rent`) · **Redução de Preço** (`#tab-reducao`, table `table-reducao-preco` — not mapped yet).

Venda and Locação share the same shape: an intro ("A seguir, apresentamos as oportunidades de
publicação segmentadas por tipo. Caso queira descartar algum dos imóveis listados, o descarte
deve ser feito via CRM … ou entrando em contato com o time de CX" — the CX link is a WhatsApp
`api.whatsapp.com/send/?phone=…` URL), three scorecards, then three tables:

| Section | Table id (Venda / Locação) | Section text (verbatim, abridged) |
|---|---|---|
| Correção de Dados | `table-correcao` / `table-correcao-rent` | "Os imóveis abaixo precisam de correção no CRM. A coluna de Oportunidade indica quais dados devem ser revisados e ajustados no CRM." |
| Disponibilidade | `table-disponibilidade` / `table-disponibilidade-rent` | "o QuintoAndar não conseguiu contato com o proprietário para confirmar a disponibilidade e a autorização de publicação no Marketplace. Entre em contato com o proprietário e confirme a disponibilidade na Central da Imobiliária ou entre em contato com o suporte." |
| Qualidade de Imagens | `table-imagem` / `table-imagem-rent` | "Os imóveis abaixo apresentam baixa qualidade de imagens ou uso de imagens ilustrativas. Remova as fotos fora do padrão dentro do seu CRM ou agende novas fotos." |

## Columns (all three section tables)

`Concluído?` (checkbox, `data-id` = CRM code; client-side only: the script has no fetch/XHR and no localStorage, so ticks are lost on reload) · `ID
Imobiliária` (CRM/Vista code, e.g. `ONE…`, `CA…`, `AP…`) · `Parceiro` (agency name) · `ID QA`
(QuintoAndar id, 9 digits; "Não Possui" when the listing never got one) · `Oportunidade`
(reason text, expandable) · `Endereço` (street + number) · `Preço` (pt-BR `1.234,56`; rent
value on the Locação tab) · `Nome Captador` · `Nº Captador` (`+55…`) · `Período de Envio`
(bucket: "Até 7 dias" · "de 7 a 30 dias" · "de 30 a 90 dias" · "Mais de 90 dias").

A second header row holds client-side filters (Todos/Marcados/Não Marcados, text boxes,
price Mín/Máx, period select) → `applyAllFilters('<table id>')`.

## Values seen on 2026-10-01 (snapshot — will move)

- Venda scorecards: Correção 4 · Disponibilidade 18 · Imagens 7.
- Locação scorecards: Correção 6 · Disponibilidade 48 · Imagens 1.
- Disponibilidade `Oportunidade` text: only "Não conseguimos contato com o proprietário"
  (all 18 venda + all 48 locação rows). All rows "de 7 a 30 dias".
- Correção `Oportunidade` texts: "tipo de telefone inválido", "falta telefone da pessoa
  proprietária", "número de quartos ou banheiros inválido" (meaning of "tipo de telefone
  inválido" → memory `vista-crm-data-conventions` rule 4).
- No CRM code appears in both the Venda and Locação Disponibilidade tables.

## How to read it into data

Parse by table id; each `<tbody><tr>` has 10 `<td>`, the first is the checkbox. Strip tags
and the `▼` expand glyph. Snapshot of the 2026-10-01 Locação Disponibilidade table, enriched
with Vista status, lives in `../reports/` (codes + listing fields only — no names/phones,
per AGENT.md rule 4).
