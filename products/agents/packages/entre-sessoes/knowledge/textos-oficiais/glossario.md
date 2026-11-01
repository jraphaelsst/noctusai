---
titulo: "Glossário"
tipo: fonte
resumo: "Termos para código, documentação e interface."
proveniencia:
  origem: "projects/app/entre-sessoes/guia-diario-entre-sessoes/01-produto/01-glossario.md (guia v1.0, 31/10/2026)"
  notas: "Cópia integral."
---
# Glossário e definições

Use estes termos no código (comentários, nomes de variáveis em português quando fizer sentido), na documentação e na interface.

| Termo | Definição | Observação |
|---|---|---|
| Analisanda | Mulher em análise com Mônica, pessoa que usa o app | Nunca "paciente", "cliente" ou "usuária" na interface |
| Análise | O processo psicanalítico | Em rótulos, "análise" no lugar de "terapia" |
| Sessão | O encontro de análise | "Minha sessão" é o campo onde a analisanda anota dia e hora |
| Registro | Uma entrada do diário, criada pelos 7 passos | Unidade principal de dado |
| Exemplo | Registro fictício que vem pré-carregado para mostrar como o diário fica | Marcado com `example: true`. Não entra no envio a Mônica |
| Levar à análise | Registro marcado para ser incluído no texto enviado a Mônica | Estado efetivo dado por `isLevar(r)` |
| Talvez levar | Registro em que a analisanda respondeu "Talvez" no passo 7 | Não entra no envio até ser marcado na aba Levar |
| Escolha do passo 7 (`bring`) | Resposta dada ao salvar: `sim`, `talvez` ou `nao` | Histórico da intenção inicial; não muda depois |
| Marcação de levar (`levar`) | Decisão atual de incluir no envio, feita na aba Levar | Sobrepõe a escolha do passo 7 |
| Pergunta para hoje | Uma das 5 perguntas do passo 5, escolhida pela analisanda | Obrigatório escolher uma; responder é opcional |
| O que despertou | Opções do passo 6 sobre o efeito da pergunta | Múltipla escolha, opcional |
| Emoções | Lista de 16 opções do passo 3 | Múltipla escolha, opcional, inclui "Não sei nomear" |
| Envio | Texto montado com os registros marcados, copiado ou aberto no WhatsApp | Hoje não fica registrado em lugar nenhum |
| Abertura | Tela inicial de boas-vindas, onde o nome é cadastrado uma única vez | Some depois do cadastro |
| Citação | Frase de um teórico exibida na Semana, filtro Todos | Muda a cada abertura do app |
| Resumo | Contagens dos últimos 7 dias | Só conta o que foi marcado; não interpreta |
| Últimos 7 dias | Da 00h00 de seis dias atrás até o momento atual, no fuso do aparelho | Usado no filtro "Esta semana" e no Resumo |
