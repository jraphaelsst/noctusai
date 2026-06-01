/**
 * Checkout — Phase 7 SKELETON.
 *
 * Order placement form. Uses react-hook-form (already a dep) so Phase 7 PROPER
 * can drop in zod resolvers + a real submit handler with no structural rework.
 */
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { CreditCard, FileCheck } from "lucide-react";
import { useCart, useCartMutations } from "@/hooks/useCart";

interface CheckoutFormData {
  delivery_address: string;
  delivery_city: string;
  delivery_state: string;
  delivery_zip: string;
  payment_method: "boleto" | "credit_card" | "pix";
  notes?: string;
}

const inputClass =
  "w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export default function Checkout() {
  const navigate = useNavigate();
  const { data: cart } = useCart();
  // Checkout finalizes the server-side cart (the `checkout` mutation takes only
  // { observacoes }); usePlaceOrder is the lower-level items-array path.
  const { checkout } = useCartMutations();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CheckoutFormData>({
    defaultValues: {
      payment_method: "boleto",
    },
  });

  const onSubmit = (data: CheckoutFormData) => {
    if (!cart) return;
    checkout.mutate({ observacoes: data.notes });
    // TODO(adconnect-phase-7): on success, navigate to /orders/{newOrderId}
    // and clear the cart cache.
    navigate("/orders");
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <FileCheck className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Finalizar pedido</h1>
          <p className="text-sm text-muted-foreground">
            Confirme os dados de entrega e a forma de pagamento
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Delivery */}
        <fieldset className="rounded-lg border border-border bg-card p-5 space-y-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Endereço de entrega
          </legend>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">Endereço</label>
            <input
              type="text"
              className={inputClass}
              {...register("delivery_address", { required: "Obrigatório" })}
            />
            {errors.delivery_address && (
              <p className="text-xs text-destructive">{errors.delivery_address.message}</p>
            )}
          </div>
          <div className="grid gap-3 grid-cols-1 md:grid-cols-3">
            <div className="space-y-1 md:col-span-2">
              <label className="text-sm font-medium text-foreground">Cidade</label>
              <input
                type="text"
                className={inputClass}
                {...register("delivery_city", { required: "Obrigatório" })}
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-foreground">UF</label>
              <input
                type="text"
                maxLength={2}
                className={inputClass}
                {...register("delivery_state", { required: "Obrigatório" })}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground">CEP</label>
            <input
              type="text"
              className={inputClass}
              {...register("delivery_zip", { required: "Obrigatório" })}
            />
          </div>
        </fieldset>

        {/* Payment */}
        <fieldset className="rounded-lg border border-border bg-card p-5 space-y-4">
          <legend className="px-2 text-sm font-semibold text-foreground inline-flex items-center gap-2">
            <CreditCard className="h-4 w-4" /> Pagamento
          </legend>
          <div className="space-y-2">
            {(["boleto", "credit_card", "pix"] as const).map((method) => (
              <label
                key={method}
                className="flex items-center gap-3 p-3 rounded-md border border-border hover:bg-muted/30 cursor-pointer"
              >
                <input type="radio" value={method} {...register("payment_method")} />
                <span className="text-sm capitalize text-foreground">
                  {method === "credit_card" ? "Cartão de crédito" : method}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="rounded-lg border border-border bg-card p-5 space-y-2">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Observações
          </legend>
          <textarea
            rows={3}
            className={inputClass}
            placeholder="Informações adicionais (opcional)"
            {...register("notes")}
          />
        </fieldset>

        {/* Summary */}
        <div className="rounded-lg border border-border bg-muted/20 p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">Total do pedido</p>
            <p className="text-2xl font-bold text-foreground">
              {formatBRL(cart?.total ?? 0)}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate("/cart")}
              className="px-4 py-2 rounded-md border border-border text-sm font-medium hover:bg-muted"
            >
              Voltar
            </button>
            <button
              type="submit"
              disabled={checkout.isPending}
              className="px-6 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {checkout.isPending ? "Enviando…" : "Confirmar pedido"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
