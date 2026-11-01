# Estado atual (fase 0)

## Resumo técnico

- **Um único arquivo HTML** autocontido (`fonte/diario-entre-sessoes.html`, cerca de 340 a 370 KB), com CSS e JavaScript embutidos e imagens em base64 (webp).
- **Sem framework, sem dependências de execução**, JavaScript ES5/ES2015 dentro de uma IIFE com `'use strict'`.
- **Única dependência externa**: Google Fonts (Bodoni Moda 500 e itálico 500; Inter 400, 600 e 700).
- **Sem servidor**. Dados em `localStorage` do navegador da analisanda.
- **Hospedagem atual**: página publicada como artifact no claude.ai (endereço fixo, versões numeradas). Cada artifact roda em origem própria, então o `localStorage` pertence a essa origem.

## Montagem (build)

Arquivos em `fonte/`:

| Arquivo | Papel |
|---|---|
| `template.html` | Fonte da verdade (versão de teste escura). Contém marcadores `{{...}}` no lugar das imagens |
| `template_v21.html` | Fonte da versão oficial publicada (v21) |
| `build.py` | Substitui os marcadores pelo base64 das imagens em `assets/` e gera `diario-entre-sessoes.html` e `check.js` |
| `assets/*.webp` | Imagens já reduzidas |
| `assets/torn.txt` | SVG de papel rasgado em data URI (marcador `{{TORN}}`) |

Comandos:

```bash
cd fonte
python3 build.py              # gera diario-entre-sessoes.html e check.js
node --check check.js         # confere a sintaxe do script
```

Para montar a versão oficial v21: `python3 build.py template_v21.html`.

Marcadores e imagens:

| Marcador | Arquivo | Uso |
|---|---|---|
| `{{LOGO}}` | glogo.webp | Logo Nós no Limiar |
| `{{G1}}` | g1.webp | Passos 1 (mulher de costas com flores, asset 16) |
| `{{G2}}` | g2.webp | Passo 2 (mulher à janela, asset 20) |
| `{{G3}}` | g3.webp | Passo 3 (mãos com flores, asset 21) |
| `{{G4}}` | g4.webp | Passo 4 e aba Levar (mulher caminhando, asset 19) |
| `{{G5}}` | g5.webp | Passo 5 (mulher lendo, asset 18) |
| `{{G6}}` | g6.webp | Passo 6 (mulher de perfil, asset 17) |
| `{{G7}}` | g7.webp | Passo 7 e Como usar (composição horizontal, asset 22) |
| `{{GROD}}` | grod.webp | Faixa do rodapé (asset 26) |
| `{{W23}}` | w23.webp | Abertura (asset 23) |
| `{{C25}}` | c25.webp | Cabeçalho do Resumo (asset 25) |
| `{{C28}}` | c28.webp | Cartão da citação, só na versão de teste (asset 28) |
| `{{ARR}}` | arranjo.webp | Arranjo fosco atrás da citação, só na v21 |
| `{{PA}}` `{{PB}}` `{{PC}}` | pa/pb/pc.webp | Painéis de flores dos filtros Esta semana, Levar, Talvez |

## Mapa do código (template.html, bloco `<script>`)

| Seção | Funções e dados principais |
|---|---|
| Conteúdo fixo | `WHATSAPP`, `EMOCOES`, `PERGUNTAS`, `DESPERTOU`, `BRING`, `ICONS`, `icon()` |
| Armazenamento | chaves `STORE_KEY` etc., `lsGet`, `lsSet`, `store`, `load()`, `persist()`, `seedExamples()` |
| Utilidades | `fmtWhen`, `fmtDM`, `clip`, `norm`, `weekRange`, `el`, `byId`, `toast` |
| Nome e sessão | `aplicarNome`, `esconderNomeSeCadastrado`, listeners de `#nome` e `#sessao` |
| Abas | `TABS`, `show(tab)`, navegação por setas |
| Semana | `isLevar`, `CITACOES`, `renderQuote`, `renderSavedNote`, `FILTROS`, `renderTiles`, `passa`, `renderExBar`, `recCard`, `renderSemana` |
| Registrar | montagem dos controles, `validate`, `go(n)`, `saveRecord` |
| Resumo e Levar | `countBy`, `sortedEntries`, `buildLevarMsg`, `renderLevar`, `renderLevarSend`, `renderResumo` |
| Abertura | `fecharAbertura`, condição de exibição |

Renderização: imperativa. Cada `render*` limpa o contêiner e recria os nós com `el()`. Não há estado reativo; quem muda dados chama `persist()` e depois o `render` da tela visível.

## Limitações conhecidas

1. `q` e `awakened` guardam **índices** das listas. Reordenar `PERGUNTAS` ou `DESPERTOU` corrompe o significado de registros antigos. Corrigir na migração v2 (ver `03-dados/05-backup-e-migracoes.md`).
2. `localStorage` tem limite de alguns MB por origem e é síncrono.
3. No Safari (iOS e macOS), o armazenamento gravado por script pode ser apagado depois de 7 dias de uso do navegador sem a pessoa interagir com o site, exceto em apps adicionados à tela de início (WebKit, 2020). Risco real de perda de registros.
4. Não há backup nem exportação. Trocar de aparelho ou limpar o navegador apaga tudo.
5. A lista mostra no máximo 40 registros, mesmo com busca.
6. Não há como trocar o nome depois do cadastro.
7. Fontes vêm do Google (envio do IP da analisanda a terceiro e dependência de rede).
8. Hospedagem dependente da plataforma do artifact.
