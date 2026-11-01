# Imagens

Banco Visual Nós no Limiar: 30 PNGs (não incluídos neste pacote pelo tamanho; pedir a Mônica). As versões reduzidas usadas no app estão em `fonte/assets/`.

## Mapa por tela

| Tela | Asset do banco | Arquivo no app | Tratamento |
|---|---|---|---|
| Abertura | 23 fundo app boas-vindas vertical | w23.webp (440x782) | cover, esmaece em cima e embaixo |
| Registrar passo 1 | 16 mulher de costas com flores | g1.webp | recorte transparente, contain |
| Passo 2 | 20 mulher à janela | g2.webp | idem |
| Passo 3 | 21 mãos segurando flores | g3.webp | idem |
| Passo 4 e aba Levar | 19 mulher caminhando | g4.webp | idem |
| Passo 5 | 18 mulher sentada lendo | g5.webp | idem |
| Passo 6 | 17 mulher de perfil | g6.webp | idem |
| Passo 7 e Como usar | 22 hero horizontal | g7.webp | cover com esmaecimento |
| Resumo | 25 cabeçalho de artigo | c25.webp | cover |
| Citação (teste) | 28 card horizontal folhas | c28.webp | faixa de 150 px sobre bloco vinho |
| Filtros Esta semana / Levar / Talvez | composições de botânicos 01 a 11 | pa, pb, pc.webp | painéis foscos, sem texto |
| Rodapé | 26 fundo rodapé | grod.webp | faixa com esmaecimento |

## Regras

1. Uma composição principal por tela.
2. Texto nunca sobre rosto, flores ou papel de contraste variável. Texto fica em creme ou vinho liso.
3. Imagens decorativas com `aria-hidden="true"` ou alt vazio.
4. Não cortar rosto, mãos ou o círculo vinho pela metade.

## Orçamento de peso

- App completo: **até 400 KB** (hoje cerca de 340 KB na versão de teste, 370 KB na v21).
- Cada imagem nova: webp, largura máxima 640 px (recortes 400 px), qualidade 38 a 50, alfa 60. Medir o ganho visual contra o peso; base64 aumenta cerca de 33%.
- Processamento sugerido (Pillow): redimensionar com LANCZOS, `save(..., 'webp', quality=42, method=6)`.
