# E-mail para a Vista — solicitação de permissões na chave final 644c

> Rascunho. Copie do bloco abaixo.
> As chaves são citadas apenas pelos 4 dígitos finais, que é como a Vista já se
> referiu a elas no chamado anterior — evita trafegar a credencial completa por
> e-mail.

---

**Assunto:** Solicitação de liberação de permissões na chave de API (final 644c)

Boa tarde,

Recebemos a nova chave de API (final **bced**) e já realizamos os testes. Ela está funcionando normalmente, obrigado.

Durante os testes percebemos que as duas chaves da nossa conta estão com permissões diferentes:

- **Chave final 644c** (a que já utilizamos): não consegue acessar os dados dos proprietários dos imóveis e não tem permissão para cadastrar ou gerenciar fotos.
- **Chave final bced** (a nova): acessa os dados dos proprietários e consegue cadastrar, alterar e excluir fotos.

Nossa integração precisa não apenas consultar os dados, mas também gerenciá-los dentro do Vista. Por isso, gostaríamos de solicitar que a **chave final 644c** receba as mesmas permissões da chave final bced, ou seja:

1. Acesso aos dados dos proprietários dos imóveis;
2. Permissão para cadastrar e gerenciar as fotos dos imóveis;
3. Acesso ao cadastro de corretores (`corretores/listar`), que hoje está bloqueado nas duas chaves.

Se for necessário abrir um chamado específico ou houver algum procedimento adicional para essa liberação, por favor nos avise.

Ficamos à disposição.

Atenciosamente,

Raphael
ONE Consultoria Imobiliária
