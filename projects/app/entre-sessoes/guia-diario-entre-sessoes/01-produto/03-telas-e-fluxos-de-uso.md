# Telas e fluxos de uso

Largura de referência: 390 px. Deve funcionar de 320 a 430 px; em telas maiores, coluna central de até 480 px. Navegação inferior fixa com 5 abas: **Semana, Registrar, Levar, Resumo, Como usar**.

## T0. Abertura (primeira visita)

Aparece quando não há nome salvo ou a abertura nunca foi concluída. O app por trás fica inerte (`inert`, `aria-hidden`).

Elementos: logo (230 px), colagem vertical (asset 23), título "Um espaço seu entre uma sessão e outra.", texto curto, campo "Meu nome" (obrigatório), ajuda "Você escreve uma vez só...", botão "Começar agora", assinatura de Mônica.

Fluxo: digita o nome → "Começar agora" (ou Enter) → salva nome, marca abertura vista → mostra Semana. Sem nome: mensagem "Escreva seu nome para começar." e foco no campo.

## T1. Semana (início)

Ordem: logo → etiqueta "Diário entre sessões" → saudação "Olá, {nome},<br>que bom ter você aqui!" → campo "Minha sessão" → aviso de registro salvo (quando houver) → barra de exemplos (quando houver) → citação ou painel de flores → "Seus registros" com contagem → busca → 4 filtros → lista.

- Campo "Meu nome" fica oculto quando já há nome.
- Filtro **Todos**: título "Uma frase para hoje" + cartão de citação.
- Filtros **Esta semana**, **Levar à análise**, **Talvez levar**: só o painel de flores do filtro, sem título e sem texto. Cada filtro tem um painel diferente.
- Lista: até 40 registros mais recentes que passam no filtro e na busca. Cartão fechado mostra data, etiquetas, trecho de "o que aconteceu" e emoções. Aberto mostra todos os campos, com pergunta e resposta visualmente distintas, e "Apagar este registro".
- Vazio sem registros: "Nenhum registro ainda..." + "Fazer um registro". Vazio por filtro ou busca: mensagem + "Ver todos".
- Barra de exemplos: "Apagar os exemplos" → confirmação "Apagar mesmo" / "Manter".

## T2. Registrar (7 passos)

Cabeçalho com figura que muda por passo, botão voltar, etiqueta "Passo N de 7" e barra de progresso. Botão principal: "Ir para o passo N+1"; no passo 7, "Salvar registro".

| Passo | Título | Tipo | Obrigatório | Campo |
|---|---|---|---|---|
| 1 | O que aconteceu? | texto, até 1500 | sim | `happened` |
| 2 | O que veio à sua mente? | texto, até 1500 | não | `mind` |
| 3 | Qual emoção veio junto? | múltipla escolha (16) | não | `emotions` |
| 4 | O que você fez? | texto, até 1500 | não | `did` |
| 5 | Uma pergunta para hoje | escolha única (5) + resposta até 2000 | escolher sim, responder não | `q`, `answer` |
| 6 | O que essa pergunta despertou em você? | múltipla escolha (6) + texto até 1500 | não | `awakened`, `extra` |
| 7 | Tem alguma coisa sobre isso que você gostaria de conversar na sua próxima sessão? | escolha única (3) | sim | `bring` |

Mensagens de validação: ver `04-textos-oficiais.md`. Voltar no passo 1 leva à Semana. Ao salvar: limpa o formulário, volta ao passo 1, vai para Semana com filtro Todos; se `bring = sim`, mostra o aviso vinho "Registro salvo e marcado para levar à análise." com botão "Ir para Levar à análise". Toast "Registro salvo.".

## T3. Levar

Título "Levar à análise", texto de orientação, contagem "N registros marcados", lista de todos os registros reais (sem exemplos) do mais recente ao mais antigo, cada um com caixa de marcação, data, etiqueta "Marquei Sim"/"Marquei Talvez" e trecho. Abaixo, "Texto para a Mônica" (somente leitura), "Copiar texto pra mandar pra Mônica" e "Abrir o WhatsApp com o texto pronto".

- Nada marcado: botões desabilitados e texto "Marque ao menos um registro para montar o texto."
- Texto codificado com mais de 3500 caracteres: botão do WhatsApp desabilitado e orientação para copiar.
- Cópia falhou: seleciona o texto e avisa "Não consegui copiar automaticamente...".

## T4. Resumo

Cabeçalho com colagem (asset 25), período "dd/mm a dd/mm", título "Resumo dos últimos 7 dias", número total em bloco vinho, aviso sobre exemplos quando houver, "Emoções que mais apareceram" (barras), "O que as perguntas despertaram" (3 mais marcadas), bloco com botão "Ir para Levar à análise".

## T5. Como usar

Sete passos numerados de orientação e nota sobre armazenamento local. Texto oficial em `04-textos-oficiais.md`.

## Rodapé (todas as abas)

Faixa de colagem (asset 26), crédito "Mônica Tangerino, Psicanalista Clínica e Escritora do livro *Funcionar Não é Estar Bem*" e bloco de segurança em negrito, num parágrafo só, fundo rosa velho e texto vinho.
