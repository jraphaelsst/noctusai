---
titulo: "Identidade visual — o essencial para revisar uma tela"
tipo: sintese
proveniencia:
  origem: "limiar-app agents/nos-no-limiar/knowledge/04-identidade-visual.md (v0.1.0)"
  notas: "Sintetizado em 2026-10-03 a partir da sessão de desenvolvimento do limiar-app."
---
# Identidade visual — o essencial para revisar uma tela

Fonte completa: `docs/design/visual-identity.md` (valores) e `src/theme/` (código, prevalece).
Guia visual publicado: https://claude.ai/artifact/4yUqxRhrSTCd1GSuUnvXxP

## Regras que mais aparecem em revisão
- **Vinho `#651B19` significa "agir"**: botão principal, aba ativa, estado selecionado. Uma ação
  principal em vinho por tela. Nunca decoração.
- Fundo off-white `#F3F0EA`; superfícies `#FAF7F1`; areia `#D8CBB8` para chips e fundos de card.
- `sun #782B20` só em ilustração/colagem — nunca em texto ou controle.
- Em fundo areia, texto em `ink`, nunca no cinza de corpo (contraste 4,25:1 reprova).
- Nenhuma cor literal em componente: tudo via `color.*` dos tokens.
- Tipografia: **Cormorant Garamond** (títulos, botões, cards) · **Lora** (leitura) · **Inter** (interface,
  chips, abas, legendas). Escala aprovada no iPhone em 2026-10-03.
- Acentos altos do Cormorant: **aceitos como caráter da marca** (a tagline do logo tem o mesmo traço).
- Números no Cormorant sempre `lining-nums`; números de emergência em Inter.
- Ícones Phosphor `light`; `fill` só para aba ativa/seleção. Salvos = **marcador**, não coração.
- Logo: arquivos em `assets/brand/`; 240 pt nas boas-vindas, 176 pt em cabeçalhos; nunca redigitar.
- Imagem: colagem analógica (papel rasgado, sol vinho, botânica). **Boas-vindas sem fotografia**.
  Texto nunca dentro de bitmap.
- Sem métricas sociais (curtidas), sem gamificação, sem streaks.
