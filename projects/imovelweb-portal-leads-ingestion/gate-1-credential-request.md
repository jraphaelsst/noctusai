# Gate 1 — credential request (ready to send)

> **Why this exists now.** Gate 1 is blocked on the vendor, and vendor turnaround
> is the longest pole in the project — days, not hours, and the sandbox is only up
> ~07:00–21:00 UTC-3. Everything else (Phases A, B) can be built against the
> transcribed contract while this is in flight, so the email should go out
> **before** the code is finished, not after.
>
> **One decision before sending** — see "The ReadOnly call" below. The draft asks
> for a ReadOnly integration. If you want listing events (`AVISO_*`), change one
> line; the consequence is spelled out.

---

## The ReadOnly call

The vendor delivers `AVISO_ACTIVIDAD` / `AVISO_ESTADO_PUBLICACION` /
`AVISO_CALIDAD` / `CREDITO` **only to Read-and-Write integrations**. ReadOnly
integrations receive the two lead events and nothing else.

| | ReadOnly *(drafted)* | Read-and-Write |
|---|---|---|
| Lead events (`CONTACTO`, `CONTACTO_MENSAJE`) | ✅ | ✅ |
| Listing events (`AVISO_*`, `CREDITO`) | ❌ | ✅ |
| What else it grants | nothing | **publish / unpublish / delete our clients' listings on ImovelWeb** |
| Overlap | — | collides with `products/erp-imobiliario`'s existing outbound XML feed — two systems able to change the same listings |
| API surface it opens | the ~15 lead/agency/config endpoints we use | **~55**: reading the generated spec on 2026-08-18 showed 40 further endpoints, almost all listing publication (`anuncios`, `lancamentos`, `multimidia`, `tipopropriedade`, `locais`, agency `usuarios`) |

**Recommendation: ask for ReadOnly.** The lead legs carry the value we are
actually after, and read/write can be requested later as a separate credential
without reworking anything we build — the package, the receiver and the
subscription code are identical either way. Asking for write access we do not yet
use widens the blast radius for a feature nobody has requested.

Reading the vendor's spec sharpened this rather than changing it. Read-and-Write
is not "the same integration plus four event types": it opens a whole publication
API — roughly 40 endpoints that can create, associate, force-publish and unpublish
listings — the same territory `erp-imobiliario` already reaches by XML feed. That
is a second writer to the same data, which is a design decision about the ERP, not
a checkbox on a credential request.

To flip it: change *"integração ReadOnly (somente leitura)"* to *"integração de
Leitura e Escrita"* in §1 of the email and add the `AVISO_*` events to §2.

---

## Draft email

**To:** `integracao@imovelweb.com.br`
**Cc:** `open@navent.com`
**Assunto:** Solicitação de credenciais Sandbox — integração Open API (recebimento de leads)

---

Olá, tudo bem?

Somos a **NoctusAI**, desenvolvedora de um CRM imobiliário, e queremos integrar o
recebimento de leads do ImovelWeb diretamente pela Open API, via callbacks.

Já estudamos a documentação em `open-classifieds.notion.site/bra` e a
especificação em `api-br-open.navent.com/v2/api-docs?group=opennavent-realestate`.
Gostaríamos de solicitar as **credenciais de Sandbox** para iniciar os testes.

**1. Tipo de integração**

Pretendemos operar uma **integração ReadOnly (somente leitura)** — nosso objetivo
nesta primeira fase é exclusivamente **receber os leads** gerados nos anúncios das
imobiliárias que nos autorizarem. Não vamos publicar nem despublicar anúncios por
esta integração.

**2. Eventos que pretendemos assinar**

- `CONTACTO` (consulta de telefone)
- `CONTACTO_MENSAJE` (mensagem do interessado)

**3. O que precisamos receber de vocês**

- `client_id` e `client_secret` para o ambiente de **Sandbox**
- O identificador de integrador (`[INTEGRADOR]`) que devemos usar na URL do botão
  de login (`https://loginbr-open.navent.com/[INTEGRADOR]/[CODIGOIMOBILIARIA].js`)
- Confirmação de quais imobiliárias e anúncios de teste ficarão disponíveis no
  Sandbox, já que o endpoint de simulação de eventos exige códigos reais

**4. Configuração de callbacks**

Pretendemos configurar os callbacks **pelo próprio endpoint**
(`PUT /v1/configuracao/callbacks`), sem depender do suporte, e faremos a
verificação com `GET /v1/configuracao/callbacks`. A autorização do callback será
enviada por nós no header, no formato `Basic <token>`.

**5. Dúvidas técnicas**

Aproveitando, algumas dúvidas que a documentação não deixa claras e que impactam
diretamente o desenho da nossa integração:

1. **Limites de requisição (rate limits).** Existe algum limite documentado? Em
   especial para `GET /v2/imobiliarias/{codigoImobiliaria}/mensagens`, que
   pretendemos usar em uma rotina de reconciliação periódica.
2. **Escopo do token.** O token de aplicação é por integrador ou por imobiliária?
   Um único par de credenciais atende todas as imobiliárias que nos autorizarem?
3. **Validade do token.** Qual a duração? O `refreshToken` retornado no login é
   utilizável, ou o caminho previsto é refazer o login?
4. **Callback por imobiliária.** A configuração de callback é global do
   integrador (não há código de imobiliária no path). É possível configurar uma
   **URL por imobiliária**? Isso simplificaria muito a identificação do cliente do
   lead no nosso lado.
5. **`lenguajeCallbackBody` — qual recomendam?** Notamos que o corpo em `EN2`
   inclui `leadOrigin` (que identifica o portal: Imovelweb / Wimoveis /
   CasaMineira) mas, no exemplo da documentação, **não** traz o código da
   imobiliária; já os corpos em `PT` / `ES` / `EN` trazem o código da imobiliária
   (`codigoImobiliaria` / `codigoCliente` / `clientCode`) mas **não** trazem
   `leadOrigin`. Como atendemos várias imobiliárias, precisamos dos dois. Qual
   variante vocês recomendam nesse caso? O `EN2` realmente não inclui o código da
   imobiliária?
6. **`clientListingId` / `referencia`.** A documentação se contradiz em um ponto:
   em uma seção diz que o código não é incluído *caso a associação não tenha sido
   realizada*, e em outra que ele será `null` *caso a associação tenha sido
   realizada*. Qual é o comportamento correto?
7. **`configuracao` ou `configuracion`?** A documentação escreve
   `/v1/configuracion/callbacks`, mas a especificação do ambiente BR traz
   `/v1/configuracao/callbacks`. Qual está ativo? O outro é um alias?
8. **Endpoint de simulação.** A documentação cita
   `/v1/callbacks/generacion/evento`, mas a especificação do Sandbox traz
   `POST /v1/callbacks/geracao/eventos`. Qual devemos usar?
9. **Identificadores de mensagem.** O `Mensaje` retornado por
   `GET /v2/imobiliarias/{cod}/mensagens` traz `id` e `idMensaje`. O callback traz
   `eventId` e `messageId`. Esses identificadores pertencem ao mesmo espaço? Ou
   seja: conseguimos correlacionar um lead recebido por callback com o mesmo lead
   retornado pela consulta, para não duplicá-lo?
10. **Faixa de IPs.** Os callbacks partem de uma faixa de IPs fixa? Como o
    esquema de autorização não assina o corpo da requisição, uma allowlist de IP
    seria uma camada adicional de segurança do nosso lado.
11. **Status de entrega.** Existe alguma consulta que informe quais callbacks
    ficaram como `VENCIDO`? Isso nos permitiria detectar perdas de forma ativa,
    em vez de depender apenas da reconciliação.

Ficamos à disposição para qualquer informação adicional que precisem do nosso
lado.

Obrigado!

---

## After they reply — what to record where

| What arrives | Where it goes |
|---|---|
| `client_id` / `client_secret` (sandbox) | `mcp/imovelweb/.env` (gitignored) — **never** committed |
| `[INTEGRADOR]` identifier | `endpoints.py::IMOVELWEB_REFERENCE_URLS` + the onboarding section of `KB § MCP-SERVERS/imovelweb.md` |
| Test agency / listing codes | `mcp/imovelweb/.env` + the Gate-1 checklist |
| Answers to §5 Q1–Q11 | `KB § INTEGRATIONS/imovelweb.md` §8 change log, **dated**, and the matching `contract.py` / `endpoints.py` constants |
| The `lenguajeCallbackBody` recommendation (Q5) | `imovelweb_callback_language` default + org-resolution rung 1 in the product slice |

**Do not flip any `verified` flag on the strength of an email.** A vendor's answer
is better evidence than their docs, but it is still prose. `verified` flips when
`imovelweb.contract.diff_observed` sees a real body — Gate 1.7 / Gate 2.3.

## Production credentials

A **second** email, after sandbox testing is complete — that is the vendor's
documented process, not an option. Same address. Ask at Gate 2, not before.
