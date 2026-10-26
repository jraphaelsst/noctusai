/**
 * Commerce host-product copy (pt-BR + en) layered OVER the organ's i18n map.
 *
 * `usePageT()` resolves a key here first, then falls back to the organ's
 * `useCommerceT()` table (so `common.*`, `order_status.*`, ... come from the
 * organ — never duplicated here). Locale comes from the surrounding
 * `CommerceLocaleProvider` (storefront: the store's `locale`; back office:
 * the store profile's `locale`).
 *
 * `describeError()` maps the organ's API error codes (CONTRACT-DELTAS A2/A3)
 * to a translated sentence; an unmapped code falls back to the server's own
 * message (never blank, never swallowed).
 *
 * NOC-REMEDIATE[commerce-error-i18n-organ]: the `error.*` table belongs in the
 * organ's `seed/lib/frontend/src/commerce/messages.ts` so the organ components
 * (which today render the server `message`) map codes too; lift it there and
 * delete it from here (CONTRACT-DELTAS D3).
 */
import * as React from "react";
import { useCommerceT, resolveLocale, apiErrorCode, apiErrorStatus, type CommerceLocale } from "@noctusai/lib";

type Table = Record<string, string>;

const PT: Table = {
  // ── back office ──
  "admin.brand": "Commerce",
  "admin.group_store": "Loja",
  "admin.group_sales": "Vendas",
  "admin.group_settings": "Configurações",
  "admin.profile_title": "Perfil da loja",
  "admin.profile_intro": "Dados legais exibidos na vitrine (Decreto 7.962), regime tributário, idioma e identidade visual.",
  "admin.hosts_title": "Endereços da vitrine",
  "admin.hosts_intro": "Domínios em que esta loja atende compradores. Apenas a administração da plataforma pode alterá-los.",
  "admin.hosts_hostname": "Domínio",
  "admin.hosts_primary": "Principal",
  "admin.hosts_make_primary": "Definir como principal",
  "admin.hosts_add": "Adicionar endereço",
  "admin.hosts_empty": "Nenhum endereço cadastrado — a vitrine ainda não está acessível a compradores.",
  "admin.hosts_forbidden": "Somente a administração da plataforma pode ver e alterar os endereços desta loja.",
  "admin.hosts_remove_confirm": "Remover {host}? Compradores deixam de acessar a loja por este endereço.",
  "admin.categories_title": "Categorias",
  "admin.products_title": "Produtos",
  "admin.products_new": "Novo produto",
  "admin.products_search": "Buscar produtos",
  "admin.products_empty": "Nenhum produto cadastrado ainda.",
  "admin.products_empty_search": "Nenhum produto encontrado para esta busca.",
  "admin.products_col_title": "Produto",
  "admin.products_col_type": "Tipo",
  "admin.products_col_status": "Situação",
  "admin.products_col_updated": "Atualizado em",
  "admin.product_edit_title": "Editar produto",
  "admin.product_new_title": "Novo produto",
  "admin.product_offers_hint": "Salve o produto para cadastrar ofertas e mídias.",
  "admin.back_to_products": "Voltar para produtos",
  "admin.coupons_title": "Cupons",
  "admin.customers_title": "Clientes",
  "admin.customers_intro": "Clique em um cliente para ver pedidos, consentimentos e as ações de privacidade (exportar / anonimizar).",
  "admin.orders_title": "Pedidos",
  "admin.order_title": "Pedido",
  "admin.back_to_orders": "Voltar para pedidos",
  "admin.order_buyer": "Comprador",
  "admin.order_buyer_name": "Nome",
  "admin.order_buyer_doc": "CPF/CNPJ",
  "admin.order_fiscal_until": "Registro fiscal retido até",
  "admin.privacy_title": "Solicitações de privacidade",
  "admin.privacy_intro":
    "Os pedidos de titulares (acesso, correção, exclusão, portabilidade, revogação) chegam por e-mail verificado e ficam no cadastro do cliente. Atenda-os no cadastro do cliente abaixo: exportar os dados ou anonimizar.",
  "admin.keys_title": "Integrações (Asaas)",
  "admin.keys_intro": "Chave de API e token de webhook da conta Asaas desta loja. Os valores nunca são exibidos depois de salvos.",
  "admin.keys_admin_only": "Somente proprietários e administradores da organização podem gerenciar as chaves.",
  "admin.team_title": "Equipe",
  "admin.finance_title": "Financeiro",
  "admin.finance_intro": "Contas a receber e a pagar, fluxo de caixa, DRE, conciliação bancária e as ferramentas do contador.",
  "admin.items_title": "Itens",
  "admin.items_intro": "Catálogo de itens (SKU) com dados fiscais — a base para notas, estoque e financeiro.",
  "admin.items_tab_list": "Itens",
  "admin.items_tab_categories": "Categorias",
  "admin.items_tab_import": "Importar / exportar",
  "admin.items_back": "Voltar para itens",
  "admin.parties_title": "Parceiros",
  "admin.parties_intro": "Clientes, fornecedores e demais parceiros da loja (cadastro único com CPF/CNPJ).",
  "admin.inventory_title": "Estoque",
  "admin.inventory_intro": "Saldos por depósito, kardex, alertas de estoque baixo e valorização (custo médio).",
  "admin.inventory_tab_balances": "Saldos",
  "admin.inventory_tab_warehouses": "Depósitos",
  "admin.inventory_tab_alerts": "Alertas e valorização",
  "admin.inventory_back": "Voltar para saldos",
  "admin.purchasing_title": "Compras",
  "admin.purchasing_intro": "Pedidos de compra a fornecedores: rascunho, aprovação, envio e recebimento (entrada no estoque e contas a pagar).",
  "admin.purchasing_tab_orders": "Pedidos de compra",
  "admin.purchasing_tab_receipts": "Recebimentos",
  "admin.purchasing_tab_approvers": "Aprovadores",
  "admin.purchasing_back": "Voltar para compras",
  "admin.purchasing_receive": "Receber mercadoria",
  "admin.quotes_title": "Orçamentos",
  "admin.quotes_intro": "Propostas para clientes, com link seguro de aceite. Aceito, o orçamento de produtos vira um pedido e o de serviços vira um contrato (rascunho).",
  "admin.contracts_title": "Contratos",
  "admin.contracts_intro": "Contratos com cobrança recorrente: cada parcela vira uma conta a receber no financeiro.",
  "admin.settings_title": "Configurações",
  "admin.settings_intro": "Perfil da loja, endereços da vitrine e integrações.",
  "admin.settings_installments": "Parcelamento",
  "admin.settings_fiscal": "Dados fiscais",
  // ── storefront ──
  "store.cart": "Carrinho",
  "store.cart_count": "Carrinho ({count})",
  "store.my_orders": "Minhas compras",
  "store.privacy": "Privacidade",
  "store.continue_shopping": "Continuar comprando",
  "store.checkout_title": "Finalizar compra",
  "store.cart_empty_checkout": "Seu carrinho está vazio — adicione um produto antes de finalizar.",
  "store.staff_link": "Área do lojista",
  "store.myorders_list_title": "Suas compras",
  "store.myorders_empty": "Nenhuma compra encontrada para este e-mail.",
  "store.myorders_open": "Ver pedido",
  "store.myorders_request_new": "Pedir um novo link",
  "store.privacy_title": "Seus dados (LGPD)",
  "store.privacy_intro": "Peça acesso, correção, exclusão ou portabilidade dos seus dados. Enviaremos um link de confirmação para o seu e-mail.",
  "store.privacy_kind": "O que você deseja?",
  "store.privacy_details": "Detalhes (opcional)",
  "store.privacy_send": "Enviar solicitação",
  "store.privacy_sent": "Se houver um cadastro com este e-mail, enviamos um link para confirmar a solicitação.",
  "store.privacy_verify_title": "Confirmação da solicitação",
  "store.privacy_verifying": "Confirmando sua solicitação…",
  "store.privacy_verified": "Solicitação de {kind} confirmada. A loja vai atendê-la no prazo legal.",
  "store.privacy_no_token": "Link incompleto. Abra o link exatamente como recebido por e-mail.",
  "privacy_kind.access": "acesso aos dados",
  "privacy_kind.correction": "correção dos dados",
  "privacy_kind.deletion": "exclusão dos dados",
  "privacy_kind.portability": "portabilidade dos dados",
  "privacy_kind.revoke_consent": "revogação de consentimento",
  // ── API error codes (CONTRACT-DELTAS A2/A3 + host/profile codes) ──
  "error.documento_invalido": "CPF ou CNPJ inválido.",
  "error.oferta_indisponivel": "Uma das ofertas do carrinho não está mais disponível.",
  "error.cupom_invalido": "Cupom inválido ou expirado.",
  "error.total_zero": "O desconto não pode zerar o total do pedido.",
  "error.sem_oferta_ativa": "Para publicar, o produto precisa de ao menos uma oferta ativa.",
  "error.slug_em_uso": "Este identificador (slug) já está em uso.",
  "error.transicao_invalida": "Esta mudança de situação não é permitida para o pedido.",
  "error.link_invalido": "Este link é inválido ou expirou. Peça um novo.",
  "error.link_indisponivel": "Links por e-mail estão indisponíveis no momento. Tente mais tarde.",
  "error.midia_invalida": "Arquivo de mídia inválido (formato ou tamanho).",
  "error.assinatura_invalida": "Assinatura do aviso de pagamento inválida.",
  "error.cnpj_invalido": "CNPJ inválido.",
  "error.versao_conflitante": "Outra pessoa salvou antes de você. Recarregue e tente de novo.",
  "error.aceite_obrigatorio": "Os aceites obrigatórios não foram confirmados.",
  "error.pagamento_indisponivel": "Pagamento indisponível no momento. Tente novamente em instantes.",
  "error.pagamento_falhou": "Não foi possível gerar a cobrança. Tente novamente.",
  "error.loja_nao_configurada": "Esta loja ainda não concluiu a configuração de pagamentos.",
  "error.hostname_invalido": "Domínio inválido.",
  "error.host_ja_existe": "Este domínio já está em uso.",
  "error.cupom_ja_existe": "Já existe um cupom com este código.",
  "error.admin_obrigatorio": "Apenas administradores da organização podem fazer isso.",
  "error.forbidden": "Você não tem permissão para esta ação.",
  "error.not_found": "Não encontrado.",
  "error.rate_limited": "Muitas tentativas. Aguarde um pouco e tente de novo.",
  "error.estorno_falhou": "O gateway recusou ou não respondeu ao reembolso. Nada foi estornado — tente de novo.",
  "error.valor_excede_saldo": "O valor excede o saldo reembolsável.",
  "error.pedido_nao_reembolsavel": "Este pedido não pode ser reembolsado agora.",
  "error.pedido_alterado": "O pedido mudou enquanto você agia. Recarregue a página.",
  "error.muitas_tentativas": "Muitas tentativas de pagamento. Aguarde um pouco ou fale com a loja.",
  "error.parcelamento_invalido": "Esse parcelamento não está disponível para este pedido.",
};

const EN: Table = {
  "admin.brand": "Commerce",
  "admin.group_store": "Store",
  "admin.group_sales": "Sales",
  "admin.group_settings": "Settings",
  "admin.profile_title": "Store profile",
  "admin.profile_intro": "Legal details shown on the storefront (Decree 7.962), tax regime, language and visual identity.",
  "admin.hosts_title": "Storefront addresses",
  "admin.hosts_intro": "Domains where this store serves buyers. Only platform administrators can change them.",
  "admin.hosts_hostname": "Domain",
  "admin.hosts_primary": "Primary",
  "admin.hosts_make_primary": "Make primary",
  "admin.hosts_add": "Add address",
  "admin.hosts_empty": "No address yet — buyers cannot reach the storefront.",
  "admin.hosts_forbidden": "Only platform administrators can view and change this store's addresses.",
  "admin.hosts_remove_confirm": "Remove {host}? Buyers will no longer reach the store at this address.",
  "admin.categories_title": "Categories",
  "admin.products_title": "Products",
  "admin.products_new": "New product",
  "admin.products_search": "Search products",
  "admin.products_empty": "No products yet.",
  "admin.products_empty_search": "No products match this search.",
  "admin.products_col_title": "Product",
  "admin.products_col_type": "Type",
  "admin.products_col_status": "Status",
  "admin.products_col_updated": "Updated",
  "admin.product_edit_title": "Edit product",
  "admin.product_new_title": "New product",
  "admin.product_offers_hint": "Save the product to add offers and media.",
  "admin.back_to_products": "Back to products",
  "admin.coupons_title": "Coupons",
  "admin.customers_title": "Customers",
  "admin.customers_intro": "Click a customer to see orders, consents and the privacy actions (export / anonymize).",
  "admin.orders_title": "Orders",
  "admin.order_title": "Order",
  "admin.back_to_orders": "Back to orders",
  "admin.order_buyer": "Buyer",
  "admin.order_buyer_name": "Name",
  "admin.order_buyer_doc": "Tax ID",
  "admin.order_fiscal_until": "Tax record retained until",
  "admin.privacy_title": "Privacy requests",
  "admin.privacy_intro":
    "Data-subject requests (access, correction, deletion, portability, consent withdrawal) arrive by verified e-mail and are kept on the customer record. Handle them on the customer record below: export the data or anonymize.",
  "admin.keys_title": "Integrations (Asaas)",
  "admin.keys_intro": "API key and webhook token of this store's Asaas account. Values are never shown again after saving.",
  "admin.keys_admin_only": "Only organization owners and administrators can manage the keys.",
  "admin.team_title": "Team",
  "admin.finance_title": "Finance",
  "admin.finance_intro": "Receivables and payables, cash flow, income statement, bank reconciliation and the accountant tools.",
  "admin.items_title": "Items",
  "admin.items_intro": "Item (SKU) catalog with tax data — the base for invoices, stock and finance.",
  "admin.items_tab_list": "Items",
  "admin.items_tab_categories": "Categories",
  "admin.items_tab_import": "Import / export",
  "admin.items_back": "Back to items",
  "admin.parties_title": "Partners",
  "admin.parties_intro": "Customers, suppliers and other partners of the store (one registry keyed by CPF/CNPJ).",
  "admin.inventory_title": "Stock",
  "admin.inventory_intro": "Balances per warehouse, kardex, low-stock alerts and valuation (average cost).",
  "admin.inventory_tab_balances": "Balances",
  "admin.inventory_tab_warehouses": "Warehouses",
  "admin.inventory_tab_alerts": "Alerts and valuation",
  "admin.inventory_back": "Back to balances",
  "admin.purchasing_title": "Purchasing",
  "admin.purchasing_intro": "Purchase orders to suppliers: draft, approval, sending and receiving (stock in and payables).",
  "admin.purchasing_tab_orders": "Purchase orders",
  "admin.purchasing_tab_receipts": "Receipts",
  "admin.purchasing_tab_approvers": "Approvers",
  "admin.purchasing_back": "Back to purchasing",
  "admin.purchasing_receive": "Receive goods",
  "admin.quotes_title": "Quotes",
  "admin.quotes_intro": "Proposals for customers with a secure acceptance link. Once accepted, a goods quote becomes an order and a services quote becomes a (draft) contract.",
  "admin.contracts_title": "Contracts",
  "admin.contracts_intro": "Contracts with recurring billing: each installment becomes a receivable in finance.",
  "admin.settings_title": "Settings",
  "admin.settings_intro": "Store profile, storefront addresses and integrations.",
  "admin.settings_installments": "Installments",
  "admin.settings_fiscal": "Tax details",
  "store.cart": "Cart",
  "store.cart_count": "Cart ({count})",
  "store.my_orders": "My orders",
  "store.privacy": "Privacy",
  "store.continue_shopping": "Continue shopping",
  "store.checkout_title": "Checkout",
  "store.cart_empty_checkout": "Your cart is empty — add a product before checking out.",
  "store.staff_link": "Store admin",
  "store.myorders_list_title": "Your orders",
  "store.myorders_empty": "No orders found for this e-mail.",
  "store.myorders_open": "View order",
  "store.myorders_request_new": "Request a new link",
  "store.privacy_title": "Your data (LGPD)",
  "store.privacy_intro": "Request access, correction, deletion or portability of your data. We will e-mail you a confirmation link.",
  "store.privacy_kind": "What do you need?",
  "store.privacy_details": "Details (optional)",
  "store.privacy_send": "Send request",
  "store.privacy_sent": "If there is an account with this e-mail, we sent a link to confirm the request.",
  "store.privacy_verify_title": "Request confirmation",
  "store.privacy_verifying": "Confirming your request…",
  "store.privacy_verified": "Your {kind} request is confirmed. The store will handle it within the legal deadline.",
  "store.privacy_no_token": "Incomplete link. Open the link exactly as received by e-mail.",
  "privacy_kind.access": "data access",
  "privacy_kind.correction": "data correction",
  "privacy_kind.deletion": "data deletion",
  "privacy_kind.portability": "data portability",
  "privacy_kind.revoke_consent": "consent withdrawal",
  "error.documento_invalido": "Invalid CPF or CNPJ.",
  "error.oferta_indisponivel": "One of the offers in your cart is no longer available.",
  "error.cupom_invalido": "Invalid or expired coupon.",
  "error.total_zero": "A discount cannot bring the order total to zero.",
  "error.sem_oferta_ativa": "A product needs at least one active offer to be published.",
  "error.slug_em_uso": "This identifier (slug) is already in use.",
  "error.transicao_invalida": "This status change is not allowed for the order.",
  "error.link_invalido": "This link is invalid or expired. Request a new one.",
  "error.link_indisponivel": "E-mailed links are unavailable right now. Try again later.",
  "error.midia_invalida": "Invalid media file (format or size).",
  "error.assinatura_invalida": "Invalid payment notification signature.",
  "error.cnpj_invalido": "Invalid CNPJ.",
  "error.versao_conflitante": "Someone else saved first. Reload and try again.",
  "error.aceite_obrigatorio": "The required agreements were not confirmed.",
  "error.pagamento_indisponivel": "Payment is unavailable right now. Try again shortly.",
  "error.pagamento_falhou": "The charge could not be created. Try again.",
  "error.loja_nao_configurada": "This store has not finished setting up payments yet.",
  "error.hostname_invalido": "Invalid domain.",
  "error.host_ja_existe": "This domain is already in use.",
  "error.cupom_ja_existe": "A coupon with this code already exists.",
  "error.admin_obrigatorio": "Only organization administrators can do this.",
  "error.forbidden": "You are not allowed to do this.",
  "error.not_found": "Not found.",
  "error.rate_limited": "Too many attempts. Wait a moment and try again.",
  "error.estorno_falhou": "The gateway refused or did not answer the refund. Nothing was refunded — try again.",
  "error.valor_excede_saldo": "The amount exceeds the refundable balance.",
  "error.pedido_nao_reembolsavel": "This order cannot be refunded right now.",
  "error.pedido_alterado": "The order changed while you were acting. Reload the page.",
  "error.muitas_tentativas": "Too many payment attempts. Wait a moment or contact the store.",
  "error.parcelamento_invalido": "This installment option is not available for this order.",
};

export const PAGE_MESSAGES: Record<CommerceLocale, Table> = { "pt-BR": PT, en: EN } as Record<CommerceLocale, Table>;

export type PageTranslate = (key: string, vars?: Record<string, string | number>) => string;

function interpolate(raw: string, vars?: Record<string, string | number>): string {
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
}

/** Host copy first, organ copy second, the key itself last (visible, never blank). */
export function usePageT(localeOverride?: string): { t: PageTranslate; locale: CommerceLocale } {
  const { t: organT, locale } = useCommerceT(localeOverride);
  const t = React.useCallback<PageTranslate>(
    (key, vars) => {
      const own = PAGE_MESSAGES[resolveLocale(locale)]?.[key] ?? PT[key];
      return own !== undefined ? interpolate(own, vars) : organT(key, vars);
    },
    [locale, organT],
  );
  return { t, locale };
}

/** A translated sentence for an API error: code → status → server message. */
export function describeError(err: unknown, t: PageTranslate): string {
  if (!err) return "";
  const code = apiErrorCode(err);
  if (code) {
    const key = `error.${code}`;
    const msg = t(key);
    if (msg !== key) return msg;
  }
  const status = apiErrorStatus(err);
  if (status === 403) return t("error.forbidden");
  if (status === 429) return t("error.rate_limited");
  if (status === 404) return t("error.not_found");
  if (status === 502) return t("error.pagamento_falhou");
  if (status === 503) return t("error.pagamento_indisponivel");
  return err instanceof Error ? err.message : String(err);
}
