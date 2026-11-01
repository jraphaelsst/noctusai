---
title: "Design System Nós no Limiar"
subtitle: "Identidade, interface e implementação"
author: "Mônica Tangerino"
date: "Versão 2.1 - 29 de outubro de 2026"
lang: pt-BR
titlegraphic: "/workspace/scratch/f19a39200ffb/Logo-Nos-no-Limiar-transparente.png"
---

## 1. Finalidade

Este documento orienta a criação do aplicativo e dos produtos digitais do Nós no Limiar. Ele reúne identidade visual, regras de interface, componentes, estados, acessibilidade, uso das imagens e critérios de implementação.

O sistema foi construído a partir do mockup aprovado, da paleta oficial e do Banco Visual Nós no Limiar. Um novo designer ou desenvolvedor deve conseguir criar telas coerentes sem escolher novamente cores, medidas ou comportamentos.

### Ordem de autoridade

1. Instruções expressas de Mônica Tangerino.
2. Paleta oficial e logo original.
3. Este design system.
4. Mockup aprovado.
5. Decisões locais de implementação.

Quando houver conflito, o item anterior prevalece.

## 2. Princípios do produto

### Clareza

Cada tela deve permitir que a usuária entenda onde está, o que encontra ali e qual ação pode realizar. A estética editorial não pode dificultar a navegação.

### Maturidade sem estereótipos

O público principal é composto por mulheres maduras. A interface evita infantilização, excesso de ornamentos, imagens genéricas de envelhecimento e linguagem condescendente.

### Calma visual

O creme domina as superfícies. Vinho, marrom e rosa velho organizam a hierarquia. Colagens aparecem em pontos definidos e não competem com textos ou controles.

### Continuidade

Componentes iguais devem manter aparência e comportamento em todas as telas. Uma mudança em botão, card ou navegação precisa ser aplicada no sistema inteiro.

### Acessibilidade desde a base

Contraste, tamanho de texto, área de toque, leitura por tecnologia assistiva e adaptação a fontes ampliadas fazem parte dos componentes.

## 3. Identidade visual

### 3.1 Paleta oficial

| Token | Nome | HEX | Aplicação principal |
|---|---|---|---|
| `color.wine` | Vinho | `#5C0003` | Botão principal, seleção, foco e destaques |
| `color.brown` | Marrom | `#4B291D` | Texto, títulos, ícones e bordas fortes |
| `color.cream` | Creme | `#F5EFE5` | Fundo global, texto sobre superfícies escuras |
| `color.rose` | Rosa velho | `#C9826C` | Fundos auxiliares, tags e detalhes gráficos |

Estas são as únicas cores da marca. Variações de estado usam opacidade, borda, ícone e texto. Não criar novos tons hexadecimais para resolver estados locais.

### 3.2 Contraste permitido

| Combinação | Contraste | Uso |
|---|---:|---|
| Vinho sobre creme | 12,61:1 | Texto, botão e ícone |
| Marrom sobre creme | 11,24:1 | Texto principal e navegação |
| Creme sobre vinho | 12,61:1 | Botão principal e cabeçalho escuro |
| Creme sobre marrom | 11,24:1 | Texto sobre superfície marrom |
| Vinho sobre rosa velho | 4,73:1 | Texto normal e ícones |
| Marrom sobre rosa velho | 4,22:1 | Texto grande ou peso reforçado; validar no tamanho real |
| Rosa velho sobre marrom | 4,22:1 | Texto grande, ícones e grafismos |
| Creme sobre rosa velho | 2,66:1 | Grafismos e decoração; não usar em texto funcional |
| Rosa velho sobre creme | 2,66:1 | Apenas decoração e fundos; proibido para texto funcional |
| Marrom sobre vinho | 1,12:1 | Proibido |

As combinações rosa velho sobre marrom e creme sobre rosa velho fazem parte da identidade visual. Para preservar a acessibilidade, rosa velho sobre marrom fica restrito a texto grande, ícones e detalhes gráficos. Creme sobre rosa velho pode ser usado em composições e elementos decorativos, mas não em textos, botões, rótulos ou informações funcionais. O rosa velho não pode ser usado como cor de texto sobre creme. Em botões e áreas interativas, a diferença de estado não pode depender somente de cor.

### 3.3 Opacidades

| Token | Valor | Uso |
|---|---:|---|
| `opacity.strong` | 88% | Texto secundário marrom |
| `opacity.medium` | 64% | Metadados e ícones inativos |
| `opacity.disabled` | 40% | Elementos desabilitados com explicação |
| `opacity.subtle` | 16% | Bordas e divisores |
| `opacity.overlay` | 72% | Fundo de modal |

### 3.4 Logo

Usar o PNG transparente aprovado. Não redigitar o nome, redesenhar o símbolo, aplicar sombra, inclinar, comprimir ou trocar as proporções.

| Contexto | Largura recomendada |
|---|---:|
| Boas-vindas | 220 a 240 px |
| Cabeçalho principal | 160 a 176 px |
| Rodapé web | 180 a 220 px |
| Ícone reduzido | Usar variante própria quando aprovada |

Respiro mínimo ao redor do conjunto: 16 px. Se a assinatura ficar ilegível, usar uma variante oficial sem assinatura. Não cortar a assinatura automaticamente.

### 3.5 Tipografia

#### Títulos e expressão editorial

Família recomendada: **Bodoni Moda**.

Uso: títulos de página, títulos de seção, chamadas editoriais e números de destaque. A identificação exata da fonte original do logo permanece pendente; Bodoni Moda é a aproximação de trabalho.

#### Interface e leitura

Família recomendada: **Inter**.

Uso: parágrafos, formulários, botões, navegação, legendas, metadados e mensagens do sistema.

A Bodoni possui traços finos e perde legibilidade em tamanhos pequenos. Por isso, o sistema separa expressão editorial e leitura funcional. O logo permanece como imagem e não depende da fonte instalada.

| Token | Fonte | Tamanho / entrelinha | Peso | Uso |
|---|---|---:|---:|---|
| `type.display` | Bodoni Moda | 40 / 44 px | 500 | Hero web e boas-vindas |
| `type.h1` | Bodoni Moda | 34 / 40 px | 500 | Título principal |
| `type.h2` | Bodoni Moda | 28 / 34 px | 500 | Seção |
| `type.h3` | Bodoni Moda | 22 / 28 px | 500 | Card e subtítulo |
| `type.body.lg` | Inter | 18 / 28 px | 400 | Texto editorial |
| `type.body` | Inter | 16 / 24 px | 400 | Corpo e descrição |
| `type.label` | Inter | 16 / 20 px | 600 | Botões e campos |
| `type.caption` | Inter | 14 / 20 px | 500 | Metadados e tags |

Texto funcional nunca fica abaixo de 14 px. Parágrafos não são justificados. Caixa alta fica restrita a tags curtas e à marca.

## 4. Espaçamento, forma e elevação

### 4.1 Escala de espaço

| Token | Valor |
|---|---:|
| `space.1` | 4 px |
| `space.2` | 8 px |
| `space.3` | 12 px |
| `space.4` | 16 px |
| `space.5` | 20 px |
| `space.6` | 24 px |
| `space.8` | 32 px |
| `space.10` | 40 px |
| `space.12` | 48 px |
| `space.16` | 64 px |

Margem lateral padrão no celular: 24 px. Abaixo de 360 px: 16 px. Intervalo entre seções: 32 px. Intervalo entre cards: 12 ou 16 px.

### 4.2 Raios

| Token | Valor | Uso |
|---|---:|---|
| `radius.sm` | 8 px | Tags e detalhes |
| `radius.md` | 16 px | Campos e cards |
| `radius.lg` | 24 px | Painéis e bottom sheets |
| `radius.pill` | 999 px | Botões principais e chips |

### 4.3 Bordas e sombras

Borda padrão: marrom com 16% de opacidade, 1 px. Foco: vinho sólido, 3 px, com afastamento de 2 px.

Sombra de card: `0 4px 16px rgba(75, 41, 29, 0.08)`. Usar somente quando a borda não for suficiente. Não aplicar sombras em todos os elementos.

## 5. Layout responsivo

### 5.1 Celular

Base de projeto: 390 x 844 unidades lógicas. O layout deve funcionar entre 320 e 430 px de largura. A proporção 9:16 serve como referência visual e não como tamanho fixo.

### 5.2 Tablet e web

| Faixa | Regra |
|---|---|
| 431 a 767 px | Uma coluna central, largura fluida |
| 768 a 1023 px | Conteúdo até 720 px, duas colunas quando houver espaço |
| 1024 px ou mais | Container até 1200 px, leitura até 680 px por coluna |

Cards passam para duas colunas somente quando cada coluna comportar título, resumo e área de toque. Aumento de fonte pode devolver o layout para uma coluna.

### 5.3 Áreas seguras

Respeitar recortes, barra de status, indicador inferior e teclado. Páginas com navegação inferior reservam pelo menos 96 px no final do conteúdo, acrescidos da safe area do sistema.

## 6. Imagens e colagens

O Banco Visual Nós no Limiar possui 30 arquivos. Textos, botões e ícones permanecem nativos da interface e nunca devem ser incorporados às imagens.

### 6.1 Grupos de assets

| Arquivos | Conteúdo | Uso recomendado |
|---|---|---|
| 01 a 12 | Flores, folhas, ramos e ornamentos transparentes | Cabeçalhos, divisores, cantos e cards |
| 13 a 15 | Papéis rasgados e círculo vinho transparentes | Composição de fundos e destaques |
| 16 a 21 | Mulheres e mãos em colagem transparente | Hero, capa, página editorial |
| 22 a 30 | Composições prontas | Fundos, cards, artigos, stories e capas |

### 6.2 Mapeamento principal

| Contexto | Asset preferencial |
|---|---|
| Hero do site | `22-hero-site-horizontal.png` |
| Boas-vindas do app | `23-fundo-app-boas-vindas-vertical.png` |
| Card quadrado | `24-card-quadrado-botanico.png` |
| Cabeçalho de artigo | `25-cabecalho-artigo-horizontal.png` |
| Rodapé web | `26-fundo-rodape-horizontal.png` |
| Story ou tela vertical | `27-fundo-story-vertical.png` |
| Card horizontal | `28-card-horizontal-folhas.png` |
| Fundo de baixa interferência | `29-padrao-botanico-suave.png` |
| Capa editorial | `30-capa-editorial-mulher-flores.png` |

### 6.3 Regras de composição

- Usar uma composição principal por seção.
- Manter áreas de texto sobre creme ou vinho sólido.
- Evitar texto diretamente sobre flores, rostos e papéis com contraste variável.
- Preservar a proporção e o ponto focal.
- Não cortar rosto, mãos, flores principais ou o círculo vinho pela metade, salvo quando o asset foi criado com esse corte.
- Elementos transparentes podem ser combinados, com limite sugerido de três por composição.
- Textura de papel aparece nas imagens e em áreas editoriais específicas. Campos, botões e parágrafos ficam sobre superfícies limpas.
- Colagem decorativa recebe texto alternativo vazio. Imagem com informação recebe descrição objetiva.

## 7. Iconografia

Usar uma única família de ícones vetoriais de linha, como Lucide, com 24 px, traço de 1,75 px e pontas arredondadas.

Conjunto inicial: home, compass, bookmark, user, search, bell, arrow-left, arrow-right, chevron-right, share, clock, check, leaf, heart, coffee e book-open.

Ícones interativos têm nome acessível. Ícones decorativos são ignorados por leitores de tela. Emojis não substituem ícones de interface.

## 8. Componentes

Todos os componentes devem incluir estados padrão, foco, pressionado e desabilitado. Carregamento, erro e sucesso são adicionados quando a ação exige resposta do sistema.

### 8.1 Botão principal

- Altura mínima: 56 px.
- Padding horizontal: 24 px.
- Raio: pill.
- Fundo: vinho.
- Texto: creme, Inter 16/20, peso 600.
- Ícone opcional: 20 px.
- Pressionado: vinho com 88% de opacidade e deslocamento visual de 1 px.
- Foco: contorno vinho de 3 px em fundo claro; contorno creme em fundo vinho.
- Desabilitado: marrom a 40% sobre creme, com motivo visível quando necessário.
- Carregando: manter largura, preservar o rótulo e adicionar indicador.

### 8.2 Botão secundário

Fundo creme, texto vinho e borda vinho de 1 px. Mesmas dimensões e estados do botão principal.

### 8.3 Ação textual

Texto vinho, sublinhado ao foco ou hover. Área de toque mínima de 48 px quando isolada. Usar para ações de menor prioridade.

### 8.4 Botão de ícone

Área de toque 48 x 48 px, ícone 24 px, raio pill. Deve possuir rótulo acessível. Estado selecionado usa fundo rosa velho e ícone vinho.

### 8.5 Campo de formulário

- Label persistente acima do campo.
- Altura mínima: 52 px.
- Fundo: creme.
- Borda: marrom a 16%.
- Texto: marrom.
- Placeholder: marrom a 64%.
- Foco: borda e contorno vinho.
- Erro: borda vinho de 2 px, ícone e mensagem específica abaixo.
- Conteúdo digitado permanece após erro.

### 8.6 Busca

Ícone de busca, campo, ação limpar e envio pelo teclado. Label acessível: “Buscar conteúdos”. A consulta permanece quando a usuária volta à tela anterior.

### 8.7 Badge e chip

Altura mínima de 32 px. Fundo rosa velho, texto vinho. Tags informativas não devem parecer botões. Chips interativos incluem estado selecionado, foco e ação clara.

### 8.8 Card de conteúdo

Estrutura: imagem, categoria, título, resumo opcional, metadados e ação salvar.

- Raio: 16 px.
- Fundo: creme.
- Borda: marrom a 16%.
- Padding interno: 16 px.
- Imagem 4:3 ou 16:9 conforme o contexto.
- Título: H3.
- Área inteira pode navegar, mas salvar permanece como botão separado.
- Não aninhar botões dentro de links.

### 8.9 Card de destaque

Usar composição 22, 24, 25 ou 28 conforme a proporção. Texto em área limpa, com bloco sólido quando necessário. CTA e salvar mantêm áreas de toque independentes.

### 8.10 Item de categoria

Ícone em área de 48 px, rótulo abaixo ou ao lado. Em listas horizontais, permitir rolagem sem comprimir o texto. Estado atual usa vinho e marca visual adicional.

### 8.11 Linha de tópico

Altura mínima: 80 px. Ícone 48 px, título, descrição curta e chevron. A altura cresce com fonte ampliada.

### 8.12 Cabeçalho da marca

Logo central, com até uma ação em cada lado. As áreas laterais reservadas impedem colisão com a marca. Em telas estreitas, reduzir a logo dentro dos limites definidos.

### 8.13 Cabeçalho de página

Voltar, título e até duas ações. O botão voltar preserva a posição da tela anterior. Cabeçalho sobre imagem usa controles com fundo sólido ou placa de contraste.

### 8.14 Navegação inferior

Itens recomendados: Início, Explorar, Favoritos e Perfil. Altura visual mínima de 64 px, além da safe area. Cada item possui ícone e rótulo. O item atual é indicado por cor e forma, não somente por cor.

### 8.15 Dialog e bottom sheet

Dialog até 480 px. Bottom sheet com raio superior de 24 px. Ambos possuem título, ação fechar e ordem de foco controlada. O teclado não pode cobrir o campo ou a ação principal.

### 8.16 Alertas e mensagens

Como a paleta não inclui verde ou amarelo, status usam ícone, título e texto:

- Sucesso: marrom, ícone de confirmação e mensagem objetiva.
- Atenção: rosa velho como fundo, vinho no ícone e no texto.
- Erro: vinho, ícone de alerta e instrução de recuperação.

A cor nunca comunica o status sozinha.

### 8.17 Loading, skeleton e vazio

Skeleton utiliza marrom a 8% sobre creme e não é lido por tecnologia assistiva. Loading de botão impede envio duplicado. Estado vazio apresenta título, explicação e ação quando houver um próximo passo útil.

## 9. Padrões de tela

### 9.1 Boas-vindas

Ordem sugerida:

1. Safe area superior.
2. Logo de 220 a 240 px.
3. Asset `23-fundo-app-boas-vindas-vertical.png` ou composição com elementos 14, 16 e 04.
4. Título editorial.
5. Descrição curta.
6. Botão principal.
7. Ação de acesso existente.
8. Safe area inferior.

A tela deve rolar em aparelhos menores. Não usar navegação inferior.

### 9.2 Início

Cabeçalho da marca, saudação, busca, categorias, destaque semanal, recomendações e navegação inferior. A saudação não depende do nome da usuária. Cada seção carrega de maneira independente.

### 9.3 Conteúdo

Cabeçalho de artigo com asset 25, categoria, H1, resumo, metadados reais e corpo de leitura. A ação depende do formato: “Ler conteúdo”, “Ouvir áudio” ou “Começar atividade”. Parágrafos permanecem como texto acessível, sem rasterização.

### 9.4 Explorar

Busca ou título, categorias, filtros, resultados e navegação inferior. Filtros ativos aparecem como chips selecionados. A tela preserva consulta e filtros ao retornar de um conteúdo.

### 9.5 Favoritos

Lista de conteúdos salvos. Sem itens, exibir “Os conteúdos salvos aparecerão aqui” e uma ação para explorar. Favoritar pode atualizar imediatamente e reverter se houver falha.

### 9.6 Perfil

Dados essenciais, preferências, acessibilidade, notificações e sair. Não incluir perguntas clínicas ou dados sensíveis sem finalidade, consentimento e proteção definidos.

### 9.7 Novos planos

Usar “planos” somente após definir seu significado. Se a página tratar de projetos pessoais, preferir “Explorar possibilidades”. Se tratar de assinatura, a oferta precisa informar preço, periodicidade, condições e destino do pagamento.

## 10. Estados transversais

| Estado | Mensagem e comportamento |
|---|---|
| Carregando | Manter estrutura estável e anunciar atualização quando necessário |
| Sem conteúdo | “Ainda não há conteúdos nesta categoria.” |
| Busca sem resultado | “Nenhum conteúdo encontrado.” com ação limpar |
| Sem favoritos | “Os conteúdos salvos aparecerão aqui.” |
| Sem conexão | Exibir conteúdo local quando disponível e ação tentar novamente |
| Erro de servidor | “Não foi possível carregar o conteúdo.” |
| Falha ao salvar | Reverter estado e informar que o conteúdo não foi salvo |
| Formulário inválido | Mensagem junto ao campo e foco no primeiro erro após envio |
| Conteúdo removido | Informar indisponibilidade e permitir voltar ao catálogo |

Não simular sucesso quando a ação falhar. Erros aparecem depois da interação ou do envio, nunca antes.

## 11. Acessibilidade

- Contraste mínimo de 4,5:1 para texto normal e 3:1 para texto grande.
- Área de toque mínima de 48 x 48 px.
- Fonte ampliada até 200% sem perda de informação ou ação.
- Ordem de foco acompanha a leitura.
- Foco visível em todos os controles.
- Cabeçalhos seguem hierarquia sem saltos.
- Imagens informativas recebem descrição objetiva.
- Colagens decorativas usam texto alternativo vazio.
- Atualizações assíncronas são anunciadas sem interromper a leitura.
- Modais devolvem o foco ao acionador ao fechar.
- Conteúdo continua utilizável com redução de movimento.

## 12. Movimento

| Token | Duração | Uso |
|---|---:|---|
| `motion.fast` | 120 ms | Pressão e hover |
| `motion.normal` | 180 ms | Mudança de estado |
| `motion.panel` | 240 ms | Dialog e bottom sheet |

Easing padrão: `ease-out`. Evitar parallax, pulsação permanente e movimento ornamental. Animação não pode ser necessária para compreender o estado.

## 13. Linguagem do produto

Português brasileiro, frases diretas e vocabulário comum. A interface não diagnostica, promete cura ou transforma sentimentos em falha pessoal.

Rótulos descrevem a ação: “Salvar conteúdo”, “Ler artigo”, “Ouvir áudio” e “Tentar novamente”. Evitar “Clique aqui”, “Saiba mais” e “Continuar” quando uma ação específica estiver disponível.

Textos do mockup são exemplos e precisam de aprovação editorial antes da publicação.

## 14. Tokens para implementação

```json
{
  "color": {
    "wine": "#5C0003",
    "brown": "#4B291D",
    "cream": "#F5EFE5",
    "rose": "#C9826C"
  },
  "font": {
    "display": "Bodoni Moda, Didot, serif",
    "interface": "Inter, Arial, sans-serif"
  },
  "space": [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64],
  "radius": {
    "small": 8,
    "medium": 16,
    "large": 24,
    "pill": 999
  },
  "size": {
    "touchMin": 48,
    "buttonMin": 56,
    "fieldMin": 52,
    "icon": 24,
    "mobileGutter": 24,
    "readingMax": 680
  },
  "motion": {
    "fast": 120,
    "normal": 180,
    "panel": 240
  }
}
```

## 15. Nomenclatura de componentes

No Figma e no código, usar nomes previsíveis:

- `Button/Primary/Default`
- `Button/Primary/Pressed`
- `Button/Primary/Disabled`
- `Button/Secondary/Default`
- `Field/Text/Default`
- `Field/Text/Focus`
- `Field/Text/Error`
- `Card/Content/Vertical`
- `Card/Content/Horizontal`
- `Card/Featured`
- `Navigation/Bottom`
- `Header/Brand`
- `Header/Page`
- `Feedback/Alert`
- `Feedback/Empty`
- `Feedback/Skeleton`

Variantes ficam dentro do componente. Não duplicar um componente para mudar apenas cor, ícone ou texto.

## 16. Contratos de dados

```text
Content
id, slug, title, summary, categoryId, format,
image { src, alt, decorative, focalPoint },
estimatedMinutes?, access, saved, bodyOrMedia

Category
id, title, description?, iconKey, destination

UserPreference
fontScale, reducedMotion, notifications, savedCategories
```

Campos opcionais aparecem somente quando possuem valor. Contagens, dificuldade, preço e disponibilidade não podem ser inventados para preencher o layout.

## 17. Governança

### Quando criar um componente

Criar quando o padrão aparece em três contextos ou quando possui comportamento próprio. Uma variação visual isolada deve começar como composição de componentes existentes.

### Quando alterar um componente

Registrar o motivo, as telas afetadas, a mudança de acessibilidade e a versão. Alterações incompatíveis exigem migração planejada.

### Versão

- Patch: correção sem alterar uso.
- Minor: nova variante compatível.
- Major: mudança que exige adaptação das telas.

Este documento iniciou na versão 2.0 porque substituiu a especificação provisória anterior. A versão 2.1 acrescenta as combinações rosa velho sobre marrom e creme sobre rosa velho às regras de contraste e composição.

## 18. Entrega para desenvolvimento

O pacote de implementação deve conter:

1. Logo transparente aprovado.
2. Banco Visual com 30 PNGs.
3. Fontes ou links oficiais com licença confirmada.
4. Tokens centralizados no tema.
5. Componentes compartilhados.
6. Telas montadas com os componentes.
7. Estados de loading, vazio, erro e offline.
8. Testes de contraste, foco, teclado, leitor de tela e fonte ampliada.

Imagens do mockup não devem ser usadas como tela clicável. Molduras de telefone, sombras externas e cenário de apresentação ficam fora do aplicativo.

## 19. Critérios de aceite

- Paleta limitada aos quatro códigos oficiais.
- Logo preservada e sem reconstrução.
- Bodoni Moda restrita a títulos e expressão editorial.
- Inter aplicada a leitura e controles.
- Componentes com estados documentados.
- Área de toque mínima de 48 px.
- Tela funcional entre 320 e 430 px e adaptada a tablet e web.
- Textos continuam editáveis e acessíveis.
- Imagens utilizam assets separados do Banco Visual.
- Foco, contraste, fonte ampliada e redução de movimento verificados.
- Busca, favoritos e navegação preservam estado quando necessário.
- Nenhum botão ou link aparece sem destino funcional.
- Nenhuma função de pagamento, clínica ou assinatura é criada por inferência visual.

## 20. Pendências antes da publicação

- Confirmar o arquivo e a licença da fonte original do logo.
- Confirmar se Bodoni Moda será a fonte editorial definitiva.
- Definir autenticação, notificações, favoritos e funcionamento offline.
- Definir o significado e o destino de “planos”.
- Aprovar textos finais das telas.
- Validar os componentes em aparelho real com usuárias do público principal.

