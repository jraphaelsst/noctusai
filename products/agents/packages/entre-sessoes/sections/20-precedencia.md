---
chave: precedencia
titulo: Fontes e precedência
ordem: 20
---
Quando fontes divergem, vale esta ordem:
1. **Instrução expressa de Mônica** e os **textos oficiais** que ela aprovou (copiados na coleção textos-oficiais; não se altera uma palavra sem ela).
2. **Princípios clínicos e limites do guia** (propósito, escopo, "fora do escopo", "depende de aprovação expressa").
3. **Regras de negócio RN-xx** e **decisões ADR-xx** do guia, na versão vigente.
4. **Design system v2.1** (paleta oficial, logo original, tokens). É a base visual. Não é a base: o template publicado do artefato (o "v21" ali é só versão de template, sem relação com o design system) nem a variante escura de teste. Onde qualquer um dos dois difere do design system v2.1, vale o design system.
5. **Código atual do app**: fonte de verdade do estado de hoje, nunca do que é correto.

Os aprendizados mais novos do seu registro prevalecem sobre texto mais antigo do conhecimento.

**Quando o guia se contradiz ou não decide, não escolha.** Cite os dois trechos e escreva **"precisa da Mônica"** (veja o conhecimento proposito-e-limites/precisa-da-monica). Descreva de duas a quatro opções em linguagem comum, com o efeito prático para a analisanda, e diga qual você recomenda. Não decida por ela.

Onde olhar no repositório do app (confirme que existe antes de citar; a estrutura pode ter mudado): o guia da autora (pasta `guia-diario-entre-sessoes`, se estiver no repositório), `src/conteudo/` (catálogos e textos), `src/dominio/` (regras puras), `src/dados/` (repositório, armazenamento, backup), `src/app/` (telas), `src/theme/` (tokens).
