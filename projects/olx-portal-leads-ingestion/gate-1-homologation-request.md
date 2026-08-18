# Gate 1 — Grupo OLX homologation request (ready to send)

> **Why this is the first artifact of Phase 2, not the last.** Gate 1 is blocked
> on a vendor-issued `SECRET_KEY`, and vendor turnaround is the longest pole in
> the project — the precedent issue on their own GitHub
> ([olxbr/crm-lead-integration#16](https://github.com/olxbr/crm-lead-integration/issues/16))
> is an integrator reporting *no reply at all* to a SECRET_KEY request. Slices 1–3
> (seed forwarder organ, multi-tenant receiver, Lais forwarder) are all buildable
> against the transcribed contract while this is in flight, so the email goes out
> **before** the code is finished.
>
> **Nothing in this draft is a guess.** Every claim about our side is checked
> against the code; every question exists because the vendor's published docs do
> not answer it. Do not let a helpful-sounding reply flip a `verified` flag —
> see "After they reply" below.

**To:** `integracaoleads@grupozap.com`
**Cc:** `chamado.integracao@olxbr.com`
**Assunto:** Homologação de CRM para recebimento de leads — NoctusAI

---

## The one decision before sending

The draft asks to be homologated as a **CRM/integrador multi-cliente** — one
homologation, one `SECRET_KEY`, and a **distinct URL per anunciante**, matching
the shape already in production on the account of *One Consultoria Imobiliária*:

```
https://prod.lastro.services/api/public/v1/leads/webhook/grupozap/10b7165c-17a4-4565-acb2-53c9c447…
                                                                 └── per-advertiser token ──┘
```

That is **observed evidence, not an inference** — it is the value currently
saved in that account's Canal Pro → Integrações → Leads → "Receber leads no
CRM" field, delivering successfully (three `Sucesso` deliveries, 17–18/08/26).
It resolves an item this project has carried as open since 2026-08-17
("whether OLX registers one endpoint per CRM or per advertiser").

If you would rather register **only One Consultoria** and defer multi-tenancy,
cut §2 and §5 Q1 from the email — but say so before sending, because the
receiver work in slice 2 is shaped by the answer.

---

## Draft email

Olá, tudo bem?

Somos a **NoctusAI**, desenvolvedora de um CRM imobiliário, e gostaríamos de
iniciar o processo de **homologação para recebimento de leads** do Grupo OLX
(ZAP Imóveis, VivaReal, OLX, ImovelWeb e Casa Mineira).

**1. O que já temos pronto**

Nosso endpoint receptor já está implementado e em produção, seguindo a
documentação de vocês em `developers.grupozap.com/webhooks/integration_leads.html`
e `/webhooks/security.html`:

- `POST` HTTPS, `Content-Type: application/json`, um lead por requisição;
- autenticação `Authorization: Basic base64("vivareal:<SECRET_KEY>")`, validada
  a cada requisição;
- **idempotência por `originLeadId`** — uma reentrega do mesmo lead é registrada
  e respondida com `2xx`, sem duplicar o cadastro;
- respondemos `4xx` em **uma única** condição: lead de anúncio sem
  `clientListingId`, exatamente o caminho de reprocessamento que a documentação
  de vocês descreve. Qualquer outra divergência (campo desconhecido, enum novo)
  é registrada e respondida com `2xx`, para não provocar reentrega de um lead
  que já temos;
- a resposta é enviada antes do processamento interno, de modo que o
  processamento nunca segura a conexão de vocês.

**2. Modelo de integração que precisamos**

Atendemos **várias imobiliárias**. Pelo que entendemos da documentação, o
`SECRET_KEY` é por CRM e não por anunciante, e portanto não identifica de qual
cliente o lead é. Para resolver isso pretendemos registrar, no campo "URL de
integração" de cada anunciante, uma **URL distinta contendo um identificador
opaco do cliente no path** — o mesmo formato que já observamos em uso por outro
CRM homologado:

```
https://social-wiring.noctusai.com/api/portals/olx/leads/<token-do-anunciante>
```

**Pergunta:** vocês confirmam que esse é o modelo suportado — uma homologação e
um `SECRET_KEY` para a NoctusAI, com uma URL diferente por anunciante? Existe
alguma restrição de formato ou de tamanho para essa URL?

**3. O que precisamos receber de vocês**

- O `SECRET_KEY` da NoctusAI (e o procedimento de rotação, se houver);
- confirmação do usuário da autenticação Basic — a documentação usa
  literalmente `vivareal`; queremos confirmar que segue assim após o rebranding
  para Grupo OLX;
- orientação sobre o **validador de endpoint** em
  `developers.grupozap.com/webhooks/endpoint_validator/` — se há credencial
  específica para ele e se ele pode ser usado antes da homologação concluída;
- o formulário de homologação, caso exista um além deste contato.

**4. Ativação ImovelWeb / Casa Mineira**

Entendemos, pela página `leadManager/imovelweb_casamineira.html`, que os leads
de ImovelWeb e Casa Mineira passam a chegar pelo mesmo webhook do Gestor de
Leads mediante um **código de ativação por conta**, solicitado ao suporte da
ImovelWeb. Está correto? Nossos clientes devem solicitar esse código
diretamente, ou podemos encaminhar a solicitação como integrador?

**5. Dúvidas técnicas que impactam o desenho da integração**

1. **Identificação do anunciante.** Além da URL por anunciante (§2), existe
   algum campo no corpo do lead que identifique o anunciante/imobiliária? Hoje
   a documentação não descreve nenhum, e o `SECRET_KEY` é por CRM.
2. **Identificação do portal de origem.** Esta é a dúvida mais importante para
   nós. O campo `leadOrigin` documentado assume apenas `"Grupo OLX"` ou
   `"MCMV_OLX"`, ou seja, **não diz se o lead veio do ZAP, do VivaReal, da OLX,
   da ImovelWeb ou da Casa Mineira**. Nossos clientes precisam medir retorno por
   portal. Existe algum campo — documentado ou não — que carregue o portal de
   origem? Se não existir hoje, é possível incluí-lo, ou há alguma outra forma
   recomendada de fazer essa distinção?
3. **Leads via chat.** O painel do Canal Pro tem um botão "Receber leads por
   chat". Quando ativado, esses leads chegam pelo mesmo webhook? O corpo é
   idêntico, ou muda algum campo além de `extraData.leadType`
   (`CONTACT_CHAT`)? Há alguma expectativa de tempo de resposta diferente?
4. **Faixa de IPs de origem.** As entregas partem de uma faixa fixa de IPs?
   Como o esquema Basic não assina o corpo da requisição, uma allowlist de IP
   seria uma camada adicional de segurança do nosso lado.
5. **Política de retentativa.** A documentação cita até 3 tentativas e
   armazenamento por 14 dias. Qual é o **intervalo** entre as tentativas, e o
   reenvio após o período de armazenamento é automático ou precisa ser
   solicitado?
6. **Timeout.** Qual o tempo máximo que vocês aguardam pela nossa resposta antes
   de considerar a entrega como falha?
7. **Volume.** Existe algum limite de requisições por segundo por endpoint que
   devamos considerar no dimensionamento?
8. **`extraData`.** Quais chaves realmente chegam em cada `leadType`? A
   documentação lista `leadCerto`, `izi`, `feedback`, `leadType` e `mcmv`, mas
   não diz quais são garantidas.
9. **Ambiente de testes.** Existe algum ambiente de homologação/sandbox que
   permita gerar um lead de teste, ou o validador de endpoint é a única forma
   de exercitar a integração antes do tráfego real?

**6. Migração de um CRM já integrado**

Um dos nossos clientes já recebe leads em outro CRM homologado e pretende passar
a recebê-los na NoctusAI. Como o campo "URL de integração" aceita apenas uma
URL, entendemos que a troca é feita simplesmente substituindo o valor no Canal
Pro do próprio anunciante, com efeito imediato. Está correto? Há alguma janela
de propagação ou risco de perda de leads durante a troca?

Ficamos à disposição para qualquer informação adicional que precisem do nosso
lado, e podemos disponibilizar o endpoint para validação assim que recebermos
as orientações.

Obrigado!

---

## After they reply — what goes where

| What arrives | Where it goes |
|---|---|
| `SECRET_KEY` | `integration_accounts` (per-org, encrypted) — **never** committed, never in `.env.example` |
| Confirmation of the per-advertiser URL model (§2) | `KB § INTEGRATIONS/olx.md § 4` — replaces the "open — Gate 1 item 2" heading |
| Basic username confirmation (§3) | `GRUPO_OLX_BASIC_USERNAME` in `noctusai_lib.security.webhook_signatures` |
| Portal-of-origin answer (§5 Q2) | Decides slice 5. A named field ⇒ one `PortalRule`. "No such field" ⇒ record that as the answer and stop looking. |
| Retry interval / timeout / rate (§5 Q4–Q7) | `KB § INTEGRATIONS/olx.md § 3` + the receiver's latency budget |
| IP range (§5 Q4) | Cloudflare tunnel ingress allowlist — a real second factor, since Basic does not bind the body |
| Everything else | `KB § INTEGRATIONS/olx.md § 8` change log, **dated** |

**A vendor's prose is better evidence than their docs, and still not an
observation.** `verified` flags flip when `olx.contract.diff_observed` sees a
real body — not before. Same rule the ImovelWeb draft carries, for the same
reason: `PortalRule` refuses construction without a recorded observation, and an
email is not one.
