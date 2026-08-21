# Vista — e-mail de agradecimento (rascunho)

> **O que é isto.** Resposta à equipe Vista/Loft depois que a liberação de
> permissões entrou em vigor. Sucede o pedido anterior (`VISTA-SUPPORT-EMAIL.md`,
> commit `7c434cf3`), que perguntava **em qual chave** a liberação havia sido
> aplicada.
>
> **Status verificado em 21/08/2026**, por probe ao vivo em
> `oneconsu-rest.vistahost.com.br` — não por memória:
>
> | Método | Antes (19/08) | Agora (21/08) |
> |---|---|---|
> | `GET /clientes/listar` | 401 Permissão Negada | **200 OK** — 42.963 clientes, 860 páginas |
> | `GET /clientes/detalhes` | 401 Permissão Negada | **liberado** (400 só por falta do parâmetro `cliente`, que é o comportamento correto) |
> | `GET /corretores/listar` | 401 Permissão Negada | 401 — **e está tudo bem, não precisamos** |
>
> A chave continua sendo a mesma, final `644c` — ou seja, a liberação foi
> aplicada à nossa chave e **não houve necessidade de rotação**. Era exatamente
> essa a dúvida do e-mail anterior.
>
> **Como usar.** O corpo abaixo é texto simples de propósito — sem `#`, sem
> tabelas, sem negrito — para colar direto no cliente de e-mail sem quebrar
> formatação. Copie de "Prezada equipe" até a assinatura.
>
> **Antes de enviar:** preencher nome / telefone / e-mail na assinatura.
>
> **Não colar a chave completa em e-mail.** Os últimos 4 dígitos bastam para
> identificar.

---

## Assunto

```
Permissões liberadas com sucesso — obrigado (oneconsu-rest, chave final 644c)
```

---

## Corpo do e-mail

Prezada equipe Vista,

Escrevo para agradecer e para fechar o chamado sobre as permissões da API REST do nosso ambiente (oneconsu-rest.vistahost.com.br).

A liberação entrou em vigor. Confirmamos hoje, 21 de agosto, com testes ao vivo contra a mesma chave de sempre — a que termina em 644c. Registro o resultado abaixo para que fique documentado do lado de vocês também.


1. O QUE PASSOU A FUNCIONAR

    GET /clientes/listar     -> 200 OK
    GET /clientes/detalhes   -> liberado

O /clientes/listar já está retornando a base completa: 42.963 clientes, em 860 páginas. O /clientes/detalhes também deixou de responder 401 — o 400 que ele retorna agora é apenas a cobrança do parâmetro "cliente", ou seja, o comportamento esperado de quem já tem permissão.

Vale registrar um ponto que era a dúvida central do nosso e-mail anterior: a liberação foi aplicada à NOSSA chave, a mesma que já usávamos. Não foi preciso emitir chave nova nem coordenar rotação. Isso nos poupou uma janela de manutenção em produção, e agradecemos o cuidado.


2. SOBRE O /corretores/listar — NÃO É NECESSÁRIO

O método GET /corretores/listar continua retornando 401 (Permissão Negada).

E está tudo bem. Não precisamos dele.

Faço questão de dizer isso de forma explícita para que ninguém do lado de vocês gaste tempo investigando: nós já obtemos a informação de corretor por outro caminho, dentro do próprio retorno dos imóveis, que atende plenamente a nossa necessidade. Considerem esse item encerrado, sem pendência.

Se o acesso a esse método exigir contratação de módulo, plano diferente ou qualquer aprovação adicional, também não há necessidade de seguir com o processo. Preferimos não abrir demanda para algo que não vamos usar.


3. O QUE JÁ ESTAVA FUNCIONANDO E SEGUE ESTÁVEL

Para completar o quadro, estes continuam respondendo normalmente:

    GET /imoveis/listar          -> 200 OK
    GET /imoveis/detalhes        -> 200 OK
    GET /imoveis/listarConteudo  -> 200 OK
    GET /usuarios/listar         -> 200 OK
    GET /agencias/listar         -> 200 OK

Do nosso lado, o catálogo de imóveis já está integrado e sincronizando de forma automática, diariamente. A integração está em produção e estável.


4. AGRADECIMENTO

Obrigado pela atenção e pela persistência no atendimento. O chamado passou por algumas idas e vindas até identificarmos que a questão era permissão por método, e não autenticação, e a equipe de vocês seguiu conosco até a resolução.

Nossa integração está funcionando, e o que ficou de fora ficou por escolha nossa, não por falta de suporte de vocês.

Permanecemos à disposição.

Atenciosamente,

[NOME]
[CARGO]
[EMPRESA]
[TELEFONE]
[E-MAIL]

---

## Versão curta (se preferir enviar apenas 3 parágrafos)

Prezada equipe Vista,

Escrevo para agradecer e encerrar o chamado sobre as permissões da API REST do ambiente oneconsu-rest. A liberação entrou em vigor: confirmamos hoje, 21 de agosto, que GET /clientes/listar responde 200 OK (42.963 registros, 860 páginas) e que GET /clientes/detalhes também foi liberado. Importante: tudo isso na mesma chave que já usávamos, a de final 644c — não foi necessário emitir chave nova nem coordenar rotação, o que nos poupou uma janela de manutenção.

Sobre o GET /corretores/listar, que segue retornando 401: está tudo bem, não precisamos dele. Digo isso de forma explícita para que ninguém do lado de vocês gaste tempo investigando — já obtemos a informação de corretor pelo retorno dos imóveis, e isso atende plenamente. Considerem o item encerrado, sem pendência e sem necessidade de contratação adicional.

Obrigado pela atenção e pela persistência até a resolução. Nossa integração está em produção, sincronizando o catálogo diariamente, e o que ficou de fora ficou por escolha nossa, não por falta de suporte de vocês.

Atenciosamente,
[NOME] — [EMPRESA]
