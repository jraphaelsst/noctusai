import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { CreditCard, Plus, Trash2 } from 'lucide-react';
import { usePaymentMethods, useAddPaymentMethod, useRemovePaymentMethod } from '@/hooks/usePayments';

const BRAND_ICONS: Record<string, string> = {
  visa: 'Visa',
  mastercard: 'Master',
  amex: 'Amex',
  elo: 'Elo',
};

export default function PaymentMethods() {
  const [addOpen, setAddOpen] = useState(false);
  const [cardNumber, setCardNumber] = useState('');
  const [cardExpiry, setCardExpiry] = useState('');
  const [cardCvc, setCardCvc] = useState('');
  const [cardName, setCardName] = useState('');

  const { data: methods, isLoading } = usePaymentMethods();
  const addMethod = useAddPaymentMethod();
  const removeMethod = useRemovePaymentMethod();

  function handleAddCard() {
    if (!cardNumber || !cardExpiry || !cardCvc) return;
    // In production this would tokenize via Stripe Elements.
    // Here we submit the stub token.
    addMethod.mutate(
      { token: `tok_stub_${Date.now()}`, set_default: (methods?.length ?? 0) === 0 },
      {
        onSuccess: () => {
          setAddOpen(false);
          setCardNumber('');
          setCardExpiry('');
          setCardCvc('');
          setCardName('');
        },
      },
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Metodos de Pagamento</h1>
        <p className="text-muted-foreground">Gerencie seus cartoes e formas de pagamento</p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-lg">Cartoes Salvos</CardTitle>
            <CardDescription>
              Um cartao validado e obrigatorio para realizar agendamentos
            </CardDescription>
          </div>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Adicionar Cartao
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Adicionar Cartao</DialogTitle>
                <DialogDescription>
                  Insira os dados do seu cartao de credito
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label>Nome no Cartao</Label>
                  <Input
                    placeholder="Nome completo"
                    value={cardName}
                    onChange={(e) => setCardName(e.target.value)}
                  />
                </div>
                <div>
                  <Label>Numero do Cartao</Label>
                  <Input
                    placeholder="0000 0000 0000 0000"
                    maxLength={19}
                    value={cardNumber}
                    onChange={(e) => setCardNumber(e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Validade</Label>
                    <Input
                      placeholder="MM/AA"
                      maxLength={5}
                      value={cardExpiry}
                      onChange={(e) => setCardExpiry(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>CVC</Label>
                    <Input
                      placeholder="000"
                      maxLength={4}
                      type="password"
                      value={cardCvc}
                      onChange={(e) => setCardCvc(e.target.value)}
                    />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={handleAddCard}
                  disabled={addMethod.isPending || !cardNumber || !cardExpiry || !cardCvc}
                >
                  {addMethod.isPending ? 'Adicionando...' : 'Adicionar'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Carregando...</p>
          ) : !methods || methods.length === 0 ? (
            <div className="text-center py-8">
              <CreditCard className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                Nenhum metodo de pagamento cadastrado.
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Adicione um cartao para poder agendar sessoes.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {methods.map((method) => (
                <div
                  key={method.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex items-center gap-4">
                    <div className="rounded-md bg-muted p-2">
                      <CreditCard className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {BRAND_ICONS[method.brand.toLowerCase()] ?? method.brand}
                        </span>
                        <span className="text-muted-foreground">
                          **** {method.last4}
                        </span>
                        {method.is_default && (
                          <Badge variant="default" className="text-xs">Padrao</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Expira {String(method.exp_month).padStart(2, '0')}/{method.exp_year}
                      </p>
                    </div>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Remover cartao?</AlertDialogTitle>
                        <AlertDialogDescription>
                          O cartao terminado em {method.last4} sera removido permanentemente.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => removeMethod.mutate(method.id)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          Remover
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
