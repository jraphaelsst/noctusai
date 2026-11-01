# Banco de dados do servidor (fase 2)

**Status: proposta. Não implementar sem aprovação expressa de Mônica e sem avaliação jurídica.**

DDL completo com políticas de segurança por linha e carga de catálogos: `schemas/banco.sql` (PostgreSQL 15+, pensado para Supabase).

## Tabelas

| Tabela | Finalidade | Dados sensíveis | Quem lê |
|---|---|---|---|
| `pessoa` | Identidade autenticada e papel | não | a própria pessoa |
| `profissional` | Mônica: nome, WhatsApp, chave pública | não | ela mesma e suas analisandas |
| `analisanda` | Vínculo com a profissional, nome e sessão cifrados | sim (cifrado) | a própria; a profissional vê a existência e o nome cifrado |
| `termo` | Versões do termo de consentimento | não | autenticadas |
| `consentimento` | Aceite e revogação por analisanda | não | a própria |
| `emocao`, `pergunta`, `despertar`, `citacao` | Catálogos | não | autenticadas |
| `registro` | Registro do diário com conteúdo cifrado | sim (cifrado) | **só a dona** |
| `registro_emocao`, `registro_despertar` | Metadados em claro (opcional, desaconselhado) | sim | só a dona |
| `envio` | Pacote enviado a Mônica, cifrado para ela | sim (cifrado) | a analisanda que enviou e a profissional destinatária |
| `envio_item` | Quais registros compõem o envio | não | as duas partes |
| `evento` | Auditoria sem conteúdo | não | a própria pessoa |

## Decisões de modelagem

1. **Conteúdo cifrado no aparelho.** Os campos de texto, emoções e despertares vão dentro de `conteudo_cifrado`. O servidor não consegue ler o diário.
2. **Profissional sem acesso a `registro`.** Ela lê apenas `envio`. Isso implementa P2 no próprio banco, não só na interface.
3. **Envio é uma cópia.** Se a analisanda apagar o registro depois, o envio que Mônica recebeu permanece, como acontece hoje no WhatsApp. `envio_item.registro_id` não tem chave estrangeira por isso.
4. **Exclusão lógica em `registro.apagado_em`** só para propagar a exclusão a outros aparelhos; purga definitiva em 30 dias por tarefa agendada.
5. **Exemplos não sobem.** Ficam só no aparelho.
6. **Exclusão de conta** apaga `pessoa` em cascata; envios já recebidos pela profissional seguem a política de guarda definida por Mônica com assessoria jurídica.

## Sincronização (resumo)

- Cada aparelho mantém IndexedDB como fonte local.
- Envia alterações com `atualizado_em`; o servidor aceita a versão com `atualizado_em` maior (última escrita vence, por registro).
- Busca e Resumo continuam calculados no aparelho, sobre dados decifrados.
