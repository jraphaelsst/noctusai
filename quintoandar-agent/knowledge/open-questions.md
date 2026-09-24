# Open questions & untested actions

## A · Questions for the user

### Open
- [ ] Some properties marked Aluguel + Venda show a single value in lists, and the published
      HYBRID property page showed only the Aluguel price card. Why?
- [ ] "TIC" and "CCV" (sale-offer chips/routes) — the portal never defines them.
- [ ] Two HYBRID leads listed "Com pendências" show NO "Anúncio com pendências" card nor
      its buttons on their lead page. Expected?
- [ ] Is `/photos` ("Sessões de Fotos", no menu link) a screen the team uses?
- [ ] Should any write action (§B) be tested on a test property, with per-action consent?
- [ ] Motivo lists were sampled from page 1 only — is the full reason inventory needed?
- [ ] Red floating icon on property pages: `#aiFabShadowRoot` injected on `<html>`, Adobe
      Acrobat logo, outside the app — confirm it's a browser extension.

### Answered
- [x] Floating green "$" button = browser extension, not the portal
      `[confirmado pelo usuário]`. (Unrelated-host images from `cuponomia.com.br` and a
      "Lojas similares que têm cashback" popup also appeared on the page.)
- [x] Sidebar vs. list total for "Todos os imóveis" — user doesn't know the cause; record
      the divergence only `[confirmado pelo usuário]`.
- [x] Scope rule for mapping: 10 detail pages across statuses, forms may be opened, never
      saved `[confirmado pelo usuário]`.

## B · Controls never clicked (writes / unknown effect)

| Control (exact label) | Where |
|---|---|
| Confirmar visita · Cancelar visita | visit drawers, "⋮" |
| Baixar autorização de entrada | "⋮"; property Visitas tab (download) |
| Abrir anúncio no QuintoAndar | visit "⋮" |
| Confirmar horários | hours modal |
| Continuar (after changing the key option) · Confirmar alteração | entry wizard |
| Enviar correções | "Revisar anúncio" |
| Reativar anúncio | deactivated property Resumo |
| Marcar pendências como resolvidas · Descartar anúncio | lead page |
| Salvar | "Alteração de preço" |
| Alterar valor · Compartilhar no WhatsApp | report setup |
| Compartilhar relatório | expanded performance row |
| Editar preço · Editar imóvel | performance "⋮" |
| Editar horários de visitas · Mostrar anúncio | `/listing` page |
| Adicionar usuário · Reenviar convite · trash icon | Gerenciar usuários |
| Salvar área de atuação · Desmarcar todos os bairros · map clicks · Editar áreas selecionadas | operation areas |
| Final steps of "Agendar fotos" | `/photos` |
| Last "Continuar" of the Calculadora | step 5 |
| Sair da conta | user menu (logs out) |
