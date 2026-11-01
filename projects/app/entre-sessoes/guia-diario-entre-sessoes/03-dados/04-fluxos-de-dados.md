# Fluxos de dados

Diagramas em Mermaid. Cada fluxo indica onde o dado nasce, por onde passa e onde termina. Nas fases 0 e 1, **nenhum fluxo sai do aparelho**, exceto F6, por gesto da analisanda.

## F1. Primeira abertura

```mermaid
sequenceDiagram
  actor A as Analisanda
  participant UI as Abertura
  participant R as Repositório
  A->>UI: abre o app
  UI->>R: lerConfig(nome), lerConfig(aberturaVista)
  alt sem nome ou abertura não vista
    UI-->>A: mostra Abertura (app inerte)
    A->>UI: digita nome + Começar agora
    UI->>R: gravarConfig(nome), gravarConfig(aberturaVista=true)
  end
  R->>R: se exemplosSemeados=false, semeia 3 exemplos
  UI-->>A: Semana com "Olá, {nome},"
```

## F2. Criar registro

```mermaid
flowchart LR
  P1[Passo 1 texto obrigatório] --> P2[Passo 2] --> P3[Passo 3 emoções] --> P4[Passo 4] --> P5[Passo 5 pergunta obrigatória + resposta] --> P6[Passo 6 despertares + extra] --> P7[Passo 7 sim/talvez/nao obrigatório]
  P7 -->|Salvar registro| V{valida}
  V -->|ok| S[repositorio.salvarRegistro]
  S --> DB[(Armazenamento local)]
  S --> L{bring = sim?}
  L -->|sim| N[Semana + aviso vinho + levar=true]
  L -->|não| M[Semana + toast]
```

Os dados do formulário ficam só na memória da página até salvar. Sair da aba Registrar no meio do caminho preserva os campos enquanto a página estiver aberta; recarregar perde (backlog: rascunho local).

## F3. Listar, filtrar e buscar

```mermaid
flowchart LR
  DB[(Registros)] --> O[ordena por ts desc] --> F{filtro} --> B{busca normalizada} --> C[até 40 cartões]
```

Busca: minúsculas, sem acentos, em `happened`, `mind`, `did`, `answer`, `extra` e rótulos das emoções.

## F4. Marcar o que levar

```mermaid
sequenceDiagram
  actor A as Analisanda
  participant UI as Aba Levar
  participant R as Repositório
  UI->>R: listarRegistros() sem exemplos
  UI-->>A: caixas marcadas conforme isLevar(r)
  A->>UI: marca ou desmarca
  UI->>R: marcarLevar(id, valor)
  UI->>UI: remonta texto para Mônica
```

## F5. Resumo

```mermaid
flowchart LR
  DB[(Registros)] --> J[janela 7 dias] --> T[total, inclui exemplos]
  J --> E[contagem de emoções]
  J --> D[3 despertares mais marcados]
```

## F6. Envio a Mônica (único fluxo que sai do aparelho)

```mermaid
sequenceDiagram
  actor A as Analisanda
  participant UI as Aba Levar
  participant SO as Área de transferência / WhatsApp
  actor M as Mônica
  A->>UI: Copiar texto ou Abrir WhatsApp
  UI->>SO: texto montado (mensagem.montar)
  A->>SO: confere e toca em enviar
  SO->>M: mensagem no WhatsApp
```

O app não sabe se a mensagem foi enviada. Nada é registrado.

## F7. Apagar

- Registro: confirmação em dois toques, exclusão definitiva no aparelho.
- Exemplos: confirmação, remove todos com `example = true`; não voltam (exemplosSemeados continua true).

## F8. Backup (fase 1)

```mermaid
flowchart LR
  E[Exportar] --> R[repositorio.exportar] --> C{senha?}
  C -->|sim| X[cifra AES-GCM] --> A[arquivo .json baixado]
  C -->|não| A
  I[Importar arquivo] --> V[valida backup.schema.json] --> D{cifrado?}
  D -->|sim| S[pede senha e decifra] --> M[mescla por id: mantém updatedTs maior]
  D -->|não| M
  M --> DB[(Registros)]
```

## F9. Migração v1 para v2 (fase 1)

Ver `05-backup-e-migracoes.md`.
