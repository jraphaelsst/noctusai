# Gate 1 — pedido à Lastro (CRM "Lais"), pronto para enviar

> **Por que este e-mail existe.** O campo "URL de integração" do Canal Pro aceita
> **uma única URL**. Hoje ela aponta para `prod.lastro.services` e está
> entregando (3× `Sucesso`, 17–18/08/26). A decisão tomada em 2026-08-18 é que a
> NoctusAI passa a ser o endpoint registrado e **repassa cada lead à Lastro**,
> para que o Lais continue funcionando sem interrupção.
>
> Isso torna a NoctusAI responsável pela entrega. O Grupo OLX considera o lead
> entregue assim que respondemos 2xx — não há reenvio depois disso, e não existe
> API de replay. Logo, um repasse que falhe é um lead que a Lastro **nunca**
> recebe. Por isso o repasse será store-and-forward com fila e retentativa
> nossa, e por isso precisamos saber exatamente o que o endpoint deles espera
> antes de construí-lo.
>
> **Destinatário a confirmar.** Não temos o endereço de suporte técnico da
> Lastro verificado — não inventamos um. Use o canal de suporte da conta
> (o mesmo por onde a integração do Lais foi configurada) ou peça ao time deles
> o contato de integrações antes de enviar.

**Para:** `[preencher — suporte técnico / integrações da Lastro]`
**Assunto:** Integração de leads Grupo OLX — mudança de endpoint e repasse para o Lais

---

## As três respostas que mudam o que construímos

| Pergunta | Se a resposta for A | Se a resposta for B |
|---|---|---|
| O endpoint valida o `Authorization: Basic` do GrupoZAP? | repassamos o header verbatim | precisamos da credencial/esquema que eles esperam |
| Existe idempotência por `originLeadId`? | podemos retentar sem medo | a retentativa precisa ser exatamente-uma-vez do nosso lado |
| A Lastro consegue espelhar leads para uma URL nossa? | **nada muda no Canal Pro** — caminho mais seguro | seguimos com o plano de repasse |

A terceira é a que vale perguntar primeiro: se a Lastro puder espelhar, ninguém
precisa mexer no campo do Canal Pro e o risco de perda de lead na troca
desaparece.

---

## Rascunho do e-mail

Olá, tudo bem?

Sou responsável pela tecnologia da **One Consultoria Imobiliária**, cliente de
vocês (CRM "Lais"). Estamos implantando um sistema próprio, a **NoctusAI**, que
passará a receber e trabalhar os leads dos portais do Grupo OLX (ZAP Imóveis,
VivaReal, OLX e ImovelWeb), e queremos fazer essa mudança **sem interromper o
Lais** — a intenção é que vocês continuem recebendo exatamente os mesmos leads
que recebem hoje.

**1. A situação**

No Canal Pro, em Configurações → Integrações → aba Leads → "Receber leads no
CRM", existe **apenas um campo de URL**. Hoje ele está preenchido com o endpoint
de vocês:

```
https://prod.lastro.services/api/public/v1/leads/webhook/grupozap/10b7165c-17a4-4565-acb2-53c9c447...
```

(o identificador final aparece truncado na tela; se precisarmos do valor
completo, conseguimos extrair daí.)

Como o campo é único, não é possível cadastrar dois destinos. Nosso plano é:

1. a NoctusAI passa a ser o endpoint cadastrado no Canal Pro;
2. a cada lead recebido, **repassamos imediatamente a mesma requisição para o
   endpoint de vocês**, preservando o corpo original sem alteração;
3. o Lais segue operando como hoje, sem mudança de configuração do lado de
   vocês.

**2. Por que estamos perguntando antes de fazer**

O Grupo OLX considera o lead entregue assim que o endpoint responde 2xx. Depois
disso não há reenvio, e não existe API de replay: um lead perdido é perdido em
definitivo. Ou seja, a partir da troca **nós passamos a ser responsáveis pela
entrega a vocês**, e não queremos construir esse repasse com base em suposições
sobre o comportamento do endpoint de vocês.

**3. O que precisamos saber**

1. **Autenticação.** O endpoint valida o header `Authorization: Basic` que o
   GrupoZAP envia (o `SECRET_KEY` por CRM)? Se sim, podemos repassar o header
   original sem alteração. Se não — ou se vocês preferirem outro esquema para
   chamadas vindas de nós — qual credencial devemos usar?
2. **Idempotência.** O endpoint deduplica por `originLeadId`? Precisamos saber
   se uma retentativa nossa (em caso de timeout, por exemplo) geraria um lead
   duplicado no Lais.
3. **Contrato aceito.** Devemos repassar o corpo **exatamente** como o GrupoZAP
   envia, ou vocês têm um endpoint de API próprio, com formato próprio, que
   seria o caminho recomendado para uma integração servidor-a-servidor?
4. **Timeout e retentativa.** Qual o tempo máximo de resposta esperado, e vocês
   fazem alguma retentativa própria em caso de falha?
5. **Limites.** Existe algum limite de requisições por segundo ou por dia que
   devamos respeitar?
6. **Allowlist de IP.** Há alguma restrição de origem? Nossas chamadas sairão de
   um IP fixo, e podemos informá-lo caso seja necessário liberá-lo.
7. **A alternativa que preferimos, se existir:** a Lastro consegue **espelhar**
   os leads recebidos para uma URL nossa? Nesse caso a URL do Canal Pro
   permaneceria apontando para vocês, nada precisaria ser trocado, e o risco de
   perda de lead durante a transição deixaria de existir. Se isso for possível,
   é o caminho que preferimos.

**4. Como pretendemos fazer a troca com segurança**

Se seguirmos pelo repasse, a troca será feita assim, e só depois que os itens
acima estiverem respondidos:

- validamos o repasse contra o endpoint de vocês antes de tocar no Canal Pro;
- trocamos a URL no Canal Pro em horário de baixo volume;
- monitoramos as duas pontas nas primeiras horas e comparamos as contagens;
- mantemos o caminho antigo restaurável — basta recolocar a URL original no
  campo, sem depender de nenhuma ação de vocês.

Ficamos à disposição para uma conversa técnica rápida, se for mais prático.

Obrigado!

---

## Depois da resposta — o que vai para onde

| O que chegar | Destino |
|---|---|
| Esquema de autenticação aceito | configuração do encaminhador (slice 3); credencial em `integration_accounts`, nunca no repositório |
| Resposta sobre idempotência | decide se a retentativa é "no mínimo uma vez" ou precisa ser exatamente-uma-vez |
| Contrato/endpoint recomendado | o alvo do encaminhador |
| Confirmação de espelhamento (item 7) | **cancela** a troca de URL no Canal Pro; slice 4 deixa de existir |
| Timeout / limites / IP | orçamento de latência + allowlist |

**Nenhuma dessas respostas conclui o Gate 1 do Grupo OLX.** Este e-mail resolve
o destino do repasse; o `SECRET_KEY` e a homologação continuam sendo assunto do
`gate-1-homologation-request.md`, e os dois correm em paralelo.
