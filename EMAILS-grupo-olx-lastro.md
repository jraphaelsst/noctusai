# E-mails prontos para enviar — integração de leads dos portais

> Arquivo de trabalho, **não versionado**. Os originais versionados, com o
> raciocínio e o "depois da resposta, o que vai para onde", vivem em
> `projects/olx-portal-leads-ingestion/gate-1-homologation-request.md` e
> `.../gate-1-lastro-request.md`. Aqui está só o texto para copiar e colar.
>
> Gerado em 2026-08-19.

---

## 1 · Grupo OLX — homologação

**Para:** `integracaoleads@grupozap.com`
**Cc:** `chamado.integracao@olxbr.com`
**Assunto:** Homologação de CRM para recebimento de leads — NoctusAI

---

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
---

## 2 · Lastro / Lais — contrato do repasse

**Para:** `[PREENCHER — não temos um contato técnico verificado da Lastro]`
**Assunto:** Integração de leads Grupo OLX — mudança de endpoint e repasse para o Lais

---

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
