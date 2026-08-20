# Vista — e-mail de suporte (rascunho)

> **O que é isto.** Rascunho do e-mail para o Suporte Vista sobre a liberação de
> permissões que foi informada como concedida mas não está em vigor. Derivado de
> `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md § 9` (os tiers do pedido de
> suporte) e da re-verificação de 19/08/2026 (§ 8).
>
> **Como usar.** O corpo abaixo está em texto simples de propósito — sem `###`,
> sem tabelas, sem negrito — para colar direto no cliente de e-mail sem quebrar.
> Copie a partir de "Prezada equipe" até a assinatura.
>
> **Antes de enviar:** preencher nome/telefone/e-mail na assinatura. Conferir se
> a chave ainda termina em `644c` (se já foi rotacionada, atualizar a seção 2).
>
> **Se preferir enviar curto:** as seções 1 e 2 sozinhas já formam um e-mail
> completo — são a parte que desbloqueia. O resto pode ir depois.
>
> **Não colar a chave completa em e-mail.** Os últimos 4 dígitos bastam para eles
> identificarem, e é exatamente o problema que a seção 6 reporta.

---

## Assunto

```
Permissões da API REST ainda negadas após liberação informada — chave final 644c (oneconsu-rest)
```

---

## Corpo do e-mail

Prezada equipe de Suporte Vista,

Escrevo a respeito da solicitação de liberação de permissões na API REST do nosso ambiente (oneconsu-rest.vistahost.com.br). Fomos informados de que o acesso foi concedido, porém nossos testes indicam que a liberação não está em vigor na chave que utilizamos.


1. SITUAÇÃO ATUAL (verificada em 19/08/2026)

Os três métodos solicitados continuam retornando HTTP 401:

    GET /clientes/listar     -> 401  "Permissão Negada: "<chave>" Método: clientes/listar"
    GET /clientes/detalhes   -> 401  "Permissão Negada: "<chave>" Método: clientes/detalhes"
    GET /corretores/listar   -> 401  "Permissão Negada: "<chave>" Método: corretores/listar"

Na mesma bateria de testes, e com a mesma chave, os métodos já liberados responderam normalmente:

    GET /imoveis/listar      -> 200 OK
    GET /usuarios/listar     -> 200 OK

Ou seja: a chave está ativa e autenticando corretamente. O que não está em vigor é a permissão por método.

Repetimos a verificação três vezes, em processos e sessões distintas e com requisições "pesquisa" bem formadas, justamente para descartar cache do nosso lado ou erro de formatação na requisição. O resultado foi o mesmo nas três.


2. O QUE PRECISAMOS CONFIRMAR — PEDIDO PRINCIPAL

Em qual chave a liberação foi aplicada? A nossa termina em 644c.

Se a liberação foi aplicada a outra chave, a outro ambiente/conta, ou se uma nova chave foi emitida para nós, precisamos saber qual é a chave correta e qual o procedimento de rotação recomendado — a troca precisa ser coordenada para não interromper nosso ambiente de produção.

Observação: a autorização de vocês é por método — a própria mensagem de 401 cita "Método: clientes/listar". Por isso listamos método a método, e não "acesso a clientes".


3. ENDPOINTS QUE RETORNAM 404 — DÚVIDA SOBRE CONTRATO OU VERSÃO

Ao mapear a superfície disponível, treze famílias retornaram 404 "No route found":

    /leads, /atendimentos, /agendamentos, /negociacoes, /propostas, /vendas,
    /condominios, /empreendimentos, /portais, /buscas, /campanhas, /tarefas, /reservas

O mesmo ocorreu com as sub-rotas de /clientes: pesquisar, porcorretor, poragencia, historicos, favoritos, campos, cadastrar, alterar, cadhis, cadcor e lead.

Para esses casos, poderiam esclarecer se se trata de (a) módulo contratado à parte, (b) recurso disponível em uma versão mais recente da API à qual não estamos apontados, ou (c) recurso não oferecido?

Pergunta direta: existe uma URL base ou versão mais recente da API REST para este ambiente? Treze famílias documentadas retornando 404 nos parece mais compatível com uma diferença de versão ou de contrato do que com treze recursos inexistentes.


4. GRAVAÇÃO DE LEADS — IMPACTO DE PRODUTO

Os métodos /clientes/lead e /clientes/cadastrar retornam 404. Sem eles, não existe caminho via API para gravar no Vista um lead capturado em nossos canais, o que obrigaria a equipe da imobiliária a consultar dois sistemas distintos.

Este ponto é decisivo para nós. Existe alguma forma suportada de fazer essa gravação?

Registramos que mapeamos a superfície de escrita apenas por GET, usando a distinção entre 405 e 404. Em nenhum momento enviamos POST a um CRM em produção.


5. QUESTÕES OPERACIONAIS

a) Limite de paginação. O parâmetro "quantidade" é limitado a 50 pelo servidor. Com aproximadamente 1.928 imóveis, uma sincronização completa exige 39 requisições. Esse limite é ajustável?

b) Sincronização incremental. Existe filtro documentado do tipo "alterados desde DataAtualizacao"? O "advFilter" contempla isso? A documentação pública não traz a especificação desse parâmetro, e sem ele toda sincronização precisa varrer o catálogo inteiro.


6. OBSERVAÇÃO DE SEGURANÇA

Registramos um ponto que consideramos relevante comunicar: o corpo da resposta 401 contém a chave de API do chamador em texto puro.

    {"status":401,"message":"Permissão Negada: \"<CHAVE COMPLETA EM TEXTO PURO>\" Método: clientes/listar"}

Na prática, qualquer cliente que registre corpos de resposta em log está persistindo uma credencial válida. Do nosso lado já aplicamos redação da chave no momento da recepção, mas o ajuste adequado é no servidor. Reportamos em caráter colaborativo e ficamos à disposição para detalhar.


Agradecemos desde já o retorno. O item da seção 2 é o que nos desbloqueia de imediato; os demais podem ser respondidos conforme a disponibilidade de vocês.

Atenciosamente,

[Seu nome]
ONE CONSULTORIA IMOBILIÁRIA
[telefone] · [e-mail]

---

## Versão curta (só o desbloqueio)

Use esta se preferir não enviar tudo de uma vez. É autossuficiente.

Prezada equipe de Suporte Vista,

Escrevo a respeito da liberação de permissões na API REST do nosso ambiente (oneconsu-rest.vistahost.com.br). Fomos informados de que o acesso foi concedido, porém os três métodos solicitados continuam retornando HTTP 401 na chave que utilizamos (final 644c):

    GET /clientes/listar     -> 401  "Permissão Negada ... Método: clientes/listar"
    GET /clientes/detalhes   -> 401  "Permissão Negada ... Método: clientes/detalhes"
    GET /corretores/listar   -> 401  "Permissão Negada ... Método: corretores/listar"

Na mesma bateria de testes e com a mesma chave, /imoveis/listar e /usuarios/listar responderam 200 OK — a chave está ativa e autenticando; o que não está em vigor é a permissão por método. Repetimos a verificação três vezes, em sessões distintas e com requisições bem formadas, para descartar cache ou erro de formatação do nosso lado.

Nossa pergunta: em qual chave a liberação foi aplicada? Se foi aplicada a outra chave ou conta, ou se uma nova chave foi emitida, precisamos saber qual é a correta e o procedimento de rotação recomendado, para coordenar a troca sem interromper nosso ambiente de produção.

Atenciosamente,

[Seu nome]
ONE CONSULTORIA IMOBILIÁRIA
[telefone] · [e-mail]

---

## Procedência

- Evidência dos 401/200: re-probe de 19/08/2026, três verificações independentes
  (probe do MCP, HTTP puro em processo novo, sessão MCP reiniciada).
  Registrado em `KB § CONTEXT/INTEGRATIONS/vista.md § 8`.
- Tiers do pedido (seções 2 a 6 acima): `KB § CONTEXT/INTEGRATIONS/vista.md § 9`.
- Superfície 404 e a técnica 405-vs-404: `§ 4.2`, `§ 4.6` do mesmo documento.
- Ao receber a resposta da Vista: atualizar `§ 9` (status do Tier 1) e `§ 8`
  (change log) — o documento é a fonte de verdade, este rascunho não é.
