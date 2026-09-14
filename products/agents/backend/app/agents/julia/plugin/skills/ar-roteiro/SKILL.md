---
name: ar-roteiro
description: Escreve roteiro de vídeo de treinamento em PT-BR — dispara em "roteiro", "script do vídeo", "vamos gravar uma aula sobre". Ancorado em fonte regulatória capturada; nunca inventa fato técnico.
version: 1.0.0
---

# ar-roteiro — roteiro de vídeo de treinamento

Um roteiro tecnicamente errado é passivo, não rascunho.

## Antes de escrever — pare e verifique

1. **Quem assiste?** Busque no conhecimento do projeto (`mcp__academia__kb_buscar`,
   categoria `contexto`) a descrição do público. Se não existir ou estiver incompleta,
   **pergunte antes de escrever**: duração, linguagem, exemplos e ritmo dependem
   inteiramente disso.
2. **Qual o método?** Busque a metodologia (categoria `dominio`). Se estiver vazia, o
   roteiro é um experimento — diga isso ao entregar.
3. **Os fatos técnicos têm fonte?** Busque (categoria `dominio`). Um fato sem fonte
   confirmada **não entra** — use `/ar-pesquisa` para capturar a fonte primeiro.

## Forma

- **PT-BR**, tom conforme o material de marca do projeto (categoria `marca`), quando
  existir; enquanto não existir, escreva claro e direto, sem gíria e sem solenidade, e
  sinalize que a voz é provisória.
- Estrutura por blocos com **tempo estimado** em cada um.
- Texto falado, não texto escrito: frase curta, voz ativa, sem subordinada empilhada.
- Toda afirmação técnica carrega a fonte num comentário lateral — some na gravação, fica
  na revisão.
- Feche com uma ação concreta que a pessoa faz amanhã no posto de trabalho dela.
  Conhecimento sem ação não muda comportamento, e mudar comportamento é o objetivo do
  treinamento.

## Depois

`mcp__academia__conteudo_salvar` (tipo `roteiro`, `fontes` com os slugs usados).

## Guardrails

- Não invente número ("X% do lixo é reciclável"). Sem fonte capturada, não vai.
- Não prometa resultado dentro do roteiro.
- Não copie estrutura de treinamento de terceiro. O método é o ativo do projeto.
