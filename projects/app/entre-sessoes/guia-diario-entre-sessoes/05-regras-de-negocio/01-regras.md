# Regras de negócio

Cada regra tem um código (RN-nn). Testes e commits devem citar o código.

## Abertura e identidade

- **RN-01** A abertura aparece se não houver nome salvo ou se a abertura nunca foi concluída. Enquanto aparece, o resto do app fica inerte.
- **RN-02** O nome é obrigatório para sair da abertura (até 30 caracteres, espaços nas pontas removidos).
- **RN-03** Com nome salvo, a saudação é "Olá, {nome}," e o campo "Meu nome" fica oculto na Semana. Sem nome, a saudação é "Olá,".
- **RN-04** "Minha sessão" é texto livre de até 40 caracteres, salvo a cada alteração.

## Registro

- **RN-05** Obrigatórios: passo 1 (texto não vazio), passo 5 (uma pergunta escolhida), passo 7 (uma das três opções). Demais campos são opcionais.
- **RN-06** Ao salvar: `ts` = agora; `levar` inicial = (`bring` == `sim`).
- **RN-07** A escolha do passo 7 (`bring`) não muda depois de salva.
- **RN-08** `isLevar(r)`: se `r.levar` é booleano, vale `r.levar`; senão vale `r.bring === 'sim'`.
- **RN-09** Apagar um registro exige confirmação e é definitivo.

## Lista, filtros e busca

- **RN-10** Filtros: Todos (sem restrição); Esta semana (`ts` ≥ 00h00 de seis dias atrás, horário do aparelho); Levar à análise (`isLevar`); Talvez levar (`bring === 'talvez'`, independente de `levar`).
- **RN-11** Busca: sem acento e sem diferença de maiúsculas, em `happened`, `mind`, `did`, `answer`, `extra` e rótulos das emoções. Combina com o filtro (E lógico).
- **RN-12** Ordem: mais recente primeiro. Limite atual de 40 cartões (ver backlog).
- **RN-13** Etiquetas: "exemplo" se `example`; "Levar à análise" se `isLevar`; senão "Talvez levar" se `bring === 'talvez'`.

## Citação

- **RN-14** Mostrada só no filtro Todos. Índice = contador salvo módulo total de citações. O contador começa num valor aleatório entre 0 e 999 e soma 1 a cada carregamento do app.
- **RN-15** Nos demais filtros, aparece só o painel de flores do filtro, sem título nem texto.

## Exemplos

- **RN-16** Três exemplos são criados uma única vez, na primeira carga. Não voltam depois de apagados.
- **RN-17** Exemplos aparecem na lista e no Resumo (com aviso), mas **nunca** na aba Levar nem no texto para Mônica.

## Levar e envio

- **RN-18** A aba Levar lista todos os registros reais, de qualquer data, mais recentes primeiro.
- **RN-19** O texto para Mônica inclui só registros com `isLevar` verdadeiro, do mais antigo ao mais novo, no formato de `01-produto/04-textos-oficiais.md`. Campos vazios são omitidos.
- **RN-20** Sem registro marcado: botões de copiar e WhatsApp desabilitados.
- **RN-21** WhatsApp: `https://wa.me/5511975518400?text=` + texto codificado. Se o texto codificado passar de 3500 caracteres, o botão fica desabilitado e a orientação é copiar.
- **RN-22** Nada é enviado automaticamente. O app não registra se houve envio.

## Resumo

- **RN-23** Janela: a mesma de "Esta semana". O período aparece como "dd/mm a dd/mm".
- **RN-24** Total conta todos os registros da janela, inclusive exemplos; se houver exemplos, mostrar o aviso.
- **RN-25** Emoções: todas as marcadas na janela, ordenadas por contagem desc e, no empate, pela ordem do catálogo.
- **RN-26** Despertares: os 3 mais marcados, mesmo critério de desempate.
- **RN-27** O Resumo não interpreta, não compara semanas e não dá conselho.

## Segurança

- **RN-28** O texto de segurança aparece em todas as abas, com links `tel:192` e `tel:188`.
