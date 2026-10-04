---
titulo: "Voz e linguagem do app"
tipo: sintese
proveniencia:
  origem: "limiar-app agents/nos-no-limiar/knowledge/03-voz-e-linguagem.md (v0.1.0)"
  notas: "Sintetizado em 2026-10-03 a partir da sessão de desenvolvimento do limiar-app."
---
# Voz e linguagem do app

Duas fontes: a **especificação do app** (obrigatória) e a **base editorial da marca** (pasta
`NoctusAI/nos-no-limiar/KNOWLEDGE-BASE/VOZ`, feita para Instagram). Quando divergem, **o app segue a
spec**. As decisões tomadas estão no fim deste documento e em `docs/design/decisions.md`.

## Regras da spec (§2, §2.1) — obrigatórias
- Português brasileiro simples, adulto, natural. Frases concretas.
- Curiosidade antes de patologia; movimento antes de ruminação; autonomia (a usuária escolhe).
- Vida adulta, não autoajuda: sem slogans, positividade forçada, infantilização, medalhas, "guerreira".
- Sem reforço de drama: não ecoar "vazio", "dor", "depressão" como forma de vínculo.
- Sem falsa intimidade. Sem culpa ("se não fizer agora vai se arrepender").
- Evitar "não é X, é Y", paralelismos decorativos, moral da história.
- Sem "você precisa / você deve" em conteúdo normal (em emergência, linguagem direta é permitida).
- Blocos de tela: 40–120 palavras. "Síndrome do ninho vazio" nunca como diagnóstico.

## O que a base da marca acrescenta (compatível com a spec)
- Tom: substância séria, entrega gentil, linguagem **simples sem ser simplista**. Tratamento por "você".
- Pares: honesto, não performático · caloroso, não sacarino · adulto, não aspiracional · sério, não
  severo · curioso, não certo demais.
- **Reconhecimento, não correção.** Nada de frase corretiva.
- **Uma ideia por superfície.** Espaço vazio também comunica.
- Sem exclamação, sem emoji como decoração, sem superlativos, sem contagem regressiva ou escassez.
- Léxico bem-vindo: sustentar, dar conta, pausa, respiro, repouso, limiar, **habitável** ("vida
  habitável, não vida confortável"), reconhecer, redistribuir, curiosidade.
- Léxico a evitar: burnout, esgotamento, sobrecarga, resiliente/resiliência, empoderamento,
  autoconhecimento, guerreira, forte (como virtude aspiracional).
- Crédito a autores é sofisticação; jargão é cerca — mas no app, **nenhum** vocabulário clínico.

## O que da base da marca NÃO vale para o app
- A tese parte de "sofrimento silencioso" e de um público que "não chama isso de sofrimento" — o app
  **não presume sofrimento** (§1.1). Usar a tese só como fundo.
- "Porta clínica" como pilar de conteúdo — no app, encaminhamento é só a rota de segurança.
- Termos quase diagnósticos (hiperfuncionamento, hiperresponsabilidade, "adultos desertificados").
- Proibição de hífen, aspas, itálico e bullets: é regra de legenda de Instagram, não de interface.
- Hooks com "cansaço", "esgota", "pesa por dentro" — tom pesado demais para o app.

## Decisões tomadas (2026-10-03, Decision Board)
- **Lista "evitar" da marca adotada como regra do app**: ocorrência em copy = **corrigir**.
- **Botão principal continua em pílula** (o mockup aprovado manda na aparência; a regra da marca vale para redes/impresso).
- **Erro continua em `brick #8B2420`**, sempre com palavras: vinho significa "agir" no app.

## Exemplos aplicados no app
- "Uma nova fase. Muitas possibilidades." + "Pequenas experiências, jogos e ideias para descobrir o
  que combina com a vida de hoje." (substituiu "apoio… depois que os filhos saem de casa", que presumia perda).
- Vazio de Salvos: "As atividades que você guardar aparecem aqui." (sem culpa, sem "ainda não salvou nada!").
