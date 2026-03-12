import { useState, useEffect } from 'react';
import { useSendWhatsAppProperty, useWhatsAppConfig } from '@/hooks/useWhatsApp';
import { useClientes } from '@/hooks/useClientes';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  MessageCircle,
  Send,
  Phone,
  HomeIcon,
  MapPin,
  BedDouble,
  Car,
  AlertTriangle,
} from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

interface ImovelPreview {
  id: string;
  titulo_anuncio?: string | null;
  tipo_imovel?: string | null;
  valor?: number;
  cidade?: string | null;
  bairro?: string | null;
  estado?: string | null;
  quartos?: number | null;
  vagas?: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  condominio_nome?: string | null;
}

interface SendPropertyModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  imovel: ImovelPreview | null;
}

export function SendPropertyModal({ open, onOpenChange, imovel }: SendPropertyModalProps) {
  const [phone, setPhone] = useState('');
  const [clienteId, setClienteId] = useState<string>('manual');
  const [mensagemAdicional, setMensagemAdicional] = useState('');

  const { data: whatsappConfig } = useWhatsAppConfig();
  const { data: clientes = [] } = useClientes();
  const sendMutation = useSendWhatsAppProperty();

  // When selecting a client, auto-fill phone
  useEffect(() => {
    if (clienteId && clienteId !== 'manual') {
      const cliente = clientes.find((c) => c.id === clienteId);
      if (cliente?.telefone) {
        setPhone(cliente.telefone);
      }
    }
  }, [clienteId, clientes]);

  const handleSend = () => {
    if (!imovel || !phone) return;

    sendMutation.mutate(
      {
        phone,
        imovel_id: imovel.id,
        cliente_id: clienteId !== 'manual' ? clienteId : undefined,
        mensagem_adicional: mensagemAdicional || undefined,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setPhone('');
          setClienteId('manual');
          setMensagemAdicional('');
        },
      }
    );
  };

  const handleClose = () => {
    onOpenChange(false);
    setPhone('');
    setClienteId('manual');
    setMensagemAdicional('');
  };

  if (!imovel) return null;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-green-600" />
            Enviar via WhatsApp
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Dry run warning */}
          {whatsappConfig?.dry_run && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                WhatsApp nao configurado. As mensagens serao simuladas (modo teste).
              </AlertDescription>
            </Alert>
          )}

          {/* Property Preview */}
          <Card>
            <CardContent className="pt-4 space-y-2">
              <div className="flex items-center gap-2">
                <HomeIcon className="h-4 w-4 text-primary" />
                <span className="font-semibold">
                  {imovel.titulo_anuncio || `${(imovel.tipo_imovel || 'Imovel').charAt(0).toUpperCase() + (imovel.tipo_imovel || 'imovel').slice(1)}`}
                </span>
              </div>

              {(imovel.cidade || imovel.bairro) && (
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <MapPin className="h-3 w-3" />
                  {[imovel.bairro, imovel.cidade, imovel.estado].filter(Boolean).join(', ')}
                </div>
              )}

              <div className="flex gap-3 text-sm text-muted-foreground">
                {imovel.quartos && (
                  <span className="flex items-center gap-1">
                    <BedDouble className="h-3 w-3" />{imovel.quartos}q
                  </span>
                )}
                {imovel.vagas && (
                  <span className="flex items-center gap-1">
                    <Car className="h-3 w-3" />{imovel.vagas}v
                  </span>
                )}
                {(imovel.area_total || imovel.area_privativa) && (
                  <span>{imovel.area_total || imovel.area_privativa}m2</span>
                )}
              </div>

              {imovel.valor && (
                <p className="text-lg font-bold text-primary">{formatCurrency(imovel.valor)}</p>
              )}

              {imovel.condominio_nome && (
                <Badge variant="outline">{imovel.condominio_nome}</Badge>
              )}
            </CardContent>
          </Card>

          {/* Recipient */}
          <div className="space-y-3">
            <div className="space-y-2">
              <Label>Selecionar cliente</Label>
              <Select value={clienteId} onValueChange={setClienteId}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione um cliente ou digite manualmente" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Digitar numero manualmente</SelectItem>
                  {clientes.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.nome} {c.telefone ? `(${c.telefone})` : '(sem telefone)'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="phone">
                <Phone className="h-3 w-3 inline mr-1" />
                Numero do WhatsApp
              </Label>
              <Input
                id="phone"
                placeholder="(11) 99999-9999"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                O numero sera normalizado automaticamente para o formato internacional
              </p>
            </div>
          </div>

          {/* Additional Message */}
          <div className="space-y-2">
            <Label htmlFor="mensagem_adicional">Mensagem adicional (opcional)</Label>
            <Textarea
              id="mensagem_adicional"
              placeholder="Ola! Segue um imovel que pode ser do seu interesse..."
              value={mensagemAdicional}
              onChange={(e) => setMensagemAdicional(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancelar
          </Button>
          <Button
            onClick={handleSend}
            disabled={sendMutation.isPending || !phone || phone.length < 8}
            className="bg-green-600 hover:bg-green-700"
          >
            {sendMutation.isPending ? (
              'Enviando...'
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Enviar via WhatsApp
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
