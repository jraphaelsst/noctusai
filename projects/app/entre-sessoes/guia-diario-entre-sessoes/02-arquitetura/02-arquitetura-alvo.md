# Arquitetura alvo

A evolução tem três fases. **Fase 1 é a recomendada e pode ser feita sem nova decisão de Mônica além de aprovar o roteiro. Fase 2 só começa com aprovação expressa dela.**

## Fase 1: app local robusto (PWA, sem servidor de dados)

Objetivo: resolver perda de dados e dependências externas mantendo a regra de que nada sai do aparelho sem decisão da analisanda.

- **Projeto em módulos** (JavaScript puro em ES modules, sem framework), empacotado num único HTML ou num site estático pequeno. Ferramenta de build sugerida: Vite. Alternativa aceitável: manter `build.py`.
- **PWA**: `manifest.webmanifest` e service worker com cache do app para abrir sem internet. Ao ser adicionado à tela de início, o app fica fora do limite de 7 dias do Safari.
- **IndexedDB** no lugar do `localStorage` para registros (esquema em `03-dados/schemas/indexeddb.md`), com `navigator.storage.persist()` pedido após o primeiro registro salvo.
- **Backup**: exportar todos os registros num arquivo `.json` (schema `backup.schema.json`) e importar de volta, com mesclagem por `id`. Criptografia opcional com senha (Web Crypto, AES-GCM, chave derivada por PBKDF2).
- **Fontes servidas pelo próprio app** (arquivos woff2 de Bodoni Moda e Inter, licença SIL Open Font License 1.1), sem chamada ao Google.
- **Migração de dados v1 → v2** na primeira abertura da nova versão, lendo o `localStorage` antigo.
- **Hospedagem**: domínio próprio da marca (site estático com HTTPS). Sem banco, sem coleta.
- **Trocar nome** em Como usar ou num menu discreto.

Estrutura de pastas sugerida:

```
diario/
  index.html
  manifest.webmanifest
  sw.js
  src/
    main.js              # inicialização, abertura, abas
    conteudo/            # catálogos e textos (somente dados)
      emocoes.js  perguntas.js  despertares.js  citacoes.js  textos.js
    dados/
      repositorio.js     # interface única de leitura e escrita
      idb.js             # implementação IndexedDB
      legado.js          # leitura do localStorage v1 e migração
      backup.js          # exportar e importar
      schema.js          # validação das estruturas
    dominio/
      regras.js          # isLevar, janela de 7 dias, filtros, contagens
      mensagem.js        # montagem do texto para Mônica
    telas/
      abertura.js semana.js registrar.js levar.js resumo.js comousar.js rodape.js
    ui/
      el.js icones.js toast.js
    estilo/
      tokens.css base.css componentes.css telas.css
  assets/  (webp, woff2, ícones do PWA)
  tests/   (Playwright)
```

## Fase 2 (somente com aprovação): conta, sincronização e caixa de envios

Motivação possível: a analisanda usa mais de um aparelho, ou Mônica prefere receber os envios dentro do app em vez do WhatsApp.

- Backend com PostgreSQL, autenticação por e-mail com link mágico e políticas de acesso por linha (RLS). Esquema em `03-dados/schemas/banco.sql`.
- **Criptografia de ponta a ponta recomendada**: o conteúdo dos registros é cifrado no aparelho; o servidor guarda apenas texto cifrado. Envios a Mônica são cifrados para a chave dela.
- Mônica acessa **somente envios** (P2). Nunca registros não enviados.
- Exige avaliação jurídica (LGPD, dados sensíveis de saúde), termo de consentimento, política de privacidade e definição de operador de infraestrutura. Ver `06-privacidade-e-seguranca/01-lgpd-e-seguranca.md`.

## Fora de qualquer fase

Itens de `01-produto/02-escopo.md` marcados como fora do escopo.
