# Design system aplicado

Fonte da verdade da marca: `09-referencias/design-system-v2.1.md`. Este documento diz **como** ele foi aplicado no diário e quais desvios Mônica aprovou.

## Tokens em uso (CSS)

```css
:root{
  --font-display:'Bodoni Moda',Didot,'Times New Roman',serif;   /* títulos, citação, números */
  --font-body:'Inter',system-ui,-apple-system,'Segoe UI',Arial,sans-serif; /* todo o resto */
  --paper:#F5EFE5;   /* creme */
  --ink:#4B291D;     /* marrom */
  --wine:#5C0003;    /* vinho */
  --rose:#C9826C;    /* rosa velho */
  --on-wine:#F5EFE5;
  --sand:rgba(75,41,29,.08);    /* superfície de cartão */
  --sand-2:rgba(75,41,29,.16);
  --line:rgba(75,41,29,.16);    /* borda padrão */
  --soft:rgba(75,41,29,.88);    /* texto secundário */
  --focus:#5C0003;
}
```

Somente os quatro códigos oficiais aparecem. Variações são opacidade do marrom.

## Escala usada

| Elemento | Fonte | Tamanho |
|---|---|---|
| Saudação, título de aba | Bodoni Moda 500 | 34 px (30 px abaixo de 360 px) |
| Título de passo | Bodoni Moda 500 | 30 px (26 px nos longos) |
| Título de seção | Bodoni Moda 500 | 25 px |
| Lead do cartão | Bodoni Moda 500 | 21 px |
| Citação | Bodoni Moda itálico 500 | 24 px (20 px se longa) |
| Número do Resumo | Bodoni Moda 500 | 59 px |
| Corpo, campos | Inter 400 | **18 px** |
| Botões | Inter 600 | 18 px |
| Rótulos e perguntas | Inter 600 | 16 a 18 px |
| Etiquetas | Inter 700 caixa alta | 14 px |
| Abas | Inter 500 | **13 px** |

## Desvios aprovados

| Design system | No diário | Motivo |
|---|---|---|
| Corpo 16 px | 18 px | Pedido de Mônica, leitura das analisandas |
| Texto funcional ≥ 14 px | Abas em 13 px | Cinco rótulos cabem em 320 px; revisar se houver aba nova |
| Navegação Início/Explorar/Favoritos/Perfil | Semana/Registrar/Levar/Resumo/Como usar | Produto diferente |
| Busca "Buscar conteúdos" | "Buscar nos meus registros..." | Contexto do diário |

## Componentes

A tabela descreve a versão de teste (`fonte/template.html`). Na v21 oficial, a etiqueta "exemplo" é clara com borda, "Talvez levar" tem contorno vinho e a citação fica sobre o arranjo de flores foscas.

| Componente | Regra no diário |
|---|---|
| Botão principal | Vinho, texto creme, pill, ≥ 56 px, ícone seta à direita. Pressionado: opacidade 88% e 1 px abaixo |
| Botão secundário | Contorno vinho 1.5 px, texto vinho |
| Campo | Fundo creme, borda marrom 16%, ≥ 52 px, foco vinho 3 px com afastamento 2 px |
| Cartão de registro | Fundo marrom 8%, raio 24 px, botão redondo vinho de abrir |
| Etiqueta | Pill 14 px. Exemplo: marrom com texto creme. Levar: vinho com creme. Talvez: rosa com vinho |
| Filtro | Quadrado 58 px raio 16, borda 16%; selecionado vinho com ícone creme e rótulo em negrito |
| Aba ativa | Cor vinho, ícone preenchido, barra vinho de 3 px no topo (cor + forma) |
| Aviso de segurança | Fundo rosa velho, texto vinho em negrito (contraste 4,73:1) |
| Pergunta x resposta | Pergunta: faixa rosa à esquerda e etiqueta "Pergunta escolhida". Resposta: campo com faixa vinho e etiqueta "Sua resposta" |

## Cores escuras: onde usar

Uso com parcimônia, decisão de Mônica. Vinho em superfície grande só em: cartão da citação (versão de teste), bloco do número do Resumo, aviso de registro salvo. Marrom em superfície só na etiqueta "exemplo". Não criar novas superfícies escuras sem pedir.

## Acessibilidade obrigatória

Contraste mínimo 4,5:1 (3:1 para texto grande); rosa velho nunca como cor de texto sobre creme; creme nunca como texto sobre rosa; marrom sobre vinho proibido; área de toque ≥ 48 px; foco visível; funcionar com fonte ampliada a 200%; respeitar `prefers-reduced-motion`.
