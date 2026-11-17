# S0 — Legal review for the NoctusAI sales Julia (legal-advisor, 2026-11-17)

> This is advice, not legal counsel. An OAB lawyer approves the final notice text, decides how the
> controller passes from the natural person to the company when the CNPJ opens, and decides whether any
> client counts as a consumer. Sources are cited through the repo legal canon (`lgpd-privacy-program.md`,
> `consumer-ecommerce.md`). They were not re-checked on Planalto today, so re-verify before publishing.

## 1 · Controller
- **Before the CNPJ:** the owner, as a natural person, is the controller (LGPD art. 5 VI; art. 4 I, since
  the purpose is economic). This is already reflected in `seed/framework/frontend/src/content/consent.ts:20-27`.
- **The notice must name:** the controller (full name), a contact email, and the encarregado (DPO)
  (arts. 9 III, 41). No CPF or home address.
- **Deadlines:** do not count on the small-agent doubled deadlines (AI = emerging tech, possibly high risk,
  Res. CD/ANPD 2/2022 art. 4).
- **When the CNPJ opens:** publish notice v2 with the razão social, CNPJ and address. Tell existing leads
  about the change of controller, and record the succession. Contract signing waits for the CNPJ.

## 2 · Privacy notice v1 (published at `/privacidade/:slug` via `PUT /api/julia/agente/aviso`)
Placeholders: `[Nome completo]`, `[e-mail]`, `[data]`, the database region, the AI provider(s).

**Aviso de Privacidade — Julia, assistente virtual da NoctusAI** (vigente desde [data]; versão 1)

**Quem trata seus dados.** Controlador: [Nome completo], pessoa física, que opera a NoctusAI enquanto a empresa não tem CNPJ. Contato e encarregado: [e-mail]. Quando a empresa for constituída, este aviso será atualizado e você será informado.

**O que coletamos.** Seu nome, número de WhatsApp, as mensagens que você nos envia e as respostas sobre sua empresa: segmento, tamanho da equipe, ferramenta atual, volume de leads, principais dificuldades, quem decide e prazo. Não precisamos de dados sensíveis (saúde, religião, etc.) nem de documentos: por favor, não envie.

**Para quê.** Entender sua necessidade e agendar uma conversa com [Nome]. A Julia não vende, não informa preços e não fecha contratos.

**Base legal.** Procedimentos preliminares a um contrato, a seu pedido (LGPD art. 7º, V): você iniciou o contato. Lembretes sobre a conversa agendada usam nosso legítimo interesse (art. 7º, IX), e você pode recusá-los a qualquer momento.

**Quem vê seus dados.** [Nome] e prestadores que operam o serviço: hospedagem do banco de dados ([região a confirmar]), servidor do WhatsApp e provedores de IA que geram as respostas ([provedor(es) — confirmar]). Alguns ficam fora do Brasil, sobretudo nos EUA. Essa transferência internacional se apoia em cláusulas-padrão contratuais da ANPD (Res. CD/ANPD 19/2024). Você pode pedir cópia das cláusulas. Não vendemos seus dados e não os usamos para treinar modelos.

**Por quanto tempo.** Se não houver contratação, até 12 meses após o último contato; depois, excluímos ou anonimizamos. Se você virar cliente, guardamos pelo prazo do contrato e das obrigações legais.

**Decisões automatizadas.** A Julia só organiza as informações. Quem decide sobre a conversa é uma pessoa.

**Seus direitos (art. 18).** Confirmação, acesso, correção, anonimização ou exclusão, portabilidade, informação sobre compartilhamento e oposição. Peça pelo [e-mail]; respondemos em até 15 dias. Você também pode peticionar à ANPD (gov.br/anpd).

**Como parar.** Responda **PARAR** a qualquer momento: a Julia não envia mais nada, e seus dados são excluídos se você pedir.

Open items:
- the 12-month retention period is provisional;
- the AI provider(s) and the database region need confirming, along with whether the SCCs are in those
  contracts;
- whether art. 33 IX is enough on its own;
- a written legitimate-interest test for the reminders.

## 3 · Microcopy
- **Under the CTA:** "Você vai conversar no WhatsApp com a Julia, assistente virtual (IA) da NoctusAI, que fará algumas perguntas para agendar sua conversa. Veja como tratamos seus dados no [Aviso de Privacidade]."
- **Julia's first message:** "Oi! Sou a Julia, assistente virtual (IA) da NoctusAI, não uma pessoa. Vou fazer algumas perguntas rápidas para marcar sua conversa com o [Nome]. Como tratamos seus dados: [URL]/privacidade/[slug]. Para parar a qualquer momento, responda PARAR."
- "PARAR" must be on the deterministic STOP floor. This is forwarded to the `julia-lais-study-agents` slice.

## 4 · Consumer law
- **Decreto 7.962 art. 2 (supplier identity):** does not apply yet, because there is no priced offer and
  no closing. It applies from the moment there is a checkout. LGPD art. 9 III still requires naming the
  controller.
- **The CDC applies anyway**, even when selling to businesses. Art. 29 extends consumer protection to
  everyone exposed to the advertising, so arts. 30, 31, 36, 37 and 39 apply: no claimed features that
  don't exist. Use the spec's claimable-vs-planned table.
- **Self-employed brokers and small agencies** may count as consumers (STJ mitigated finalism).
- **The CONAR code** applies to the advertising.
